# Author-voice redesign: featured, film pages, adaptive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild featured cards, film pages and adaptive behavior with a single-author voice ("Рекомендую лично / My recommendations") and quiet terminal-cinematic styling, without breaking static deploy.

**Architecture:** Pure CSS + Vue-template + generator-template changes only: tokens and components in `css/style.css`, copy in `js/i18n.js`, markup in `index.html` featured block and `tools/gen_pages.py` film template, selection logic in `js/app.js`; derived files regenerated via generator.

**Tech Stack:** Static HTML, CSS (custom properties, no build), Vue 3 global prod build, Python generators (`tools/gen_pages.py`, `tools/verify.py`), Node smoke (`tools/smoke.js` via verify).

**Spec:** `AGENTS.md` (project contract) + audit synthesis 2026-09-25 (3 parallel audits: main/featured, film pages, adaptive) + author constraint: no "editorial" wording, first-person voice only (`Рекомендую`, `My recommendations`, new badge `Выбор автора` / `Author's pick`).

## Global Constraints

- No server-side logic, no build step; URL params handled client-side via `URLSearchParams` + `history.replaceState`.
- `titleEn` Latin only; `desc.ru`/`desc.en` required non-empty; `genres` only from `I18N` genre keys; every user-facing string needs BOTH `ru` and `en` keys.
- Poster files must exist under `static/posters/...webp`, names `^[a-z0-9_]+\.webp$`, no case-insensitive collisions.
- `js/data.js` grouped `movie` → `documentary` → `series`; keep records in block; `titleEn` spelling is permanent (slug source).
- NEVER hand-edit generated outputs: `index.html` marker blocks (theme-script, index-ld, catalog-noscript, last-updated, metrika), `films/*/index.html`, `js/catalog.js`, `js/*.min.js` — change sources, re-run `python tools/gen_pages.py`.
- After ANY change to `js/data.js`, `js/i18n.js`, `js/app.js`, `js/film.js`, `js/common.js`, `index.html`, `css/style.css`, `tools/lib.py`, `tools/gen_pages.py`: run `python tools/verify.py`, output must end with `✅ All good`.
- No code comments unless asked; all comments/docstrings in English (RU only in data/content strings).
- No commit, no push without explicit permission. Restore point: local branch `checkpoint-redesign-2026-09-25` = `a0c7374` (clean tree).

## Review Focus

- Featured shuffle removal changes which 8 titles show on reload — a reasonable person expects the showcase to be stable and memorable, not random.
- New `authorPick` i18n keys must exist in BOTH `ru` and `en` or verify.py fails the build.
- Rating chips must not rely on color alone (KP vs IMDb must differ by label, not just hue) for color-blind users.
- 44px touch targets on mobile sort/filter/poster buttons — a reasonable person on 375px expects tappable controls without mis-taps.
- `≤525px` featured/related must not silently amputate content (`display:none` without "show more") — a reasonable person expects all recommendations reachable.

---

### Task 1: Author voice + rating-chip component + tokens

**Files:**
- Modify: `js/i18n.js` (add `authorPick` key both langs, ~lines 25-27 / 116-118)
- Modify: `css/style.css` (tokens `:root` ~lines 1-56 + dark `:root.dark` ~113-136; chip classes near rating styles ~979-1011)

**Interfaces:**
- Consumes: existing `--kp`, `--imdb`, `--accent`, `--muted`, `--fs-xs` tokens; `I18N.ru/en` shape.
- Produces: `t.authorPick` for Tasks 2-3; `.rating-chip` (`.rating-chip--kp`, `.rating-chip--imdb`) + `--tap:44px`, `--space-*`, `--radius-*` tokens for Tasks 2-4.

- [ ] **Step 1: Add `authorPick` keys (failing check first)**

```js
// js/i18n.js ru (after favFilterTitle:27):
authorPick: "Выбор автора",
// js/i18n.js en (after favFilterTitle:118):
authorPick: "Author's pick",
```

Run: `python tools/verify.py`
Expected: FAIL or same pass (keys unused yet — documents baseline); if FAIL, read error and fix key placement before continuing.

- [ ] **Step 2: Add chip + token CSS (minimal)**

```css
:root {
  --tap: 44px;
  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem; --space-4: 1rem;
  --radius-s: 6px; --radius-m: 12px; --radius-l: 16px;
}
.rating-chip {
  display: inline-flex; align-items: center; gap: 0.25em;
  border: 1px solid var(--line-strong); border-radius: 999px;
  padding: 0.1em 0.5em; font-variant-numeric: tabular-nums; white-space: nowrap;
}
```

- [ ] **Step 3: Regenerate + verify**

```bash
python tools/gen_pages.py
python tools/verify.py
```

Expected: output ends with `✅ All good`.

