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
| T1 | Scaffold: `pyproject.toml`, package layout, config paths, models, license, asset pipeline | S1, S9 | inline | done — `e7a846d` |
| T2 | Geo data + braille globe renderer (projection, country mask, markers, ASCII fallback) | S2 | inline | done — `e7a846d` |
| T3 | Radio Browser client: mirror failover, normalization, cache, offline seed, retry | S1, S4, S10 | inline | done — `e7a846d`, `9cf5a80` |
| T4 | Persistence store: favorites, history, settings, corrupt recovery | S6 | inline | done — `e7a846d` |
| T5 | mpv IPC player: subprocess, socket protocol, state/metadata, fake-player tests | S5 | inline | done — `e7a846d` |
| T6 | App shell: layout, header, globe widget, now playing, status bar, workers | S1, S2, S9 | inline | done — `5daa6a2` |
| T7 | Country/city browser, station table, search, favorites/recent, random | S3, S4, S6, S8 | inline | done — `5daa6a2` |
| T8 | Help modal, notifications, empty/error/offline/missing-mpv states, responsive layout | S7, S9, S10 | inline | done — `5daa6a2` |
| T9 | Tests: unit, golden globe, fake mpv, Textual pilot | S1–S10 | inline | done — `e7a846d`, `b9b9a89` |
| T10 | README, architecture notes, demo assets, final QA | S9 | inline | done — documentation commit on this branch |

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

### L5 — UI and delivery completed (2026-10-30)

- Implemented the Textual shell, braille globe widget, country/city/station tables, debounced search, favorites/recent views, help modal, responsive header/now-playing/status layout, and CLI flags.
- Commits: `9cf5a80` (catalog retry + seed countries), `5daa6a2` (UI and app behavior), `b9b9a89` (model/cache/geo/globe/CLI tests).
- The UI work unit exceeds the 400-line planning heuristic because `app.py` is one state machine that references every widget; splitting it would leave a non-runnable intermediate commit. Tests, docs, and assets accompany the behavior.
- Visual QA: screenshots at 140×40 and 80×24, plus ASCII mode at 100×30. Fixed the DataTable horizontal scrollbar leak, themed the help scrollbar, and made the cache badge disclose offline state.
- `risk: none` — new application code, no stored-data migration, no public contract change, no credentials, no concurrency primitives.

### L6 — Verification evidence (2026-10-30)

- `pytest`: 108 passed (API 18, app 8, cache 9, CLI 5, geo/globe 27, models 14, player 10, store 7, shared fakes).
- Golden globe frame at 48×16 pins the bundled mask and braille output.
- Radio Browser remains unavailable (`503 no available server`); failover, cache, seed, cooldown, and reset paths are covered with `httpx.MockTransport`.
- mpv is not installed on this machine; the IPC protocol, event handling, and state transitions are covered against `tests/fake_mpv.py`. `NullPlayer` keeps the app usable and the status bar explains the requirement.
- Screenshot and ASCII captures were generated headlessly through Textual's pilot and inspected; no screenshot or state file is written by the test suite.

### L7 — Documentation (2026-10-30)

- Added `README.md` (install, keys, offline behavior, configuration, privacy, development) and `docs/architecture.md` (module map, rendering pipeline, IPC, persistence, UI state machine, tradeoffs).
- Added `docs/screenshot.svg`, rendered from the bundled seed catalog with the offline badge, so the demo does not depend on the live API.

### L8 — README diagrams, repo rename, first push (2026-11-02)

> pushiar lo trabajado y si queda algun detallito hacerlo y rear un readme completo en ingles y si podes iluta la app con ... dibujados en la docu para que se entienda el concepto

- Rewrote `README.md` in English with drawn illustrations: a real braille globe captured headlessly, an ASCII layout schematic, a braille 2×4 dot explainer, a component/source tree, and an offline degradation ladder.
- Corrected the repository identity to `radio-atlas-TUI` in `pyproject.toml`, `radio_atlas/__init__.py` (`USER_AGENT`), and the README clone URL.
- Pushed the branch to the new empty remote `https://github.com/emimontanari/radio-atlas-TUI` as `main`, per the user's init snippet.
- Added `docs/screenshot.png` (rsvg-convert from the Rich SVG) because PNG renders reliably through GitHub's image proxy; the SVG stays as the vector source.
- `pytest`: 108 passed after the change.
- `risk: none` — documentation and string metadata only; no behavior, stored data, or dependency change.

### L9 — Real playback QA and cold-start fix (2026-11-02)

> ok perfecto acordate hace un branch para la tarea siempre y testea con gh si es posible para implementar

- Working branch: `chore/real-playback-qa` (user requires one branch per task).
- Installed mpv 0.41.0 with Homebrew and the checkout editable with `uv pip install -e '.[dev]'`. The existing `.venv` was created by uv and has no `pip`; the README's `python -m venv` path (which does include pip) was validated separately on a fresh clone.
- Real IPC QA with `MpvPlayer`: played `France Info` and `SomaFM Groove Salad`, received ICY metadata (`Sometimes We Hope` / `Kick Bong`), and verified pause/resume, volume 35, mute, and stop against mpv's own properties.
- TUI smoke with the real binary (`radio-atlas --ascii --mpv <path>`) launched and quit cleanly.
- Live Radio Browser API: world, 227 countries, by-country, search, and random all returned `source=network` with no offline fallback.
- `gh repo clone` of `main` into a scratch directory followed the README steps: `radio-atlas 0.1.0` and 108 tests passed.
- Defect found: the first mpv launch after install exceeded the 3s IPC connect timeout and surfaced `mpv did not open its IPC socket`. Raised `CONNECT_TIMEOUT` to 8s; the next launch connected in ~0.15s. Reproduced with a wrapper that sleeps 4s before exec'ing mpv: the old 3s timeout failed at 3.05s with the same error, and the new 8s timeout connected at 4.24s. The wrapper is not committed as a test because it would add seconds to every suite run.
- `pytest`: 108 passed.
- `risk: none` — timeout constant only; no contract, stored data, or dependency change.
