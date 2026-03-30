"""
loader.py - Configuration loading and schema validation  (v3)
==============================================================
No structural changes vs v2.  Version bump to stay in sync with
models.py / builder.py v3.

Key behaviours (from v2):
  - resolve_size() uses int(val, 0) -- handles 0x hex and decimal correctly
  - _fail() raises ConfigError (no sys.exit in library code)
  - SchemaValidator: validates project_config.yaml structure
  - RegistryValidator: validates ip_registry.yaml (module, bus_type, interfaces)
  - cross-validation: every enabled peripheral type must exist in registry
  - lookup_registry: explicit 'type' field -> exact match -> suffix-strip heuristic
"""

from __future__ import annotations
import os
import re
import sys
import yaml
from typing import Tuple

from models import BusType, ConfigError


# =============================================================================
# Helpers
# =============================================================================

# Global flag: set to True by --warnings-as-errors CLI option
_WARNINGS_AS_ERRORS: bool = False


def resolve_size(val) -> int:
    """
    Parse an integer from YAML.
    Handles hex strings ('0x400'), decimal strings ('1024'), and bare ints.
    Uses int(s, 0) so Python handles the prefix automatically.

    v1 bug fixed: int('16', 16) == 22.  Now: int('16', 0) == 16.
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


def _fail(msg: str) -> None:
    raise ConfigError(msg)


def _warn(msg: str) -> None:
    """
    Print a warning to stdout (NOT stderr).
    TCL exec treats any stderr output as failure, so we must avoid stderr.
    If _WARNINGS_AS_ERRORS is True, raises ConfigError instead.
    """
    if _WARNINGS_AS_ERRORS:
        raise ConfigError(f"Warning promoted to error: {msg}")
    print(f"[WARN]  {msg}")
    sys.stdout.flush()


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
            soc = cfg.get("soc", {})
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

            # ram_latency
            lat = soc.get("ram_latency", "registered")
            if lat not in ("registered", "combinational"):
                errors.append(
                    f"soc.ram_latency must be 'registered' or "
                    f"'combinational', got {lat!r}")

            # reset_vector / ram_base / ram_alias -- must be parseable ints
            for addr_field in ("reset_vector", "ram_base", "ram_alias"):
                val = soc.get(addr_field)
                if val is None:
                    continue
                try:
                    resolve_size(val)
                except ConfigError:
                    errors.append(
                        f"soc.{addr_field}: cannot parse {val!r} as int")

            # stack_percent
            sp = soc.get("stack_percent", 25)
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
            try:
                base = resolve_size(pcfg["base"])
            except ConfigError:
                errors.append(
                    f"peripherals.{inst}.base: cannot parse {pcfg['base']!r} as int")
                continue
            if base < 0:
                errors.append(f"peripherals.{inst}.base must be >= 0")

        for inst, mcfg in cfg.get("standalone_modules", {}).items():
            if not isinstance(mcfg, dict):
                errors.append(f"standalone_modules.{inst} must be a mapping")

        if errors:
            raise ConfigError(
                f"Schema validation failed for {path}:\n" +
                "".join(f"  * {e}\n" for e in errors))

        print("[OK] Schema: valid")


# =============================================================================
# Registry Validator
# =============================================================================

class RegistryValidator:
    """Validates ip_registry.yaml structure."""

    REQUIRED_PERIPH_FIELDS = ("module", "bus_type")
    VALID_BUS_TYPES        = {bt.value for bt in BusType}

    def validate(self, registry: dict, path: str) -> None:
        errors = []

        for name, meta in registry.items():
            if not isinstance(meta, dict):
                errors.append(f"registry.{name}: must be a mapping")
                continue

            if meta.get("type") == "cpu":
                if not meta.get("files"):
                    errors.append(
                        f"registry.{name} (cpu): 'files' list is required")
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

            for iface in meta.get("interfaces", []):
                if not isinstance(iface, dict):
                    errors.append(
                        f"registry.{name}.interfaces: entry must be a mapping")
                    continue
                if "type" not in iface:
                    errors.append(
                        f"registry.{name}.interfaces: entry missing 'type'")

        if errors:
            raise ConfigError(
                f"Registry validation failed for {path}:\n" +
                "".join(f"  * {e}\n" for e in errors))

        print(f"[OK] Registry: {len(registry)} entries, all valid")


# =============================================================================
# Config Loader
# =============================================================================

class ConfigLoader:

    def __init__(self, project_cfg_path: str, registry_path: str):
        self.project_cfg_path = os.path.abspath(project_cfg_path)
        self.registry_path    = os.path.abspath(registry_path)
        self._schema_validator   = SchemaValidator()
        self._registry_validator = RegistryValidator()
        self.raw_cfg: dict = {}
        self.raw_reg: dict = {}
        self._load()

    def _load_yaml(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="ascii") as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            raise ConfigError(f"File not found: {path}")
        except UnicodeDecodeError as e:
            raise ConfigError(
                f"Non-ASCII characters in {path} "
                f"(Quartus requires ASCII-only files): {e}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {path}: {e}")
        return data or {}

    def _load(self) -> None:
        self.raw_cfg = self._load_yaml(self.project_cfg_path)
        self.raw_reg = self._load_yaml(self.registry_path)
        self._schema_validator.validate(self.raw_cfg, self.project_cfg_path)
        self.registry = self.raw_reg.get("peripherals", {})
        self._registry_validator.validate(self.registry, self.registry_path)
        self._cross_validate()

    def _cross_validate(self) -> None:
        errors = []
        for inst, pcfg in self.raw_cfg.get("peripherals", {}).items():
            if not isinstance(pcfg, dict) or not pcfg.get("enabled"):
                continue
            try:
                self.lookup_registry(inst, pcfg)
            except ConfigError as e:
                errors.append(str(e))
        if errors:
            raise ConfigError(
                "Cross-validation failed (project <-> registry):\n" +
                "".join(f"  * {e}\n" for e in errors))
        print("[OK] Cross-validation: all peripheral types resolved")

    def lookup_registry(self, inst_name: str, inst_cfg: dict) -> Tuple[dict, str]:
        """
        Deterministic registry lookup.
        Order: explicit 'type' field -> exact match -> suffix-strip heuristic.
        """
        reg = self.registry

        explicit_type = inst_cfg.get("type")
        if explicit_type and explicit_type in reg:
            return reg[explicit_type], explicit_type

        if inst_name in reg:
            return reg[inst_name], inst_name

        base = re.sub(r"_?\d+$", "", inst_name)
        if base and base in reg:
            return reg[base], base

        candidates = [k for k in reg if k.startswith(inst_name[:3])]
        hint = (f"  Did you mean: {candidates[0]!r}?" if len(candidates) == 1
                else f"  Candidates: {candidates}" if candidates else "")
        raise ConfigError(
            f"Peripheral '{inst_name}' not found in ip_registry.yaml "
            f"(tried: type={explicit_type!r}, exact={inst_name!r}, "
            f"base={base!r}).\n"
            f"  -> Add it to ip_registry.yaml or set 'type:' in "
            f"project_config.yaml.\n{hint}"
        )
