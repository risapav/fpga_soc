"""
builder.py - ModelBuilder: assembles SoCModel from raw YAML + registry.
Single responsibility: transform loaded config into validated dataclasses.
"""

from __future__ import annotations
import os, sys
from typing import List

from models import (
    SoCModel, SoCMode, Peripheral, StandaloneModule,
    ExtPort, IrqLine, RegField, PortDir, RegAccess
)
from loader import ConfigLoader, resolve_size, _fail, _warn

EXTERNAL_IFACE_TYPES = {'serial', 'display', 'gpio', 'video', 'memory', 'interface'}


class ModelBuilder:
    """Builds a validated SoCModel from a ConfigLoader."""

    def __init__(self, loader: ConfigLoader, project_cfg_path: str, root_dir: str):
        self._loader   = loader
        self._proj_path = project_cfg_path
        self._root_dir  = root_dir

    def build(self) -> SoCModel:
        cfg = self._loader.raw_cfg
        soc = cfg.get('soc', {})

        # Determine gen_dir
        default_cfg = os.path.join(self._root_dir, "board", "config", "project_config.yaml")
        is_demo     = (os.path.abspath(self._proj_path) != default_cfg)
        if is_demo:
            demo_root = os.path.normpath(
                os.path.join(os.path.dirname(self._proj_path), ".."))
            gen_dir = os.path.join(demo_root, "gen")
        else:
            gen_dir = os.path.join(self._root_dir, "gen")

        cfg_dir = os.path.join(self._root_dir, "board", "config")
        mode    = SoCMode(cfg.get('demo', {}).get('mode', 'soc'))

        model = SoCModel(
            ram_size   = int(soc.get('ram_size',   32768)),
            clock_freq = int(soc.get('clock_freq', 50_000_000)),
            board_type = cfg.get('board', {}).get('type', 'qmtech_ep4ce55'),
            onboard    = cfg.get('onboard', {}),
            pmod       = cfg.get('pmod', {}),
            mode       = mode,
            gen_dir    = gen_dir,
            cfg_dir    = cfg_dir,
            root_dir   = self._root_dir,
        )

        if mode == SoCMode.STANDALONE:
            model.standalone_modules = self._build_standalone_modules(cfg)
        else:
            model.peripherals = self._build_peripherals(cfg, model.ram_size)
            model.cpu_params  = cfg.get('cpu_params', {})
            cpu_name = cfg.get('soc', {}).get('cpu', 'picorv32')
            model.cpu_type    = cpu_name
            # Read CPU files from ip_registry
            cpu_meta = self._loader.registry.get(cpu_name, {})
            model.cpu_files = cpu_meta.get('files', [f'{cpu_name}/{cpu_name}.v'])

        return model

    # -------------------------------------------------------------------------

    def _build_registers(self, inst_name: str, meta: dict) -> List[RegField]:
        regs    = []
        offsets = set()
        size    = resolve_size(meta.get('address_range', 0x10))

        for r in meta.get('registers', []):
            off   = resolve_size(r['offset']) if isinstance(r['offset'], str) else r['offset']
            name  = r['name']
            acc   = r.get('access', 'rw')
            width = r.get('width', 32)
            reset = r.get('reset', 0)
            desc  = r.get('desc', '')

            if acc not in ('rw', 'ro', 'wo'):
                _fail(f"Register '{name}' on '{inst_name}': access must be rw/ro/wo")
            if off % 4 != 0:
                _fail(f"Register '{name}' on '{inst_name}': offset 0x{off:X} not 4-byte aligned")
            if off >= size:
                _fail(f"Register '{name}' on '{inst_name}': offset 0x{off:X} >= size 0x{size:X}")
            if off in offsets:
                _fail(f"Register offset collision at 0x{off:X} on '{inst_name}'")
            offsets.add(off)

            regs.append(RegField(
                name=name, offset=off,
                access=RegAccess(acc),
                width=width, reset=reset, desc=desc
            ))

        return sorted(regs, key=lambda r: r.offset)

    def _build_ext_ports(self, inst_name: str, meta: dict) -> List[ExtPort]:
        ports = []
        for iface in meta.get('interfaces', []):
            if iface.get('type') not in EXTERNAL_IFACE_TYPES:
                continue
            for sig in iface.get('signals', []):
                name  = sig['name']
                d     = sig['dir']
                w     = sig.get('width', 1)
                tname = sig.get('top_name') or name
                nopfx = sig.get('no_prefix', False)
                tport = tname if nopfx else f"{inst_name}_{tname}"

                if d not in ('output', 'input', 'inout'):
                    _fail(f"Signal '{name}' on '{inst_name}': invalid dir '{d}'")
                if w < 1:
                    _fail(f"Signal '{name}' on '{inst_name}': invalid width {w}")

                ports.append(ExtPort(
                    name=name, dir=PortDir(d), width=w, top_port=tport
                ))
        return ports

    def _build_peripherals(self, cfg: dict, ram_size: int) -> List[Peripheral]:
        enabled = {
            n: c for n, c in cfg.get('peripherals', {}).items()
            if isinstance(c, dict) and c.get('enabled')
        }

        periphs     = []
        addr_ranges = []
        irq_ids     = {}

        for inst, inst_cfg in enabled.items():
            meta, base_type = self._loader.lookup_registry(inst, inst_cfg)

            base     = inst_cfg['base']
            size     = resolve_size(meta.get('address_range', 0x10))
            port_map = meta.get('port_map', {})
            aw       = meta.get('addr_width', 6)

            # Alignment warning
            if size & (size - 1) == 0 and base & (size - 1):
                _warn(f"'{inst}' base 0x{base:08X} not aligned to size 0x{size:X}")

            # addr_width sanity
            min_aw = (size - 1).bit_length()
            if aw < min_aw:
                _warn(f"'{inst}': addr_width={aw} may be too small (need >= {min_aw})")

            # RAM overlap check
            if base <= ram_size - 1:
                _fail(f"'{inst}' base 0x{base:08X} overlaps RAM (0x0..0x{ram_size-1:08X})")

            # Address collision
            end = base + size - 1
            for other, ob, oe in addr_ranges:
                if base <= oe and end >= ob:
                    _fail(f"Address collision: '{inst}' overlaps '{other}'")
            addr_ranges.append((inst, base, end))

            # IRQ validation
            irqs = []
            for irq in meta.get('interrupts', []):
                iid = irq['id']
                if iid in irq_ids:
                    _fail(f"IRQ ID {iid} collision: '{irq_ids[iid]}' and '{inst}'")
                irq_ids[iid] = inst
                irqs.append(IrqLine(id=iid, name=irq['name']))

            ext_ports = self._build_ext_ports(inst, meta)
            registers = self._build_registers(inst, meta)

            # Merge params: registry defaults + project_config overrides
            reg_params = {
                p['name']: p.get('default')
                for p in meta.get('params', [])
                if isinstance(p, dict) and 'name' in p
            }
            reg_params.update(inst_cfg.get('params', {}))

            periphs.append(Peripheral(
                inst=inst, type=base_type,
                module=meta.get('module', f"{base_type}_top"),
                base=base, size=size,
                clk_port=port_map.get('clk',   'SYS_CLK'),
                rst_port=port_map.get('rst_n',  'RESET_N'),
                addr_width=aw,
                ext_ports=ext_ports,
                irqs=irqs,
                registers=registers,
                params=reg_params,
                files=meta.get('files', []),
            ))

        # Top-level port name collision check
        seen = set()
        for p in periphs:
            for ep in p.ext_ports:
                if ep.top_port in seen:
                    _fail(f"soc_top port collision: '{ep.top_port}' in multiple peripherals")
                seen.add(ep.top_port)

        print(f"[OK] Peripherals: {len(periphs)}, IRQs: {len(irq_ids)}, "
              f"no address/IRQ/port collisions.")
        return periphs

    def _build_standalone_modules(self, cfg: dict) -> List[StandaloneModule]:
        mods = []
        for inst, inst_cfg in cfg.get('standalone_modules', {}).items():
            if not inst_cfg.get('enabled', True):
                continue
            mod_type = inst_cfg.get('module', inst)
            if mod_type not in self._loader.registry:
                _fail(f"Standalone module '{inst}' (module: '{mod_type}') "
                      f"not found in ip_registry.yaml.")
            meta  = self._loader.registry[mod_type]
            ports = []
            for iface in meta.get('interfaces', []):
                for sig in iface.get('signals', []):
                    ports.append(ExtPort(
                        name=sig['name'],
                        dir=PortDir(sig['dir']),
                        width=sig.get('width', 1),
                        top_port=sig['name'],
                    ))
            mods.append(StandaloneModule(
                inst=inst, module=mod_type,
                params=inst_cfg.get('params', {}),
                ext_ports=ports,
                files=meta.get('files', []),
            ))
        return mods
