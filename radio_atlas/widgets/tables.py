"""Data tables for countries, cities and stations."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import DataTable

from ..models import Country, Station, format_count

EMPTY_KEY = "__empty__"
ALL_CITIES_KEY = "__all__"
UNKNOWN_CITY_KEY = "__unknown__"


def _cell(value: str, width: int, *, style: str = "", justify: str = "left") -> Text:
    clipped = value if len(value) <= width else value[: max(0, width - 1)] + "…"
    return Text(
        clipped,
        style=style,
        no_wrap=True,
        overflow="ellipsis",
        justify=justify,
    )


class StationsTable(DataTable):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.stations: list[Station] = []
        self._index: dict[str, int] = {}

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("STATION", "PLACE", "TAGS")

    def set_stations(self, stations: list[Station]) -> None:
        self.clear()
        self.stations = list(stations)
        self._index = {station.id: index for index, station in enumerate(self.stations)}
        if not stations:
            self.add_row(
                _cell("No stations here", 34, style="italic #64748b"),
                _cell("", 14),
                _cell("", 16),
                key=EMPTY_KEY,
            )
            return
        for station in stations:
            self.add_row(
                _cell(station.name, 34, style="bold #e2e8f0"),
                _cell(station.place, 14, style="#94a3b8"),
                _cell(station.tagline.replace(" · ", ","), 18, style="#475569"),
                key=station.id,
            )
        if self.row_count:
            self.move_cursor(row=0, animate=False)

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
                _cell("No countries match", 30, style="italic #64748b"),
                _cell("", 4),
                _cell("", 8),
                key=EMPTY_KEY,
            )
            return
        for country in visible:
            self.add_row(
                _cell(country.name, 30, style="bold #e2e8f0"),
                _cell(country.code, 4, style="#64748b"),
                _cell(
                    format_count(country.station_count),
                    9,
                    style="#38bdf8",
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
                _cell("No cities found", 32, style="italic #64748b"),
                _cell("", 8),
                key=EMPTY_KEY,
            )
            return
        if not query:
            self._keys[ALL_CITIES_KEY] = ""
            self._visible_keys.append(ALL_CITIES_KEY)
            self.add_row(
                _cell(f"All stations ({format_count(total)})", 32, style="bold #e2e8f0"),
                _cell(format_count(total), 8, style="#38bdf8", justify="right"),
                key=ALL_CITIES_KEY,
            )
        for city, count in visible:
            label = city or "Unknown city"
            key = city or UNKNOWN_CITY_KEY
            self._keys[key] = city
            self._visible_keys.append(key)
            self.add_row(
                _cell(label, 32, style="#e2e8f0"),
                _cell(format_count(count), 8, style="#38bdf8", justify="right"),
                key=key,
            )
        if self.row_count:
            self.move_cursor(row=0, animate=False)

    def city_for_key(self, key: str) -> str | None:
        return self._keys.get(key)

    def first_key(self) -> str | None:
        return self._visible_keys[0] if self._visible_keys else None
