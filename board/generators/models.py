"""
models.py - SoC Framework intermediate model  (v5)
====================================================
v5 changes -- Node architecture:
  Each optional section of the SoC is represented by a dedicated node.
  A node is either ACTIVE (section present in YAML) or ABSENT.
  Absent nodes are excluded from JSON, DOT, and generator output.

  Nodes:
    ClockNode       -- active if clock_domains defined
    ResetNode       -- active if timing_config has reset section
    CpuNode         -- active if soc.cpu defined
    MemoryNode      -- active if soc.ram_size defined
    BusNode         -- active if peripherals with needs_bus exist
    PeripheralNode  -- active if peripherals section non-empty
    StandaloneNode  -- active if standalone_modules section non-empty

  SoCModel is now a thin composition of active nodes.
  validate() checks each active node independently + cross-node checks.
  to_dict() serialises only active nodes.
"""

from __future__ import annotations
import math
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Enums  (unchanged)
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
# Exception
# =============================================================================

class ConfigError(Exception):
    """Raised for any configuration or schema error."""


# =============================================================================
# Small value objects  (unchanged)
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
                errors.append(f"{inst}: param '{self.name}'={val} < min={self.min}")
            if self.max is not None and val > self.max:
                errors.append(f"{inst}: param '{self.name}'={val} > max={self.max}")
        elif self.type == ParamType.BOOL:
            if not isinstance(val, bool):
                errors.append(f"{inst}: param '{self.name}' must be bool")
        elif self.type == ParamType.STR:
            if not isinstance(val, str):
                errors.append(f"{inst}: param '{self.name}' must be str")
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
        if not (1 <= self.width <= 64):
            errors.append(
                f"{inst}.{self.name}: width {self.width} must be 1..64")
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
    """Descriptor for one cdc_reset_synchronizer instance."""
    inst_name:  str
    domain:     str
    clk_signal: str
    rst_in:     str
    rst_out:    str
    stages:     int = 2
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
    rst_signal:  str             = "RESET_N"
    ip_depends:  List[str]       = field(default_factory=list)

    @property
    def end_addr(self) -> int:
        return self.base + self.size - 1

    @property
    def addr_width(self) -> int:
        if self.size <= 1:
            return 1
        return math.ceil(math.log2(max(2, self.size)))

    @property
    def is_aligned(self) -> bool:
        if self.size & (self.size - 1):
            return (self.base % 4) == 0
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
# StandaloneModule
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

    def validate(self) -> List[str]:
        errors: List[str] = []
        for ep in self.ext_ports:
            errors.extend(ep.validate(self.inst))
        return errors

    def to_dict(self) -> dict:
        return {
            "inst":      self.inst,
            "module":    self.module,
            "clk_port":  self.clk_port,
            "rst_port":  self.rst_port,
            "params":    self.params,
            "ext_ports": [{"name": ep.name, "dir": ep.dir.value,
                           "width": ep.width, "top_port": ep.top_port}
                          for ep in self.ext_ports],
            "files":     self.files,
        }


# =============================================================================
# Board config objects
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
        return {"enabled": self.enabled, "slots": self.slots}


# =============================================================================
# RamConfig
# =============================================================================

@dataclass
class RamConfig:
    module:    str            = "soc_ram"
    inst:      str            = "u_ram"
    base:      int            = 0x00000000
    alias:     Optional[int]  = None
    size:      int            = 4096
    latency:   str            = "registered"
    init_file: str            = "gen/software.mif"
    port_map:  Dict[str, str] = field(default_factory=lambda: {
        "clk": "clk", "addr": "addr", "be": "be",
        "we": "we", "wdata": "wdata", "rdata": "rdata"
    })
    files:     List[str]      = field(default_factory=list)

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

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.size <= 0 or self.size % 4 != 0:
            errors.append(f"ram.size {self.size} must be > 0 and multiple of 4")
        if self.size & (self.size - 1):
            errors.append(f"ram.size {self.size} must be power of 2")
        if self.base < 0 or self.base % 4 != 0:
            errors.append(f"ram.base 0x{self.base:08X} must be >= 0 and 4-byte aligned")
        if self.alias is not None:
            if self.alias < 0 or self.alias % 4 != 0:
                errors.append(
                    f"ram.alias 0x{self.alias:08X} must be >= 0 and 4-byte aligned")
            if self.alias == self.base:
                errors.append(
                    f"ram.alias 0x{self.alias:08X} must differ from ram.base")
        if self.latency not in ("registered", "combinational"):
            errors.append(
                f"ram.latency must be 'registered' or 'combinational', "
                f"got {self.latency!r}")
        return errors

    def to_dict(self) -> dict:
        d = {
            "module":    self.module,
            "base":      f"0x{self.base:08X}",
            "end":       f"0x{self.end_addr:08X}",
            "size":      self.size,
            "latency":   self.latency,
            "init_file": self.init_file,
        }
        if self.alias is not None:
            d["alias"] = f"0x{self.alias:08X}"
        return d


