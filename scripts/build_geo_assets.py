"""Build the compact geographic assets shipped with Radio Atlas.

The full Natural Earth GeoJSON is never shipped. This script rasterizes the
country polygons into an equirectangular country mask (one byte per cell) and
writes a small country index used for labels, ISO lookups, and camera targets.

Usage:
    python scripts/build_geo_assets.py [--source PATH] [--out-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_110m_admin_0_countries.geojson"
)
GRID_WIDTH = 1440
GRID_HEIGHT = 720
VALID_CODE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def ring_points(ring: list[list[float]]) -> list[tuple[float, float]]:
    """Unwrap a ring's longitudes so consecutive points never jump the seam."""
    points: list[tuple[float, float]] = []
    previous_lon: float | None = None
    for coordinate in ring:
        if not isinstance(coordinate, list) or len(coordinate) < 2:
            continue
        try:
            lon = float(coordinate[0])
            lat = float(coordinate[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lon) and math.isfinite(lat)):
            continue
        if previous_lon is not None:
            while lon - previous_lon > 180:
                lon -= 360
            while lon - previous_lon < -180:
                lon += 360
        points.append((lon, lat))
        previous_lon = lon
    return points


def fill_polygon(
    mask: bytearray,
    polygons: list[list[tuple[float, float]]],
    value: int,
) -> None:
    """Rasterize one polygon (outer ring plus holes) with even-odd fill."""
    for shift in (-360.0, 0.0, 360.0):
        edges: list[tuple[float, float, float, float]] = []
        minimum_lon = math.inf
        maximum_lon = -math.inf
        minimum_lat = math.inf
        maximum_lat = -math.inf
        for ring in polygons:
            if len(ring) < 3:
                continue
            for index in range(len(ring)):
                x1, y1 = ring[index - 1]
                x2, y2 = ring[index]
                x1 += shift
                x2 += shift
                if y1 == y2:
                    continue
                if y1 > y2:
                    x1, y1, x2, y2 = x2, y2, x1, y1
                edges.append((x1, y1, x2, y2))
                minimum_lon = min(minimum_lon, x1, x2)
                maximum_lon = max(maximum_lon, x1, x2)
                minimum_lat = min(minimum_lat, y1, y2)
                maximum_lat = max(maximum_lat, y1, y2)
        if not edges or minimum_lon > 180 or maximum_lon < -180:
            continue

        first_row = max(0, math.floor((90 - maximum_lat) / 180 * GRID_HEIGHT))
        last_row = min(
            GRID_HEIGHT - 1, math.ceil((90 - minimum_lat) / 180 * GRID_HEIGHT)
        )
        for row in range(first_row, last_row + 1):
            latitude = 90 - (row + 0.5) / GRID_HEIGHT * 180
            crossings: list[float] = []
            for x1, y1, x2, y2 in edges:
                if (y1 <= latitude < y2) or (y2 <= latitude < y1):
                    crossings.append(
                        x1 + (latitude - y1) * (x2 - x1) / (y2 - y1)
                    )
            if len(crossings) < 2:
                continue
            crossings.sort()
            for index in range(0, len(crossings) - 1, 2):
                start = max(
                    0,
                    math.ceil(
                        (crossings[index] + 180) / 360 * GRID_WIDTH - 0.5
                    ),
                )
                end = min(
                    GRID_WIDTH - 1,
                    math.floor(
                        (crossings[index + 1] + 180) / 360 * GRID_WIDTH - 0.5
                    ),
                )
                if start > end:
                    continue
                offset = row * GRID_WIDTH
                mask[offset + start : offset + end + 1] = bytes(
                    [value] * (end - start + 1)
                )


def country_code(properties: dict) -> str:
    for key in ("ISO_A2", "ISO_A2_EH"):
        code = str(properties.get(key) or "").strip().upper()
        if len(code) == 2 and set(code) <= VALID_CODE:
            return code
    return ""


def geometry_polygons(geometry: dict) -> list[list[list[list[float]]]]:
    if geometry.get("type") == "Polygon":
        return [geometry.get("coordinates") or []]
    if geometry.get("type") == "MultiPolygon":
        return geometry.get("coordinates") or []
    return []


def build(source: Path, out_dir: Path) -> None:
    data = json.loads(source.read_text())
    features = data.get("features") or []
    out_dir.mkdir(parents=True, exist_ok=True)

    mask = bytearray(GRID_WIDTH * GRID_HEIGHT)
    countries: list[dict] = []
    codes: set[str] = set()

    for feature in features:
        properties = feature.get("properties") or {}
        name = str(properties.get("NAME") or properties.get("ADMIN") or "").strip()
        if not name:
            continue
        code = country_code(properties)
        if code and code in codes:
            code = ""
        if code:
            codes.add(code)

        try:
            label_lon = float(properties.get("LABEL_X"))
            label_lat = float(properties.get("LABEL_Y"))
        except (TypeError, ValueError):
            label_lon = label_lat = None
        if label_lat is None or label_lon is None:
            label_lon = label_lat = None

        countries.append(
            {
                "code": code,
                "name": name,
                "continent": str(properties.get("CONTINENT") or ""),
                "label_lat": round(label_lat, 4) if label_lat is not None else None,
                "label_lon": round(label_lon, 4) if label_lon is not None else None,
            }
        )
        index = len(countries)
        if index > 255:
            raise SystemExit("Too many countries for the one-byte mask")

        for polygon in geometry_polygons(feature.get("geometry") or {}):
            rings = [ring_points(ring) for ring in polygon]
            rings = [ring for ring in rings if len(ring) >= 3]
            if rings:
                fill_polygon(mask, rings, index)

    (out_dir / "worldmask.bin").write_bytes(bytes(mask))
    (out_dir / "countries.json").write_text(
        json.dumps(countries, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    covered = sum(1 for value in mask if value)
    print(
        f"Wrote {len(countries)} countries, {covered} land cells "
        f"({covered / (GRID_WIDTH * GRID_HEIGHT):.1%}) to {out_dir}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "radio_atlas" / "assets",
    )
    args = parser.parse_args()

    source = args.source
    if source is None:
        cache = Path(__file__).resolve().parent / ".cache"
        cache.mkdir(exist_ok=True)
        source = cache / "ne_110m_admin_0_countries.geojson"
        if not source.exists():
            print(f"Downloading {SOURCE_URL}")
            urllib.request.urlretrieve(SOURCE_URL, source)
    build(source, args.out_dir)


if __name__ == "__main__":
    main()
