# about-shared-infra Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `about.html` as a Vue app on the site's shared infrastructure (film-page pattern), so only its central content differs from the rest of the site.

**Architecture:** New `js/about.js` Vue app (mirrors `js/film.js`) renders the page from a new `about` namespace in `js/i18n.js`; `js/common.js` and `css/style.css` are reused unchanged (minus moving shared `.privacy`/`.profile*` styles into `style.css`); `about.html` becomes static shell (`#app` + noscript fallback + 4 deferred scripts). `tools/gen_pages.py` and `tools/verify.py` get `about.js` added to their file lists so `js/about.min.js` is generated and verified.

**Tech Stack:** Vue 3 (global prod build already vendored), plain ES5-compatible JS, static HTML, Python tooling (`tools/gen_pages.py`, `tools/verify.py`), Node for syntax checks.

**Spec:** `docs/superpowers/specs/2026-09-24-about-vue-shared-infra-design.md`

## Global Constraints

- **RU texts byte-exact:** all RU strings moved to `js/i18n.js` are verbatim from the current `about.html` inline dict (lines 322–345). Do NOT rephrase, transliterate, or "fix" anything (`хакерского` with escaped quotes, straight ASCII quotes, informal style included).
- **Verification gate:** every task ends with the repo's verifier green: `python tools/gen_pages.py` then `python tools/verify.py --strict` last printed line `✅ All good`. `verify.py --strict` fails if Node is missing.
- **Generated files are never hand-edited:** `<!-- begin:theme-script -->` and `<!-- begin:metrika -->` blocks, `js/*.min.js`, `js/catalog.js` are generated. The theme-script and Metrika blocks in `about.html` must be copied byte-for-byte from the current file (verify asserts exact equality with `gen_pages.THEME_SCRIPT` / `gen_pages.METRIKA_SCRIPT`).
- **i18n parity:** every new key exists in BOTH `ru` and `en` (verify block 5b enforces this).
- **Pages reference `.min.js`** (e.g. `js/i18n.min.js`, `js/about.min.js`), never the raw `.js`.
- **No intermediate commits:** per user instruction, all changes land in ONE final combined commit at the end of Task 5. Do not `git add`/`git commit` in individual tasks.
- **No code comments** unless the user asks for them.
- **Bilingual header title:** `about.heading` is `«О сайте»` / `"About the site"`; the header `h1` shows the current-lang value and `altTitle` shows the other-language value (film-page pattern).

## Review Focus

Inputs/failure modes the spec implies but that routine checks won't fully pin; each gets a step in the owning task:

1. **Text drift when copying RU strings** — the riskiest failure (user-curated copy). Pinned in Task 1 by a sentinel-string test on the literal JS source.
2. **`about.js` must be valid standalone JS** (it first runs in Node-only checks before the browser ever sees it) — pinned in Task 2/4 via `node --check` + verify's bracket-balance.
3. **`js/about.min.js` must stay fresh after every change to `js/about.js`** — pinned in Task 4 via verify block 9b (runs `gen_pages.py`).
4. **No-JS visitors must see the complete RU page** (noscript has its own copy of all content; the old pattern showed both lang blocks without JS) — pinned in Task 5 manual smoke with JS disabled.
5. **Sprite icons (`<use href="#i-…">`) must render inside the Vue-rendered template** (sprite lives outside `#app`; unlike film pages this page uses an inline sprite) — pinned in Task 5 manual smoke (icons visible in the profile card).

---

### Task 1: `js/i18n.js` — add `about` namespace (ru + en)

**Files:**
- Modify: `js/i18n.js` (insert two `about` blocks: after `genres` in `ru`, line 66 → before line 67; after `genres` in `en`, line 132 → before line 133)

**Interfaces:**
- Produces: `I18N.ru.about.*` and `I18N.en.about.*` — keys consumed by Task 2 (`js/about.js`): `title`, `desc`, `heading`, `lead`, `ideaH`, `ideaP`, `whoH`, `whoP`, `recordH`, `recordP`, `siteH`, `siteP`, `suggestH`, `suggestP`, `principlesH`, `principlesP`, `linksLabel`.

- [ ] **Step 1: Insert the `ru.about` block**

In `js/i18n.js`, after the `genres: { … },` closing brace of the `ru` dict (line 66) and before the `ru` dict's closing `},` (line 67), insert exactly:

```js
    about: {
      title: "О сайте — IT Movies",
      desc: "О сайте IT Movies: кто создал каталог кино о компьютерах и ИИ, как отбираются фильмы и как предложить свой.",
      heading: "О сайте",
      lead: "IT Movies — вручную собранный и поддерживаемый мной каталог фильмов, сериалов и документалок о компьютерах, киберпанке, интернете, ИИ и т.д. Без алгоритмов и ссылок на стриминги (не маленькие, сами найдете)",
      ideaH: "Для кого это всё",
      ideaP: "Для тех кто постоянно пишет мне в личку и/или чатах, форумах, что бы такого \"хакерского\" посмотреть. Тут все собрано в одном месте — это список, который я реально порекомендовал бы товарищам.",
      whoH: "Кто за этим стоит и как отбираются фильмы",
      whoP: "Подборку веду сам, мой канал <a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Whitehat Lab</a>. Это некоммерческий pet-проект, написать мне можно по ссылкам выше.",
      recordH: "Что внутри каждой записи",
      recordP: "Английское и русское название, год, жанры, короткое описание на двух языках и постер. Рейтинги <b>КиноПоиска</b> и <b>IMDB</b> — ровно такие, какими были на момент обновления: без накрутки в ту или иную сторону.",
      siteH: "Как устроен сайт",
      siteP: "Статическая сборка без бекенда, аккаунтов и комментариев. Есть фильтры по типу, жанру, году и рейтингу, сортировка, русский и английский интерфейс, светлая и тёмная тема — и всё работает даже без JavaScript. Все данные в одном открытом файле, дата обновления берётся из истории Git.",
      suggestH: "Как предложить фильм",
      suggestP: "Нашли ошибку или знаете отличный фильм? Пишите в <a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Telegram</a> или открывайте pull request на <a href='https://github.com/akhomlyuk/IT_movies' target='_blank' rel='noopener noreferrer'>GitHub</a> — проверяю и публикую без долгих очередей.",
      principlesH: "Принципы",
      principlesP: "Никаких партнёрских ссылок и трекинга сверх того, что собирает яндекс метрика, описано в <a href='privacy.html'>политике конфиденциальности</a>. Код открыт — любое утверждение на сайте можно проверить в репозитории.",
      linksLabel: "Ссылки",
    },
```

- [ ] **Step 2: Insert the `en.about` block**

After the `genres: { … },` closing brace of the `en` dict (line 132) and before the `en` dict's closing `},` (line 133), insert exactly:

```js
    about: {
      title: "About the site — IT Movies",
      desc: "About the IT Movies site: who curates the catalog, how titles are selected and how to suggest one.",
      heading: "About the site",
      lead: "IT Movies is a hand-curated catalog of films, series and documentaries about computers, cyberpunk, the internet, AI and more, which I collect and maintain myself. No algorithms, no streaming links (they are not hard to find).",
      ideaH: "Who it's for",
      ideaP: "For everyone who keeps writing to me in DMs and/or chats and forums asking what \"hacker\" stuff to watch. Everything is gathered in one place — this is a list I would genuinely recommend to friends.",
      whoH: "Who's behind it and how titles are selected",
      whoP: "I curate the selection myself — my channel is <a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Whitehat Lab</a>. It's a non-commercial pet project; you can write to me via the links above.",
      recordH: "What each record contains",
      recordP: "English and Russian titles, year, genres, a short description in both languages and a poster. <b>Kinopoisk</b> and <b>IMDb</b> ratings are exactly as they were at the time of the update — not inflated in either direction.",
      siteH: "How the site works",
      siteP: "A static build with no backend, accounts or comments. Filters by type, genre, year and rating, sorting, RU/EN interface, light and dark theme — and everything works even without JavaScript. All data lives in one open file; the update date comes straight from Git history.",
      suggestH: "How to suggest a film",
      suggestP: "Found an error or know a great film? Write on <a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Telegram</a> or open a pull request on <a href='https://github.com/akhomlyuk/IT_movies' target='_blank' rel='noopener noreferrer'>GitHub</a> — I review and publish them without long queues.",
      principlesH: "Principles",
      principlesP: "No affiliate links and no tracking beyond what Yandex Metrika collects, as described in the <a href='privacy.html'>privacy policy</a>. The code is open — any claim on this site can be verified in the repository.",
      linksLabel: "Links",
    },
```

- [ ] **Step 3: Sentinel test for RU/EN fidelity**

Create `_tmp/about_i18n_sentinel.js`:

```js
const fs = require("fs");
const src = fs.readFileSync("js/i18n.js", "utf8");
const needles = [
  'about.heading: "О сайте"',
  '"About the site"',
  '"хакерского"',
  "<a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Whitehat Lab</a>",
  "<b>КиноПоиска</b>",
  "журналах",
  "дата обновления берётся из истории Git",
  "<a href='privacy.html'>политике конфиденциальности</a>",
  "not inflated in either direction",
];
for (const n of needles) {
  if (!src.includes(n)) throw new Error("missing in js/i18n.js: " + n);
}
console.log("about i18n sentinel strings: OK");
```

Note: the sentinel `"журналах"` (not part of the real texts) is intentionally absent — remove it **before** running; its only purpose was to demonstrate the check catches drift. (If it remains, the check fails with `missing in js/i18n.js: "журналах"` — delete that line.)

- [ ] **Step 4: Run the sentinel + syntax checks**

Run: `node _tmp/about_i18n_sentinel.js`
Expected: `about i18n sentinel strings: OK`

Run: `node --check js/i18n.js`
Expected: no output, exit code 0.

- [ ] **Step 5: Regenerate derived files + full verify**

Run: `python tools/gen_pages.py` (regenerates `js/i18n.min.js` — expected: `js/i18n.min.js: generated`)
Run: `python tools/verify.py --strict --no-write`
Expected: last line `✅ All good` (i18n ru/en parity block prints `OK`; no stale-min errors). Note: `--no-write` keeps sitemap/robots untouched.

**Verification gate:** Steps 4–5 all pass.

---

### Task 2: `css/style.css` — add shared `.privacy` / `.profile*` styles

