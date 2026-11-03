# Architecture

Radio Atlas is a Textual application with three independent edges: a geographic renderer, a directory client with offline fallback, and an mpv process driven over JSON IPC. The UI composes them and never blocks the event loop on network or playback work.

## Module map

| Module | Responsibility |
| --- | --- |
| `radio_atlas/app.py` | Textual app, view modes, key bindings, workers, search, playback orchestration |
| `radio_atlas/app.tcss` | Layout, theme and the `.narrow` / `.compact` responsive classes |
| `radio_atlas/widgets/panels.py` | Icon mapping (`ICON_CODEPOINTS`, `ICONS`, `ASCII_ICONS`, `icon_text`), `AtlasHeader`, `PlayerInfo`, `NowPlaying`, `Transport`, `VolumeBar`, `KeyFooter` (key chips and toast) |
| `radio_atlas/widgets/tables.py` | `StationsTable` (two-line rows, star column), genres, countries and cities tables |
| `radio_atlas/widgets/globe.py`, `help.py` | Globe canvas; keyboard help modal |
| `radio_atlas/globe.py` | Orthographic projection, braille rasterizer, markers, hit testing |
| `radio_atlas/geo.py` | Country index and country mask lookup |
| `radio_atlas/models.py` | `Station`, `Country`, `HistoryEntry`, normalization, metadata parsing |
| `radio_atlas/api.py` | Radio Browser mirrors, cache/seed fallback, search ranking |
| `radio_atlas/cache.py` | Atomic JSON disk cache |
| `radio_atlas/store.py` | Favorites, history, settings, corrupt-state quarantine |
| `radio_atlas/player.py` | mpv JSON IPC and `NullPlayer` fallback |
| `radio_atlas/cli.py` | Argument parsing and entry point |
| `scripts/` | Asset generation from Natural Earth and a curated station list |

## Startup

`on_mount` renders the bundled seed catalog immediately, then starts two workers in parallel:

1. `MpvPlayer.start()` spawns mpv or reports it missing.
2. `RadioBrowserClient.world()` fetches the top-clicked stations.

Both are best-effort. The UI is interactive before either finishes, and every failure becomes a toast or an inline player state rather than an exception.

## Directory client

`RadioBrowserClient` returns result objects instead of raising:

- `CatalogResult(stations, source, offline, error)`
- `CountriesResult(countries, source, offline, error)`

`source` is `network`, `cache`, or `seed`. Each lookup tries the network, then the cache, then the seed catalog. When all mirrors fail, the client sets a 60-second cooldown; `R` clears it through `reset_offline()`.

Mirror discovery resolves `all.api.radio-browser.info`, shuffles the returned hosts, and appends a fixed fallback list. Up to three mirrors are attempted per request. The first healthy base is reused for later requests.

Search runs three parallel queries (`name`, `tag`, `country`), merges results by station UUID, and ranks them:

1. name prefix or token prefix;
2. name substring;
3. tag/country/state substring;
4. votes, then clicks.

Offline search applies the same all-token match against the seed catalog's `search_text`.

## Globe rendering

`scripts/build_geo_assets.py` converts Natural Earth 1:110m country polygons into two compact assets:

- `countries.json`: 177 countries with ISO code, name, continent, and label coordinates.
- `worldmask.bin`: a 1440×720 byte mask where 0 is ocean and 1..255 is a country index.

The full GeoJSON is not shipped.

`GlobeRenderer.render()` samples the mask through an inverse orthographic projection. Each terminal cell is a 2×4 braille grid (`U+2800` base); every visible dot looks up the country mask, builds a braille byte, and marks focus, rim, or ocean. The same mask answers country hit-testing after a click, so rendering and interaction cannot disagree.

Station markers are projected through the forward orthographic transform and placed in their nearest cell. Priority is playing (`◉`), selected (`◇`), favorite (`★`), then station (`●`). A `+` reticle marks the map center when no station occupies that cell. Braille is replaced by `#` and ASCII glyphs with `--ascii`.

A full redraw is roughly 6 ms at 96×28 cells and 23 ms at 160×45 on the development machine, which keeps rotation interactive without a render thread.

## Playback

`MpvPlayer` launches:

