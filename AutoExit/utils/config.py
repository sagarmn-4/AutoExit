"""
Configuration helper module.
- Loads `config.json` from the repo root and exposes helpers to get sections
  and environment-based credentials.
- Loads the `.env` file via `utils.common.load_env()` on import so callers
  can read environment variables safely.

Keep this module focused: do not perform side-effects other than loading env
and reading `config.json` so imports remain cheap.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
from typing import Any, Dict, Optional

from .common import CONFIG_PATH, ENV_PATH, load_env

# Ensure environment variables from .env are loaded at import time
load_env(ENV_PATH)


def _read_config(path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(f"config.json not found at {p}")

    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


# Top-level config dict (read once)
try:
    CONFIG: Dict[str, Any] = _read_config()
except Exception:
    # Defer raising until callers explicitly request config if file is missing
    CONFIG = {}


def get_config() -> Dict[str, Any]:
    """Return the loaded configuration dict. Raises if empty."""
    if not CONFIG:
        raise FileNotFoundError("config.json not loaded; missing or invalid file")
    return CONFIG


def get_section(section: str) -> Dict[str, Any]:
    """Return a named section from `config.json` (e.g. 'SELL', 'SYSTEM')."""
    cfg = get_config()
    if section not in cfg:
        raise KeyError(f"Section '{section}' not found in config.json")
    return cfg[section]


def get_kite_credentials() -> Dict[str, Optional[str]]:
    """Return Kite-related credentials read from environment variables.

    Keys returned: KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN
    """
    return {
        "KITE_API_KEY": os.getenv("KITE_API_KEY"),
        "KITE_API_SECRET": os.getenv("KITE_API_SECRET"),
        "KITE_ACCESS_TOKEN": os.getenv("KITE_ACCESS_TOKEN"),
    }


def get_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)


__all__ = [
    "CONFIG",
    "get_config",
    "get_section",
    "get_kite_credentials",
    "get_env_var",
]
