"""Radio Browser API client with mirror failover and offline catalog fallback."""

from __future__ import annotations

import asyncio
import json
import random
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import httpx

from . import USER_AGENT
from .cache import DiskCache
from .config import api_base_override, asset_path, cache_dir
from .models import Country, Station, normalize_stations

RADIO_BROWSER_HOST = "all.api.radio-browser.info"
FALLBACK_MIRRORS = (
    "de1.api.radio-browser.info",
    "de2.api.radio-browser.info",
    "nl1.api.radio-browser.info",
    "at1.api.radio-browser.info",
    "fr1.api.radio-browser.info",
    "fi1.api.radio-browser.info",
)
MAX_MIRROR_ATTEMPTS = 3
DEFAULT_TIMEOUT = 3.0
OFFLINE_COOLDOWN = 60.0
WORLD_LIMIT = 500
COUNTRY_LIMIT = 300
SEARCH_LIMIT = 120
SEARCH_FIELDS = ("name", "tag", "country")


class ApiError(RuntimeError):
    """Raised when a directory request cannot be satisfied by any mirror."""


@dataclass(slots=True)
class CatalogResult:
    stations: list[Station] = field(default_factory=list)
    source: str = "network"
    fetched_at: float = field(default_factory=time.time)
    offline: bool = False
    error: str = ""

    def __bool__(self) -> bool:
        return bool(self.stations)

    def __len__(self) -> int:
        return len(self.stations)


@dataclass(slots=True)
class CountriesResult:
    countries: list[Country] = field(default_factory=list)
    source: str = "network"
    fetched_at: float = field(default_factory=time.time)
    offline: bool = False
    error: str = ""

    def __bool__(self) -> bool:
        return bool(self.countries)

    def __len__(self) -> int:
        return len(self.countries)


def discover_mirrors() -> list[str]:
    """Resolve Radio Browser mirrors through DNS, then append known fallbacks."""
    hosts: list[str] = []
    try:
        infos = socket.getaddrinfo(
            RADIO_BROWSER_HOST, 443, proto=socket.IPPROTO_TCP
        )
    except OSError:
        infos = []
    for info in infos:
        address = info[4][0]
        try:
            host, _, _ = socket.gethostbyaddr(address)
        except OSError:
            continue
        host = host.rstrip(".")
        if host.endswith(".api.radio-browser.info") and host not in hosts:
            hosts.append(host)
    random.shuffle(hosts)
    for host in FALLBACK_MIRRORS:
        if host not in hosts:
            hosts.append(host)
    return [f"https://{host}" for host in hosts]


def _name_tier(name: str, query: str) -> int:
    lowered = name.casefold()
    if lowered.startswith(query):
        return 3
    tokens = [token for token in lowered.replace("-", " ").split() if token]
    if any(token.startswith(query) for token in tokens):
        return 2
    if query in lowered:
        return 1
    return 0


def rank_stations(stations: Iterable[Station], query: str) -> list[Station]:
    """Rank search hits by name relevance, then community votes."""
    query = query.casefold().strip()
    if not query:
        return list(stations)

    def score(station: Station) -> tuple[int, int, int]:
        tier = _name_tier(station.name, query)
        if tier == 0:
            haystack = f"{station.tags} {station.country} {station.state}".casefold()
            tier = -1 if query in haystack else -2
        return (tier, station.votes, station.clicks)

    return sorted(stations, key=score, reverse=True)