# =============================================================================
# Feature Nodes  (v5 -- core new concept)
# =============================================================================

@dataclass
class ClockNode:
    """Active when clock_domains section is present."""
    domain_map: Dict[str, str] = field(default_factory=lambda: {"sys_clk": "SYS_CLK"})

    def validate(self) -> List[str]:
        return []

    def to_dict(self) -> dict:
        return {"domains": self.domain_map}


@dataclass
class ResetNode:
    """Active when timing_config has reset section."""
    syncs:       List[ResetSync] = field(default_factory=list)
    extra_files: List[str]       = field(default_factory=list)

    def rst_signal_for_domain(self, domain: str) -> str:
        for rs in self.syncs:
            if rs.domain == domain:
                return rs.rst_out
        if self.syncs:
            print(f"[WARN]  ResetNode: domain '{domain}' has no reset sync "
                  f"-- falling back to raw RESET_N", flush=True)
        return "RESET_N"

    def validate(self) -> List[str]:
        return []

    def to_dict(self) -> dict:
        return {"syncs": [
            {"inst": rs.inst_name, "domain": rs.domain,
             "clk": rs.clk_signal, "rst_in": rs.rst_in,
             "rst_out": rs.rst_out, "stages": rs.stages,
             "type": rs.sync_type}
            for rs in self.syncs
        ]}


@dataclass
class CpuNode:
    """Active when soc.cpu is defined."""
    cpu_type:     str           = "picorv32"
    cpu_files:    List[str]     = field(default_factory=list)
    cpu_port_map: Dict[str,str] = field(default_factory=dict)
    cpu_params:   Dict[str,Any] = field(default_factory=dict)
    reset_vector: int           = 0x00000000
    stack_percent: int          = 25

    def validate(self) -> List[str]:
        return []

    def to_dict(self) -> dict:
        return {
            "type":         self.cpu_type,
            "reset_vector": f"0x{self.reset_vector:08X}",
            "stack_percent": self.stack_percent,
        }


@dataclass
class MemoryNode:
    """Active when soc.ram_size is defined."""
    ram: RamConfig = field(default_factory=RamConfig)

    def validate(self) -> List[str]:
        return self.ram.validate()

    def to_dict(self) -> dict:
        return self.ram.to_dict()


