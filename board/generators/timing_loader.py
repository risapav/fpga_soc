"""
timing_loader.py - Timing / SDC configuration loader and validator
==================================================================
Načítava timing konfiguráciu buď z:
  A) sekcie timing: v project_config.yaml
  B) samostatného timing_config.yaml (cesta v project_config.yaml
     alebo vedľa neho ako <demo_name>_timing.yaml / timing_config.yaml)

Výstupom je validovaný TimingConfig objekt ktorý SDCGenerator priamo používa.

Schéma (všetky polia okrem clocks sú voliteľné):

timing:
  clocks:
    - name: SYS_CLK
      port: SYS_CLK
      period_ns: 20.0           # 50 MHz
      uncertainty_ns: 0.2       # voliteľné, default 0.0
      reset:                    # voliteľné
        port: RESET_N
        active_low: true
        sync_stages: 2          # počet FF synchronizačných stupňov

  plls:
    - inst: clkpll_inst
      source: SYS_CLK           # ref. na clocks[].name
      outputs:
        - name: pixel_clk
          multiply_by: 4
          divide_by: 5
          pin_index: 0          # clk[N] výstup PLL
          reset:                # voliteľné - reset synchronizér
            sync_from: SYS_CLK
            sync_stages: 2
        - name: pixel_clk5
          multiply_by: 4
          divide_by: 1
          pin_index: 1
        - name: clk_100mhz_shifted
          multiply_by: 2
          divide_by: 1
          offset_ns: -2.5
          pin_index: 3

  clock_groups:
    - type: asynchronous        # asynchronous | exclusive
      groups:
        - [SYS_CLK]
        - [pixel_clk, pixel_clk5, clk_100mhz]

  io_delays:
    auto: true                  # odvoď porty z SoCModel.peripherals[].ext_ports
    clock: SYS_CLK              # default clock pre auto IO delays
    default_input_max_ns:  3.0
    default_output_max_ns: 3.0
    overrides:
      - port: SDRAM_CLK
        direction: output
        clock: SYS_CLK
        max_ns: 1.5

  false_paths:
    - from_port: RESET_N
      comment: "Async reset - false path for all domains"
    - from_clock: SYS_CLK
      to_clock: pixel_clk
      comment: "CDC: SYS_CLK -> pixel_clk handled by synchroniser"

  multicycle_paths:
    - from_cell: "u_uart0|*"
      to_cell:   "u_uart0|*"
      cycles: 2
      setup: true               # setup multicycle (default true)
      hold:  false              # hold multicycle (default false)
      comment: "UART baudrate divider"
"""

from __future__ import annotations
import os
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from models import ConfigError


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class ResetConfig:
    port:         str   = "RESET_N"
    active_low:   bool  = True
    sync_stages:  int   = 2
    sync_from:    str   = ""   # ak prázdne = vlastná doména, inak CDC synchronizér


@dataclass
class ClockDef:
    name:           str
    port:           str
    period_ns:      float
    uncertainty_ns: float        = 0.0
    reset:          Optional[ResetConfig] = None

    @property
    def freq_mhz(self) -> float:
        return round(1000.0 / self.period_ns, 3)


@dataclass
class PllOutput:
    name:        str
    multiply_by: int
    divide_by:   int
    pin_index:   int
    offset_ns:   Optional[float]       = None
    reset:       Optional[ResetConfig] = None

    @property
    def period_ns(self) -> Optional[float]:
        """Vypočítaná perióda PLL výstupu (potrebuje source period)."""
        return None   # vypočíta SDCGenerator podľa source


@dataclass
class PllDef:
    inst:    str          # RTL inštancia napr. "clkpll_inst"
    source:  str          # ref. na ClockDef.name
    outputs: List[PllOutput] = field(default_factory=list)

    # Quartus Cyclone IV PLL pin path template
    # {inst}|altpll_component|auto_generated|pll1|clk[{index}]
    def pin_path(self, index: int) -> str:
        return (f"{self.inst}|altpll_component|"
                f"auto_generated|pll1|clk[{index}]")


@dataclass
class ClockGroup:
    type:   str              # "asynchronous" | "exclusive"
    groups: List[List[str]]  # [[clk1, clk2], [clk3], ...]


@dataclass
class IoDelay:
    port:      str
    direction: str           # "input" | "output"
    clock:     str
    max_ns:    float
    min_ns:    Optional[float] = None
    comment:   str = ""


@dataclass
class FalsePath:
    from_port:  str = ""
    from_clock: str = ""
    to_clock:   str = ""
    from_cell:  str = ""
    to_cell:    str = ""
    comment:    str = ""


@dataclass
class MulticyclePath:
    cycles:    int
    from_cell: str  = ""
    to_cell:   str  = ""
    from_clock: str = ""
    to_clock:   str = ""
    setup:     bool = True
    hold:      bool = False
    comment:   str  = ""


