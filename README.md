# Radio Atlas TUI

**World radio, one terminal.**

```text
                           ⠂⣀⣀⣠⢤⡤⠤⠤⣄⣀⣀⠂
                       ⠂⣀⣤⣶⣿⣿⠿⠿⠄  ⠠⠌⠉⠁●●●●⠂
                     ⠂⣴⣾⠿⣿⣿⣿      ⣠⢾⣿⣶⣦⡑ ●●●⡀
                   ⠂⡐⠘⠉⢁⣄⢽⣿⣷⠐⢀   ⡠⣘⡵⡤⢄⡈⠛⠂   ●●⠂
                  ⠂⠂⠁      ⢘⣴⣿⣿⣶⣶⣾⣽⣽⡿⠠⢩⣤⣤⣤⣀   ⠂⠂
                 ⠂⠂        ⠐⠉⠉⠙⢿⣿⣿⣿⣿⣷⣤⣤⣸⣿⣯⣨    ⠂⠂
                ⠂⠂⠂            ⠈●⣿⣿⣿⣿⣿⣿⣿●●●    ⠂⠂⠂
                ⠂⠂              ⢸●⣿⣿⣿⣿⣿⣿⣿●⠄     ⠂⠂
                ⠂⠂              ⠈◉⣿⣿⣿⣿⣿⣿⡿⠿⡀     ⠂⠂
                ⠂⠂                ⠹⡻⣿⣿⣿⠁  ⠄⠒⠐ ⢠⢀⠠⠂
                ⠂⠂⠂                ⠈⠊⠻⣿⣦⣤⣇⣤ ⢠⣶⣿⣿⡇⠂
                 ⠂⠂                       ⠈ ●⣿⣿⡟⠂
                  ⠂⠂                       ⢸⣿⣿⡟⠂
                   ⠂⠂⠂                      ⢩⠏⠂
                     ⠂⠂⠂                  ⠂⠔⠁
                       ⠂⠂⠂⠂⠂          ⠂⠂⠂⠂⠂
                           ⠂⠂⠂⠂⠂⠂⠂⠂⠂⠂⠂⠂
```

Radio Atlas is a keyboard-driven terminal application for discovering and
playing live radio from around the world. A braille globe is the navigation
surface: rotate it, tilt it, zoom in, click a country, and drill from country
to city to station without ever leaving the terminal.

