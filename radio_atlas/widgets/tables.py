"""Data tables for countries, cities and stations."""

from __future__ import annotations

from typing import Literal

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widgets import DataTable

from ..genres import Genre
from ..models import Country, Station, format_count
from .panels import ACCENT, FAVORITE_COLOR, ICONS, MUTED, TEXT

EMPTY_KEY = "__empty__"
ALL_CITIES_KEY = "__all__"
UNKNOWN_CITY_KEY = "__unknown__"


def _cell(value: str, width: int, *, style: str = "", justify: Literal["left", "right"] = "left") -> Text:
    clipped = value if len(value) <= width else value[: max(0, width - 1)] + "…"
    return Text(
        clipped,
        style=style,
        no_wrap=True,
        overflow="ellipsis",
        justify=justify,
    )


FAVORITE_WIDTH = 5
MARKER_WIDTH = 1
ROW_HEIGHT = 2


def _marker(playing: bool) -> Text:
    return Text("▶" if playing else " ", style=f"bold {ACCENT}", no_wrap=True)


class StationsTable(DataTable):
    class FavoriteClicked(Message):
        """A row's star block was clicked; carries that row's station id."""

        def __init__(self, station_id: str) -> None:
            super().__init__()
            self.station_id = station_id

    def __init__(self, *, ascii_mode: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.ascii_mode = ascii_mode
        self.tooltip = "Click the star at the right of a station row to toggle its favorite without playing it."
        self.stations: list[Station] = []
        self._index: dict[str, int] = {}
        self._favorite_ids: set[str] = set()
        self._playing_id: str | None = None
        self._viewport_width = 0

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = False
        self.show_header = False
        self.show_row_labels = False
        self._rebuild_rows()

    def on_resize(self) -> None:
        selected = self.selected_station()
        if self.size.width != self._viewport_width:
            self._rebuild_rows()
        # Height-only changes can otherwise leave the selected row offscreen.
        if selected is not None:
            self.select_station(selected.id)

    def set_stations(self, stations: list[Station], favorite_ids: set[str] | None = None) -> None:
        self.stations = list(stations)
        self._index = {station.id: index for index, station in enumerate(self.stations)}
        self._favorite_ids = set(favorite_ids or ())
        self._rebuild_rows()

    def _star(self, active: bool) -> Text:
        glyph = "[*]" if self.ascii_mode and active else (
            "[ ]" if self.ascii_mode else (ICONS["star"] if active else ICONS["star_outline"])
        )
        color = FAVORITE_COLOR if active else MUTED
        return Text(glyph, style=f"bold {color}" if active else color, justify="center", no_wrap=True)

    def _rebuild_rows(self) -> None:
        # Reserve a scrollbar cell even before it appears. Fixed column widths
        # prevent End / horizontal scrolling from hiding the station names.
        self._viewport_width = self.size.width
        padding = self.cell_padding * 2 * 3
        station_width = max(
            1, self.size.width - 1 - MARKER_WIDTH - FAVORITE_WIDTH - padding
        )
        self.clear(columns=True)
        self.add_column("PLAYING", key="marker", width=MARKER_WIDTH)
        self.add_column("STATION", key="station", width=station_width)
        self.add_column("STAR", key="favorite", width=FAVORITE_WIDTH)
        if not self.stations:
            self.add_row(
                _cell("", MARKER_WIDTH),
                _cell("No stations here", 34, style=f"italic {MUTED}"),
                _cell("", FAVORITE_WIDTH),
                key=EMPTY_KEY,
            )
            return
        for station in self.stations:
            card = Text(station.name, style=f"bold {TEXT}", no_wrap=True, overflow="ellipsis")
            meta = " · ".join(part for part in (
                station.country_code, station.codec,
                f"{station.bitrate} kbps" if station.bitrate else "",
            ) if part)
            card.append(f"\n{meta}", style=f"not bold {MUTED}")
            self.add_row(
                _marker(station.id == self._playing_id),
                card,
                self._star(station.id in self._favorite_ids),
                key=station.id,
                height=ROW_HEIGHT,
            )
        if self.row_count:
            self.move_cursor(row=0, animate=False)

    def update_favorites(self, favorite_ids: set[str]) -> None:
        changed = self._favorite_ids ^ set(favorite_ids)
        self._favorite_ids = set(favorite_ids)
        for station_id in changed:
            if station_id in self._index:
                self.update_cell(station_id, "favorite", self._star(station_id in favorite_ids))

    def update_playing(self, station_id: str | None) -> None:
        """Mark the station that is playing or paused with a ▶ in the gutter."""
        previous, self._playing_id = self._playing_id, station_id
        for key in {previous, station_id}:
            if key is not None and key in self._index:
                self.update_cell(key, "marker", _marker(key == station_id))

    def on_click(self, event: events.Click) -> None:
        # A star click toggles that row only: keep it from moving the cursor or
        # selecting (and therefore playing) the row.
        meta = event.style.meta
        if "row" not in meta or meta.get("column") != self.get_column_index("favorite") or meta["row"] < 0:
            return
        if meta["row"] >= len(self.ordered_rows):
            return
        key = self.ordered_rows[meta["row"]].key.value
        if key not in self._index:
            return
        event.prevent_default()
        event.stop()
        self.post_message(self.FavoriteClicked(key))

    def selected_station(self) -> Station | None:
        if not self.stations:
            return None
        try:
            row = self.cursor_row
        except Exception:
            return self.stations[0] if self.stations else None
        if 0 <= row < len(self.stations):
            return self.stations[row]
        return None

    def station_for_key(self, key: str) -> Station | None:
        index = self._index.get(key)
        return self.stations[index] if index is not None else None

    def select_station(self, station_id: str) -> None:
        index = self._index.get(station_id)
        if index is not None:
            self.move_cursor(row=index, animate=False)


class CountriesTable(DataTable):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.countries: list[Country] = []
        self._by_code: dict[str, Country] = {}
    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("COUNTRY", "CODE", "STATIONS")

    def set_countries(self, countries: list[Country], filter_text: str = "") -> None:
        query = filter_text.strip().casefold()
        if query:
            visible = [
                country
                for country in countries
                if query in country.name.casefold() or query in country.code.casefold()
            ]
        else:
            visible = list(countries)
        self.clear()
        self.countries = visible
        self._by_code = {country.code: country for country in visible}
        if not visible:
            self.add_row(
                _cell("No countries match", 30, style="italic #9a9aa8"),
                _cell("", 4),
                _cell("", 8),
                key=EMPTY_KEY,
            )
            return
        for country in visible:
            self.add_row(
                _cell(country.name, 30, style="bold #e4e4ec"),
                _cell(country.code, 4, style="#9a9aa8"),
                _cell(
                    format_count(country.station_count),
                    9,
                    style="#b49cf0",
                    justify="right",
                ),
                key=country.code,
            )
        if self.row_count:
            self.move_cursor(row=0, animate=False)

    def country_for_key(self, key: str) -> Country | None:
        return self._by_code.get(key)

    def first_country(self) -> Country | None:
        return self.countries[0] if self.countries else None


class GenresTable(DataTable):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.genres: list[tuple[Genre, int]] = []
        self._by_tag: dict[str, Genre] = {}

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("GENRE", "STATIONS")

    def set_genres(
        self, genres: list[tuple[Genre, int]], filter_text: str = ""
    ) -> None:
        query = filter_text.strip().casefold()
        if query:
            visible = [
                (genre, count)
                for genre, count in genres
                if query in genre.name.casefold() or query in genre.tag
            ]
        else:
            visible = list(genres)
        self.clear()
        self.genres = visible
        self._by_tag = {genre.tag: genre for genre, _ in visible}
        if not visible:
            self.add_row(
                _cell("No genres match", 28, style="italic #9a9aa8"),
                _cell("", 8),
                key=EMPTY_KEY,
            )
            return
        for genre, count in visible:
            self.add_row(
                _cell(genre.name, 28, style="bold #e4e4ec"),
                _cell(
                    format_count(count),
                    8,
                    style="#b49cf0",
                    justify="right",
                ),
                key=genre.tag,
            )
        if self.row_count:
            self.move_cursor(row=0, animate=False)

    def genre_for_key(self, key: str) -> Genre | None:
        return self._by_tag.get(key)

    def first_genre(self) -> Genre | None:
        return self.genres[0][0] if self.genres else None

    def selected_genre(self) -> Genre | None:
        if not self.genres:
            return None
        try:
            row = self.cursor_row
        except Exception:
            return self.genres[0][0]
        if 0 <= row < len(self.genres):
            return self.genres[row][0]
        return None


class CitiesTable(DataTable):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cities: list[tuple[str, int]] = []
        self._keys: dict[str, str] = {}
        self._visible_keys: list[str] = []

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("CITY", "STATIONS")

    def set_cities(
        self, cities: list[tuple[str, int]], total: int, filter_text: str = ""
    ) -> None:
        query = filter_text.strip().casefold()
        if query:
            visible = [
                (city, count)
                for city, count in cities
                if query in (city or "unknown city").casefold()
            ]
        else:
            visible = list(cities)
        self.clear()
        self.cities = visible
        self._keys = {}
        self._visible_keys = []
        if total <= 0:
            self.add_row(
                _cell("No cities found", 32, style="italic #9a9aa8"),
                _cell("", 8),
                key=EMPTY_KEY,
            )
            return
        if not query:
            self._keys[ALL_CITIES_KEY] = ""
            self._visible_keys.append(ALL_CITIES_KEY)
            self.add_row(
                _cell(f"All stations ({format_count(total)})", 32, style="bold #e4e4ec"),
                _cell(format_count(total), 8, style="#b49cf0", justify="right"),
                key=ALL_CITIES_KEY,
            )
        for city, count in visible:
            label = city or "Unknown city"
            key = city or UNKNOWN_CITY_KEY
            self._keys[key] = city
            self._visible_keys.append(key)
            self.add_row(
                _cell(label, 32, style="#e4e4ec"),
                _cell(format_count(count), 8, style="#b49cf0", justify="right"),
                key=key,
            )
        if self.row_count:
            self.move_cursor(row=0, animate=False)

    def city_for_key(self, key: str) -> str | None:
        return self._keys.get(key)

    def first_key(self) -> str | None:
        return self._visible_keys[0] if self._visible_keys else None
