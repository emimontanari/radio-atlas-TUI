"""Keyboard help modal."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

SECTIONS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Browse",
        (
            ("1 / 2 / 3 / 4", "World, favorites, recent, genres"),
            ("c", "Countries and cities"),
            ("enter", "Open or play the selected row"),
            ("esc", "Go back one level"),
            ("j / k or ↑ / ↓", "Select rows; station names stay in view"),
            ("h / l or ← / →", "Move across browse-list columns"),
            ("g / G", "Jump to top or bottom"),
            ("ctrl+d / ctrl+u", "Half-page down or up"),
            ("tab", "Cycle focus between map and lists"),
        ),
    ),
    (
        "Playback",
        (
            ("space", "Play or pause the selection"),
            ("s", "Stop"),
            ("n / p", "Next or previous station"),
            ("[ / ]", "Volume down or up"),
            ("m", "Mute"),
            ("r", "Random station, or within the active genre"),
        ),
    ),
    (
        "Map",
        (
            ("H / L", "Rotate west or east"),
            ("J / K", "Tilt south or north"),
            ("+ / -", "Zoom in or out"),
            ("0", "Reset the map"),
            ("click", "Play a station or open a country"),
        ),
    ),
    (
        "Clickable controls",
        (
            ("Search", "Click the search icon or press /; underline-only field"),
            ("Tabs", "World │ Favorites │ Recent"),
            ("Transport", "Previous, play/pause, next, stop icons (p, space, n, s)"),
            ("Volume", "Click a VOL segment to set it; the speaker icon (right group) mutes"),
            ("Stars", "Click the star icon at the row's right edge; f toggles"),
            ("Player star", "Outline/filled star icon right after the station name"),
            ("Font", "Select a Nerd Font in your terminal; --ascii avoids icons"),
            ("Footer", "Click a key chip to run it; narrow views drop chips"),
            ("LIVE", "Green only while playing; PAUSED/STOPPED otherwise"),
            ("Compact view", "Map becomes a context strip; all keys still work"),
        ),
    ),
    (
        "More",
        (
            ("/", "Search stations or filter lists"),
            ("f", "Add or remove a favorite"),
            ("R", "Refresh the Radio Browser catalog"),
            ("?", "Toggle this help"),
            ("q", "Quit"),
        ),
    ),
)


def help_content() -> Text:
    text = Text()
    text.append("RADIO ATLAS", style="bold #b49cf0")
    text.append(" · keys\n", style="italic #9a9aa8")
    text.append("A map of live radio. No account, no tracking.\n", style="#9a9aa8")
    for heading, rows in SECTIONS:
        text.append("\n")
        text.append(heading.upper(), style="bold #b49cf0")
        text.append("\n")
        for keys, description in rows:
            text.append(f"› {keys:<18}", style="bold #e4e4ec")
            text.append(f"{description}\n", style="#e4e4ec")
    text.append("\nPress ? or esc to close.", style="italic #9a9aa8")
    return text


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("question_mark", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: #090b0d 70%;
    }
    #help-dialog {
        width: 72;
        max-width: 100%;
        height: 85%;
        max-height: 85%;
        background: #111119;
        border: round #b49cf0;
        padding: 1 2;
    }
    #help-scroll {
        height: 1fr;
        scrollbar-color: #41414d;
        scrollbar-color-hover: #9a9aa8;
        scrollbar-color-active: #b49cf0;
        scrollbar-background: #111119;
    }
    #help-content {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            with VerticalScroll(id="help-scroll"):
                yield Static(help_content(), id="help-content")

    def on_mount(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).focus()

    def action_close(self) -> None:
        self.dismiss(None)
