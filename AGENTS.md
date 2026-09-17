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
- `js/data.js` — the catalog (`window.CATALOG`, array of items)
- `js/i18n.js` — translations (`window.I18N`), keys for both `ru` and `en`
- `js/app.js` — Vue 3 app (global prod build in `js/vue.global.prod.js`), all filtering/sorting/i18n/theme logic
- `css/style.css` — all styling, CSS variables for theming
- `static/` — images, fonts, posters (`static/posters/*.webp`)
- `scripts/` — local Python helper scripts (gitignored)

## CRITICAL rules

- Everything that is NOT data validation must stay compatible with a fully static deployment: no server-side logic, no build step. URL parameters are handled client-side via `URLSearchParams` + `history.replaceState`.
- Do NOT break the contract between `data.js`, `i18n.js` and `app.js`:
  - `titleEn` must be Latin script; `titleRu` is the Russian title
  - `genres` values must come only from the keys defined in `I18N.ru.genres` / `I18N.en.genres`
  - any new user-facing string needs keys in BOTH `ru` and `en`
  - if `poster` is set, the file must exist under `static/posters/...webp`
  - `fav: true` marks a "recommended" item
- `scripts/verify.py` is the source of truth for data integrity. After ANY change to `js/data.js`, `js/i18n.js`, `index.html`, `css/style.css` or `js/app.js`, run it. Output must end with `✅ Всё в порядке` (no errors).
- `js/data.js` is grouped by type in blocks: `movie` → `documentary` → `series`. Keep records in their block.
- Do NOT add code comments unless the user asks for them.