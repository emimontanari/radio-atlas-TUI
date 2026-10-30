"""Radio Browser client behavior: failover, cache, seed fallback, search."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from radio_atlas.api import RadioBrowserClient, rank_stations
from radio_atlas.cache import DiskCache
from radio_atlas.models import Station, station_from_api


def record(
    uuid: str,
    name: str,
    *,
    country: str = "United States",
    code: str = "US",
    state: str = "New York",
    tags: str = "jazz",
    votes: int = 10,
    clicks: int = 100,
    lat: float | None = 40.7,
    lon: float | None = -74.0,
) -> dict:
    return {
        "stationuuid": uuid,
        "name": name,
        "url_resolved": f"https://stream.example/{uuid}",
        "country": country,
        "countrycode": code,
        "state": state,
        "tags": tags,
        "codec": "MP3",
        "bitrate": 128,
        "votes": votes,
        "clickcount": clicks,
        "geo_lat": lat,
        "geo_long": lon,
    }


def station(uuid: str, name: str, **kwargs) -> Station:
    parsed = station_from_api(record(uuid, name, **kwargs))
    assert parsed is not None
    return parsed


def make_client(tmp_path, handler, **kwargs) -> RadioBrowserClient:
    return RadioBrowserClient(
        cache=DiskCache(tmp_path / "cache"),
        mirrors=["https://a.test", "https://b.test"],
        transport=httpx.MockTransport(handler),
        timeout=0.5,
        **kwargs,
    )


async def test_world_fails_over_to_second_mirror(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "a.test":
            return httpx.Response(503, text="no available server")
        return httpx.Response(200, json=[record("u1", "Jazz FM")])

    client = make_client(tmp_path, handler)
    result = await client.world()
    await client.close()

    assert [s.name for s in result.stations] == ["Jazz FM"]
    assert result.source == "network"
    assert result.offline is False
    assert result.error == ""
    assert calls[0] == "a.test"

    # The healthy mirror is reused instead of retrying the broken one.
    def only_b(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "b.test"
        return httpx.Response(200, json=[record("u2", "Talk Radio")])

    client = make_client(tmp_path, only_b)
    client._base = "https://b.test"
    countries = await client.by_country("US")
    await client.close()
    assert [s.name for s in countries.stations] == ["Talk Radio"]


async def test_world_uses_cache_when_network_fails(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    cache.save("world", [record("u1", "Cached Jazz")])

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    client = RadioBrowserClient(
        cache=cache,
        mirrors=["https://a.test"],
        transport=httpx.MockTransport(handler),
        timeout=0.5,
    )
    result = await client.world()
    await client.close()

    assert [s.name for s in result.stations] == ["Cached Jazz"]
    assert result.source == "cache"
    assert result.offline is True
    assert "1 mirror" in result.error


async def test_world_falls_back_to_bundled_seed(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="no available server")

    client = make_client(tmp_path, handler)
    result = await client.world()
    await client.close()

    assert result.source == "seed"
    assert result.offline is True
    assert len(result.stations) >= 20
    assert all(s.url.startswith("http") for s in result.stations)
    names = [s.name for s in result.stations]
    assert "SomaFM Groove Salad" in names


async def test_by_country_uses_seed_when_offline(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="no available server")

    client = make_client(tmp_path, handler)
    result = await client.by_country("us")
    await client.close()

    assert result.source == "seed"
    assert result.stations
    assert all(s.country_code == "US" for s in result.stations)


async def test_search_merges_name_tag_and_country_results(tmp_path):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        for key in ("name", "tag", "country"):
            if key in params:
                seen[key] = params[key]
                return httpx.Response(200, json=[record(f"{key}-1", f"{key} hit")])
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    result = await client.search("jazz")
    await client.close()

    assert set(seen) == {"name", "tag", "country"}
    assert {s.id for s in result.stations} == {"name-1", "tag-1", "country-1"}
    assert result.source == "network"


async def test_search_ranks_relevant_stations_first():
    stations = [
        station("u1", "Late Night Jazz", votes=5000),
        station("u2", "Jazz FM", votes=10),
        station("u3", "Rock", tags="jazz", votes=9000),
    ]
    ranked = rank_stations(stations, "jazz")
    assert [s.name for s in ranked] == ["Jazz FM", "Late Night Jazz", "Rock"]


async def test_search_falls_back_to_seed_when_offline(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="no available server")

    client = make_client(tmp_path, handler)
    result = await client.search("soma")
    await client.close()

    assert result.source == "seed"
    assert result.stations
    assert all("soma" in s.search_text for s in result.stations)


async def test_countries_parses_iso_codes_and_counts(tmp_path):
    payload = [
        {"name": "United States", "iso_3166_1": "US", "stationcount": 1234},
        {"name": "Argentina", "iso_3166_1": "AR", "stationcount": 99},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/json/countries"
        return httpx.Response(200, json=payload)

    client = make_client(tmp_path, handler)
    result = await client.countries()
    await client.close()

    by_code = {country.code: country for country in result.countries}
    assert by_code["US"].station_count == 1234
    assert by_code["US"].name == "United States"
    assert by_code["AR"].latitude is not None
    assert result.source == "network"


async def test_countries_fall_back_to_seed(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    client = make_client(tmp_path, handler)
    result = await client.countries()
    await client.close()

    by_code = {country.code: country for country in result.countries}
    assert result.source == "seed"
    assert by_code["US"].station_count > 0
    assert by_code["FR"].station_count > 0
    assert by_code["FR"].name == "France"


async def test_user_agent_and_click_registration(tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.startswith("/json/url/"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json=[record("u1", "Jazz FM")])

    client = make_client(tmp_path, handler)
    await client.world()
    await client.register_click("u1")
    await client.close()

    assert requests[0].headers["user-agent"].startswith("radio-atlas-tui/")
    click = requests[-1]
    assert click.method == "GET"
    assert click.url.path == "/json/url/u1"


async def test_click_failures_are_silent(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = make_client(tmp_path, handler)
    await client.register_click("u1")  # must not raise
    await client.close()


async def test_random_station_avoids_excluded_ids(tmp_path):
    records = [record(f"u{i}", f"Station {i}") for i in range(10)]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/json/stations/search"
        assert request.url.params.get("order") == "random"
        return httpx.Response(200, json=records)

    client = make_client(tmp_path, handler)
    excluded = {f"u{i}" for i in range(9)}
    picked = await client.random_station(excluded_ids=excluded)
    await client.close()

    assert picked is not None
    assert picked.id == "u9"


async def test_random_station_falls_back_to_seed(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="no available server")

    client = make_client(tmp_path, handler)
    picked = await client.random_station(excluded_ids=set())
    await client.close()

    assert picked is not None
    assert picked.url.startswith("http")


async def test_offline_cooldown_skips_repeated_network_attempts(tmp_path):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("unreachable", request=request)

    client = make_client(tmp_path, handler)
    await client.world()
    first = calls
    await client.world()
    second = calls
    await client.close()

    assert first == 2
    assert second == first
    assert client.offline is True


async def test_env_style_base_override_is_used(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, json=[record("u1", "Local")])

    client = RadioBrowserClient(
        cache=DiskCache(tmp_path / "cache"),
        base_url="https://mirror.local",
        transport=httpx.MockTransport(handler),
        timeout=0.5,
    )
    result = await client.world()
    await client.close()

    assert seen == ["mirror.local"]
    assert result.source == "network"


def test_seed_cache_key_is_stable(tmp_path):
    client = RadioBrowserClient(
        cache=DiskCache(tmp_path / "cache"),
        mirrors=["https://a.test"],
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
    )
    assert client.cache_key("world") == "world"
    assert client.cache_key("country", "US") == "country-US"
    assert client.cache_key("countries") == "countries"


async def test_reset_offline_allows_an_immediate_retry(tmp_path):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise httpx.ConnectError("unreachable", request=request)
        return httpx.Response(200, json=[record("u1", "Back Online")])

    client = make_client(tmp_path, handler)
    first = await client.world()
    assert first.source == "seed"
    assert client.offline is True

    client.reset_offline()
    second = await client.world()
    await client.close()

    assert client.offline is False
    assert second.source == "network"
    assert [station.name for station in second.stations] == ["Back Online"]


def test_seed_countries_are_derived_from_the_bundled_catalog(tmp_path):
    client = RadioBrowserClient(cache=DiskCache(tmp_path / "cache"))
    countries = {country.code: country for country in client.seed_countries()}
    assert countries["US"].station_count > 0
    assert countries["FR"].name == "France"
    assert countries["US"].latitude is not None

