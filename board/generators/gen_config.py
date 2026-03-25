#!/usr/bin/env python3
"""
gen_config.py  -  QMTech Cyclone IV RISC-V SoC Framework Generator
====================================================================
Thin orchestrator. See models.py, loader.py, builder.py, generators/*.py
"""

import os, sys, hashlib, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import SoCModel, SoCMode
from loader import ConfigLoader
from builder import ModelBuilder
from generators.rtl import RTLGenerator
from generators.sw  import SWGenerator
from generators.tcl import TCLGenerator


class SoCOrchestrator:

    def __init__(self, project_cfg_override=None):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir   = os.path.normpath(os.path.join(self.script_dir, "..", ".."))
        cfg_dir     = os.path.join(self.root_dir, "board", "config")
        default_cfg = os.path.join(cfg_dir, "project_config.yaml")
        proj_path   = os.path.abspath(project_cfg_override or default_cfg)
        reg_path    = os.path.join(cfg_dir, "ip_registry.yaml")
        loader      = ConfigLoader(proj_path, reg_path)
        builder     = ModelBuilder(loader, proj_path, self.root_dir)
        self.model  = builder.build()

    def generate_all(self, dry_run=False):
        m       = self.model
        gen_dir = m.gen_dir
        cfg_dir = m.cfg_dir
        if dry_run:
            self._dry_run_report(); return
        os.makedirs(gen_dir, exist_ok=True)
        os.makedirs(cfg_dir, exist_ok=True)
        rtl = RTLGenerator(m)
        sw  = SWGenerator(m)
        tcl = TCLGenerator(m)
        if m.mode == SoCMode.STANDALONE:
            self._gen_standalone(gen_dir, cfg_dir, rtl, tcl)
        else:
            self._gen_soc(gen_dir, cfg_dir, rtl, sw, tcl)

    def _gen_standalone(self, gen_dir, cfg_dir, rtl, tcl):
        m = self.model
        print(f"\n[DEMO] Standalone -> {gen_dir}\n")
        rtl.generate_soc_top(os.path.join(gen_dir, "soc_top.sv"))
        tcl.generate_tcl_config(os.path.join(cfg_dir, "generated_config.tcl"))
        static_mods = []
        for mo in m.standalone_modules:
            if mo.files:
                for f in mo.files: static_mods.append(f"../../src/soc/static/{f}")
            else:
                static_mods.append(f"../../src/soc/static/{mo.module}.sv")
        tcl.generate_files_tcl(os.path.join(gen_dir, "files.tcl"),
                                "gen/soc_top.sv", static_mods)
        print(f"\n[OK] Done: gen/soc_top.sv  gen/files.tcl  board/config/generated_config.tcl")

    def _gen_soc(self, gen_dir, cfg_dir, rtl, sw, tcl):
        m = self.model
        print(f"\n[GEN] SoC -> {gen_dir}")
        print(f"      Peripherals: {[p.inst for p in m.peripherals]}\n")
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
            if p.files:
                for f in p.files: static_mods.append(f"../../src/soc/static/{f}")
            else:
                static_mods.append(f"../../src/soc/static/{p.module}.sv")
        qsf_dir = os.path.dirname(gen_dir)
        rtl.verify_static_files(static_mods, qsf_dir, m.root_dir)
        tcl.generate_files_tcl(
            os.path.join(gen_dir, "files.tcl"),
            "gen/soc_top.sv", static_mods,
reg_sv_files + ["gen/soc_interfaces.sv"] + [f"../../src/cpu/{f}" for f in m.cpu_files],
        )
        print(f"\n[OK] Done - all files in {gen_dir}")

    def _dry_run_report(self):
        m = self.model
        print(f"\n[DRY-RUN] Output: {m.gen_dir}  (mode: {m.mode.value})")
        if m.mode == SoCMode.SOC:
            print(f"\n  {'Region':<20} {'Base':>12}  {'End':>12}  {'Size':>8}  Module")
            print(f"  {'-'*20} {'-'*12}  {'-'*12}  {'-'*8}  ------")
            print(f"  {'RAM':<20} {'0x00000000':>12}  {'0x'+f'{m.ram_size-1:08X}':>12}  "
                  f"{str(m.ram_size)+' B':>8}  soc_ram")
            for p in m.peripherals:
                ri = f"  [{len(p.registers)} regs]" if p.registers else ""
                print(f"  {p.inst:<20} {'0x'+f'{p.base:08X}':>12}  "
                      f"{'0x'+f'{p.end_addr:08X}':>12}  {'0x'+f'{p.size:X}':>8}  {p.module}{ri}")
            if any(p.irqs for p in m.peripherals):
                print("\n  IRQs:")
                for p in m.peripherals:
                    for irq in p.irqs: print(f"    [{irq.id}] {p.inst}.{irq.name}")
        else:
            for mo in m.standalone_modules: print(f"  Module: {mo.module}  inst: {mo.inst}")
        print("\n[DRY-RUN] Validation passed.")


if __name__ == "__main__":
    _hash = hashlib.md5(open(__file__, "rb").read()).hexdigest()[:8]
    parser = argparse.ArgumentParser(description="SoC Framework Generator")
    parser.add_argument("--config",  default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(f"[GEN] gen_config.py  rev:{_hash}")
    SoCOrchestrator(project_cfg_override=args.config).generate_all(dry_run=args.dry_run)
