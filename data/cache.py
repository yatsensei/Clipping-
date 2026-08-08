"""FastF1 cache setup. Sessions are 50-100 MB, so caching is mandatory, not optional."""

from __future__ import annotations

import logging
from pathlib import Path

import fastf1

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache"
PROCESSED_DIR = ROOT / "data" / "processed"

_enabled = False


def enable(quiet: bool = True) -> Path:
    """Enable the on-disk FastF1 cache. Idempotent."""
    global _enabled
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if not _enabled:
        fastf1.Cache.enable_cache(str(CACHE_DIR))
        _enabled = True
    if quiet:
        fastf1.set_log_level(logging.ERROR)
    return CACHE_DIR
