"""Textual application behavior with injected data sources."""

from __future__ import annotations

from typing import cast

import pytest
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


def make_app(tmp_path) -> RadioAtlasApp:
    return RadioAtlasApp(
        client=cast(RadioBrowserClient, FakeClient()),
        store=Store(tmp_path / "state.json"),
        player=FakePlayer(),
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
        assert app.screen.styles.background.hex == "#111119"
        assert not app.stations_table.show_header
        assert app.stations_table.get_row_at(0)[0].plain == "Jazz FM\nUS · MP3 · 128 kbps"


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
            "#control-mute", "#control-down", "#control-up", "#control-random",
            "#control-quit",
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
async def test_search_border_is_visible_above_workspace(tmp_path, size, editing):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        if editing:
            await pilot.press("slash")
        await pilot.pause(0.1)
        search = app.search_input if editing else app.query_one("#search-trigger")
        region = search.region
        bottom = rendered_screen_lines(app)[region.bottom - 1][region.x:region.right]
        assert "└" in bottom and "┘" in bottom, repr(bottom)
        assert region.bottom <= app.query_one("#top-bar").content_region.bottom
        assert region.bottom <= app.query_one("#main").region.y


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
async def test_transport_controls_offer_multi_row_hit_areas(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        for name in ("previous", "play", "next", "stop", "mute", "down", "up"):
            control = app.query_one(f"#control-{name}")
            region = control.region
            assert region.height >= 2, name
            assert region.width >= 3, name
            assert region.bottom <= size[1] and region.right <= size[0], name
        # The extra control row must really be clickable, not clipped by its parent.
        await pilot.click("#control-play", offset=(1, 1))
        await pilot.pause(0.1)
        assert app.player.state.status == "playing"


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
            assert "● LIVE" in text.plain
            dot = text.plain.index("●")
            color = text.get_style_at_offset(app.console, dot).color
            assert color is not None
            rgb = color.get_truecolor()
            assert rgb.green > rgb.red and rgb.green > rgb.blue
            assert "● LIVE" in "\n".join(rendered_screen_lines(app))
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
        assert "★" in name_line
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
        assert "● LIVE" in "\n".join(rendered_screen_lines(app))
        await pilot.press("space")
        await pilot.pause(0.1)
        rendered = "\n".join(rendered_screen_lines(app))
        assert "LIVE" not in rendered
        assert "Paused" in rendered


@pytest.mark.parametrize("size", [(120, 40), (80, 24), (60, 24)])
async def test_live_badge_remains_visible_with_wide_character_station_name(tmp_path, size):
    app = make_app(tmp_path)
    assert isinstance(app.client, FakeClient)
    app.client.stations[0] = make_station("us1", "東京深夜放送局 — 夜の音楽 " * 8)
    async with app.run_test(size=size) as pilot:
        await pilot.press("space")
        await pilot.pause(0.1)
        playing_line = next(line for line in rendered_screen_lines(app) if "▶" in line)
        assert "● LIVE" in playing_line
        assert "jazz · smooth" in "\n".join(rendered_screen_lines(app))
        await pilot.press("space")
        await pilot.pause(0.1)
        rendered = "\n".join(rendered_screen_lines(app))
        assert "LIVE" not in rendered
        assert "Paused" in rendered


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
    """Locate a row's rendered star from the actual terminal cells."""
    lines = rendered_station_rows(app).splitlines()
    for line_index in range(row * 3, row * 3 + 3):
        for glyph in "☆★":
            if glyph in lines[line_index]:
                return lines[line_index].index(glyph), line_index
    raise AssertionError(f"no star rendered for row {row}")


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
        assert button_label(app, "#control-play") == "▶"
        assert play.tooltip == "Play · space"
        await pilot.press("space")
        await pilot.pause(0.1)
        assert app.player.state.status == "playing"
        assert button_label(app, "#control-play") == "❚❚"
        assert play.tooltip == "Pause · space"
        assert "❚❚" in "\n".join(rendered_screen_lines(app))
        await pilot.press("space")
        await pilot.pause(0.1)
        assert app.player.state.status == "paused"
        assert button_label(app, "#control-play") == "▶"
        assert play.tooltip == "Play · space"
        await pilot.press("s")
        await pilot.pause(0.1)
        assert app.player.state.status == "stopped"
        assert button_label(app, "#control-play") == "▶"


@pytest.mark.parametrize("size", SIZES)
async def test_transport_controls_are_icon_only_with_named_tooltips(tmp_path, size):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        expected = {
            "control-previous": ("⏮", "Previous · p"), "control-play": ("▶", "Play · space"),
            "control-next": ("⏭", "Next · n"), "control-stop": ("■", "Stop · s"),
            "control-mute": ("♪", "Mute · m"), "control-down": ("−", "Volume down · ["),
            "control-up": ("+", "Volume up · ]"),
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


@pytest.mark.parametrize("size", SIZES)
async def test_transport_and_favorite_controls_fit_without_overlap(tmp_path, size):
    app = make_long_name_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        await pilot.press("space")
        await pilot.pause(0.1)
        controls = [app.query_one(f"#{ident}") for ident in TRANSPORT_IDS]
        controls.append(app.query_one("#player-favorite"))
        rendered = "\n".join(rendered_screen_lines(app))
        for control in controls:
            region = control.region
            assert region.width > 0 and region.height >= 2, control.id
            assert 0 <= region.x and region.right <= size[0], control.id
            assert 0 <= region.y and region.bottom <= size[1], control.id
        for index, first in enumerate(controls):
            for second in controls[index + 1:]:
                assert not first.region.overlaps(second.region), (first.id, second.id)
        transport = app.query_one("#transport").region
        for control in controls:
            assert transport.contains_region(control.region), control.id
        favorite = app.query_one("#player-favorite").region
        assert favorite.height >= 2
        assert favorite.width > app.query_one("#control-play").region.width
        assert transport.contains_region(favorite)
        assert "❚❚" in rendered and "☆" in rendered
        assert app.query_one("#transport").region.bottom <= app.query_one("#status-bar").region.y
        assert app.stations_table.scroll_x == 0
        assert "Jazz FM" in rendered_station_rows(app)
        assert app.query_one("#transport").virtual_size.width <= transport.width


async def test_clicking_a_non_cursor_row_star_toggles_only_that_station(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        assert app.stations_table.cursor_row == 0
        await click_star(app, pilot, 2)
        assert app.store.favorite_ids == {"fr1"}
        assert app.stations_table.cursor_row == 0
        assert plays(app) == []
        assert app.player.state.status == "stopped"
        assert "★" in station_lines(app, "Radio France")[0]
        assert "☆" in station_lines(app, "Jazz FM")[0]
        assert "Radio France" in "\n".join(rendered_screen_lines(app))
        assert "Added" in "\n".join(rendered_screen_lines(app))
        await click_star(app, pilot, 2)
        assert app.store.favorite_ids == set()
        assert "☆" in station_lines(app, "Radio France")[0]
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
        column = app.stations_table.columns["favorite"]
        assert column.width >= 4


async def test_player_favorite_button_toggles_and_mirrors_other_paths(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("space")
        await pilot.pause(0.1)
        assert button_label(app, "#player-favorite") == "☆ Favorite"
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
        assert app.store.favorite_ids == {"us1"}
        assert button_label(app, "#player-favorite") == "★ Favorited"
        assert "★ Favorited" in "\n".join(rendered_screen_lines(app))
        assert "★" in station_lines(app, "Jazz FM")[0]
        assert app.player.state.status == "playing"
        # The f key flips the same station and the button follows.
        await pilot.press("f")
        await pilot.pause(0.1)
        assert app.store.favorite_ids == set()
        assert button_label(app, "#player-favorite") == "☆ Favorite"
        # A row star on the playing station updates the button too.
        await click_star(app, pilot, 0)
        assert button_label(app, "#player-favorite") == "★ Favorited"
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
        assert app.store.favorite_ids == set()
        assert button_label(app, "#player-favorite") == "☆ Favorite"


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
        assert button_label(app, "#player-favorite") == "★ Favorited"


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
        assert "★" in station_lines(second, "Jazz FM")[0]
        assert "★" in station_lines(second, "Night Talk")[0]
        assert "☆" in station_lines(second, "Radio France")[0]
        await pilot.press("2")
        await pilot.pause(0.1)
        assert second.stations_table.row_count == 2
        assert "★" in station_lines(second, "Night Talk")[0]


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


@pytest.mark.parametrize(
    "size,visible",
    [((160, 40), True), ((120, 40), False), ((100, 32), False), ((80, 24), False), ((60, 24), True)],
)
async def test_volume_readout_shows_where_the_transport_has_room(tmp_path, size, visible):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        label = app.query_one("#volume-label")
        assert label.display is visible
        assert ("70%" in "\n".join(rendered_screen_lines(app))) is visible
        assert "VOL" in "\n".join(rendered_screen_lines(app))
        if visible:
            assert app.query_one("#transport").region.contains_region(label.region)


@pytest.mark.parametrize("size,label", [((160, 40), "☆ Favorite"), ((120, 40), "☆ Favorite"),
                                         ((100, 32), "☆"), ((80, 24), "☆"), ((60, 24), "☆ Favorite")])
async def test_favorite_button_label_fits_its_width(tmp_path, size, label):
    app = make_app(tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        assert button_label(app, "#player-favorite") == label
        await pilot.click("#player-favorite")
        await pilot.pause(0.1)
        assert button_label(app, "#player-favorite") == label.replace("☆", "★").replace("Favorite", "Favorited")
        region = app.query_one("#player-favorite").region
        assert region.height >= 2 and region.right <= size[0]
