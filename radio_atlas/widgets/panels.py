"""Header, now-playing panel, volume bar and key footer."""

from __future__ import annotations

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget

from ..models import Station, format_count
from ..player import PlayerState

ACCENT = "#b49cf0"
ACCENT_INK = "#14101f"
ACCENT_DIM = "#8a7bc2"  # tenue violet for secondary headings
FAVORITE_COLOR = "#f5c542"
TEXT = "#e4e4ec"
MUTED = "#9a9aa8"
DIM = "#3f3f52"
RULE = "#6f5fa8"
LIVE = "#65d69a"
WARN = "#f0c36a"
ERROR = "#f87171"


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


# Font Awesome codepoints used by Nerd Fonts (FA 4.7 naming). These are
# private-use glyphs, not standard Unicode symbols; users need a Nerd Font.
ICON_CODEPOINTS = {
    "star": 0xF005,
    "star_outline": 0xF006,
    "play": 0xF04B,
    "pause": 0xF04C,
    "step_backward": 0xF048,
    "step_forward": 0xF051,
    "stop": 0xF04D,
    "volume_up": 0xF028,
    "volume_off": 0xF026,
    "search": 0xF002,
    "signal": 0xF012,
}
ICONS = {name: chr(codepoint) for name, codepoint in ICON_CODEPOINTS.items()}
ASCII_ICONS = {
    "star": "[*]", "star_outline": "[ ]", "play": ">", "pause": "||",
    "step_backward": "<", "step_forward": ">", "stop": "[]",
    "volume_up": "^", "volume_off": "x", "search": "/", "signal": "#",
}


def icon_text(name: str, *, ascii_mode: bool = False, active: bool = False) -> Text:
    """Return one named Nerd Font icon, with an explicit ASCII-mode fallback."""
    glyph = (ASCII_ICONS if ascii_mode else ICONS)[name]
    style = (
        f"bold {FAVORITE_COLOR}" if name == "star" and active
        else MUTED if name == "star_outline"
        else None if name in ("play", "pause")
        else f"bold {ACCENT}" if name == "volume_off"
        else TEXT
    )
    return Text(glyph, style=style or "", no_wrap=True, justify="center")


def star_text(active: bool, *, ascii_mode: bool = False) -> Text:
    """Recognizable outline/filled font star; no custom dot art or text label."""
    return icon_text("star" if active else "star_outline", ascii_mode=ascii_mode, active=active)


# -- header ------------------------------------------------------------------

SOURCE_LABELS = {
    "network": ("ONLINE", LIVE),
    "cache": ("CACHE OFFLINE", WARN),
    "seed": ("SEED OFFLINE", MUTED),
}


