"""
generators/tcl.py - TCL/Quartus file generator
===============================================
Generates:
  - board/config/generated_config.tcl   (runtime vars for legacy HAL chain)
  - gen/files.tcl                        (Quartus source file list)
  - gen/hal/board.tcl                    (flat static pin assignments for Quartus)

board.tcl replaces the dynamic source-chain approach:
  OLD: pre_flow.tcl -> board.tcl -> generated_config.tcl -> hal_qmtech_ep4ce55.tcl
  NEW: pre_flow.tcl -> gen/hal/board.tcl   (self-contained, no runtime logic)

Pin data is encoded directly in this module (BSP_DATA) so board.tcl is
100% deterministic and readable -- grep-able for any pin name.
"""

from __future__ import annotations
import os
from typing import List, Dict
from models import SoCModel
from generators.base import render, write


# =============================================================================
# BSP pin database for QMTech EP4CE55F23C8
# Single source of truth -- mirrors hal_qmtech_ep4ce55.tcl v4.1
# =============================================================================

# On-board peripheral pin lists (signal index = list index)
_ONB_PINS: Dict[str, List[str]] = {
    "SEG":     ["PIN_C4","PIN_B2","PIN_A3","PIN_C3","PIN_A5","PIN_B4","PIN_B1","PIN_A4"],
    "DIG":     ["PIN_B5","PIN_B3","PIN_B6"],
    "LEDS":    ["PIN_E4","PIN_A8","PIN_B8","PIN_A7","PIN_B7","PIN_A6"],
    "BUTTONS": ["PIN_Y13","PIN_AA13"],
    "VGA":     ["PIN_B11","PIN_A11","PIN_B12","PIN_A12","PIN_B13","PIN_A13",
                "PIN_C11","PIN_D11","PIN_E11","PIN_B14","PIN_A14","PIN_C14",
                "PIN_B10","PIN_A10"],
    "SDRAM":   ["PIN_V2","PIN_V1","PIN_U2","PIN_U1","PIN_T1","PIN_R1",
                "PIN_P2","PIN_P1","PIN_N2","PIN_N1","PIN_M2","PIN_M1",
                "PIN_L2","PIN_L1"],
    "ETH":     ["PIN_D3","PIN_E3","PIN_F4","PIN_G4","PIN_H4"],
    "SDC":     ["PIN_K1","PIN_K2","PIN_L3","PIN_L4"],
    "CAM":     ["PIN_R14","PIN_T14","PIN_T13","PIN_R13","PIN_T12","PIN_R12",
                "PIN_T11","PIN_R11","PIN_T10","PIN_R10"],
}

_ONB_IO_STD: Dict[str, str] = {
    "SEG":     "3.3-V LVTTL",
    "DIG":     "3.3-V LVTTL",
    "LEDS":    "3.3-V LVTTL",
    "BUTTONS": "3.3-V LVTTL",
    "VGA":     "3.3-V LVTTL",
    "SDRAM":   "3.3-V SSTL-2 Class I",
    "ETH":     "3.3-V LVTTL",
    "SDC":     "3.3-V LVTTL",
    "CAM":     "3.3-V LVTTL",
}

# PMOD physical pin map: (connector, header_pin_number) -> FPGA pin
_PMOD_PINS: Dict[tuple, str] = {
    ("J10",1):"PIN_H1", ("J10",2):"PIN_F1", ("J10",3):"PIN_E1", ("J10",4):"PIN_C1",
    ("J10",7):"PIN_H2", ("J10",8):"PIN_F2", ("J10",9):"PIN_D2", ("J10",10):"PIN_C2",
    ("J11",1):"PIN_R1", ("J11",2):"PIN_P1", ("J11",3):"PIN_N1", ("J11",4):"PIN_M1",
    ("J11",7):"PIN_R2", ("J11",8):"PIN_P2", ("J11",9):"PIN_N2", ("J11",10):"PIN_M2",
}

