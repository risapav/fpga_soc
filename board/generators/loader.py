"""
loader.py - Configuration loading and schema validation.
Reads YAML files, enforces ASCII, validates structure.
"""

from __future__ import annotations
import os, re, sys, yaml
from typing import Tuple, Dict, Any

from models import (
    SoCModel, SoCMode, Peripheral, StandaloneModule,
    ExtPort, IrqLine, RegField, PortDir, RegAccess
)


def _fail(msg: str) -> None:
    print(f"[ERROR] {msg}")
    sys.exit(1)


def _warn(msg: str) -> None:
    print(f"[WARN]  {msg}")


def resolve_size(val) -> int:
    return int(val, 16) if isinstance(val, str) else int(val)


# =============================================================================
# Schema Validator
# =============================================================================

class SchemaValidator:
    """Validates project_config.yaml structure before model building."""

    def validate(self, cfg: dict, path: str) -> None:
        errors = []

        board = cfg.get("board", {})
        if not isinstance(board, dict) or not board.get("type"):
            errors.append("board.type is required (e.g. 'qmtech_ep4ce55')")

        mode = cfg.get("demo", {}).get("mode", "soc")
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
                        errors.append(f"soc.{fname} must be a number, got: {val!r}")

        for inst, pcfg in cfg.get("peripherals", {}).items():
            if not isinstance(pcfg, dict):
                errors.append(f"peripherals.{inst} must be a dict")
                continue
            if pcfg.get("enabled") and "base" not in pcfg:
                errors.append(f"peripherals.{inst}: 'base' required when enabled=true")

        for inst, mcfg in cfg.get("standalone_modules", {}).items():
            if not isinstance(mcfg, dict):
                errors.append(f"standalone_modules.{inst} must be a dict")

        if errors:
            print(f"[ERROR] Schema validation failed for {path}:")
            for e in errors:
                print(f"        - {e}")
            sys.exit(1)

        print("[OK] Schema: valid")


# =============================================================================
# Config Loader
# =============================================================================

class ConfigLoader:
    """Loads and parses YAML configuration files."""

    def __init__(self, project_cfg_path: str, registry_path: str):
        self.project_cfg_path = os.path.abspath(project_cfg_path)
        self.registry_path    = os.path.abspath(registry_path)
        self._validator = SchemaValidator()
        self.raw_cfg: dict = {}
        self.raw_reg: dict = {}
        self._load()

    def _load(self) -> None:
        for path, attr in [
            (self.project_cfg_path, 'raw_cfg'),
            (self.registry_path,    'raw_reg'),
        ]:
            try:
                with open(path, 'r', encoding='ascii') as f:
                    data = yaml.safe_load(f)
            except FileNotFoundError:
                _fail(f"File not found: {path}")
            except UnicodeDecodeError as e:
                _fail(f"Non-ASCII in {path} (Quartus requires ASCII): {e}")
            except yaml.YAMLError as e:
                _fail(f"Invalid YAML in {path}: {e}")
            setattr(self, attr, data or {})

        self._validator.validate(self.raw_cfg, self.project_cfg_path)
        self.registry = self.raw_reg.get('peripherals', {})

    def lookup_registry(self, inst_name: str, inst_cfg: dict) -> Tuple[dict, str]:
        """
        Find registry entry for a peripheral instance.
        Resolution: exact match -> strip suffix -> use 'type' field.
        """
        reg = self.registry
        if inst_name in reg:
            return reg[inst_name], inst_name

        base  = re.sub(r'_?\d+$', '', inst_name)
        tname = inst_cfg.get('type', base)
        for candidate in (base, tname):
            if candidate in reg:
                return reg[candidate], candidate

        candidates = [k for k in reg if k.startswith(base[:3])]
        hint = f" Did you mean: {candidates[0]!r}?" if candidates else ""
        _fail(
            f"Peripheral '{inst_name}' not found in ip_registry.yaml "
            f"(tried: {inst_name!r}, {base!r}, {tname!r}).{hint}\n"
            f"  -> Add it to ip_registry.yaml or fix name in project_config.yaml."
        )
