"""Orthographic braille globe rendering.

The globe samples the bundled equirectangular country mask. Each terminal cell
is a 2x4 braille grid, which keeps a full redraw cheap enough for keyboard
rotation while producing recognizable coastlines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .geo import GeoIndex
from .models import Country, Station

DOT_BITS = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)

MIN_ZOOM = 0.55
MAX_ZOOM = 5.0
MIN_LATITUDE = -78.0
MAX_LATITUDE = 78.0

STYLE_OCEAN = "ocean"
STYLE_LAND = "land"
STYLE_FOCUS = "focus"
STYLE_RIM = "rim"
STYLE_STATION = "station"
STYLE_PLAYING = "playing"
STYLE_FAVORITE = "favorite"
STYLE_SELECTED = "selected"
STYLE_RETICLE = "reticle"

MARKER_GLYPHS = {
    STYLE_PLAYING: "◉",
    STYLE_SELECTED: "◇",
    STYLE_FAVORITE: "★",
    STYLE_STATION: "●",
}
ASCII_GLYPHS = {
    STYLE_PLAYING: "@",
    STYLE_SELECTED: "O",
    STYLE_FAVORITE: "*",
    STYLE_STATION: "o",
}

MARKER_PRIORITY = {
    STYLE_PLAYING: 4,
    STYLE_SELECTED: 3,
    STYLE_FAVORITE: 2,
    STYLE_STATION: 1,
}


def wrap_longitude(longitude: float) -> float:
    wrapped = (longitude + 180.0) % 360.0
    if wrapped < 0:
        wrapped += 360.0
    return wrapped - 180.0


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def project(
    latitude: float, longitude: float, center_latitude: float, center_longitude: float
) -> tuple[float, float, float]:
    """Orthographic projection. Returns (x, y, z); z>0 faces the viewer."""
    phi = math.radians(latitude)
    lam = math.radians(wrap_longitude(longitude - center_longitude))
    phi0 = math.radians(center_latitude)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)
    cos_phi0 = math.cos(phi0)
    sin_phi0 = math.sin(phi0)
    return (
        cos_phi * math.sin(lam),
        cos_phi0 * sin_phi - sin_phi0 * cos_phi * math.cos(lam),
        sin_phi0 * sin_phi + cos_phi0 * cos_phi * math.cos(lam),
    )


def unproject(
    x: float, y: float, center_latitude: float, center_longitude: float
) -> tuple[float, float] | None:
    """Inverse orthographic projection for a point in the unit disc."""
    rho2 = x * x + y * y
    if rho2 > 1.0:
        return None
    z = math.sqrt(max(0.0, 1.0 - rho2))
    phi0 = math.radians(center_latitude)
    cos_phi0 = math.cos(phi0)
    sin_phi0 = math.sin(phi0)
    latitude = math.asin(clamp(y * cos_phi0 + z * sin_phi0, -1.0, 1.0))
    longitude = math.radians(center_longitude) + math.atan2(
        x, z * cos_phi0 - y * sin_phi0
    )
    return math.degrees(latitude), wrap_longitude(math.degrees(longitude))


@dataclass(frozen=True, slots=True)
class Marker:
    station: Station
    column: int
    row: int
    depth: float


@dataclass(frozen=True, slots=True)
class GlobeFrame:
    width: int
    height: int
    lines: tuple[tuple[tuple[str, str], ...], ...]
    markers: tuple[Marker, ...]
    center_country: Country | None

    def plain(self) -> str:
        return "\n".join("".join(char for char, _ in line) for line in self.lines)


def globe_radius(width: int, height: int, zoom: float) -> float:
    return min(width * 2, height * 4) * 0.47 * clamp(zoom, MIN_ZOOM, MAX_ZOOM)


def station_cell(
    latitude: float,
    longitude: float,
    width: int,
    height: int,
    center_latitude: float,
    center_longitude: float,
    zoom: float,
) -> tuple[int, int, float] | None:
    """Map a coordinate to a terminal cell, or None when not visible."""
    if width <= 0 or height <= 0:
        return None
    x, y, z = project(latitude, longitude, center_latitude, center_longitude)
    if z <= 0.02:
        return None
    radius = globe_radius(width, height, zoom)
    dot_x = width + x * radius
    dot_y = height * 2 - y * radius
    column = int(dot_x // 2)
    row = int(dot_y // 4)
    if not (0 <= column < width and 0 <= row < height):
        return None
    return column, row, z


class GlobeRenderer:
    def __init__(self, geo: GeoIndex, *, ascii_mode: bool = False) -> None:
        self.geo = geo
        self.ascii_mode = ascii_mode

    def render(
        self,
        *,
        width: int,
        height: int,
        center_latitude: float = 20.0,
        center_longitude: float = 0.0,
        zoom: float = 1.0,
        stations: Iterable[Station] = (),
        selected_id: str | None = None,
        playing_id: str | None = None,
        favorite_ids: Sequence[str] | set[str] = (),
    ) -> GlobeFrame:
        if width <= 0 or height <= 0:
            return GlobeFrame(width, height, (), (), None)

        center_latitude = clamp(center_latitude, MIN_LATITUDE, MAX_LATITUDE)
        center_longitude = wrap_longitude(center_longitude)
        zoom = clamp(zoom, MIN_ZOOM, MAX_ZOOM)
        dot_width = width * 2
        dot_height = height * 4
        center_x = dot_width / 2
        center_y = dot_height / 2
        radius = globe_radius(width, height, zoom)

        center_country = self.geo.nearest_country(
            center_latitude, center_longitude, 1.5
        )
        focus_index = center_country.index if center_country else 0
        phi0 = math.radians(center_latitude)
        sin0 = math.sin(phi0)
        cos0 = math.cos(phi0)
        lon0 = math.radians(center_longitude)

        bits = [0] * (width * height)
        land = bytearray(width * height)
        focus = bytearray(width * height)
        rim = bytearray(width * height)

        left = max(0, int(center_x - radius) - 1)
        right = min(dot_width, int(center_x + radius) + 2)
        top = max(0, int(center_y - radius) - 1)
        bottom = min(dot_height, int(center_y + radius) + 2)

        for dot_row in range(top, bottom):
            dy = (center_y - (dot_row + 0.5)) / radius
            cell_row = dot_row // 4
            sub_row = dot_row % 4
            for dot_column in range(left, right):
                dx = (dot_column + 0.5 - center_x) / radius
                distance_squared = dx * dx + dy * dy
                if distance_squared > 1.0:
                    continue
                z = math.sqrt(max(0.0, 1.0 - distance_squared))
                latitude = math.asin(clamp(dy * cos0 + z * sin0, -1.0, 1.0))
                longitude = lon0 + math.atan2(dx, z * cos0 - dy * sin0)
                value = self.geo.value_at(
                    math.degrees(latitude), math.degrees(longitude)
                )
                if value == 0:
                    continue
                cell_column = dot_column // 2
                index = cell_row * width + cell_column
                land[index] = 1
                bits[index] |= DOT_BITS[sub_row][dot_column % 2]
                if focus_index and value == focus_index:
                    focus[index] = 1

        self._draw_rim(rim, width, height, center_x, center_y, radius)

        markers: dict[int, tuple[int, str, str]] = {}
        station_markers: list[Marker] = []
        favorites = set(favorite_ids)
        for station in stations:
            if not station.has_location:
                continue
            cell = station_cell(
                station.latitude or 0.0,
                station.longitude or 0.0,
                width,
                height,
                center_latitude,
                center_longitude,
                zoom,
            )
            if cell is None:
                continue
            column, row, depth = cell
            station_markers.append(Marker(station, column, row, depth))
            if station.id == playing_id:
                style = STYLE_PLAYING
            elif station.id == selected_id:
                style = STYLE_SELECTED
            elif station.id in favorites:
                style = STYLE_FAVORITE
            else:
                style = STYLE_STATION
            priority = MARKER_PRIORITY[style]
            index = row * width + column
            existing = markers.get(index)
            if existing is None or priority > existing[0]:
                markers[index] = (priority, style, MARKER_GLYPHS[style])

        center_index = (height // 2) * width + width // 2
        if center_index not in markers:
            markers[center_index] = (0, STYLE_RETICLE, "+")

        lines: list[tuple[tuple[str, str], ...]] = []
        for row in range(height):
            cells: list[tuple[str, str]] = []
            for column in range(width):
                index = row * width + column
                marker = markers.get(index)
                if marker is not None:
                    cells.append((marker[2], marker[1]))
                elif land[index]:
                    if self.ascii_mode:
                        cells.append(("#", STYLE_FOCUS if focus[index] else STYLE_LAND))
                    else:
                        cells.append(
                            (
                                chr(0x2800 + bits[index]),
                                STYLE_FOCUS if focus[index] else STYLE_LAND,
                            )
                        )
                elif rim[index]:
                    cells.append(("." if self.ascii_mode else "⠂", STYLE_RIM))
                else:
                    cells.append((" ", STYLE_OCEAN))
            lines.append(tuple(cells))

        return GlobeFrame(
            width=width,
            height=height,
            lines=tuple(lines),
            markers=tuple(station_markers),
            center_country=center_country,
        )

    def country_at_cell(
        self,
        column: int,
        row: int,
        *,
        width: int,
        height: int,
        center_latitude: float,
        center_longitude: float,
        zoom: float,
    ) -> Country | None:
        if width <= 0 or height <= 0:
            return None
        radius = globe_radius(width, height, zoom)
        dx = ((column * 2 + 1) - width) / radius
        dy = (height * 2 - (row * 4 + 2)) / radius
        point = unproject(dx, dy, center_latitude, center_longitude)
        if point is None:
            return None
        return self.geo.nearest_country(point[0], point[1], 0.75)

    def station_at_cell(
        self, column: int, row: int, markers: Iterable[Marker], radius: int = 1
    ) -> Marker | None:
        best: Marker | None = None
        best_distance = float("inf")
        for marker in markers:
            dx = abs(marker.column - column)
            dy = abs(marker.row - row)
            if dx > radius or dy > radius:
                continue
            distance = math.hypot(dx, dy)
            if distance < best_distance:
                best = marker
                best_distance = distance
        return best

    @staticmethod
    def _draw_rim(
        rim: bytearray,
        width: int,
        height: int,
        center_x: float,
        center_y: float,
        radius: float,
    ) -> None:
        band = max(0.012, 2.2 / radius)
        for row in range(height):
            for column in range(width):
                dx = (column * 2 + 1 - center_x) / radius
                dy = (center_y - (row * 4 + 2)) / radius
                distance = math.hypot(dx, dy)
                if abs(distance - 1.0) <= band:
                    rim[row * width + column] = 1