```text
mpv --no-video --idle=yes --no-terminal --really-quiet \
    --input-ipc-server=<socket> --volume=<v> --cache=yes --cache-secs=10
```

The IPC socket lives in a private `mkdtemp` directory under the system temp directory because macOS limits Unix socket paths to about 104 bytes. `MpvIpc` multiplexes newline-delimited JSON requests and events over one connection, matches responses by `request_id`, and forwards `property-change` events to update now-playing metadata.

`parse_track()` strips a leading station name only when it is the whole value or followed by a separator, so an artist like "Rockwell" on a station named "Rock" is not lost, then splits `Artist - Title` variants.

`NullPlayer` implements the same surface when mpv is unavailable. Playback actions return `False`, an error toast and the player's state slot explain the requirement, and the rest of the app remains usable.

## Persistence

`Store` keeps favorites, history (most recent first, bounded), and settings in one `state.json`. Writes go to a temporary file in the same directory followed by `os.replace`; corrupt files are renamed with a `.corrupt-<timestamp>` suffix and replaced by defaults. A failed write never breaks the UI.

`DiskCache` uses the same atomic-write pattern for API responses. Cache keys are sanitized to a filesystem-safe filename, and entries larger than 16 MB are ignored on read.

## UI layout

A full-height globe sits on the left; the right column stacks tabs, the active table, the player and (outside it) the footer. Buttons call the existing `action_*` methods, so mouse and keyboard share one code path.

| Widget | Role |
| --- | --- |
| `AtlasHeader` | one row: signal icon, brand, `MODE · N STATIONS`, source badge; the underlined search field sits beside it |
| `StationsTable` | two-line rows, `▶` gutter marker, bounded 5-cell star column |
| `PlayerInfo` | container holding `NowPlaying` and the floating `#player-favorite` button |
| `NowPlaying` | three text lines under a top rule (see below) |
| `Transport` | the control row: transport group on the left, volume group on the right |
| `VolumeBar` | `VOL ▮▮▮▯ 85%`; clickable segments |
| `KeyFooter` | toast rule plus clickable key chips |

Random and quit have no buttons any more; they stay on `r` / `q` and in the footer chips.

### Player row budget

The player is **6 rows** (7 when the volume group wraps):

| Row | Content |
| --- | --- |
| 1 | top rule (the border of `NowPlaying`) |
| 2 | dim `NOW PLAYING` left, state right: green icon + `LIVE` only while `playing`, else `PAUSED`, `STOPPED` or the error text (ellipsized) |
| 3 | bold station name, ellipsized so the star always fits, then the star one cell after it |
| 4 | muted `title · CODEC · NNN kbps`; the title is `artist — title` when known, else `country · state`; only the title part is ellipsized |
| 5 | blank breathing row (top padding of `Transport`) |
| 6 | controls: Previous, Play/Pause, Next, Stop (3/5/3/3 columns, 2-column gaps; Play/Pause is a filled lavender pill) on the left; speaker button + `VolumeBar` right-aligned |

The Play/Pause glyph inherits the button foreground (dark ink on lavender) instead of carrying its own Rich color, so hover and focus keep their contrast.

`#player-favorite` is a 3×1 button. `PlayerInfo.place_favorite` offsets it to the cell after the clipped station name (re-run on every update and resize). It keeps its id, tooltips and the `f` / row-star sync.

### Volume

`VolumeBar` renders at most `MAX_SLOTS = 24` segments and keeps the percentage one space after the bar. Its width shrinks first when space is short, down to `MIN_SLOTS = 6`; the buttons and the percentage never shrink. The volume group has a 2-column left margin, so the gap to Stop is at least 2 columns. `Transport.on_resize` adds the `wrapped` class when its content is narrower than `MIN_WIDTH = 41`; the volume group then moves to a second row. Clicking a segment posts `VolumeBar.Changed`; the app turns it into a delta and calls `_change_volume`, the same path as `[` / `]`, so the level persists in the store.

### Responsive classes

`RadioAtlasApp.on_resize` toggles two classes on the app; there is no `.roomy` class any more.

| Class | Width | Effect |
| --- | --- | --- |
| `.narrow` | < 100 | search moves to its own full-width row, side panel widens (2fr) |
| `.compact` | < 72 | a map-context strip replaces the globe; the station workspace is full width |
| `wrapped` (on `Transport`) | content < 41 | volume group on its own row |

