"""
export.py - SoC Framework export utilities  (v3, new module)
=============================================================
Provides two exporters:

  GraphvizExporter  -- generates soc_graph.dot (Graphviz DOT format)
                      visualises the full SoC topology:
                        * CPU node
                        * RAM node
                        * Peripheral nodes (grouped by bus type)
                        * Bus fabric subgraphs
                        * BusBridge edges between fabrics
                        * IRQ edges (dashed)
                        * Dependency edges (clock/reset, grey dotted)

  JsonExporter      -- writes soc_map.json (SoCModel.to_dict())
                      machine-readable memory map for SW tooling,
                      simulators, debug GUIs, and CI checks

Both classes work without the graphviz Python package being installed:
GraphvizExporter writes raw .dot text; rendering (PNG/SVG) requires the
`dot` binary from the Graphviz suite, but is not required for the build.
"""

from __future__ import annotations
import json
import os
from typing import List

from models import BusType, DepKind, SoCModel


# =============================================================================
# Graphviz DOT exporter
# =============================================================================

class GraphvizExporter:
    """
    Generates a Graphviz DOT file representing the SoC topology.

    Node shapes:
      CPU       -> box3d (3D box)
      RAM       -> cylinder
      Peripheral-> box  (filled, colour by bus type)
      Fabric    -> cluster subgraph

    Edge styles:
      bus       -> solid black
      irq       -> dashed red
      bridge    -> bold orange
      clock/reset -> dotted grey (drawn only when show_clk_rst=True)
    """

    # colour palette per bus type (Graphviz colour names)
    _BUS_COLOUR = {
        BusType.SIMPLE:     "#dde8f0",   # light blue
        BusType.AXI_LITE:   "#d5f0dd",   # light green
        BusType.AXI_FULL:   "#f0ead5",   # light amber
        BusType.AXI_STREAM: "#f0d5e8",   # light pink
        BusType.NONE:       "#eeeeee",   # light grey
    }

    def __init__(self, model: SoCModel, show_clk_rst: bool = False):
        self.m            = model
        self.show_clk_rst = show_clk_rst

    def generate(self, path: str) -> None:
        lines = self._build()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"  -> {os.path.basename(path)}")

    def _build(self) -> List[str]:
        m  = self.m
        L  = []
        L += [
            "// AUTO-GENERATED -- do not edit manually",
            f"// SoC: {m.board_type}  CPU: {m.cpu_type}  "
            f"RAM: {m.ram_size} B  @{m.clock_freq // 1_000_000} MHz",
            "digraph soc {",
            '  graph [rankdir=LR fontname="Helvetica" bgcolor="#fafafa" '
            'label="" splines=ortho nodesep=0.6 ranksep=1.2];',
            '  node  [fontname="Helvetica" fontsize=10];',
            '  edge  [fontname="Helvetica" fontsize=9];',
            "",
        ]

        # ---- CPU node -------------------------------------------------------
        L.append(
            f'  cpu [label="{m.cpu_type}\\n(CPU)" shape=box3d '
            f'style=filled fillcolor="#ffe0b2" color="#e65100" '
            f'fontcolor="#e65100"];')

        # ---- RAM node -------------------------------------------------------
        L.append(
            f'  ram [label="soc_ram\\n0x0..0x{m.ram_size - 1:X}" '
            f'shape=cylinder style=filled fillcolor="#e8eaf6" '
            f'color="#3949ab"];')

        # ---- CPU -> RAM ------------------------------------------------------
        L.append('  cpu -> ram [color="#3949ab" penwidth=2];')
        L.append("")

        # ---- Bus fabric subgraphs + peripheral nodes ------------------------
        if m.bus_fabrics:
            for fi, fabric in enumerate(m.bus_fabrics):
                colour = self._BUS_COLOUR.get(fabric.bus_type, "#eeeeee")
                L.append(f"  subgraph cluster_{fi} {{")
                L.append(f'    label="{fabric.bus_type.value}";')
                L.append(f'    style=filled; fillcolor="{colour}";')
                L.append(f'    color="#999999"; fontsize=9;')
                for p in fabric.slaves:
                    irq_label = (f"\\n[IRQ {','.join(str(i.id) for i in p.irqs)}]"
                                 if p.irqs else "")
                    reg_label = (f"\\n{len(p.registers)} regs"
                                 if p.registers else "")
                    L.append(
                        f'    {p.inst} [label="{p.inst}\\n0x{p.base:08X}'
                        f'{irq_label}{reg_label}" '
                        f'shape=box style=filled fillcolor="{colour}" '
                        f'color="#555555"];')
                L.append("  }")
                L.append("")
        else:
            # no fabrics -- draw peripherals flat
            for p in m.peripherals:
                L.append(f'  {p.inst} [label="{p.inst}\\n0x{p.base:08X}" '
                         f'shape=box style=filled fillcolor="#dde8f0"];')

        # ---- CPU -> fabric edges (bus) ---------------------------------------
        for fabric in m.bus_fabrics:
            for p in fabric.slaves:
                L.append(
                    f'  cpu -> {p.inst} '
                    f'[color="#555555" penwidth=1.5 '
                    f'label="{fabric.bus_type.value}"];')
        L.append("")

        # ---- Bridge edges ---------------------------------------------------
        for fabric in m.bus_fabrics:
            for bridge in fabric.bridges:
                # avoid drawing both directions; only draw A->B where A < B str
                if fabric.bus_type.value < bridge.to_type.value:
                    target_fabric = m.fabric_for(bridge.to_type)
                    if target_fabric and target_fabric.slaves:
                        src_rep = fabric.slaves[0].inst if fabric.slaves else "cpu"
                        dst_rep = target_fabric.slaves[0].inst
                        L.append(
                            f'  {src_rep} -> {dst_rep} '
                            f'[label="{bridge.module}" '
                            f'style=bold color="#e65100" '
                            f'constraint=false fontcolor="#e65100"];')
        L.append("")

        # ---- IRQ edges ------------------------------------------------------
        for p in m.peripherals:
            if p.irqs:
                irq_ids = ", ".join(str(i.id) for i in p.irqs)
                L.append(
                    f'  {p.inst} -> cpu '
                    f'[label="IRQ {irq_ids}" style=dashed '
                    f'color="#c62828" fontcolor="#c62828" constraint=false];')
        L.append("")

        # ---- Clock / reset edges (optional, clutters large designs) ---------
        if self.show_clk_rst:
            L.append('  SYS_CLK [label="SYS_CLK" shape=diamond '
                     'style=filled fillcolor="#fff9c4"];')
            L.append('  RESET_N [label="RESET_N" shape=diamond '
                     'style=filled fillcolor="#fce4ec"];')
            for e in m.dependencies:
                if e.kind in (DepKind.CLOCK, DepKind.RESET):
                    colour = "#f9a825" if e.kind == DepKind.CLOCK else "#e91e63"
                    L.append(
                        f'  {e.target} -> {e.source} '
                        f'[style=dotted color="{colour}" constraint=false];')
            L.append("")

        L.append("}")
        return L

    def render_png(self, dot_path: str, out_path: str = "") -> bool:
        """
        Optionally render the .dot to PNG using the `dot` binary.
        Returns True on success, False if graphviz is not installed.
        """
        import shutil
        import subprocess
        if not shutil.which("dot"):
            print("[WARN] 'dot' binary not found -- install Graphviz to render PNG")
            return False
        if not out_path:
            out_path = dot_path.replace(".dot", ".png")
        try:
            subprocess.run(
                ["dot", "-Tpng", dot_path, "-o", out_path],
                check=True, capture_output=True,
            )
            print(f"  -> {os.path.basename(out_path)} (rendered)")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[WARN] dot render failed: {e.stderr.decode().strip()}")
            return False


# =============================================================================
# JSON exporter
# =============================================================================

class JsonExporter:
    """
    Writes soc_map.json -- a machine-readable snapshot of the full SoC model.

    Consumers:
      - SW tooling (address auto-discovery)
      - simulators / emulators
      - debug GUIs
      - CI: diff against golden file to detect unintended map changes
    """

    def __init__(self, model: SoCModel):
        self.m = model

    def generate(self, path: str) -> None:
        data = self.m.to_dict()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print(f"  -> {os.path.basename(path)}")
