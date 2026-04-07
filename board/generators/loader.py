"""
loader.py - Configuration loading, schema validation, and IP plugin discovery (v5)
===================================================================================
Changes vs v4:
  HIGH priority fixes:
  - Layout C detection: robustnejšia heuristika (všetky values musia byť non-dict)
  - Base registry provenance: _origin_yaml / _plugin_path injektovaný aj pre base registry
  - SchemaValidator: fix None bug pre soc blok pri ram_latency validácii
  - registry_utils: lookup_registry presunutý do tohto modulu (prevencia cyclic import)

  MEDIUM priority fixes:
  - os.walk namiesto glob.glob (menej memory overhead, lepšia kontrola)
  - Reserved key warning pri injekcii _origin_yaml / _plugin_path

  LOW priority fixes:
  - _info() helper wrapper pre budúci logger swap
  - UTF-8 čítanie s ASCII validáciou (pluginy môžu mať UTF-8 komentáre)
"""

from __future__ import annotations
import os
import re
import sys
import yaml
from typing import Dict, List, Optional, Tuple

from models import BusType, ConfigError


# =============================================================================
# Logging helpers  (LOW: wrappery pre budúci logger swap bez refaktoru)
# =============================================================================

_WARNINGS_AS_ERRORS: bool = False


def _info(msg: str) -> None:
    """Structured info output. Swap body for logging later."""
    print(f"[INFO] {msg}")
    sys.stdout.flush()


def _warn(msg: str) -> None:
    """
    Print a warning to stdout (NOT stderr).
    TCL exec treats any stderr output as failure -- must avoid stderr.
    If _WARNINGS_AS_ERRORS is True, raises ConfigError instead.
    """
    if _WARNINGS_AS_ERRORS:
        raise ConfigError(f"Warning promoted to error: {msg}")
    print(f"[WARN]  {msg}")
    sys.stdout.flush()


def _fail(msg: str) -> None:
    raise ConfigError(msg)


# =============================================================================
# resolve_size (unchanged from v3/v4)
# =============================================================================

def resolve_size(val) -> int:
    """
    Parse an integer from YAML.
    Handles hex strings ('0x400'), decimal strings ('1024'), and bare ints.
    """
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            return int(val, 0)
        except ValueError:
            raise ConfigError(f"Cannot parse integer from {val!r}")
    raise ConfigError(
        f"Expected int or string, got {type(val).__name__}: {val!r}")


# =============================================================================
# registry_utils: shared lookup  (MEDIUM: moved here to prevent cyclic import)
# =============================================================================

def lookup_registry(registry: dict, inst_name: str,
                    inst_cfg: dict) -> Tuple[dict, str]:
    """
    Deterministic registry lookup. Single source of truth used by both
    ConfigLoader (cross-validation) and ModelBuilder (instantiation).

    Order: explicit 'type' field -> exact match -> suffix-strip heuristic.

    Moved from builder.py to loader.py to prevent potential cyclic imports:
      builder imports loader (for resolve_size, _warn)
      loader previously imported builder (for lookup_registry)
    """
    explicit_type = inst_cfg.get("type")
    if explicit_type and explicit_type in registry:
        return registry[explicit_type], explicit_type

    if inst_name in registry:
        return registry[inst_name], inst_name

    # Issue 4 fix: strip _N or _vN suffixes
    # uart0 -> uart, uart_v2 -> uart (not uart_v)
    base = re.sub(r"(_v?\d+)$", "", inst_name)
    if base and base in registry:
        return registry[base], base

    candidates = [k for k in registry if k.startswith(inst_name[:3])]
    hint = (f"  Did you mean: {candidates[0]!r}?" if len(candidates) == 1
            else f"  Candidates: {candidates}" if candidates else "")
    raise ConfigError(
        f"Peripheral '{inst_name}' not found in registry "
        f"(tried: type={explicit_type!r}, exact={inst_name!r}, "
        f"base={base!r}).\n"
        f"  -> Add it to ip_registry.yaml or create a *.ip.yaml plugin.\n"
        f"{hint}"
    )