@dataclass
class TimingConfig:
    clocks:          List[ClockDef]      = field(default_factory=list)
    plls:            List[PllDef]        = field(default_factory=list)
    clock_groups:    List[ClockGroup]    = field(default_factory=list)
    io_delays_auto:  bool                = False
    io_delay_clock:  str                 = "SYS_CLK"
    io_input_max_ns: float               = 3.0
    io_output_max_ns: float              = 3.0
    io_overrides:    List[IoDelay]       = field(default_factory=list)
    false_paths:     List[FalsePath]     = field(default_factory=list)
    multicycle_paths: List[MulticyclePath] = field(default_factory=list)
    derive_uncertainty: bool             = True

    def all_clock_names(self) -> List[str]:
        names = [c.name for c in self.clocks]
        for pll in self.plls:
            names.extend(o.name for o in pll.outputs)
        return names

    def clock_by_name(self, name: str) -> Optional[ClockDef]:
        return next((c for c in self.clocks if c.name == name), None)

    def pll_source_period(self, pll: PllDef) -> Optional[float]:
        c = self.clock_by_name(pll.source)
        return c.period_ns if c else None


# =============================================================================
# Validator
# =============================================================================

class TimingValidator:

    def validate(self, cfg: TimingConfig, source: str) -> None:
        errors: List[str] = []
        clock_names = {c.name for c in cfg.clocks}
        all_names   = set(cfg.all_clock_names())

        if not cfg.clocks:
            errors.append("timing: at least one clock must be defined")

        for c in cfg.clocks:
            if c.period_ns <= 0:
                errors.append(
                    f"clock '{c.name}': period_ns must be > 0, "
                    f"got {c.period_ns}")
            if c.reset and c.reset.sync_stages < 1:
                errors.append(
                    f"clock '{c.name}': reset.sync_stages must be >= 1")

        for pll in cfg.plls:
            if pll.source not in clock_names:
                errors.append(
                    f"pll '{pll.inst}': source '{pll.source}' not in clocks "
                    f"({sorted(clock_names)})")
            for out in pll.outputs:
                if out.multiply_by <= 0 or out.divide_by <= 0:
                    errors.append(
                        f"pll '{pll.inst}' output '{out.name}': "
                        f"multiply_by and divide_by must be > 0")
                if out.reset and out.reset.sync_from:
                    if out.reset.sync_from not in all_names:
                        errors.append(
                            f"pll '{pll.inst}' output '{out.name}': "
                            f"reset.sync_from '{out.reset.sync_from}' "
                            f"not a defined clock")

        for grp in cfg.clock_groups:
            if grp.type not in ("asynchronous", "exclusive"):
                errors.append(
                    f"clock_groups: type must be 'asynchronous' or "
                    f"'exclusive', got '{grp.type}'")
            for g in grp.groups:
                for cname in g:
                    if cname not in all_names:
                        errors.append(
                            f"clock_groups: clock '{cname}' not defined")

        for fp in cfg.false_paths:
            if not any([fp.from_port, fp.from_clock, fp.from_cell]):
                errors.append(
                    "false_path: must specify at least from_port, "
                    "from_clock, or from_cell")

        if errors:
            raise ConfigError(
                f"Timing validation failed ({source}):\n" +
                "".join(f"  * {e}\n" for e in errors))

        print(f"[OK] Timing: {len(cfg.clocks)} clock(s), "
              f"{len(cfg.plls)} PLL(s), "
              f"{len(cfg.clock_groups)} group(s)")


# =============================================================================
# Parser
# =============================================================================

def _parse_reset(d: Any) -> Optional[ResetConfig]:
    if not d or not isinstance(d, dict):
        return None
    return ResetConfig(
        port        = d.get("port", "RESET_N"),
        active_low  = bool(d.get("active_low", True)),
        sync_stages = int(d.get("sync_stages", 2)),
        sync_from   = d.get("sync_from", ""),
    )


