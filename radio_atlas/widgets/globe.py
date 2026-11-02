"""Interactive braille globe widget."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from ..globe import (
    STYLE_FAVORITE,
    STYLE_FOCUS,
    STYLE_LAND,
    STYLE_OCEAN,
    STYLE_PLAYING,
    STYLE_RETICLE,
    STYLE_RIM,
    STYLE_SELECTED,
    STYLE_STATION,
    GlobeFrame,
    GlobeRenderer,
)
from ..models import Country, Station

STYLE_COLORS = {
    STYLE_OCEAN: "on #090b0d",
    STYLE_LAND: "#303b44",
    STYLE_FOCUS: "#8580ad",
    STYLE_RIM: "#41454d",
    STYLE_STATION: "#c4cad0",
    STYLE_PLAYING: "bold #b1a9dc",
    STYLE_FAVORITE: "bold #c6c6cd",
    STYLE_SELECTED: "bold #a5a0c4",
    STYLE_RETICLE: "#777781",
}


class GlobeWidget(Widget, can_focus=True):
    """Renders the orthographic globe and reports clicks as messages."""

    class StationActivated(Message):
        def __init__(self, station: Station) -> None:
            self.station = station
            super().__init__()

    class CountryActivated(Message):
        def __init__(self, country: Country) -> None:
            self.country = country
            super().__init__()

    DEFAULT_CSS = """
    GlobeWidget {
        background: #090b0d;
    }
    """

    def __init__(self, renderer: GlobeRenderer, **kwargs) -> None:
        super().__init__(**kwargs)
        self.renderer = renderer
        self.center_latitude = 20.0
        self.center_longitude = 0.0
        self.zoom = 1.0
        self.stations: list[Station] = []
        self.selected_id: str | None = None
        self.playing_id: str | None = None
        self.favorite_ids: set[str] = set()
        self._frame: GlobeFrame | None = None

    def configure(
        self,
        *,
        center_latitude: float | None = None,
        center_longitude: float | None = None,
        zoom: float | None = None,
        stations: list[Station] | None = None,
        selected_id: str | None = None,
        playing_id: str | None = None,
        favorite_ids: set[str] | None = None,
    ) -> None:
        if center_latitude is not None:
            self.center_latitude = center_latitude
        if center_longitude is not None:
            self.center_longitude = center_longitude
        if zoom is not None:
            self.zoom = zoom
        if stations is not None:
            self.stations = stations
        self.selected_id = selected_id
        self.playing_id = playing_id
        if favorite_ids is not None:
            self.favorite_ids = favorite_ids
        self.refresh()

    def render(self) -> Text:
        width, height = self.content_size
        if width <= 0 or height <= 0:
            self._frame = None
            return Text("")
        frame = self.renderer.render(
            width=width,
            height=height,
            center_latitude=self.center_latitude,
            center_longitude=self.center_longitude,
            zoom=self.zoom,
            stations=self.stations,
            selected_id=self.selected_id,
            playing_id=self.playing_id,
            favorite_ids=self.favorite_ids,
        )
        self._frame = frame
        text = Text(no_wrap=True, overflow="crop")
        for row_index, row in enumerate(frame.lines):
            if row_index:
                text.append("\n")
            for character, style in row:
                text.append(character, style=STYLE_COLORS.get(style, ""))
        return text

    def on_click(self, event: events.Click) -> None:
        frame = self._frame
        if frame is None:
            return
        marker = self.renderer.station_at_cell(
            event.x, event.y, frame.markers, radius=1
        )
        if marker is not None:
            self.post_message(self.StationActivated(marker.station))
            return
        country = self.renderer.country_at_cell(
            event.x,
            event.y,
            width=frame.width,
            height=frame.height,
            center_latitude=self.center_latitude,
            center_longitude=self.center_longitude,
            zoom=self.zoom,
        )
        if country is not None:
            self.post_message(self.CountryActivated(country))

    def on_resize(self, event: events.Resize) -> None:
        self.refresh()
