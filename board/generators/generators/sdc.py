"""
generators/sdc.py - Quartus SDC timing constraints generator
=============================================================
Generuje soc_top.sdc z TimingConfig + SoCModel.

Výstupné sekcie (v poradí):
  1. Header + legenda
  2. create_clock        (vstupné board hodiny)
  3. create_generated_clock (PLL výstupy)
  4. set_clock_groups    (async / exclusive domény)
  5. derive_clock_uncertainty
  6. set_false_path      (reset porty + CDC + manuálne)
  7. set_input_delay / set_output_delay (IO constraints)
  8. set_multicycle_path
  9. Reset synchronizér komentáre (dokumentácia)

Reset synchronizéry:
  - Generátor produkuje KOMENTÁRE a false_path constraints pre CDC reset.
  - Samotný RTL reset synchronizér modul (rst_sync.sv) je statický IP
    a musí byť v src/ip/rst_sync/ -- generátor len overí jeho existenciu
    a pridá ho do files.tcl cez model (budúca práca).
"""

from __future__ import annotations
import os
import sys
from typing import List, Optional

from models import SoCModel
from generators.base import render, write
from timing_loader import (
    TimingConfig, ClockDef, PllDef, PllOutput,
    ClockGroup, IoDelay, FalsePath, MulticyclePath,
)


# =============================================================================
# Context builder
# =============================================================================

