#!/usr/bin/env node
/* Node smoke harnesses for the IT Movies static site.
   Usage: node tools/smoke.js <app|slug|film|related>
   Replaces the four inline node -e harnesses that used to live in verify.py. */
"use strict";

const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");

function read(p) {
  return fs.readFileSync(path.join(ROOT, p), "utf8");
}

const MINIFY_MAP = {
  "i18n.js": "i18n.min.js",
  "common.js": "common.min.js",
  "app.js": "app.min.js",
  "film.js": "film.min.js",
};

let min = false;
let mode = process.argv[2];
if (mode === "--min") {
  min = true;
  mode = process.argv[3];
} else if (process.argv.includes("--min")) {
  min = true;
}

function jsSrc(name) {
  return read("js/" + (min && MINIFY_MAP[name] ? MINIFY_MAP[name] : name));
}

const MIN_LABEL = min ? " (minified)" : "";

function bootApp() {
  global.window = global;
  global.location = {
    pathname: "/IT_movies/",
    search: "",
    href: "https://example.org/IT_movies/",
  };
  Object.defineProperty(global, "navigator", {
    value: { language: "ru" },
    configurable: true,
    enumerable: true,
    writable: true,
  });
  Object.defineProperty(global, "performance", {
    value: { getEntriesByType: () => [], now: () => 1000 },
    configurable: true,
  });
  global.document = {
    querySelector: () => ({ setAttribute() {} }),
    documentElement: { classList: { add() {}, toggle() {} }, lang: "" },
    title: "",
    body: {},
  };
  global.history = { replaceState() {} };
  global.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  global.addEventListener = () => {};
  global.removeEventListener = () => {};
  global.localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
  const noop = () => {};
  let captured = null;
  global.Vue = {
    createApp: (opts) => {
      captured = opts.setup;
      return { components: {}, config: {}, mount: noop };
    },
    computed: (fn) => ({ value: fn() }),
    reactive: (o) => o,
    ref: (v) => ({ value: v }),
    watch: noop,
    onMounted: noop,
    onUnmounted: noop,
    nextTick: () => Promise.resolve(),
  };
  return () => captured;
}

