"""
generators/tcl.py - TCL/Quartus file generator (files.tcl, generated_config.tcl).
Uses Jinja2 templates.
"""

from __future__ import annotations
from models import SoCModel
from generators.base import render, write


class TCLGenerator:

    def __init__(self, model: SoCModel):
        self.m = model

    def generate_tcl_config(self, path: str) -> None:
        m = self.m
        content = render(
            "generated_config.tcl.j2",
            board_type  = m.board_type,
            onboard     = m.onboard,
            pmod        = m.pmod,
            peripherals = m.peripherals,
        )
        write(path, content)
        print("  -> generated_config.tcl")

    def generate_files_tcl(self, path: str, soc_top_path: str,
                           static_modules: list = None,
                           extra_files: list = None) -> None:
        content = render(
            "files.tcl.j2",
            soc_top_path   = soc_top_path,
            static_modules = static_modules or [],
            extra_files    = extra_files or [],
        )
        write(path, content)
        print("  -> files.tcl")
