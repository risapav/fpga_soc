"""
builder.py - SoC Model Builder (v6)
=====================================
v6 changes -- NodeFactory architecture:
  ModelBuilder now delegates section detection to NodeFactory.
  Each YAML section activates a dedicated node via NodeFactory.
  Absent sections produce None nodes -- never default-constructed.

  NodeFactory._detect():
    ClockNode      -- if clock_domains in cfg or soc_ram has ram_base
    CpuNode        -- if soc.cpu defined
    MemoryNode     -- if soc.ram_size defined AND mode == soc
    PeripheralNode -- if peripherals section non-empty
    StandaloneNode -- if standalone_modules section non-empty
    ResetNode      -- populated by RTLGenerator from timing_cfg

  Address allocator: source-tagged tuples, sorted, defensive overlap check.
  lookup_registry: delegated to loader.py (no cyclic import).
"""

import os
import re
from typing import List, Dict, Tuple, Optional

from models import (
    SoCModel, SoCMode, ConfigError,
    # nodes
    ClockNode, ResetNode, CpuNode, MemoryNode, PeripheralNode, StandaloneNode,
    # data objects
    Peripheral, StandaloneModule, BusType, BusFabric, RamConfig,
    DependencyEdge, DepKind, ParamDef,
    OnboardConfig, PmodConfig, RegField, RegAccess,
    IrqLine, ExtPort, PortDir, ClockPort,
)
from loader import resolve_size, _warn, lookup_registry as _lookup_registry_util


# =============================================================================
# Registry lookup -- delegated to loader.py
# =============================================================================

def lookup_registry(registry: dict, inst_name: str,
                    inst_cfg: dict) -> Tuple[dict, str]:
    return _lookup_registry_util(registry, inst_name, inst_cfg)


# =============================================================================
# NodeFactory
# =============================================================================

class NodeFactory:
    """
    Inspects raw YAML config and activates only the nodes whose sections exist.
    Returns None for absent sections -- never constructs empty default nodes.
    """

    def __init__(self, cfg: dict, registry: dict):
        self.cfg      = cfg
        self.registry = registry
        self._mode    = SoCMode(cfg.get("demo", {}).get("mode", "soc"))
        self._soc     = cfg.get("soc") or {}

    # ------------------------------------------------------------------

    def build_clock_node(self) -> Optional[ClockNode]:
        """Active if clock_domains section present."""
        raw = self.cfg.get("clock_domains")
        if not raw:
            return None
        domain_map = {"sys_clk": "SYS_CLK", "reset": "RESET_N"}
        for domain, signal in raw.items():
            domain_map[domain] = str(signal)
        return ClockNode(domain_map=domain_map)

    def build_cpu_node(self) -> Optional[CpuNode]:
        """Active if soc.cpu is defined."""
        cpu_type = self._soc.get("cpu")
        if not cpu_type or self._mode != SoCMode.SOC:
            return None
        meta          = self.registry.get(cpu_type, {})
        cpu_files     = self._resolve_files(meta)
        reset_vector  = resolve_size(
            self._soc.get("reset_vector", meta.get("reset_vector", 0x00000000)))
        return CpuNode(
            cpu_type      = cpu_type,
            cpu_files     = cpu_files,
            cpu_port_map  = meta.get("port_map", {}),
            reset_vector  = reset_vector,
            stack_percent = self._soc.get("stack_percent", 25),
        )

    def build_memory_node(self) -> Optional[MemoryNode]:
        """Active if soc.ram_size defined AND mode == soc."""
        if self._mode != SoCMode.SOC:
            return None
        ram_size_raw = self._soc.get("ram_size")
        if not ram_size_raw:
            return None
        ram_meta  = self.registry.get("soc_ram", {})
        cpu_type  = self._soc.get("cpu", "picorv32")
        cpu_meta  = self.registry.get(cpu_type, {})
        ram_base  = resolve_size(
            self._soc.get("ram_base", cpu_meta.get("ram_base", 0x00000000)))
        alias_raw = self._soc.get("ram_alias", cpu_meta.get("ram_alias"))
        ram_alias = resolve_size(alias_raw) if alias_raw is not None else None
        return MemoryNode(ram=RamConfig(
            module    = ram_meta.get("module", "soc_ram"),
            inst      = "u_ram",
            base      = ram_base,
            alias     = ram_alias,
            size      = resolve_size(ram_size_raw),
            latency   = self._soc.get("ram_latency", "registered"),
            init_file = self._soc.get("init_file", "gen/software.mif"),
            port_map  = ram_meta.get("port_map", {
                "clk": "clk", "addr": "addr", "be": "be",
                "we": "we", "wdata": "wdata", "rdata": "rdata",
            }),
            files = self._resolve_files(ram_meta),
        ))

    def build_peripheral_node(self) -> Optional[PeripheralNode]:
        """Active if peripherals section is non-empty."""
        periph_cfg = self.cfg.get("peripherals", {})
        if not periph_cfg:
            return None
        return PeripheralNode()  # populated by ModelBuilder._instantiate_peripherals

    def build_standalone_node(self) -> Optional[StandaloneNode]:
        """Active if standalone_modules section is non-empty."""
        sa_cfg = self.cfg.get("standalone_modules", {})
        if not sa_cfg:
            return None
        return StandaloneNode()  # populated by ModelBuilder._instantiate_standalone

    def _resolve_files(self, meta: dict) -> List[str]:
        plugin_path = meta.get("_plugin_path", "")
        result = []
        for f in meta.get("files", []):
            if os.path.isabs(f):
                result.append(f)
            elif plugin_path:
                result.append(os.path.normpath(os.path.join(plugin_path, f)))
            else:
                _warn(f"Unresolved relative path '{f}' in IP metadata")
                result.append(f)
        return result


