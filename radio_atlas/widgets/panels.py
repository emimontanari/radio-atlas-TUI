"""Header, now-playing panel and status bar."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static

from ..models import Station, format_count
from ..player import PlayerState


def _clip(value: str, width: int) -> str:
    if width <= 0:
        return ""
    text = Text(value)
    text.truncate(width, overflow="ellipsis")
    return text.plain


def _pad(left: Text, right: Text, width: int) -> Text:
    gap = max(1, width - left.cell_len - right.cell_len)
    line = Text()
    line.append_text(left)
    line.append(" " * gap)
    line.append_text(right)
    return line


SOURCE_LABELS = {
    "network": ("● ONLINE", "#c6c6cd"),
    "cache": ("◐ CACHE OFFLINE", "#a5a0c4"),
    "seed": ("○ SEED OFFLINE", "#888892"),
}


class AtlasHeader(Widget):
    DEFAULT_CSS = """
    AtlasHeader {
        height: 3;
        padding: 0 1;
        background: #111119;
        border-bottom: solid #292933;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode_label = "WORLD"
        self.count = 0
        self.unit = "STATIONS"
        self.source = "seed"

    def update_header(
        self, *, mode_label: str, count: int, source: str, unit: str = "STATIONS"
    ) -> None:
        self.mode_label = mode_label
        self.count = count
        self.unit = unit
        self.source = source
        self.refresh()

    def render(self) -> Text:
        width = self.content_size.width or 80
        brand = Text("RADIO ATLAS", style="bold #c6c6cd")
        context = Text(
            f"{self.mode_label} · {format_count(self.count)} {self.unit}",
            style="bold #c6c6cd",
        )
        label, color = SOURCE_LABELS.get(self.source, SOURCE_LABELS["seed"])
        badge = Text(label, style=f"bold {color}")
        line_one = brand
        line_two = _pad(context, badge, width)
        text = Text(no_wrap=True, overflow="crop")
        text.append_text(line_one)
        text.append("\n")
        text.append_text(line_two)
        return text


class Transport(Horizontal):
    """Control row that tells the app how much room the buttons have."""

    # Widths: 26 cells of icon buttons, plus the favorite button (5 short, 12 full)
    # and a 4-cell volume readout.
    FULL_FAVORITE = 38
    READOUT = 35

    def on_resize(self, event: events.Resize) -> None:
        width = event.size.width
        wide = width >= self.FULL_FAVORITE
        changed = self.has_class("short-favorite") == wide
        self.set_class(not wide, "short-favorite")
        self.set_class(width < self.READOUT + (7 if wide else 0), "no-readout")
        if changed:
            self.call_after_refresh(self.app.refresh_favorite_views)


class NowPlaying(Widget):
    DEFAULT_CSS = """
    NowPlaying {
        height: 8;
        padding: 0 1;
        background: #111119;
        border-top: solid #292933;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = PlayerState()
        self.selected: Station | None = None
        self.source = "seed"

    def update_view(
        self,
        state: PlayerState,
        *,
        selected: Station | None = None,
        source: str = "seed",
    ) -> None:
        self.state = state
        self.selected = selected
        self.source = source
        self.border_title = "NOW PLAYING" if state.status in ("playing", "paused") else "PLAYER"
        self.refresh()

    def render(self) -> Text:
        width = self.content_size.width or 60
        state = self.state
        station = state.station or self.selected

        if state.status == "playing":
            glyph, tone = "▶", "#c6c6cd"
        elif state.status == "paused":
            glyph, tone = "⏸", "#a5a0c4"
        elif state.status in ("error", "unavailable"):
            glyph, tone = "⚠", "#f87171"
        else:
            glyph, tone = "■", "#777781"

        name = station.name if station else "Nothing playing"
        title = Text()
        title.append(f" {glyph} ", style=f"bold {tone}")
        reserve = 12 if station and state.status == "playing" else 4
        if state.muted:
            reserve += 7
        title.append(
            _clip(name, max(8, width - reserve)),
            style=f"bold {tone}" if station else "#777781",
        )
        if station and state.status == "playing":
            title.append("  ● LIVE", style="bold #65d69a")
        if state.muted:
            title.append("  MUTED", style="bold #a5a0c4")

        if state.title:
            second = Text(
                _clip(
                    f"{state.artist} — {state.title}" if state.artist else state.title,
                    width,
                ),
                style="#c6c6cd",
            )
        elif station is not None:
            second = Text(
                _clip(station.tagline or station.meta or "No metadata", width),
                style="#888892",
            )
        else:
            second = Text("Press space on a station to tune in", style="italic #777781")

        if station is not None:
            compact = width < 52
            reserve = 15 if compact else 20
            meta = Text(
                _clip(
                    " · ".join(
                        part
                        for part in (
                            station.country_label,
                            station.state,
                            station.codec,
                            f"{station.bitrate} kbps" if station.bitrate else "",
                        )
                        if part
                    ),
                    max(8, width - reserve),
                ),
                style="#777781",
            )
            volume = self._volume_text(width, compact=compact)
            third = _pad(meta, volume, width)
        else:
            third = self._volume_text(width)

        fourth = Text()
        if state.error:
            fourth.append(_clip(state.error, width), style="#f87171")
        elif state.status == "paused":
            fourth.append("Paused — space resumes", style="#a5a0c4")
        elif state.status == "stopped" and station is not None:
            fourth.append("Stopped — space tunes in", style="#777781")
        elif self.source == "network":
            fourth.append("Streaming live from Radio Browser", style="#777781")
        else:
            fourth.append("Offline catalog — browsing stays available", style="#777781")

        text = Text(no_wrap=True, overflow="crop")
        for index, line in enumerate((title, second, third, fourth)):
            if index:
                text.append("\n")
            text.append_text(line)
        return text

    def _volume_text(self, width: int, *, compact: bool = False) -> Text:
        volume = max(0, min(100, self.state.volume))
        slots = 5 if compact else 10
        filled = round(volume / (100 / slots))
        bar = "▮" * filled + "▯" * (slots - filled)
        text = Text()
        text.append(f"VOL {bar} {volume:>3}", style="#888892")
        if self.state.muted:
            text.append(" ✕", style="bold #a5a0c4")
        return text


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        padding: 0 1;
        background: #111119;
        color: #888892;
    }
    """

    def set_message(self, message: str, tone: str = "info") -> None:
        colors = {
            "info": "#888892",
            "good": "#c6c6cd",
            "warn": "#a5a0c4",
            "error": "#f87171",
        }
        self.update(Text(message, style=colors.get(tone, colors["info"])))