**Files:**
- Modify: `css/style.css` (append block at the end)

**Interfaces:**
- Produces: global classes `.privacy` (content card), `.profile`, `.profile-avatar`, `.profile-links` (+ a, a:hover/:focus-visible, svg, span, `@media 480px`) — consumed by Task 5 (`about.html` template + noscript). No name collisions exist in `style.css` today (verified: no `.privacy`/`.profile`/`.wrap` selectors).

- [ ] **Step 1: Append styles**

Append exactly this block at the end of `css/style.css`:

```css
.privacy {
  margin: 2.5rem 0 3rem;
  padding: 2rem 1.5rem;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.privacy h1,
.privacy h2:first-child {
  margin: 0 0 0.35rem;
  font-size: clamp(1.5rem, 4vw, 2rem);
  font-weight: 500;
}
.privacy h2 {
  margin: 1.6rem 0 0.5rem;
  font-size: 1.15rem;
  font-weight: 500;
}
.privacy p, .privacy ul {
  margin: 0.5rem 0;
  line-height: 1.6;
}
.privacy ul {
  padding-left: 1.25rem;
}
.privacy li {
  margin: 0.3rem 0;
}
.privacy code {
  font-family: ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace;
}
.privacy a {
  color: var(--ink);
  text-decoration: underline;
  text-decoration-color: var(--line-strong);
}
.privacy a:hover {
  text-decoration-color: var(--ink);
}
.profile {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin: 1.4rem 0 0.5rem;
  padding: 1.25rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
}
.profile-avatar {
  flex: none;
  width: clamp(88px, 20vw, 120px);
  height: clamp(88px, 20vw, 120px);
  border-radius: 50%;
  border: 2px solid var(--line-strong);
  object-fit: cover;
}
.profile-links {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}
.profile-links a {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.4rem 0.5rem;
  border-radius: 6px;
  color: var(--ink);
  text-decoration: none;
}
.profile-links a:hover,
.profile-links a:focus-visible {
  background: var(--hover);
  text-decoration: underline;
  text-decoration-color: var(--line-strong);
}
.profile-links svg {
  flex: none;
  width: 22px;
  height: 22px;
  fill: currentColor;
}
.profile-links span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 480px) {
  .profile {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
  .profile-links {
    width: 100%;
  }
  .profile-links a {
    justify-content: center;
  }
}
```

- [ ] **Step 2: Full verify**

Run: `python tools/verify.py --strict --no-write`
Expected: last line `✅ All good` (block 6b checks `url()` references — new rules introduce none; no broken references).

**Verification gate:** Step 2 passes.

---

### Task 3: `js/about.js` — new Vue app (film-page pattern)

**Files:**
- Create: `js/about.js`

**Interfaces:**
- Consumes: `window.ITMoviesCommon` (`safeRead`, `safeWrite`, `langFrom`, `themeFrom`, `toggleThemeClass`, `scrollToTop`, `installErrorHandler`), `window.I18N` (`t.*` existing keys + `about.*` from Task 1), Vue globals.
- Produces: standalone Vue app mounted on `#app` — later tasks depend on its public contract only through `about.html` (Task 5) linking `js/about.min.js`; `about.value` must expose `heading`, `lead`, `ideaH/P`, `whoH/P`, `recordH/P`, `siteH/P`, `suggestH/P`, `principlesH/P`, `linksLabel`.

- [ ] **Step 1: Write `js/about.js`**

Create `js/about.js` with exactly this content:

```js
const { createApp, computed, ref, watch, onMounted, onUnmounted } = Vue;

const {
  safeRead,
  safeWrite,
  langFrom,
  themeFrom,
  toggleThemeClass,
  scrollToTop,
  installErrorHandler,
} = window.ITMoviesCommon;

let currentLang = "ru";

const ABOUT_TEMPLATE = `
  <header class="top">
    <div class="brand">
      <div class="logo">
        <a href="./"><img src="static/logo.webp" alt="IT Movies" fetchpriority="high" decoding="async" width="100" height="100"></a>
      </div>
      <div class="brand-text">
        <h1>{{ about.heading }}</h1>
        <p v-if="altTitle">{{ altTitle }}</p>
      </div>
    </div>
    <div class="toolbar">
      <div class="switchers">
        <button type="button" class="lang" :aria-label="t.swapLang + ': ' + (lang === 'ru' ? 'RU' : 'EN')" @click="setLang(lang === 'ru' ? 'en' : 'ru')">🌐 {{ lang === 'ru' ? 'RU' : 'EN' }}</button>
        <button type="button" class="theme-toggle" :aria-label="theme === 'dark' ? t.themeToLight : t.themeToDark" @click="setTheme(theme === 'dark' ? 'light' : 'dark')">{{ theme === 'dark' ? '🌙' : '☀️' }}</button>
      </div>
    </div>
  </header>

  <main id="main" tabindex="-1">
    <nav class="breadcrumb" :aria-label="t.home">
      <a href="./">{{ t.home }}</a><span class="bc-sep"> › </span><span class="bc-current">{{ about.heading }}</span>
    </nav>

    <article class="privacy">
      <p>{{ about.lead }}</p>

      <div class="profile">
        <img class="profile-avatar" src="static/exited3n_avatar.png" alt="Exited3n" width="140" height="140" decoding="async">
        <nav class="profile-links">
          <span class="visually-hidden">{{ about.linksLabel }}</span>
          <a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer"><svg aria-hidden="true"><use href="#i-tg"></use></svg><span>Whitehat Lab</span></a>
          <a href="https://max.ru/join/ByzPb9lbZJwBbvKvRvi3ioBNaFF9TyuXDy5vrIX48vs" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-max"></use></svg><span>Whitehat Lab MAX</span></a>
          <a href="https://github.com/akhomlyuk" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-gh"></use></svg><span>GitHub</span></a>
          <a href="https://hackerlab.pro/users/Exited3n" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-hlab"></use></svg><span>Hackerlab</span></a>
          <a href="https://standoff365.com/profile/Exited3n/" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-standoff"></use></svg><span>Standoff 365</span></a>
          <a href="./"><svg aria-hidden="true"><use href="#i-movie"></use></svg><span>IT Movies</span></a>
        </nav>
      </div>

      <h2>{{ about.ideaH }}</h2>
      <p>{{ about.ideaP }}</p>

      <h2>{{ about.whoH }}</h2>
      <p v-html="about.whoP"></p>

      <h2>{{ about.recordH }}</h2>
      <p v-html="about.recordP"></p>

      <h2>{{ about.siteH }}</h2>
      <p>{{ about.siteP }}</p>

      <h2>{{ about.suggestH }}</h2>
      <p v-html="about.suggestP"></p>

      <h2>{{ about.principlesH }}</h2>
      <p v-html="about.principlesP"></p>
    </article>
  </main>

  <footer>
    <div class="footer-line">
      <span>{{ t.codedWith }}</span><span class="heart"> ♥ </span><a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer">Exited3n</a>
    </div>
    <div class="footer-line">
      <a class="footer-privacy" href="./">{{ t.title }}</a><span class="footer-privacy"> · </span><a class="footer-privacy" href="privacy.html">{{ t.privacy }}</a>
    </div>
  </footer>
  <button class="scroll-top" :aria-label="t.scrollTop" @click="scrollToTop">↑</button>
`;

const app = createApp({
  setup() {
    const urlParams = new URLSearchParams(location.search);
    const lang = ref(langFrom(urlParams, safeRead));

    const colorScheme = window.matchMedia("(prefers-color-scheme: light)");
    const theme = ref(themeFrom(urlParams, safeRead));
    let cleanupColorScheme = null;

    watch(
      theme,
      (value) => toggleThemeClass(value),
      { immediate: true }
    );

    onMounted(() => {
      const onColorScheme = (e) => {
        if (!safeRead("it-movies-theme")) {
          theme.value = e.matches ? "light" : "dark";
        }
      };
      colorScheme.addEventListener("change", onColorScheme);
      cleanupColorScheme = () =>
        colorScheme.removeEventListener("change", onColorScheme);
    });

    onUnmounted(() => {
      if (cleanupColorScheme) cleanupColorScheme();
    });

    function setLang(next) {
      lang.value = next;
    }

    function setTheme(next) {
      theme.value = next;
      safeWrite("it-movies-theme", next);
    }

    const t = computed(() => I18N[lang.value]);
    const about = computed(() => I18N[lang.value].about);
    const heading = computed(() => about.value.heading);
    const altTitle = computed(() =>
      lang.value === "ru" ? I18N.en.about.heading : I18N.ru.about.heading
    );

    watch(
      lang,
      (value) => {
        currentLang = value;
        safeWrite("it-movies-lang", value);
        document.documentElement.lang = value;
        document.title = I18N[value].about.title;
        const metaDesc = document.querySelector('meta[name="description"]');
        if (metaDesc) metaDesc.setAttribute("content", I18N[value].about.desc);
      },
      { immediate: true }
    );

    return {
      lang,
      theme,
      t,
      about,
      heading,
      altTitle,
      setLang,
      setTheme,
      scrollToTop,
    };
  },
  template: ABOUT_TEMPLATE,
});

installErrorHandler(app, () => currentLang, () => I18N);

app.mount("#app");
```

- [ ] **Step 2: Syntax check the new file**

Run: `node --check js/about.js`
Expected: no output, exit code 0.

