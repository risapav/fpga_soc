"""
models.py - SoC Framework intermediate model  (v3)
====================================================
Changes vs v2:
  - BusBridge: explicit bridge descriptor between two bus types
  - BusFabric: replaces BusGroup -- first-class bus topology object
    with masters, slaves, bridges, and fabric-level validation
  - ParamDef: typed parameter definition from registry
    (name, type, min, max, required) -- used for validation in builder
  - SoCModel._check_address_space: now checks periph <-> periph overlaps
    (v2 only checked RAM <-> periph)
  - SoCModel.topological_sort(): returns peripherals ordered by
    dependency graph (clock/reset/irq/bus edges)
  - SoCModel.to_dict(): full JSON-serialisable representation
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Enums
# =============================================================================

class PortDir(str, Enum):
    OUTPUT = "output"
    INPUT  = "input"
    INOUT  = "inout"

    def sv(self) -> str:
        return {"output": "output wire",
                "input":  "input  wire",
                "inout":  "inout  wire"}[self.value]


class RegAccess(str, Enum):
    RW = "rw"
    RO = "ro"
    WO = "wo"


class BusType(str, Enum):
    SIMPLE     = "simple_bus"
    AXI_LITE   = "axi_lite"
    AXI_FULL   = "axi_full"
    AXI_STREAM = "axi_stream"
    NONE       = "none"

    @property
    def needs_interconnect(self) -> bool:
        return self in (BusType.AXI_LITE, BusType.AXI_FULL, BusType.AXI_STREAM)


class SoCMode(str, Enum):
    SOC        = "soc"
    STANDALONE = "standalone"


class DepKind(str, Enum):
    CLOCK = "clock"
    RESET = "reset"
    IRQ   = "irq"
    BUS   = "bus"


class ParamType(str, Enum):
    INT  = "int"
    STR  = "str"
    BOOL = "bool"
    HEX  = "hex"   # integer, displayed as hex in RTL


# =============================================================================
# ParamDef
# =============================================================================

@dataclass
class ParamDef:
    """
    Typed parameter definition from ip_registry.yaml.

    Example registry entry:
      params:
        - name: BAUD_RATE
          type: int
          default: 115200
          min: 9600
          max: 10000000
          required: false
    """
    name:     str
    type:     ParamType     = ParamType.INT
    default:  Any           = None
    min:      Optional[int] = None
    max:      Optional[int] = None
    required: bool          = False
    desc:     str           = ""

    def validate_value(self, val: Any, inst: str) -> List[str]:
        errors: List[str] = []
        if val is None:
            if self.required:
                errors.append(f"{inst}: required param '{self.name}' is missing")
            return errors
        if self.type in (ParamType.INT, ParamType.HEX):
            # accept "0x1000" strings in addition to bare ints
            if isinstance(val, str):
                try:
                    val = int(val, 0)
                except ValueError:
                    errors.append(
                        f"{inst}: param '{self.name}' cannot parse "
                        f"{val!r} as integer")
                    return errors
            if not isinstance(val, int):
                errors.append(
                    f"{inst}: param '{self.name}' must be int, "
                    f"got {type(val).__name__} ({val!r})")
                return errors
            if self.min is not None and val < self.min:
                errors.append(
                    f"{inst}: param '{self.name}'={val} < min={self.min}")
            if self.max is not None and val > self.max:
                errors.append(
                    f"{inst}: param '{self.name}'={val} > max={self.max}")
        elif self.type == ParamType.BOOL:
            if not isinstance(val, bool):
                errors.append(
                    f"{inst}: param '{self.name}' must be bool, "
                    f"got {type(val).__name__}")
        elif self.type == ParamType.STR:
            if not isinstance(val, str):
                errors.append(
                    f"{inst}: param '{self.name}' must be str, "
                    f"got {type(val).__name__}")
        return errors

    @classmethod
    def from_dict(cls, d: dict) -> "ParamDef":
        return cls(
            name     = d["name"],
            type     = ParamType(d.get("type", "int")),
            default  = d.get("default"),
            min      = d.get("min"),
            max      = d.get("max"),
            required = bool(d.get("required", False)),
            desc     = d.get("desc", ""),
        )


# =============================================================================
# Small value objects
# =============================================================================

@dataclass
class RegField:
    name:   str
    offset: int
    access: RegAccess
    width:  int = 32
    reset:  int = 0
    desc:   str = ""

    @property
    def word_addr(self) -> int:
        return self.offset >> 2

    @property
    def byte_range(self):
        """Inclusive byte range [start, end] occupied by this register."""
        nbytes = max(1, (self.width + 7) // 8)
        return (self.offset, self.offset + nbytes - 1)

    def validate(self, inst: str, periph_size: int) -> List[str]:
        errors: List[str] = []
        if self.offset % 4 != 0:
            errors.append(
                f"{inst}.{self.name}: offset 0x{self.offset:X} not 4-byte aligned")
        if self.offset >= periph_size:
            errors.append(
                f"{inst}.{self.name}: offset 0x{self.offset:X} "
                f">= periph size 0x{periph_size:X}")
        if not (1 <= self.width <= 32):
            errors.append(
                f"{inst}.{self.name}: width {self.width} must be between 1 and 32")
        return errors

    def to_dict(self) -> dict:
        return {"name": self.name, "offset": self.offset,
                "access": self.access.value, "width": self.width,
                "reset": self.reset, "desc": self.desc}


@dataclass
class ExtPort:
    name:     str
    dir:      PortDir
    width:    int
    top_port: str

    @property
    def width_str(self) -> str:
        return f" [{self.width-1}:0]" if self.width > 1 else "      "

    def validate(self, inst: str) -> List[str]:
        errors: List[str] = []
        if self.width < 1:
            errors.append(f"{inst}.{self.name}: width must be >= 1")
        if not self.top_port:
            errors.append(f"{inst}.{self.name}: top_port must not be empty")
        return errors


@dataclass
class IrqLine:
    id:   int
    name: str


@dataclass
class DependencyEdge:
    source: str
    target: str
    kind:   DepKind


# =============================================================================
# Bus fabric
# =============================================================================

@dataclass
class BusBridge:
    """
    Protocol bridge between two bus segments.
    RTL generator uses this to instantiate the correct bridge module.
    """
    from_type: BusType
    to_type:   BusType
    module:    str = ""
    inst:      str = ""

    def __post_init__(self):
        if not self.module:
            self.module = (f"{self.from_type.value}_to_"
                           f"{self.to_type.value}_bridge")
        if not self.inst:
            self.inst = f"u_{self.from_type.value}_to_{self.to_type.value}_bridge"

    @property
    def needed(self) -> bool:
        return self.from_type != self.to_type

    def to_dict(self) -> dict:
        return {"from": self.from_type.value, "to": self.to_type.value,
                "module": self.module, "inst": self.inst}


@dataclass
class BusFabric:
    """
    First-class bus topology object -- one per unique BusType in the SoC.
    Multiple fabrics connect via BusBridge objects.

    masters  -- component names that drive this bus (usually the CPU)
    slaves   -- Peripheral objects on this segment
    bridges  -- outgoing bridges to other bus types
    """
    bus_type:   BusType
    data_width: int                = 32
    addr_width: int                = 32
    masters:    List[str]          = field(default_factory=list)
    slaves:     List["Peripheral"] = field(default_factory=list)
    bridges:    List[BusBridge]    = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.bus_type.value}_fabric"

    def add_bridge_to(self, other: "BusFabric") -> BusBridge:
        bridge = BusBridge(from_type=self.bus_type, to_type=other.bus_type)
        self.bridges.append(bridge)
        return bridge

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.masters:
            errors.append(f"{self.name}: no masters defined")
        if not self.slaves:
            errors.append(f"{self.name}: no slaves (empty fabric)")
        targets_seen: set = set()
        for b in self.bridges:
            if b.from_type == b.to_type:
                errors.append(
                    f"{self.name}: self-loop bridge {b.from_type.value} -> {b.to_type.value}")
            if b.to_type in targets_seen:
                errors.append(
                    f"{self.name}: duplicate bridge target {b.to_type.value}")
            targets_seen.add(b.to_type)
        return errors

    def to_dict(self) -> dict:
        return {
            "bus_type":   self.bus_type.value,
            "data_width": self.data_width,
            "addr_width": self.addr_width,
            "masters":    self.masters,
            "slaves":     [s.inst for s in self.slaves],
            "bridges":    [b.to_dict() for b in self.bridges],
        }


# =============================================================================
# Peripheral
# =============================================================================

@dataclass
class Peripheral:
    inst:       str
    type:       str
    module:     str
    base:       int
    size:       int
    bus_type:   BusType
    clk_port:   str              = "SYS_CLK"
    rst_port:   str              = "RESET_N"
    ext_ports:  List[ExtPort]    = field(default_factory=list)
    irqs:       List[IrqLine]    = field(default_factory=list)
    registers:  List[RegField]   = field(default_factory=list)
    params:     Dict[str, Any]   = field(default_factory=dict)
    param_defs: List[ParamDef]   = field(default_factory=list)
    files:      List[str]        = field(default_factory=list)

    @property
    def end_addr(self) -> int:
        return self.base + self.size - 1

    @property
    def addr_width(self) -> int:
        if self.size <= 1:
            return 1
        return math.ceil(math.log2(self.size))

    @property
    def is_aligned(self) -> bool:
        if self.size & (self.size - 1):
            return True
        return (self.base & (self.size - 1)) == 0

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.size <= 0:
            errors.append(f"{self.inst}: size must be > 0")
        if self.base < 0:
            errors.append(f"{self.inst}: base must be >= 0")
        if not self.is_aligned:
            errors.append(
                f"{self.inst}: base 0x{self.base:08X} not aligned "
                f"to size 0x{self.size:X}")
        # register byte-range overlap check (catches same-offset AND partial overlaps)
        ranges_seen: list = []   # list of (start, end, name)
        for r in self.registers:
            errors.extend(r.validate(self.inst, self.size))
            rb_start, rb_end = r.byte_range
            for prev_start, prev_end, prev_name in ranges_seen:
                if rb_start <= prev_end and rb_end >= prev_start:
                    errors.append(
                        f"{self.inst}: register byte-range overlap: "
                        f"'{r.name}' [0x{rb_start:X}..0x{rb_end:X}] vs "
                        f"'{prev_name}' [0x{prev_start:X}..0x{prev_end:X}]")
            ranges_seen.append((rb_start, rb_end, r.name))
        for ep in self.ext_ports:
            errors.extend(ep.validate(self.inst))
        for pdef in self.param_defs:
            val = self.params.get(pdef.name, pdef.default)
            errors.extend(pdef.validate_value(val, self.inst))
        return errors

    def to_dict(self) -> dict:
        return {
            "inst":       self.inst,
            "type":       self.type,
            "module":     self.module,
            "base":       f"0x{self.base:08X}",
            "end":        f"0x{self.end_addr:08X}",
            "size":       self.size,
            "bus_type":   self.bus_type.value,
            "addr_width": self.addr_width,
            "params":     self.params,
            "registers":  [r.to_dict() for r in self.registers],
            "irqs":       [{"id": irq.id, "name": irq.name}
                           for irq in self.irqs],
            "ext_ports":  [{"name": ep.name, "dir": ep.dir.value,
                            "width": ep.width, "top_port": ep.top_port}
                           for ep in self.ext_ports],
        }


# =============================================================================
# Standalone module
# =============================================================================

@dataclass
class StandaloneModule:
    inst:      str
    module:    str
    params:    Dict[str, Any]
    ext_ports: List[ExtPort]
    files:     List[str] = field(default_factory=list)


# =============================================================================
# Board config
# =============================================================================

@dataclass
class OnboardConfig:
    leds:    bool = False
    uart:    bool = False
    buttons: bool = False
    clk:     bool = True
    # _raw: kept so Jinja2 templates can call .get() for unknown board features
    _raw:    Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, d: dict) -> "OnboardConfig":
        obj = cls(
            leds    = bool(d.get("leds",    False)),
            uart    = bool(d.get("uart",    False)),
            buttons = bool(d.get("buttons", False)),
            clk     = bool(d.get("clk",     True)),
        )
        object.__setattr__(obj, "_raw", dict(d))
        return obj

    def get(self, key: str, default: Any = None) -> Any:
        """dict-compatible get() for Jinja2 templates (e.g. onboard.get('seg'))."""
        if key in ("leds", "uart", "buttons", "clk"):
            return getattr(self, key)
        return self._raw.get(key, default)

    def to_dict(self) -> dict:
        d = {"leds": self.leds, "uart": self.uart,
             "buttons": self.buttons, "clk": self.clk}
        for k, v in self._raw.items():
            if k not in d:
                d[k] = v
        return d


@dataclass
class PmodConfig:
    enabled: bool           = False
    slots:   Dict[str, str] = field(default_factory=dict)
    _raw:    Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, d: dict) -> "PmodConfig":
        slots = {k: v for k, v in d.items() if k != "enabled"}
        obj   = cls(enabled=bool(d.get("enabled", bool(slots))), slots=slots)
        object.__setattr__(obj, "_raw", dict(d))
        return obj

    def get(self, key: str, default: Any = None) -> Any:
        if key in ("enabled", "slots"):
            return getattr(self, key)
        return self._raw.get(key, default)

    def items(self):
        """dict-compatible items() for Jinja2: pmod.items() -> port/module pairs."""
        return self.slots.items()

    def to_dict(self) -> dict:
        d = {"enabled": self.enabled, "slots": self.slots}
        for k, v in self._raw.items():
            if k not in d:
                d[k] = v
        return d


# =============================================================================
# SoCModel
# =============================================================================

@dataclass
class SoCModel:
    ram_size:   int
    clock_freq: int
    board_type: str
    onboard:    OnboardConfig
    pmod:       PmodConfig
    mode:       SoCMode
    gen_dir:    str
    cfg_dir:    str
    root_dir:   str
    peripherals:        List[Peripheral]       = field(default_factory=list)
    standalone_modules: List[StandaloneModule] = field(default_factory=list)
    cpu_params:         Dict[str, Any]         = field(default_factory=dict)
    cpu_type:           str                    = "picorv32"
    cpu_files:          List[str]              = field(default_factory=list)
    cpu_port_map:       Dict[str, str]         = field(default_factory=dict)
    # RAM / memory map config (from project_config.yaml soc: block)
    ram_base:           int                    = 0x00000000
    ram_alias:          Optional[int]          = None
    reset_vector:       int                    = 0x00000000
    ram_latency:        str                    = "registered"   # "registered"|"combinational"
    init_file:          str                    = "gen/software.mif"
    stack_percent:      int                    = 25
    # RAM module identity (from ip_registry soc_ram entry + project_config soc:)
    ram_module:         str                    = "soc_ram"
    ram_inst:           str                    = "u_ram"
    ram_port_map:       Dict[str, str]         = field(default_factory=lambda: {
        "clk": "clk", "addr": "addr", "be": "be",
        "we": "we", "wdata": "wdata", "rdata": "rdata"
    })
    bus_fabrics:        List[BusFabric]        = field(default_factory=list)
    dependencies:       List[DependencyEdge]   = field(default_factory=list)

    # ---- derived ------------------------------------------------------------

    @property
    def ram_depth(self) -> int:
        return self.ram_size // 4

    @property
    def ram_addr_bits(self) -> int:
        return math.ceil(math.log2(self.ram_depth))

    @property
    def ram_addr_top(self) -> int:
        return self.ram_addr_bits + 1

    # ---- topology -----------------------------------------------------------

    def fabric_for(self, bus_type: BusType) -> Optional[BusFabric]:
        for f in self.bus_fabrics:
            if f.bus_type == bus_type:
                return f
        return None

    def peripherals_by_bus(self) -> Dict[BusType, List[Peripheral]]:
        groups: Dict[BusType, List[Peripheral]] = {}
        for p in self.peripherals:
            groups.setdefault(p.bus_type, []).append(p)
        return groups

    # ---- dependency graph ---------------------------------------------------

    def topological_sort(self) -> List[Peripheral]:
        """
        Return peripherals ordered so that dependencies come first.
        Uses Kahn's algorithm on IRQ + BUS edges between peripherals.
        Tie-broken by base address (deterministic).
        """
        inst_to_p = {p.inst: p for p in self.peripherals}
        in_deg: Dict[str, int]       = {p.inst: 0 for p in self.peripherals}
        adj:    Dict[str, List[str]] = {p.inst: [] for p in self.peripherals}

        for e in self.dependencies:
            if e.source in inst_to_p and e.target in inst_to_p:
                adj[e.target].append(e.source)
                in_deg[e.source] += 1

        queue = sorted(
            [p for p in self.peripherals if in_deg[p.inst] == 0],
            key=lambda p: p.base,
        )
        result: List[Peripheral] = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for dep_inst in sorted(adj[node.inst]):
                in_deg[dep_inst] -= 1
                if in_deg[dep_inst] == 0:
                    dep = inst_to_p[dep_inst]
                    for i, r in enumerate(queue):
                        if dep.base < r.base:
                            queue.insert(i, dep)
                            break
                    else:
                        queue.append(dep)

        # append any remaining (e.g. cycle guard)
        seen = {p.inst for p in result}
        result.extend(
            sorted([p for p in self.peripherals if p.inst not in seen],
                   key=lambda p: p.base))
        return result

    # ---- validation ---------------------------------------------------------

    def validate(self) -> None:
        errors: List[str] = []
        if self.ram_size <= 0:
            errors.append("ram_size must be > 0")
        if self.ram_size % 4 != 0:
            errors.append(f"ram_size {self.ram_size} is not a multiple of 4")
        if self.ram_size & (self.ram_size - 1):
            errors.append(f"ram_size {self.ram_size} is not a power of 2")

        if self.mode == SoCMode.SOC:
            errors.extend(self._check_address_space())
            errors.extend(self._check_irq_ids())
            errors.extend(self._check_top_port_names())
            errors.extend(self._check_bus_compatibility())
            for p in self.peripherals:
                errors.extend(p.validate())
            for f in self.bus_fabrics:
                errors.extend(f.validate())

        if errors:
            raise ConfigError("Model validation failed:\n" +
                              "".join(f"  * {e}\n" for e in errors))

    def _check_address_space(self) -> List[str]:
        """RAM <-> periph AND periph <-> periph overlap detection."""
        errors: List[str] = []
        regions: List[Tuple[int, int, str]] = [
            (self.ram_base, self.ram_base + self.ram_size - 1, "RAM")
        ]
        if self.ram_alias is not None:
            regions.append((
                self.ram_alias,
                self.ram_alias + self.ram_size - 1,
                f"RAM@0x{self.ram_alias:08X}",
            ))
        for p in self.peripherals:
            regions.append((p.base, p.end_addr, p.inst))

        for i, (b0, e0, n0) in enumerate(regions):
            for b1, e1, n1 in regions[i + 1:]:
                if b0 <= e1 and b1 <= e0:
                    errors.append(
                        f"Address overlap: '{n0}' [0x{b0:08X}..0x{e0:08X}] "
                        f"vs '{n1}' [0x{b1:08X}..0x{e1:08X}]")
        return errors

    def _check_irq_ids(self) -> List[str]:
        errors: List[str] = []
        seen: Dict[int, str] = {}
        for p in self.peripherals:
            for irq in p.irqs:
                if irq.id in seen:
                    errors.append(
                        f"IRQ id {irq.id} collision: '{seen[irq.id]}' and '{p.inst}'")
                seen[irq.id] = p.inst
        return errors

    def _check_top_port_names(self) -> List[str]:
        errors: List[str] = []
        seen: Dict[str, str] = {}
        for p in self.peripherals:
            for ep in p.ext_ports:
                if ep.top_port in seen:
                    errors.append(
                        f"soc_top port collision: '{ep.top_port}' "
                        f"in '{seen[ep.top_port]}' and '{p.inst}'")
                seen[ep.top_port] = p.inst
        return errors

    def _check_bus_compatibility(self) -> List[str]:
        errors: List[str] = []
        for p in self.peripherals:
            if p.bus_type == BusType.AXI_FULL and self.cpu_type == "picorv32":
                errors.append(
                    f"'{p.inst}' uses axi_full but picorv32 has no AXI master")
        return errors

    # ---- serialisation ------------------------------------------------------

    def _build_hash(self) -> str:
        """Deterministic SHA-256 hash of the SoC config (first 12 hex chars)."""
        import hashlib, json
        key_data = {
            "board":    self.board_type,
            "cpu":      self.cpu_type,
            "clock_hz": self.clock_freq,
            "ram_size":      self.ram_size,
            "ram_base":      f"0x{self.ram_base:08X}",
            "ram_alias":     f"0x{self.ram_alias:08X}" if self.ram_alias is not None else None,
            "ram_latency":   self.ram_latency,
            "reset_vector":  f"0x{self.reset_vector:08X}",
            "init_file":     self.init_file,
            "peripherals": sorted([
                {"inst": p.inst, "base": p.base, "size": p.size,
                 "module": p.module, "params": p.params}
                for p in self.peripherals
            ], key=lambda x: x["base"]),
        }
        return hashlib.sha256(
            json.dumps(key_data, sort_keys=True).encode()
        ).hexdigest()[:12]

    def address_gaps(self):
        """
        Return list of (gap_start, gap_end, size) for unused address ranges
        between consecutive regions (RAM + peripherals), sorted by address.
        Useful for debug and memory map documentation.
        """
        if not self.peripherals:
            return []
        regions = sorted(
            [(0, self.ram_size - 1)]
            + [(p.base, p.end_addr) for p in self.peripherals],
            key=lambda r: r[0],
        )
        gaps = []
        for i in range(len(regions) - 1):
            end_curr   = regions[i][1]
            start_next = regions[i + 1][0]
            if start_next > end_curr + 1:
                gap_size = start_next - end_curr - 1
                gaps.append((end_curr + 1, start_next - 1, gap_size))
        return gaps

    def to_dict(self) -> dict:
        all_irqs = sorted(
            [{"id": irq.id,
              "name": f"{p.inst.upper()}_{irq.name.upper()}_IRQ",
              "peripheral": p.inst}
             for p in self.peripherals for irq in p.irqs],
            key=lambda x: x["id"],
        )
        gaps = [
            {"start": f"0x{s:08X}", "end": f"0x{e:08X}", "size": sz}
            for s, e, sz in self.address_gaps()
        ]
        return {
            "meta": {
                "schema_version": "v4",
                "build_hash":  self._build_hash(),
                "board":       self.board_type,
                "cpu":         self.cpu_type,
                "clock_hz":    self.clock_freq,
                "ram_size":    self.ram_size,
                "mode":        self.mode.value,
            },
            "onboard":     self.onboard.to_dict(),
            "pmod":        self.pmod.to_dict(),
            "memory_map":  {
                "RAM": {"base": "0x00000000",
                        "end":  f"0x{self.ram_size - 1:08X}",
                        "size": self.ram_size, "module": "soc_ram"},
                **{p.inst: p.to_dict() for p in self.peripherals},
            },
            "irqs":        all_irqs,
            "address_gaps": gaps,
            "bus_fabrics": [f.to_dict() for f in self.bus_fabrics],
            "dependencies": [
                {"source": e.source, "target": e.target, "kind": e.kind.value}
                for e in self.dependencies
            ],
        }


# =============================================================================
# Exceptions
# =============================================================================

class ConfigError(Exception):
    """Raised for any configuration or schema error."""

