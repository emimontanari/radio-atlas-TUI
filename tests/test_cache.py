"""Atomic JSON disk cache behavior."""

from __future__ import annotations

import json
import time

import pytest

from radio_atlas import cache as cache_module
from radio_atlas.cache import DiskCache


def test_save_and_load_roundtrip(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    payload = [{"name": "Radio Café", "votes": 3}]
    assert cache.save("world/us", payload) is True
    entry = cache.load("world/us")
    assert entry is not None
    assert entry.data == payload
    assert entry.path.name == "world_us.json"
    assert entry.age < 5
    assert entry.is_fresh(60)


def test_keys_are_sanitized_and_share_the_same_file(tmp_path):
    cache = DiskCache(tmp_path)
    cache.save("../../evil key", {"ok": True})
    files = [path.name for path in tmp_path.iterdir()]
    assert files == [".._.._evil_key.json"]
    assert cache.load("../../evil key").data == {"ok": True}


def test_missing_and_corrupt_files_load_as_none(tmp_path):
    cache = DiskCache(tmp_path)
    assert cache.load("missing") is None

    (tmp_path / "broken.json").write_text("{not json")
    assert cache.load("broken") is None

    (tmp_path / "list.json").write_text("[]")
    assert cache.load("list") is None

    (tmp_path / "no-date.json").write_text(json.dumps({"data": 1}))
    assert cache.load("no-date") is None

    (tmp_path / "bad-date.json").write_text(json.dumps({"saved_at": "soon", "data": 1}))
    assert cache.load("bad-date") is None


def test_oversized_entries_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "MAX_CACHE_BYTES", 10)
    cache = DiskCache(tmp_path)
    assert cache.save("big", {"payload": "longer than ten bytes"}) is True
    assert cache.load("big") is None


def test_freshness_uses_the_stored_timestamp(tmp_path):
    cache = DiskCache(tmp_path)
    cache.save("old", {"value": 1})
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps({"saved_at": time.time() - 120, "data": {"value": 1}})
    )
    entry = cache.load("old")
    assert entry is not None
    assert 100 < entry.age < 200
    assert entry.is_fresh(60) is False
    assert entry.is_fresh(300) is True


def test_delete_removes_the_file(tmp_path):
    cache = DiskCache(tmp_path)
    cache.save("gone", 1)
    cache.delete("gone")
    assert cache.load("gone") is None
    cache.delete("gone")  # idempotent


def test_save_failure_returns_false(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("")
    assert DiskCache(blocker).save("key", 1) is False


def test_load_ignores_unreadable_directories(tmp_path):
    cache = DiskCache(tmp_path / "does-not-exist")
    assert cache.load("key") is None


@pytest.mark.parametrize("value", [None, 0, "", {"a": [1, 2]}, "ñandú"])
def test_roundtrip_handles_json_values(tmp_path, value):
    cache = DiskCache(tmp_path)
    assert cache.save("value", value)
    entry = cache.load("value")
    assert entry is not None
    assert entry.data == value
