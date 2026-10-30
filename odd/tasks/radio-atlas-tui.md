# Radio Atlas TUI

Objective: a fast, minimal Python TUI to explore and play world radio through a braille globe, country/city browser, search, favorites, and history.
Branch: `feat/radio-atlas-tui` · Delivery: `single-pr` (new project, one branch) · Test runner: `pytest` (`uv run pytest`).

## Specs

- **S1** — Build a **TUI (Terminal User Interface) en Python**, on **macOS y Linux**, with **Python, Textual, Radio Browser API y mpv**.
- **S2** — Provide a **"mapa mundial en ASCII/Unicode"**: a world map rendered in Unicode braille that can be rotated and zoomed, with live station signals as markers.
- **S3** — Support **"navegación por países y ciudades"**: browse countries, drill into cities/states, then stations.
- **S4** — Support **"búsqueda de emisoras"** by station name, tag, and country, with debounced live results.
- **S5** — Support **"reproducción en vivo"** through mpv: play/pause/stop, volume, mute, stream-failure feedback, retry, and now-playing metadata.
- **S6** — Support **"favoritos, historial"** persisted across sessions.
- **S7** — Provide **"controles mediante teclado estilo Vim"**: `h/j/k/l`, `g/G`, `Ctrl+d/u`, `/`, `space`, `f`, `r`, `?`, plus mouse support for the globe.
- **S8** — Replicate the reference project's core discovery features: world/favorites/recent views, **random tuning** that avoids recent stations, and automatic globe focus on the playing station.
- **S9** — Be **"ligera, rápida, visualmente atractiva y open source"**: minimal dependencies, responsive interactions, rounded-panel design, MIT license.
- **S10** — Degrade gracefully when Radio Browser is unreachable: cached catalog plus a bundled seed catalog, clearly marked offline; and when mpv is missing, keep browsing usable with install guidance. (Assumption: required by "rápida" and the reference project's cache behavior.)

## Tasks

| ID | Scope | Specs | Route | Status |
| --- | --- | --- | --- | --- |
| T1 | Scaffold: `pyproject.toml`, package layout, config paths, models, license, asset pipeline | S1, S9 | inline | done |
| T2 | Geo data + braille globe renderer (projection, country mask, markers, ASCII fallback) | S2 | inline | done |
| T3 | Radio Browser client: mirror failover, normalization, cache, offline seed | S1, S4, S10 | inline | in progress |
| T4 | Persistence store: favorites, history, settings, corrupt recovery | S6 | inline | pending |
| T5 | mpv IPC player: subprocess, socket protocol, state/metadata, fake-player tests | S5 | inline | pending |
| T6 | App shell: layout, header, globe widget, now playing, status bar, workers | S1, S2, S9 | inline | pending |
| T7 | Country/city browser, station table, search, favorites/recent, random | S3, S4, S6, S8 | inline | pending |
| T8 | Help modal, notifications, empty/error/offline/missing-mpv states, responsive layout | S7, S9, S10 | inline | pending |
| T9 | Tests: unit, golden globe, fake mpv, Textual pilot | S1–S10 | inline | pending |
| T10 | README, architecture notes, demo assets, final QA | S9 | inline | pending |

## Log

### L1 — Original request (2026-10-30)

> ## 🌍 Radio Atlas TUI — Radio mundial desde la terminal
>
> Crear una aplicación **TUI (Terminal User Interface) en Python**, inspirada en **Radio Atlas para Omarchy**, que permita explorar y escuchar emisoras de radio de todo el mundo directamente desde la terminal de macOS y Linux.
>
> La idea es replicar las funcionalidades del proyecto original, adaptándolas a una interfaz moderna, minimalista e interactiva, con un mapa mundial en ASCII/Unicode, navegación por países y ciudades, búsqueda de emisoras, reproducción en vivo, favoritos, historial y controles mediante teclado estilo Vim.
>
> El objetivo es construir una alternativa ligera, rápida, visualmente atractiva y open source, utilizando **Python, Textual, Radio Browser API y mpv**.
>
> **Repositorio de referencia:** https://github.com/AksharP5/omarchy-radio-atlas

### L2 — Environment findings (2026-10-30)

- Python 3.13.5 available at `.venv`; Textual 8.2.8 installed. mpv is not installed on this machine, so playback is verified against a fake IPC server and the app must degrade gracefully.
- `https://*.api.radio-browser.info/json/*` currently answers `503 no available server`; the live API cannot be used for development. Unit tests use `httpx.MockTransport`; the app ships a seed catalog and cache fallback (S10).
- Natural Earth 1:110m country geometries (public domain) are used to generate a compact country index and an equirectangular land mask. The full GeoJSON is not shipped.

### L3 — Decisions (2026-10-30)

- Globe renderer samples a bundled 720×360 country mask through an orthographic inverse projection; 2×4 braille dots per cell. This keeps a full redraw in pure Python fast and lets country hit-testing and highlighting reuse the same mask.
- Side panel hosts three mutually exclusive views: countries, cities, stations. One DataTable each, preserving cursor state; `/` filters the country/city view when it is active.
- mpv is driven over its JSON IPC socket in a private temp directory (short path for the 104-byte macOS socket limit). `NullPlayer` covers missing mpv.
- Persistence is a single atomic `state.json` under the platform data dir; caches live under the platform cache dir. Env overrides exist for tests.

### L4 — Status correction + API design (2026-10-30)

- Corrected T3–T10: the previous "done" marks were premature. T1–T2 are implemented; T3 is now in progress and T4–T10 are pending.
- API client contract: `CatalogResult`/`CountriesResult` carry `source` (`network`, `cache`, `seed`), `offline`, `fetched_at`, and `error`. Network failures never raise to the UI; they degrade to stale cache, then to the bundled seed catalog.
- Search runs name/tag/country queries in parallel, merges and ranks by relevance plus votes; if all fail it filters the seed catalog.
- Mirrors are discovered through `all.api.radio-browser.info` reverse DNS, then a fixed fallback list, shuffled. The first healthy base is reused; failures rotate to the next mirror. A short offline cooldown prevents retry storms while the API is down.
