"""
builder.py - SoC Model Builder (v5)
=====================================
Changes vs v4.2:
  - Issue 1 FIXED: _resolve_files() centralizes path resolution for ALL IPs
    (previously only RAM files were resolved to absolute paths)
  - Issue 2 FIXED: smart address allocator collision detection
    Tracks manual + RAM regions, skips over collisions instead of silent overlap
  - Issue 3 FIXED: ip_depends edges added to dependency graph
  - Issue 6 FIXED: lookup_registry moved to shared utility in loader.py,
    ModelBuilder._lookup() delegates to it (no more duplicated logic)
  - lookup_registry imported from loader as shared utility
"""

import os
import re
from typing import List, Dict, Tuple, Optional

from models import (
    SoCModel, Peripheral, BusType, BusFabric,
    DependencyEdge, DepKind, ConfigError, ParamDef,
    OnboardConfig, PmodConfig, RamConfig, RegField, RegAccess,
    IrqLine, ExtPort, PortDir, ClockPort, SoCMode
)
from loader import resolve_size, _warn, lookup_registry as _lookup_registry_util


# =============================================================================
# Registry lookup -- delegated to loader.py (MEDIUM fix: prevents cyclic import)
# =============================================================================

def lookup_registry(registry: dict, inst_name: str,
                    inst_cfg: dict) -> Tuple[dict, str]:
    """Delegate to loader.lookup_registry (single source of truth)."""
    return _lookup_registry_util(registry, inst_name, inst_cfg)


# =============================================================================
# ModelBuilder
# =============================================================================

