#!/usr/bin/env python3
"""
gen_config.py  --  QMTech Cyclone IV RISC-V SoC Framework Generator  (v3)
=========================================================================
Changes vs v2:
  - JsonExporter integrated: soc_map.json written alongside .h / .md
  - GraphvizExporter integrated: soc_graph.dot (+ optional PNG) generated
  - dry-run shows topological sort order, bus fabrics, bridge warnings
  - --explain <inst>: prints registry entry + params + registers for one peripheral
  - --graph: force graphviz export even without --dry-run
  - --graph-clk-rst: include clock/reset edges in graph
  - --warnings-as-errors: treat all [WARN] as fatal (unchanged from v2)
  - sys.exit only at the CLI boundary (unchanged from v2)
"""

import os
import sys
import hashlib
import argparse
import loader as _loader_mod  # for _WARNINGS_AS_ERRORS flag

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import ConfigError, SoCMode, SoCModel
from loader import ConfigLoader
from builder import ModelBuilder
from export import GraphvizExporter, JsonExporter
from generators.rtl import RTLGenerator
from generators.sw  import SWGenerator
from generators.tcl import TCLGenerator


# =============================================================================
# Orchestrator
# =============================================================================

class SoCOrchestrator:

    def __init__(self, project_cfg_override=None):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir   = os.path.normpath(
            os.path.join(self.script_dir, "..", ".."))
        cfg_dir     = os.path.join(self.root_dir, "board", "config")
        default_cfg = os.path.join(cfg_dir, "project_config.yaml")
        proj_path   = os.path.abspath(project_cfg_override or default_cfg)
        reg_path    = os.path.join(cfg_dir, "ip_registry.yaml")
        loader      = ConfigLoader(proj_path, reg_path)
        builder     = ModelBuilder(loader, proj_path, self.root_dir)
        self.model  = builder.build()
        self._loader = loader

    # -------------------------------------------------------------------------

    def generate_all(self, dry_run=False, export_graph=False,
                     graph_clk_rst=False) -> None:
        m       = self.model
        gen_dir = m.gen_dir
        cfg_dir = m.cfg_dir

        if dry_run:
            self._dry_run_report()
            return

        os.makedirs(gen_dir, exist_ok=True)
        os.makedirs(cfg_dir, exist_ok=True)

        rtl = RTLGenerator(m)
        sw  = SWGenerator(m)
        tcl = TCLGenerator(m)

        if m.mode == SoCMode.STANDALONE:
            self._gen_standalone(gen_dir, cfg_dir, rtl, tcl)
        else:
            self._gen_soc(gen_dir, cfg_dir, rtl, sw, tcl)

        # JSON export (always)
        JsonExporter(m).generate(os.path.join(gen_dir, "soc_map.json"))

        # Graphviz export (opt-in, or always for multi-fabric SoCs)
        if export_graph or len(m.bus_fabrics) > 1:
            dot_path = os.path.join(gen_dir, "soc_graph.dot")
            gv = GraphvizExporter(m, show_clk_rst=graph_clk_rst)
            gv.generate(dot_path)
            gv.render_png(dot_path)   # no-op if `dot` not installed

    # -------------------------------------------------------------------------

    def explain(self, inst_name: str) -> None:
        """Print registry entry + resolved params + registers for one peripheral."""
        m = self.model
        # find in model
        periph = next((p for p in m.peripherals if p.inst == inst_name), None)
        if periph is None:
            print(f"[ERROR] '{inst_name}' not found in model "
                  f"(available: {[p.inst for p in m.peripherals]})")
            return

        print(f"\n{'='*60}")
        print(f"  Peripheral: {periph.inst}  (type: {periph.type})")
        print(f"  Module:     {periph.module}")
        print(f"  Base:       0x{periph.base:08X}")
        print(f"  End:        0x{periph.end_addr:08X}")
        print(f"  Size:       0x{periph.size:X} ({periph.size} bytes)")
        print(f"  Bus type:   {periph.bus_type.value}")
        print(f"  addr_width: {periph.addr_width}  (computed)")
        print(f"  clk_port:   {periph.clk_port}")
        print(f"  rst_port:   {periph.rst_port}")

        if periph.params:
            print(f"\n  Params:")
            for k, v in periph.params.items():
                pdef = next((pd for pd in periph.param_defs if pd.name == k), None)
                tinfo = f"  [{pdef.type.value}]" if pdef else ""
                rinfo = ""
                if pdef:
                    parts = []
                    if pdef.min is not None:
                        parts.append(f"min={pdef.min}")
                    if pdef.max is not None:
                        parts.append(f"max={pdef.max}")
                    if pdef.required:
                        parts.append("required")
                    if parts:
                        rinfo = f"  ({', '.join(parts)})"
                print(f"    {k:<20} = {v}{tinfo}{rinfo}")

        if periph.registers:
            print(f"\n  Registers:")
            print(f"    {'Offset':<8} {'Name':<16} {'Access':<6} "
                  f"{'Width':<6} {'Reset':<10} Description")
            print(f"    {'-'*8} {'-'*16} {'-'*6} {'-'*6} {'-'*10} -----------")
            for r in periph.registers:
                print(f"    0x{r.offset:04X}   {r.name:<16} "
                      f"{r.access.value:<6} {r.width:<6} "
                      f"0x{r.reset:08X} {r.desc}")

        if periph.irqs:
            print(f"\n  IRQs:")
            for irq in periph.irqs:
                print(f"    [{irq.id}] {periph.inst.upper()}_{irq.name.upper()}_IRQ")

        if periph.ext_ports:
            print(f"\n  External ports:")
            for ep in periph.ext_ports:
                ws = f"[{ep.width-1}:0]" if ep.width > 1 else "     "
                print(f"    {ep.dir.value:<8} {ws} {ep.top_port}")

        print(f"{'='*60}\n")

    # -------------------------------------------------------------------------

    def _gen_standalone(self, gen_dir, cfg_dir, rtl, tcl):
        m = self.model
        print(f"\n[DEMO] Standalone -> {gen_dir}\n")
        rtl.generate_soc_top(os.path.join(gen_dir, "soc_top.sv"))
        tcl.generate_tcl_config(os.path.join(cfg_dir, "generated_config.tcl"))
        static_mods = []
        for mo in m.standalone_modules:
            for f in (mo.files or [f"{mo.module}.sv"]):
                static_mods.append(f"../../src/soc/static/{f}")
        tcl.generate_files_tcl(
            os.path.join(gen_dir, "files.tcl"),
            "gen/soc_top.sv", static_mods)
        tcl.generate_board_hal(os.path.join(gen_dir, "hal", "board.tcl"))
        print("\n[OK] Done: soc_top.sv  files.tcl  generated_config.tcl")

    def _gen_soc(self, gen_dir, cfg_dir, rtl, sw, tcl):
        m = self.model
        print(f"\n[GEN] SoC -> {gen_dir}")
        print(f"      CPU: {m.cpu_type}  |  "
              f"Peripherals (topo order): "
              f"{[p.inst for p in m.topological_sort()]}\n")
        rtl.generate_interfaces(os.path.join(gen_dir, "soc_interfaces.sv"))
        rtl.generate_soc_top(os.path.join(gen_dir, "soc_top.sv"))
        sw.generate_soc_map_h(os.path.join(gen_dir, "soc_map.h"))
        sw.generate_soc_irq_h(os.path.join(gen_dir, "soc_irq.h"))
        sw.generate_linker_script(os.path.join(gen_dir, "sections.lds"))
        sw.generate_ram_size_mk(os.path.join(gen_dir, "ram_size.mk"))
        sw.generate_soc_map_md(os.path.join(gen_dir, "soc_map.md"))
        tcl.generate_tcl_config(os.path.join(cfg_dir, "generated_config.tcl"))

        reg_sv_files = []
        for p in m.peripherals:
            if p.registers:
                rp = os.path.join(gen_dir, f"{p.module}_regs.sv")
                rtl.generate_reg_block(p, rp)
                reg_sv_files.append(f"gen/{p.module}_regs.sv")

        static_mods = ["../../src/soc/static/soc_ram.sv"]
        for p in m.peripherals:
            for f in (p.files or [f"{p.module}.sv"]):
                static_mods.append(f"../../src/soc/static/{f}")

        qsf_dir = os.path.dirname(gen_dir)
        rtl.verify_static_files(static_mods, qsf_dir, m.root_dir)

        tcl.generate_files_tcl(
            os.path.join(gen_dir, "files.tcl"),
            "gen/soc_top.sv",
            static_mods,
            reg_sv_files
            + ["gen/soc_interfaces.sv"]
            + [f"../../src/cpu/{f}" for f in m.cpu_files],
        )
        tcl.generate_board_hal(os.path.join(gen_dir, "hal", "board.tcl"))
        print(f"\n[OK] Done -- all files in {gen_dir}")

    # -------------------------------------------------------------------------

    def _dry_run_report(self):
        m = self.model
        print(f"\n[DRY-RUN] Output : {m.gen_dir}  (mode: {m.mode.value})")
        print(f"          CPU    : {m.cpu_type}  @"
              f"  {m.clock_freq // 1_000_000} MHz")

        if m.mode == SoCMode.SOC:
            # memory map
            print(f"\n  {'Region':<20} {'Base':>12}  {'End':>12}  "
                  f"{'Size':>8}  Bus            Module")
            print(f"  {'-'*20} {'-'*12}  {'-'*12}  "
                  f"{'-'*8}  {'-'*14} ------")
            print(f"  {'RAM':<20} {'0x00000000':>12}  "
                  f"{'0x'+f'{m.ram_size-1:08X}':>12}  "
                  f"{str(m.ram_size)+' B':>8}  {'--':14} soc_ram")
            for p in m.peripherals:
                ri = f"  [{len(p.registers)} regs]" if p.registers else ""
                pi = f"  [{len(p.param_defs)} params]" if p.param_defs else ""
                print(f"  {p.inst:<20} {'0x'+f'{p.base:08X}':>12}  "
                      f"{'0x'+f'{p.end_addr:08X}':>12}  "
                      f"{'0x'+f'{p.size:X}':>8}  "
                      f"{p.bus_type.value:<14} {p.module}{ri}{pi}")

            # bus fabrics
            if m.bus_fabrics:
                print("\n  Bus fabrics:")
                for fab in m.bus_fabrics:
                    slaves = [p.inst for p in fab.slaves]
                    print(f"    {fab.bus_type.value:<14} "
                          f"master={fab.masters}  slaves={slaves}")
                    for bridge in fab.bridges:
                        print(f"      bridge -> {bridge.to_type.value}  "
                              f"module={bridge.module}")

            # topological sort order
            topo = m.topological_sort()
            print(f"\n  Instantiation order (topological):")
            print(f"    {' -> '.join(p.inst for p in topo)}")

            # IRQs
            if any(p.irqs for p in m.peripherals):
                print("\n  IRQs:")
                for p in m.peripherals:
                    for irq in p.irqs:
                        print(f"    [{irq.id}] {p.inst}.{irq.name}")

        else:
            for mo in m.standalone_modules:
                print(f"  Module: {mo.module}  inst: {mo.inst}")

        print("\n[DRY-RUN] Validation passed -- no files written.\n")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    _hash = hashlib.md5(open(__file__, "rb").read()).hexdigest()[:8]
    parser = argparse.ArgumentParser(
        description="SoC Framework Generator v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config",   default=None,
                        help="Path to project_config.yaml")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Validate and print map, no file writes")
    parser.add_argument("--explain",  metavar="INST",
                        help="Show registry details for one peripheral instance")
    parser.add_argument("--graph",    action="store_true",
                        help="Generate soc_graph.dot (+ PNG if dot is available)")
    parser.add_argument("--graph-clk-rst", action="store_true",
                        help="Include clock/reset edges in graph (verbose)")
    parser.add_argument("--warnings-as-errors", action="store_true",
                        help="Treat all [WARN] as fatal errors")
    args = parser.parse_args()

    if args.warnings_as_errors:
        import loader as _lm
        _lm._WARNINGS_AS_ERRORS = True

    print(f"[GEN] gen_config.py  rev:{_hash}")
    try:
        orch = SoCOrchestrator(project_cfg_override=args.config)

        if args.explain:
            orch.explain(args.explain)
        else:
            orch.generate_all(
                dry_run      = args.dry_run,
                export_graph = args.graph,
                graph_clk_rst= args.graph_clk_rst,
            )
    except ConfigError as e:
        print(f"\n[FATAL] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)
