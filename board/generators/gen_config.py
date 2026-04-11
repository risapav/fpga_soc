"""
gen_config.py - SoC Framework Orchestrator (v6)
================================================
Changes vs v5:
  - Build pipeline is now fully connected:
      Loader -> Builder -> RTLGenerator / SWGenerator / TCLGenerator / Exporters
  - Supports two registry modes (automatically detected):
      A) Classic:  --registry path/to/ip_registry.yaml
      B) Plugin:   paths.ip_plugins in project_config.yaml (no --registry needed)
      C) Both:     base registry + plugin overrides
  - Exit codes:
      0  success
      1  configuration / schema / validation error
      2  critical runtime error (IO, template, unexpected)
  - Output contract (gen/ subdirs created unconditionally):
      gen/rtl/soc_interfaces.sv
      gen/rtl/soc_top.sv
      gen/rtl/<inst>_regs.sv    (one per peripheral with registers)
      gen/sw/soc_map.h
      gen/sw/soc_irq.h
      gen/sw/sections.lds
      gen/sw/ram_size.mk
      gen/doc/soc_map.md
      gen/doc/soc_graph.dot
      gen/doc/soc_map.json
      gen/hal/board.tcl
      gen/tcl/generated_config.tcl
      gen/tcl/files.tcl
"""

import os
import sys
import argparse

from loader import ConfigLoader
from builder import ModelBuilder
from models import ConfigError, SoCMode

# Generator imports (these are in generators/ sub-package)
try:
    from generators.rtl import RTLGenerator
    from generators.sw  import SWGenerator
    from generators.tcl import TCLGenerator
except ImportError as _imp_err:
    # Allow running from repo root where generators/ is a sibling directory
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _here)
    try:
        from generators.rtl import RTLGenerator
        from generators.sw  import SWGenerator
        from generators.tcl import TCLGenerator
    except ImportError:
        raise ImportError(
            f"Cannot import generator modules: {_imp_err}\n"
            "Ensure generators/rtl.py, sw.py, tcl.py exist."
        ) from _imp_err

from export import GraphvizExporter, JsonExporter
from structure_exporter import StructureExporter
from timing_loader import TimingLoader


# =============================================================================
# Orchestrator
# =============================================================================