class AtlasHeader(Widget):
    DEFAULT_CSS = """
    AtlasHeader {
        height: 1;
        padding: 0 1;
        background: #0c0c15;
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
        label, color = SOURCE_LABELS.get(self.source, SOURCE_LABELS["seed"])
        ascii_mode = bool(getattr(getattr(self.app, "renderer", None), "ascii_mode", False))
        source_icon = ASCII_ICONS["signal"] if ascii_mode else ICONS["signal"]
        # The search field sits to the right in wide layouts; narrow ones give it its own row.
        divider = Text("" if self.app.has_class("narrow") else " │", style=RULE)
        badge = Text(f"{source_icon} {label}", style=f"bold {color}")
        prefix = Text()
        ascii_mode = bool(getattr(getattr(self.app, "renderer", None), "ascii_mode", False))
        prefix.append(icon_text("signal", ascii_mode=ascii_mode))
        prefix.append(" │ ", style=RULE)
        prefix.append("RADIO ATLAS", style=f"bold {ACCENT}")
        prefix.append(" │ ", style=RULE)
        room = width - prefix.cell_len - badge.cell_len - divider.cell_len - 1
        context = Text(
            _clip(f"{self.mode_label} · {format_count(self.count)} {self.unit}", room),
            style=f"bold {TEXT}",
        )
        left = Text()
        left.append_text(prefix)
        left.append_text(context)
        right = Text()
        right.append_text(badge)
        right.append_text(divider)
        text = Text(no_wrap=True, overflow="crop")
        text.append_text(_pad(left, right, width))
        return text


class Transport(Horizontal):
    """Single control row: transport group on the left, speaker + VOL group on the right.

    Below `MIN_WIDTH` columns the volume group wraps onto a second row (class `wrapped`).
    """

    # 20 (prev, play, next, stop with 2-col gaps) + 2 (gap) + 3 (speaker) + 1 + 15 (VOL, 6 slots, %)
    MIN_WIDTH = 41

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(self.content_size.width < self.MIN_WIDTH, "wrapped")


# -- now playing -------------------------------------------------------------

PAD = 2  # columns of horizontal padding shared by the info lines and the controls


class PlayerInfo(Container):
    """Info block: NowPlaying text with the favorite icon floating right after the name."""

    def place_favorite(self) -> None:
        buttons = self.query("#player-favorite")
        if not buttons:
            return
        info = self.query_one(NowPlaying)
        button = buttons.first()
        button.styles.width = info.favorite_reserve()
        # Row 2 = station line (row 0 is the top rule, row 1 the NOW PLAYING heading).
        button.styles.offset = (info.favorite_column(), 2)


class NowPlaying(Widget):
    DEFAULT_CSS = """
    NowPlaying {
        height: 4;
        padding: 0 2;
        background: #0c0c15;
        border-top: solid #6f5fa8;
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
        self.refresh()
        self._place_favorite()

    def on_resize(self, event: events.Resize) -> None:
        self._place_favorite()

    def _place_favorite(self) -> None:
        place = getattr(self.parent, "place_favorite", None)
        if place is not None:
            place()

    def _glyphs(self) -> dict[str, str]:
        ascii_mode = bool(getattr(getattr(self.app, "renderer", None), "ascii_mode", False))
        return ASCII_ICONS if ascii_mode else ICONS

    def _content_width(self) -> int:
        return self.content_size.width or 60

    def favorite_reserve(self) -> int:
        """Cells for the favorite target: gap + glyph + trailing cell."""
        return cell_len(self._glyphs()["star"]) + 2

    def _station_name(self) -> str:
        station = self.state.station or self.selected
        name = station.name if station else "Nothing playing"
        return _clip(name, max(4, self._content_width() - self.favorite_reserve()))

    def favorite_column(self) -> int:
        """Column (from the widget's left edge) where the favorite target starts."""
        return PAD + cell_len(self._station_name())

    def _state_label(self, glyphs: dict[str, str]) -> Text:
        state = self.state
        station = state.station or self.selected
        if state.error or state.status in ("error", "unavailable"):
            return Text(state.error or "ERROR", style=ERROR)
        if state.status == "playing" and station is not None:
            return Text(f"{glyphs['signal']} LIVE", style=f"bold {LIVE}")
        if state.status == "paused":
            return Text("PAUSED", style=f"bold {ACCENT}")
        return Text("STOPPED", style=f"bold {MUTED}")

    def _meta_line(self, width: int) -> Text:
        state = self.state
        station = state.station or self.selected
        if station is None:
            return Text("Press space on a station to tune in", style=f"italic {MUTED}")
        if state.title:
            lead = f"{state.artist} — {state.title}" if state.artist else state.title
        else:
            lead = " · ".join(part for part in (station.country_label, station.state) if part)
        tail = " · ".join(
            part
            for part in (station.codec, f"{station.bitrate} kbps" if station.bitrate else "")
            if part
        )
        suffix = f" · {tail}" if tail and lead else tail
        room = width - cell_len(suffix)
        text = _clip(lead, room) + suffix if room >= 4 else _clip(lead + suffix, width)
        return Text(text or "No metadata", style=MUTED)

    def render(self) -> Text:
        width = self._content_width()
        station = self.state.station or self.selected
        heading = Text("NOW PLAYING", style=ACCENT_DIM)
        status = self._state_label(self._glyphs())
        status.truncate(max(0, width - heading.cell_len - 2), overflow="ellipsis")
        first = _pad(heading, status, width) if status.plain else heading
        name = Text(
            self._station_name(), style=f"bold {TEXT}" if station else f"bold {MUTED}"
        )
        text = Text(no_wrap=True, overflow="crop")
        for index, line in enumerate((first, name, self._meta_line(width))):
            if index:
                text.append("\n")
            text.append_text(line)
        return text


# -- volume ------------------------------------------------------------------


class VolumeBar(Widget):
    """`VOL ▮▮▮▮▯▯ 85%`: one grouped control; clicking a segment sets the level."""

    LABEL = "VOL "
    READOUT = 5  # " 85%" / " 100%": a space, the level and the percent sign
    MIN_SLOTS = 6
    MAX_SLOTS = 24  # keep in step with `#volume-bar { max-width }` (4 + 24 + 5)

    class Changed(Message):
        """The user clicked a segment; carries the requested volume (0-100)."""

        def __init__(self, volume: int) -> None:
            super().__init__()
            self.volume = volume

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.volume = 70
        self.muted = False
        self.tooltip = "Click a segment to set volume · [ ] step"

    def update_state(self, volume: int, muted: bool) -> None:
        self.volume = max(0, min(100, volume))
        self.muted = muted
        self.refresh()

    def _geometry(self) -> tuple[str, int]:
        """The label to show and the number of segments that fit."""
        width = self.size.width
        label = self.LABEL if width - len(self.LABEL) - self.READOUT >= 3 else ""
        return label, max(0, min(self.MAX_SLOTS, width - len(label) - self.READOUT))

    def render(self) -> Text:
        label, slots = self._geometry()
        filled = round(self.volume / 100 * slots)
        text = Text(no_wrap=True, overflow="crop")
        text.append(label, style=MUTED)
        text.append("▮" * filled, style=MUTED if self.muted else ACCENT)
        text.append("▮" * (slots - filled), style=DIM)
        text.append(
            f" {self.volume}%".ljust(self.READOUT),
            style=f"bold {ACCENT}" if self.muted else TEXT,
        )
        return text

    def on_click(self, event: events.Click) -> None:
        label, slots = self._geometry()
        index = event.x - len(label)
        if slots and 0 <= index < slots:
            event.stop()
            self.post_message(self.Changed(round((index + 1) / slots * 100)))


# -- footer: key chips and toast ---------------------------------------------

TONE_STYLES = {
    "info": (MUTED, "·"),
    "good": (LIVE, "✓"),
    "warn": (WARN, "!"),
    "error": (ERROR, "✕"),
}

# Chips are dropped lowest priority first when the row is too narrow.
CHIP_PRIORITY = ("space", "q", "question_mark", "slash", "f", "2", "1", "3", "r", "c", "4")


class KeyFooter(Widget):
    """Rule row (doubles as the transient toast) above a row of key chips."""

    # Seconds a message stays on the rule row; errors linger longest.
    DURATIONS = {"info": 3.0, "good": 3.0, "warn": 8.0, "error": 12.0}

    DEFAULT_CSS = """
    KeyFooter {
        height: 2;
        background: #0c0c15;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._notice: tuple[str, str] | None = None
        self._timer: Timer | None = None

    def set_notice(self, message: str, tone: str = "info") -> None:
        if self._timer is not None:
            self._timer.stop()
        self._notice = (message, tone)
        self._timer = self.set_timer(
            self.DURATIONS.get(tone, self.DURATIONS["info"]), self._expire
        )
        self.refresh()

    def _expire(self) -> None:
        self._notice = None
        self._timer = None
        self.refresh()

    @property
    def notice(self) -> tuple[str, str] | None:
        return self._notice

    def _binding_items(self) -> list[tuple[str, str, str, str]]:
        """(binding key, key label, description, action) for each visible binding."""
        items = []
        for binding in self.app.BINDINGS:
            if isinstance(binding, Binding) and binding.show:
                items.append((
                    binding.key,
                    self.app.get_key_display(binding),
                    binding.description,
                    binding.action,
                ))
        return items

    def _rule_line(self, width: int) -> Text:
        rule = Style(color=RULE)
        if self._notice is None:
            return Text("─" * width, style=rule)
        message, tone = self._notice
        color, icon = TONE_STYLES.get(tone, TONE_STYLES["info"])
        body = _clip(f"{icon} {message}", max(1, width - 6))
        line = Text(no_wrap=True, overflow="crop")
        line.append("─" * max(0, width - len(body) - 4), style=rule)
        line.append(f" {body} ", style=Style(color=color, bold=True))
        line.append("──", style=rule)
        return line

    def _chip_line(self, width: int) -> Text:
        items = self._binding_items()
        sizes = {item[0]: len(item[1]) + 3 + len(item[2]) for item in items}
        order = [k for k in CHIP_PRIORITY if k in sizes] + [
            item[0] for item in items if item[0] not in CHIP_PRIORITY
        ]
        room = width - 2
        keep: set[str] = set()
        used = 0
        for key in order:
            need = sizes[key] + (1 if keep else 0)
            if used + need <= room:
                keep.add(key)
                used += need
        shown = [item for item in items if item[0] in keep]
        gap = 2 if used + len(shown) - 1 <= room else 1
        line = Text(no_wrap=True, overflow="crop")
        line.append(" ")
        for index, (_, label, description, action) in enumerate(shown):
            meta = {"action": action}
            if index:
                line.append(" " * gap)
            line.append(f" {label} ", style=Style.parse(f"bold {ACCENT_INK} on {ACCENT}") + Style(meta=meta))
            line.append(f" {description}", style=Style(color=TEXT, meta=meta))
        return line

    def render(self) -> Text:
        width = self.size.width or 80
        text = Text(no_wrap=True, overflow="crop")
        text.append_text(self._rule_line(width))
        text.append("\n")
        text.append_text(self._chip_line(width))
        return text

    async def on_click(self, event: events.Click) -> None:
        action = event.style.meta.get("action")
        if action:
            event.stop()
            await self.app.run_action(f"app.{action}")
