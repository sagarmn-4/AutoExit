"""
Runtime state persistence for AutoExit bot.

Stores small runtime settings (target_points, paper_mode, paused) in a JSON
file at the project root so changes via Telegram survive restarts.

This module is intentionally simple: no locking, best-effort I/O.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .common import ROOT


RUNTIME_STATE_PATH: Path = ROOT / "runtime_state.json"


DEFAULT_STATE: Dict[str, Any] = {
    "target_points": None,   # None means: use config default
    "paper_mode": None,      # None means: use config default
    "paused": None,          # None means: default not paused
}


def load_runtime_state() -> Dict[str, Any]:
    """Load runtime state from file, returning defaults if missing/invalid."""
    try:
        if RUNTIME_STATE_PATH.exists():
            data = json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = DEFAULT_STATE.copy()
                merged.update({k: data.get(k) for k in DEFAULT_STATE.keys()})
                return merged
    except Exception:
        # Fall back to defaults if file is corrupt/unreadable
        pass
    return DEFAULT_STATE.copy()


def save_runtime_state(state: Dict[str, Any]) -> None:
    """Persist runtime state to disk (best-effort)."""
    try:
        # Only persist known keys
        payload = {k: state.get(k) for k in DEFAULT_STATE.keys()}
        RUNTIME_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Best-effort: ignore write errors
        pass


def update_runtime_state(**kwargs: Any) -> Dict[str, Any]:
    """Update specific fields atomically and save; returns the new state."""
    current = load_runtime_state()
    current.update({k: v for k, v in kwargs.items() if k in DEFAULT_STATE})
    save_runtime_state(current)
    return current