if (mode === "slug") {
  global.window = global;
  eval(jsSrc("catalog.js"));
  eval(jsSrc("common.js"));
  const api = global.ITMoviesCommon;
  console.log(JSON.stringify(global.CATALOG.map((it) => api.itemSlug(it))));
} else if (mode === "app") {
  const captured = bootApp();
  eval(
    jsSrc("i18n.js") + "\n" +
    jsSrc("common.js") + "\n" +
    jsSrc("catalog.js") + "\n" +
    jsSrc("app.js")
  );
  const setup = captured();
  const state = setup();
  if (!state || typeof state.movies.value.length !== "number" || !state.setLang) {
    throw new Error("app.js setup() returned invalid state");
  }
  if (!state.featured || !Array.isArray(state.featured.value) || state.featured.value.length === 0) {
    throw new Error("app.js must expose a non-empty featured shelf");
  }
  if (new Set(state.featured.value.map((item) => item.type)).size < 2) {
    throw new Error("app.js featured shelf must include more than one media type");
  }
  if (typeof state.pickFeatured !== "function") {
    throw new Error("app.js must expose pickFeatured for recommendation shuffling");
  }
  const featuredWithSeed = state.pickFeatured(global.CATALOG, () => 0.25);
  if (featuredWithSeed.length !== 8 || new Set(featuredWithSeed.map((item) => item.type)).size < 3) {
    throw new Error("pickFeatured must return eight mixed recommended titles");
  }
  if (typeof state.resetFilters !== "function" || !state.hasActiveFilters) {
    throw new Error("app.js must expose filter reset state");
  }
  if (!state.genre) {
    throw new Error("app.js must expose genre filter state");
  }
  if (!state.genreOptions || state.genreOptions.value.length !== 17) {
    throw new Error("app.js must expose all genre filter options");
  }
  const genreLabels = state.genreOptions.value.map((option) => option[1]);
  const sortedGenreLabels = genreLabels.slice().sort((a, b) => a.localeCompare(b, "ru"));
  if (genreLabels.join("|") !== sortedGenreLabels.join("|")) {
    throw new Error("genre filter options must be alphabetically sorted");
  }
  state.query.value = "matrix";
  state.onlyFav.value = true;
  state.genre.value = "ai";
  state.resetFilters();
  if (state.query.value || state.onlyFav.value || state.genre.value) {
    throw new Error("app.js resetFilters must clear search and recommendation state");
  }
  const total = state.movies.value.length + state.series.value.length + state.documentaries.value.length;
  if (total !== global.CATALOG.length) {
    throw new Error("sections total " + total + " != CATALOG.length " + global.CATALOG.length);
  }
  const mainMarkup = read("index.html");
  const styleSource = read("css/style.css");
  if (!mainMarkup.includes('class="title-layout"')) {
    throw new Error("index.html must keep title cell layout inside a table-cell-safe wrapper");
  }
  if (!mainMarkup.includes('class="title-primary"')) {
    throw new Error("index.html must isolate title line clamping from the inline link");
  }
  if (!mainMarkup.includes('class="mobile-sort"')) {
    throw new Error("index.html must preserve genre sorting on mobile");
  }
  if (!mainMarkup.includes('id="genre-filter"')) {
    throw new Error("index.html must expose the genre filter control");
  }
  if (!mainMarkup.includes('class="catalog-tools"')) {
    throw new Error("index.html must group search and genre controls");
  }
  const aboutMarkup = read("about.html");
  if (!aboutMarkup.includes('class="about-article"') || !aboutMarkup.includes('class="about-section"')) {
    throw new Error("about.html must expose the structured article and sections");
  }
  const aboutSource = read("js/about.js");
  if (!aboutSource.includes('class="about-article"') || !aboutSource.includes('class="about-section"')) {
    throw new Error("about.js must expose the structured article and sections");
  }
  if (styleSource.includes("min-width: 640px")) {
    throw new Error("style.css must not force horizontal table scrolling on mobile");
  }
  if (!styleSource.includes("font-size: clamp(1.3rem, 2vw, 1.7rem)")) {
    throw new Error("brand heading scale must use the reduced compact clamp");
  }
  if (!styleSource.includes("grid-template-columns: 32px 32px")) {
    throw new Error("title layout must use equal icon columns");
  }
  if (styleSource.includes(".title-cell {\n  display: flex")) {
    throw new Error("style.css must not turn the table title cell into a flex item");
  }
  if (!styleSource.includes("grid-column: 3")) {
    throw new Error("title copy must have an explicit grid position independent of heart visibility");
  }
  if (!styleSource.includes(".title-cell a") || !styleSource.includes("display: inline;")) {
    throw new Error("title links must remain inline instead of stretching across the full column");
  }
  if (!mainMarkup.includes('class="catalog-status"')) {
    throw new Error("index.html must keep result status outside the search control row");
  }
  if (mainMarkup.includes('src="static/favorite_32.png"')) {
    throw new Error("index.html must use an inline SVG recommendation icon");
  }
  if (!mainMarkup.includes('class="icon poster-icon-svg"')) {
    throw new Error("index.html must use the inline SVG poster icon");
  }
  if (mainMarkup.includes("poster_icon.")) {
    throw new Error("poster icon must not be loaded as an image asset");
  }
  if (styleSource.includes("monospace")) {
    throw new Error("style.css must not introduce a monospace font override");
  }
  const privacySource = read("privacy.html");
  if (privacySource.includes("monospace")) {
    throw new Error("privacy.html must not introduce a monospace font override");
  }
  const api = global.ITMoviesCommon;
  for (const it of global.CATALOG) {
    const url = api.imdbUrl(it);
    if (it.imdbId && url !== "https://www.imdb.com/title/" + it.imdbId + "/") {
      throw new Error("imdbUrl mismatch: " + it.titleEn);
    }
    if (!it.imdbId && url) {
      throw new Error("imdbUrl for record without imdbId must be null: " + it.titleEn);
    }
  }
  console.log("app.js smoke (catalog.js, sections sum == CATALOG): OK" + MIN_LABEL);
} else if (mode === "film") {
  const filmSource = read("js/film.js");
  if (!filmSource.includes('class="film-header-title"')) {
    throw new Error("film.js must expose the film title in the header");
  }
  if (filmSource.includes('class="film-title"')) {
    throw new Error("film.js must not duplicate the giant film title in the hero");
  }
  if (!filmSource.includes('class="film-meta"')) {
    throw new Error("film.js must expose a structured metadata block");
  }
  if (!filmSource.includes('class="bc-type"')) {
    throw new Error("film.js must expose a compact breadcrumb category");
  }
  if (!filmSource.includes('class="rc-poster"')) {
    throw new Error("film.js must render related poster thumbnails");
  }
  if (filmSource.includes('class="fav-icon"')) {
    throw new Error("film.js must not render recommendation hearts in related cards");
  }
  const generatorSource = read("tools/gen_pages.py");
  if (!generatorSource.includes('film-header-title')) {
    throw new Error("generated film pages must keep the title in the header");
  }
  if (generatorSource.includes('class="film-title"')) {
    throw new Error("generated film pages must not duplicate the giant title in the hero");
  }
  if (!generatorSource.includes('film-meta')) {
    throw new Error("generated film pages must include structured metadata");
  }
  if (!generatorSource.includes('bc-type')) {
    throw new Error("generated film pages must include compact breadcrumb metadata");
  }
  if (!generatorSource.includes('"poster",')) {
    throw new Error("generated related records must include poster data");
  }
  if (generatorSource.includes('class="fav-icon"')) {
    throw new Error("generated film pages must not render recommendation hearts in related cards");
  }
  const capture = bootApp();
  eval(
    jsSrc("i18n.js") + "\n" +
    jsSrc("common.js") + "\n" +
    read("js/data.js") + "\n" +
    jsSrc("film.js")
  );
  const pool = global.CATALOG.slice(1, 10);
  global.FILM_PAGE = {
    item: global.CATALOG[0],
    related: global.CATALOG.slice(1, 3),
    relatedPool: pool,
    posterW: null,
    posterH: null,
  };
  const setup = capture();
  const poolSlugs = new Set(pool.map((r) => global.ITMoviesCommon.itemSlug(r)));
  const seen = new Set();
  for (let i = 0; i < 12; i++) {
    const state = setup();
    if (!state || typeof state.related.length !== "number" || !state.itemSlug) {
      throw new Error("film.js setup() returned invalid state");
    }
    if (!state.desc.value) {
      throw new Error("film.js desc is empty");
    }
    if (state.related.length !== 4) {
      throw new Error("film.js related must have 4 items, got " + state.related.length);
    }
    const slugs = state.related.map((r) => global.ITMoviesCommon.itemSlug(r));
    if (new Set(slugs).size !== 4 || slugs.some((s) => !poolSlugs.has(s))) {
      throw new Error("film.js related must be 4 distinct relatedPool items: " + slugs.join(","));
    }
    seen.add(slugs.slice().sort().join("|"));
  }
  if (seen.size < 2) {
    throw new Error("film.js related must vary across loads, got " + seen.size + " unique set(s)");
  }
  global.FILM_PAGE = {
    item: global.CATALOG[0],
    related: global.CATALOG.slice(1, 3),
    posterW: null,
    posterH: null,
  };
  const fallbackState = setup();
  if (fallbackState.related.length !== 2) {
    throw new Error("film.js related must fall back to static related without a pool, got " + fallbackState.related.length);
  }
  console.log("film.js smoke (FILM_PAGE, no data.js load on film page): OK" + MIN_LABEL);
} else if (mode === "related") {
  bootApp();
  eval(
    jsSrc("i18n.js") + "\n" +
    jsSrc("common.js") + "\n" +
    read("js/data.js") + "\n" +
    jsSrc("film.js") + "\n" +
    "global.__relatedItems = relatedItems;"
  );
  const fakeDoc = { type: "documentary", titleEn: "Doc", genres: ["history"], kpId: 999001 };
  const fakeFic = { type: "movie", titleEn: "Fic", genres: ["history"], kpId: 999002 };
  const ficRel = global.__relatedItems([fakeDoc, fakeFic], fakeFic, 4);
  if (ficRel.some((r) => r.type === "documentary")) {
    throw new Error("relatedItems must not return documentaries for non-documentary items");
  }
  const docRel = global.__relatedItems([fakeDoc, fakeFic], fakeDoc, 4);
  if (docRel.length !== 1 || docRel[0] !== fakeFic) {
    throw new Error("relatedItems must allow non-documentary items for documentaries");
  }
  const cat = global.CATALOG;
  const N = 6;
  const api = global.ITMoviesCommon;
  const out = cat.map((it) => global.__relatedItems(cat, it, N).map((r) => api.itemSlug(r)));
  console.log(JSON.stringify(out));
} else {
  console.error("usage: node tools/smoke.js <app|slug|film|related>");
  process.exit(2);
}