**Verification gate:** Step 2 passes. (Full repo verify for `about.js` lands in Task 4 once verify's file lists include it.)

---

### Task 4: Pipeline — wire `about.js` into `gen_pages.py` + `verify.py`

**Files:**
- Modify: `tools/gen_pages.py:793` (minify list)
- Modify: `tools/verify.py:176,310,354-357,382` (4 lists)

**Interfaces:**
- Produces: `js/about.min.js` (generated), plus `verify.py` checks pressure on `about.js`/`about.min.js` — required by Task 5's full gate.

- [ ] **Step 1: `gen_pages.py` — add `about.js` to minify list**

In `tools/gen_pages.py`, `main()` (line ~788-794), change:

```python
        for name in ("i18n.js", "common.js", "app.js", "film.js")
```

to:

```python
        for name in ("i18n.js", "common.js", "app.js", "film.js", "about.js")
```

- [ ] **Step 2: `verify.py` — static-reference scan includes `about.js`**

Around line 170-177, after `film_js = (ROOT / "js" / "film.js").read_text(encoding="utf-8")`, add:

```python
about_js = (ROOT / "js" / "about.js").read_text(encoding="utf-8")
```

and change the `re.findall(...)` concatenation (line 176):

```python
    for r in re.findall(r"""['"]((?:static|\.\./static)/[^'"]+)['"]""", i18n_src + raw + app_js + film_js + catalog_src)
```

to:

```python
    for r in re.findall(r"""['"]((?:static|\.\./static)/[^'"]+)['"]""", i18n_src + raw + app_js + film_js + about_js + catalog_src)
```

- [ ] **Step 3: `verify.py` — bracket-balance list**

Line ~310, change:

```python
for name in ("app.js", "i18n.js", "film.js", "common.js"):
```

to:

```python
for name in ("app.js", "i18n.js", "film.js", "common.js", "about.js"):
```

- [ ] **Step 4: `verify.py` — node --check list**

Lines ~354-357, change:

```python
    for name in (
        "app.js", "i18n.js", "film.js", "common.js", "data.js",
        "catalog.js", "i18n.min.js", "common.min.js", "app.min.js", "film.min.js",
    ):
```

to:

```python
    for name in (
        "app.js", "i18n.js", "film.js", "common.js", "data.js", "about.js",
        "catalog.js", "i18n.min.js", "common.min.js", "app.min.js", "film.min.js", "about.min.js",
    ):
```

- [ ] **Step 5: `verify.py` — derived `.min.js` freshness list**

Line ~382, change:

```python
    for name in ("i18n.js", "common.js", "app.js", "film.js")
```

to:

```python
    for name in ("i18n.js", "common.js", "app.js", "film.js", "about.js")
```

- [ ] **Step 6: Regenerate + full verify**

Run: `python tools/gen_pages.py`
Expected: `js/about.min.js: generated` (plus re-generated `js/i18n.min.js` if not already current).
Run: `python tools/verify.py --strict --no-write`
Expected: last line `✅ All good`; bracket-balance and `node --check` include `about.js`/`about.min.js`; block 9b reports derived JS checked.

**Verification gate:** Steps 6 lines match expectations.

---

### Task 5: `about.html` — rebuild page on the shared shell

**Files:**
- Modify: `about.html` (full rewrite of `<head>` styles + `<body>`)

**Interfaces:**
- Consumes: `js/vue.global.prod.js`, `js/i18n.min.js`, `js/common.min.js`, `js/about.min.js` (Task 4), sprite `#i-*` symbols, `css/style.css` classes from Task 2.

- [ ] **Step 1: Rebuild `about.html`**

Replace the entire file with:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>О сайте — IT Movies</title>
  <meta name="description" content="О сайте IT Movies: кто создал каталог кино о компьютерах и ИИ, как отбираются фильмы и как предложить свой.">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:locale:alternate" content="en_US">
  <meta property="og:title" content="О сайте — IT Movies">
  <meta property="og:description" content="О сайте IT Movies: кто создал каталог кино о компьютерах и ИИ, как отбираются фильмы и как предложить свой.">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://akhomlyuk.github.io/IT_movies/static/ogimage.webp">
  <meta property="og:url" content="https://akhomlyuk.github.io/IT_movies/about.html">
  <meta property="og:site_name" content="IT Movies">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="https://akhomlyuk.github.io/IT_movies/static/ogimage.webp">
  <link rel="canonical" href="https://akhomlyuk.github.io/IT_movies/about.html">
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" content="#eef1f6">
  <meta name="theme-color" content="#171b2d" media="(prefers-color-scheme: dark)">
  <!-- COPY theme-script block byte-for-byte from the current file (between begin/end:theme-script markers, lines 22-42) — do not retype -->
  <link rel="manifest" href="static/site.webmanifest">
  <link rel="icon" href="static/favicons/favicon.ico" sizes="48x48">
  <link rel="icon" type="image/png" sizes="16x16" href="static/favicons/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="static/favicons/favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="48x48" href="static/favicons/favicon-48x48.png">
  <link rel="icon" type="image/png" sizes="64x64" href="static/favicons/favicon-64x64.png">
  <link rel="icon" type="image/png" sizes="128x128" href="static/favicons/favicon-128x128.png">
  <link rel="icon" type="image/png" sizes="256x256" href="static/favicons/favicon-256x256.png">
  <link rel="apple-touch-icon" sizes="57x57" href="static/favicons/apple-touch-icon-57x57.png">
  <link rel="apple-touch-icon" sizes="114x114" href="static/favicons/apple-touch-icon-114x114.png">
  <link rel="apple-touch-icon" sizes="120x120" href="static/favicons/apple-touch-icon-120x120.png">
  <link rel="apple-touch-icon" href="static/favicons/apple-touch-icon.png">
  <meta name="msapplication-TileColor" content="#eef1f6">
  <link rel="stylesheet" href="css/style.css">
  <link rel="preload" href="static/fonts/ubuntu-cyrillic-400-normal.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="preload" href="static/fonts/ubuntu-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "AboutPage",
    "name": "О сайте — IT Movies",
    "url": "https://akhomlyuk.github.io/IT_movies/about.html",
    "description": "О сайте IT Movies: кто создал каталог кино о компьютерах и ИИ, как отбираются фильмы и как предложить свой.",
    "inLanguage": ["ru", "en"],
    "isPartOf": {
      "@type": "WebSite",
      "name": "IT Movies",
      "url": "https://akhomlyuk.github.io/IT_movies/"
    },
    "about": {
      "@type": "Person",
      "name": "Andrey (Exited3n)",
      "alternateName": "Exited3n",
      "jobTitle": "Cybersecurity enthusiast",
      "url": "https://t.me/wh_lab",
      "sameAs": [
        "https://t.me/wh_lab",
        "https://github.com/akhomlyuk"
      ]
    },
    "creator": {
      "@type": "Person",
      "name": "Andrey (Exited3n)",
      "url": "https://t.me/wh_lab"
    }
  }
  </script>