@dataclass
class PeripheralNode:
    """Active when peripherals section is non-empty."""
    peripherals:  List[Peripheral]     = field(default_factory=list)
    bus_fabrics:  List[BusFabric]      = field(default_factory=list)
    dependencies: List[DependencyEdge] = field(default_factory=list)

    def validate(self) -> List[str]:
        errors: List[str] = []
        for p in self.peripherals:
            errors.extend(p.validate())
        for f in self.bus_fabrics:
            errors.extend(f.validate())
        errors.extend(self._check_address_overlap())
        errors.extend(self._check_irq_ids())
        return errors

    def _check_address_overlap(self) -> List[str]:
        errors: List[str] = []
        regions = [(p.base, p.end_addr, p.inst) for p in self.peripherals]
        for i, (b0, e0, n0) in enumerate(regions):
            for b1, e1, n1 in regions[i+1:]:
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

    def topological_sort(self) -> List[Peripheral]:
        """Kahn's algorithm: peripherals ordered so dependencies come first."""
        inst_to_p = {p.inst: p for p in self.peripherals}
        in_deg = {p.inst: 0 for p in self.peripherals}
        adj    = {p.inst: [] for p in self.peripherals}
        for e in self.dependencies:
            if e.source in inst_to_p and e.target in inst_to_p:
                adj[e.target].append(e.source)
                in_deg[e.source] += 1
        queue = sorted(
            [p for p in self.peripherals if in_deg[p.inst] == 0],
            key=lambda p: p.base)
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
        if len(result) != len(self.peripherals):
            in_cycle = [p.inst for p in self.peripherals
                        if p.inst not in {r.inst for r in result}]
            raise ConfigError(
                f"Dependency cycle detected: {in_cycle}")
        return result

    def to_dict(self) -> dict:
        return {
            "peripherals": {p.inst: p.to_dict() for p in self.peripherals},
            "bus_fabrics":  [f.to_dict() for f in self.bus_fabrics],
            "dependencies": [
                {"source": e.source, "target": e.target, "kind": e.kind.value}
                for e in self.dependencies
            ],
        }


@dataclass
class StandaloneNode:
    """Active when standalone_modules section is non-empty."""
    modules: List[StandaloneModule] = field(default_factory=list)

    def validate(self) -> List[str]:
        errors: List[str] = []
        # Validate individual modules
        for sm in self.modules:
            errors.extend(sm.validate())
        # Cross-module port collision check
        seen: Dict[str, str] = {}
        for sm in self.modules:
            for ep in sm.ext_ports:
                if ep.top_port in seen:
                    errors.append(
                        f"soc_top port collision: '{ep.top_port}' "
                        f"driven by '{seen[ep.top_port]}' and '{sm.inst}' -- "
                        f"use port_overrides in project_config.yaml to rename")
                seen[ep.top_port] = sm.inst
        return errors

    def to_dict(self) -> dict:
        return {"modules": {sm.inst: sm.to_dict() for sm in self.modules}}


# =============================================================================
# SoCModel  (v5 -- thin composition of active nodes)
# =============================================================================

