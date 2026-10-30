"""Application paths and runtime constants."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_cache_dir, user_data_dir

from . import APP_NAME, APP_SLUG

ASSET_DIR = Path(__file__).resolve().parent / "assets"


def _override(variable: str) -> Path | None:
    value = os.environ.get(variable)
    return Path(value).expanduser() if value else None


def data_dir() -> Path:
    """Persistent state (favorites, history, settings)."""
    return _override("RADIO_ATLAS_DATA_DIR") or Path(
        user_data_dir(APP_SLUG, APP_NAME)
    )


def cache_dir() -> Path:
    """Disposable API caches."""
    return _override("RADIO_ATLAS_CACHE_DIR") or Path(
        user_cache_dir(APP_SLUG, APP_NAME)
    )


def state_path() -> Path:
    return data_dir() / "state.json"


def asset_path(name: str) -> Path:
    return ASSET_DIR / name


def api_base_override() -> str | None:
    value = os.environ.get("RADIO_ATLAS_API_URL", "").strip().rstrip("/")
    return value or None


def mpv_override() -> str | None:
    value = os.environ.get("RADIO_ATLAS_MPV", "").strip()
    return value or None