# =============================================================================
# PluginLoader
# =============================================================================

# Fields that are part of IP metadata (not IP names)
_IP_META_FIELDS = frozenset({
    "module", "bus_type", "address_range", "needs_bus",
    "registers", "interrupts", "interfaces", "port_map",
    "params", "files", "description", "type", "depends_on",
    "gen_regs", "clocks", "clock_domain", "no_hw_warning",
})

# Internal provenance keys injected by loader -- warn if already present in YAML
_RESERVED_KEYS = frozenset({"_origin_yaml", "_plugin_path"})


class PluginLoader:
    """
    Discovers and loads *.ip.yaml files from one or more plugin directories.

    Supported layouts:
      Layout B: top-level key 'peripherals:' wrapping multiple IP names
      Layout C: top-level keys are IP meta fields (single IP, name from filename)
      Layout A: top-level keys are IP names, values are IP meta dicts

    Detection order: B -> C -> A.
    Layout C is detected conservatively: ALL values must be non-dict
    (prevents false-positive match against Layout A).

    Metadata injected into every loaded entry:
        _origin_yaml  -- absolute path to the *.ip.yaml file
        _plugin_path  -- absolute path to the directory containing it
    """

    def __init__(self, search_dirs: List[str], project_root: str = ""):
        self.search_dirs  = search_dirs
        self.project_root = os.path.abspath(project_root or os.getcwd())
        self._loaded:  Dict[str, dict] = {}
        self._sources: Dict[str, str]  = {}

    # ------------------------------------------------------------------
    def load(self) -> Dict[str, dict]:
        """Scan, load, merge and return registry dict."""
        yaml_files = self._discover()
        if yaml_files:
            _info(f"Plugin load order ({len(yaml_files)} file(s)):")
            for fp in yaml_files:
                print(f"  {fp}")
        for fpath in yaml_files:
            self._load_file(fpath)
        if self._loaded:
            _info(f"Plugins: loaded {len(self._loaded)} IP(s) "
                  f"from {len(yaml_files)} file(s)")
        return dict(self._loaded)

    # ------------------------------------------------------------------
    def _discover(self) -> List[str]:
        """
        Return globally sorted list of *.ip.yaml absolute paths.

        MEDIUM fix: uses os.walk instead of glob.glob for lower memory
        overhead and better control in large trees.
        Global sort ensures cross-machine determinism.
        """
        found: List[str] = []
        for raw_dir in self.search_dirs:
            abs_dir = (raw_dir if os.path.isabs(raw_dir)
                       else os.path.normpath(
                           os.path.join(self.project_root, raw_dir)))
            if not os.path.isdir(abs_dir):
                _warn(f"ip_plugins dir not found, skipping: {abs_dir}")
                continue
            dir_files = []
            for root, _dirs, files in os.walk(abs_dir):
                for fname in files:
                    if fname.endswith(".ip.yaml"):
                        dir_files.append(os.path.join(root, fname))
            if not dir_files:
                _warn(f"ip_plugins dir contains no *.ip.yaml files: {abs_dir}")
            found.extend(dir_files)
        # Global sort for cross-machine determinism (not just per-dir)
        return sorted(found)

    # ------------------------------------------------------------------
    def _load_file(self, fpath: str) -> None:
        """Parse one *.ip.yaml and merge its entries into self._loaded."""
        # LOW fix: read as UTF-8, validate ASCII separately for Quartus compat
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                raw_text = f.read()
            # Warn if non-ASCII (Quartus tools may reject non-ASCII filenames/IDs)
            try:
                raw_text.encode("ascii")
            except UnicodeEncodeError:
                _warn(f"Plugin {fpath} contains non-ASCII characters "
                      f"-- Quartus requires ASCII-only identifiers")
            data = yaml.safe_load(raw_text)
        except FileNotFoundError:
            _warn(f"Plugin file disappeared during scan: {fpath}")
            return
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in plugin {fpath}: {e}")

        if not isinstance(data, dict):
            _warn(f"Plugin file is not a YAML mapping, skipping: {fpath}")
            return

        entries = self._detect_layout(data, fpath)
        if entries is None:
            return

        plugin_dir = os.path.dirname(fpath)
        for name, meta in entries.items():
            if not isinstance(meta, dict):
                _warn(f"Plugin {fpath}: entry '{name}' is not a dict, skipping")
                continue

            meta = dict(meta)

            # MEDIUM fix: warn if reserved keys already present in YAML
            existing = _RESERVED_KEYS & set(meta.keys())
            if existing:
                _warn(f"Plugin {fpath} entry '{name}': reserved key(s) "
                      f"{sorted(existing)} will be overwritten by loader")

            meta["_origin_yaml"] = fpath
            meta["_plugin_path"] = plugin_dir

            if name in self._loaded:
                prev = self._sources[name]
                _warn(f"IP '{name}' redefined by plugin {fpath} "
                      f"(previously from {prev}) -- later definition wins")

            self._loaded[name]  = meta
            self._sources[name] = fpath

    # ------------------------------------------------------------------
    def _detect_layout(self, data: dict, fpath: str) -> Optional[dict]:
        """
        Detect YAML layout and return {name: meta} entries dict, or None.

        Layout B: top-level key 'peripherals:' -> wrap
        Layout C: ALL values are non-dict AND meta fields present -> single IP
        Layout A: ALL values are dicts -> multi-IP map

        HIGH fix: Layout C detection now requires ALL values to be non-dict.
        This prevents false-positive match against Layout A when a file has
        both meta fields and nested dicts.
        """
        # Layout B
        if "peripherals" in data and isinstance(data["peripherals"], dict):
            return data["peripherals"]

        values = list(data.values())

        # Layout C: IP meta fields present at top level.
        # Known meta sub-dicts (port_map, params dict) are allowed --
        # we check if top-level keys are IP meta fields, not IP names.
        # Heuristic: if ANY key is a known meta field -> Layout C.
        # BUT: to avoid false positives on Layout A, verify that values
        # are NOT all dicts (which would be Layout A).
        has_meta      = bool(_IP_META_FIELDS & set(data.keys()))
        # Non-meta keys at top level (would be IP names in Layout A)
        non_meta_keys = set(data.keys()) - _IP_META_FIELDS
        # Layout C if: has meta fields AND no "IP name" keys with dict values
        all_non_meta_are_non_dict = all(
            not isinstance(data[k], dict) for k in non_meta_keys
        ) if non_meta_keys else True

        if has_meta and all_non_meta_are_non_dict:
            # Derive IP name from filename: strip .ip.yaml suffix
            fname_stem = os.path.basename(fpath)
            if fname_stem.endswith(".ip.yaml"):
                fname_stem = fname_stem[:-len(".ip.yaml")]
            else:
                fname_stem = fname_stem.split(".")[0]
            return {fname_stem: data}

        # Layout A: ALL values are dicts
        if values and all(isinstance(v, dict) for v in values):
            return data

        _warn(f"Cannot determine layout of plugin file, skipping: {fpath}")
        return None