# =============================================================================
# ModelBuilder
# =============================================================================

class ModelBuilder:

    def __init__(self, raw_cfg: dict, registry: dict):
        self.cfg      = raw_cfg
        self.registry = registry
        # Address allocator: (base, end, source_label)
        self._allocated: List[Tuple[int, int, str]] = []
        self._auto_cursor = 0x90000000

    def build(self) -> SoCModel:
        factory = NodeFactory(self.cfg, self.registry)
        mode    = SoCMode(self.cfg.get("demo", {}).get("mode", "soc"))
        soc     = self.cfg.get("soc") or {}

        # Build all nodes (only active ones are non-None)
        clock_node      = factory.build_clock_node()
        cpu_node        = factory.build_cpu_node()
        memory_node     = factory.build_memory_node()
        peripheral_node = factory.build_peripheral_node()
        standalone_node = factory.build_standalone_node()

        onboard = OnboardConfig.from_dict(self.cfg.get("onboard", {}))
        pmod    = PmodConfig.from_dict(self.cfg.get("pmod", {}))

        model = SoCModel(
            board_type      = self.cfg.get("board", {}).get("type", "unknown"),
            clock_freq      = int(soc.get("clock_freq", 50_000_000)),
            mode            = mode,
            gen_dir         = "gen",
            cfg_dir         = "board/config",
            root_dir        = "",
            onboard         = onboard,
            pmod            = pmod,
            clock_node      = clock_node,
            cpu_node        = cpu_node,
            memory_node     = memory_node,
            peripheral_node = peripheral_node,
            standalone_node = standalone_node,
        )

        # Seed address allocator with RAM regions (if MemoryNode active)
        if memory_node:
            self._insert_allocated(
                memory_node.ram.base,
                memory_node.ram.base + memory_node.ram.size - 1,
                "RAM")
            if memory_node.ram.alias is not None:
                self._insert_allocated(
                    memory_node.ram.alias,
                    memory_node.ram.alias + memory_node.ram.size - 1,
                    "RAM@alias")

        # Seed with manually assigned peripheral addresses
        self._seed_manual_addresses()

        # Populate nodes
        if peripheral_node is not None:
            self._instantiate_peripherals(model, peripheral_node)
            self._build_bus_fabrics(peripheral_node, cpu_node)
            self._build_dependencies(peripheral_node, cpu_node)

        if standalone_node is not None:
            self._instantiate_standalone(model, standalone_node)

        model.validate()
        return model

    # -------------------------------------------------------------------------
    # Address allocator
    # -------------------------------------------------------------------------

    def _insert_allocated(self, base: int, end: int,
                           source: str = "<internal>") -> None:
        import bisect
        for b, e, s in self._allocated:
            if base <= e and end >= b:
                raise ConfigError(
                    f"Address collision: '{source}' [0x{base:08X}..0x{end:08X}] "
                    f"overlaps '{s}' [0x{b:08X}..0x{e:08X}]")
        keys = [r[0] for r in self._allocated]
        self._allocated.insert(bisect.bisect_left(keys, base), (base, end, source))

    def _allocate_address(self, size: int) -> int:
        alignment = size if (size & (size - 1)) == 0 else 4
        alignment = max(alignment, 4)
        cursor    = self._auto_cursor
        for _ in range(1024):
            if cursor % alignment:
                cursor += alignment - (cursor % alignment)
            if cursor + size - 1 > 0xFFFFFFFF:
                raise ConfigError(
                    f"Auto address allocator exhausted (0x{cursor:08X}, size=0x{size:X})")
            end = cursor + size - 1
            collision = next(
                ((b, e, s) for b, e, s in self._allocated
                 if cursor <= e and end >= b), None)
            if collision is None:
                self._insert_allocated(cursor, end, "<auto>")
                self._auto_cursor = cursor + size
                return cursor
            cursor = collision[1] + 1
        raise ConfigError(
            f"Auto address allocator failed after 1024 iterations (size=0x{size:X})")

    def _seed_manual_addresses(self):
        for inst, pcfg in self.cfg.get("peripherals", {}).items():
            if not isinstance(pcfg, dict) or not pcfg.get("enabled", True):
                continue
            raw_base = pcfg.get("base")
            if raw_base and raw_base != "auto":
                try:
                    base = resolve_size(raw_base)
                    meta, _ = lookup_registry(self.registry, inst, pcfg)
                    size    = resolve_size(meta.get("address_range", 0x100))
                    end     = base + size - 1
                    conflict = next(
                        ((b, e, s) for b, e, s in self._allocated
                         if base <= e and end >= b), None)
                    if conflict:
                        cb, ce, cs = conflict
                        raise ConfigError(
                            f"peripherals.{inst}: manual base 0x{base:08X} "
                            f"(size 0x{size:X}) overlaps '{cs}' "
                            f"[0x{cb:08X}..0x{ce:08X}]")
                    self._insert_allocated(base, end, f"peripherals.{inst}")
                except ConfigError:
                    raise
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # File resolution (shared)
    # -------------------------------------------------------------------------

    def _resolve_files(self, meta: dict) -> List[str]:
        plugin_path = meta.get("_plugin_path", "")
        result = []
        for f in meta.get("files", []):
            if os.path.isabs(f):
                result.append(f)
            elif plugin_path:
                result.append(os.path.normpath(os.path.join(plugin_path, f)))
            else:
                _warn(f"Unresolved relative path '{f}' in IP metadata")
                result.append(f)
        return result

    # -------------------------------------------------------------------------
    # Standalone node population
    # -------------------------------------------------------------------------

    def _instantiate_standalone(self, model: SoCModel, node: StandaloneNode):
        sa_cfg = self.cfg.get("standalone_modules", {})
        for inst, mcfg in sa_cfg.items():
            if not isinstance(mcfg, dict) or not mcfg.get("enabled", True):
                continue
            module_name = mcfg.get("module", inst)

            # Registry lookup: module name -> inst name -> by module field
            meta = self.registry.get(module_name) or self.registry.get(inst)
            if meta is None:
                meta = next(
                    (m for m in self.registry.values()
                     if isinstance(m, dict) and m.get("module") == module_name),
                    None)
            meta = meta or {}

            pm       = meta.get("port_map", {})
            clk_port = pm.get("clk",   "SYS_CLK")
            rst_port = pm.get("rst_n", "RESET_N")

            # Apply clock_domain override from project_config
            inst_clock_map = mcfg.get("clock_domains", {})
            if inst_clock_map and clk_port in inst_clock_map:
                # Resolve logical domain name to physical signal
                domain  = inst_clock_map[clk_port]
                signal  = model.clock_domain_map.get(domain, domain)
                clk_port = signal

            # Params: merge registry defaults with project overrides
            params = {}
            for pd in meta.get("params", []):
                if isinstance(pd, dict) and "name" in pd:
                    params[pd["name"]] = pd.get("default")
            params.update(mcfg.get("params", {}))

            # Port overrides (instance-level top_name remapping)
            port_overrides = mcfg.get("port_overrides", {})
            ext_ports = self._build_ext_ports(inst, meta, port_overrides)
            files     = self._resolve_files(meta)

            node.modules.append(StandaloneModule(
                inst      = inst,
                module    = module_name,
                params    = params,
                ext_ports = ext_ports,
                files     = files,
                clk_port  = clk_port,
                rst_port  = rst_port,
            ))

    # -------------------------------------------------------------------------
    # Peripheral node population
    # -------------------------------------------------------------------------

    def _instantiate_peripherals(self, model: SoCModel, node: PeripheralNode):
        clock_map = model.clock_domain_map
        for inst, pcfg in self.cfg.get("peripherals", {}).items():
            if not isinstance(pcfg, dict) or not pcfg.get("enabled", True):
                continue
            meta, reg_name = lookup_registry(self.registry, inst, pcfg)
            size    = resolve_size(meta.get("address_range", 0x100))
            raw_base = pcfg.get("base")
            base    = (self._allocate_address(size)
                       if raw_base == "auto"
                       else resolve_size(raw_base))
            clk_port, rst_port = self._resolve_port_map(meta)
            node.peripherals.append(Peripheral(
                inst        = inst,
                type        = reg_name,
                module      = meta["module"],
                base        = base,
                size        = size,
                bus_type    = BusType(meta.get("bus_type", "simple_bus")),
                clk_port    = clk_port,
                rst_port    = rst_port,
                params      = pcfg.get("params", {}),
                param_defs  = [ParamDef.from_dict(pd)
                               for pd in meta.get("params", [])],
                files       = self._resolve_files(meta),
                registers   = self._build_registers(inst, meta),
                irqs        = self._build_irqs(meta),
                ext_ports   = self._build_ext_ports(inst, meta),
                gen_regs    = bool(meta.get("gen_regs", True)),
                clock_ports = self._build_clock_ports(inst, meta, pcfg, clock_map),
                ip_depends  = self._resolve_depends(inst, meta),
            ))

    def _build_bus_fabrics(self, node: PeripheralNode,
                           cpu_node: Optional[CpuNode]):
        fabrics_map = {}
        for p in node.peripherals:
            bt = p.bus_type
            if bt not in fabrics_map:
                fabrics_map[bt] = BusFabric(bus_type=bt)
            fabrics_map[bt].slaves.append(p)
        cpu_name = cpu_node.cpu_type if cpu_node else "none"
        for fabric in fabrics_map.values():
            fabric.masters.append(cpu_name)
            node.bus_fabrics.append(fabric)

    def _build_dependencies(self, node: PeripheralNode,
                             cpu_node: Optional[CpuNode]):
        inst_names = {p.inst for p in node.peripherals}
        seen: set  = set()
        cpu_name   = cpu_node.cpu_type if cpu_node else "none"

        def _add(source: str, target: str, kind: DepKind):
            key = (source, target, kind)
            if key not in seen:
                seen.add(key)
                node.dependencies.append(DependencyEdge(source, target, kind))

        for p in node.peripherals:
            _add(p.inst, "SYS_CLK", DepKind.CLOCK)
            _add(p.inst, "RESET_N", DepKind.RESET)
            _add(p.inst, cpu_name,  DepKind.BUS)
            for dep_type in p.ip_depends:
                if dep_type in inst_names:
                    _add(p.inst, dep_type, DepKind.BUS)
                else:
                    for other in node.peripherals:
                        if other.type == dep_type and other.inst != p.inst:
                            _add(p.inst, other.inst, DepKind.BUS)

    # -------------------------------------------------------------------------
    # Sub-object builders (shared between peripheral and standalone)
    # -------------------------------------------------------------------------

    def _resolve_port_map(self, meta: dict):
        pm = meta.get("port_map", {})
        return pm.get("clk", "SYS_CLK"), pm.get("rst_n", "RESET_N")

    def _build_registers(self, inst: str, meta: dict):
        result = []
        for r in meta.get("registers", []):
            if not isinstance(r, dict):
                continue
            try:
                result.append(RegField(
                    name   = r["name"],
                    offset = resolve_size(r["offset"]),
                    access = RegAccess(r.get("access", "rw")),
                    width  = int(r.get("width", 32)),
                    reset  = resolve_size(r.get("reset", 0)),
                    desc   = r.get("desc", ""),
                ))
            except (KeyError, ValueError) as e:
                raise ConfigError(
                    f"IP '{inst}': malformed register entry {r!r}: {e}")
        return result

    def _build_irqs(self, meta: dict):
        result = []
        for irq in meta.get("interrupts", []):
            if not isinstance(irq, dict):
                continue
            result.append(IrqLine(
                id   = int(irq["id"]),
                name = irq.get("name", f"irq{irq['id']}"),
            ))
        return result

    def _build_ext_ports(self, inst: str, meta: dict,
                         port_overrides: dict = None):
        BUS_IFACE = {"simple_bus", "axi_lite", "axi_full", "axi_stream"}
        overrides = port_overrides or {}
        result    = []
        for iface in meta.get("interfaces", []):
            if not isinstance(iface, dict):
                continue
            if iface.get("type") in BUS_IFACE:
                continue
            for sig in iface.get("signals", []):
                if not isinstance(sig, dict):
                    continue
                sig_name = sig["name"]
                dir_str  = sig.get("dir", "output")
                width    = int(sig.get("width", 1))
                top_name = sig.get("top_name") or sig.get("top_port")
                if not top_name:
                    top_name = (sig_name.upper() if sig.get("no_prefix")
                                else f"{inst}_{sig_name}")
                # Instance-level override
                top_port = overrides.get(top_name, top_name)
                try:
                    port_dir = PortDir(dir_str)
                except ValueError:
                    raise ConfigError(
                        f"IP '{inst}': unknown port direction {dir_str!r}")
                result.append(ExtPort(
                    name=sig_name, dir=port_dir,
                    width=width, top_port=top_port))
        return result

    def _build_clock_ports(self, inst: str, meta: dict,
                           pcfg: dict, model_clock_map: dict) -> list:
        inst_overrides = pcfg.get("clock_domains", {})
        ip_clocks      = meta.get("clocks", [])
        if ip_clocks:
            ports = []
            for ck in ip_clocks:
                port   = ck["port"]
                domain = inst_overrides.get(port, ck.get("domain", "sys_clk"))
                signal = model_clock_map.get(domain)
                if signal is None:
                    _warn(f"{inst}.{port}: domain '{domain}' not in "
                          f"clock_domains map -- using SYS_CLK")
                    signal = "SYS_CLK"
                ports.append(ClockPort(port=port, domain=domain, signal=signal))
            return ports
        single_domain = meta.get("clock_domain", "sys_clk")
        pm            = meta.get("port_map", {})
        clk_port      = pm.get("clk", "SYS_CLK")
        domain        = inst_overrides.get(clk_port, single_domain)
        signal        = model_clock_map.get(domain, "SYS_CLK")
        return [ClockPort(port=clk_port, domain=domain, signal=signal)]

    def _resolve_depends(self, inst: str, meta: dict) -> List[str]:
        visited = set()
        result  = []

        def _collect(ip_name: str, depth: int = 0):
            if depth > 16 or ip_name in visited:
                return
            visited.add(ip_name)
            dep_meta = self.registry.get(ip_name)
            if dep_meta is None:
                from loader import _WARNINGS_AS_ERRORS
                msg = (f"{inst}: depends_on '{ip_name}' not found in registry")
                if _WARNINGS_AS_ERRORS:
                    raise ConfigError(msg)
                _warn(msg)
                return
            for sub in dep_meta.get("depends_on", []):
                _collect(sub, depth + 1)
            result.append(ip_name)

        for dep in meta.get("depends_on", []):
            _collect(dep)
        return result

    def _lookup(self, inst: str, pcfg: dict) -> Tuple[dict, str]:
        return lookup_registry(self.registry, inst, pcfg)