### Icons

Icons come from one named mapping in `widgets/panels.py`: `ICON_CODEPOINTS` (Font Awesome 4.7 private-use codepoints provided by a Nerd Font), expanded into `ICONS`, with `ASCII_ICONS` as the `--ascii` fallback. `icon_text(name, ascii_mode=..., active=...)` returns the styled glyph. Stars are U+F006 (outline, muted) and U+F005 (filled, `FAVORITE_COLOR` `#f5c542`). The app does not scale fonts; it widens click targets instead. Without a Nerd Font, private-use characters render as tofu; selecting a font is a terminal setting and the app never installs one.

### Favorites

All three entry points converge on `RadioAtlasApp._toggle_favorite(station)`: the `f` key (`action_favorite`, current selection), the player star (`_toggle_player_favorite`, playing station or the selection when idle) and the row star (`StationsTable.FavoriteClicked` → `_star_clicked`). It updates `Store.favorite_ids`, then calls `_sync_globe`, repopulates the table when the Favorites tab is open, runs `_refresh_player_views` (labels, tooltips, button state) and posts a toast.

### Toasts and footer

`KeyFooter` replaced the old status bar. `_set_status` calls `KeyFooter.set_notice(message, tone)`, which draws the message on the footer's rule row for `DURATIONS[tone]` seconds (info/good 3, warn 8, error 12). The second row draws the visible `RadioAtlasApp.BINDINGS` as clickable key chips and drops the lowest-priority chips (`CHIP_PRIORITY`) when the width is short. Connectivity is disclosed by the header badge, and player errors by the state slot, so nothing depends on a toast being on screen.

### Station list

`StationsTable` uses fixed viewport-bounded marker/station/star columns, reserving cell padding and a scrollbar cell. Rows are two lines tall (name, then `CC · codec · kbps`), and `update_playing` puts a `▶` in the gutter of the playing or paused station. On width changes it rebuilds the presentation through DataTable APIs and restores selection by UUID; it does not refetch data or modify favorites/history. The star column is a click target spanning each two-line row. Names ellipsize, and horizontal keys/gestures cannot scroll them out of view.

Modes are `world`, `favorites`, `recent`, `search`, `countries`, `cities`, and `stations`. Only one DataTable is visible at a time; each keeps its own cursor state. `esc` unwinds the browsing hierarchy, and search remembers the view that opened it.

Global key bindings forward `j/k/h/l/g/G/ctrl+d/ctrl+u` to the active table because DataTable does not bind them. While the search input is visible and focused, app shortcuts are ignored so typed characters reach the query.

Network lookups run in exclusive Textual workers. Search debounces for 350 ms and tags each request with a generation number, so a stale response cannot overwrite newer results.

## Testing

- `tests/test_api.py`: normalization, ranking, mirror failover, cache and seed fallback, cooldowns, using `httpx.MockTransport`.
- `tests/test_player.py`: IPC command/response, event ordering, state transitions, and stream errors against a fake mpv socket server.
- `tests/test_store.py`: roundtrip, atomic writes, corrupt-state quarantine, history bounds.
- `tests/test_geo_globe.py`: bundled assets, projection roundtrips, hit testing, marker priority, ASCII mode, and a golden frame.
- `tests/test_app.py`: Textual pilot flows with injected client and player fakes; compositor readback (cells, colors, contrast) at 120×40, 100×32, 80×24, and 60×24, the 6-row player block, long-name and resize recovery, search field, empty selections, control hit areas, truthful LIVE states, and a pinned key-footer rendering.
- `tests/test_cli.py`: argument parsing, version output, and missing-asset handling.

## Known tradeoffs

- The mask is sampled per braille dot in pure Python; that is fast enough at terminal sizes but not intended for pixel-perfect coastlines.
- Cached responses are served without a TTL. Directory data is stable enough that stale results are preferable to an empty terminal, and the header always discloses the source.
- Track metadata depends on the stream's ICY metadata. Many stations broadcast none, in which case the station name remains the now-playing label.
- The seed catalog is intentionally small. It proves offline browsing and preserves a useful demo, not a complete directory.