class _SDCContext:
    """
    Transformuje TimingConfig + SoCModel na kontext pre Jinja2 šablónu.
    Všetka logika (výpočty, odvodenie) je tu -- šablóna je len formátovanie.
    """

    def __init__(self, model: SoCModel, cfg: TimingConfig):
        self.m   = model
        self.cfg = cfg

    # ------------------------------------------------------------------
    def build(self) -> dict:
        return {
            "clocks":           self._clocks(),
            "generated_clocks": self._generated_clocks(),
            "clock_groups":     self._clock_groups(),
            "derive_uncertainty": self.cfg.derive_uncertainty,
            "false_paths":      self._false_paths(),
            "io_delays":        self._io_delays(),
            "multicycle_paths": self._multicycle_paths(),
            "reset_syncs":      self._reset_syncs(),
            "all_clock_names":  self.cfg.all_clock_names(),
        }

    # ------------------------------------------------------------------
    def _clocks(self) -> List[dict]:
        result = []
        for c in self.cfg.clocks:
            result.append({
                "name":           c.name,
                "port":           c.port,
                "period_ns":      f"{c.period_ns:.3f}",
                "uncertainty_ns": f"{c.uncertainty_ns:.3f}" if c.uncertainty_ns else "",
                "freq_mhz":       f"{c.freq_mhz:.3f}",
            })
        return result

    # ------------------------------------------------------------------
    def _generated_clocks(self) -> List[dict]:
        result = []
        for pll in self.cfg.plls:
            src_period = self.cfg.pll_source_period(pll)
            # Nájdi source port z ClockDef
            src_clock  = self.cfg.clock_by_name(pll.source)
            src_port   = src_clock.port if src_clock else pll.source

            for out in pll.outputs:
                entry = {
                    "name":        out.name,
                    "source_port": src_port,
                    "source_clock": pll.source,
                    "multiply_by": out.multiply_by,
                    "divide_by":   out.divide_by,
                    "pin_path":    pll.pin_path(out.pin_index),
                    "offset_ns":   (f"{out.offset_ns:.3f}"
                                    if out.offset_ns is not None else ""),
                }
                # Vypočítaj výslednú periódu pre komentár
                if src_period:
                    period = src_period * out.divide_by / out.multiply_by
                    entry["freq_mhz"] = f"{1000.0 / period:.3f}"
                    entry["period_ns"] = f"{period:.3f}"
                else:
                    entry["freq_mhz"]  = ""
                    entry["period_ns"] = ""
                result.append(entry)
        return result

    # ------------------------------------------------------------------
    def _clock_groups(self) -> List[dict]:
        result = []
        for grp in self.cfg.clock_groups:
            result.append({
                "type":   grp.type,
                "groups": grp.groups,
            })
        return result

    # ------------------------------------------------------------------
    def _false_paths(self) -> List[dict]:
        result = []

        # Automaticky: false path pre všetky reset porty z clocks[]
        seen_reset_ports = set()
        for c in self.cfg.clocks:
            if c.reset and c.reset.port and c.reset.port not in seen_reset_ports:
                result.append({
                    "type":    "from_port",
                    "value":   c.reset.port,
                    "comment": f"Async reset for domain {c.name}",
                })
                seen_reset_ports.add(c.reset.port)

        # Automaticky: false path pre CDC reset synchronizéry
        for pll in self.cfg.plls:
            for out in pll.outputs:
                if out.reset and out.reset.sync_from:
                    result.append({
                        "type":    "cdc_reset",
                        "from_clock": out.reset.sync_from,
                        "to_clock":   out.name,
                        "comment": (f"CDC reset sync: {out.reset.sync_from} "
                                    f"-> {out.name} "
                                    f"({out.reset.sync_stages}-stage FF)"),
                    })

        # Manuálne false paths -- preskocime from_port ktore uz su automaticke
        seen_cdc = {(e["from_clock"], e["to_clock"])
                    for e in result if e["type"] == "cdc_reset"}

        for fp in self.cfg.false_paths:
            if fp.from_port:
                if fp.from_port in seen_reset_ports:
                    continue   # uz vygenerovane automaticky
                result.append({
                    "type":    "from_port",
                    "value":   fp.from_port,
                    "comment": fp.comment,
                })
                seen_reset_ports.add(fp.from_port)
            elif fp.from_clock and fp.to_clock:
                result.append({
                    "type":       "cdc_reset",
                    "from_clock": fp.from_clock,
                    "to_clock":   fp.to_clock,
                    "comment":    fp.comment,
                })
            elif fp.from_cell or fp.to_cell:
                result.append({
                    "type":      "cell",
                    "from_cell": fp.from_cell,
                    "to_cell":   fp.to_cell,
                    "comment":   fp.comment,
                })
        return result

    # ------------------------------------------------------------------
    def _io_delays(self) -> List[dict]:
        result = []
        override_ports = {ov.port for ov in self.cfg.io_overrides}

        # Automatické IO delays z ext_ports modelu
        if self.cfg.io_delays_auto:
            default_clk = self.cfg.io_delay_clock
            for p in self.m.peripherals:
                for ep in p.ext_ports:
                    if ep.top_port in override_ports:
                        continue  # override nižšie
                    direction = ("input"  if ep.dir.value == "input"
                                 else "output")
                    max_ns    = (self.cfg.io_input_max_ns
                                 if direction == "input"
                                 else self.cfg.io_output_max_ns)
                    result.append({
                        "direction": direction,
                        "port":      ep.top_port,
                        "clock":     default_clk,
                        "max_ns":    f"{max_ns:.3f}",
                        "comment":   f"{p.inst}.{ep.name}",
                    })

        # Manuálne overrides
        for ov in self.cfg.io_overrides:
            result.append({
                "direction": ov.direction,
                "port":      ov.port,
                "clock":     ov.clock,
                "max_ns":    f"{ov.max_ns:.3f}",
                "comment":   ov.comment,
            })

        return result

    # ------------------------------------------------------------------
    def _multicycle_paths(self) -> List[dict]:
        result = []
        for mp in self.cfg.multicycle_paths:
            result.append({
                "cycles":     mp.cycles,
                "from_cell":  mp.from_cell,
                "to_cell":    mp.to_cell,
                "from_clock": mp.from_clock,
                "to_clock":   mp.to_clock,
                "setup":      mp.setup,
                "hold":       mp.hold,
                "comment":    mp.comment,
            })
        return result

    # ------------------------------------------------------------------
    def _reset_syncs(self) -> List[dict]:
        """
        Dokumentačná sekcia: zoznam všetkých reset synchronizérov.
        Každý entry popisuje potrebný RTL rst_sync modul.
        """
        result = []

        # Hlavné clock domény s resetom
        for c in self.cfg.clocks:
            if c.reset:
                result.append({
                    "domain":       c.name,
                    "reset_port":   c.reset.port,
                    "active_low":   c.reset.active_low,
                    "sync_stages":  c.reset.sync_stages,
                    "sync_from":    "",
                    "type":         "primary",
                    "inst_name":    f"u_rst_sync_{c.name.lower()}",
                })

        # PLL výstupné domény s CDC reset synchronizérom
        for pll in self.cfg.plls:
            for out in pll.outputs:
                if out.reset:
                    result.append({
                        "domain":      out.name,
                        "reset_port":  out.reset.port if out.reset.port else "RESET_N",
                        "active_low":  out.reset.active_low,
                        "sync_stages": out.reset.sync_stages,
                        "sync_from":   out.reset.sync_from,
                        "type":        "cdc" if out.reset.sync_from else "primary",
                        "inst_name":   f"u_rst_sync_{out.name.lower()}",
                    })

        return result


# =============================================================================
# SDCGenerator
# =============================================================================

class SDCGenerator:

    def __init__(self, model: SoCModel, timing_cfg: TimingConfig):
        self.m   = model
        self.cfg = timing_cfg

    def generate(self, path: str) -> None:
        ctx     = _SDCContext(self.m, self.cfg).build()
        content = render("soc_top.sdc.j2", **ctx)
        write(path, content)
        print("  -> soc_top.sdc")

    def rst_sync_needed(self) -> List[dict]:
        """
        Vráti zoznam reset synchronizérov ktoré treba inštanciovať v RTL.
        Používa gen_config.py pre generovanie rst_sync blokov.
        """
        return _SDCContext(self.m, self.cfg)._reset_syncs()