class SoCOrchestrator:

    def __init__(self, config_path: str, registry_path: str = "",
                 out_dir: str = "gen", verbose: bool = False):
        self.verbose  = verbose
        self.out_dir  = os.path.abspath(out_dir)
        self._setup_output_dirs()

        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Auto-detect base registry path if not explicitly given
        if not registry_path:
            candidate = os.path.normpath(
                os.path.join(script_dir, "..", "board", "config",
                             "ip_registry.yaml"))
            if os.path.exists(candidate):
                registry_path = candidate
                self.log(f"Auto-detected registry: {candidate}")
            else:
                self.log("No ip_registry.yaml found -- relying on ip_plugins only")

        self.log("=" * 60)
        self.log("SoC Build System  (gen_config.py v6)")
        self.log(f"  Config:   {os.path.abspath(config_path)}")
        if registry_path:
            self.log(f"  Registry: {registry_path}")
        self.log(f"  Output:   {self.out_dir}")
        self.log("=" * 60)

        # Phase 1: LOAD
        try:
            self.loader = ConfigLoader(config_path, registry_path)
        except ConfigError as e:
            self.error(f"Load phase failed:\n{e}")
            sys.exit(1)

    # ------------------------------------------------------------------

    def _setup_output_dirs(self):
        for sd in ("rtl", "sw", "tcl", "doc", "hal"):
            os.makedirs(os.path.join(self.out_dir, sd), exist_ok=True)

    def log(self, msg: str):
        print(f"[INFO] {msg}")

    def error(self, msg: str):
        print(f"[ERROR] {msg}", file=sys.stderr)

    def _p(self, *parts) -> str:
        """Join out_dir with path parts."""
        return os.path.join(self.out_dir, *parts)

    # ------------------------------------------------------------------

    def _build_model(self):
        """Phase 2: BUILD (Raw Data -> validated SoCModel)."""
        self.log("Building SoC model (address allocation & bus stitching)...")
        try:
            model = ModelBuilder(
                self.loader.raw_cfg,
                self.loader.registry,
            ).build(timing_cfg=self._timing_cfg)
        except ConfigError as e:
            self.error(f"Build phase failed:\n{e}")
            sys.exit(1)

        self.log(f"  mode        : {model.mode.value}")
        self.log(f"  active nodes: {model.active_nodes()}")
        self.log(f"  peripherals : {len(model.peripherals)}")
        self.log(f"  standalone  : {len(model.standalone_modules)}")
        if model.cpu_node:
            self.log(f"  cpu         : {model.cpu_type}")
            self.log(f"  ram         : {model.ram_size} B @ "
                     f"0x{model.ram_base:08X}  (latency={model.ram_latency})")
            self.log(f"  reset vec   : 0x{model.reset_vector:08X}")
        if model.clock_tree_node:
            plls = model.clock_tree_node.plls
            self.log(f"  clock tree  : "
                     f"{len(model.clock_tree_node.board_clocks)} clock(s)"
                     + (f", {len(plls)} PLL(s)" if plls else ""))
        return model

    # ------------------------------------------------------------------

    def _generate_rtl(self, model):
        """Phase 3: RTL Generation."""
        self.log("Generating SystemVerilog RTL...")
        gen = RTLGenerator(model)

        # soc_interfaces.sv (bus_if) only in SOC mode
        if model.mode == SoCMode.SOC:
            gen.generate_interfaces(self._p("rtl", "soc_interfaces.sv"))
        gen.generate_soc_top(self._p("rtl", "soc_top.sv"))

        # If reset syncs were generated, resolve cdc_reset_synchronizer files
        if model.reset_syncs:
            self._add_rst_sync_files(model)

        # Per-peripheral register blocks
        # Only generate if ip.yaml does NOT set gen_regs: false
        # (IPs with self-contained register logic set gen_regs: false)
        for p in model.peripherals:
            if p.registers and p.gen_regs:
                fname = f"{p.module}_regs.sv"
                gen.generate_reg_block(p, self._p("rtl", fname))

        # Verify all static RTL files referenced by the model exist
        static_mods = [f for p in model.peripherals for f in p.files]
        if static_mods and model.root_dir:
            gen.verify_static_files(
                static_mods,
                qsf_dir  = model.cfg_dir,
                root_dir = model.root_dir,
            )

    # ------------------------------------------------------------------

    def _add_rst_sync_files(self, model) -> None:
        """
        Resolve cdc_reset_synchronizer RTL files from registry
        and add to model.extra_files for inclusion in files.tcl.
        Raises ConfigError if IP not found in registry.
        """
        from models import ConfigError
        rst_meta = self.loader.registry.get("cdc_reset_synchronizer")
        if rst_meta is None:
            raise ConfigError(
                "Reset synchronisers required (timing_config has reset: sections) "
                "but 'cdc_reset_synchronizer' not found in registry.\n"
                "  -> Add src/ip/cdc/ to ip_plugins in project_config.yaml")

        plugin_path = rst_meta.get("_plugin_path", "")
        for f in rst_meta.get("files", []):
            if os.path.isabs(f):
                abs_path = f
            elif plugin_path:
                abs_path = os.path.normpath(os.path.join(plugin_path, f))
            else:
                continue
            if abs_path not in model.extra_files:
                model.extra_files.append(abs_path)
                self.log(f"  [reset] Added: {os.path.basename(abs_path)}")

    def _generate_sw(self, model):
        """Phase 4: Software header / linker script generation."""
        self.log("Generating software support files...")
        gen = SWGenerator(model)

        gen.generate_soc_map_h(self._p("sw", "soc_map.h"))
        gen.generate_soc_irq_h(self._p("sw", "soc_irq.h"))
        gen.generate_linker_script(self._p("sw", "sections.lds"))
        gen.generate_ram_size_mk(self._p("sw", "ram_size.mk"))
        gen.generate_soc_map_md(self._p("doc", "soc_map.md"))

    # ------------------------------------------------------------------

    def _generate_tcl(self, model):
        """Phase 5: Quartus TCL generation."""
        self.log("Generating Quartus TCL scripts...")
        gen = TCLGenerator(model)

        gen.generate_tcl_config(self._p("tcl", "generated_config.tcl"))

        # --- Collect ALL RTL files with absolute paths ---

        is_soc = (model.mode == SoCMode.SOC)

        # Generated RTL files (mode-dependent)
        extra_files = []
        if is_soc:
            extra_files.append(self._p("rtl", "soc_interfaces.sv"))
            for p in model.peripherals:
                if p.registers and p.gen_regs:
                    extra_files.append(self._p("rtl", f"{p.module}_regs.sv"))

        # Static IP files (already resolved to absolute by builder)
        # Rules: soc_ram + CPU = SOC only; peripherals + standalone = both modes
        static_modules = []
        for p in model.peripherals:
            for f in p.files:
                if f and f not in static_modules:
                    static_modules.append(f)
        for sm in model.standalone_modules:
            for f in sm.files:
                if f and f not in static_modules:
                    static_modules.append(f)
        if is_soc:
            for f in model.ram_files:
                if f and f not in static_modules:
                    static_modules.append(f)
            for f in model.cpu_files:
                if f and f not in static_modules:
                    static_modules.append(f)
        for f in model.extra_files:
            if f and f not in static_modules:
                static_modules.append(f)

        gen.generate_files_tcl(
            self._p("tcl", "files.tcl"),
            soc_top_path   = self._p("rtl", "soc_top.sv"),
            static_modules = static_modules,
            extra_files    = extra_files,
        )

        gen.generate_board_hal(self._p("hal", "board.tcl"))

    # ------------------------------------------------------------------


    def _generate_timing(self, model):
        """Phase 6: SDC timing constraints generation."""
        timing_cfg = self._timing_cfg
        if timing_cfg is None:
            return

        self.log("Generating SDC timing constraints...")
        try:
            from generators.sdc import SDCGenerator
        except ImportError:
            _here = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, _here)
            from generators.sdc import SDCGenerator

        sdc_path = self._p("tcl", "soc_top.sdc")
        SDCGenerator(model, timing_cfg).generate(sdc_path)

        # Pridaj SDC do files.tcl extra_files (re-generuj files.tcl)
        # Jednoduchsie: len zaloguj -- files.tcl uz bol vygenerovany
        self.log(f"  SDC: {sdc_path}")

        # Reset sync dokumentacia
        rst_syncs = SDCGenerator(model, timing_cfg).rst_sync_needed()
        if rst_syncs:
            self.log(f"  Reset synchronisers needed: {len(rst_syncs)}")
            for rs in rst_syncs:
                self.log(f"    {rs['inst_name']}  domain={rs['domain']}  "
                         f"stages={rs['sync_stages']}  type={rs['type']}"
                         + (f"  sync_from={rs['sync_from']}" if rs['sync_from'] else ""))

    def _generate_exports(self, model):
        """Phase 6: Export DOT graph and JSON memory map."""
        self.log("Exporting documentation artefacts...")

        dot_path = self._p("doc", "soc_graph.dot")
        GraphvizExporter(model).generate(dot_path)
        GraphvizExporter(model).render_png(dot_path)   # no-op if dot not installed

        JsonExporter(model).generate(self._p("doc", "soc_map.json"))

        StructureExporter(model, self.loader.registry).generate(
            report_path = self._p("doc", "build_report.md"),
            map_path    = self._p("doc", "plugin_map.json"),
        )

    # ------------------------------------------------------------------

    def run(self):
        """Execute the complete build pipeline."""
        try:
            # Load timing config FIRST -- needed by build() + RTL + SDC
            self._timing_cfg = TimingLoader(
                self.loader.project_cfg_path,
                self.loader.raw_cfg).load()

            model = self._build_model()

            if model.mode == SoCMode.SOC:
                self._generate_rtl(model)
                self._generate_sw(model)
                self._generate_tcl(model)
                self._generate_timing(model)
                self._generate_exports(model)
            elif model.mode == SoCMode.STANDALONE:
                self._generate_rtl(model)
                self._generate_tcl(model)
                self._generate_timing(model)
                self._generate_exports(model)
            else:
                self.error(f"Unknown SoC mode: {model.mode}")
                sys.exit(1)

            self.log("=" * 60)
            self.log("Build SUCCESSFUL")
            self.log(f"Output in: {self.out_dir}/")
            self.log("=" * 60)

        except ConfigError as e:
            if self.verbose:
                import traceback
                traceback.print_exc()
            self.error(f"Configuration error:\n{e}")
            sys.exit(1)
        except Exception as e:
            if self.verbose:
                import traceback
                traceback.print_exc()
            self.error(f"Critical error during generation: {e}")
            sys.exit(2)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="QMTech SoC Generator  (gen_config.py v6)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Registry resolution (later source wins on collision):
  1. --registry ip_registry.yaml  (or auto-detected board/config/ip_registry.yaml)
  2. *.ip.yaml files from paths.ip_plugins in project_config.yaml