# Signal index order per PMOD module type
_PMOD_ORDER_DEFAULT = [10, 4, 9, 3, 8, 2, 7, 1]
_PMOD_ORDER_SEG     = [10, 9, 3, 4, 8, 2, 1, 7]

# onboard config key -> ONB label (UART handled separately)
_ONB_KEY_TO_LABEL = {
    "leds":    "LEDS",
    "seg":     "SEG",
    "dig":     "DIG",
    "buttons": "BUTTONS",
    "vga":     "VGA",
    "sdram":   "SDRAM",
    "eth":     "ETH",
    "sdc":     "SDC",
    "cam":     "CAM",
}


# =============================================================================
# TCLGenerator
# =============================================================================

class TCLGenerator:

    def __init__(self, model: SoCModel):
        self.m = model

    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------

    def generate_board_hal(self, path: str) -> None:
        """
        Generate gen/hal/board.tcl -- flat static Quartus pin assignments.

        The file is self-contained: it needs no runtime `source` of
        generated_config.tcl or hal_qmtech_ep4ce55.tcl.  Quartus
        pre_flow.tcl can source it directly with a single line.

        Pin data comes from the BSP database (_ONB_PINS / _PMOD_PINS)
        filtered by the active onboard/pmod config in the SoCModel.
        """
        m = self.m
        onboard = m.onboard   # dict-like: .get(key) or onboard[key]
        pmod    = m.pmod      # dict: {"J10": "NONE"|"SEG"|..., "J11": ...}

        # ── on-board blocks (all except UART which is handled separately) ──
        onboard_blocks = []
        for cfg_key, label in _ONB_KEY_TO_LABEL.items():
            enabled = (onboard.get(cfg_key)
                       if hasattr(onboard, "get") else getattr(onboard, cfg_key, False))
            if not enabled:
                continue
            pins = _ONB_PINS.get(label, [])
            onboard_blocks.append({
                "label":   label,
                "signal":  f"ONB_{label}",
                "io_std":  _ONB_IO_STD.get(label, "3.3-V LVTTL"),
                "pull_up": label == "BUTTONS",
                "pins":    [{"idx": i, "pin": p} for i, p in enumerate(pins)],
            })

        # ── PMOD blocks ───────────────────────────────────────────────────
        pmod_blocks = []
        for port, module in (pmod.items() if hasattr(pmod, "items") else pmod):
            if module == "NONE":
                continue
            io_std    = "LVDS" if module.startswith("HDMI") else "3.3-V LVTTL"
            pin_order = _PMOD_ORDER_SEG if module == "SEG" else _PMOD_ORDER_DEFAULT
            pins = []
            for idx, header_pin in enumerate(pin_order):
                fpga_pin = _PMOD_PINS.get((port, header_pin), "")
                if fpga_pin:
                    pins.append({"idx": idx, "pin": fpga_pin})
            pmod_blocks.append({
                "port":    port,
                "module":  module,
                "io_std":  io_std,
                "signal":  f"PMOD_{port}_P",
                "pins":    pins,
            })

        # ── external port summary (from model peripherals) ─────────────────
        ext_port_summary = [
            {"inst": p.inst, "top_port": ep.top_port,
             "dir": ep.dir.value, "width": ep.width}
            for p in m.peripherals
            for ep in p.ext_ports
        ]

        use_uart = (onboard.get("uart")
                    if hasattr(onboard, "get") else getattr(onboard, "uart", False))

        content = render(
            "board_hal.tcl.j2",
            board_type      = m.board_type,
            clock_mhz       = m.clock_freq // 1_000_000,
            use_uart        = use_uart,
            onboard_blocks  = onboard_blocks,
            pmod_blocks     = pmod_blocks,
            ext_port_summary= ext_port_summary,
        )
        write(path, content)
        print("  -> gen/hal/board.tcl")