- [ ] **Step 4: Visual check (user on http://127.0.0.1:8008)**

No visual change yet except nothing broken. Confirm main + one film page render, then continue.

---

### Task 2: Featured cards rebuild (main page)

**Files:**
- Modify: `index.html` featured block (lines 117-133)
- Modify: `js/app.js` `pickFeatured` (lines 61-78)
- Modify: `css/style.css` featured section (lines 543-638 + mobile 1410-1422)

**Interfaces:**
- Consumes: `t.authorPick` (Task 1), `.rating-chip` (Task 1), `filmUrl`, `genreLabel`, `poster400`.
- Produces: stable `featured` array (catalog order, no shuffle); markup with badge + chips used by Task 4 breakpoints.

- [ ] **Step 1: Stabilize selection (no per-load shuffle)**

```js
function pickFeatured(catalog) {
  const favorites = catalog.filter((item) => item.fav);
  const selected = ["movie", "documentary", "series"].flatMap((type) =>
    favorites.filter((item) => item.type === type).slice(0, type === "series" ? 2 : 3)
  );
  return selected.slice(0, 8);
}
```

Keep `shuffle` helper (used nowhere else? check callers first; remove only if unused).

- [ ] **Step 2: Featured markup — badge + chips + bigger poster**

```html
<li v-for="item in featured" :key="'featured-' + (item.imdbId || item.kpId)">
  <a class="featured-card" :href="filmUrl(item)">
    <img :src="item.poster400 || item.poster" alt="" width="240" height="360" loading="lazy" decoding="async">
    <span class="featured-card-copy">
      <span class="featured-badge">{{ t.authorPick }}</span>
      <span class="featured-card-title">{{ lang === 'ru' ? item.titleRu : item.titleEn }}</span>
      <span class="featured-card-meta">{{ item.year }} · {{ genreLabel(item) }}</span>
      <span class="featured-ratings">
        <span v-if="item.kpRating" class="rating-chip rating-chip--kp">КП {{ item.kpRating }}</span>
        <span v-if="item.imdbRating" class="rating-chip rating-chip--imdb">IMDb {{ item.imdbRating }}</span>
      </span>
    </span>
  </a>
</li>
```

Rating display: reuse `hasRating`/`formatRating` from `window.ITMoviesCommon` instead of raw interpolation if they handle nulls (check `js/common.js` first).

- [ ] **Step 3: Featured CSS — poster 96-120px, accent line, no amputation on mobile**

Replace `≤525px` `li:nth-child(n+5){display:none}` with horizontal scroll-snap rail; poster `width:96-120px; aspect-ratio:2/3`; `line-clamp:2` for meta (no `nowrap`); one accent top-line on `.featured-card`.

- [ ] **Step 4: Regenerate + verify**

```bash
python tools/gen_pages.py
python tools/verify.py
```

Expected: `✅ All good` (noscript block + min.js refreshed).

- [ ] **Step 5: Visual check (user on http://127.0.0.1:8008)**

375px / 768px / 1440px + dark/light: badge reads first-person, chips labeled KP/IMDb (not color-only), all 8 reachable on mobile, posters crisp, no CLS.

---

### Task 3: Film pages — hero + trust strip + related rail

**Files:**
- Modify: `tools/gen_pages.py` (film template: hero order, meta strip, related markup)
- Modify: `css/style.css` (film sections ~1450-1743 + mobile 1795-1845)
- Modify: `js/film.js` only if template needs new bindings (lines 44-123)

**Interfaces:**
- Consumes: `t.authorPick`, `.rating-chip` (Task 1); `window.FILM_PAGE` shape unchanged (no `data.js` on film pages).
- Produces: hero layout + ratings strip + poster-rail related used by Task 4.

- [ ] **Step 1: Template — H1 into hero, trust strip above description**

Hero: poster (keep eager+fetchpriority) + H1 + type chip + `authorPick` badge when `fav` + ratings strip `КП x.x (N голосов) · IMDb y.y` + genre/year chips. Breadcrumb keeps `Главная › тип`; bottom back-link stays.

- [ ] **Step 2: Description — lead + EN collapser**

First ~200 chars styled as lead; second-language paragraph into `<details>` (noscript fallback: both visible as today). No copy changes, only markup/classes.

- [ ] **Step 3: Related — poster-rail, no hiding**

Posters ≥120px dominant, title + year + ONE rating; desktop row of 6, mobile swipe carousel; drop `display:none` rules (`style.css:1839-1843`); optional reason microcopy only if derivable from existing overlap data (no new strings beyond i18n keys added in both langs).

- [ ] **Step 4: Regenerate + verify**

```bash
python tools/gen_pages.py
python tools/verify.py
```

Expected: `✅ All good` (all `films/*` fresh, sitemap/robots consistent).

- [ ] **Step 5: Visual check (user on http://127.0.0.1:8008)**

Check `films/tt0133093-the-matrix/` + one series + one doc, RU/EN, dark/light, 375px: H1 in hero, ratings above fold, related swipeable with posters.

---

### Task 4: Adaptive hardening

**Files:**
- Modify: `css/style.css` (table ~656-1011, mobile ~1250-1422, film mobile ~1795-1845, modal ~859-883, scroll-top ~1120)

**Interfaces:**
- Consumes: `--tap` token + chips + rails from Tasks 1-3.
- Produces: final responsive behavior; nothing downstream.

- [ ] **Step 1: Table on 360-375px — restore safe overflow**

`.table-wrap` mobile: `overflow-x:hidden` → `auto` (keep `table-layout:fixed` + `nowrap` numbers intact, no clipped digits/external-link icon).

- [ ] **Step 2: 44px targets**

`.th-sort` padding, `.mobile-sort min-height:36px→var(--tap)`, `.reset-filters` add to 44px list, poster-icon 32px→44px hit area (visual can stay 32px with padding).

- [ ] **Step 3: Breakpoint cleanup**

Featured `526-720px` single full-width column → 2-col earlier or capped card width; unify `720/1024` (+480 profile only); fluid `clamp()` for h1/h2/table font; container padding `clamp(1rem,4vw,2.25rem)`.

- [ ] **Step 4: Modal + scroll-top edges**

Poster modal close button inside viewport at 320px; scroll-top offset respects footer (keep JS fallback class from `app.js`).

- [ ] **Step 5: Regenerate + verify + full visual sweep**

```bash
python tools/gen_pages.py
python tools/verify.py
```

Expected: `✅ All good`. User sweep: 320/375/768/1024/1440, light/dark, keyboard Tab, `prefers-reduced-motion`.