Built with [Textual](https://textual.textualize.io/), the
[Radio Browser](https://www.radio-browser.info/) directory, and
[mpv](https://mpv.io/) for playback. No account, no telemetry, no browser tab.

## Quick start

| You need | Why |
| --- | --- |
| Python 3.11+ on macOS or Linux | runs the app |
| `mpv` | playback; browsing works without it |
| A **Nerd Font** selected in your terminal | every UI icon is a Font Awesome glyph from the Nerd Fonts private-use range; without one they render as empty boxes (tofu). `--ascii` swaps icons for ASCII instead |

```bash
uv tool install .    # or: pipx install .
radio-atlas
```

Radio Atlas never installs fonts or edits terminal settings. Pick a Nerd Font
in your terminal's own font settings. Full steps are in [Install](#install).

![Radio Atlas playing RTL from the live directory](docs/screenshot.png)

---

## The idea

Radio directories are lists. Lists are efficient, but they hide the one thing
that makes world radio interesting: **where the signal comes from**.

Radio Atlas puts geography first. The globe is not decoration; it is the
primary index. Every station you can play has a coordinate, and every country
you can open is a shape on the map. Search and lists exist for when you already
know what you want. The map exists for when you do not.

```text
 [signal] │ RADIO ATLAS │ SEARCH · 92 STATIONS         [signal] ONLINE │ [search] lofi█
──────────────────────────────────────────────────────────────────────────────────────
                                    │ World │ Favorites │ Recent
                                    │ 92 STATIONS
         braille globe              │ ▶ Lofi 24/7                           [star ●]
      rotate · tilt · zoom          │   US · MP3 · 128 kbps
                                    │   lofi girl                           [star ○]
        ●      ◉      ●             │   US · MP3
              ●                     ├────────────────────────────────────────────────
                                    │  NOW PLAYING                      [signal] LIVE
                                    │  Lofi 24/7 [star ●]
                                    │  franceinfo-midfi.mp3 · MP3 · 128 kbps
                                    │
                                    │  [prev] [pause] [next] [stop]   [spk] VOL ▮▮▮▮▮▮▮▮ 85%
───────────────────────────────── ✓ Added Lofi 24/7 to favorites ─────────────────────
  1 World  2 Favs  3 Recent  4 Genres  c Browse  / Find  space Play/Pause  r Random ...
```

`[name]` marks a Nerd Font icon (Font Awesome glyph). `[star ●]` is the filled
yellow star (`#f5c542`, favorite) and `[star ○]` the muted outline star.

| Area | What you see |
| --- | --- |
| Header (1 row) | signal icon, `RADIO ATLAS`, `MODE · N STATIONS`, source badge (green `ONLINE`, amber `CACHE OFFLINE`, grey `SEED OFFLINE`), underlined search field with a search icon |
| Globe (left) | braille map; fills the left half in wide terminals |
| Tabs and count | `World │ Favorites │ Recent` (active tab underlined), then a muted station count |
| Station rows | two lines each (name, then `CC · codec · kbps`); `▶` marks the playing or paused station, the cursor row is tinted lavender, the star column on the right is clickable |
| Player (6 rows) | rule; `NOW PLAYING` on the left with the state on the right; bold station name with its star right after it; muted `title · CODEC · NNN kbps`; one blank row; controls |
| Controls row | left: Previous, Play/Pause (lavender pill), Next, Stop. Right: speaker, `VOL` bar, percentage |
| Footer (2 rows) | rule that doubles as the toast line, then clickable key chips |

One list is visible at a time; `esc` walks back up the hierarchy.

Four ways in, one globe: **world** (most-clicked stations), **countries and
cities**, **genres**, and **search**. Favorites and recent history sit on top.

---

## The globe

The map is real geography, not an illustration. `scripts/build_geo_assets.py`
converts Natural Earth 1:110m country polygons into two compact assets:

- `countries.json` — 177 countries with ISO code, name, continent, and label
  coordinates;
- `worldmask.bin` — a 1440 × 720 byte mask where `0` is ocean and `1..255` is
  a country index.

The full GeoJSON is never shipped. At render time each terminal cell becomes a
2 × 4 braille grid, and every visible dot samples the mask through an inverse
orthographic projection:

```text
 one terminal cell  =  2 × 4 dots  =  8 braille bits

     ⠁  ⠂  ⠄  ⡀          dot 1 … dot 8 → bits 0 … 7 of U+2800
     ⠈  ⠐  ⠠  ⢀          a full cell is ⣿

     ⢀⣀⣀⣤⣤⣤⣤⣀⣀⡀        each dot asks worldmask.bin:
     ⣠⣴⣶⣿⣿⡿⠏⠉⠂⠁        "is this ocean, land, or the focused country?"
```

The same mask answers hit-testing after a click, so rendering and interaction
can never disagree. Rotation, tilt, and zoom are just changes to the projection
matrix followed by a redraw.

Markers are projected through the forward transform and placed in the nearest
cell:

```text
 ◉  playing        ◇  selected       ★  favorite
 ●  station        +  map centre     ▓  focused country
```

These are map markers drawn into the braille canvas. They are separate from the
Nerd Font star icons used by the station list and the player.

Press `H`/`L` to rotate, `J`/`K` to tilt, `+`/`-` to zoom, `0` to reset. On a
terminal without braille support, `--ascii` swaps the globe rasterizer for
`#` and plain glyphs; it also uses explicit ASCII aliases for action/favorite
icons (`<`, `>`, `[*]`, `[ ]`).

---

## Discovery and playback

```text
  Textual app
  ├── Globe renderer ──► worldmask.bin + countries.json
  ├── Player ──► mpv  (JSON IPC over a private unix socket)
  │              └─ missing mpv → NullPlayer, browsing stays up
  └── Directory client
        ├─ try  ──► Radio Browser mirrors ──► ● ONLINE
        ├─ then ─► disk cache             ──► ◐ CACHE OFFLINE
        └─ then ─► bundled seed catalog   ──► ○ SEED OFFLINE
```

**Directory.** `RadioBrowserClient` mirrors are discovered through
`all.api.radio-browser.info`, shuffled, and backed by a fixed fallback list. Up
to three mirrors are tried per request, and the first healthy base is reused.
Network failures never raise into the UI: each lookup degrades to the disk
cache, then to the bundled seed catalog, and the header always says which
source you are looking at.

**Search.** Three queries (`name`, `tag`, `country`) run in parallel, merge by
station UUID, and rank by name prefix, name substring, tag/country match, then
votes and clicks. Typing debounces for 350 ms and each request is tagged with a
generation number, so a slow response cannot overwrite newer results.

**Genres.** `radio_atlas/genres.py` curates 32 genres and maps each one to a
real Radio Browser tag (`Jazz` → `jazz`, `Hip-Hop` → `hip-hop`). The Genres
view (`4`) fetches `/json/tags` once for station counts and caches it, `/`
filters the list, `enter` loads that tag through `tagList`, and `r` tunes a
random station inside the genre. Without a network the same view falls back to
counts and stations derived from the seed catalog.

**Playback.** `MpvPlayer` launches mpv with `--no-video --idle=yes
--input-ipc-server=<socket>` and multiplexes newline-delimited JSON requests
and `property-change` events over one connection. The socket lives in a private
`mkdtemp` directory because macOS limits unix socket paths to about 104 bytes.
When mpv is missing, `NullPlayer` keeps every other feature usable and the
notice explains what to install.

---

## Install

Requirements: **Python 3.11+** on macOS or Linux, **mpv** for playback, and a
**Nerd Font** selected in your terminal for the UI icons.

```bash
# macOS
brew install mpv

# Debian / Ubuntu
sudo apt install mpv

# Fedora
sudo dnf install mpv

# Arch
sudo pacman -S mpv
```

Install the app:

```bash
uv tool install .
# or
pipx install .
```

From a checkout:

```bash
git clone https://github.com/emimontanari/radio-atlas-TUI.git
cd radio-atlas-TUI
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/radio-atlas
```

Browsing works without mpv; playback does not.

**Nerd Font.** Install any [Nerd Font](https://www.nerdfonts.com/) with your
system's usual method, then select it in your terminal's font settings (for
example iTerm2 → Profiles → Text, or the font option in Alacritty, kitty,
WezTerm or GNOME Terminal). Radio Atlas does not install fonts or change
terminal configuration. Without one the icons show as tofu boxes; run
`radio-atlas --ascii` to use ASCII icons and an ASCII globe instead.

---

## Usage

```bash
radio-atlas                 # braille globe
radio-atlas --ascii         # ASCII globe and ASCII icons (no Nerd Font needed)
radio-atlas --mpv /opt/mpv  # explicit mpv binary
radio-atlas --version
```

### Keys

| Key | Action |
| --- | --- |
| `1` / `2` / `3` | World, favorites, recent |
| `4` | Browse genres |
| `c` | Browse countries and cities |
| `/` | Search stations, or filter the active list |
| `enter` | Open the selected country/city or play the selected station |
| `esc` | Go back one level, or cancel search |
| `j` / `k` or `↑` / `↓` | Select rows; station names remain in view |
| `h` / `l` or `←` / `→` | Move across columns in browse lists |
| `g` / `G` | Jump to top or bottom |
| `ctrl+d` / `ctrl+u` | Half-page down or up |
| `tab` | Cycle focus between the map and lists |
| `space` | Play or pause the selection |
| `s` | Stop |
| `n` / `p` | Next or previous station |
| `[` / `]` | Volume down or up |
| `m` | Mute |
| `r` | Tune a random station, avoiding recent history — within the active genre when there is one |
| `f` | Add or remove a favorite |
| `H` / `L` | Rotate the globe west or east |
| `J` / `K` | Tilt the globe south or north |
| `+` / `-` | Zoom in or out |
| `0` | Reset the map |
| `R` | Refresh the Radio Browser catalog |
| `?` | Toggle help |
| `q` | Quit |

### Mouse and on-screen controls

| Control | Behavior |
| --- | --- |
| Globe marker / land | play that station / open that country |
| Search icon or field | start a search (same as `/`) |
| Tabs | switch World, Favorites, Recent |
| Row star (right edge) | toggle that station's favorite; does not play it or move the cursor |
| Player star (right after the name) | toggle the favorite of the playing station, or the selection when idle |
| Previous, Play/Pause, Next, Stop | same as `p`, `space`, `n`, `s`; hover for name and shortcut |
| Speaker icon | mute or unmute (same as `m`); shows the muted icon while muted |
| `VOL` bar segment | set the volume to that segment (saved like `[` / `]`) |
| Footer key chip | run that binding |

### Favorites

- Toggle with the row star, the player star or `f`; all three share one code
  path and stay in sync, including the globe markers and the Favorites tab.
- A favorite is a filled yellow star (`#f5c542`); a non-favorite is a muted
  outline. With `--ascii` they are `[*]` and `[ ]`.
- Favorites persist in `state.json` across restarts.

### Player states

| State | Header line (right side) |
| --- | --- |
| Playing | green signal icon + `LIVE`, shown only while playback is really playing |
| Paused | `PAUSED` |
| Stopped / idle | `STOPPED` |
| Error or mpv unavailable | the error text in red, ellipsized; the same message also appears as a toast |

The metadata line shows the stream's title (`artist — title` when known), or
`country · state` when there is none, followed by codec and bitrate. Long text
is ellipsized.

### Volume

The speaker icon, the `VOL` bar and the percentage form one group on the right
of the controls row. The bar holds at most 24 segments and the percentage
follows it after one space. Keyboard (`[`, `]`, `m`) and mouse use the same
path, and the level and mute state persist.

### Toasts

The old status bar is gone. Messages appear on the footer's rule line:

| Tone | Examples | Stays for |
| --- | --- | --- |
| info | Paused, Removed from favorites, genre and country counts | 3 s |
| good | Playing, Added to favorites | 3 s |
| warn | Nothing playing yet, offline country list | 8 s |
| error | stream failures, mpv missing | 12 s |

Connectivity is always shown by the header badge, and player errors also stay
in the player's state slot, so nothing depends on a toast being on screen.

### Responsive behavior

| Terminal width | Change |
| --- | --- |
| below 100 columns | search gets its own full-width row; the right panel widens to 2/3 |
| below 72 columns | the globe becomes a one-line map strip; the station list uses the full width |
| narrower panels | the volume bar shrinks first (down to 6 segments), never the percentage or the buttons; a gap of at least 2 columns separates the transport and volume groups |
| panel content below 41 columns | the volume group wraps to its own row (the player becomes 7 rows) |
| footer too short | key chips are dropped lowest-priority first |

Station and metadata text is ellipsized, there is no horizontal scrolling, and
resizing keeps the selected station. Every shortcut keeps working in every
layout; `?` opens a scrollable help list that fits the terminal.

### Icons

Icons are Font Awesome 4.7 glyphs in the Nerd Fonts private-use range, defined
once in `radio_atlas/widgets/panels.py`:

| Icon | Codepoint | Icon | Codepoint |
| --- | --- | --- | --- |
| `nf-fa-step_backward` | U+F048 | `nf-fa-star` (filled) | U+F005 |
| `nf-fa-play` | U+F04B | `nf-fa-star_o` (outline) | U+F006 |
| `nf-fa-pause` | U+F04C | `nf-fa-volume_up` | U+F028 |
| `nf-fa-step_forward` | U+F051 | `nf-fa-volume_off` | U+F026 |
| `nf-fa-stop` | U+F04D | `nf-fa-search` / `nf-fa-signal` | U+F002 / U+F012 |

The terminal draws glyphs at its font's cell size; the app cannot scale them,
so it enlarges click targets (3 to 5 columns) instead. Codepoints follow the
Font Awesome 4.7 mapping bundled with Nerd Fonts and were not checked against a
local font file.

---

## Offline behavior

```text
  network  ──►  live directory          ● ONLINE
     │ fail
     ▼
  cache    ──►  last successful reply   ◐ CACHE OFFLINE
     │ miss
     ▼
  seed     ──►  69 stations / 25 countries   ○ SEED OFFLINE
```

When every mirror fails, Radio Atlas serves the last successful response from
its disk cache, then the bundled seed catalog, marks the header, and pauses
network attempts for 60 seconds to avoid retry storms. Press `R` to retry
immediately. Search, genres, browsing, favorites, and history stay available
offline: genre counts come from the seed tags and genre stations from the seed
catalog.

Cached responses are served without a TTL: directory data is stable enough that
stale results beat an empty terminal, and the header never hides the source.

The same degradation covers missing mpv: an error toast and the player's state slot explain that playback
needs it while the rest of the app keeps working.

---

## Configuration

| Variable | Purpose |
| --- | --- |
| `RADIO_ATLAS_DATA_DIR` | Directory for `state.json` (favorites, history, volume, mute) |
| `RADIO_ATLAS_CACHE_DIR` | Directory for API response caches |
| `RADIO_ATLAS_API_URL` | Pin a specific Radio Browser mirror |
| `RADIO_ATLAS_MPV` | Default mpv binary path |

Default locations follow platform conventions via `platformdirs`:
`~/Library/Application Support/radio-atlas` and `~/Library/Caches/radio-atlas`
on macOS; `$XDG_DATA_HOME/radio-atlas` and `$XDG_CACHE_HOME/radio-atlas` on
Linux.

State writes are atomic (`os.replace` from a temp file in the same directory).
A corrupt `state.json` is renamed with a `.corrupt-<timestamp>` suffix and
replaced with defaults instead of breaking startup.

---

## Privacy

No accounts, no telemetry, no tracking. The app talks only to the Radio Browser
directory and the stream URLs you play, and stores favorites, history, and
settings locally. A station click is reported to Radio Browser only through its
public `/json/url/{uuid}` counter endpoint.

---

## Development

```bash
.venv/bin/python -m pytest
```

Tests cover the API client with mocked transports, the mpv IPC protocol
against a fake socket server, persistence recovery, globe rendering with a
golden frame at 48 × 16, CLI behavior, and Textual pilot flows. See
[docs/architecture.md](docs/architecture.md) for the module map, rendering
pipeline, IPC details, and known tradeoffs.

| Area | What it pins |
| --- | --- |
| `tests/test_api.py` | normalization, ranking, mirror failover, cache/seed fallback, cooldown |
| `tests/test_player.py` | IPC command/response, event ordering, stream errors |
| `tests/test_store.py` | roundtrip, atomic writes, corrupt-state quarantine, history bounds |
| `tests/test_geo_globe.py` | bundled assets, projection roundtrips, hit testing, marker priority, ASCII mode, golden frame |
| `tests/test_app.py` | Textual pilot flows with injected client and player fakes; compositor readback (cells, colors, contrast) at 120×40, 100×32, 80×24 and 60×24 |
| `tests/test_cli.py` | argument parsing, version output, missing assets |

Regenerate the bundled assets:

```bash
.venv/bin/python scripts/build_geo_assets.py
.venv/bin/python scripts/build_seed_catalog.py
```

---

## License

MIT. Bundled country geometry derives from Natural Earth (public domain). Seed
station names and stream URLs belong to their respective broadcasters.

---

<p align="center">
  <a href="https://github.com/Gentleman-Programming/gentle-ai">
    <img width="220" src="https://raw.githubusercontent.com/Gentleman-Programming/gentle-ai/main/docs/assets/brand/built-with-gentle-ai.png" alt="Built with Gentle-AI" />
  </a>
</p>