class ModelBuilder:
    def __init__(self, raw_cfg: dict, registry: dict):
        self.cfg      = raw_cfg
        self.registry = registry
        # Issue 2: track all allocated regions (base, end) for collision detection
        self._allocated: List[Tuple[int, int]] = []
        self._auto_cursor = 0x90000000

    def build(self) -> SoCModel:
        """Main model build pipeline."""
        model = self._create_base_model()

        # Issue 2: seed allocator with RAM regions
        self._insert_allocated(model.ram.base,
                               model.ram.base + model.ram.size - 1)
        if model.ram.alias is not None:
            self._insert_allocated(model.ram.alias,
                                   model.ram.alias + model.ram.size - 1)

        # Seed with manually-assigned peripheral addresses (first pass)
        for inst, pcfg in self.cfg.get("peripherals", {}).items():
            if not isinstance(pcfg, dict) or not pcfg.get("enabled", True):
                continue
            raw_base = pcfg.get("base")
            if raw_base and raw_base != "auto":
                try:
                    base = resolve_size(raw_base)
                    meta, _ = lookup_registry(self.registry, inst, pcfg)
                    size    = resolve_size(meta.get("address_range", 0x100))
                    end = base + size - 1
                    # Issue 7: check collision with already-registered regions
                    conflict = next(
                        ((b, e) for b, e in self._allocated
                         if base <= e and end >= b),
                        None)
                    if conflict:
                        cb, ce = conflict
                        raise ConfigError(
                            f"peripherals.{inst}: manual base 0x{base:08X} "
                            f"(size 0x{size:X}) overlaps already-assigned region "
                            f"[0x{cb:08X}..0x{ce:08X}]")
                    self._insert_allocated(base, end)
                except ConfigError:
                    raise   # Issue 7: propagate manual conflicts immediately
                except Exception:
                    pass    # lookup failure handled by cross-validation

        self._instantiate_peripherals(model)
        self._build_bus_fabrics(model)
        self._build_dependencies(model)
        model.validate()
        return model

    # -------------------------------------------------------------------------
    # Base model
    # -------------------------------------------------------------------------

    def _create_base_model(self) -> SoCModel:
        soc   = self.cfg.get("soc", {})
        board = self.cfg.get("board", {})

        cpu_type = soc.get("cpu", "picorv32")
        cpu_meta = self.registry.get(cpu_type, {})

        # CPU-driven defaults
        reset_vector = resolve_size(
            soc.get("reset_vector",
                    cpu_meta.get("reset_vector", 0x00000000)))
        ram_base = resolve_size(
            soc.get("ram_base",
                    cpu_meta.get("ram_base", 0x00000000)))
        ram_alias_raw = soc.get("ram_alias", cpu_meta.get("ram_alias"))
        ram_alias = (resolve_size(ram_alias_raw)
                     if ram_alias_raw is not None else None)

        # RAM module defaults -- build RamConfig object (Issue 6)
        ram_meta     = self.registry.get("soc_ram", {})
        ram_cfg      = RamConfig(
            module   = ram_meta.get("module", "soc_ram"),
            inst     = "u_ram",
            base     = ram_base,
            alias    = ram_alias,
            size     = resolve_size(soc.get("ram_size", 4096)),
            latency  = soc.get("ram_latency", "registered"),
            init_file= soc.get("init_file", "gen/software.mif"),
            port_map = ram_meta.get("port_map", {
                "clk": "clk", "addr": "addr", "be": "be",
                "we": "we", "wdata": "wdata", "rdata": "rdata"
            }),
            files    = self._resolve_files(ram_meta),
        )
        cpu_port_map    = cpu_meta.get("port_map", {})

        # Issue 4 fix: CPU files use centralized _resolve_files() like all others
        # (previously had custom logic -- now unified)
        cpu_files = self._resolve_files(cpu_meta)

        # Clock domain map
        clock_domain_map = {"sys_clk": "SYS_CLK", "reset": "RESET_N"}
        for domain, signal in self.cfg.get("clock_domains", {}).items():
            clock_domain_map[domain] = str(signal)

        onboard = OnboardConfig.from_dict(self.cfg.get("onboard", {}))
        pmod    = PmodConfig.from_dict(self.cfg.get("pmod", {}))

        return SoCModel(
            clock_freq       = int(soc.get("clock_freq", 50_000_000)),
            board_type       = board.get("type", "unknown"),
            onboard          = onboard,
            pmod             = pmod,
            mode             = SoCMode(self.cfg.get("demo", {}).get("mode", "soc")),
            gen_dir          = "gen",
            cfg_dir          = "board/config",
            root_dir         = "",
            cpu_type         = cpu_type,
            cpu_port_map     = cpu_port_map,
            cpu_files        = cpu_files,
            reset_vector     = reset_vector,
            ram              = ram_cfg,
            clock_domain_map = clock_domain_map,
            stack_percent    = soc.get("stack_percent", 25),
        )

    # -------------------------------------------------------------------------
    # Issue 1 fix: centralized file resolution
    # -------------------------------------------------------------------------

    def _resolve_files(self, meta: dict) -> List[str]:
        """
        Resolve all file paths in meta['files'] to absolute paths.
        Uses meta['_plugin_path'] as base for relative paths.
        All IPs (RAM, CPU, peripherals) use this single method.
        """
        plugin_path = meta.get("_plugin_path", "")
        result = []
        for f in meta.get("files", []):
            if os.path.isabs(f):
                result.append(f)
            elif plugin_path:
                result.append(os.path.normpath(
                    os.path.join(plugin_path, f)))
            else:
                _warn(f"Unresolved relative path '{f}' in IP metadata "
                      f"(no _plugin_path set) -- may not be found at build time")
                result.append(f)
        return result

    # -------------------------------------------------------------------------
    # Peripheral instantiation
    # -------------------------------------------------------------------------

    def _instantiate_peripherals(self, model: SoCModel):
        periphs_cfg = self.cfg.get("peripherals", {})

        for inst, pcfg in periphs_cfg.items():
            if not pcfg.get("enabled", True):
                continue

            meta, reg_name = lookup_registry(self.registry, inst, pcfg)

            raw_base = pcfg.get("base")
            size     = resolve_size(meta.get("address_range", 0x100))

            if raw_base == "auto":
                base = self._allocate_address(size)
            else:
                base = resolve_size(raw_base)

            p_defs      = [ParamDef.from_dict(pd)
                           for pd in meta.get("params", [])]
            clk_port, rst_port = self._resolve_port_map(meta)
            clock_ports = self._build_clock_ports(
                inst, meta, pcfg, model.clock_domain_map)
            registers   = self._build_registers(inst, meta)
            irqs        = self._build_irqs(meta)
            ext_ports   = self._build_ext_ports(inst, meta)
            ip_depends  = self._resolve_depends(inst, meta)

            # Issue 1 fix: use centralized file resolution
            files = self._resolve_files(meta)

            p = Peripheral(
                inst        = inst,
                type        = reg_name,
                module      = meta["module"],
                base        = base,
                size        = size,
                bus_type    = BusType(meta.get("bus_type", "simple_bus")),
                clk_port    = clk_port,
                rst_port    = rst_port,
                params      = pcfg.get("params", {}),
                param_defs  = p_defs,
                files       = files,
                registers   = registers,
                irqs        = irqs,
                ext_ports   = ext_ports,
                gen_regs    = bool(meta.get("gen_regs", True)),
                clock_ports = clock_ports,
                ip_depends  = ip_depends,
            )
            model.peripherals.append(p)

    # -------------------------------------------------------------------------
    # Registry sub-object builders
    # -------------------------------------------------------------------------

    def _resolve_port_map(self, meta: dict):
        pm  = meta.get("port_map", {})
        clk = pm.get("clk", "SYS_CLK")
        rst = pm.get("rst_n", "RESET_N")
        return clk, rst

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

    def _build_ext_ports(self, inst: str, meta: dict):
        BUS_IFACE_TYPES = {"simple_bus", "axi_lite", "axi_full", "axi_stream"}
        result = []
        for iface in meta.get("interfaces", []):
            if not isinstance(iface, dict):
                continue
            if iface.get("type") in BUS_IFACE_TYPES:
                continue
            for sig in iface.get("signals", []):
                if not isinstance(sig, dict):
                    continue
                sig_name  = sig["name"]
                dir_str   = sig.get("dir", "output")
                width     = int(sig.get("width", 1))
                no_prefix = sig.get("no_prefix", False)
                top_name  = sig.get("top_name") or sig.get("top_port")
                if top_name:
                    top_port = top_name
                elif no_prefix:
                    top_port = sig_name.upper()
                else:
                    top_port = f"{inst}_{sig_name}"
                try:
                    port_dir = PortDir(dir_str)
                except ValueError:
                    raise ConfigError(
                        f"IP '{inst}': unknown port direction {dir_str!r} "
                        f"for signal '{sig_name}'")
                result.append(ExtPort(
                    name=sig_name, dir=port_dir,
                    width=width, top_port=top_port))
        return result

    # -------------------------------------------------------------------------
    # Clock port resolution
    # -------------------------------------------------------------------------

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
        signal        = model_clock_map.get(domain)
        if signal is None:
            _warn(f"{inst}.{clk_port}: domain '{domain}' not in "
                  f"clock_domains map -- using SYS_CLK")
            signal = "SYS_CLK"
        return [ClockPort(port=clk_port, domain=domain, signal=signal)]

    # -------------------------------------------------------------------------
    # IP dependency resolution
    # -------------------------------------------------------------------------

    def _resolve_depends(self, inst: str, meta: dict) -> List[str]:
        """
        Transitively resolve depends_on: list from ip.yaml.
        Returns ordered list (dependencies before dependants).
        Detects and breaks cycles with a warning.
        """
        visited = set()
        result  = []

        def _collect(ip_name: str, depth: int = 0):
            if depth > 16:
                _warn(f"{inst}: dependency chain too deep at '{ip_name}' "
                      f"-- possible cycle, stopping")
                return
            if ip_name in visited:
                return
            visited.add(ip_name)
            dep_meta = self.registry.get(ip_name)
            if dep_meta is None:
                from loader import _WARNINGS_AS_ERRORS
                msg = (f"{inst}: depends_on '{ip_name}' not found in registry "
                       f"-- add its ip.yaml to ip_plugins")
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

    # -------------------------------------------------------------------------
    # Issue 2+3+7: smart address allocator with sorted regions
    # -------------------------------------------------------------------------

    def _insert_allocated(self, base: int, end: int) -> None:
        """
        Insert region sorted by base (Issue 3: O(log n) ready).
        Defensive overlap check catches internal allocator bugs early.
        """
        import bisect
        for b, e in self._allocated:
            if base <= e and end >= b:
                raise ConfigError(
                    f"Internal allocator overlap at "
                    f"[0x{base:08X}..0x{end:08X}] vs [0x{b:08X}..0x{e:08X}]"
                    f" -- please file a bug report")
        keys = [r[0] for r in self._allocated]
        self._allocated.insert(bisect.bisect_left(keys, base), (base, end))

    def _allocate_address(self, size: int) -> int:
        """
        Allocate next free address block of given size.

        - Alignment: address must be multiple of size (natural alignment)
        - Collision detection: skips over already-allocated regions
          (RAM, manual peripherals, previously auto-allocated)
        - Raises ConfigError if no free slot found within 256 MB window
        """
        # Issue 2 fix: power-of-2 sizes use natural alignment (base % size == 0)
        # Non-power-of-2 sizes fall back to 4-byte alignment
        alignment = size if (size & (size - 1)) == 0 else 4
        alignment = max(alignment, 4)   # minimum 4-byte
        cursor    = self._auto_cursor
        max_addr  = 0xFFFFFFFF

        for _ in range(1024):   # max iterations guard
            # Align cursor
            if cursor % alignment:
                cursor += alignment - (cursor % alignment)

            if cursor + size - 1 > max_addr:
                raise ConfigError(
                    f"Auto address allocator exhausted address space "
                    f"(last tried: 0x{cursor:08X}, size=0x{size:X})")

            end = cursor + size - 1
            # Check for collision with any allocated region
            collision = next(
                ((b, e) for b, e in self._allocated if cursor <= e and end >= b),
                None)

            if collision is None:
                # Free slot found -- insert sorted (Issue 3)
                self._insert_allocated(cursor, end)
                self._auto_cursor = cursor + size
                return cursor
            else:
                # Jump past the colliding region
                cursor = collision[1] + 1

        raise ConfigError(
            f"Auto address allocator failed after 1024 iterations "
            f"(size=0x{size:X}) -- check manual base assignments")

    # -------------------------------------------------------------------------
    # Issue 6 fix: _lookup delegates to shared utility
    # -------------------------------------------------------------------------

    def _lookup(self, inst: str, pcfg: dict) -> Tuple[dict, str]:
        return lookup_registry(self.registry, inst, pcfg)

    # -------------------------------------------------------------------------
    # Bus fabrics
    # -------------------------------------------------------------------------

    def _build_bus_fabrics(self, model: SoCModel):
        fabrics_map = {}
        for p in model.peripherals:
            bt = p.bus_type
            if bt not in fabrics_map:
                fabrics_map[bt] = BusFabric(bus_type=bt)
            fabrics_map[bt].slaves.append(p)
        for bt, fabric in fabrics_map.items():
            fabric.masters.append(model.cpu_type)
            model.bus_fabrics.append(fabric)

    # -------------------------------------------------------------------------
    # Issue 3 fix: dependency graph includes ip_depends
    # -------------------------------------------------------------------------

    def _build_dependencies(self, model: SoCModel):
        """
        Build dependency graph for topological ordering in RTL.

        Edges:
          - CLOCK: every peripheral depends on SYS_CLK
          - RESET: every peripheral depends on RESET_N
          - BUS:   every peripheral depends on CPU
          - ip_depends: inter-IP edges (only for instantiated peripherals)

        Issue 8 fix: deduplication via seen set prevents duplicate edges
        that would inflate in_deg counts and break topological sort.
        """
        inst_names = {p.inst for p in model.peripherals}
        seen_edges: set = set()   # (source, target, kind) tuples

        def _add_edge(source: str, target: str, kind: DepKind):
            key = (source, target, kind)
            if key not in seen_edges:
                seen_edges.add(key)
                model.dependencies.append(DependencyEdge(source, target, kind))

        for p in model.peripherals:
            _add_edge(p.inst, "SYS_CLK", DepKind.CLOCK)
            _add_edge(p.inst, "RESET_N", DepKind.RESET)
            _add_edge(p.inst, model.cpu_type, DepKind.BUS)

            # ip_depends contains IP *type* names (e.g. "uart").
            # Issue 5 fix (review 20): map type -> instance for correct edges.
            # Both direct inst name match AND type->inst mapping.
            for dep_type in p.ip_depends:
                if dep_type in inst_names:
                    # Direct inst name match
                    _add_edge(p.inst, dep_type, DepKind.BUS)
                else:
                    # Type -> instance mapping
                    for other in model.peripherals:
                        if other.type == dep_type and other.inst != p.inst:
                            _add_edge(p.inst, other.inst, DepKind.BUS)
