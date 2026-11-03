"""Textual application behavior with injected data sources."""

from __future__ import annotations

import re
from typing import cast

import pytest
from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual.widgets import Button

from radio_atlas.api import (
    CatalogResult,
    CountriesResult,
    RadioBrowserClient,
    TagsResult,
)
from radio_atlas.app import RadioAtlasApp
from radio_atlas.genres import GENRES
from radio_atlas.models import Country, Station
from radio_atlas.player import PlayerState
from radio_atlas.store import Store
from radio_atlas.widgets import HelpScreen
from radio_atlas.widgets.tables import EMPTY_KEY, StationsTable


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
        self.country_data = [
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
        self.by_tag_calls: list[str] = []
        self.random_tags: list[str | None] = []
        self.closed = False

    def seed_world(self, limit: int = 500):
        return list(self.stations)

    def seed_stations(self):
        return list(self.stations)

    def seed_countries(self):
        return list(self.country_data)

    async def world(self, limit: int = 500):
        return CatalogResult(list(self.stations), "seed", offline=True)

    async def countries(self):
        return CountriesResult(list(self.country_data), "seed", offline=True)

    async def tags(self):
        return TagsResult([("jazz", 3), ("rock", 2)], "seed", offline=True)

    async def by_tag(self, tag: str, limit: int = 300):
        self.by_tag_calls.append(tag)
        return CatalogResult(
            [s for s in self.stations if tag in s.tags], "seed", offline=True
        )

    async def by_country(self, code: str, limit: int = 300):
        return CatalogResult(
            [s for s in self.stations if s.country_code == code], "seed", offline=True
        )

    async def search(self, query: str, limit: int = 120):
        self.search_calls.append(query)
        return CatalogResult(list(self.search_results), "seed", offline=True)

    async def random_station(
        self, *, excluded_ids=(), limit: int = 120, tag: str | None = None
    ):
        self.random_tags.append(tag)
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


def make_app(tmp_path, **kwargs) -> RadioAtlasApp:
    return RadioAtlasApp(
        client=cast(RadioBrowserClient, FakeClient()),
        store=Store(tmp_path / "state.json"),
        player=FakePlayer(),
        **kwargs,
    )


@pytest.mark.parametrize("size", [(120, 40), (80, 24)])
async def test_reference_layout_keeps_globe_left_and_player_right(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        side = app.query_one("#side-panel")
        assert app.globe.region.right <= side.region.x
        assert app.now_playing.region.x >= side.region.x
        assert app.now_playing.region.bottom <= size[1]
        assert app.globe.region.height > app.now_playing.region.height * 2
        assert app.query_one("#search-trigger").region.y < app.globe.region.y
        assert app.query_one("#navigation").region.y < app.stations_table.region.y
        assert app.query_one("#transport").region.y >= app.now_playing.region.bottom
        assert app.screen.styles.background.hex.lower() == "#0c0c15"
        assert not app.stations_table.show_header
        assert app.stations_table.get_row_at(0)[1].plain == "Jazz FM\nUS · MP3 · 128 kbps"


@pytest.mark.parametrize("size", [(120, 40), (80, 24)])
async def test_reference_render_discloses_source_metadata_errors_and_controls(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)

        def screen_text():
            return "\n".join(
                "".join(segment.text for segment in line)
                for line in app.screen._compositor.render_full_update().strips
            )

        rendered = screen_text()
        assert "SEED OFFLINE" in rendered
        assert "US · MP3 · 128 kbps" in rendered
        for selector in (
            "#nav-world", "#nav-favorites", "#nav-recent", "#search-trigger",
            "#control-previous", "#control-play", "#control-next", "#control-stop",
            "#control-mute", "#volume-bar", "#player-favorite",
        ):
            region = app.query_one(selector).region
            assert region.width > 0 and region.height > 0
            assert 0 <= region.x < region.right <= size[0]
            assert 0 <= region.y < region.bottom <= size[1]

        app.player.state = PlayerState(
            status="error", station=app.catalog[0], title="Offline track",
            artist="Test artist", error="Stream unavailable", volume=70,
        )
        app._on_player_state(app.player.state)
        await pilot.pause(0.1)
        rendered = screen_text()
        assert "Test artist — Offline track" in rendered
        assert rendered.count("Stream unavailable") == 2
        assert "SEED OFFLINE" in rendered


async def test_reference_controls_use_existing_terminal_actions(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.click("#nav-favorites")
        assert app.mode == "favorites"
        await pilot.click("#nav-world")
        assert app.mode == "world"
        await pilot.click("#control-play")
        await pilot.pause(0.1)
        assert app.player.state.status == "playing"
        await pilot.click("#control-play")
        await pilot.pause(0.1)
        assert app.player.state.status == "paused"
        await pilot.click("#control-stop")
        await pilot.pause(0.1)
        assert app.player.state.status == "stopped"
        await pilot.click("#search-trigger")
        assert app.search_input.has_focus
        await pilot.press("j", "a", "z", "z")
        await pilot.pause(0.55)
        assert app.mode == "search"
        await pilot.press("escape")
        assert app.mode == "world"
        assert app.query_one("#search-trigger").display


def rendered_screen_lines(app):
    """Inspect actual terminal cells, including compositor clipping."""
    return [
        "".join(segment.text for segment in strip)
        for strip in app.screen._compositor.render_full_update().strips
    ]


def rendered_station_rows(app):
    region = app.stations_table.region
    return "\n".join(
        line[region.x:region.right]
        for line in rendered_screen_lines(app)[region.y:region.bottom]
    )


def make_long_name_app(tmp_path):
    app = make_app(tmp_path)
    assert isinstance(app.client, FakeClient)
    app.client.stations.append(make_station(
        "long", "Radio TEDU Lo-Fi — " + "International study sessions " * 5
    ))
    return app


@pytest.mark.parametrize("size", [(120, 40), (100, 32), (80, 24), (60, 24)])
@pytest.mark.parametrize("editing", [False, True])
async def test_search_is_an_underlined_field_above_workspace(tmp_path, size, editing):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        if editing:
            await pilot.press("slash")
        await pilot.pause(0.1)
        search = app.search_input if editing else app.query_one("#search-trigger")
        region = search.region
        assert region.height == 1 and 0 <= region.x < region.right <= size[0]
        assert region.bottom <= app.query_one("#top-bar").content_region.bottom
        assert region.bottom <= app.query_one("#main").region.y
        strips = app.screen._compositor.render_full_update().strips
        underlined = [
            segment
            for chunk in strips[region.y]
            for segment in chunk
            if segment.style is not None and segment.style.underline and segment.text.strip()
        ]
        assert underlined, "search field must be underlined, not boxed"
        line = rendered_screen_lines(app)[region.y]
        assert not any(char in line for char in "┌┐└┘│╭╮╰╯") or size[0] >= 100 and "│" in line


@pytest.mark.parametrize("keys", [("right", "left"), ("l", "h"), ("end",), ("home",)])
@pytest.mark.parametrize("station_id, prefix", [("us1", "Jazz FM"), ("long", "Radio TEDU")])
async def test_station_names_and_metadata_survive_horizontal_navigation(
    tmp_path, keys, station_id, prefix
):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause(0.1)
        if station_id == "long":
            await pilot.press("down", "down", "down")
        await pilot.press(*keys)
        await pilot.pause(0.1)
        selected = app.stations_table.selected_station()
        assert selected is not None and selected.id == station_id
        visible = rendered_station_rows(app)
        assert prefix in visible
        assert "US · MP3 · 128 kbps" in visible
        assert app.stations_table.max_scroll_x == 0


async def test_station_selection_survives_resize_round_trip(tmp_path):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("down")
        horizontal_overflow = []
        for size in ((60, 24), (80, 24), (120, 40)):
            await pilot.resize_terminal(*size)
            await pilot.pause(0.1)
            selected = app.stations_table.selected_station()
            assert selected is not None and selected.id == "us2"
            assert "Night Talk" in rendered_station_rows(app)
            assert "US · MP3 · 128 kbps" in rendered_station_rows(app)
            assert app.stations_table.region.right <= size[0]
            horizontal_overflow.append((size, app.stations_table.max_scroll_x))
        assert all(overflow == 0 for _, overflow in horizontal_overflow), horizontal_overflow


async def test_escape_recovers_station_names_after_horizontal_scroll(tmp_path):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.press("end", "escape")
        await pilot.pause(0.1)
        assert app.mode == "world"
        selected = app.stations_table.selected_station()
        assert selected is not None and selected.id == "us1"
        assert "Jazz FM" in rendered_station_rows(app)


@pytest.mark.parametrize("has_results", [False, True])
async def test_search_empty_selection_and_escape_recovery(tmp_path, has_results):
    app = make_app(tmp_path)
    assert isinstance(app.client, FakeClient)
    app.client.search_results = (
        [make_station("match", "Radio TEDU Lo-Fi")] if has_results else []
    )
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("slash", "l", "o", "f", "i")
        await pilot.pause(0.55)
        assert app.mode == "search"
        selected = app.stations_table.selected_station()
        if has_results:
            assert selected is not None and selected.id == "match"
            assert "Radio TEDU" in rendered_station_rows(app)
        else:
            assert selected is None
            assert "No stations" in rendered_station_rows(app)
            await pilot.press("enter")
            assert isinstance(app.player, FakePlayer)
            assert plays(app) == []
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.mode == "world"
        assert app.stations_table.has_focus
        selected = app.stations_table.selected_station()
        assert selected is not None and selected.id == "us1"
        assert "Jazz FM" in rendered_station_rows(app)


@pytest.mark.parametrize("size", [(120, 40), (80, 24)])
async def test_transport_controls_are_single_row_targets_that_stay_clickable(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        for name in ("previous", "play", "next", "stop", "mute"):
            region = app.query_one(f"#control-{name}").region
            assert region.height == 1 and region.width >= 3, name
            assert region.bottom <= size[1] and region.right <= size[0], name
        # Every cell of the Play target, edges included, must reach the button.
        expected = ["playing", "paused", "playing"]
        for offset, status in zip(((0, 0), (4, 0), (2, 0)), expected, strict=True):
            await pilot.click("#control-play", offset=offset)
            await pilot.pause(0.1)
            assert app.player.state.status == status, offset


@pytest.mark.parametrize("status", ["playing", "paused", "stopped", "error", "unavailable"])
async def test_live_badge_is_green_and_only_shown_when_playing(tmp_path, status):
    class RejectedPlayer(FakePlayer):
        async def play(self, station):
            self.state = PlayerState(status=status, station=station, error="Stream unavailable")
            return False

    app = make_app(tmp_path)
    if status in ("error", "unavailable"):
        app.player = RejectedPlayer()
    async with app.run_test(size=(120, 40)) as pilot:
        if status != "stopped":
            await pilot.click("#control-play")
            await pilot.pause(0.1)
            if status == "paused":
                await pilot.press("space")
        await pilot.pause(0.1)
        assert app.player.state.status == status
        text = app.now_playing.render()
        if status == "playing":
            assert ICON_PUA["signal"] + " LIVE" in text.plain
            dot = text.plain.index(ICON_PUA["signal"])
            color = text.get_style_at_offset(app.console, dot).color
            assert color is not None
            rgb = color.get_truecolor()
            assert rgb.green > rgb.red and rgb.green > rgb.blue
            assert ICON_PUA["signal"] + " LIVE" in "\n".join(rendered_screen_lines(app))
        else:
            assert "LIVE" not in text.plain
            if status in ("error", "unavailable"):
                assert "Stream unavailable" in "\n".join(rendered_screen_lines(app))
                assert app.store.history == []


@pytest.mark.parametrize("size", [(120, 40), (100, 32), (80, 24), (60, 24)])
async def test_long_selected_station_stays_readable_and_favorited(tmp_path, size):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("down", "down", "down", "f")
        await pilot.resize_terminal(*size)
        await pilot.pause(0.1)
        await pilot.press("end", "right", "l", "home", "left", "h")
        # Exercise the same public scrolling interface as horizontal gestures.
        app.stations_table.scroll_to(x=10_000, animate=False)
        await pilot.pause(0.1)
        visible = rendered_station_rows(app)
        name_line = next(line for line in visible.splitlines() if "Radio TEDU" in line)
        assert "…" in name_line
        assert row_starred(app, "Radio TEDU")[0]
        assert "US · MP3 · 128 kbps" in visible
        selected = app.stations_table.selected_station()
        assert selected is not None and selected.id == "long"
        assert app.store.favorite_ids == {"long"}
        assert "STATIONS" in "\n".join(rendered_screen_lines(app))
        await pilot.resize_terminal(120, 40)
        await pilot.pause(0.1)
        selected = app.stations_table.selected_station()
        assert selected is not None and selected.id == "long"
        assert "Radio TEDU" in rendered_station_rows(app)


async def test_height_only_resize_keeps_selected_station_visible(tmp_path):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("down", "down", "down")
        for height in (24, 40):
            await pilot.resize_terminal(120, height)
            await pilot.pause(0.1)
            selected = app.stations_table.selected_station()
            assert selected is not None and selected.id == "long"
            assert "Radio TEDU" in rendered_station_rows(app)
            assert "US · MP3 · 128 kbps" in rendered_station_rows(app)


async def test_compact_empty_library_and_keyboard_recovery(tmp_path):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=(60, 24)) as pilot:
        await pilot.press("2")
        await pilot.pause(0.1)
        assert app.stations_table.selected_station() is None
        assert "No stations" in rendered_station_rows(app)
        await pilot.press("enter")
        assert app.player.state.status == "stopped"
        await pilot.press("escape", "space")
        await pilot.pause(0.1)
        assert app.mode == "world"
        assert app.stations_table.has_focus
        assert ICON_PUA["signal"] + " LIVE" in "\n".join(rendered_screen_lines(app))
        await pilot.press("space")
        await pilot.pause(0.1)
        rendered = "\n".join(rendered_screen_lines(app))
        assert "LIVE" not in rendered
        assert "PAUSED" in rendered


@pytest.mark.parametrize("size", [(120, 40), (80, 24), (60, 24)])
async def test_live_badge_remains_visible_with_wide_character_station_name(tmp_path, size):
    app = make_app(tmp_path)
    assert isinstance(app.client, FakeClient)
    app.client.stations[0] = make_station("us1", "東京深夜放送局 — 夜の音楽 " * 8)
    async with app.run_test(size=size) as pilot:
        await pilot.press("space")
        await pilot.pause(0.1)
        playing_line = next(
            line for line in rendered_screen_lines(app) if ICON_PUA["signal"] + " LIVE" in line
        )
        assert "NOW PLAYING" in playing_line
        name_line = next(
            line for line in rendered_screen_lines(app) if ICON_PUA["star_outline"] in line and "…" in line
        )
        assert name_line.index(ICON_PUA["star_outline"]) > name_line.index("…")
        await pilot.press("space")
        await pilot.pause(0.1)
        rendered = "\n".join(rendered_screen_lines(app))
        assert "LIVE" not in rendered
        assert "PAUSED" in rendered


async def test_help_stays_readable_in_compact_terminal(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(60, 24)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause(0.1)
        assert "RADIO ATLAS" in "\n".join(rendered_screen_lines(app))
        dialog = app.screen.query_one("#help-dialog")
        assert 0 <= dialog.region.x < dialog.region.right <= 60
        await pilot.press("escape")
        assert not isinstance(app.screen, HelpScreen)


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
        assert app.player.state.station is not None
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
        assert isinstance(app.client, FakeClient)
        assert app.client.search_calls
        assert app.mode == "search"
        assert app.stations_table.row_count == 1
        selected = app.stations_table.selected_station()
        assert selected is not None and selected.name == "Jazz FM"

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


async def test_genres_view_opens_a_genre_and_random_respects_it(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("4")
        await pilot.pause(0.1)
        assert app.mode == "genres"
        assert app.genres_table.row_count == len(GENRES)

        first = GENRES[0]
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app.mode == "stations"
        assert app.current_genre is not None
        assert app.current_genre.tag == first.tag
        assert isinstance(app.client, FakeClient)
        assert app.client.by_tag_calls[-1] == first.tag

        await pilot.press("r")
        await pilot.pause(0.1)
        assert app.client.random_tags[-1] == first.tag

        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.mode == "genres"


async def test_genre_search_filters_the_list(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("4")
        await pilot.pause(0.1)

        await pilot.press("slash")
        for key in "jazz":
            await pilot.press(key)
        await pilot.pause(0.1)
        assert app.genres_table.row_count == 1
        assert app.genres_table.genres[0][0].tag == "jazz"

        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.mode == "genres"
        assert app.genres_table.row_count == len(GENRES)


# -- transport labels and favorite controls ---------------------------------

SIZES = [(120, 40), (100, 32), (80, 24), (60, 24)]
TRANSPORT_IDS = (
    "control-previous", "control-play", "control-next", "control-stop",
    "control-mute", "control-down", "control-up",
)


def button_label(app, selector):
    """Collapse a stacked icon/caption label into one readable line."""
    return " ".join(str(app.query_one(selector, Button).label).split())


def star_offset(app, row):
    lines = rendered_station_rows(app).splitlines()
    for line_index in range(row * 2, row * 2 + 2):
        for index, char in enumerate(lines[line_index]):
            if ord(char) in (0xF005, 0xF006):
                return index, line_index
    raise AssertionError(f"no favorite icon rendered for row {row}")


async def click_star(app, pilot, row):
    await pilot.click(StationsTable, offset=star_offset(app, row))
    await pilot.pause(0.1)


def plays(app):
    return cast(FakePlayer, app.player).plays


def station_lines(app, name):
    return [line for line in rendered_station_rows(app).splitlines() if name in line]


async def test_play_button_shows_icon_and_tooltip_for_its_action(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        play = app.query_one("#control-play", Button)
        assert button_label(app, "#control-play") == ICON_PUA["play"]
        assert play.tooltip == "Play · space"
        await pilot.press("space")
        await pilot.pause(0.1)
        assert app.player.state.status == "playing"
        assert button_label(app, "#control-play") == ICON_PUA["pause"]
        assert play.tooltip == "Pause · space"
        assert ICON_PUA["pause"] in "\n".join(rendered_screen_lines(app))
        await pilot.press("space")
        await pilot.pause(0.1)
        assert app.player.state.status == "paused"
        assert button_label(app, "#control-play") == ICON_PUA["play"]
        assert play.tooltip == "Play · space"
        await pilot.press("s")
        await pilot.pause(0.1)
        assert app.player.state.status == "stopped"
        assert button_label(app, "#control-play") == ICON_PUA["play"]


@pytest.mark.parametrize("size", SIZES)
async def test_transport_controls_are_icon_only_with_named_tooltips(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        expected = {
            "control-previous": (ICON_PUA["step_backward"], "Previous · p"), "control-play": (ICON_PUA["play"], "Play · space"),
            "control-next": (ICON_PUA["step_forward"], "Next · n"), "control-stop": (ICON_PUA["stop"], "Stop · s"),
            "control-mute": (ICON_PUA["volume_up"], "Mute · m"),
        }
        lines = rendered_screen_lines(app)
        for ident, (icon, tooltip) in expected.items():
            assert button_label(app, f"#{ident}") == icon
            assert app.query_one(f"#{ident}", Button).tooltip == tooltip
            region = app.query_one(f"#{ident}").region
            assert region.width >= 3
            cells = "".join(line[region.x:region.right] for line in lines[region.y:region.bottom])
            assert icon in cells
            # No caption words under (or beside) the icons.
            assert not any(char.isalpha() for char in cells), (ident, cells)


async def test_clicking_a_non_cursor_row_star_toggles_only_that_station(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        assert app.stations_table.cursor_row == 0
        center_x, _ = star_offset(app, 2)
        for offset in ((center_x - 2, 4), (center_x + 2, 5)):
            await pilot.click(StationsTable, offset=(offset[0], offset[1]))
            await pilot.pause(0.3)
        assert app.store.favorite_ids == set()
        await click_star(app, pilot, 2)
        assert app.store.favorite_ids == {"fr1"}
        assert app.stations_table.cursor_row == 0
        assert plays(app) == []
        assert app.player.state.status == "stopped"
        assert row_starred(app, "Radio France")[0] is True
        assert row_starred(app, "Jazz FM")[0] is False
        assert "Radio France" in "\n".join(rendered_screen_lines(app))
        assert "Added" in "\n".join(rendered_screen_lines(app))
        await click_star(app, pilot, 2)
        assert app.store.favorite_ids == set()
        assert row_starred(app, "Radio France")[0] is False
        assert plays(app) == []
        assert "Removed" in "\n".join(rendered_screen_lines(app))


async def test_clicking_the_station_name_still_plays_the_row(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.click(StationsTable, offset=(3, 3))
        await pilot.pause(0.1)
        await pilot.click(StationsTable, offset=(3, 3))
        await pilot.pause(0.1)
        assert plays(app)[-1:] == ["us2"]
        assert app.store.favorite_ids == set()


async def test_enter_on_a_row_still_plays_it(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        app.stations_table.focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.1)
        assert plays(app) == ["us2"]


async def test_star_column_is_a_wide_target(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        column = next(
            value for key, value in app.stations_table.columns.items()
            if key.value == "favorite"
        )
        assert column.width >= 4


async def test_player_favorite_button_toggles_and_mirrors_other_paths(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("space")
        await pilot.pause(0.1)
        assert player_starred(app) is False
        for offset in ((0, 0), (2, 0), (0, 0), (2, 0)):  # edges toggle too: even count = off
            await pilot.click("#player-favorite", offset=offset)
            await pilot.pause(0.3)
        assert app.store.favorite_ids == set()
        await pilot.click("#player-favorite", offset=(1, 0))
        await pilot.pause(0.3)
        assert app.store.favorite_ids == {"us1"}
        assert player_starred(app) is True
        assert row_starred(app, "Jazz FM")[0] is True
        assert app.player.state.status == "playing"
        # The f key flips the same station and the button follows.
        await pilot.press("f")
        await pilot.pause(0.1)
        assert app.store.favorite_ids == set()
        assert player_starred(app) is False
        # A row star on the playing station updates the button too.
        await click_star(app, pilot, 0)
        assert player_starred(app) is True
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
        assert app.store.favorite_ids == set()
        assert player_starred(app) is False


async def test_player_favorite_follows_the_selection_when_idle(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        app.stations_table.focus()
        await pilot.press("down")
        await pilot.pause(0.1)
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
        assert app.store.favorite_ids == {"us2"}
        assert plays(app) == []
        assert player_starred(app) is True


async def test_player_star_targets_playing_station_not_new_cursor_selection(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("space")
        await pilot.pause(0.1)
        app.stations_table.focus()
        await pilot.press("down")
        await pilot.pause(0.1)
        selected = app.stations_table.selected_station()
        assert selected is not None and selected.id == "us2"
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
        assert app.store.favorite_ids == {"us1"}
        assert row_starred(app, "Jazz FM")[0]
        assert not row_starred(app, "Night Talk")[0]
        assert plays(app) == ["us1"]


async def test_player_favorite_is_inert_without_a_station(tmp_path):
    app = make_app(tmp_path)
    cast(FakeClient, app.client).stations.clear()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        button = app.query_one("#player-favorite", Button)
        assert button.disabled
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
        assert app.store.favorite_ids == set()


async def test_favorites_survive_a_fresh_app_instance(tmp_path):
    first = make_app(tmp_path)
    async with first.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await click_star(first, pilot, 1)
        await pilot.press("space")
        await pilot.pause(0.1)
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
    second = make_app(tmp_path)
    async with second.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        assert row_starred(second, "Jazz FM")[0] is True
        assert row_starred(second, "Night Talk")[0] is True
        assert row_starred(second, "Radio France")[0] is False
        await pilot.press("2")
        await pilot.pause(0.1)
        assert second.stations_table.row_count == 2
        assert row_starred(second, "Night Talk")[0] is True


async def test_unstarring_in_the_favorites_view_removes_the_row(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await click_star(app, pilot, 0)
        await click_star(app, pilot, 1)
        await pilot.press("2")
        await pilot.pause(0.1)
        assert app.mode == "favorites"
        assert app.stations_table.row_count == 2
        await click_star(app, pilot, 1)
        assert app.stations_table.row_count == 1
        assert app.mode == "favorites"
        await click_star(app, pilot, 0)
        assert app.store.favorites == []
        assert app.stations_table.row_count == 1
        assert app.stations_table.ordered_rows[0].key.value == EMPTY_KEY
        assert "No stations here" in rendered_station_rows(app)
        assert plays(app) == []


async def test_previous_and_next_buttons_step_stations(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.click("#control-next")
        await pilot.pause(0.1)
        assert plays(app) == ["us2"]
        await pilot.click("#control-previous")
        await pilot.pause(0.1)
        assert plays(app) == ["us2", "us1"]
        await pilot.press("n")
        await pilot.pause(0.1)
        await pilot.press("p")
        await pilot.pause(0.1)
        assert plays(app)[-2:] == ["us2", "us1"]


# -- reference redesign: Nerd Font icons, VOL bar, footer, notices ----------

# Font Awesome private-use codepoints used by Nerd Fonts: verified constants from
# the explicitly selected Font Awesome glyph set (not general Unicode symbols).
ICON_PUA = {
    "star": chr(0xF005), "star_outline": chr(0xF006),
    "play": chr(0xF04B), "pause": chr(0xF04C),
    "step_backward": chr(0xF048), "step_forward": chr(0xF051),
    "stop": chr(0xF04D), "volume_up": chr(0xF028),
    "volume_off": chr(0xF026), "search": chr(0xF002),
    "signal": chr(0xF012),
}
REAL_CHIPS = [
    ("1", "World"), ("2", "Favs"), ("3", "Recent"), ("4", "Genres"), ("c", "Browse"),
    ("/", "Find"), ("space", "Play/Pause"), ("r", "Random"), ("f", "Star"),
    ("?", "Help"), ("q", "Quit"),
]


def icon_cells(app, region, glyph):
    lines = rendered_screen_lines(app)
    return [
        (x, y) for y in range(region.y, region.bottom)
        for x in range(region.x, region.right) if lines[y][x] == glyph
    ]


def compositor_style_at(app, x, y):
    """Read the fully composed foreground/background at one terminal cell."""
    column = 0
    for chunk in app.screen._compositor.render_full_update().strips[y]:
        for segment in chunk:
            width = cell_len(segment.text)
            if column <= x < column + width:
                assert segment.style is not None, (x, y, segment)
                return segment.style
            column += width
    raise AssertionError(f"no compositor segment covers ({x}, {y})")


def color_rgb(color):
    triplet = color.get_truecolor()
    return (triplet.red, triplet.green, triplet.blue)



def player_starred(app):
    button = app.query_one("#player-favorite", Button)
    return ICON_PUA["star"] in str(button.label)


def row_starred(app, name):
    lines = rendered_station_rows(app).splitlines()
    for index, line in enumerate(lines):
        if name in line:
            return ICON_PUA["star"] in line, index
    raise AssertionError(f"no star row for {name!r}")


def row_star_glyph(app, name):
    filled, index = row_starred(app, name)
    return (ICON_PUA["star"] if filled else ICON_PUA["star_outline"]), index


def footer_lines(app):
    lines = rendered_screen_lines(app)
    return lines[-2], lines[-1]


@pytest.mark.parametrize("size", SIZES)
async def test_header_is_one_row_with_brand_mode_count_and_source_badge(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        lines = rendered_screen_lines(app)
        assert ICON_PUA["signal"] in lines[0]
        assert "RADIO ATLAS" in lines[0]
        assert "WORLD · 3 STATIONS" in lines[0]
        assert "SEED OFFLINE" in lines[0]
        rule_row = 2 if size[0] < 100 else 1
        assert set(lines[rule_row].strip()) == {"─"}
        assert ICON_PUA["search"] in "".join(lines[:rule_row])


async def test_header_badge_is_green_online_and_distinct_for_cache_and_seed(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        colors = {}
        for source in ("network", "cache", "seed"):
            app.header.update_header(mode_label="WORLD", count=3, source=source)
            text = app.header.render()
            label = {"network": "ONLINE", "cache": "CACHE OFFLINE", "seed": "SEED OFFLINE"}[source]
            style = text.get_style_at_offset(app.console, text.plain.index(label))
            assert style.color is not None
            colors[source] = style.color.get_truecolor()
        assert colors["network"].green > colors["network"].red
        assert colors["network"].green > colors["network"].blue
        assert len(set(colors.values())) == 3


def test_fontawesome_nerd_font_aliases_are_explicit_and_stable():
    from radio_atlas.widgets.panels import ICON_CODEPOINTS

    assert ICON_CODEPOINTS == {
        "star": 0xF005, "star_outline": 0xF006,
        "play": 0xF04B, "pause": 0xF04C,
        "step_backward": 0xF048, "step_forward": 0xF051,
        "stop": 0xF04D, "volume_up": 0xF028,
        "volume_off": 0xF026, "search": 0xF002,
        "signal": 0xF012,
    }


@pytest.mark.parametrize("size", SIZES)
async def test_player_favorite_uses_nerd_font_star_icons_and_yellow(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        button = app.query_one("#player-favorite", Button)
        label = str(button.label)
        assert ICON_PUA["star_outline"] in label
        assert not any(0x2800 <= ord(char) <= 0x28FF for char in label)
        assert "Favorite" not in label and "Favorited" not in label
        assert button.styles.background != "#b49cf0"
        await pilot.press("space")
        await pilot.pause(0.1)
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
        label = str(button.label)
        assert ICON_PUA["star"] in label
        assert ICON_PUA["star_outline"] not in label
        assert "Favorite" not in label and "Favorited" not in label
        assert app.store.favorite_ids == {"us1"}

        rendered = rendered_screen_lines(app)
        points = icon_cells(app, button.region, ICON_PUA["star"])
        assert points, "filled Nerd Font star must render in the button"
        label_text = cast(Text, button.label)
        assert len(label_text.spans) == 1
        span_style = Style.parse(str(label_text.spans[0].style))
        color = getattr(span_style, "color", None)
        assert color is not None
        rgb = color.get_truecolor()
        assert (rgb.red, rgb.green, rgb.blue) == (0xF5, 0xC5, 0x42)
        assert "LIVE" in "\n".join(rendered)


async def test_row_nerd_font_star_is_clickable_without_playing(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        line = next(line for line in rendered_station_rows(app).splitlines() if "Radio France" in line)
        assert ICON_PUA["star_outline"] in line
        assert not any(0x2800 <= ord(char) <= 0x28FF for char in line)
        await click_star(app, pilot, 2)
        line = next(line for line in rendered_station_rows(app).splitlines() if "Radio France" in line)
        assert ICON_PUA["star"] in line and ICON_PUA["star_outline"] not in line
        row = app.stations_table.get_row_at(2)
        assert "#f5c542" in str(cast(Text, row[2]).style).lower()
        assert app.store.favorite_ids == {"fr1"}
        assert plays(app) == []
        assert app.stations_table.cursor_row == 0


@pytest.mark.parametrize("size", SIZES)
async def test_ascii_mode_keeps_ascii_favorite_fallback(tmp_path, size):
    app = make_app(tmp_path, ascii_globe=True)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        assert "[ ]" in str(app.query_one("#player-favorite", Button).label)
        await pilot.press("f")
        await pilot.pause(0.1)
        assert "[*]" in str(app.query_one("#player-favorite", Button).label)
        assert "[*]" in next(line for line in rendered_station_rows(app).splitlines() if "Jazz FM" in line)


@pytest.mark.parametrize("size", SIZES)
async def test_station_rows_are_two_lines_with_playing_marker(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        assert all(row.height == 2 for row in app.stations_table.ordered_rows)
        rows = rendered_station_rows(app).splitlines()
        assert "Jazz FM" in rows[0] and "US · MP3 · 128 kbps" in rows[1]
        assert "Night Talk" in rows[2]
        assert "▶" not in "\n".join(rows)
        await pilot.press("space")
        await pilot.pause(0.1)
        rows = rendered_station_rows(app).splitlines()
        assert "▶" in rows[0] and rows[0].index("▶") < rows[0].index("Jazz FM")
        assert "▶" not in "\n".join(rows[2:])


async def test_playing_marker_follows_the_playing_station_not_the_cursor(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("space")
        await pilot.pause(0.1)
        app.stations_table.focus()
        await pilot.press("down")
        await pilot.pause(0.1)
        rows = rendered_station_rows(app).splitlines()
        assert "▶" in rows[0] and "▶" not in rows[2]
        await pilot.press("s")
        await pilot.pause(0.1)
        assert "▶" not in rendered_station_rows(app)


async def test_tabs_are_separated_and_the_active_tab_is_underlined(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        region = app.query_one("#navigation").region
        line = rendered_screen_lines(app)[region.y]
        assert re.search(r"World\s*│\s*Favorites\s*│\s*Recent", line), line
        assert app.query_one("#nav-world").has_class("active")
        assert "underline" in str(app.query_one("#nav-world").styles.text_style)
        assert "underline" not in str(app.query_one("#nav-recent").styles.text_style)
        heading = app.query_one("#list-heading")
        assert str(heading.render()).strip() == "3 STATIONS"


@pytest.mark.parametrize("size", SIZES)
async def test_volume_bar_is_grouped_and_click_sets_persisted_volume(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        bar = app.query_one("#volume-bar")
        assert not app.query("#control-down") and not app.query("#control-up")
        row = rendered_screen_lines(app)[bar.region.y][bar.region.x:bar.region.right]
        assert row.startswith("VOL ") and row.rstrip().endswith("70%"), row
        segments = min(24, bar.region.width - len("VOL ") - 5)
        assert segments >= 1
        for index in (segments - 1, 0, segments // 2):
            await pilot.click("#volume-bar", offset=(4 + index, 0))
            await pilot.pause(0.1)
            expected = round((index + 1) / segments * 100)
            assert app.player.state.volume == expected
            assert app.store.get("volume") == expected
            row = rendered_screen_lines(app)[bar.region.y][bar.region.x:bar.region.right]
            assert row.rstrip().endswith(f"{expected}%"), row
        await pilot.press("right_square_bracket")
        await pilot.pause(0.1)
        assert app.player.state.volume == min(100, expected + 5)
        await pilot.press("left_square_bracket", "left_square_bracket")
        await pilot.pause(0.1)
        assert app.store.get("volume") == app.player.state.volume == expected - 5


async def test_volume_bar_filled_segments_follow_the_level_and_clamp(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        bar = app.query_one("#volume-bar")
        for _ in range(8):
            await pilot.press("right_square_bracket")
        await pilot.pause(0.2)
        assert app.player.state.volume == 100
        text = cast(Text, bar.render())
        assert text.plain.rstrip().endswith("100%")
        filled = [
            span for span in text.spans if "b49cf0" in str(span.style).lower()
        ]
        assert filled, "filled segments must use the lavender accent"
        await pilot.click("#volume-bar", offset=(0, 0))  # the VOL label is not a segment
        await pilot.pause(0.1)
        assert app.player.state.volume == 100


@pytest.mark.parametrize("size", SIZES)
async def test_footer_chips_show_the_real_bindings_on_one_line(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        _, chips = footer_lines(app)
        assert len(chips) <= size[0]
        assert re.search(r"space\s+Play/Pause", chips)
        assert re.search(r"q\s+Quit", chips)
        shown = [(k, v) for k, v in REAL_CHIPS if re.search(rf"(?<!\S){re.escape(k)}\s+{re.escape(v)}", chips)]
        if size[0] >= 120:
            assert shown == REAL_CHIPS, chips
        for key, label in REAL_CHIPS:
            if (key, label) not in shown:
                assert label[:3] not in chips, (label, chips)  # dropped, never half-clipped
        assert "Favorite" not in chips and "Play " not in chips.replace("Play/Pause", "")


async def test_footer_chips_are_clickable_actions(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        _, chips = footer_lines(app)
        await pilot.click(offset=(chips.index("Genres"), 39))
        await pilot.pause(0.1)
        assert app.mode == "genres"


async def test_status_bar_is_replaced_by_a_footer_toast(tmp_path, monkeypatch):
    from radio_atlas.widgets.panels import KeyFooter

    for tone in KeyFooter.DURATIONS:
        monkeypatch.setitem(KeyFooter.DURATIONS, tone, 0.8)
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(1.2)
        assert not app.query("#status-bar")
        rule, _ = footer_lines(app)
        assert set(rule.strip()) == {"─"}
        await pilot.press("f")
        await pilot.pause(0.1)
        rule, _ = footer_lines(app)
        assert "Added Jazz FM to favorites" in rule
        assert rule.rstrip().endswith("─") or "─" in rule


async def test_toast_expires_but_errors_outlast_info_and_stay_inline(tmp_path, monkeypatch):
    from radio_atlas.widgets.panels import KeyFooter

    assert KeyFooter.DURATIONS["error"] >= 10 > KeyFooter.DURATIONS["info"]
    assert KeyFooter.DURATIONS["warn"] >= 8
    monkeypatch.setitem(KeyFooter.DURATIONS, "info", 0.8)
    monkeypatch.setitem(KeyFooter.DURATIONS, "good", 0.8)
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("f")
        await pilot.pause(0.1)
        assert "Added Jazz FM" in footer_lines(app)[0]
        await pilot.pause(1.0)
        assert "Added Jazz FM" not in footer_lines(app)[0]
        app.player.state = PlayerState(
            status="error", station=app.catalog[0], error="Stream failed to play", volume=70
        )
        app._on_player_state(app.player.state)
        await pilot.pause(0.5)
        rendered = "\n".join(rendered_screen_lines(app))
        assert "Stream failed to play" in footer_lines(app)[0]
        assert rendered.count("Stream failed to play") == 2
        assert "LIVE" not in rendered


class NoMpvPlayer(FakePlayer):
    async def start(self) -> bool:
        self.state = PlayerState(
            status="unavailable", error="mpv is not installed. Install it to play radio."
        )
        return False


@pytest.mark.parametrize("size", [(120, 40), (60, 24)])
async def test_missing_mpv_and_offline_catalog_stay_disclosed(tmp_path, size, monkeypatch):
    from radio_atlas.widgets.panels import KeyFooter

    for tone in ("info", "good", "warn", "error"):
        monkeypatch.setitem(KeyFooter.DURATIONS, tone, 0.1)
    app = make_app(tmp_path)
    app.player = NoMpvPlayer()
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.6)
        rendered = "\n".join(rendered_screen_lines(app))
        assert "mpv is not installed" in rendered  # inline, after the toast expired
        assert "SEED OFFLINE" in rendered
        assert "LIVE" not in rendered


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("state", ["idle", "playing", "paused", "favorited"])
async def test_reference_layout_stays_inside_bounds(tmp_path, size, state):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        if state != "idle":
            await pilot.press("space")
            await pilot.pause(0.1)
        if state == "paused":
            await pilot.press("space")
            await pilot.pause(0.1)
        if state == "favorited":
            await pilot.press("f")
            await pilot.pause(0.1)
        lines = rendered_screen_lines(app)
        assert len(lines) == size[1] and all(len(line) <= size[0] for line in lines)
        for selector in ("#top-bar", "#header", "#search-box", "#main", "#side-panel",
                         "#navigation", "#now-playing", "#transport", "#key-footer"):
            region = app.query_one(selector).region
            assert region.width > 0 and region.height > 0, selector
            assert 0 <= region.x < region.right <= size[0], selector
            assert 0 <= region.y < region.bottom <= size[1], selector
        controls = [app.query_one(f"#{ident}") for ident in (
            "control-previous", "control-play", "control-next", "control-stop",
            "control-mute", "volume-bar", "player-favorite")]
        transport = app.query_one("#transport").region
        assert app.now_playing.region.contains_region(app.query_one("#player-favorite").region)
        for index, first in enumerate(controls):
            if first.id != "player-favorite":
                assert transport.contains_region(first.region), first.id
            for second in controls[index + 1:]:
                assert not first.region.overlaps(second.region), (first.id, second.id)
        assert app.query_one("#transport").region.bottom <= app.query_one("#key-footer").region.y
        assert app.now_playing.region.bottom <= app.query_one("#transport").region.y
        assert app.stations_table.scroll_x == 0 and app.stations_table.max_scroll_x == 0
        assert "Jazz FM" in rendered_station_rows(app)
        assert any("…" in line for line in rendered_station_rows(app).splitlines()) or size[0] >= 100
        if size[0] < 72:
            assert not app.query_one("#left-panel").display
            assert "WORLD MAP" in "\n".join(lines)
        playing = state in ("playing", "favorited")
        assert (ICON_PUA["signal"] + " LIVE" in "\n".join(lines)) is playing


async def test_random_and_quit_stay_reachable_after_the_top_bar_buttons_went(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        assert not app.query("#control-random") and not app.query("#control-quit")
        _, chips = footer_lines(app)
        await pilot.click(offset=(chips.index("Random"), 39))
        await pilot.pause(0.2)
        assert cast(FakeClient, app.client).random_tags == [None]
        assert plays(app) == ["us1"]
        await pilot.press("r")
        await pilot.pause(0.2)
        assert cast(FakeClient, app.client).random_tags == [None, None]
        await pilot.click(offset=(chips.index("Quit"), 39))
        await pilot.pause(0.2)
        assert app._exit


@pytest.mark.parametrize("state", ["idle", "playing", "paused"])
@pytest.mark.parametrize("interaction", ["normal", "focus", "hover"])
async def test_play_pause_icon_has_primary_background_contrast_in_compositor(
    tmp_path, state, interaction
):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        if state in ("playing", "paused"):
            await pilot.press("space")
            await pilot.pause(0.1)
        if state == "paused":
            await pilot.press("space")
            await pilot.pause(0.1)

        button = app.query_one("#control-play", Button)
        if interaction == "focus":
            button.focus()
            await pilot.pause(0.1)
        elif interaction == "hover":
            await pilot.hover(button)
            await pilot.pause(0.1)

        glyph = ICON_PUA["pause"] if state == "playing" else ICON_PUA["play"]
        (x, y), = icon_cells(app, button.region, glyph)
        style = compositor_style_at(app, x, y)
        assert style.color is not None and style.bgcolor is not None
        foreground = color_rgb(style.color)
        background = color_rgb(style.bgcolor)
        assert foreground == (0x14, 0x10, 0x1F), (state, interaction, foreground, background)
        expected_backgrounds = {
            "normal": (0xB4, 0x9C, 0xF0),
            "hover": (0xCD, 0xBD, 0xF7),
            "focus": (0xCD, 0xBE, 0xF5),
        }
        assert background == expected_backgrounds[interaction], (
            state, interaction, foreground, background
        )

        def luminance(rgb):
            channels = [value / 255 for value in rgb]
            linear = [
                value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                for value in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        contrast = (luminance(background) + 0.05) / (luminance(foreground) + 0.05)
        assert contrast >= 7, (state, interaction, foreground, background, contrast)



# -- player-only refinement: 6-row block, name + star, compact controls ------

PLAYER_COLORS = {
    "dim_violet": (0x8A, 0x7B, 0xC2), "accent": (0xB4, 0x9C, 0xF0),
    "text": (0xE4, 0xE4, 0xEC), "muted": (0x9A, 0x9A, 0xA8),
    "live": (0x65, 0xD6, 0x9A), "error": (0xF8, 0x71, 0x71),
    "favorite": (0xF5, 0xC5, 0x42), "dim": (0x3F, 0x3F, 0x52),
}
PLAYER_STATES = ["idle", "playing", "paused", "favorited", "muted", "error"]

# Captured from the pre-refinement build (rule row carries the seed-offline toast).
FOOTER_BASELINE = {
    (120, 40): (
        "───────────────────────────────────────────────────────────── ! Radio Browser unavailable — using the bundled catalog ──",
        "  1  World  2  Favs  3  Recent  4  Genres  c  Browse  /  Find  space  Play/Pause  r  Random  f  Star  ?  Help  q  Quit  ",
    ),
    (100, 32): (
        "───────────────────────────────────────── ! Radio Browser unavailable — using the bundled catalog ──",
        "  1  World  2  Favs  3  Recent  /  Find  space  Play/Pause  r  Random  f  Star  ?  Help  q  Quit    ",
    ),
    (80, 24): (
        "───────────────────── ! Radio Browser unavailable — using the bundled catalog ──",
        "  1  World  2  Favs  /  Find  space  Play/Pause  f  Star  ?  Help  q  Quit      ",
    ),
    (60, 24): (
        "── ! Radio Browser unavailable — using the bundled catal… ──",
        "  /  Find   space  Play/Pause   f  Star   ?  Help   q  Quit ",
    ),
}


async def enter_player_state(app, pilot, state):
    if state in ("playing", "paused", "favorited", "muted"):
        await pilot.press("space")
        await pilot.pause(0.1)
    if state == "paused":
        await pilot.press("space")
        await pilot.pause(0.1)
    if state == "favorited":
        await pilot.press("f")
        await pilot.pause(0.1)
    if state == "muted":
        await pilot.press("m")
        await pilot.pause(0.1)
    if state == "error":
        app.player.state = PlayerState(
            status="error", station=app.catalog[0], error="Stream failed to play", volume=70
        )
        app._on_player_state(app.player.state)
        await pilot.pause(0.2)


def player_rows(app):
    """Every terminal row of the player block, cropped to its columns."""
    top = app.now_playing.region
    bottom = app.query_one("#transport").region.bottom
    lines = rendered_screen_lines(app)
    return [line[top.x:top.right] for line in lines[top.y:bottom]], top


def cell_rgb(app, x, y):
    return color_rgb(compositor_style_at(app, x, y).color)


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("state", PLAYER_STATES)
async def test_player_block_is_six_rows_with_one_top_rule(tmp_path, size, state):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        await enter_player_state(app, pilot, state)
        rows, top = player_rows(app)
        assert len(rows) == 6, rows
        assert set(rows[0].strip()) == {"─"}
        assert rows[4].strip() == "", rows  # breathing row between info and controls
        assert not any("─" in row for row in rows[1:]), rows
        assert app.query_one("#transport").region.height == 2
        assert app.query_one("#transport").region.bottom <= app.query_one("#key-footer").region.y


async def test_volume_group_wraps_to_a_seventh_row_only_when_the_panel_is_too_narrow(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(44, 24)) as pilot:
        await pilot.pause(0.2)
        rows, top = player_rows(app)
        assert len(rows) == 7, rows
        previous = app.query_one("#control-previous").region
        mute = app.query_one("#control-mute").region
        bar = app.query_one("#volume-bar").region
        assert mute.y == previous.y + 1 and bar.y == mute.y
        assert mute.x == previous.x  # same left axis as the transport group
        assert bar.right <= top.right and app.query_one("#transport").scroll_x == 0


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("state,label,tone", [
    ("idle", "STOPPED", "muted"), ("playing", ICON_PUA["signal"] + " LIVE", "live"),
    ("paused", "PAUSED", "accent"), ("error", "Stream failed to play", "error"),
])
async def test_player_header_line_has_dim_title_left_and_state_right(tmp_path, size, state, label, tone):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        await enter_player_state(app, pilot, state)
        rows, top = player_rows(app)
        line = rows[1]
        assert line.startswith("  NOW PLAYING"), line
        assert line.rstrip().endswith(label), line
        assert len(line.rstrip()) == top.width - 2, line  # right edge = 2-col padding
        lowered = line.lower()
        for hint in ("space", "resumes", "tunes", "streaming", "press"):
            assert hint not in lowered, line
        assert ("LIVE" in line) is (state == "playing")
        assert cell_rgb(app, top.x + 2, top.y + 1) == PLAYER_COLORS["dim_violet"]
        assert not compositor_style_at(app, top.x + 2, top.y + 1).bold
        assert cell_rgb(app, top.x + len(line.rstrip()) - 1, top.y + 1) == PLAYER_COLORS[tone]


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("favorited", [False, True])
async def test_station_name_is_bold_with_the_favorite_icon_right_after_it(tmp_path, size, favorited):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        if favorited:
            await pilot.press("f")
            await pilot.pause(0.1)
        rows, top = player_rows(app)
        line = rows[2]
        assert line.startswith("  Jazz FM"), line
        name_end = len("  Jazz FM")
        glyph = ICON_PUA["star"] if favorited else ICON_PUA["star_outline"]
        assert glyph in line and line.index(glyph) - name_end == 1, line
        name_style = compositor_style_at(app, top.x + 2, top.y + 2)
        assert name_style.bold and color_rgb(name_style.color) == PLAYER_COLORS["text"]
        star_color = cell_rgb(app, top.x + line.index(glyph), top.y + 2)
        assert star_color == PLAYER_COLORS["favorite" if favorited else "muted"]
        button = app.query_one("#player-favorite").region
        assert (button.x, button.y, button.width, button.height) == (top.x + name_end, top.y + 2, 3, 1)
        assert top.contains_region(button)


@pytest.mark.parametrize("size", SIZES)
async def test_long_station_name_ellipsizes_before_the_favorite_icon_is_pushed_off(tmp_path, size):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        await pilot.press("down", "down", "down")
        await pilot.pause(0.1)
        rows, top = player_rows(app)
        line = rows[2]
        assert "…" in line and "Radio TEDU" in line, line
        star = line.index(ICON_PUA["star_outline"])
        assert star == line.index("…") + 2 and star <= top.width - 3, line
        assert top.contains_region(app.query_one("#player-favorite").region)
        assert app.query_one("#player-favorite").region.right <= top.right - 2 + 1


@pytest.mark.parametrize("favorited", [False, True])
async def test_player_favorite_icon_is_a_clickable_target_that_never_starts_playback(tmp_path, favorited):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        expected: set[str] = set()
        for offset in ((0, 0), (1, 0), (2, 0)):
            await pilot.click("#player-favorite", offset=offset)
            await pilot.pause(0.2)
            expected = set() if expected else {"us1"}
            assert app.store.favorite_ids == expected, offset
        assert plays(app) == [] and app.player.state.status == "stopped"
        rows, _ = player_rows(app)
        assert (ICON_PUA["star"] in rows[2]) is bool(expected)


@pytest.mark.parametrize("size", SIZES)
async def test_metadata_line_shows_title_codec_and_bitrate_muted_and_ellipsized(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        rows, top = player_rows(app)
        assert rows[3].strip() == "United States · New York · MP3 · 128 kbps"[:len(rows[3].strip())] or \
            rows[3].strip().endswith("MP3 · 128 kbps"), rows[3]
        assert "Jazz FM" not in rows[3]
        await pilot.press("space")
        await pilot.pause(0.1)
        station = app.player.state.station
        app.player.state = PlayerState(status="playing", station=station, title="franceinfo-midfi.mp3", volume=70)
        app._on_player_state(app.player.state)
        await pilot.pause(0.2)
        rows, top = player_rows(app)
        assert rows[3].rstrip() == "  franceinfo-midfi.mp3 · MP3 · 128 kbps", rows[3]
        assert cell_rgb(app, top.x + 2, top.y + 3) == PLAYER_COLORS["muted"]
        app.player.state = PlayerState(
            status="playing", station=station, artist="A" * 30, title="T" * 90, volume=70
        )
        app._on_player_state(app.player.state)
        await pilot.pause(0.2)
        rows, top = player_rows(app)
        assert "…" in rows[3] and rows[3].rstrip().endswith(" · MP3 · 128 kbps"), rows[3]
        assert len(rows[3].rstrip()) <= top.width - 2


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("state", ["idle", "playing", "paused"])
async def test_transport_group_is_one_row_with_compact_equal_gap_targets(tmp_path, size, state):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        await enter_player_state(app, pilot, state)
        names = ("previous", "play", "next", "stop")
        regions = [app.query_one(f"#control-{name}").region for name in names]
        assert [r.width for r in regions] == [3, 5, 3, 3]
        assert {r.height for r in regions} == {1} and len({r.y for r in regions}) == 1
        gaps = {right.x - left.right for left, right in zip(regions, regions[1:], strict=False)}
        assert gaps == {2}
        rows, top = player_rows(app)
        assert regions[0].x == top.x + 2 and regions[0].y == top.y + 5  # left axis shared with the info lines
        play_glyph = ICON_PUA["pause"] if state == "playing" else ICON_PUA["play"]
        glyphs = [ICON_PUA["step_backward"], play_glyph, ICON_PUA["step_forward"], ICON_PUA["stop"]]
        for region, glyph in zip(regions, glyphs, strict=True):
            assert icon_cells(app, region, glyph) == [(region.x + (region.width - 1) // 2, region.y)]
        play = regions[1]
        style = compositor_style_at(app, play.x + 2, play.y)
        assert color_rgb(style.color) == (0x14, 0x10, 0x1F) and color_rgb(style.bgcolor) == PLAYER_COLORS["accent"]
        assert not app.query_one("#control-play").region.overlaps(app.query_one("#control-mute").region)


@pytest.mark.parametrize("size", [*SIZES, (160, 40)])
@pytest.mark.parametrize("muted", [False, True])
async def test_volume_group_is_speaker_label_short_bar_percent_aligned_right(tmp_path, size, muted):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        if muted:
            await pilot.press("m")
            await pilot.pause(0.1)
        rows, top = player_rows(app)
        mute = app.query_one("#control-mute").region
        bar = app.query_one("#volume-bar").region
        stop = app.query_one("#control-stop").region
        assert mute.y == bar.y == stop.y and (mute.width, mute.height) == (3, 1)
        speaker = ICON_PUA["volume_off" if muted else "volume_up"]
        assert icon_cells(app, mute, speaker) == [(mute.x + 1, mute.y)]
        assert mute.right + 1 == bar.x  # single-cell gap keeps related items together
        text = rendered_screen_lines(app)[bar.y][bar.x:bar.right]
        match = re.fullmatch(r"VOL (▮+) (\d{1,3}%) *", text)
        assert match, text
        slots = len(match.group(1))
        assert 6 <= slots <= 28, slots
        if size[0] >= 120:
            assert slots >= 21, slots
        if size[0] >= 160:
            assert slots == 24 and mute.x - stop.right >= 10  # surplus width becomes flexible space
        assert bar.width <= 4 + 24 + 5
        assert mute.x - stop.right >= 2  # minimum two-column gap between the groups at every width
        assert bar.right >= top.right - 2 - 2  # group hugs the right padding
        percent = text.index(match.group(2))
        assert color_rgb(compositor_style_at(app, bar.x + 4, bar.y).color) == (
            PLAYER_COLORS["muted"] if muted else PLAYER_COLORS["accent"]
        )
        assert text[percent - 1] == " " and text[4 + slots] == " "


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("state", PLAYER_STATES)
async def test_player_block_stays_inside_bounds_without_overlap_or_scroll(tmp_path, size, state):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        await enter_player_state(app, pilot, state)
        top = app.now_playing.region
        transport = app.query_one("#transport")
        ids = ["control-previous", "control-play", "control-next", "control-stop",
               "control-mute", "volume-bar", "player-favorite"]
        regions = [app.query_one(f"#{ident}").region for ident in ids]
        for ident, region in zip(ids, regions, strict=True):
            assert transport.region.contains_region(region) or top.contains_region(region), ident
            assert region.x >= 0 and region.right <= size[0] and region.bottom <= size[1], ident
        for index, first in enumerate(regions):
            for second in regions[index + 1:]:
                assert not first.overlaps(second)
        assert transport.scroll_x == 0 and transport.max_scroll_x == 0
        lines = rendered_screen_lines(app)
        assert len(lines) == size[1] and all(len(line) <= size[0] for line in lines)


@pytest.mark.parametrize("size", SIZES)
async def test_key_footer_is_byte_identical_to_the_pre_refinement_build(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.3)
        assert footer_lines(app) == FOOTER_BASELINE[size]


@pytest.mark.parametrize("size", SIZES)
async def test_volume_group_keeps_a_two_column_gap_and_shrinks_the_bar_first(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        stop = app.query_one("#control-stop").region
        group = app.query_one("#volume-group").region
        mute = app.query_one("#control-mute").region
        assert group.x - stop.right >= 2 and mute.x - stop.right >= 2
        # Buttons keep their size; only the bar absorbs the squeeze, and the percent survives.
        assert [app.query_one(f"#control-{n}").region.width for n in ("previous", "play", "next", "stop")] == [3, 5, 3, 3]
        text = rendered_screen_lines(app)[app.query_one("#volume-bar").region.y]
        assert text.rstrip().endswith("70%"), text
