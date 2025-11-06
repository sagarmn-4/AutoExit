"""
Shared utilities and constants used across the project.
- Provides project paths (ROOT, LOG_DIR, CONFIG_PATH, ENV_PATH)
- Lightweight env loader wrapper
- Reusable logger setup helper

This module is intentionally minimal and dependency-free so it can be
imported safely from many places in the codebase.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import os

# Project root (one level above the utils package)
ROOT: Path = Path(__file__).resolve().parent.parent
LOG_DIR: Path = ROOT / "logs"
CONFIG_PATH: Path = ROOT / "config.json"
ENV_PATH: Path = ROOT / ".env"

# Ensure log directory exists when requested
def ensure_log_dir() -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Best-effort; don't fail imports because of logging directory
        pass


def setup_logger(name: str, logfile: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Create or return a configured logger.

    - Adds a StreamHandler and optional FileHandler writing to `logs/`.
    - Safe to call multiple times; avoids duplicate handlers.
    """
    ensure_log_dir()

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding duplicate handlers during repeated calls
    if not logger.handlers:
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S")

        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)

        if logfile:
            try:
                fh = logging.FileHandler(LOG_DIR / logfile, encoding="utf-8")
                fh.setFormatter(fmt)
                logger.addHandler(fh)
            except Exception:
                # If file handler cannot be created, don't break execution
                pass

    return logger


def load_env(dotenv_path: Optional[Path] = None) -> None:
    """Load environment variables from .env file if present.

    This wraps python-dotenv's load_dotenv and uses the repo `.env` by default.
    """
    path = dotenv_path or ENV_PATH
    if path and Path(path).exists():
        load_dotenv(dotenv_path=str(path))


def mask_secret(value: Optional[str], visible: int = 4) -> Optional[str]:
    """Return a masked representation of a secret for safe logging.

    Example: mask_secret("abcdefghijkl", 3) -> "abc...jkl"
    """
    if not value:
        return None
    val = str(value)
    if len(val) <= visible * 2:
        return "..."
    return f"{val[:visible]}...{val[-visible:]}"
