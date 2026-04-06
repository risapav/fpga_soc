"""
models.py - SoC Framework intermediate model  (v4)
====================================================
Changes vs v3:
  - ClockPort: clock input port descriptor with resolved physical signal
  - ResetSync: descriptor for one cdc_reset_synchronizer instance
  - SoCModel.clock_domain_map: logical -> physical signal mapping
  - SoCModel.ram_files: absolute paths for RAM RTL files
  - SoCModel.reset_syncs: populated by RTLGenerator
  - SoCModel.extra_files: additional RTL files added by generators
  - SoCModel.rst_signal_for_domain(): helper for reset wire lookup
  - Peripheral.gen_regs: False = IP has self-contained register logic
  - Peripheral.clock_ports: List[ClockPort] for multi-clock IPs
  - Peripheral.rst_signal: resolved reset wire for this peripheral
  - Peripheral.ip_depends: List[str] - transitive IP dependencies
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
    HEX  = "hex"


# =============================================================================
# ParamDef
# =============================================================================

@dataclass
class ParamDef:
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
class ClockPort:
    """One clock input port of a peripheral."""
    port:   str
    domain: str = "sys_clk"
    signal: str = "SYS_CLK"


@dataclass
class ResetSync:
    """
    Descriptor for one cdc_reset_synchronizer instance in soc_top.

    inst_name  -- RTL instance name   (e.g. "u_rst_sync_sys_clk")
    domain     -- logical domain name (e.g. "sys_clk", "pixel_clk")
    clk_signal -- physical clock wire (e.g. "SYS_CLK", "pixel_clk")
    rst_in     -- input reset signal  (RESET_N or parent rst_out)
    rst_out    -- output wire name    (e.g. "sys_rst_n", "pixel_rst_n")
    stages     -- number of FF stages
    sync_type  -- "primary" | "cdc"
    sync_from  -- source domain for CDC type (empty for primary)
    """
    inst_name:  str
    domain:     str
    clk_signal: str
    rst_in:     str
    rst_out:    str
    stages:     int = 2
    # Issue 7: use Literal for sync_type to catch typos at IDE/type-check time
    sync_type:  str = "primary"   # "primary" | "cdc"
    sync_from:  str = ""

    def __post_init__(self):
        if self.sync_type not in ("primary", "cdc"):
            raise ValueError(
                f"ResetSync.sync_type must be 'primary' or 'cdc', "
                f"got {self.sync_type!r}")


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
                    f"{self.name}: self-loop bridge "
                    f"{b.from_type.value} -> {b.to_type.value}")
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
    inst:        str
    type:        str
    module:      str
    base:        int
    size:        int
    bus_type:    BusType
    clk_port:    str             = "SYS_CLK"
    rst_port:    str             = "RESET_N"
    ext_ports:   List[ExtPort]   = field(default_factory=list)
    irqs:        List[IrqLine]   = field(default_factory=list)
    registers:   List[RegField]  = field(default_factory=list)
    params:      Dict[str, Any]  = field(default_factory=dict)
    param_defs:  List[ParamDef]  = field(default_factory=list)
    files:       List[str]       = field(default_factory=list)
    gen_regs:    bool            = True
    clock_ports: List[ClockPort] = field(default_factory=list)
    # Resolved reset signal -- set by RTLGenerator, default = RESET_N
    rst_signal:  str             = "RESET_N"
    # Transitive IP dependencies from depends_on: in ip.yaml
    ip_depends:  List[str]       = field(default_factory=list)

    @property
    def end_addr(self) -> int:
        return self.base + self.size - 1

    @property
    def addr_width(self) -> int:
        """
        Address bits needed to index all registers in this peripheral.
        Issue 3 fix: safe for non-power-of-2 sizes (ceil(log2) of next power).
        """
        if self.size <= 1:
            return 1
        return math.ceil(math.log2(max(2, self.size)))

    @property
    def is_aligned(self) -> bool:
        """
        True if base address satisfies alignment requirements.
        - Power-of-2 size: base must be aligned to size (natural alignment)
        - Non-power-of-2 size: base must be 4-byte aligned (minimum)
        Issue 1 fix: previous logic returned True for non-power-of-2 regardless.
        """
        if self.size & (self.size - 1):
            # Non-power-of-2: require at minimum 4-byte alignment
            return (self.base % 4) == 0
        # Power-of-2: natural alignment
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
        ranges_seen: list = []
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
            "inst":         self.inst,
            "type":         self.type,
            "module":       self.module,
            "base":         f"0x{self.base:08X}",
            "end":          f"0x{self.end_addr:08X}",
            "size":         self.size,
            "bus_type":     self.bus_type.value,
            "addr_width":   self.addr_width,
            "params":       self.params,
            "registers":    [r.to_dict() for r in self.registers],
            "irqs":         [{"id": irq.id, "name": irq.name}
                             for irq in self.irqs],
            "ext_ports":    [{"name": ep.name, "dir": ep.dir.value,
                              "width": ep.width, "top_port": ep.top_port}
                             for ep in self.ext_ports],
            "clock_domain": self.clock_ports[0].domain if self.clock_ports else "sys_clk",
            "rst_signal":   self.rst_signal,
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
    clk_port:  str       = "SYS_CLK"
    rst_port:  str       = "RESET_N"


# =============================================================================
# Board config
# =============================================================================

@dataclass
class OnboardConfig:
    leds:    bool = False
    uart:    bool = False
    buttons: bool = False
    clk:     bool = True
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
        return self.slots.items()

    def to_dict(self) -> dict:
        d = {"enabled": self.enabled, "slots": self.slots}
        for k, v in self._raw.items():
            if k not in d:
                d[k] = v
        return d


# =============================================================================
# RamConfig  (Issue 6: extracted from SoCModel for clarity)
# =============================================================================

@dataclass
class RamConfig:
    """
    On-chip RAM configuration. Extracted from SoCModel to reduce field count
    and group related settings. Populated by builder from ip_registry soc_ram
    entry + project_config.yaml soc: block.
    """
    module:      str            = "soc_ram"
    inst:        str            = "u_ram"
    base:        int            = 0x00000000
    alias:       Optional[int]  = None
    size:        int            = 4096
    latency:     str            = "registered"   # "registered" | "combinational"
    init_file:   str            = "gen/software.mif"
    port_map:    Dict[str, str] = field(default_factory=lambda: {
        "clk": "clk", "addr": "addr", "be": "be",
        "we": "we", "wdata": "wdata", "rdata": "rdata"
    })
    files:       List[str]      = field(default_factory=list)

    @property
    def depth(self) -> int:
        return self.size // 4

    @property
    def addr_bits(self) -> int:
        return math.ceil(math.log2(self.depth))

    @property
    def addr_top(self) -> int:
        return self.addr_bits + 1

    @property
    def end_addr(self) -> int:
        return self.base + self.size - 1

    def to_dict(self) -> dict:
        d = {
            "module":   self.module,
            "base":     f"0x{self.base:08X}",
            "end":      f"0x{self.end_addr:08X}",
            "size":     self.size,
            "latency":  self.latency,
            "init_file": self.init_file,
        }
        if self.alias is not None:
            d["alias"] = f"0x{self.alias:08X}"
        return d


# =============================================================================
# SoCModel
# =============================================================================

@dataclass
class SoCModel:
    # ram_size removed as required field -- now a property via self.ram.size
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
    # Issue 6: RAM config grouped in RamConfig object
    # Backward-compat flat fields remain as properties below
    ram:                RamConfig              = field(default_factory=RamConfig)
    reset_vector:       int                    = 0x00000000
    stack_percent:      int                    = 25
    bus_fabrics:        List[BusFabric]        = field(default_factory=list)
    dependencies:       List[DependencyEdge]   = field(default_factory=list)
    clock_domain_map:   Dict[str, str]         = field(default_factory=lambda: {
        "sys_clk": "SYS_CLK"
    })
    # Populated by RTLGenerator when timing_cfg is present
    reset_syncs:        List[ResetSync]        = field(default_factory=list)
    # Extra RTL files added by generators (rst_sync, CDC lib, ...)
    extra_files:        List[str]              = field(default_factory=list)

    # ---- derived ------------------------------------------------------------
    # Backward-compat properties delegating to self.ram (Issue 6)

    @property
    def ram_base(self) -> int:
        return self.ram.base

    @property
    def ram_alias(self) -> Optional[int]:
        return self.ram.alias

    @property
    def ram_size(self) -> int:
        return self.ram.size

    @property
    def ram_latency(self) -> str:
        return self.ram.latency

    @property
    def init_file(self) -> str:
        return self.ram.init_file

    @property
    def ram_module(self) -> str:
        return self.ram.module

    @property
    def ram_inst(self) -> str:
        return self.ram.inst

    @property
    def ram_port_map(self) -> Dict[str, str]:
        return self.ram.port_map

    @property
    def ram_files(self) -> List[str]:
        return self.ram.files

    @property
    def ram_depth(self) -> int:
        return self.ram.depth

    @property
    def ram_addr_bits(self) -> int:
        return self.ram.addr_bits

    @property
    def ram_addr_top(self) -> int:
        return self.ram.addr_top

    # ---- reset helpers ------------------------------------------------------

    def rst_signal_for_domain(self, domain: str) -> str:
        """
        Return the reset wire name for a logical clock domain.
        Issue 5 fix: warn when domain has no sync (debug visibility).
        """
        for rs in self.reset_syncs:
            if rs.domain == domain:
                return rs.rst_out
        if self.reset_syncs:
            # Syncs exist but this domain has none -- likely a config gap
            import sys
            print(f"[WARN]  rst_signal_for_domain: domain '{domain}' has no "
                  f"reset sync -- falling back to raw RESET_N", flush=True)
        return "RESET_N"

    def rst_signal_for_clock(self, clk_signal: str) -> str:
        """Return reset wire for a physical clock signal."""
        domain = next(
            (d for d, s in self.clock_domain_map.items() if s == clk_signal),
            None)
        if domain:
            return self.rst_signal_for_domain(domain)
        return "RESET_N"

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
        Kahn's algorithm: peripherals ordered so dependencies come first.
        Tie-broken by base address (deterministic).

        Issue 1 fix: edge direction was inverted.
          DependencyEdge(source, target) means "source depends on target"
          so in the graph: target -> source (target must come first)
          Correct: adj[target].append(source), in_deg[source] += 1

        Issue 9: cycle detection -- raises ConfigError if cycle found.
        """
        inst_to_p = {p.inst: p for p in self.peripherals}
        in_deg: Dict[str, int]       = {p.inst: 0 for p in self.peripherals}
        # adj[x] = list of nodes that depend on x (x must come before them)
        adj:    Dict[str, List[str]] = {p.inst: [] for p in self.peripherals}

        for e in self.dependencies:
            # Only intra-peripheral edges (both must be instantiated peripherals)
            if e.source in inst_to_p and e.target in inst_to_p:
                # Issue 1 fix: target must come before source
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

        # Issue 9: cycle detection
        if len(result) != len(self.peripherals):
            in_cycle = [p.inst for p in self.peripherals
                        if p.inst not in {r.inst for r in result}]
            raise ConfigError(
                f"Dependency cycle detected among peripherals: "
                f"{in_cycle}\n"
                f"  Check depends_on: entries in ip.yaml files.")

        return result

    # ---- validation ---------------------------------------------------------

    def validate(self) -> None:
        errors: List[str] = []
        # RAM size checks
        if self.ram_size <= 0:
            errors.append("ram_size must be > 0")
        if self.ram_size % 4 != 0:
            errors.append(f"ram_size {self.ram_size} is not a multiple of 4")
        if self.ram_size & (self.ram_size - 1):
            errors.append(f"ram_size {self.ram_size} is not a power of 2")
        # Issue 6: validate RamConfig fields not covered by individual checks
        if self.ram.base < 0:
            errors.append(f"ram.base 0x{self.ram.base:08X} must be >= 0")
        if self.ram.base % 4 != 0:
            errors.append(f"ram.base 0x{self.ram.base:08X} must be 4-byte aligned")
        if self.ram.alias is not None:
            if self.ram.alias < 0:
                errors.append(f"ram.alias 0x{self.ram.alias:08X} must be >= 0")
            if self.ram.alias % 4 != 0:
                errors.append(
                    f"ram.alias 0x{self.ram.alias:08X} must be 4-byte aligned")
            if self.ram.alias == self.ram.base:
                errors.append(
                    f"ram.alias 0x{self.ram.alias:08X} must differ from ram.base")
        if self.ram.latency not in ("registered", "combinational"):
            errors.append(
                f"ram.latency must be 'registered' or 'combinational', "
                f"got {self.ram.latency!r}")

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
                        f"IRQ id {irq.id} collision: "
                        f"'{seen[irq.id]}' and '{p.inst}'")
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
        import hashlib, json
        key_data = {
            "board":        self.board_type,
            "cpu":          self.cpu_type,
            "clock_hz":     self.clock_freq,
            "ram_size":     self.ram_size,
            "ram_base":     f"0x{self.ram_base:08X}",
            "ram_alias":    (f"0x{self.ram_alias:08X}"
                             if self.ram_alias is not None else None),
            "ram_latency":  self.ram_latency,
            "reset_vector": f"0x{self.reset_vector:08X}",
            "init_file":    self.init_file,
            # Issue 7 fix: include clock domains + reset syncs in hash
            # so that timing config changes invalidate the build hash
            "clock_domains": {k: v for k, v in
                              sorted(self.clock_domain_map.items())},
            "reset_syncs":  sorted([
                f"{rs.domain}:{rs.clk_signal}:{rs.stages}:{rs.sync_type}"
                for rs in self.reset_syncs
            ]),
            "peripherals":  sorted([
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
        Issue 2 fix: use ram_base instead of hardcoded 0.
        Also includes ram_alias region if defined.
        """
        if not self.peripherals:
            return []
        ram_regions = [(self.ram_base, self.ram_base + self.ram_size - 1)]
        if self.ram_alias is not None:
            ram_regions.append((self.ram_alias, self.ram_alias + self.ram_size - 1))
        regions = sorted(
            ram_regions + [(p.base, p.end_addr) for p in self.peripherals],
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
            "onboard":      self.onboard.to_dict(),
            "pmod":         self.pmod.to_dict(),
            "memory_map":   {
                # Issue 3+6: use RamConfig.to_dict() for consistency
                "RAM": self.ram.to_dict(),
                **{p.inst: p.to_dict() for p in self.peripherals},
            },
            "irqs":         all_irqs,
            "address_gaps": gaps,
            "bus_fabrics":  [f.to_dict() for f in self.bus_fabrics],
            "reset_syncs":  [
                {"inst":    rs.inst_name, "domain": rs.domain,
                 "clk":     rs.clk_signal, "rst_in": rs.rst_in,
                 "rst_out": rs.rst_out,    "stages": rs.stages,
                 "type":    rs.sync_type}
                for rs in self.reset_syncs
            ],
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
