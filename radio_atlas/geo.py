"""Country index and equirectangular land mask bundled with the app."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from .config import asset_path
from .models import Country

MASK_WIDTH = 1440
MASK_HEIGHT = 720


class GeoAssetError(RuntimeError):
    """Raised when the bundled geographic assets are missing or invalid."""


class GeoIndex:
    """Look up the country at a coordinate using the bundled country mask."""

    def __init__(self, mask: bytes, countries: list[dict]) -> None:
        if len(mask) != MASK_WIDTH * MASK_HEIGHT:
            raise GeoAssetError(
                f"worldmask.bin has {len(mask)} bytes, expected "
                f"{MASK_WIDTH * MASK_HEIGHT}"
            )
        if len(countries) > 255:
            raise GeoAssetError("countries.json has more entries than the mask can hold")
        self._mask = mask
        self.countries: list[Country] = []
        self._by_code: dict[str, Country] = {}
        for index, raw in enumerate(countries, start=1):
            country = Country(
                code=str(raw.get("code") or ""),
                name=str(raw.get("name") or ""),
                continent=str(raw.get("continent") or ""),
                latitude=raw.get("label_lat"),
                longitude=raw.get("label_lon"),
                index=index,
            )
            self.countries.append(country)
            if country.code:
                self._by_code.setdefault(country.code, country)

    @classmethod
    def load(cls, directory: Path | None = None) -> "GeoIndex":
        base = directory or asset_path("")
        try:
            mask = (base / "worldmask.bin").read_bytes()
            countries = json.loads((base / "countries.json").read_text())
        except OSError as error:
            raise GeoAssetError(f"Cannot read geographic assets in {base}: {error}") from error
        except json.JSONDecodeError as error:
            raise GeoAssetError(f"countries.json is not valid JSON: {error}") from error
        return cls(mask, countries)

    def __len__(self) -> int:
        return len(self.countries)

    def value_at(self, latitude: float, longitude: float) -> int:
        """Return the 1-based country index at a coordinate, or 0 for ocean."""
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            return 0
        latitude = max(-90.0, min(90.0, latitude))
        longitude = ((longitude + 180.0) % 360.0) - 180.0
        column = int((longitude + 180.0) / 360.0 * MASK_WIDTH) % MASK_WIDTH
        row = int((90.0 - latitude) / 180.0 * MASK_HEIGHT)
        row = max(0, min(MASK_HEIGHT - 1, row))
        return self._mask[row * MASK_WIDTH + column]

    def country_at(self, latitude: float, longitude: float) -> Country | None:
        value = self.value_at(latitude, longitude)
        return self.countries[value - 1] if value else None

    def country_by_code(self, code: str) -> Country | None:
        return self._by_code.get(code.strip().upper())

    def country_name(self, code: str) -> str:
        country = self.country_by_code(code)
        return country.name if country else code

    def nearest_country(
        self, latitude: float, longitude: float, radius_degrees: float = 1.5
    ) -> Country | None:
        """Return the nearest land country within a small radius."""
        country = self.country_at(latitude, longitude)
        if country is not None:
            return country
        steps = max(1, int(radius_degrees * 2))
        for ring in range(1, steps + 1):
            delta = ring * 0.5
            offsets = (
                (delta, 0.0),
                (-delta, 0.0),
                (0.0, delta),
                (0.0, -delta),
                (delta, delta),
                (delta, -delta),
                (-delta, delta),
                (-delta, -delta),
            )
            for lat_offset, lon_offset in offsets:
                country = self.country_at(
                    latitude + lat_offset, longitude + lon_offset
                )
                if country is not None:
                    return country
        return None


@lru_cache(maxsize=1)
def load_geo_index() -> GeoIndex:
    return GeoIndex.load()
