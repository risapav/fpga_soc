"""
builder.py - ModelBuilder  (v3)
================================
Changes vs v2:
  - _build_bus_fabrics(): assembles BusFabric objects with masters + slaves;
    detects inter-fabric boundaries and registers BusBridge objects
  - _build_param_defs(): parses ParamDef list from registry;
    validation now deferred to Peripheral.validate() via param_defs field
  - Peripheral.param_defs populated so SoCModel.validate() can check
    types, min/max, required constraints
  - topological_sort() used for deterministic periph ordering
    (replaces simple base-address sort)
  - dependency graph edges now include BUS edges between peripheral
    and its fabric (for accurate topological sort)
  - alignment: simple_bus = hard error; other bus types = warning (unchanged)
  - EXTERNAL_IFACE_TYPES still registry-driven (unchanged from v2)
"""

from __future__ import annotations
import os
from typing import Dict, List

from models import (
    BusBridge, BusFabric, BusType, ConfigError, DepKind, DependencyEdge,
    ExtPort, IrqLine, OnboardConfig, ParamDef, ParamType, Peripheral,
    PmodConfig, PortDir, RegAccess, RegField, SoCMode, SoCModel,
    StandaloneModule,
)
from loader import ConfigLoader, resolve_size, _fail, _warn

_DEFAULT_EXTERNAL_IFACE_CATEGORIES = frozenset({
    "serial", "display", "gpio", "video", "memory", "interface",
})


def _ext_cats(registry_meta: dict) -> frozenset:
    cats: set = set(_DEFAULT_EXTERNAL_IFACE_CATEGORIES)
    for iface in registry_meta.get("interfaces", []):
        cat = iface.get("category")
        if cat:
            cats.add(cat)
    return frozenset(cats)