# =============================================================================
# Schema Validator
# =============================================================================

class SchemaValidator:
    """Validates project_config.yaml structure before model building."""

    VALID_MODES = {"soc", "standalone"}

    def validate(self, cfg: dict, path: str) -> None:
        errors = []

        board = cfg.get("board", {})
        if not isinstance(board, dict) or not board.get("type"):
            errors.append("board.type is required (e.g. 'qmtech_ep4ce55')")

        mode = cfg.get("demo", {}).get("mode", "soc")
        if mode not in self.VALID_MODES:
            errors.append(
                f"demo.mode must be one of {self.VALID_MODES}, got {mode!r}")

        if mode != "standalone":
            soc = cfg.get("soc") or {}   # HIGH fix: handle None soc block
            if not isinstance(soc, dict):
                errors.append("soc: block is required for soc mode")
            else:
                for fname in ("ram_size", "clock_freq"):
                    val = soc.get(fname)
                    if val is None:
                        errors.append(f"soc.{fname} is required for soc mode")
                    elif not isinstance(val, (int, float)):
                        errors.append(
                            f"soc.{fname} must be a number, got: {val!r}")
                rs = soc.get("ram_size")
                if isinstance(rs, int):
                    if rs <= 0:
                        errors.append("soc.ram_size must be > 0")
                    elif rs % 4 != 0:
                        errors.append(
                            f"soc.ram_size {rs} is not a multiple of 4")
                    elif rs & (rs - 1):
                        errors.append(
                            f"soc.ram_size {rs} is not a power of 2")

            # HIGH fix: use `soc or {}` to prevent crash when soc is None
            soc_safe = soc if isinstance(soc, dict) else {}
            lat = soc_safe.get("ram_latency", "registered")
            if lat not in ("registered", "combinational"):
                errors.append(
                    f"soc.ram_latency must be 'registered' or "
                    f"'combinational', got {lat!r}")

            for addr_field in ("reset_vector", "ram_base", "ram_alias"):
                val = soc_safe.get(addr_field)
                if val is None:
                    continue
                try:
                    resolve_size(val)
                except ConfigError:
                    errors.append(
                        f"soc.{addr_field}: cannot parse {val!r} as int")

            sp = soc_safe.get("stack_percent", 25)
            if not isinstance(sp, int) or not (1 <= sp <= 90):
                errors.append(
                    f"soc.stack_percent must be int 1..90, got {sp!r}")

        for inst, pcfg in cfg.get("peripherals", {}).items():
            if not isinstance(pcfg, dict):
                errors.append(f"peripherals.{inst} must be a mapping")
                continue
            if not pcfg.get("enabled"):
                continue
            if "base" not in pcfg:
                errors.append(
                    f"peripherals.{inst}: 'base' required when enabled=true")
                continue
            base_val = pcfg["base"]
            if base_val == "auto":
                pass
            else:
                try:
                    base = resolve_size(base_val)
                except ConfigError:
                    errors.append(
                        f"peripherals.{inst}.base: cannot parse "
                        f"{base_val!r} as int (use a number or 'auto')")
                    continue
                if base < 0:
                    errors.append(f"peripherals.{inst}.base must be >= 0")

        for inst, mcfg in cfg.get("standalone_modules", {}).items():
            if not isinstance(mcfg, dict):
                errors.append(f"standalone_modules.{inst} must be a mapping")

        for raw_dir in cfg.get("paths", {}).get("ip_plugins", []):
            if not isinstance(raw_dir, str):
                errors.append(
                    f"paths.ip_plugins entry must be a string, got {raw_dir!r}")

        if errors:
            raise ConfigError(
                f"Schema validation failed for {path}:\n" +
                "".join(f"  * {e}\n" for e in errors))

        print("[OK] Schema: valid")