</head>
<body>
  <svg xmlns="http://www.w3.org/2000/svg" style="display:none" aria-hidden="true">
    <symbol id="i-tg" viewBox="0 0 24 24"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></symbol>
    <symbol id="i-max" viewBox="0 0 1000 1000"><path d="M508.211 878.328c-75.007 0-109.864-10.95-170.453-54.75-38.325 49.275-159.686 87.783-164.979 21.9 0-49.456-10.95-91.248-23.36-136.873-14.782-56.21-31.572-118.807-31.572-209.508 0-216.626 177.754-379.597 388.357-379.597 210.785 0 375.947 171.001 375.947 381.604.707 207.346-166.595 376.118-373.94 377.224m3.103-571.585c-102.564-5.292-182.499 65.7-200.201 177.024-14.6 92.162 11.315 204.398 33.397 210.238 10.585 2.555 37.23-18.98 53.837-35.587a189.8 189.8 0 0 0 92.71 33.032c106.273 5.112 197.08-75.794 204.215-181.95 4.154-106.382-77.67-196.486-183.958-202.574Z"/></symbol>
    <symbol id="i-gh" viewBox="0 0 24 24"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></symbol>
    <symbol id="i-hlab" viewBox="0 0 837.8 616.6"><path fill="currentColor" d="M257.1,124.1c-29.8,25.5-32.4,52.7-32.4,89.8c0,63.4-14.7,172.2,107,263.6C262,375.6,271.1,277.5,271,206c-0.1-36.3,1.4-66.9,24.1-96.8C281.5,112.1,268.5,116,257.1,124.1L257.1,124.1z"/><path fill="#36f097" d="M382.1,515.2c-28.9-119.8-25.4-224.9-25.4-305.5c0-39.4-1.6-80.3,10.1-118.4l-40.1,9.9c-19.6,31.9-18,70.7-18,106.6c0.1,75.1-6.4,176.5,45.2,286.2C363.3,501.2,372.7,508.2,382.1,515.2L382.1,515.2z"/><path fill="#36f097" d="M398.3,83.5c-8.4,76.2-4.4,154.8-3.8,231.4c0.6,72.4,3.2,144.9,9.7,217c13.1,9.8,15.1,9.8,28.2,0c6.6-72.1,9.1-144.6,9.8-217c0.7-76.6,4.7-155.1-3.8-231.4C422,79.5,414.6,79.5,398.3,83.5L398.3,83.5z"/><path fill="#36f097" d="M454.6,515.2c9.4-7.1,18.8-14.1,28.2-21.1c51.6-109.6,45.2-211,45.2-286.2c0.1-36,1.7-74.7-18-106.6l-40.1-9.9c11.7,38.2,10.1,79,10.1,118.4C479.9,290.6,483.5,395.5,454.6,515.2L454.6,515.2z"/><path fill="currentColor" d="M611.9,213.9c0-37.1-2.6-64.3-32.4-89.8-11.4-8.2-24.4-12-38-15c22.7,29.9,24.2,60.6,24.1,96.9c-0.2,69.8,9.3,169.1-60.8,271.5C624.1,388.1,611.9,284.2,611.9,213.9L611.9,213.9z"/><path fill="currentColor" d="M631.6,233.5c0,41.8,3.1,82.6-17.7,136.4c46.7,23.6,129.3,70,142.9,120.4c22.2-6,31.9-32.5,18.3-51c-22-30-59.4-59.4-113.1-89c10.5-41,9.5-70.6,9.5-91.7c54.7-26.9,126-66.4,159.8-117.3c12.8-19.3,1.7-45.4-21-50C797.8,152.4,689.4,206.4,631.6,233.5L631.6,233.5z"/><path fill="currentColor" d="M205.1,192.9c0-7.6-0.7-22.6,6.6-41.2c11.4-29.3,36.4-51.2,66.9-58.8l139.7-34.6L558,92.9c43.2,10.7,73.6,49.5,73.6,94.1v5.9c76.1-37.3,160.2-86.7,167.7-157.1c2.6-24.2-21.4-42.6-44.2-33.4c16.8,41.5-11.8,72-46.8,99.2c-13.4,10.3-29.5,20.7-48,31.2c-4.4-10.2-10-19.8-16.8-28.7c20.2-14.2,45.3-36.1,56-62.6c8.6-21.5-12.2-43.1-34-35.1c9.3,25.5-23.8,54.3-49.1,71c-29.1-21.7-38.3-20.3-198.2-60.2C260.9,56.5,249.9,55.1,220.1,77.4C194.8,60.8,161.7,32,171,6.4c-21.7-8-42.6,13.6-34,35.1c10.7,26.6,35.8,48.4,56,62.6c-6.7,8.8-12.4,18.5-16.8,28.7c-16-9.1-33.8-20.2-48.2-31.3C92.8,75.2,65.2,43,81.6,2.4C59-6.8,34.8,11.5,37.4,35.8C45.2,109.6,138.4,160.2,205.1,192.9L205.1,192.9z"/><path fill="currentColor" d="M165.2,258.6c0,20.4-1,50.4,9.5,91.7C121,380,83.6,409.4,61.6,439.4c-13.6,18.6-3.9,45,18.3,51c13.6-50.6,96.2-96.7,142.9-120.5c-20.6-53.5-17.7-93.1-17.7-136.4C143.7,204.7,38.7,151.7,26.4,91.2c-22.7,4.6-33.8,30.8-21,50C39.1,192,110.3,231.6,165.2,258.6z"/><path fill="currentColor" d="M746.5,543.2c-11.7-63.3-88.3-109.1-148.2-140c-34.2,61.5-67.8,79.7-180,163.8l-107.5-80.6c-29.7-22.4-54.4-50.7-72.5-83.2c-57.9,29.9-136.4,76-148.2,140c-4.4,23.7,18.6,43.7,41.8,35.8c-4.1-12-16.7-48.7,56.4-99.8c1.7-1.1,13.7-10.1,36.6-23.4c6.2,8.3,12.7,16.3,19.7,23.9c-20.9,13.8-50.8,37.5-62.7,67.1c-8.7,21.5,12.2,43.1,34,35.1c-10.3-28.1,30.8-60.1,56.4-75.6c10.7,9.1,1.5,1.9,146.1,110.3c143.5-107.6,135-100.9,146.1-110.3c25.5,15.5,66.6,47.5,56.3,75.6c21.8,8,42.6-13.6,34-35.1c-11.9-29.6-41.8-53.4-62.7-67.1c7-7.6,13.5-15.6,19.7-23.9c23,13.2,35,22.2,36.7,23.4c73.1,51.1,60.5,87.7,56.3,99.8l0,0C727.8,586.9,751,567.1,746.5,543.2L746.5,543.2z"/></symbol>
    <symbol id="i-standoff" viewBox="0 0 32 33"><rect y="0.318848" width="32" height="32" rx="8" fill="black"/><path d="M16.5129 14.9322V12.3188H25V13.715V14.441V20.8997H21.9124H21.6113H21.4319V18.2758H16.5129V15.766H21.4319V14.9322H16.5129Z" fill="white"/><path d="M10.5682 14.9322H15.4868V12.3188H7V13.715V14.441V20.8997H10.0875H10.3888H10.5682V18.2758H15.4871V15.766H10.5682V14.9322Z" fill="white"/></symbol>
    <symbol id="i-movie" viewBox="0 0 24 24"><path d="M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4z"/></symbol>
  </svg>
  <div id="app" v-cloak>
    <noscript>
      <header class="top">
        <div class="brand">
          <div class="logo">
            <a href="./"><img src="static/logo.webp" alt="IT Movies" width="100" height="100"></a>
          </div>
          <div class="brand-text">
            <h1>О сайте</h1>
            <p>About the site</p>
          </div>
        </div>
      </header>
      <main>
        <nav class="breadcrumb" aria-label="Главная">
          <a href="./">Главная</a><span class="bc-sep"> › </span><span class="bc-current">О сайте</span>
        </nav>
        <article class="privacy">
          <p>IT Movies — вручную собранный и поддерживаемый мной каталог фильмов, сериалов и документалок о компьютерах, киберпанке, интернете, ИИ и т.д. Без алгоритмов и ссылок на стриминги (не маленькие, сами найдете)</p>
          <div class="profile">
            <img class="profile-avatar" src="static/exited3n_avatar.png" alt="Exited3n" width="140" height="140" decoding="async">
            <nav class="profile-links">
              <span class="visually-hidden">Ссылки</span>
              <a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer"><svg aria-hidden="true"><use href="#i-tg"></use></svg><span>Whitehat Lab</span></a>
              <a href="https://max.ru/join/ByzPb9lbZJwBbvKvRvi3ioBNaFF9TyuXDy5vrIX48vs" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-max"></use></svg><span>Whitehat Lab MAX</span></a>
              <a href="https://github.com/akhomlyuk" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-gh"></use></svg><span>GitHub</span></a>
              <a href="https://hackerlab.pro/users/Exited3n" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-hlab"></use></svg><span>Hackerlab</span></a>
              <a href="https://standoff365.com/profile/Exited3n/" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-standoff"></use></svg><span>Standoff 365</span></a>
              <a href="./"><svg aria-hidden="true"><use href="#i-movie"></use></svg><span>IT Movies</span></a>
            </nav>
          </div>
          <h2>Для кого это всё</h2>
          <p>Для тех кто постоянно пишет мне в личку и/или чатах, форумах, что бы такого "хакерского" посмотреть. Тут все собрано в одном месте — это список, который я реально порекомендовал бы товарищам.</p>
          <h2>Кто за этим стоит и как отбираются фильмы</h2>
          <p>Подборку веду сам, мой канал <a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer">Whitehat Lab</a>. Это некоммерческий pet-проект, написать мне можно по ссылкам выше.</p>
          <h2>Что внутри каждой записи</h2>
          <p>Английское и русское название, год, жанры, короткое описание на двух языках и постер. Рейтинги <b>КиноПоиска</b> и <b>IMDB</b> — ровно такие, какими были на момент обновления: без накрутки в ту или иную сторону.</p>
          <h2>Как устроен сайт</h2>
          <p>Статическая сборка без бекенда, аккаунтов и комментариев. Есть фильтры по типу, жанру, году и рейтингу, сортировка, русский и английский интерфейс, светлая и тёмная тема — и всё работает даже без JavaScript. Все данные в одном открытом файле, дата обновления берётся из истории Git.</p>
          <h2>Как предложить фильм</h2>
          <p>Нашли ошибку или знаете отличный фильм? Пишите в <a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer">Telegram</a> или открывайте pull request на <a href="https://github.com/akhomlyuk/IT_movies" target="_blank" rel="noopener noreferrer">GitHub</a> — проверяю и публикую без долгих очередей.</p>
          <h2>Принципы</h2>
          <p>Никаких партнёрских ссылок и трекинга сверх того, что собирает яндекс метрика, описано в <a href="privacy.html">политике конфиденциальности</a>. Код открыт — любое утверждение на сайте можно проверить в репозитории.</p>
        </article>
      </main>
      <footer>
        <div class="footer-line">
          <span>Сделано с</span><span class="heart"> ♥ </span><a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer">Exited3n</a>
        </div>
        <div class="footer-line">
          <a class="footer-privacy" href="./">IT Movies</a><span class="footer-privacy"> · </span><a class="footer-privacy" href="privacy.html">Политика конфиденциальности</a>
        </div>
      </footer>
    </noscript>
  </div>

  <script src="js/vue.global.prod.js" defer></script>
  <script src="js/i18n.min.js" defer></script>
  <script src="js/common.min.js" defer></script>
  <script src="js/about.min.js" defer></script>
  <!-- COPY metrika block byte-for-byte from the current file (between begin/end:metrika markers, lines 451-453) — do not retype -->
