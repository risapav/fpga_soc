"""
generators/rtl.py - RTL file generator (soc_top.sv, reg blocks, interfaces).
Uses Jinja2 templates.
"""

from __future__ import annotations
import os, sys
from datetime import datetime
from models import SoCModel, SoCMode, Peripheral
from generators.base import render, write

def _fail(msg):
    print(f"[ERROR] {msg}")
    sys.exit(1)

class RTLGenerator:

    def __init__(self, model: SoCModel):
        self.m = model

    def generate_interfaces(self, path: str) -> None:
        content = render("soc_interfaces.sv.j2")
        write(path, content)
        print("  -> soc_interfaces.sv")

    def generate_soc_top(self, path: str) -> None:
        ctx = self._get_soc_top_context()
        content = render("soc_top.sv.j2", **ctx)
        write(path, content)
        mode_str = "standalone" if self.m.mode == SoCMode.STANDALONE else "SoC mode"
        print(f"  -> soc_top.sv ({mode_str})")

    def generate_reg_block(self, p: Peripheral, path: str) -> None:
        module_name = f"{p.module}_regs"
        content = render("periph_regs.sv.j2", p=p, module_name=module_name)
        write(path, content)
        print(f"  -> {os.path.basename(path)}")

    def _get_soc_top_context(self) -> dict:
        m  = self.m
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Unique external ports
        ext_ports_dict = {}
        for p in getattr(m, 'peripherals', []):
            for ep in p.ext_ports:
                if ep.top_port not in ext_ports_dict:
                    ext_ports_dict[ep.top_port] = ep
        for sm in getattr(m, 'standalone_modules', []):
            for ep in sm.ext_ports:
                if ep.top_port not in ext_ports_dict:
                    ext_ports_dict[ep.top_port] = ep
        ext_ports = list(ext_ports_dict.values())

        # 2. Internal wires (PLL outputs + rst_sync outputs + internal_ports)
        internal_wires = []
        internal_wire_names = set()
        if m.clock_tree_node:
            for sig, w in m.clock_tree_node.internal_wires():
                internal_wires.append((sig, w))
                internal_wire_names.add(sig)
        for sm in getattr(m, 'standalone_modules', []):
            for ep in getattr(sm, "internal_ports", []):
                if ep.top_port not in internal_wire_names:
                    internal_wires.append((ep.top_port, ep.width))
                    internal_wire_names.add(ep.top_port)

        # 3. CPU params (SOC mode only)
        cpu_params = {}
        if m.mode == SoCMode.SOC and m.cpu_node:
            _latched  = "1" if m.ram_latency == "registered" else "0"
            _progaddr = f"32'h{m.reset_vector:08X}"
            cpu_params = {
                "ENABLE_IRQ":        "1",
                "LATCHED_MEM_RDATA": _latched,
                "PROGADDR_RESET":    _progaddr,
            }
            cpu_params.update(getattr(m.cpu_node.cpu, 'params', {}))

        # 4. Used IRQ IDs (for tie-off of unused lines)
        used_irqs = [irq.id
                     for p in getattr(m, 'peripherals', [])
                     for irq in p.irqs]

        return {
            "timestamp":          ts,
            "mode":               m.mode.value,
            "board_type":         m.board_type,
            "clock_mhz":          m.clock_freq // 1_000_000,
            "ext_ports":          ext_ports,
            "internal_wires":     sorted(internal_wires, key=lambda x: x[0]),
            "reset_syncs":        m.reset_syncs,
            "standalone_modules": getattr(m, 'standalone_modules', []),
            "peripherals":        getattr(m, 'peripherals', []),
            "ram_size":           getattr(m, 'ram_size',    0),
            "ram_base":           getattr(m, 'ram_base',    0),
            "ram_alias":          getattr(m, 'ram_alias',   None),
            "ram_latency":        getattr(m, 'ram_latency', 'registered'),
            "ram_addr_top":       getattr(m, 'ram_addr_top', 31),
            "ram_module":         getattr(m, 'ram_module',  'soc_ram'),
            "ram_inst":           getattr(m, 'ram_inst',    'u_ram'),
            "init_file":          getattr(m, 'init_file',   'gen/software.mif'),
            "cpu_type":           getattr(m, 'cpu_type',    'none'),
            "cpu_params":         cpu_params,
            "cpu_port_map":       getattr(m, 'cpu_port_map', {}),
            "used_irqs":          used_irqs,
        }

    def verify_static_files(self, static_mods: list,
                            qsf_dir: str, root_dir: str) -> None:
        for rel in static_mods:
            abs_path = os.path.normpath(os.path.join(qsf_dir, rel))
            if not os.path.exists(abs_path):
                _fail(
                    f"Missing RTL file: {abs_path}\n"
                    f"  Create {os.path.relpath(abs_path, root_dir)} "
                    f"or remove the peripheral from project_config.yaml."
                )