class RadioBrowserClient:
    """Async directory client.

    Every public lookup returns a result object instead of raising: network
    failures degrade to the disk cache and then to the bundled seed catalog.
    """

    def __init__(
        self,
        *,
        cache: DiskCache | None = None,
        mirrors: Sequence[str] | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        seed_path=None,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.cache = cache if cache is not None else DiskCache(cache_dir())
        self.mirrors = list(mirrors) if mirrors else []
        self.base_url = (base_url or api_base_override() or "").rstrip("/") or None
        self.timeout = timeout
        self.user_agent = user_agent
        self._transport = transport
        self._seed_path = seed_path or asset_path("seed_stations.json")
        self._seed: list[Station] | None = None
        self._client: httpx.AsyncClient | None = None
        self._base: str | None = self.base_url
        self._offline_until = 0.0

    # -- lifecycle ---------------------------------------------------------

    async def __aenter__(self) -> "RadioBrowserClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def offline(self) -> bool:
        return time.monotonic() < self._offline_until

    def reset_offline(self) -> None:
        """Allow an immediate retry after the user asks for a refresh."""
        self._offline_until = 0.0
        self._base = self.base_url

    def _mark_offline(self) -> None:
        self._offline_until = time.monotonic() + OFFLINE_COOLDOWN

    # -- cache -------------------------------------------------------------

    @staticmethod
    def cache_key(kind: str, *parts: str) -> str:
        return "-".join((kind, *(str(part).upper() for part in parts if part)))

    def _cached_stations(self, key: str) -> list[Station] | None:
        entry = self.cache.load(key)
        if entry is None or not isinstance(entry.data, list):
            return None
        stations = normalize_stations(
            (item for item in entry.data if isinstance(item, Mapping)),
            limit=WORLD_LIMIT * 4,
        )
        return stations or None

    def _cached_countries(self, key: str) -> list[Country] | None:
        entry = self.cache.load(key)
        if entry is None or not isinstance(entry.data, list):
            return None
        countries = self._parse_countries(entry.data)
        return countries or None

    # -- mirrors -----------------------------------------------------------

    async def _candidate_bases(self) -> list[str]:
        if self.base_url:
            return [self.base_url]
        if self._base:
            return [self._base]
        bases = list(self.mirrors)
        if not bases:
            bases = await asyncio.to_thread(discover_mirrors)
        return bases[:MAX_MIRROR_ATTEMPTS]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                },
                timeout=httpx.Timeout(self.timeout, connect=self.timeout),
                follow_redirects=True,
                transport=self._transport,
            )
        return self._client

    async def _fetch_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET a JSON document, rotating mirrors until one answers."""
        if self.offline:
            raise ApiError("offline cooldown active")
        bases = await self._candidate_bases()
        if not bases:
            raise ApiError("no Radio Browser mirrors available")
        client = await self._get_client()
        errors: list[str] = []
        for base in bases:
            try:
                response = await client.get(f"{base}{path}", params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, OSError, ValueError) as error:
                errors.append(self._error_label(error))
                continue
            self._base = base
            return payload
        self._mark_offline()
        count = len(bases)
        label = "mirror" if count == 1 else "mirrors"
        raise ApiError(
            f"all mirrors failed ({count} {label}): " + "; ".join(errors[:3])
        )

    @staticmethod
    def _error_label(error: Exception) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"HTTP {error.response.status_code}"
        text = str(error).strip()
        return f"{type(error).__name__}: {text}" if text else type(error).__name__

    # -- seed catalog ------------------------------------------------------

    def seed_stations(self) -> list[Station]:
        if self._seed is None:
            try:
                payload = json.loads(self._seed_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = []
            records = payload if isinstance(payload, list) else []
            self._seed = normalize_stations(
                (item for item in records if isinstance(item, Mapping)), limit=1000
            )
        return list(self._seed)

    def seed_world(self, limit: int = WORLD_LIMIT) -> list[Station]:
        stations = sorted(
            self.seed_stations(), key=lambda s: (s.clicks, s.votes), reverse=True
        )
        return stations[:limit]

    def seed_countries(self) -> list[Country]:
        return self._seed_countries()

    # -- public lookups ----------------------------------------------------

    async def world(self, limit: int = WORLD_LIMIT) -> CatalogResult:
        key = self.cache_key("world")
        if not self.offline:
            try:
                payload = await self._fetch_json(
                    f"/json/stations/topclick/{limit}",
                    {"hidebroken": "true"},
                )
                records = self._as_records(payload)
                stations = normalize_stations(records, limit=limit)
                if stations:
                    self.cache.save(key, records[: limit * 2])
                    return CatalogResult(stations, "network")
            except ApiError as error:
                network_error = str(error)
            else:
                network_error = "empty response"
        else:
            network_error = "offline cooldown active"

        cached = self._cached_stations(key)
        if cached:
            return CatalogResult(cached[:limit], "cache", offline=True, error=network_error)
        return CatalogResult(
            self.seed_world(limit), "seed", offline=True, error=network_error
        )

    async def by_country(self, code: str, limit: int = COUNTRY_LIMIT) -> CatalogResult:
        code = code.strip().upper()
        key = self.cache_key("country", code)
        if not self.offline:
            try:
                payload = await self._fetch_json(
                    f"/json/stations/bycountrycodeexact/{code}",
                    {
                        "hidebroken": "true",
                        "order": "votes",
                        "reverse": "true",
                        "limit": limit,
                    },
                )
                records = self._as_records(payload)
                stations = normalize_stations(records, limit=limit)
                if stations:
                    self.cache.save(key, records[: limit * 2])
                    return CatalogResult(stations, "network")
            except ApiError as error:
                network_error = str(error)
            else:
                network_error = "empty response"
        else:
            network_error = "offline cooldown active"

        cached = self._cached_stations(key)
        if cached:
            return CatalogResult(cached[:limit], "cache", offline=True, error=network_error)
        seeded = [s for s in self.seed_stations() if s.country_code == code]
        seeded.sort(key=lambda s: (s.votes, s.clicks), reverse=True)
        return CatalogResult(seeded[:limit], "seed", offline=True, error=network_error)

    async def countries(self) -> CountriesResult:
        key = self.cache_key("countries")
        if not self.offline:
            try:
                payload = await self._fetch_json("/json/countries")
                raw = payload if isinstance(payload, list) else []
                countries = self._parse_countries(raw)
                if countries:
                    self.cache.save(key, raw)
                    return CountriesResult(countries, "network")
            except ApiError as error:
                network_error = str(error)
            else:
                network_error = "empty response"
        else:
            network_error = "offline cooldown active"

        cached = self._cached_countries(key)
        if cached:
            return CountriesResult(cached, "cache", offline=True, error=network_error)
        return CountriesResult(
            self._seed_countries(), "seed", offline=True, error=network_error
        )

    async def search(self, query: str, limit: int = SEARCH_LIMIT) -> CatalogResult:
        query = query.strip()
        if not query:
            return CatalogResult([], "seed", offline=self.offline)
        if self.offline:
            return self._seed_search(query, limit, "offline cooldown active")

        attempts = await asyncio.gather(
            *(self._search_field(field, query) for field in SEARCH_FIELDS),
            return_exceptions=True,
        )
        merged: list[Station] = []
        seen: set[str] = set()
        failures = 0
        error_text = ""
        for attempt in attempts:
            if isinstance(attempt, BaseException):
                failures += 1
                error_text = str(attempt)
                continue
            for station in attempt:
                if station.id not in seen:
                    seen.add(station.id)
                    merged.append(station)
        if merged:
            ranked = rank_stations(merged, query)[:limit]
            return CatalogResult(ranked, "network")
        if failures == len(SEARCH_FIELDS):
            self._mark_offline()
            return self._seed_search(query, limit, error_text)
        return CatalogResult([], "network")

    async def _search_field(self, field: str, query: str) -> list[Station]:
        payload = await self._fetch_json(
            "/json/stations/search",
            {
                field: query,
                "hidebroken": "true",
                "order": "votes",
                "reverse": "true",
                "limit": SEARCH_LIMIT,
            },
        )
        return normalize_stations(self._as_records(payload), limit=SEARCH_LIMIT)

    def _seed_search(self, query: str, limit: int, error: str) -> CatalogResult:
        tokens = [token for token in query.casefold().split() if token]
        matches = [
            station
            for station in self.seed_stations()
            if all(token in station.search_text for token in tokens)
        ]
        return CatalogResult(
            rank_stations(matches, query)[:limit],
            "seed",
            offline=True,
            error=error,
        )

    async def random_station(
        self, *, excluded_ids: Iterable[str] = (), limit: int = SEARCH_LIMIT
    ) -> Station | None:
        excluded = set(excluded_ids)
        if not self.offline:
            try:
                payload = await self._fetch_json(
                    "/json/stations/search",
                    {
                        "hidebroken": "true",
                        "order": "random",
                        "limit": limit,
                    },
                )
                stations = normalize_stations(self._as_records(payload), limit=limit)
                candidates = [s for s in stations if s.id not in excluded]
                if candidates:
                    return random.choice(candidates)
            except ApiError:
                pass
        pool = [s for s in self.seed_stations() if s.id not in excluded]
        if not pool:
            pool = self.seed_stations()
        return random.choice(pool) if pool else None

    async def register_click(self, station_id: str) -> None:
        if not station_id or station_id.startswith("seed-"):
            return
        try:
            await self._fetch_json(f"/json/url/{station_id}")
        except ApiError:
            pass

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _as_records(payload: Any) -> list[Mapping[str, Any]]:
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

    def _parse_countries(self, raw: Iterable[Any]) -> list[Country]:
        from .geo import load_geo_index

        try:
            geo = load_geo_index()
        except Exception:
            geo = None
        countries: list[Country] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            code = str(item.get("iso_3166_1") or item.get("code") or "").upper()
            if len(code) != 2 or code in seen:
                continue
            seen.add(code)
            geo_country = geo.country_by_code(code) if geo else None
            name = str(item.get("name") or "").strip() or (
                geo_country.name if geo_country else code
            )
            count = item.get("stationcount") or item.get("station_count") or 0
            try:
                count = max(0, int(count))
            except (TypeError, ValueError):
                count = 0
            countries.append(
                Country(
                    code=code,
                    name=name,
                    continent=geo_country.continent if geo_country else "",
                    latitude=geo_country.latitude if geo_country else None,
                    longitude=geo_country.longitude if geo_country else None,
                    index=geo_country.index if geo_country else 0,
                    station_count=count,
                )
            )
        countries.sort(key=lambda country: (-country.station_count, country.name))
        return countries

    def _seed_countries(self) -> list[Country]:
        from .geo import load_geo_index

        try:
            geo = load_geo_index()
        except Exception:
            geo = None
        counts: dict[str, int] = {}
        names: dict[str, str] = {}
        for station in self.seed_stations():
            code = station.country_code
            if not code:
                continue
            counts[code] = counts.get(code, 0) + 1
            names.setdefault(code, station.country)
        countries: list[Country] = []
        for code, count in counts.items():
            geo_country = geo.country_by_code(code) if geo else None
            countries.append(
                Country(
                    code=code,
                    name=geo_country.name if geo_country else names.get(code, code),
                    continent=geo_country.continent if geo_country else "",
                    latitude=geo_country.latitude if geo_country else None,
                    longitude=geo_country.longitude if geo_country else None,
                    index=geo_country.index if geo_country else 0,
                    station_count=count,
                )
            )
        countries.sort(key=lambda country: (-country.station_count, country.name))
        return countries

    def stations_for_country(self, code: str) -> list[Station]:
        code = code.strip().upper()
        return [s for s in self.seed_stations() if s.country_code == code]

    def cities_for_country(self, code: str) -> list[tuple[str, int]]:
        """Aggregate stations per city/state for the offline catalog."""
        code = code.strip().upper()
        counts: dict[str, int] = {}
        for station in self.seed_stations():
            if station.country_code != code or not station.state:
                continue
            counts[station.state] = counts.get(station.state, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def best_country_label(countries: Iterable[Country], code: str) -> str:
    for country in countries:
        if country.code == code:
            return country.name
    return code
