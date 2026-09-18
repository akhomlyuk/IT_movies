# AGENTS.md

Project instructions for AI coding agents working in this repository.

## Overview

A static single-page site: a curated catalog of films, series and documentaries about computers, technology and AI. No build step, no dependencies, no server. GitHub Pages just serves the repo root.

Run locally:

```bash
python -m http.server 8000
# then open http://localhost:8000
```

## Structure

- `index.html` — page markup, `<template id="tpl-catalog">` inline component template, Yandex.Metrika snippet
- `films/<imdbId>/index.html` — one static SEO page per record (generated; slug is `<id>-<title-en-slug>`, id falls back to `kp-<kpId>` when there is no imdbId)
- `js/data.js` — the catalog (`window.CATALOG`, array of items, each with `desc.ru`/`desc.en`)
- `js/i18n.js` — translations (`window.I18N`), keys for both `ru` and `en`
- `js/app.js` — Vue 3 app (global prod build in `js/vue.global.prod.js`), all filtering/sorting/i18n/theme logic
- `js/film.js` — Vue 3 film-page app (shared by all `films/*` pages; same lang/theme/i18n behavior as `app.js`)
- `js/common.js` — shared helpers (`window.ITMoviesCommon`): slug/URL builders, lang & theme resolution, rating formatting, storage wrappers, error handler (used by both `app.js` and `film.js`)
- `css/style.css` — all styling, CSS variables for theming
- `static/` — images, fonts, posters (`static/posters/*.webp`)
- `scripts/` — local Python helper scripts (gitignored):
  - `lib.py` — shared helpers (catalog/slug/genres parsing, `SITE_BASE`) used by the scripts below
  - `verify.py` — integrity checker (source of truth; verifies generated pages are fresh, theme head-script is in sync, also regenerates `sitemap.xml`)
  - `gen_pages.py` — regenerates `films/*` pages from `js/data.js` + `js/i18n.js`
  - `pw_kp.py` — Kinopoisk search + rating lookup via Playwright (kpId, kpRating)
  - `show_types.py` — prints every record with its line number in `js/data.js`

## CRITICAL rules

- Everything that is NOT data validation must stay compatible with a fully static deployment: no server-side logic, no build step. URL parameters are handled client-side via `URLSearchParams` + `history.replaceState`.
- Do NOT break the contract between `data.js`, `i18n.js` and `app.js`:
  - `titleEn` must be Latin script; `titleRu` is the Russian title
  - `desc` is REQUIRED on every record: `desc.ru` and `desc.en`, both non-empty (used for film pages + SEO meta)
  - `genres` values must come only from the keys defined in `I18N.ru.genres` / `I18N.en.genres`
  - any new user-facing string needs keys in BOTH `ru` and `en`
  - if `poster` is set, the file must exist under `static/posters/...webp`
  - `fav: true` marks a "recommended" item
- `scripts/verify.py` is the source of truth for data integrity. After ANY change to `js/data.js`, `js/i18n.js`, `js/app.js`, `js/film.js`, `js/common.js`, `index.html`, `css/style.css`, `scripts/lib.py` or `scripts/gen_pages.py`, run it (and re-run `scripts/gen_pages.py` when its template/data changed). Output must end with `✅ All good` (no errors).
- `films/*` pages are generated, NEVER edited by hand: change the data (or `scripts/gen_pages.py`) and re-run it.
- Page slug = `<imdbId|kp-<kpId>>-<title-en-slug>`; editing `titleEn` renames the URL, so treat `titleEn` spelling as permanent.
- `js/data.js` is grouped by type in blocks: `movie` → `documentary` → `series`. Keep records in their block.
- Do NOT add code comments unless the user asks for them.