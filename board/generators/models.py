"""
models.py - SoC Framework intermediate model
Dataclasses and Enums for type-safe generator pipeline.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List


# =============================================================================
# Enums
# =============================================================================

class PortDir(str, Enum):
    OUTPUT = "output"
    INPUT  = "input"
    INOUT  = "inout"

    def sv(self) -> str:
        """SystemVerilog port direction keyword."""
        return {"output": "output wire", "input": "input  wire",
                "inout":  "inout  wire"}[self.value]


class RegAccess(str, Enum):
    RW = "rw"
    RO = "ro"
    WO = "wo"


class BusType(str, Enum):
    SIMPLE  = "simple_bus"
    AXI_LITE   = "axi_lite"
    AXI_FULL   = "axi_full"
    AXI_STREAM = "axi_stream"
    NONE    = "none"


class SoCMode(str, Enum):
    SOC        = "soc"
    STANDALONE = "standalone"


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class RegField:
    name:   str
    offset: int        # byte offset (must be 4-byte aligned)
    access: RegAccess
    width:  int  = 32
    reset:  int  = 0
    desc:   str  = ""

    @property
    def word_addr(self) -> int:
        return self.offset >> 2


@dataclass
class ExtPort:
    name:     str       # exact .sv port name
    dir:      PortDir
    width:    int
    top_port: str       # resolved soc_top port name

    @property
    def width_str(self) -> str:
        return f" [{self.width-1}:0]" if self.width > 1 else "      "


@dataclass
class IrqLine:
    id:   int
    name: str


@dataclass
class Peripheral:
    inst:       str
    type:       str        # registry key (base type, e.g. 'uart')
    module:     str        # SV module name (e.g. 'uart_top')
    base:       int        # base address
    size:       int        # address range in bytes
    clk_port:   str        # clock port name in .sv
    rst_port:   str        # reset port name in .sv
    addr_width: int        # address bus width for bus.addr slice
    ext_ports:  List[ExtPort]
    irqs:       List[IrqLine]
    registers:  List[RegField]
    params:     dict = field(default_factory=dict)
    files:      list = field(default_factory=list)  # extra .sv files

    @property
    def end_addr(self) -> int:
        return self.base + self.size - 1


@dataclass
class StandaloneModule:
    inst:      str
    module:    str
    params:    dict
    ext_ports: List[ExtPort]
    files:     list = field(default_factory=list)


@dataclass
class SoCModel:
    # Core parameters
    ram_size:   int
    clock_freq: int
    # Board
    board_type: str
    onboard:    dict
    pmod:       dict
    # Mode
    mode:       SoCMode
    # Paths
    gen_dir:    str
    cfg_dir:    str
    root_dir:   str
    # Content
    peripherals:        List[Peripheral]       = field(default_factory=list)
    standalone_modules: List[StandaloneModule] = field(default_factory=list)
    cpu_params:         dict                   = field(default_factory=dict)
    cpu_type:           str                    = 'picorv32'
    cpu_files:          list                   = field(default_factory=list)

    @property
    def ram_depth(self) -> int:
        return self.ram_size // 4

    @property
    def ram_addr_bits(self) -> int:
        import math
        return math.ceil(math.log2(self.ram_depth))

    @property
    def ram_addr_top(self) -> int:
        return self.ram_addr_bits + 1  # for bus.addr[N:2] slice
