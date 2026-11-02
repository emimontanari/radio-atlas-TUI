# Architecture

Radio Atlas is a Textual application with three independent edges: a geographic renderer, a directory client with offline fallback, and an mpv process driven over JSON IPC. The UI composes them and never blocks the event loop on network or playback work.

## Module map

| Module | Responsibility |
| --- | --- |
| `radio_atlas/app.py` | Textual app, view modes, key bindings, workers, search, playback orchestration |
| `radio_atlas/app.tcss` | Layout and theme |
| `radio_atlas/widgets/` | Globe canvas, DataTables, header, now-playing panel, status bar, help modal |
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

Both are best-effort. The UI is interactive before either finishes, and every failure becomes a status line rather than an exception.

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

`NullPlayer` implements the same surface when mpv is unavailable. Playback actions return `False`, the status bar explains the requirement, and the rest of the app remains usable.

## Persistence

`Store` keeps favorites, history (most recent first, bounded), and settings in one `state.json`. Writes go to a temporary file in the same directory followed by `os.replace`; corrupt files are renamed with a `.corrupt-<timestamp>` suffix and replaced by defaults. A failed write never breaks the UI.

`DiskCache` uses the same atomic-write pattern for API responses. Cache keys are sanitized to a filesystem-safe filename, and entries larger than 16 MB are ignored on read.

## UI state machine

The terminal layout places a full-height globe on the left and navigation,
the active table, now-playing metadata, and transport buttons on the right.
Search lives in the top bar alongside random and quit controls. Buttons call
the existing `action_*` methods; keyboard bindings remain available. Station
cards use UUID row keys and show favorite indicators from `Store.favorite_ids`.

Search moves to a full-width bordered row below 100 columns. Below 72 columns,
a map-context strip replaces the globe, leaving a full-width station workspace.
Transport controls are icon-only, three rows tall; tooltips carry the action and
shortcut (`Pause · space` while playing, `Play · space` otherwise). The row ends
with a filled `☆ Favorite` / `★ Favorited` button for the playing station (or
the selection when idle). `Transport` measures its own width: below 38 cells the
button shortens to `☆`/`★`, and below 35/42 cells (short/full button) the `70%`
readout hides.
The player has a separate labeled boundary and shows green `● LIVE` only for
`playing`, not `paused` or rejected playback.

`StationsTable` uses fixed viewport-bounded station/favorite columns, reserving
cell padding and a scrollbar cell. On width changes it rebuilds the presentation
through DataTable APIs and restores selection by UUID; it does not refetch data
or modify favorites/history. The favorite column is a 4-cell click target:
`StationsTable.FavoriteClicked` carries that row's station id to
`RadioAtlasApp._toggle_favorite`, the helper shared by the `f` key, the row star
and the player button. Names ellipsize, metadata remains on a second line,
and horizontal keys/gestures cannot scroll the station names out of view.

Modes are `world`, `favorites`, `recent`, `search`, `countries`, `cities`, and `stations`. Only one DataTable is visible at a time; each keeps its own cursor state. `esc` unwinds the browsing hierarchy, and search remembers the view that opened it.

Global key bindings forward `j/k/h/l/g/G/ctrl+d/ctrl+u` to the active table because DataTable does not bind them. While the search input is visible and focused, app shortcuts are ignored so typed characters reach the query.

Network lookups run in exclusive Textual workers. Search debounces for 350 ms and tags each request with a generation number, so a stale response cannot overwrite newer results.

## Testing

- `tests/test_api.py`: normalization, ranking, mirror failover, cache and seed fallback, cooldowns, using `httpx.MockTransport`.
- `tests/test_player.py`: IPC command/response, event ordering, state transitions, and stream errors against a fake mpv socket server.
- `tests/test_store.py`: roundtrip, atomic writes, corrupt-state quarantine, history bounds.
- `tests/test_geo_globe.py`: bundled assets, projection roundtrips, hit testing, marker priority, ASCII mode, and a golden frame.
- `tests/test_app.py`: Textual pilot flows with injected client and player fakes; compositor readback at 120×40, 100×32, 80×24, and 60×24, long-name horizontal/resize recovery, search borders, empty selections, control hit areas, and truthful LIVE states.
- `tests/test_cli.py`: argument parsing, version output, and missing-asset handling.

## Known tradeoffs

- The mask is sampled per braille dot in pure Python; that is fast enough at terminal sizes but not intended for pixel-perfect coastlines.
- Cached responses are served without a TTL. Directory data is stable enough that stale results are preferable to an empty terminal, and the header always discloses the source.
- Track metadata depends on the stream's ICY metadata. Many stations broadcast none, in which case the station name remains the now-playing label.
- The seed catalog is intentionally small. It proves offline browsing and preserves a useful demo, not a complete directory.
