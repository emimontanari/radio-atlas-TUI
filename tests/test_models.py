"""Domain models and defensive normalization."""

from __future__ import annotations

from radio_atlas.models import (
    Station,
    clean_text,
    format_count,
    normalize_stations,
    parse_track,
    relative_time,
    station_from_api,
)


def test_clean_text_strips_invisible_characters_and_collapses_spaces():
    assert clean_text("  A\u200bB\u0000\tC  ") == "ABC"
    assert clean_text("A   B\n C") == "A B C"
    assert clean_text(None) == ""
    assert clean_text("abcdef", 3) == "abc"
    assert clean_text("\u202eRTL\ufeff") == "RTL"


def test_station_from_api_normalizes_fields_and_builds_stable_id():
    record = {
        "name": "  Jazz   FM ",
        "url_resolved": "http://stream.example/jazz",
        "country": " United   States ",
        "countrycode": "us",
        "state": "New York",
        "tags": "jazz, smooth",
        "codec": "MP3",
        "bitrate": "128",
        "votes": "10",
        "geo_lat": "40.7",
        "geo_long": "-74.0",
        "estimated_location": False,
    }
    station = station_from_api(record)
    assert station is not None
    assert station.name == "Jazz FM"
    assert station.country_code == "US"
    assert station.bitrate == 128
    assert station.latitude == 40.7
    assert station.id.startswith("local-")
    assert station.id == station_from_api(dict(record)).id
    assert station_from_api({**record, "url_resolved": "http://other.example"}).id != station.id


def test_station_from_api_falls_back_to_url_and_unknown_name():
    station = station_from_api({"url": "https://stream.example/a", "name": "  "})
    assert station is not None
    assert station.name == "Unknown station"
    assert station.url == "https://stream.example/a"


def test_station_from_api_rejects_records_without_http_url():
    assert station_from_api({"name": "A", "url": "javascript:alert(1)"}) is None
    assert station_from_api({"name": "A"}) is None
    assert station_from_api("not a mapping") is None
    assert station_from_api({"url": "ftp://example.com/a"}) is None


def test_station_from_api_drops_invalid_or_partial_coordinates():
    assert station_from_api({"url": "http://a", "geo_lat": 100, "geo_long": 0}).latitude is None
    assert station_from_api({"url": "http://a", "geo_lat": 0, "geo_long": 300}).longitude is None
    assert station_from_api({"url": "http://a", "geo_lat": 10}).longitude is None
    assert station_from_api({"url": "http://a", "geo_lat": "nan", "geo_long": 1}).latitude is None
    assert station_from_api({"url": "http://a", "geo_lat": 10, "geo_long": 20}).has_location


def test_station_derived_labels():
    station = Station(
        id="x",
        name="Radio",
        url="http://a",
        country="France",
        country_code="FR",
        state="Paris",
        tags="jazz, , soul",
        codec="AAC",
        bitrate=192,
        latitude=48.8,
        longitude=2.3,
    )
    assert station.place == "Paris"
    assert station.country_label == "France"
    assert station.meta == "France · Paris · AAC · 192 kbps"
    assert station.tagline == "jazz · soul"
    assert "paris" in station.search_text
    assert station.has_location
    assert Station(id="y", name="N", url="u").place == ""


def test_normalize_stations_deduplicates_and_respects_limit():
    records = [
        {"stationuuid": "a", "url": "http://a"},
        {"stationuuid": "a", "url": "http://duplicate"},
        {"stationuuid": "b", "url": "http://b"},
        {"stationuuid": "c", "url": "javascript:no"},
        {"stationuuid": "d", "url": "http://d"},
    ]
    stations = normalize_stations(records, limit=2)
    assert [station.id for station in stations] == ["a", "b"]


def test_parse_track_splits_artist_and_title():
    assert parse_track("Daft Punk - Around the World") == (
        "Daft Punk",
        "Around the World",
    )
    assert parse_track("Miles Davis – So What") == ("Miles Davis", "So What")
    assert parse_track("Just a title") == ("", "Just a title")
    assert parse_track("  - Hello") == ("", "Hello")


def test_parse_track_strips_only_a_real_station_prefix():
    assert parse_track("Jazz FM · Miles Davis - So What", "Jazz FM") == (
        "Miles Davis",
        "So What",
    )
    assert parse_track("Jazz FM", "Jazz FM") == ("", "")
    assert parse_track("Rockwell - Somebody's Watching Me", "Rock") == (
        "Rockwell",
        "Somebody's Watching Me",
    )


def test_relative_time_buckets():
    now = 1_000_000.0
    assert relative_time(now, now) == "now"
    assert relative_time(now - 59, now) == "now"
    assert relative_time(now - 60, now) == "1m"
    assert relative_time(now - 3_600, now) == "1h"
    assert relative_time(now - 86_400, now) == "1d"
    assert relative_time(now - 86_400 * 60, now) == "2mo"
    assert relative_time(now + 500, now) == "now"
    assert relative_time(0, 120) == "2m"


def test_format_count_uses_thousands_separators():
    assert format_count(1_234_567) == "1,234,567"
    assert format_count(9) == "9"