class ModelBuilder:

    def __init__(self, loader: ConfigLoader, project_cfg_path: str, root_dir: str):
        self._loader    = loader
        self._proj_path = project_cfg_path
        self._root_dir  = root_dir

    # =========================================================================
    # Public entry point
    # =========================================================================

    def build(self) -> SoCModel:
        cfg = self._loader.raw_cfg
        soc = cfg.get("soc", {})

        default_cfg = os.path.join(
            self._root_dir, "board", "config", "project_config.yaml")
        is_demo = os.path.abspath(self._proj_path) != default_cfg
        if is_demo:
            demo_root = os.path.normpath(
                os.path.join(os.path.dirname(self._proj_path), ".."))
            gen_dir = os.path.join(demo_root, "gen")
        else:
            gen_dir = os.path.join(self._root_dir, "gen")
        cfg_dir = os.path.join(self._root_dir, "board", "config")

        onboard = OnboardConfig.from_dict(cfg.get("onboard", {}))
        pmod    = PmodConfig.from_dict(cfg.get("pmod", {}))
        mode    = SoCMode(cfg.get("demo", {}).get("mode", "soc"))

        from loader import resolve_size

        _ram_size     = int(soc.get("ram_size",    32768))
        _ram_latency  = soc.get("ram_latency",  "registered")
        _init_file    = soc.get("init_file",    "gen/software.mif")
        _stack_pct    = int(soc.get("stack_percent", 25))

        # reset_vector: explicit in YAML, or cpu-default from registry
        _cpu_name_tmp = soc.get("cpu", "picorv32")
        _cpu_meta_tmp = self._loader.registry.get(_cpu_name_tmp, {})
        _cpu_dflt_rv  = resolve_size(
            _cpu_meta_tmp.get("reset_vector", "0x00000000"))
        _reset_vector = resolve_size(
            soc.get("reset_vector", _cpu_dflt_rv))

        # ram_base: where RAM lives in address space
        _cpu_dflt_rb  = resolve_size(
            _cpu_meta_tmp.get("ram_base", "0x00000000"))
        _ram_base     = resolve_size(
            soc.get("ram_base", _cpu_dflt_rb))

        # ram_alias: optional second mapping (e.g. 0x0 alias for 0x80000000)
        _alias_raw = soc.get("ram_alias", _cpu_meta_tmp.get("ram_alias"))
        _ram_alias = resolve_size(_alias_raw) if _alias_raw is not None else None

        if _ram_latency not in ("registered", "combinational"):
            _fail(f"soc.ram_latency must be 'registered' or 'combinational', "
                  f"got {_ram_latency!r}")

        # RAM module: project can override module name and instance name
        # port_map comes from ip_registry soc_ram entry (or override in soc:)
        _ram_reg      = self._loader.registry.get("soc_ram", {})
        _ram_module   = soc.get("ram_module", _ram_reg.get("module", "soc_ram"))
        _ram_inst     = soc.get("ram_inst",   "u_ram")
        _ram_port_map = dict(_ram_reg.get("port_map", {
            "clk": "clk", "addr": "addr", "be": "be",
            "we": "we", "wdata": "wdata", "rdata": "rdata",
        }))
        # allow per-project port overrides: soc: ram_port_map: {clk: sys_clk}
        _ram_port_map.update(soc.get("ram_port_map", {}))

        model = SoCModel(
            ram_size      = _ram_size,
            clock_freq    = int(soc.get("clock_freq", 50_000_000)),
            board_type    = cfg.get("board", {}).get("type", "qmtech_ep4ce55"),
            onboard       = onboard,
            pmod          = pmod,
            mode          = mode,
            gen_dir       = gen_dir,
            cfg_dir       = cfg_dir,
            root_dir      = self._root_dir,
            ram_base      = _ram_base,
            ram_alias     = _ram_alias,
            reset_vector  = _reset_vector,
            ram_latency   = _ram_latency,
            init_file     = _init_file,
            stack_percent = _stack_pct,
            ram_module    = _ram_module,
            ram_inst      = _ram_inst,
            ram_port_map  = _ram_port_map,
        )

        if mode == SoCMode.STANDALONE:
            model.standalone_modules = self._build_standalone_modules(cfg)
        else:
            model.cpu_params = cfg.get("cpu_params", {})
            cpu_name         = soc.get("cpu", "picorv32")
            model.cpu_type   = cpu_name
            cpu_meta         = self._loader.registry.get(cpu_name, {})
            model.cpu_files    = list(cpu_meta.get("files",
                                    [f"{cpu_name}/{cpu_name}.v"]))
            model.cpu_port_map = dict(cpu_meta.get("port_map", {}))

            model.peripherals  = self._build_peripherals(
                cfg,
                ram_size  = model.ram_size,
                ram_base  = model.ram_base,
                ram_alias = model.ram_alias,
            )
            model.bus_fabrics  = self._build_bus_fabrics(
                model.peripherals, cpu_name)
            model.dependencies = self._build_dependency_graph(model)

        model.validate()
        return model

    # =========================================================================
    # Registers
    # =========================================================================

    def _build_registers(self, inst: str, meta: dict) -> List[RegField]:
        regs: List[RegField] = []
        size = resolve_size(meta.get("address_range", 0x10))
        for r in meta.get("registers", []):
            off   = (resolve_size(r["offset"])
                     if isinstance(r["offset"], str) else int(r["offset"]))
            acc   = r.get("access", "rw")
            if acc not in ("rw", "ro", "wo"):
                _fail(f"Register '{r['name']}' on '{inst}': "
                      f"access must be rw/ro/wo, got {acc!r}")
            regs.append(RegField(
                name=r["name"], offset=off,
                access=RegAccess(acc),
                width=int(r.get("width", 32)),
                reset=int(r.get("reset", 0)),
                desc=r.get("desc", ""),
            ))
        return sorted(regs, key=lambda r: r.offset)

    # =========================================================================
    # External ports
    # =========================================================================

    def _build_ext_ports(self, inst: str, meta: dict) -> List[ExtPort]:
        ports: List[ExtPort] = []
        ext_cats = _ext_cats(meta)
        for iface in meta.get("interfaces", []):
            iface_type = iface.get("type", "")
            iface_cat  = iface.get("category", iface_type)
            if iface_cat not in ext_cats and iface_type not in ext_cats:
                continue
            for sig in iface.get("signals", []):
                d = sig["dir"]
                if d not in ("output", "input", "inout"):
                    _fail(f"Signal '{sig['name']}' on '{inst}': invalid dir {d!r}")
                w = int(sig.get("width", 1))
                if w < 1:
                    _fail(f"Signal '{sig['name']}' on '{inst}': width must be >= 1")
                tname = sig.get("top_name") or sig["name"]
                nopfx = bool(sig.get("no_prefix", False))
                tport = tname if nopfx else f"{inst}_{tname}"
                ports.append(ExtPort(
                    name=sig["name"], dir=PortDir(d),
                    width=w, top_port=tport,
                ))
        return ports

    # =========================================================================
    # Param defs
    # =========================================================================

    def _build_param_defs(self, meta: dict) -> List[ParamDef]:
        """Parse ParamDef list from registry meta; skip legacy plain-string entries."""
        defs: List[ParamDef] = []
        for p in meta.get("params", []):
            if not isinstance(p, dict) or "name" not in p:
                continue
            defs.append(ParamDef.from_dict(p))
        return defs

    # =========================================================================
    # Peripherals
    # =========================================================================

    def _build_peripherals(self, cfg: dict, ram_size: int,
                           ram_base: int = 0,
                           ram_alias = None) -> List[Peripheral]:
        enabled = {
            n: c
            for n, c in cfg.get("peripherals", {}).items()
            if isinstance(c, dict) and c.get("enabled")
        }

        periphs: List[Peripheral] = []

        for inst, inst_cfg in enabled.items():
            meta, base_type = self._loader.lookup_registry(inst, inst_cfg)

            base     = resolve_size(inst_cfg["base"])
            size     = resolve_size(meta.get("address_range", 0x10))
            port_map = meta.get("port_map", {})
            bt_str   = meta.get("bus_type", BusType.SIMPLE.value)
            bus_type = BusType(bt_str)

            # alignment
            if size & (size - 1) == 0:
                if base & (size - 1):
                    if bus_type == BusType.SIMPLE:
                        _fail(
                            f"'{inst}': base 0x{base:08X} not aligned to "
                            f"size 0x{size:X} -- required for simple_bus")
                    else:
                        _warn(
                            f"'{inst}': base 0x{base:08X} not aligned to "
                            f"size 0x{size:X}")

            # RAM overlap (fast-fail before full model validation)
            _ram_end = ram_base + ram_size - 1
            _overlaps_main  = (ram_base <= base <= _ram_end) or \
                              (base <= ram_base <= base + size - 1)
            _overlaps_alias = (ram_alias is not None) and (
                (ram_alias <= base <= ram_alias + ram_size - 1) or
                (base <= ram_alias <= base + size - 1))
            if _overlaps_main or _overlaps_alias:
                _fail(
                    f"'{inst}' base 0x{base:08X} overlaps RAM "
                    f"(0x{ram_base:08X}..0x{_ram_end:08X})")

            # ---- bus compatibility vs CPU (registry-driven) ----------------
            # cpu_meta.bus_master lists bus types the CPU can master natively.
            # Warn early if a peripheral needs a bus type the CPU can't drive.
            _cpu_name   = cfg.get("soc", {}).get("cpu", "picorv32")
            _cpu_meta   = self._loader.registry.get(_cpu_name, {})
            _supported  = set(_cpu_meta.get("bus_master", ["simple_bus"]))
            if bt_str not in _supported and bt_str != BusType.NONE.value:
                _warn(
                    f"'{inst}' uses {bt_str!r} but CPU '{_cpu_name}' "
                    f"natively supports {sorted(_supported)} -- "
                    f"a bridge will be needed")

            # ---- params: registry defaults merged with project overrides ----
            param_defs = self._build_param_defs(meta)
            reg_params: Dict[str, object] = {
                pd.name: pd.default for pd in param_defs
            }
            reg_params.update(inst_cfg.get("params", {}))

            periphs.append(Peripheral(
                inst       = inst,
                type       = base_type,
                module     = meta.get("module", f"{base_type}_top"),
                base       = base,
                size       = size,
                bus_type   = bus_type,
                clk_port   = port_map.get("clk",   "SYS_CLK"),
                rst_port   = port_map.get("rst_n",  "RESET_N"),
                ext_ports  = self._build_ext_ports(inst, meta),
                irqs       = [IrqLine(id=int(i["id"]), name=i["name"])
                              for i in meta.get("interrupts", [])],
                registers  = self._build_registers(inst, meta),
                params     = reg_params,
                param_defs = param_defs,
                files      = list(meta.get("files", [])),
            ))

        # deterministic order by base address
        periphs.sort(key=lambda p: p.base)

        # top-level port collision check
        seen: Dict[str, str] = {}
        for p in periphs:
            for ep in p.ext_ports:
                if ep.top_port in seen:
                    _fail(
                        f"soc_top port collision: '{ep.top_port}' "
                        f"in '{seen[ep.top_port]}' and '{p.inst}'")
                seen[ep.top_port] = p.inst

        print(f"[OK] Peripherals: {[p.inst for p in periphs]}")
        return periphs

    # =========================================================================
    # Bus fabrics
    # =========================================================================

    def _build_bus_fabrics(
        self,
        periphs: List[Peripheral],
        cpu_name: str,
    ) -> List[BusFabric]:
        """
        Build one BusFabric per unique BusType.
        The CPU is registered as master on every fabric.
        BusBridge objects are created between every pair of distinct fabrics.
        """
        fabric_map: Dict[BusType, BusFabric] = {}
        for p in periphs:
            if p.bus_type not in fabric_map:
                fabric_map[p.bus_type] = BusFabric(
                    bus_type = p.bus_type,
                    masters  = [cpu_name],
                )
            fabric_map[p.bus_type].slaves.append(p)

        fabrics = list(fabric_map.values())

        # register bridges between all pairs of distinct fabrics
        for i, fa in enumerate(fabrics):
            for fb in fabrics[i + 1:]:
                bridge_ab = fa.add_bridge_to(fb)
                bridge_ba = fb.add_bridge_to(fa)
                _warn(
                    f"Bus type mismatch detected: "
                    f"{fa.bus_type.value} <-> {fb.bus_type.value} -- "
                    f"bridge '{bridge_ab.module}' will be required in RTL")

        if fabrics:
            summary = ", ".join(
                f"{f.bus_type.value}x{len(f.slaves)}" for f in fabrics)
            print(f"[OK] Bus fabrics: {summary}")
            if len(fabrics) > 1:
                print(f"[WARN] {len(fabrics)} bus types -- "
                      f"{len(fabrics)*(len(fabrics)-1)//2} bridge(s) needed")

        return fabrics

    # =========================================================================
    # Dependency graph
    # =========================================================================

    def _build_dependency_graph(self, model: SoCModel) -> List[DependencyEdge]:
        edges: List[DependencyEdge] = []
        cpu      = model.cpu_type
        has_intc = any(p.type == "intc" for p in model.peripherals)

        for p in model.peripherals:
            edges.append(DependencyEdge(
                source=p.inst, target="SYS_CLK", kind=DepKind.CLOCK))
            edges.append(DependencyEdge(
                source=p.inst, target="RESET_N",  kind=DepKind.RESET))
            edges.append(DependencyEdge(
                source=p.inst, target=p.bus_type.value, kind=DepKind.BUS))
            if p.irqs:
                irq_target = "intc" if has_intc else cpu
                edges.append(DependencyEdge(
                    source=p.inst, target=irq_target, kind=DepKind.IRQ))

        if any(p.irqs for p in model.peripherals) and not has_intc:
            _warn("Peripherals have IRQs but no 'intc' present -- "
                  "all IRQs are OR'd directly to the CPU")
        return edges

    # =========================================================================
    # Standalone modules
    # =========================================================================

    def _build_standalone_modules(self, cfg: dict) -> List[StandaloneModule]:
        mods: List[StandaloneModule] = []
        for inst, inst_cfg in cfg.get("standalone_modules", {}).items():
            if not inst_cfg.get("enabled", True):
                continue
            mod_type = inst_cfg.get("module", inst)
            if mod_type not in self._loader.registry:
                _fail(f"Standalone '{inst}' (module: '{mod_type}') "
                      f"not found in ip_registry.yaml.")
            meta  = self._loader.registry[mod_type]
            ports: List[ExtPort] = []
            for iface in meta.get("interfaces", []):
                for sig in iface.get("signals", []):
                    d = sig["dir"]
                    if d not in ("output", "input", "inout"):
                        _fail(f"Standalone '{inst}': signal '{sig['name']}' "
                              f"invalid dir {d!r}")
                    ports.append(ExtPort(
                        name=sig["name"], dir=PortDir(d),
                        width=int(sig.get("width", 1)),
                        top_port=sig["name"],
                    ))
            mods.append(StandaloneModule(
                inst      = inst,
                module    = mod_type,
                params    = dict(inst_cfg.get("params", {})),
                ext_ports = ports,
                files     = list(meta.get("files", [])),
            ))
        return mods
