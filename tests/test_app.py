"""Textual application behavior with injected data sources."""

from __future__ import annotations

import pytest

from radio_atlas.api import CatalogResult, CountriesResult
from radio_atlas.app import RadioAtlasApp
from radio_atlas.models import Country, Station
from radio_atlas.player import PlayerState
from radio_atlas.store import Store
from radio_atlas.widgets import HelpScreen
from radio_atlas.widgets.tables import EMPTY_KEY


def make_station(uuid: str, name: str, *, code: str = "US", state: str = "New York") -> Station:
    return Station(
        id=uuid,
        name=name,
        url=f"https://stream.example/{uuid}",
        country="United States",
        country_code=code,
        state=state,
        tags="jazz,smooth",
        codec="MP3",
        bitrate=128,
        votes=10,
        latitude=40.7,
        longitude=-74.0,
    )


class FakeClient:
    def __init__(self) -> None:
        self.stations = [
            make_station("us1", "Jazz FM"),
            make_station("us2", "Night Talk", state="Chicago"),
            make_station("fr1", "Radio France", code="FR", state="Paris"),
        ]
        self.countries = [
            Country(
                code="US",
                name="United States",
                continent="North America",
                latitude=39.8,
                longitude=-98.6,
                station_count=2,
            ),
            Country(
                code="FR",
                name="France",
                continent="Europe",
                latitude=46.2,
                longitude=2.2,
                station_count=1,
            ),
        ]
        self.search_calls: list[str] = []
        self.search_results = [make_station("us1", "Jazz FM")]
        self.closed = False

    def seed_world(self, limit: int = 500):
        return list(self.stations)

    def seed_stations(self):
        return list(self.stations)

    def seed_countries(self):
        return list(self.countries)

    async def world(self, limit: int = 500):
        return CatalogResult(list(self.stations), "seed", offline=True)

    async def countries(self):
        return CountriesResult(list(self.countries), "seed", offline=True)

    async def by_country(self, code: str, limit: int = 300):
        return CatalogResult(
            [s for s in self.stations if s.country_code == code], "seed", offline=True
        )

    async def search(self, query: str, limit: int = 120):
        self.search_calls.append(query)
        return CatalogResult(list(self.search_results), "seed", offline=True)

    async def random_station(self, *, excluded_ids=(), limit: int = 120):
        return self.stations[0]

    async def register_click(self, station_id: str) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    def reset_offline(self) -> None:
        return None


class FakePlayer:
    def __init__(self) -> None:
        self.available = True
        self.state = PlayerState()
        self.plays: list[str] = []

    async def start(self) -> bool:
        return True

    async def play(self, station: Station) -> bool:
        self.plays.append(station.id)
        self.state = PlayerState(
            status="playing", station=station, volume=self.state.volume
        )
        return True

    async def toggle_pause(self) -> bool:
        if self.state.status == "playing":
            self.state = PlayerState(
                status="paused",
                station=self.state.station,
                volume=self.state.volume,
            )
            return True
        self.state = PlayerState(
            status="playing", station=self.state.station, volume=self.state.volume
        )
        return False

    async def stop(self) -> bool:
        self.state = PlayerState(volume=self.state.volume)
        return True

    async def set_volume(self, value: int) -> int:
        self.state = PlayerState(
            status=self.state.status,
            station=self.state.station,
            volume=max(0, min(100, value)),
        )
        return self.state.volume

    async def toggle_mute(self) -> bool:
        self.state = PlayerState(
            status=self.state.status,
            station=self.state.station,
            volume=self.state.volume,
            muted=not self.state.muted,
        )
        return self.state.muted

    async def close(self) -> None:
        return None


def make_app(tmp_path) -> RadioAtlasApp:
    return RadioAtlasApp(
        client=FakeClient(),
        store=Store(tmp_path / "state.json"),
        player=FakePlayer(),
    )


async def test_world_view_starts_with_seed_catalog(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        assert app.mode == "world"
        assert app.stations_table.row_count == 3
        assert app.stations_table.selected_station() is not None
        assert app.globe._frame is not None
        assert app.globe._frame.width > 0
        assert "SEED" in str(app.header.render())


async def test_browse_country_then_city_then_play(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("c")
        await pilot.pause(0.1)
        assert app.mode == "countries"
        assert app.countries_table.row_count == 2

        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app.mode == "cities"
        assert app.current_country is not None
        assert app.current_country.code == "US"
        assert app.cities_table.row_count >= 2

        # First city row is "All stations".
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app.mode == "stations"
        assert app.stations_table.row_count == 2

        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app.player.state.status == "playing"
        assert app.player.state.station.id == "us1"
        assert app.store.history[0].station.id == "us1"

        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.mode == "cities"
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.mode == "countries"
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.mode == "world"


async def test_search_debounces_and_escape_restores_world(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("slash")
        await pilot.pause(0.05)
        assert app.search_input.display is True
        assert app.search_input.has_focus

        for key in ("j", "a", "z", "z"):
            await pilot.press(key)
        await pilot.pause(0.55)
        assert app.client.search_calls
        assert app.mode == "search"
        assert app.stations_table.row_count == 1
        assert app.stations_table.selected_station().name == "Jazz FM"

        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.search_input.display is False
        assert app.mode == "world"
        assert app.stations_table.row_count == 3


async def test_favorites_toggle_appears_in_favorites_view(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.05)
        await pilot.press("f")
        await pilot.pause(0.05)
        assert len(app.store.favorites) == 1
        assert app.store.favorites[0].id == "us1"

        await pilot.press("2")
        await pilot.pause(0.05)
        assert app.mode == "favorites"
        assert app.stations_table.row_count == 1

        await pilot.press("f")
        await pilot.pause(0.05)
        assert app.store.favorites == []
        assert app.stations_table.row_count == 1
        assert app.stations_table.ordered_rows[0].key.value == EMPTY_KEY


async def test_play_pause_and_mute(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.05)
        await pilot.press("space")
        await pilot.pause(0.05)
        assert app.player.state.status == "playing"
        await pilot.press("space")
        await pilot.pause(0.05)
        assert app.player.state.status == "paused"
        await pilot.press("m")
        await pilot.pause(0.05)
        assert app.player.state.muted is True

        await pilot.press("s")
        await pilot.pause(0.05)
        assert app.player.state.status == "stopped"


async def test_help_modal_opens_and_closes(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause(0.05)
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert not isinstance(app.screen, HelpScreen)


async def test_typing_does_not_trigger_app_shortcuts(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("slash")
        for key in ("q", "j", "1"):
            await pilot.press(key)
        await pilot.pause(0.05)
        assert app.search_input.value == "qj1"
        assert app.mode == "world"
        await pilot.press("escape")


async def test_narrow_terminal_still_renders(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause(0.1)
        assert app.globe._frame is not None
        assert app.globe._frame.width > 0
        assert app.stations_table.row_count == 3