Examples:
  # Classic (single registry)
  python gen_config.py --config project_config.yaml

  # Plugin-only (no base registry)
  python gen_config.py --config project_config.yaml --no-base-registry

  # Explicit registry + plugins in project_config.yaml
  python gen_config.py --config project_config.yaml --registry board/config/ip_registry.yaml
""",
    )
    parser.add_argument("--config",
                        default="project_config.yaml",
                        help="Path to project_config.yaml")
    parser.add_argument("--registry",
                        default="",
                        help="Path to ip_registry.yaml "
                             "(auto-detected if omitted)")
    parser.add_argument("--no-base-registry",
                        action="store_true",
                        help="Skip auto-detection of ip_registry.yaml; "
                             "use ip_plugins only")
    parser.add_argument("--out",
                        default="gen",
                        help="Output directory (default: gen/)")
    parser.add_argument("--verbose", "-v",
                        action="store_true",
                        help="Print full tracebacks on errors")

    args = parser.parse_args()

    registry_path = ""
    if args.no_base_registry:
        registry_path = ""           # force plugins-only
    elif args.registry:
        registry_path = args.registry

    orch = SoCOrchestrator(
        config_path   = args.config,
        registry_path = registry_path,
        out_dir       = args.out,
        verbose       = args.verbose,
    )
    orch.run()
