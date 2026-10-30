"""Domain models and defensive normalization of Radio Browser records."""

from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

_CONTROL = re.compile(
    r"[\u0000-\u001f\u007f-\u009f\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]"
)
_SPACES = re.compile(r"\s+")
_TRACK_SEPARATOR = re.compile(r"^(.+?)\s+[-–—]\s+(.+)$")
_STATION_PREFIX_SEPARATOR = re.compile(r"^(\s+[-–—|·:/]\s+|\s*[:|·]\s*)")
_HTTP_URL = re.compile(r"^https?://", re.IGNORECASE)


def clean_text(value: Any, limit: int = 300) -> str:
    """Strip control, zero-width and bidi characters; collapse whitespace."""
    if value is None:
        return ""
    text = _CONTROL.sub("", str(value))
    text = _SPACES.sub(" ", text).strip()
    return text[:limit]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _code(value: Any) -> str:
    code = clean_text(value, 8).upper()
    return code if len(code) == 2 and code.isalpha() and code.isascii() else ""


def _valid_url(value: Any) -> str:
    url = clean_text(value, 2048)
    return url if _HTTP_URL.match(url) else ""


def _stable_id(name: str, url: str) -> str:
    digest = hashlib.sha1(f"{name}\0{url}".encode("utf-8")).hexdigest()
    return f"local-{digest[:20]}"


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    name: str
    url: str
    homepage: str = ""
    favicon: str = ""
    country: str = ""
    country_code: str = ""
    state: str = ""
    language: str = ""
    tags: str = ""
    codec: str = ""
    bitrate: int = 0
    votes: int = 0
    clicks: int = 0
    latitude: float | None = None
    longitude: float | None = None
    estimated_location: bool = False

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def place(self) -> str:
        return self.state or self.country

    @property
    def country_label(self) -> str:
        return self.country or self.country_code

    @property
    def meta(self) -> str:
        parts = [self.country_label]
        if self.state:
            parts.append(self.state)
        if self.codec:
            parts.append(self.codec)
        if self.bitrate > 0:
            parts.append(f"{self.bitrate} kbps")
        return " · ".join(part for part in parts if part)

    @property
    def tagline(self) -> str:
        tags = [clean_text(tag, 40) for tag in self.tags.split(",")]
        return " · ".join(tag for tag in tags if tag)[:120]

    @property
    def search_text(self) -> str:
        return " ".join(
            (
                self.name,
                self.country,
                self.country_code,
                self.state,
                self.language,
                self.tags,
                self.codec,
            )
        ).lower()

    def to_record(self) -> dict[str, Any]:
        return {
            "stationuuid": self.id,
            "name": self.name,
            "url_resolved": self.url,
            "homepage": self.homepage,
            "favicon": self.favicon,
            "country": self.country,
            "countrycode": self.country_code,
            "state": self.state,
            "language": self.language,
            "tags": self.tags,
            "codec": self.codec,
            "bitrate": self.bitrate,
            "votes": self.votes,
            "clickcount": self.clicks,
            "geo_lat": self.latitude,
            "geo_long": self.longitude,
            "estimated_location": self.estimated_location,
        }


def station_from_api(
    raw: Mapping[str, Any], *, estimated_location: bool | None = None
) -> Station | None:
    """Normalize one Radio Browser record. Returns None when unusable."""
    if not isinstance(raw, Mapping):
        return None
    url = _valid_url(raw.get("url_resolved")) or _valid_url(raw.get("url"))
    if not url:
        return None
    name = clean_text(raw.get("name"), 160) or "Unknown station"
    station_id = clean_text(
        raw.get("stationuuid") or raw.get("uuid") or raw.get("id"), 64
    )
    if not station_id:
        station_id = _stable_id(name, url)

    latitude = _as_float(raw.get("geo_lat"))
    longitude = _as_float(raw.get("geo_long"))
    if latitude is not None and not (-90 <= latitude <= 90):
        latitude = None
    if longitude is not None and not (-180 <= longitude <= 180):
        longitude = None
    if latitude is None or longitude is None:
        latitude = longitude = None

    estimate = bool(raw.get("estimated_location")) if estimated_location is None else estimated_location

    return Station(
        id=station_id,
        name=name,
        url=url,
        homepage=_valid_url(raw.get("homepage")),
        favicon=_valid_url(raw.get("favicon")),
        country=clean_text(raw.get("country"), 100),
        country_code=_code(raw.get("countrycode")),
        state=clean_text(raw.get("state"), 100),
        language=clean_text(raw.get("language"), 120),
        tags=clean_text(raw.get("tags"), 500),
        codec=clean_text(raw.get("codec"), 32),
        bitrate=_as_int(raw.get("bitrate")),
        votes=_as_int(raw.get("votes")),
        clicks=_as_int(raw.get("clickcount")),
        latitude=latitude,
        longitude=longitude,
        estimated_location=estimate,
    )


def normalize_stations(
    records: Iterable[Mapping[str, Any]], *, limit: int = 500
) -> list[Station]:
    """Normalize and deduplicate station records by uuid."""
    stations: list[Station] = []
    seen: set[str] = set()
    for record in records:
        station = station_from_api(record)
        if station is None or station.id in seen:
            continue
        seen.add(station.id)
        stations.append(station)
        if len(stations) >= limit:
            break
    return stations


@dataclass(frozen=True, slots=True)
class Country:
    code: str
    name: str
    continent: str = ""
    latitude: float | None = None
    longitude: float | None = None
    index: int = 0
    station_count: int = 0

    @property
    def has_label(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    station: Station
    played_at: float

    def to_record(self) -> dict[str, Any]:
        return {"station": self.station.to_record(), "played_at": self.played_at}


def parse_track(raw_title: str, station_name: str = "") -> tuple[str, str]:
    """Split stream metadata into an (artist, title) pair.

    A leading station name is removed only when it is the whole value or is
    followed by a separator, so "Rockwell - ..." on "Rock" stays intact.
    """
    title = clean_text(raw_title, 300).lstrip(" :|-–—·")
    station = clean_text(station_name, 160)
    if station and title.lower().startswith(station.lower()):
        rest = title[len(station) :]
        if not rest:
            title = ""
        elif _STATION_PREFIX_SEPARATOR.match(rest):
            title = rest.lstrip(" :|-–—·/").strip()
    match = _TRACK_SEPARATOR.match(title)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", title


def format_count(value: int) -> str:
    return f"{value:,}"


def relative_time(timestamp: float, now: float | None = None) -> str:
    seconds = max(0, int((now if now is not None else time.time()) - timestamp))
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    if seconds < 86400 * 30:
        return f"{seconds // 86400}d"
    return f"{seconds // (86400 * 30)}mo"
