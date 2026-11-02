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

![Radio Atlas playing SomaFM Groove Salad (previous layout)](docs/screenshot.png)

The screenshot shows the previous layout; the diagram below describes the current UI.

---

## The idea

Radio directories are lists. Lists are efficient, but they hide the one thing
that makes world radio interesting: **where the signal comes from**.

Radio Atlas puts geography first. The globe is not decoration; it is the
primary index. Every station you can play has a coordinate, and every country
you can open is a shape on the map. Search and lists exist for when you already
know what you want. The map exists for when you do not.

```text
┌ RADIO ATLAS ──────────────────────── / Search stations… ── ⤨ ─ × ┐
│ WORLD · 69 STATIONS   ○ SEED OFFLINE                             │
├──────────────────────────────────────┬──────────────────────────┤
│                                      │ World  Favorites  Recent │
│                                      ├──────────────────────────┤
│            braille globe             │ SomaFM Groove Salad    ☆ │
│         rotate · tilt · zoom         │ US · MP3 · 128 kbps      │
│                                      │                          │
│           ●      ◉      ●            │ Radio Paradise         ★ │
│                  ●                   │ US · AAC · 128 kbps      │
│                                      │                          │
│                                      ├──────────────────────────┤
│                                      │ ▶ Groove Salad ● LIVE    │
│                                      │ ambient · downtempo      │
│                                      │ US…  VOL ▮▮▮▮▯ 70        │
│                                      │ Offline catalog…         │
│                                      │ ⏮  ❚❚ ⏭  ■  ♪  −  + ☆   │
├──────────────────────────────────────┴──────────────────────────┤
│ Radio Browser unavailable — using the bundled catalog           │
│ 1 World  2 Favs  3 Recent  4 Genres  c Browse  / Find  ? Help     │
└─────────────────────────────────────────────────────────────────┘
```

The full-height map fills the left column in wide terminals. Search has a
complete bordered field above the workspace; below 100 columns it gets its own
row. The right column labels the active list and separates it from the player
and larger, two-row transport targets. Below 72 columns, the map becomes a
context strip so the station list can use the full width. The charcoal and
lavender interface stays entirely in the terminal. One list is visible at a
time; `esc` walks back up the hierarchy.

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

Press `H`/`L` to rotate, `J`/`K` to tilt, `+`/`-` to zoom, `0` to reset. On a
terminal without braille support, `--ascii` swaps the braille rasterizer for
`#` and plain glyphs.

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
status bar explains what to install.

---

## Install

Requirements: **Python 3.11+** on macOS or Linux, and **mpv** for playback.

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

---

## Usage

```bash
radio-atlas                 # braille globe
radio-atlas --ascii         # ASCII fallback for terminals without braille
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

Click a marker on the globe to play that station, or click land to open its
country. The top bar offers search, random station, and quit buttons. On the
right, click World, Favorites, or Recent to switch views; use the transport
buttons — icon-only ⏮ ▶ ⏭ ■ ♪ − + (▶ becomes ❚❚ while playing); hover for the
action name and shortcut. Click the ☆/★ at the right of any station card
to add or remove that station without playing it, or use the large
☆ Favorite / ★ Favorited button at the end of the transport row (☆ / ★ when
the panel is narrow; it follows the playing station, or the
selection when idle); `f` toggles the selected station. Favorites persist in
`state.json` across restarts. The `70%` volume readout shows only where the
transport row has room (wide terminals and the compact layout); the player's
`VOL` bar is always visible.

Station names ellipsize inside the visible list width; metadata and favorite
stars stay alongside them, without horizontal station scrolling. Resizing keeps
the selected station. The green `● LIVE` badge means playback is actually
playing; paused playback says `Paused` instead.

All keyboard shortcuts remain available, including when the map is compact.
Control sizes use terminal cells, not independently scaled fonts. Narrow
terminals may truncate footer hints and secondary metadata; `?` opens the
width-bounded, scrollable shortcut list.

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

The same degradation covers missing mpv: the status bar explains that playback
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
| `tests/test_app.py` | Textual pilot flows with injected client and player fakes |
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