# =============================================================================
# Registry Validator
# =============================================================================

class RegistryValidator:
    """Validates merged registry structure (base + plugins)."""

    REQUIRED_PERIPH_FIELDS = ("module", "bus_type")
    VALID_BUS_TYPES        = {bt.value for bt in BusType}

    HW_IFACE_TYPES = {
        "serial", "gpio", "video", "sdram", "memory",
        "interface", "display", "spi", "i2c", "pwm",
        "can", "ethernet", "usb", "camera", "audio",
    }
    BUS_IFACE_TYPES = {
        "simple_bus", "axi_lite", "axi_full", "axi_stream", "wishbone",
    }

    def validate(self, registry: dict, path: str) -> None:
        errors      = []
        hw_warnings = []

        for name, meta in registry.items():
            if not isinstance(meta, dict):
                errors.append(f"registry.{name}: must be a mapping")
                continue

            if meta.get("type") == "cpu":
                if not meta.get("files"):
                    errors.append(
                        f"registry.{name} (cpu): 'files' list is required")
                continue

            if meta.get("type") in ("memory", "utility", "standalone"):
                continue

            if not meta.get("needs_bus", True):
                continue

            for req in self.REQUIRED_PERIPH_FIELDS:
                if req not in meta:
                    errors.append(
                        f"registry.{name}: missing required field '{req}'")

            bt = meta.get("bus_type")
            if bt is not None and bt not in self.VALID_BUS_TYPES:
                errors.append(
                    f"registry.{name}.bus_type={bt!r} is not valid; "
                    f"must be one of {sorted(self.VALID_BUS_TYPES)}")

            ifaces = meta.get("interfaces", [])
            for iface in ifaces:
                if not isinstance(iface, dict):
                    errors.append(
                        f"registry.{name}.interfaces: entry must be a mapping")
                    continue
                if "type" not in iface:
                    errors.append(
                        f"registry.{name}.interfaces: entry missing 'type'")
                    continue
                itype = iface["type"]
                if itype in self.HW_IFACE_TYPES:
                    sigs = iface.get("signals", [])
                    if not sigs:
                        hw_warnings.append(
                            f"registry.{name}: interface '{itype}' "
                            f"has no signals defined -- "
                            f"no HW ports will appear in soc_top")

            if not ifaces:
                hw_warnings.append(
                    f"registry.{name}: no interfaces: defined -- "
                    f"bus connection only, no HW ports in soc_top. "
                    f"If this IP has physical pins (UART, GPIO, ...) "
                    f"add an interfaces: section.")
            else:
                iface_types     = {i.get("type", "") for i in ifaces
                                   if isinstance(i, dict)}
                hw_types_present = iface_types & self.HW_IFACE_TYPES
                bus_only         = iface_types and not hw_types_present

                if bus_only:
                    HW_NAME_HINTS = {
                        "uart", "spi", "i2c", "vga", "hdmi", "eth",
                        "sdram", "ddr", "cam", "sdc", "pwm", "can",
                        "usb", "audio", "gpio", "led", "seg",
                    }
                    name_lower   = name.lower()
                    module_lower = meta.get("module", "").lower()
                    has_hw_hint  = any(
                        h in name_lower or h in module_lower
                        for h in HW_NAME_HINTS
                    )
                    # Allow opt-out via no_hw_warning: true
                    if has_hw_hint and not meta.get("no_hw_warning", False):
                        hw_warnings.append(
                            f"registry.{name}: only bus interfaces defined "
                            f"but name suggests HW pins -- "
                            f"missing interfaces: with signals:? "
                            f"[suppress with no_hw_warning: true]")

        if errors:
            raise ConfigError(
                f"Registry validation failed for {path}:\n" +
                "".join(f"  * {e}\n" for e in errors))

        for w in hw_warnings:
            _warn(w)

        hw_ok  = len(hw_warnings) == 0
        status = "all valid" if hw_ok else f"{len(hw_warnings)} HW pin warning(s)"
        print(f"[OK] Registry: {len(registry)} entries, {status}")


