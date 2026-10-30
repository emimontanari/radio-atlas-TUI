"""Persistent favorites, history and settings with corrupt-file recovery."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from radio_atlas.models import HistoryEntry, Station, station_from_api


def _record(station: Station) -> dict[str, Any]:
    return station.to_record()


def _station(record: Any) -> Station | None:
    return station_from_api(record) if isinstance(record, dict) else None


class Store:
    def __init__(
        self,
        path: Path | None = None,
        *,
        max_history: int = 50,
        clock=time.time,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.max_history = max(1, max_history)
        self.clock = clock
        self.favorites: list[Station] = []
        self.history: list[HistoryEntry] = []
        self.settings: dict[str, Any] = {
            "volume": 70,
            "muted": False,
            "ascii_globe": False,
        }
        self.load_error = ""
        if self.path is not None:
            self.load()

    # -- persistence -------------------------------------------------------

    def load(self) -> None:
        if self.path is None:
            return
        try:
            if self.path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("state file is too large")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            self.load_error = str(error)
            self._quarantine()
            return
        if not isinstance(payload, dict):
            self.load_error = "state root is not an object"
            self._quarantine()
            return

        favorites: list[Station] = []
        seen: set[str] = set()
        for item in payload.get("favorites") or []:
            station = _station(item)
            if station is None or station.id in seen:
                continue
            seen.add(station.id)
            favorites.append(station)
        self.favorites = favorites

        history: list[HistoryEntry] = []
        seen.clear()
        for item in payload.get("history") or []:
            if not isinstance(item, dict):
                continue
            station = _station(item.get("station"))
            played_at = item.get("played_at")
            if station is None or station.id in seen:
                continue
            if not isinstance(played_at, (int, float)) or played_at <= 0:
                continue
            seen.add(station.id)
            history.append(HistoryEntry(station, float(played_at)))
        self.history = history[: self.max_history]

        settings = payload.get("settings")
        if isinstance(settings, dict):
            self.settings.update(
                {
                    key: value
                    for key, value in settings.items()
                    if key in self.settings
                }
            )
            self._validate_settings()

    def save(self) -> bool:
        if self.path is None:
            return False
        payload = {
            "version": 1,
            "favorites": [_record(station) for station in self.favorites],
            "history": [entry.to_record() for entry in self.history],
            "settings": self.settings,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".state-",
                suffix=".tmp",
                delete=False,
            )
            temporary = Path(handle.name)
            try:
                with handle:
                    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def _quarantine(self) -> None:
        if self.path is None:
            return
        try:
            stamp = int(self.clock())
            target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
            os.replace(self.path, target)
        except OSError:
            pass

    def _validate_settings(self) -> None:
        volume = self.settings.get("volume")
        try:
            volume = int(volume)
        except (TypeError, ValueError):
            volume = 70
        self.settings["volume"] = max(0, min(100, volume))
        self.settings["muted"] = bool(self.settings.get("muted", False))
        self.settings["ascii_globe"] = bool(self.settings.get("ascii_globe", False))

    # -- favorites ---------------------------------------------------------

    def is_favorite(self, station_id: str) -> bool:
        return any(station.id == station_id for station in self.favorites)

    @property
    def favorite_ids(self) -> set[str]:
        return {station.id for station in self.favorites}

    def toggle_favorite(self, station: Station) -> bool:
        if self.is_favorite(station.id):
            self.remove_favorite(station.id)
            return False
        self.add_favorite(station)
        return True

    def add_favorite(self, station: Station) -> bool:
        if self.is_favorite(station.id):
            return False
        self.favorites.insert(0, station)
        self.save()
        return True

    def remove_favorite(self, station_id: str) -> bool:
        before = len(self.favorites)
        self.favorites = [s for s in self.favorites if s.id != station_id]
        changed = len(self.favorites) != before
        if changed:
            self.save()
        return changed

    # -- history -----------------------------------------------------------

    def record_play(self, station: Station) -> None:
        self.history = [entry for entry in self.history if entry.station.id != station.id]
        self.history.insert(0, HistoryEntry(station, float(self.clock())))
        del self.history[self.max_history :]
        self.save()

    def clear_history(self) -> None:
        if not self.history:
            return
        self.history = []
        self.save()

    def recent_ids(self, limit: int = 20) -> set[str]:
        return {entry.station.id for entry in self.history[:limit]}

    # -- settings ----------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in self.settings:
            return
        self.settings[key] = value
        self._validate_settings()
        self.save()