def parse_timing_dict(raw: dict) -> TimingConfig:
    """Parse raw timing dict (from YAML) into TimingConfig."""
    cfg = TimingConfig()

    # --- clocks ---
    for cd in raw.get("clocks", []):
        cfg.clocks.append(ClockDef(
            name           = cd["name"],
            port           = cd.get("port", cd["name"]),
            period_ns      = float(cd["period_ns"]),
            uncertainty_ns = float(cd.get("uncertainty_ns", 0.0)),
            reset          = _parse_reset(cd.get("reset")),
        ))

    # --- plls ---
    for pd in raw.get("plls", []):
        outputs = []
        for od in pd.get("outputs", []):
            outputs.append(PllOutput(
                name        = od["name"],
                multiply_by = int(od["multiply_by"]),
                divide_by   = int(od["divide_by"]),
                pin_index   = int(od["pin_index"]),
                offset_ns   = (float(od["offset_ns"])
                               if "offset_ns" in od else None),
                reset       = _parse_reset(od.get("reset")),
            ))
        cfg.plls.append(PllDef(
            inst    = pd["inst"],
            source  = pd["source"],
            outputs = outputs,
        ))

    # --- clock_groups ---
    for gd in raw.get("clock_groups", []):
        cfg.clock_groups.append(ClockGroup(
            type   = gd.get("type", "asynchronous"),
            groups = [list(g) for g in gd.get("groups", [])],
        ))

    # --- io_delays ---
    io = raw.get("io_delays", {})
    if isinstance(io, dict):
        cfg.io_delays_auto   = bool(io.get("auto", False))
        cfg.io_delay_clock   = io.get("clock", "SYS_CLK")
        cfg.io_input_max_ns  = float(io.get("default_input_max_ns",  3.0))
        cfg.io_output_max_ns = float(io.get("default_output_max_ns", 3.0))
        for ov in io.get("overrides", []):
            cfg.io_overrides.append(IoDelay(
                port      = ov["port"],
                direction = ov.get("direction", "output"),
                clock     = ov.get("clock", cfg.io_delay_clock),
                max_ns    = float(ov["max_ns"]),
                min_ns    = (float(ov["min_ns"])
                             if "min_ns" in ov else None),
                comment   = ov.get("comment", ""),
            ))

    # --- false_paths ---
    for fp in raw.get("false_paths", []):
        cfg.false_paths.append(FalsePath(
            from_port  = fp.get("from_port",  ""),
            from_clock = fp.get("from_clock", ""),
            to_clock   = fp.get("to_clock",   ""),
            from_cell  = fp.get("from_cell",  ""),
            to_cell    = fp.get("to_cell",    ""),
            comment    = fp.get("comment",    ""),
        ))

    # --- multicycle_paths ---
    for mp in raw.get("multicycle_paths", []):
        cfg.multicycle_paths.append(MulticyclePath(
            cycles     = int(mp["cycles"]),
            from_cell  = mp.get("from_cell",  ""),
            to_cell    = mp.get("to_cell",    ""),
            from_clock = mp.get("from_clock", ""),
            to_clock   = mp.get("to_clock",   ""),
            setup      = bool(mp.get("setup", True)),
            hold       = bool(mp.get("hold",  False)),
            comment    = mp.get("comment",    ""),
        ))

    # --- derive_uncertainty ---
    cfg.derive_uncertainty = bool(raw.get("derive_uncertainty", True))

    return cfg


# =============================================================================
# Loader (auto-discovery)
# =============================================================================

class TimingLoader:
    """
    Načíta timing konfiguráciu z viacerých zdrojov (v poradí priority):

    1. Explicitná cesta cez timing_file: v project_config.yaml
    2. Sekcia timing: priamo v project_config.yaml
    3. Auto-discovery vedľa project_config.yaml:
         <demo_name>_timing.yaml
         timing_config.yaml
         timing.yaml

    Ak žiadny zdroj neexistuje, vráti None (SDC sa negeneruje).
    """

    def __init__(self, project_cfg_path: str, raw_cfg: dict):
        self.project_cfg_path = os.path.abspath(project_cfg_path)
        self.project_dir      = os.path.dirname(self.project_cfg_path)
        self.raw_cfg          = raw_cfg

    def load(self) -> Optional[TimingConfig]:
        raw, source = self._find_raw()
        if raw is None:
            print("[INFO] No timing configuration found -- SDC will not be generated")
            return None

        print(f"[INFO] Timing config: {source}")
        cfg = parse_timing_dict(raw)
        TimingValidator().validate(cfg, source)
        return cfg

    def _find_raw(self):
        # 1. Explicitná cesta
        explicit = self.raw_cfg.get("timing_file")
        if explicit:
            path = (explicit if os.path.isabs(explicit)
                    else os.path.join(self.project_dir, explicit))
            return self._load_yaml(path), path

        # 2. Inline sekcia
        inline = self.raw_cfg.get("timing")
        if inline and isinstance(inline, dict):
            return inline, f"{self.project_cfg_path} [timing:]"

        # 3. Auto-discovery
        demo_name = self.raw_cfg.get("demo", {}).get("name", "")
        candidates = []
        if demo_name:
            candidates.append(f"{demo_name}_timing.yaml")
        candidates += ["timing_config.yaml", "timing.yaml"]

        for fname in candidates:
            path = os.path.join(self.project_dir, fname)
            if os.path.exists(path):
                data = self._load_yaml(path)
                # súbor môže mať top-level 'timing:' alebo byť priamo obsah
                if "timing" in data:
                    return data["timing"], path
                return data, path

        return None, ""

    def _load_yaml(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data or {}
        except FileNotFoundError:
            raise ConfigError(f"Timing file not found: {path}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in timing file {path}: {e}")