# =============================================================================
# Config Loader
# =============================================================================

class ConfigLoader:
    """
    Loads project_config.yaml and the merged IP registry.

    Registry resolution order (later wins on key collision):
      1. base ip_registry.yaml  (optional)
      2. *.ip.yaml files from paths.ip_plugins directories

    HIGH fix: base registry entries now get _origin_yaml / _plugin_path
    injected (same as plugin entries) for consistent error messages.
    """

    def __init__(self, project_cfg_path: str, registry_path: str = ""):
        self.project_cfg_path = os.path.abspath(project_cfg_path)
        self.registry_path    = os.path.abspath(registry_path) if registry_path else ""
        self._schema_validator   = SchemaValidator()
        self._registry_validator = RegistryValidator()
        self.raw_cfg:  dict = {}
        self.raw_reg:  dict = {}
        self.registry: dict = {}
        self._load()

    # ------------------------------------------------------------------
    def _load_yaml(self, path: str) -> dict:
        # LOW fix: read UTF-8, validate ASCII separately
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            try:
                raw_text.encode("ascii")
            except UnicodeEncodeError:
                _warn(f"{path} contains non-ASCII characters "
                      f"(Quartus requires ASCII-only identifiers)")
            data = yaml.safe_load(raw_text)
        except FileNotFoundError:
            raise ConfigError(f"File not found: {path}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {path}: {e}")
        return data or {}

    # ------------------------------------------------------------------
    def _load(self) -> None:
        self.raw_cfg = self._load_yaml(self.project_cfg_path)
        self._schema_validator.validate(self.raw_cfg, self.project_cfg_path)

        project_root = os.path.dirname(self.project_cfg_path)

        # Base registry
        base_registry: dict = {}
        if self.registry_path:
            if os.path.exists(self.registry_path):
                self.raw_reg  = self._load_yaml(self.registry_path)
                raw_entries   = self.raw_reg.get("peripherals", {})
                base_dir      = os.path.dirname(self.registry_path)
                # HIGH fix: inject provenance into base registry entries
                for name, meta in raw_entries.items():
                    if isinstance(meta, dict):
                        meta = dict(meta)
                        meta["_origin_yaml"] = self.registry_path
                        meta["_plugin_path"] = base_dir
                        raw_entries[name] = meta
                base_registry = raw_entries
                _info(f"Base registry: {len(base_registry)} IPs "
                      f"from {os.path.basename(self.registry_path)}")
            else:
                _warn(f"ip_registry.yaml not found at {self.registry_path} "
                      f"-- continuing with plugins only")
        else:
            _info("No base ip_registry.yaml specified -- using plugins only")

        # Plugin IPs
        plugin_dirs     = self.raw_cfg.get("paths", {}).get("ip_plugins", [])
        plugin_registry: dict = {}
        if plugin_dirs:
            pl = PluginLoader(plugin_dirs, project_root=project_root)
            plugin_registry = pl.load()
        else:
            _info("No ip_plugins paths configured")

        # Merge: base first, plugins override (with warning)
        self.registry = dict(base_registry)
        for name, meta in plugin_registry.items():
            if name in self.registry:
                origin = meta.get("_origin_yaml", "<plugin>")
                _warn(f"Plugin IP '{name}' (from {origin}) "
                      f"overrides base registry entry")
            self.registry[name] = meta

        reg_label = self.registry_path or "<plugins only>"
        self._registry_validator.validate(self.registry, reg_label)
        self._cross_validate()

    # ------------------------------------------------------------------
    def _cross_validate(self) -> None:
        """Cross-validate peripherals against merged registry."""
        errors = []
        for inst, pcfg in self.raw_cfg.get("peripherals", {}).items():
            if not isinstance(pcfg, dict) or not pcfg.get("enabled"):
                continue
            try:
                lookup_registry(self.registry, inst, pcfg)
            except ConfigError as e:
                errors.append(str(e))
        if errors:
            raise ConfigError(
                "Cross-validation failed (project <-> registry):\n" +
                "".join(f"  * {e}\n" for e in errors))
        print("[OK] Cross-validation: all peripheral types resolved")

    def lookup_registry(self, inst_name: str,
                        inst_cfg: dict) -> Tuple[dict, str]:
        """Delegate to module-level shared utility."""
        return lookup_registry(self.registry, inst_name, inst_cfg)
