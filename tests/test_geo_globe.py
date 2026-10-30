"""Bundled geography and braille globe rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from radio_atlas.geo import (
    MASK_HEIGHT,
    MASK_WIDTH,
    GeoAssetError,
    GeoIndex,
    load_geo_index,
)
from radio_atlas.globe import (
    MAX_ZOOM,
    MIN_ZOOM,
    STYLE_FAVORITE,
    STYLE_LAND,
    STYLE_PLAYING,
    STYLE_SELECTED,
    STYLE_STATION,
    GlobeRenderer,
    clamp,
    globe_radius,
    project,
    station_cell,
    unproject,
    wrap_longitude,
)
from radio_atlas.models import Station

GOLDEN = Path(__file__).parent / "golden"


def make_station(station_id: str, latitude: float, longitude: float, **kwargs) -> Station:
    return Station(
        id=station_id,
        name=station_id,
        url=f"https://stream.example/{station_id}",
        latitude=latitude,
        longitude=longitude,
        **kwargs,
    )


class TestGeoIndex:
    def test_bundled_assets_load(self):
        geo = load_geo_index()
        assert len(geo) >= 150
        assert geo.country_by_code("us") is not None
        assert geo.country_by_code("us").name == "United States of America"

    @pytest.mark.parametrize(
        ("latitude", "longitude", "code"),
        [
            (48.85, 2.35, "FR"),
            (35.68, 139.69, "JP"),
            (-23.55, -46.63, "BR"),
            (19.43, -99.13, "MX"),
            (-33.87, 151.21, "AU"),
            (-1.29, 36.82, "KE"),
            (55.75, 37.62, "RU"),
        ],
    )
    def test_country_at_known_inland_coordinates(self, latitude, longitude, code):
        country = load_geo_index().country_at(latitude, longitude)
        assert country is not None
        assert country.code == code

    def test_ocean_and_invalid_coordinates_return_none(self):
        geo = load_geo_index()
        assert geo.country_at(0, 0) is None
        assert geo.country_at(float("nan"), 0) is None
        assert geo.country_at(0, float("inf")) is None
        assert geo.value_at(91, 181) == geo.value_at(90, -179)

    def test_nearest_country_recovers_coastal_gaps(self):
        geo = load_geo_index()
        assert geo.country_at(40.7, -74.0) is None
        assert geo.nearest_country(40.7, -74.0).code == "US"

    def test_code_lookup_is_case_insensitive_with_name_fallback(self):
        geo = load_geo_index()
        assert geo.country_by_code(" fr ").code == "FR"
        assert geo.country_name("fr") == "France"
        assert geo.country_name("ZZ") == "ZZ"

    def test_asset_validation(self):
        with pytest.raises(GeoAssetError, match="worldmask"):
            GeoIndex(b"short", [])
        with pytest.raises(GeoAssetError, match="more entries"):
            GeoIndex(bytes(MASK_WIDTH * MASK_HEIGHT), [{}] * 256)
        with pytest.raises(GeoAssetError, match="Cannot read"):
            GeoIndex.load(Path("/nonexistent/atlas/assets"))


class TestProjection:
    def test_wrap_longitude(self):
        assert wrap_longitude(0) == 0
        assert wrap_longitude(190) == pytest.approx(-170)
        assert wrap_longitude(-190) == pytest.approx(170)
        assert wrap_longitude(540) == pytest.approx(-180)

    def test_clamp(self):
        assert clamp(5, 0, 3) == 3
        assert clamp(-5, 0, 3) == 0
        assert clamp(2, 0, 3) == 2

    @pytest.mark.parametrize(
        ("latitude", "longitude"),
        [(0, 0), (20, 10), (-10, 20), (45, -30), (60, -120)],
    )
    def test_project_unproject_roundtrip(self, latitude, longitude):
        x, y, z = project(latitude, longitude, 20, 0)
        assert z > 0
        back = unproject(x, y, 20, 0)
        assert back is not None
        assert back[0] == pytest.approx(latitude, abs=1e-6)
        assert back[1] == pytest.approx(longitude, abs=1e-6)

    def test_unproject_rejects_points_outside_the_disc(self):
        assert unproject(1.1, 0, 0, 0) is None
        assert unproject(0.8, 0.8, 0, 0) is None

    def test_globe_radius_scales_and_clamps_zoom(self):
        assert globe_radius(80, 24, 0.1) == pytest.approx(
            globe_radius(80, 24, MIN_ZOOM)
        )
        assert globe_radius(80, 24, 99) == pytest.approx(globe_radius(80, 24, MAX_ZOOM))
        assert globe_radius(160, 48, 1) > globe_radius(80, 24, 1)


class TestStationCells:
    def test_center_maps_to_center_cell(self):
        cell = station_cell(20, 0, 60, 20, 20, 0, 1.0)
        assert cell is not None
        assert cell[:2] == (30, 10)

    def test_backside_and_invalid_sizes_are_hidden(self):
        assert station_cell(-20, 180, 60, 20, 20, 0, 1.0) is None
        assert station_cell(20, 0, 0, 20, 20, 0, 1.0) is None


class TestGlobeRenderer:
    def test_empty_dimensions_render_an_empty_frame(self):
        frame = GlobeRenderer(load_geo_index()).render(width=0, height=10)
        assert frame.width == 0
        assert frame.lines == ()
        assert frame.markers == ()

    def test_frame_has_land_rim_and_center_country(self):
        frame = GlobeRenderer(load_geo_index()).render(width=60, height=20)
        assert frame.width == 60
        assert frame.height == 20
        assert len(frame.lines) == 20
        assert all(len(line) == 60 for line in frame.lines)
        styles = {style for line in frame.lines for _, style in line}
        assert STYLE_LAND in styles
        assert frame.center_country is not None
        assert "+" in frame.plain()

    def test_ascii_mode_uses_ascii_glyphs(self):
        frame = GlobeRenderer(load_geo_index(), ascii_mode=True).render(
            width=60, height=20
        )
        text = frame.plain()
        assert "#" in text
        assert not any("\u2800" <= char <= "\u28ff" for char in text)

    def test_golden_globe(self):
        frame = GlobeRenderer(load_geo_index()).render(
            width=48, height=16, center_latitude=20, center_longitude=0
        )
        expected = (GOLDEN / "globe_48x16.txt").read_text(encoding="utf-8")
        assert frame.plain() == expected

    def test_markers_use_priority_playing_selected_favorite_station(self):
        stations = [
            make_station("plain", 48.85, 2.35),
            make_station("favorite", 48.85, 2.35),
            make_station("selected", 48.85, 2.35),
            make_station("playing", 48.85, 2.35),
        ]
        renderer = GlobeRenderer(load_geo_index())
        frame = renderer.render(
            width=60,
            height=20,
            center_latitude=48.85,
            center_longitude=2.35,
            stations=stations,
            selected_id="selected",
            playing_id="playing",
            favorite_ids={"favorite"},
        )
        assert {marker.station.id for marker in frame.markers} == {
            "plain",
            "favorite",
            "selected",
            "playing",
        }
        glyphs = {char for line in frame.lines for char, _ in line}
        assert "◉" in glyphs
        assert "◇" not in glyphs
        assert "★" not in glyphs

    @pytest.mark.parametrize(
        ("selected", "playing", "favorites", "expected"),
        [
            (None, "playing", set(), "◉"),
            ("selected", None, set(), "◇"),
            (None, None, {"favorite"}, "★"),
            (None, None, set(), "●"),
        ],
    )
    def test_single_marker_glyph_per_priority(
        self, selected, playing, favorites, expected
    ):
        stations = [make_station("station", 48.85, 2.35)]
        frame = GlobeRenderer(load_geo_index()).render(
            width=60,
            height=20,
            center_latitude=48.85,
            center_longitude=2.35,
            stations=stations,
            selected_id="station" if selected else None,
            playing_id="station" if playing else None,
            favorite_ids={"station"} if favorites else set(),
        )
        glyphs = {char for line in frame.lines for char, _ in line}
        assert expected in glyphs

    def test_offscreen_station_is_not_marked(self):
        stations = [make_station("hidden", -48.85, -177.65)]
        frame = GlobeRenderer(load_geo_index()).render(
            width=60,
            height=20,
            center_latitude=48.85,
            center_longitude=2.35,
            stations=stations,
        )
        assert frame.markers == ()

    def test_station_at_center_replaces_the_reticle(self):
        stations = [make_station("center", 20, 0)]
        frame = GlobeRenderer(load_geo_index()).render(
            width=60, height=20, center_latitude=20, center_longitude=0, stations=stations
        )
        center = frame.lines[10][30]
        assert center == ("●", STYLE_STATION)

    def test_country_at_cell_uses_the_inverse_projection(self):
        renderer = GlobeRenderer(load_geo_index())
        country = renderer.country_at_cell(
            30,
            10,
            width=60,
            height=20,
            center_latitude=48.85,
            center_longitude=2.35,
            zoom=1.0,
        )
        assert country is not None
        assert country.code == "FR"
        assert (
            renderer.country_at_cell(
                0,
                0,
                width=60,
                height=20,
                center_latitude=48.85,
                center_longitude=2.35,
                zoom=1.0,
            )
            is None
        )

    def test_station_at_cell_picks_the_nearest_marker(self):
        renderer = GlobeRenderer(load_geo_index())
        markers = (
            make_station("a", 48.85, 2.35),
            make_station("b", 48.85, 2.35),
        )
        frame = renderer.render(
            width=60,
            height=20,
            center_latitude=48.85,
            center_longitude=2.35,
            stations=markers,
        )
        nearest = renderer.station_at_cell(30, 10, frame.markers)
        assert nearest is not None
        assert nearest.column == 30 and nearest.row == 10
        assert renderer.station_at_cell(0, 0, frame.markers) is None
        assert renderer.station_at_cell(30, 10, ()) is None
