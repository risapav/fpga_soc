"""
export.py - SoC Framework export utilities  (v4)
=================================================
Changes vs v3:
  - GraphvizExporter: refactored to Jinja2 template (soc_graph.dot.j2)
    Context building (_build_context) in Python, formatting in template.
  - RAM node label uses actual ram_base (not hardcoded 0x0)
  - clock_freq=0 safe for standalone mode
  - JsonExporter: unchanged (json.dump is correct, no template needed)
"""

from __future__ import annotations
import json
import os
from typing import List

from models import BusType, DepKind, SoCModel
from generators.base import render, write


# =============================================================================
# Graphviz DOT exporter
# =============================================================================

class GraphvizExporter:
    _BUS_COLOUR = {
        BusType.SIMPLE:     "#dde8f0",
        BusType.AXI_LITE:   "#d5f0dd",
        BusType.AXI_FULL:   "#f0ead5",
        BusType.AXI_STREAM: "#f0d5e8",
        BusType.NONE:       "#eeeeee",
    }

    def __init__(self, model: SoCModel, show_clk_rst: bool = False):
        self.m            = model
        self.show_clk_rst = show_clk_rst

    def generate(self, path: str) -> None:
        ctx     = self._build_context()
        content = render("soc_graph.dot.j2", **ctx)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        print(f"  -> {os.path.basename(path)}")

    def _build_context(self) -> dict:
        m = self.m
        ctx = {
            "board_type":   m.board_type,
            "cpu_type":     m.cpu_type,
            "ram_size":     m.ram_size,
            "ram_base":     m.ram_base,
            "ram_end":      m.ram_base + m.ram_size - 1 if m.ram_size > 0 else 0,
            "clock_mhz":    m.clock_freq // 1_000_000 if m.clock_freq else 0,
            "show_clk_rst": self.show_clk_rst,
        }

        # Bus fabrics
        fabrics = []
        for fabric in m.bus_fabrics:
            colour = self._BUS_COLOUR.get(fabric.bus_type, "#eeeeee")
            slaves = []
            for p in fabric.slaves:
                slaves.append({
                    "inst":      p.inst,
                    "base":      p.base,
                    "irq_label": (f"\\n[IRQ {','.join(str(i.id) for i in p.irqs)}]"
                                  if p.irqs else ""),
                    "reg_label": (f"\\n{len(p.registers)} regs"
                                  if p.registers else ""),
                })
            fabrics.append({
                "bus_type": fabric.bus_type.value,
                "colour":   colour,
                "slaves":   slaves,
            })
        ctx["fabrics"]          = fabrics
        ctx["flat_peripherals"] = ([] if m.bus_fabrics else
                                   [{"inst": p.inst, "base": p.base}
                                    for p in m.peripherals])

        # Bridge edges
        bridges = []
        for fabric in m.bus_fabrics:
            for bridge in fabric.bridges:
                if fabric.bus_type.value < bridge.to_type.value:
                    tf = m.fabric_for(bridge.to_type)
                    if tf and tf.slaves and fabric.slaves:
                        bridges.append({
                            "src":    fabric.slaves[0].inst,
                            "dst":    tf.slaves[0].inst,
                            "module": bridge.module,
                        })
        ctx["bridges"] = bridges

        # IRQ edges
        ctx["irq_nodes"] = [
            {"inst": p.inst,
             "irq_ids": ", ".join(str(i.id) for i in p.irqs)}
            for p in m.peripherals if p.irqs
        ]

        # Clock/reset edges
        ctx["clk_rst_edges"] = []
        if self.show_clk_rst:
            ctx["clk_rst_edges"] = [
                {"source": e.source, "target": e.target,
                 "colour": "#f9a825" if e.kind == DepKind.CLOCK else "#e91e63"}
                for e in m.dependencies
                if e.kind in (DepKind.CLOCK, DepKind.RESET)
            ]
        return ctx

    def render_png(self, dot_path: str, out_path: str = "") -> bool:
        import shutil, subprocess
        if not shutil.which("dot"):
            print("[WARN] 'dot' binary not found -- install Graphviz to render PNG")
            return False
        if not out_path:
            out_path = dot_path.replace(".dot", ".png")
        try:
            subprocess.run(["dot", "-Tpng", dot_path, "-o", out_path],
                           check=True, capture_output=True)
            print(f"  -> {os.path.basename(out_path)} (rendered)")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[WARN] dot render failed: {e.stderr.decode().strip()}")
            return False


# =============================================================================
# JSON exporter  (json.dump is the right tool -- no template needed)
# =============================================================================

class JsonExporter:
    def __init__(self, model: SoCModel):
        self.m = model

    def generate(self, path: str) -> None:
        data = self.m.to_dict()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print(f"  -> {os.path.basename(path)}")