@dataclass
class SoCModel:
    """
    Composed model of active nodes.
    Only nodes whose corresponding YAML section exists are activated.
    Absent nodes are None -- generators check before use.
    """
    # Required fields
    board_type:  str
    clock_freq:  int
    mode:        SoCMode
    gen_dir:     str
    cfg_dir:     str
    root_dir:    str
    onboard:     OnboardConfig
    pmod:        PmodConfig

    # Optional nodes -- None means "not present in YAML"
    clock_node:      Optional[ClockNode]      = None
    reset_node:      Optional[ResetNode]      = None
    cpu_node:        Optional[CpuNode]        = None
    memory_node:     Optional[MemoryNode]     = None
    peripheral_node: Optional[PeripheralNode] = None
    standalone_node: Optional[StandaloneNode] = None

    # Extra RTL files (cdc lib, etc.) -- added by generators
    extra_files:  List[str] = field(default_factory=list)

    # ---- convenience accessors (backward compat) ----------------------------

    @property
    def peripherals(self) -> List[Peripheral]:
        return self.peripheral_node.peripherals if self.peripheral_node else []

    @property
    def standalone_modules(self) -> List[StandaloneModule]:
        return self.standalone_node.modules if self.standalone_node else []

    @property
    def bus_fabrics(self) -> List[BusFabric]:
        return self.peripheral_node.bus_fabrics if self.peripheral_node else []

    @property
    def dependencies(self) -> List[DependencyEdge]:
        return self.peripheral_node.dependencies if self.peripheral_node else []

    @property
    def clock_domain_map(self) -> Dict[str, str]:
        return self.clock_node.domain_map if self.clock_node else {"sys_clk": "SYS_CLK"}

    @property
    def reset_syncs(self) -> List[ResetSync]:
        return self.reset_node.syncs if self.reset_node else []

    @reset_syncs.setter
    def reset_syncs(self, value: List[ResetSync]):
        if self.reset_node is None:
            self.reset_node = ResetNode()
        self.reset_node.syncs = value

    @property
    def cpu_type(self) -> str:
        return self.cpu_node.cpu_type if self.cpu_node else "none"

    @property
    def cpu_files(self) -> List[str]:
        return self.cpu_node.cpu_files if self.cpu_node else []

    @property
    def cpu_port_map(self) -> Dict[str, str]:
        return self.cpu_node.cpu_port_map if self.cpu_node else {}

    @property
    def reset_vector(self) -> int:
        return self.cpu_node.reset_vector if self.cpu_node else 0

    @property
    def stack_percent(self) -> int:
        return self.cpu_node.stack_percent if self.cpu_node else 25

    @property
    def ram(self) -> RamConfig:
        return self.memory_node.ram if self.memory_node else RamConfig()

    # RAM backward compat
    @property
    def ram_base(self) -> int:      return self.ram.base
    @property
    def ram_alias(self) -> Optional[int]: return self.ram.alias
    @property
    def ram_size(self) -> int:      return self.ram.size
    @property
    def ram_latency(self) -> str:   return self.ram.latency
    @property
    def init_file(self) -> str:     return self.ram.init_file
    @property
    def ram_module(self) -> str:    return self.ram.module
    @property
    def ram_inst(self) -> str:      return self.ram.inst
    @property
    def ram_port_map(self) -> Dict[str, str]: return self.ram.port_map
    @property
    def ram_files(self) -> List[str]:
        return self.memory_node.ram.files if self.memory_node else []
    @property
    def ram_depth(self) -> int:     return self.ram.depth
    @property
    def ram_addr_bits(self) -> int: return self.ram.addr_bits
    @property
    def ram_addr_top(self) -> int:  return self.ram.addr_top

    # ---- helpers -------------------------------------------------------------

    def rst_signal_for_domain(self, domain: str) -> str:
        if self.reset_node:
            return self.reset_node.rst_signal_for_domain(domain)
        return "RESET_N"

    def rst_signal_for_clock(self, clk_signal: str) -> str:
        domain = next(
            (d for d, s in self.clock_domain_map.items() if s == clk_signal),
            None)
        if domain:
            return self.rst_signal_for_domain(domain)
        return "RESET_N"

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

    def topological_sort(self) -> List[Peripheral]:
        if self.peripheral_node:
            return self.peripheral_node.topological_sort()
        return []

    # ---- active node summary -------------------------------------------------

    def active_nodes(self) -> List[str]:
        """Return names of active (non-None) nodes."""
        result = []
        if self.clock_node:      result.append("ClockNode")
        if self.reset_node:      result.append("ResetNode")
        if self.cpu_node:        result.append("CpuNode")
        if self.memory_node:     result.append("MemoryNode")
        if self.peripheral_node: result.append("PeripheralNode")
        if self.standalone_node: result.append("StandaloneNode")
        return result

    # ---- validation ----------------------------------------------------------

    def validate(self) -> None:
        errors: List[str] = []

        # Per-node validation
        for node in [self.clock_node, self.reset_node, self.cpu_node,
                     self.memory_node, self.peripheral_node, self.standalone_node]:
            if node is not None:
                errors.extend(node.validate())

        # Cross-node: peripheral port names must not collide with standalone ports
        seen_ports: Dict[str, str] = {}
        for p in self.peripherals:
            for ep in p.ext_ports:
                seen_ports[ep.top_port] = p.inst
        for sm in self.standalone_modules:
            for ep in sm.ext_ports:
                if ep.top_port in seen_ports:
                    errors.append(
                        f"soc_top port collision: '{ep.top_port}' "
                        f"in peripheral '{seen_ports[ep.top_port]}' "
                        f"and standalone '{sm.inst}'")

        # Cross-node: RAM must not overlap peripherals
        if self.memory_node and self.peripheral_node:
            ram_b = self.ram.base
            ram_e = self.ram.base + self.ram.size - 1
            for p in self.peripherals:
                if ram_b <= p.end_addr and p.base <= ram_e:
                    errors.append(
                        f"Address overlap: RAM [0x{ram_b:08X}..0x{ram_e:08X}] "
                        f"vs '{p.inst}' [0x{p.base:08X}..0x{p.end_addr:08X}]")

        if errors:
            raise ConfigError("Model validation failed:\n" +
                              "".join(f"  * {e}\n" for e in errors))

    # ---- serialisation -------------------------------------------------------

    def _build_hash(self) -> str:
        import hashlib, json
        key_data: dict = {
            "board":   self.board_type,
            "mode":    self.mode.value,
            "clock_hz": self.clock_freq,
            "active_nodes": self.active_nodes(),
        }
        if self.cpu_node:
            key_data["cpu"]          = self.cpu_type
            key_data["reset_vector"] = f"0x{self.reset_vector:08X}"
        if self.memory_node:
            key_data["ram_size"]    = self.ram_size
            key_data["ram_base"]    = f"0x{self.ram_base:08X}"
            key_data["ram_latency"] = self.ram_latency
        if self.clock_node:
            key_data["clock_domains"] = {
                k: v for k, v in sorted(self.clock_domain_map.items())}
        if self.reset_node:
            key_data["reset_syncs"] = sorted([
                f"{rs.domain}:{rs.clk_signal}:{rs.stages}:{rs.sync_type}"
                for rs in self.reset_syncs])
        if self.peripheral_node:
            key_data["peripherals"] = sorted([
                {"inst": p.inst, "base": p.base, "size": p.size}
                for p in self.peripherals], key=lambda x: x["base"])
        if self.standalone_node:
            key_data["standalone"] = sorted([
                {"inst": sm.inst, "module": sm.module}
                for sm in self.standalone_modules], key=lambda x: x["inst"])
        return hashlib.sha256(
            json.dumps(key_data, sort_keys=True).encode()
        ).hexdigest()[:12]

    def address_gaps(self) -> list:
        """Return gaps in address space (SOC mode only)."""
        if not self.memory_node or not self.peripheral_node:
            return []
        regions = sorted(
            [(self.ram.base, self.ram.base + self.ram.size - 1)]
            + ([(self.ram.alias, self.ram.alias + self.ram.size - 1)]
               if self.ram.alias is not None else [])
            + [(p.base, p.end_addr) for p in self.peripherals],
            key=lambda r: r[0])
        gaps = []
        for i in range(len(regions) - 1):
            end_curr   = regions[i][1]
            start_next = regions[i+1][0]
            if start_next > end_curr + 1:
                gaps.append((end_curr + 1, start_next - 1,
                              start_next - end_curr - 1))
        return gaps

    def to_dict(self) -> dict:
        """Serialize only active nodes -- absent nodes are omitted."""
        meta: dict = {
            "schema_version": "v5",
            "build_hash":     self._build_hash(),
            "board":          self.board_type,
            "mode":           self.mode.value,
            "clock_hz":       self.clock_freq,
            "active_nodes":   self.active_nodes(),
        }
        d: dict = {
            "meta":    meta,
            "onboard": self.onboard.to_dict(),
            "pmod":    self.pmod.to_dict(),
        }
        if self.clock_node:
            d["clocks"] = self.clock_node.to_dict()
        if self.reset_node:
            d["resets"] = self.reset_node.to_dict()
        if self.cpu_node:
            d["cpu"] = self.cpu_node.to_dict()
        if self.memory_node:
            d["memory"] = self.memory_node.to_dict()
        if self.peripheral_node:
            pdata = self.peripheral_node.to_dict()
            d["peripherals"] = pdata["peripherals"]
            d["bus_fabrics"]  = pdata["bus_fabrics"]
            gaps = self.address_gaps()
            if gaps:
                d["address_gaps"] = [
                    {"start": f"0x{s:08X}", "end": f"0x{e:08X}", "size": sz}
                    for s, e, sz in gaps]
            all_irqs = sorted(
                [{"id": irq.id,
                  "name": f"{p.inst.upper()}_{irq.name.upper()}_IRQ",
                  "peripheral": p.inst}
                 for p in self.peripherals for irq in p.irqs],
                key=lambda x: x["id"])
            if all_irqs:
                d["irqs"] = all_irqs
        if self.standalone_node:
            d["standalone"] = self.standalone_node.to_dict()
        return d
