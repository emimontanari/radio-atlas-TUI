"""Radio Atlas Textual application."""

from __future__ import annotations

import asyncio
from typing import Iterable

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Footer, Input

from .api import CatalogResult, CountriesResult, RadioBrowserClient, TagsResult
from .config import state_path
from .genres import GENRE_BY_TAG, GENRES, Genre
from .geo import GeoIndex, load_geo_index
from .globe import MAX_ZOOM, MIN_ZOOM, GlobeRenderer, wrap_longitude
from .models import Country, Station, format_count, split_tags
from .player import PlayerState, create_player
from .store import Store
from .widgets import (
    AtlasHeader,
    CitiesTable,
    CountriesTable,
    GenresTable,
    GlobeWidget,
    HelpScreen,
    NowPlaying,
    StationsTable,
    StatusBar,
)
from .widgets.tables import ALL_CITIES_KEY, EMPTY_KEY, UNKNOWN_CITY_KEY

MODE_LABELS = {
    "world": "WORLD",
    "favorites": "FAVORITES",
    "recent": "RECENT",
    "search": "SEARCH",
    "countries": "COUNTRIES",
    "genres": "GENRES",
}


class RadioAtlasApp(App):
    TITLE = "Radio Atlas"
    SUB_TITLE = "world radio, one terminal"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("1", "show_world", "World", show=True),
        Binding("2", "show_favorites", "Favs", show=True),
        Binding("3", "show_recent", "Recent", show=True),
        Binding("4", "show_genres", "Genres", show=True),
        Binding("c", "show_countries", "Browse", show=True),
        Binding("slash", "search", "Find", show=True),
        Binding("space", "play_pause", "Play", show=True),
        Binding("r", "random", "Random", show=True),
        Binding("f", "favorite", "Star", show=True),
        Binding("question_mark", "help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("escape", "back", "Back", show=False),
        Binding("s", "stop", "Stop", show=False),
        Binding("n", "next_station", "Next", show=False),
        Binding("p", "previous_station", "Previous", show=False),
        Binding("m", "mute", "Mute", show=False),
        Binding("left_square_bracket", "volume_down", "Volume down", show=False),
        Binding("right_square_bracket", "volume_up", "Volume up", show=False),
        Binding("plus", "zoom_in", "Zoom in", show=False),
        Binding("minus", "zoom_out", "Zoom out", show=False),
        Binding("0", "reset_view", "Reset map", show=False),
        Binding("H", "rotate_west", "Rotate west", show=False),
        Binding("L", "rotate_east", "Rotate east", show=False),
        Binding("J", "tilt_south", "Tilt south", show=False),
        Binding("K", "tilt_north", "Tilt north", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "cursor_left", "Left", show=False),
        Binding("l", "cursor_right", "Right", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("ctrl+d", "half_page_down", "Half page down", show=False),
        Binding("ctrl+u", "half_page_up", "Half page up", show=False),
        Binding("R", "refresh", "Refresh", show=False),
    ]

    def __init__(
        self,
        *,
        client: RadioBrowserClient | None = None,
        store: Store | None = None,
        player=None,
        ascii_globe: bool = False,
        mpv_path: str | None = None,
    ) -> None:
        super().__init__()
        self.geo: GeoIndex = load_geo_index()
        self.renderer = GlobeRenderer(self.geo, ascii_mode=ascii_globe)
        self._owns_client = client is None
        self._owns_player = player is None
        self.client = client or RadioBrowserClient()
        self.store = store or Store(state_path())
        self.player = player or create_player(
            mpv_path=mpv_path,
            on_state=self._on_player_state,
            volume=int(self.store.get("volume", 70)),
            muted=bool(self.store.get("muted", False)),
        )
        if hasattr(self.player, "_on_state"):
            self.player._on_state = self._on_player_state

        self.mode = "world"
        self.catalog: list[Station] = []
        self.catalog_source = "seed"
        self.countries: list[Country] = []
        self.country_stations: list[Station] = []
        self.current_country: Country | None = None
        self.current_city = ""
        self.genres: list[tuple[Genre, int]] = []
        self.genre_stations: list[Station] = []
        self.current_genre: Genre | None = None
        self.domain_stations: list[Station] = []
        self.selected_station: Station | None = None
        self.source = "seed"
        self.offline = True
        self._ui_ready = False
        self._suppress_input = False
        self._search_generation = 0
        self._search_timer = None
        self._search_return_mode = "world"
        self._last_error = ""

    # -- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield AtlasHeader(id="header")
        with Horizontal(id="main"):
            with Vertical(id="left-panel"):
                yield GlobeWidget(self.renderer, id="globe")
                yield NowPlaying(id="now-playing")
            with Vertical(id="side-panel"):
                yield Input(
                    placeholder="Search stations…",
                    id="search-input",
                )
                with Container(id="tables"):
                    yield GenresTable(id="genres-table")
                    yield CountriesTable(id="countries-table")
                    yield CitiesTable(id="cities-table")
                    yield StationsTable(id="stations-table")
        yield StatusBar("Starting Radio Atlas…", id="status-bar")
        yield Footer(show_command_palette=False, compact=True)

    def on_mount(self) -> None:
        self.search_input.display = False
        self._ui_ready = True
        self.catalog = self.client.seed_world()
        self.countries = self.client.seed_countries()
        self.genres = self._genre_counts_from(self.catalog)
        self.catalog_source = "seed"
        self.source = "seed"
        self._populate_stations(self.catalog, focus=True)
        self._sync_all()
        self.run_worker(
            self._bootstrap(), group="bootstrap", exit_on_error=False
        )

    async def on_unmount(self) -> None:
        if self._owns_player:
            try:
                await self.player.close()
            except Exception:
                pass
        if self._owns_client:
            try:
                await self.client.close()
            except Exception:
                pass

    # -- widget access -----------------------------------------------------

    @property
    def search_input(self) -> Input:
        return self.query_one("#search-input", Input)

    @property
    def header(self) -> AtlasHeader:
        return self.query_one(AtlasHeader)

    @property
    def globe(self) -> GlobeWidget:
        return self.query_one(GlobeWidget)

    @property
    def now_playing(self) -> NowPlaying:
        return self.query_one(NowPlaying)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one(StatusBar)

    @property
    def stations_table(self) -> StationsTable:
        return self.query_one(StationsTable)

    @property
    def countries_table(self) -> CountriesTable:
        return self.query_one(CountriesTable)

    @property
    def genres_table(self) -> GenresTable:
        return self.query_one(GenresTable)

    @property
    def cities_table(self) -> CitiesTable:
        return self.query_one(CitiesTable)

    def _active_table(self) -> DataTable:
        if self.mode == "genres":
            return self.genres_table
        if self.mode == "countries":
            return self.countries_table
        if self.mode == "cities":
            return self.cities_table
        return self.stations_table

    # -- boot --------------------------------------------------------------

    async def _bootstrap(self) -> None:
        await asyncio.gather(self._start_player(), self._refresh_world())

    async def _start_player(self) -> None:
        started = await self.player.start()
        if started:
            await self.player.set_volume(int(self.store.get("volume", 70)))
            if self.store.get("muted", False):
                await self.player.toggle_mute()
            self._refresh_player_views()
        else:
            self._set_status(
                "mpv is not installed — browsing works, playback needs mpv",
                "warn",
            )
            self._refresh_player_views()

    async def _refresh_world(self) -> None:
        result = await self.client.world()
        if not self._ui_ready:
            return
        self._apply_catalog(result)

    def _apply_catalog(self, result: CatalogResult) -> None:
        if result.stations:
            self.catalog = result.stations
        self.catalog_source = result.source
        if self.mode != "search":
            self.source = result.source
        self.offline = result.offline
        if self.mode == "world":
            self._populate_stations(self.catalog, focus=False)
        self._sync_all()
        if result.source == "network":
            self._set_status(
                f"{format_count(len(self.catalog))} stations from Radio Browser",
                "good",
            )
        else:
            label = "cached" if result.source == "cache" else "bundled"
            self._set_status(
                f"Radio Browser unavailable — using the {label} catalog",
                "warn",
            )
        if result.error:
            self._last_error = result.error

    # -- views -------------------------------------------------------------

    def _populate_stations(
        self, stations: Iterable[Station], *, focus: bool = False
    ) -> None:
        self.domain_stations = list(stations)
        self.stations_table.set_stations(self.domain_stations)
        self.selected_station = self.stations_table.selected_station()
        self._show_only("stations")
        if focus:
            self.stations_table.focus()
        self._sync_all()

    def _populate_countries(self, filter_text: str = "", *, focus: bool = False) -> None:
        self.countries_table.set_countries(self.countries, filter_text)
        self._show_only("countries")
        if focus:
            self.countries_table.focus()
        self._sync_all()

    @staticmethod
    def _genre_counts_from(stations: Iterable[Station]) -> list[tuple[Genre, int]]:
        counts: dict[str, int] = {}
        for station in stations:
            for tag in split_tags(station.tags):
                counts[tag] = counts.get(tag, 0) + 1
        return [(genre, counts.get(genre.tag, 0)) for genre in GENRES]

    def _populate_genres(self, filter_text: str = "", *, focus: bool = False) -> None:
        self.genres_table.set_genres(self.genres, filter_text)
        self._show_only("genres")
        if focus:
            self.genres_table.focus()
        self._sync_all()

    def _populate_cities(self, filter_text: str = "", *, focus: bool = False) -> None:
        counts: dict[str, int] = {}
        for station in self.country_stations:
            key = station.state.strip()
            counts[key] = counts.get(key, 0) + 1
        cities = sorted(
            ((city, count) for city, count in counts.items() if city),
            key=lambda item: (-item[1], item[0]),
        )
        if "" in counts:
            cities.append(("", counts[""]))
        self.cities_table.set_cities(cities, len(self.country_stations), filter_text)
        self._show_only("cities")
        if focus:
            self.cities_table.focus()
        self._sync_all()

    def _show_only(self, wanted: str) -> None:
        for name, table in (
            ("genres", self.genres_table),
            ("countries", self.countries_table),
            ("cities", self.cities_table),
            ("stations", self.stations_table),
        ):
            table.display = name == wanted

    def _sync_all(self) -> None:
        if not self._ui_ready:
            return
        self._sync_header()
        self._sync_globe()
        self._refresh_player_views()

    def _sync_header(self) -> None:
        unit = "STATIONS"
        if self.mode == "genres":
            label = "GENRES"
            count = len(self.genres_table.genres)
            unit = "GENRE" if count == 1 else "GENRES"
        elif self.mode == "countries":
            label = "COUNTRIES"
            count = len(self.countries_table.countries)
            unit = "COUNTRY" if count == 1 else "COUNTRIES"
        elif self.mode == "cities":
            label = (
                f"CITIES · {self.current_country.name.upper()}"
                if self.current_country
                else "CITIES"
            )
            count = len(self.country_stations)
        elif self.mode == "stations":
            if self.current_genre is not None:
                label = f"GENRE · {self.current_genre.name.upper()}"
            else:
                country = (
                    self.current_country.name.upper()
                    if self.current_country
                    else "STATIONS"
                )
                label = (
                    f"{country} · {self.current_city.upper()}"
                    if self.current_city
                    else country
                )
            count = len(self.domain_stations)
        else:
            label = MODE_LABELS.get(self.mode, self.mode.upper())
            count = len(self.domain_stations)
        self.header.update_header(
            mode_label=label, count=count, source=self.source, unit=unit
        )

    def _globe_stations(self) -> list[Station]:
        if self.mode in ("world", "countries", "genres"):
            stations = list(self.catalog)
        elif self.mode == "favorites":
            stations = list(self.store.favorites)
        elif self.mode == "recent":
            stations = [entry.station for entry in self.store.history]
        elif self.mode == "cities":
            stations = list(self.country_stations)
        elif self.mode == "stations":
            stations = (
                list(self.domain_stations)
                if self.current_genre is not None
                else list(self.country_stations)
            )
        else:
            stations = list(self.domain_stations)
        playing = self.player.state.station
        if playing is not None and all(s.id != playing.id for s in stations):
            stations.append(playing)
        return stations

    def _sync_globe(self) -> None:
        if not self._ui_ready:
            return
        state = self.player.state
        playing_id = (
            state.station.id
            if state.station is not None and state.status in ("playing", "paused")
            else None
        )
        selected = self._current_station()
        self.globe.configure(
            stations=self._globe_stations(),
            selected_id=selected.id if selected else None,
            playing_id=playing_id,
            favorite_ids=self.store.favorite_ids,
        )

    def _refresh_player_views(self) -> None:
        if not self._ui_ready:
            return
        self.now_playing.update_view(
            self.player.state,
            selected=self._current_station(),
            source=self.source,
        )
        self._sync_globe()

    def _current_station(self) -> Station | None:
        if self.mode in ("world", "favorites", "recent", "search", "stations"):
            return self.stations_table.selected_station() or self.selected_station
        return self.player.state.station

    def _set_status(self, message: str, tone: str = "info") -> None:
        if self._ui_ready:
            self.status_bar.set_message(message, tone)

    def _on_player_state(self, state: PlayerState) -> None:
        if state.error:
            self._last_error = state.error
        if self._ui_ready:
            self.call_later(self._refresh_player_views)
            if state.status in ("error", "unavailable") and state.error:
                self.call_later(self._set_status, state.error, "error")

    # -- search ------------------------------------------------------------

    def action_search(self) -> None:
        if self.search_input.display:
            self.search_input.focus()
            return
        self._search_return_mode = self.mode if self.mode != "search" else "search"
        self._search_generation += 1
        self._suppress_input = True
        self.search_input.value = ""
        self._suppress_input = False
        self.search_input.placeholder = self._search_placeholder()
        self.search_input.display = True
        self.search_input.focus()
        self._set_status("Type to search · enter opens the first result · esc cancels")

    def _search_placeholder(self) -> str:
        if self._search_return_mode == "genres":
            return "Filter genres…"
        if self._search_return_mode == "countries":
            return "Filter countries…"
        if self._search_return_mode == "cities":
            return "Filter cities…"
        return "Search stations by name, tag or country…"

    @on(Input.Changed, "#search-input")
    def _search_changed(self, event: Input.Changed) -> None:
        if self._suppress_input or not self.search_input.display:
            return
        value = event.value.strip()
        if self._search_return_mode == "genres":
            self._populate_genres(value)
            self._set_status(f"{len(self.genres_table.genres)} genres", "info")
            return
        if self._search_return_mode == "countries":
            self._populate_countries(value)
            self._set_status(f"{len(self.countries_table.countries)} countries", "info")
            return
        if self._search_return_mode == "cities":
            self._populate_cities(value)
            self._set_status(f"{self.cities_table.row_count} cities", "info")
            return
        self._search_generation += 1
        generation = self._search_generation
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None
        if not value:
            self._set_status("Type to search stations", "info")
            return
        self._search_timer = self.set_timer(
            0.35, lambda: self._launch_search(value, generation)
        )

    def _launch_search(self, query: str, generation: int) -> None:
        if (
            generation != self._search_generation
            or not self.search_input.display
            or self.search_input.value.strip() != query
        ):
            return
        self.run_worker(
            self._search(query, generation),
            group="search",
            exclusive=True,
            exit_on_error=False,
        )

    async def _search(self, query: str, generation: int) -> None:
        result = await self.client.search(query)
        if (
            generation != self._search_generation
            or self.search_input.value.strip() != query
        ):
            return
        self.mode = "search"
        self.source = result.source
        self.offline = result.offline
        self._populate_stations(result.stations, focus=False)
        self._sync_all()
        suffix = " · offline catalog" if result.offline else ""
        self._set_status(
            f'{format_count(len(result.stations))} results for "{query}"{suffix}',
            "warn" if result.offline else "good",
        )

    @on(Input.Submitted, "#search-input")
    def _search_submitted(self) -> None:
        mode = self._search_return_mode
        if mode == "genres":
            genre = self.genres_table.first_genre()
            self._hide_search()
            if genre is not None:
                self.run_worker(
                    self._open_genre(genre.tag),
                    group="genre",
                    exclusive=True,
                    exit_on_error=False,
                )
            return
        if mode == "countries":
            country = self.countries_table.first_country()
            self._hide_search()
            if country is not None:
                self.run_worker(
                    self._open_country(country.code),
                    group="country",
                    exclusive=True,
                    exit_on_error=False,
                )
            return
        if mode == "cities":
            key = self.cities_table.first_key()
            self._hide_search()
            if key is not None:
                self._open_city(key)
            return
        station = self.stations_table.selected_station()
        self._hide_search()
        if station is not None:
            self.run_worker(
                self._play(station), group="player", exclusive=True, exit_on_error=False
            )

    def _hide_search(self, *, restore: bool = False) -> None:
        if self.search_input.display:
            self._search_generation += 1
            self._suppress_input = True
            self.search_input.value = ""
            self._suppress_input = False
            self.search_input.display = False
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None
        if restore:
            self._restore_view()
        else:
            self._active_table().focus()

    def _restore_view(self) -> None:
        mode = self._search_return_mode
        if mode == "genres":
            self.mode = "genres"
            self._populate_genres(focus=True)
        elif mode == "countries":
            self.mode = "countries"
            self._populate_countries(focus=True)
        elif mode == "cities":
            self.mode = "cities"
            self._populate_cities(focus=True)
        elif mode == "favorites":
            self.action_show_favorites()
        elif mode == "recent":
            self.action_show_recent()
        elif mode == "stations":
            self.mode = "stations"
            self._populate_stations(self.country_stations, focus=True)
        elif mode == "search":
            self.mode = "search"
            self.stations_table.focus()
        else:
            self.action_show_world()

    # -- actions -----------------------------------------------------------

    def _typing(self) -> bool:
        return self.search_input.display and self.search_input.has_focus

    def action_show_world(self) -> None:
        if self._typing():
            return
        self._hide_search()
        self.mode = "world"
        self.current_country = None
        self.current_city = ""
        self.current_genre = None
        self.source = self.catalog_source
        self._populate_stations(self.catalog, focus=True)

    def action_show_favorites(self) -> None:
        if self._typing():
            return
        self._hide_search()
        self.mode = "favorites"
        self.current_country = None
        self.current_genre = None
        self._populate_stations(self.store.favorites, focus=True)
        if not self.store.favorites:
            self._set_status("No favorites yet — press f on a station", "info")

    def action_show_recent(self) -> None:
        if self._typing():
            return
        self._hide_search()
        self.mode = "recent"
        self.current_country = None
        self.current_genre = None
        stations = [entry.station for entry in self.store.history]
        self._populate_stations(stations, focus=True)
        if not stations:
            self._set_status("No listening history yet", "info")

    def action_show_genres(self) -> None:
        if self._typing():
            return
        self._hide_search()
        self.mode = "genres"
        self.current_genre = None
        self.current_country = None
        self.current_city = ""
        self._populate_genres(focus=True)
        self.run_worker(
            self._refresh_genres(),
            group="genres",
            exclusive=True,
            exit_on_error=False,
        )

    async def _refresh_genres(self) -> None:
        result = await self.client.tags()
        if not self._ui_ready:
            return
        counts = {tag.casefold(): count for tag, count in result.tags}
        self.genres = [
            (genre, counts.get(genre.tag.casefold(), 0)) for genre in GENRES
        ]
        if result.source == "network":
            self.source = "network"
            self.offline = False
        if self.mode == "genres":
            filter_text = (
                self.search_input.value if self.search_input.display else ""
            )
            self._populate_genres(filter_text, focus=False)
        self._sync_header()
        if result.offline:
            self._set_status(
                "Genre counts are offline — using the local catalog", "warn"
            )

    async def _open_genre(self, tag: str) -> None:
        genre = GENRE_BY_TAG.get(tag.strip().casefold())
        if genre is None:
            return
        self.current_genre = genre
        self.current_country = None
        self.current_city = ""
        self.mode = "stations"
        self._hide_search()
        self.genre_stations = self._stations_for_genre(genre.tag)
        self._populate_stations(self.genre_stations, focus=True)
        self._set_status(f"Loading {genre.name}…", "info")
        result = await self.client.by_tag(genre.tag)
        if self.current_genre is None or self.current_genre.tag != genre.tag:
            return
        if result.stations:
            self.genre_stations = result.stations
        if result.source == "network":
            self.source = "network"
            self.offline = False
        if self.mode == "stations":
            self._populate_stations(self.genre_stations, focus=False)
        self._sync_header()
        if result.stations:
            self._set_status(
                f"{genre.name} · {format_count(len(result.stations))} stations",
                "good" if result.source == "network" else "warn",
            )
        else:
            self._set_status(
                f"No stations found for {genre.name}"
                + (" (offline catalog)" if result.offline else ""),
                "warn",
            )

    def _stations_for_genre(self, tag: str) -> list[Station]:
        stations: dict[str, Station] = {
            station.id: station
            for station in self.catalog
            if tag in split_tags(station.tags)
        }
        for station in self.client.seed_stations():
            if tag in split_tags(station.tags):
                stations.setdefault(station.id, station)
        return sorted(
            stations.values(), key=lambda s: (s.votes, s.clicks), reverse=True
        )

    def action_show_countries(self) -> None:
        if self._typing():
            return
        self._hide_search()
        self.mode = "countries"
        self.current_country = None
        self.current_genre = None
        self._populate_countries(focus=True)
        self.run_worker(
            self._refresh_countries(),
            group="countries",
            exclusive=True,
            exit_on_error=False,
        )

    async def _refresh_countries(self) -> None:
        result = await self.client.countries()
        if not self._ui_ready:
            return
        if result.countries:
            self.countries = result.countries
        if result.source == "network":
            self.source = "network"
            self.offline = False
        if self.mode == "countries":
            filter_text = (
                self.search_input.value if self.search_input.display else ""
            )
            self._populate_countries(filter_text, focus=False)
        self._sync_header()
        if result.offline:
            self._set_status("Country list is offline — using the local catalog", "warn")

    async def _open_country(self, code: str) -> None:
        code = code.strip().upper()
        country = next(
            (item for item in self.countries if item.code == code), None
        ) or self.geo.country_by_code(code)
        if country is None:
            return
        self.current_country = country
        self.current_city = ""
        self.current_genre = None
        self.mode = "cities"
        self._hide_search()
        self.country_stations = self._stations_for_country(code)
        self._center_on_country(country)
        self._populate_cities(focus=True)
        self._set_status(f"Loading {country.name}…", "info")
        result = await self.client.by_country(code)
        if self.current_country is None or self.current_country.code != code:
            return
        if result.stations:
            self.country_stations = result.stations
        if result.source == "network":
            self.source = "network"
            self.offline = False
        if self.mode == "cities":
            self._populate_cities()
        self._sync_globe()
        self._sync_header()
        if result.stations:
            self._set_status(
                f"{country.name} · {format_count(len(result.stations))} stations",
                "good" if result.source == "network" else "warn",
            )
        else:
            self._set_status(
                f"No stations found for {country.name}"
                + (" (offline catalog)" if result.offline else ""),
                "warn",
            )

    def _stations_for_country(self, code: str) -> list[Station]:
        stations: dict[str, Station] = {
            station.id: station
            for station in self.catalog
            if station.country_code == code
        }
        for station in self.client.seed_stations():
            if station.country_code == code:
                stations.setdefault(station.id, station)
        return list(stations.values())

    def _open_city(self, key: str) -> None:
        if key == EMPTY_KEY:
            return
        if key == ALL_CITIES_KEY:
            stations = list(self.country_stations)
            label = "All stations"
            city = ""
        elif key == UNKNOWN_CITY_KEY:
            stations = [s for s in self.country_stations if not s.state.strip()]
            label = "Unknown city"
            city = ""
        else:
            city = self.cities_table.city_for_key(key) or ""
            stations = [s for s in self.country_stations if s.state == city]
            label = city
        self.current_city = city
        self.mode = "stations"
        self._populate_stations(stations, focus=True)
        country = self.current_country.name if self.current_country else "country"
        self._set_status(f"{label} · {country} · {len(stations)} stations", "info")

    @on(DataTable.RowSelected)
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if not isinstance(key, str) or key == EMPTY_KEY:
            return
        table = event.data_table
        if table.id == "genres-table":
            genre = self.genres_table.genre_for_key(key)
            if genre is not None:
                self.run_worker(
                    self._open_genre(genre.tag),
                    group="genre",
                    exclusive=True,
                    exit_on_error=False,
                )
        elif table.id == "countries-table":
            self.run_worker(
                self._open_country(key),
                group="country",
                exclusive=True,
                exit_on_error=False,
            )
        elif table.id == "cities-table":
            self._open_city(key)
        elif table.id == "stations-table":
            station = self.stations_table.station_for_key(key)
            if station is not None:
                self.run_worker(
                    self._play(station),
                    group="player",
                    exclusive=True,
                    exit_on_error=False,
                )

    @on(DataTable.RowHighlighted)
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if not isinstance(key, str) or key == EMPTY_KEY:
            return
        if event.data_table.id == "stations-table":
            station = self.stations_table.station_for_key(key)
            if station is not None:
                self.selected_station = station
                self._sync_globe()
                self._refresh_player_views()
        elif event.data_table.id == "countries-table":
            country = self.countries_table.country_for_key(key)
            if country is not None:
                self._center_on_country(country)

    @on(GlobeWidget.StationActivated)
    def _globe_station(self, message: GlobeWidget.StationActivated) -> None:
        self.selected_station = message.station
        self.run_worker(
            self._play(message.station),
            group="player",
            exclusive=True,
            exit_on_error=False,
        )

    @on(GlobeWidget.CountryActivated)
    def _globe_country(self, message: GlobeWidget.CountryActivated) -> None:
        self.run_worker(
            self._open_country(message.country.code),
            group="country",
            exclusive=True,
            exit_on_error=False,
        )

    # -- playback ----------------------------------------------------------

    async def _play(self, station: Station) -> None:
        ok = await self.player.play(station)
        self._refresh_player_views()
        if not ok:
            error = self.player.state.error or "Could not start playback"
            self._set_status(error, "error")
            return
        self.selected_station = station
        self.store.record_play(station)
        if self.mode in ("world", "favorites", "recent", "search", "stations"):
            self.stations_table.select_station(station.id)
        self._center_on_station(station)
        self._sync_all()
        if self.mode == "recent":
            self._populate_stations(
                [entry.station for entry in self.store.history], focus=False
            )
        self._set_status(f"Playing {station.name}", "good")
        self.run_worker(
            self.client.register_click(station.id),
            group="click",
            exit_on_error=False,
        )

    async def _toggle_pause(self) -> None:
        paused = await self.player.toggle_pause()
        self._refresh_player_views()
        if self.player.state.station is None:
            self._set_status("Nothing playing yet", "warn")
        elif paused:
            self._set_status("Paused", "info")
        else:
            self._set_status("Playing", "good")

    async def _stop(self) -> None:
        if await self.player.stop():
            self._refresh_player_views()
            self._set_status("Stopped", "info")

    async def _random_station(self) -> None:
        genre = self.current_genre
        if genre is None and self.mode == "genres":
            genre = self.genres_table.selected_genre()
        tag = genre.tag if genre is not None else None
        station = await self.client.random_station(
            excluded_ids=self.store.recent_ids(20), tag=tag
        )
        if station is None:
            label = f" for {genre.name}" if genre is not None else ""
            self._set_status(
                f"No station available{label} for random tuning", "warn"
            )
            return
        if all(item.id != station.id for item in self.catalog):
            self.catalog.insert(0, station)
        await self._play(station)

    async def _change_volume(self, delta: int) -> None:
        volume = await self.player.set_volume(self.player.state.volume + delta)
        self.store.set("volume", volume)
        self._refresh_player_views()
        self._set_status(f"Volume {volume}%", "info")

    async def _mute(self) -> None:
        muted = await self.player.toggle_mute()
        self.store.set("muted", muted)
        self._refresh_player_views()
        self._set_status("Muted" if muted else "Sound on", "info")

    def _play_selected(self) -> None:
        station = self._current_station()
        if station is None:
            self._set_status("Select a station first", "warn")
            return
        self.run_worker(
            self._play(station), group="player", exclusive=True, exit_on_error=False
        )

    def action_play_pause(self) -> None:
        if self._typing():
            return
        if self.player.state.status in ("playing", "paused"):
            self.run_worker(
                self._toggle_pause(), group="player", exclusive=True, exit_on_error=False
            )
        else:
            self._play_selected()

    def action_stop(self) -> None:
        if self._typing():
            return
        self.run_worker(
            self._stop(), group="player", exclusive=True, exit_on_error=False
        )

    def action_next_station(self) -> None:
        self._step_station(1)

    def action_previous_station(self) -> None:
        self._step_station(-1)

    def _step_station(self, direction: int) -> None:
        if self._typing():
            return
        stations = self.domain_stations or self.catalog
        if not stations:
            self._set_status("No stations to step through", "warn")
            return
        current = self._current_station()
        index = -1
        if current is not None:
            for position, station in enumerate(stations):
                if station.id == current.id:
                    index = position
                    break
        station = stations[(index + direction) % len(stations)]
        self.run_worker(
            self._play(station), group="player", exclusive=True, exit_on_error=False
        )

    def action_random(self) -> None:
        if self._typing():
            return
        self.run_worker(
            self._random_station(), group="player", exclusive=True, exit_on_error=False
        )

    def action_favorite(self) -> None:
        if self._typing():
            return
        station = self._current_station()
        if station is None:
            self._set_status("Select a station to favorite", "warn")
            return
        added = self.store.toggle_favorite(station)
        self._sync_globe()
        if self.mode == "favorites":
            self._populate_stations(self.store.favorites, focus=False)
        self._refresh_player_views()
        self._set_status(
            f"{'Added' if added else 'Removed'} {station.name} "
            f"{'to' if added else 'from'} favorites",
            "good" if added else "info",
        )

    def action_volume_up(self) -> None:
        if self._typing():
            return
        self.run_worker(self._change_volume(5), group="player", exit_on_error=False)

    def action_volume_down(self) -> None:
        if self._typing():
            return
        self.run_worker(self._change_volume(-5), group="player", exit_on_error=False)

    def action_mute(self) -> None:
        if self._typing():
            return
        self.run_worker(self._mute(), group="player", exit_on_error=False)

    # -- map ---------------------------------------------------------------

    def _center_on_country(self, country: Country) -> None:
        if country.latitude is None or country.longitude is None:
            return
        self.globe.configure(
            center_latitude=country.latitude,
            center_longitude=country.longitude,
            zoom=max(self.globe.zoom, 1.7),
        )

    def _center_on_station(self, station: Station) -> None:
        if not station.has_location:
            return
        self.globe.configure(
            center_latitude=station.latitude,
            center_longitude=station.longitude,
        )

    def action_zoom_in(self) -> None:
        self.globe.configure(zoom=min(MAX_ZOOM, self.globe.zoom + 0.25))
        self._set_status(f"Zoom {self.globe.zoom:.2f}×", "info")

    def action_zoom_out(self) -> None:
        self.globe.configure(zoom=max(MIN_ZOOM, self.globe.zoom - 0.25))
        self._set_status(f"Zoom {self.globe.zoom:.2f}×", "info")

    def action_reset_view(self) -> None:
        self.globe.configure(center_latitude=20.0, center_longitude=0.0, zoom=1.0)
        self._set_status("Map reset", "info")

    def action_rotate_west(self) -> None:
        self.globe.configure(
            center_longitude=wrap_longitude(self.globe.center_longitude - 10)
        )

    def action_rotate_east(self) -> None:
        self.globe.configure(
            center_longitude=wrap_longitude(self.globe.center_longitude + 10)
        )

    def action_tilt_north(self) -> None:
        self.globe.configure(
            center_latitude=max(-78.0, self.globe.center_latitude - 8)
        )

    def action_tilt_south(self) -> None:
        self.globe.configure(
            center_latitude=min(78.0, self.globe.center_latitude + 8)
        )

    # -- list navigation ---------------------------------------------------

    def _table_action(self, action: str) -> None:
        if self._typing():
            return
        table = self._active_table()
        method = getattr(table, action, None)
        if callable(method):
            method()

    def action_cursor_down(self) -> None:
        self._table_action("action_cursor_down")

    def action_cursor_up(self) -> None:
        self._table_action("action_cursor_up")

    def action_cursor_left(self) -> None:
        self._table_action("action_cursor_left")

    def action_cursor_right(self) -> None:
        self._table_action("action_cursor_right")

    def action_cursor_top(self) -> None:
        if self._typing():
            return
        table = self._active_table()
        table.move_cursor(row=0, animate=False)

    def action_cursor_bottom(self) -> None:
        if self._typing():
            return
        table = self._active_table()
        if table.row_count:
            table.move_cursor(row=table.row_count - 1, animate=False)

    def action_half_page_down(self) -> None:
        self._table_action("action_page_down")

    def action_half_page_up(self) -> None:
        self._table_action("action_page_up")

    # -- misc --------------------------------------------------------------

    def action_help(self) -> None:
        if self._typing():
            return
        self.push_screen(HelpScreen())

    def action_refresh(self) -> None:
        if self._typing():
            return
        self.client.reset_offline()
        self._set_status("Refreshing Radio Browser…", "info")
        self.run_worker(
            self._refresh_world(), group="catalog", exclusive=True, exit_on_error=False
        )
        if self.mode == "genres":
            self.run_worker(
                self._refresh_genres(),
                group="genres",
                exclusive=True,
                exit_on_error=False,
            )
        elif self.current_genre is not None and self.mode == "stations":
            tag = self.current_genre.tag
            self.run_worker(
                self._open_genre(tag),
                group="genre",
                exclusive=True,
                exit_on_error=False,
            )
        elif self.mode == "countries":
            self.run_worker(
                self._refresh_countries(),
                group="countries",
                exclusive=True,
                exit_on_error=False,
            )
        elif self.current_country is not None and self.mode in ("cities", "stations"):
            code = self.current_country.code
            self.run_worker(
                self._open_country(code),
                group="country",
                exclusive=True,
                exit_on_error=False,
            )

    def action_back(self) -> None:
        if self.search_input.display:
            self._hide_search(restore=True)
            return
        if self.mode == "stations":
            if self.current_genre is not None:
                self.mode = "genres"
                self.current_genre = None
                self._populate_genres(focus=True)
            else:
                self.mode = "cities"
                self._populate_cities(focus=True)
        elif self.mode == "cities":
            self.mode = "countries"
            self.current_country = None
            self._populate_countries(focus=True)
        elif self.mode in ("genres", "countries", "favorites", "recent", "search"):
            self.action_show_world()