</body>
</html>
```

- [ ] **Step 2: Full repo gate**

Run: `python tools/gen_pages.py`
Expected: `js/about.min.js: generated` (first time), then no further output.
Run: `python tools/verify.py --strict` (WITHOUT `--no-write` — lets it regenerate sitemap/robots if stale)
Expected: last line `✅ All good`. Specifically: about.html theme block OK (9d), Metrika present (9c), canonical single+parameterless (`…/about.html`), lang/OG coherence OK, JSON-LD untouched, static refs all resolve (`js/about.min.js`, `static/logo.webp`, `static/exited3n_avatar.png`, sprite has no file refs).

- [ ] **Step 3: Manual browser smoke (optional but recommended)**

Run: `python -m http.server 8000`, open `http://localhost:8000/about.html` and verify:
- header h1 «О сайте» + subtitle «About the site»; breadcrumb `Главная › О сайте`;
- profile card renders avatar + 6 icon links (icons visible — sprite `#i-*` resolves from inside the Vue template);
- lang toggle switches all texts to EN (title, headings, paragraphs), `?lang=en` works; theme toggle + `?theme=dark` work;
- `document.title` / meta description switch with lang;
- disable JS (DevTools → Network: disable cache + JS) → full RU noscript layout displays, no double lang blocks.

