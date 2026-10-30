"""Small atomic JSON disk cache for directory responses."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SAFE_KEY = re.compile(r"[^A-Za-z0-9_.-]+")
MAX_CACHE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CacheEntry:
    saved_at: float
    data: Any
    path: Path

    @property
    def age(self) -> float:
        return max(0.0, time.time() - self.saved_at)

    def is_fresh(self, ttl: float) -> bool:
        return self.age <= ttl


class DiskCache:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _path(self, key: str) -> Path:
        safe = _SAFE_KEY.sub("_", key)[:80] or "cache"
        return self.directory / f"{safe}.json"

    def load(self, key: str) -> CacheEntry | None:
        path = self._path(key)
        try:
            if path.stat().st_size > MAX_CACHE_BYTES:
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        saved_at = payload.get("saved_at")
        if not isinstance(saved_at, (int, float)):
            return None
        return CacheEntry(float(saved_at), payload.get("data"), path)

    def save(self, key: str, data: Any) -> bool:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".tmp-",
                suffix=".json",
                delete=False,
            )
            temporary = Path(handle.name)
            try:
                with handle:
                    json.dump(
                        {"saved_at": time.time(), "data": data},
                        handle,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            pass
