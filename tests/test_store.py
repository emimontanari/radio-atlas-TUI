"""Persistence behavior: atomic saves, favorites, history and recovery."""

from __future__ import annotations

import json

from radio_atlas.models import Station
from radio_atlas.store import Store


def station(uuid: str, name: str = "Jazz FM") -> Station:
    return Station(id=uuid, name=name, url=f"https://stream.example/{uuid}")


def test_missing_state_starts_empty(tmp_path):
    store = Store(tmp_path / "state.json")
    assert store.favorites == []
    assert store.history == []
    assert store.settings["volume"] == 70
    assert store.load_error == ""


def test_favorites_persist_and_keep_order(tmp_path):
    path = tmp_path / "state.json"
    store = Store(path)
    assert store.toggle_favorite(station("a", "First")) is True
    assert store.toggle_favorite(station("b", "Second")) is True
    assert store.toggle_favorite(station("a", "First")) is False
    assert [s.name for s in store.favorites] == ["Second"]

    reloaded = Store(path)
    assert [s.name for s in reloaded.favorites] == ["Second"]
    assert reloaded.is_favorite("b")
    assert not reloaded.is_favorite("a")
    assert reloaded.favorite_ids == {"b"}


def test_history_dedupes_and_moves_to_front(tmp_path):
    store = Store(tmp_path / "state.json", max_history=3, clock=lambda: 1000.0)
    for uuid in ("a", "b", "c"):
        store.record_play(station(uuid))
    store.record_play(station("a"))
    assert [entry.station.id for entry in store.history] == ["a", "c", "b"]
    assert store.recent_ids(2) == {"a", "c"}

    store.record_play(station("d"))
    assert [entry.station.id for entry in store.history] == ["d", "a", "c"]

    store.clear_history()
    assert store.history == []


def test_settings_are_validated(tmp_path):
    store = Store(tmp_path / "state.json")
    store.set("volume", 140)
    store.set("muted", 1)
    store.set("unknown", "ignored")
    assert store.settings["volume"] == 100
    assert store.settings["muted"] is True
    assert "unknown" not in store.settings

    reloaded = Store(tmp_path / "state.json")
    assert reloaded.settings["volume"] == 100
    assert reloaded.settings["muted"] is True


def test_corrupt_state_is_quarantined(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    store = Store(path, clock=lambda: 1234)
    assert store.favorites == []
    assert store.load_error
    assert not path.exists()
    backup = tmp_path / "state.json.corrupt-1234"
    assert backup.read_text(encoding="utf-8") == "{not json"
    assert store.save() is True


def test_invalid_records_are_skipped(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "favorites": [
                    {"stationuuid": "ok", "name": "Ok", "url_resolved": "https://x.test/a"},
                    {"stationuuid": "bad", "name": "No URL"},
                    "nonsense",
                ],
                "history": [
                    {
                        "station": {
                            "stationuuid": "h1",
                            "name": "History",
                            "url_resolved": "https://x.test/h",
                        },
                        "played_at": 50,
                    },
                    {"station": {"stationuuid": "h2"}, "played_at": 50},
                    {"station": {"stationuuid": "h3", "url_resolved": "https://x.test/h3"}},
                ],
                "settings": {"volume": "loud"},
            }
        ),
        encoding="utf-8",
    )
    store = Store(path)
    assert [s.id for s in store.favorites] == ["ok"]
    assert [entry.station.id for entry in store.history] == ["h1"]
    assert store.settings["volume"] == 70


def test_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "state.json"
    store = Store(path)
    store.add_favorite(station("a"))
    assert store.save() is True
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".state-")]
    assert leftovers == []
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