- [ ] **Step 4: Final combined commit (per user instruction)**

```bash
git add -A
git commit -m "rebuild about page on shared vue/i18n infrastructure"
```

**Verification gate:** Step 2 prints `✅ All good`; Step 3 pass on visual checks; Step 4 creates the single combined commit (includes previously-staged `static/exited3n_avatar.png` and modified `about.html` from the earlier profile-card work, plus this plan's changes: `js/i18n.js`, `js/i18n.min.js`, `js/about.js`, `js/about.min.js`, `css/style.css`, `about.html`, `tools/gen_pages.py`, `tools/verify.py`).

---

## Self-Review Notes

- **Spec coverage:** every spec section maps to a task — i18n keys → T1; shared CSS → T2; Vue app → T3; pipeline lists → T4; page rebuild + noscript + smoke + final commit → T5; "не трогаем" list → no task touches those files.
- **Text fidelity:** all RU/EN strings in T1/T5 are copied verbatim from the spec table, which came byte-for-byte from the current `about.html`. T1's sentinel test pins the drift-prone literals.
- **No placeholders:** all code blocks are complete; the only "copy from current file" notes are the two generated blocks (theme-script, Metrika), which by project rule must never be retyped.
- **Type/name consistency:** `about.value.*` names in `about.js` match the i18n keys from T1 (`heading`, `lead`, `ideaH/P`, `whoH/P`, `recordH/P`, `siteH/P`, `suggestH/P`, `principlesH/P`, `linksLabel`); common.js helper names match `film.js` usage exactly.
- **Review Focus coverage:** text drift → T1 Step 3; JS validity → T2/T4 (`node --check`); min freshness → T4 Step 6/T5 Step 2 (block 9b); no-JS fallback → T5 Step 3; sprite-in-template → T5 Step 3.