#!/usr/bin/env node
/* Node smoke harnesses for the IT Movies static site.
   Usage: node tools/smoke.js <app|slug|film>
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
  if (featuredWithSeed.length !== 6 || new Set(featuredWithSeed.map((item) => item.type)).size < 3) {
    throw new Error("pickFeatured must return six mixed recommended titles");
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
  const styleSource = read("css/style.css").replace(/\r\n/g, "\n");
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
  if (!styleSource.includes("font-size: clamp(1.3rem, 2vw, 1.6rem)")) {
    throw new Error("brand heading scale must use the reduced compact clamp");
  }
  if (!styleSource.includes(".title-layout {\n  display: flex")) {
    throw new Error("title layout must be a flex row with no reserved heart track");
  }
  if (styleSource.includes(".title-cell {\n  display: flex")) {
    throw new Error("style.css must not turn the table title cell into a flex item");
  }
  if (mainMarkup.indexOf('class="title-copy"') === -1 || mainMarkup.indexOf('class="title-copy"') > mainMarkup.indexOf('class="fav-icon"')) {
    throw new Error("title heart must follow the title copy at the row end");
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
  if (!filmSource.includes('<h1 class="film-title">{{ title }}</h1>')) {
    throw new Error("film.js must expose the film title as the card's h1"
      + " (the header carries the site name, not the film)");
  }
  if (filmSource.includes('film-header-title')) {
    throw new Error("film.js must not repeat the film title in the header");
  }
  if (!/class="film-info">\s*\n\s*<h1 class="film-title">/.test(filmSource)) {
    throw new Error("the film title must be the first child of .film-info, not"
      + " something below the metadata row");
  }
  if (!/<figure class="film-poster"[^>]*>\s*\n\s*<img[^>]*>\s*\n\s*<span class="film-badge"/.test(filmSource)) {
    throw new Error("the author-pick badge belongs on the poster, inside .film-poster");
  }
  if (/\.film-info">[\s\S]{0,400}?class="film-badge"/.test(filmSource)) {
    throw new Error("the author-pick badge must not stay in .film-info");
  }
  if (!filmSource.includes('class="film-meta"')) {
    throw new Error("film.js must expose a structured metadata block");
  }
  // The rail: arrows and dots, shown only when the strip overflows. Asserted on
  // film.js because this markup lives there (unlike the card, which is the
  // generator's). The overflow condition is the design decision -- controls for a
  // strip that does not scroll are worse than no controls.
  // The rail's controls are DOTS ONLY. The partner dropped the arrows on
  // 2026-09-30: on a phone the strip is dragged with a finger, on a desktop
  // with a mouse or the left/right keys, and the dots jump. A button that
  // pages a strip the reader can already drag is a control for its own sake.
  for (const [what, needle] of [
    ["a scrollable track", 'class="related-track"'],
    ["dot pagination", 'class="related-dot"'],
  ]) {
    if (!filmSource.includes(needle)) {
      throw new Error("film.js must render " + what + " (" + needle + ")");
    }
  }
  if (filmSource.includes('class="related-nav')) {
    throw new Error("the related strip has no arrow buttons; it is dots, drag"
      + " and the left/right keys. Remove .related-nav rather than hiding it");
  }
  if (filmSource.includes('class="related-rail')) {
    throw new Error(".related-rail only existed to sit the two arrows beside"
      + " the track; with them gone it is an empty wrapper around .related-track");
  }
  // From lg up there is no carousel at all: all six cards sit in one row and the
  // dots have nothing to page. Six cards that scroll 40px on a desktop is not a
  // carousel, it is a scrollbar with extra steps.
  const railCss = read("css/style.css");
  // Every @media (min-width: 1024px) block, not just the first: the stylesheet
  // has several, and picking the first one silently checks somebody else's rules.
  const mdBlocks = [];
  const mdRe = /@media \(min-width: 1024px\)\s*\{/g;
  let md;
  while ((md = mdRe.exec(railCss)) !== null) {
    let depth = 0;
    let end = md.index + md[0].length;
    for (let i = end - 1; i < railCss.length; i++) {
      if (railCss[i] === "{") depth++;
      else if (railCss[i] === "}") {
        depth--;
        if (depth === 0) { end = i + 1; break; }
      }
    }
    mdBlocks.push(railCss.slice(md.index + md[0].length, end - 1));
  }
  const mdRail = mdBlocks.find(
    (b) => /\.related ul\s*\{[^}]*display:\s*grid/.test(b)
  );
  if (!mdRail) {
    throw new Error(
      "css/style.css must turn .related ul into a grid inside a"
      + " @media (min-width: 1024px) block, so the cards stop being a carousel"
      + " on a desktop. Found " + mdBlocks.length + " such block(s), none a grid"
    );
  }
  // One row, not two: six cards is the whole point of the rail, and a 3-column
  // grid would halve it back to the layout this replaced.
  const cols = (mdRail.match(/\.related ul\s*\{[^}]*grid-template-columns:\s*repeat\((\d+)/) || [])[1];
  if (cols !== "6") {
    throw new Error(
      "the lg grid must lay the six related cards out in ONE row"
      + " (repeat(6, minmax(0, 1fr))), found repeat(" + (cols || "none") + ")"
    );
  }
  if (!/\.related-dots\s*\{[^}]*display:\s*none/.test(mdRail)) {
    throw new Error(
      ".related-dots must be display:none from lg up, so no dot row is left"
      + " under a grid that has nothing to page"
    );
  }
  // With no arrows the dots are the only visible control, so the gate that
  // keeps them off a strip that does not scroll has exactly one site.
  const railOverflowUses = (filmSource.match(/v-if="railOverflow/g) || []).length;
  if (railOverflowUses !== 1) {
    throw new Error(
      "railOverflow must gate the dots (1 use), found " + railOverflowUses
      + ". Dots for a strip that does not scroll are worse than no dots"
    );
  }
  // Keyboard paging is now the only non-pointer way to move the strip.
  for (const key of ["@keydown.left.prevent", "@keydown.right.prevent"]) {
    if (!filmSource.includes(key)) {
      throw new Error(
        "the track must keep " + key + ": without arrows it is the only"
        + " keyboard route to the rest of the strip"
      );
    }
  }
  if (!/class="related-track"[^>]*\stabindex="0"/.test(filmSource)) {
    throw new Error("the track must stay focusable (tabindex=0) so the left and"
      + " right keys can reach it");
  }
  for (const fn of ["measureRail", "scrollRail", "scrollRailTo", "onRailScroll"]) {
    if (!filmSource.includes("function " + fn)) {
      throw new Error("film.js must define " + fn + "()");
    }
  }
  if (!filmSource.includes('"resize"')) {
    throw new Error("the rail must re-measure on resize, or the controls keep"
      + " claiming a strip scrolls after the window has stopped scrolling it");
  }
  if (!filmSource.includes("prefers-reduced-motion: reduce")) {
    throw new Error("the rail must honour prefers-reduced-motion: reduce");
  }
  if (!filmSource.includes('class="bc-type"')) {
    throw new Error("film.js must expose a compact breadcrumb category");
  }
  // Poster on top, text under it, ratings last. The order is the design: the
  // partner's second screenshot puts the artwork above the caption, and the
  // ratings sit at the bottom of the card. film.js receives the card as an
  // opaque FILM_RC_CARD string, so the order is asserted against the generator
  // source (below) and film.js is only checked for holding no second copy.
  if (filmSource.includes('class="rc-poster"')) {
    throw new Error("film.js must not hold its own copy of the related card; it"
      + " renders window.FILM_RC_CARD, whose only source is gen_pages.RC_CARD");
  }
  if (!filmSource.includes("FILM_RC_CARD")) {
    throw new Error("film.js must render the related card from window.FILM_RC_CARD, the one source the page carries");
  }
  if (filmSource.includes('class="fav-icon"')) {
    throw new Error("film.js must not render recommendation hearts in related cards");
  }
  const generatorSource = read("tools/gen_pages.py");
  if (!generatorSource.includes('class="rc-poster"')) {
    throw new Error("the one related-card source must render poster thumbnails");
  }
  // Card order, asserted as a sequence so a later edit that swaps two spans
  // fails here instead of in someone's eye. It lives in gen_pages.RC_CARD
  // because film.js renders the card as an opaque FILM_RC_CARD string.
  const rcOrder = ["rc-poster", "rc-info", "rc-title", "rc-meta"];
  const genRc = generatorSource.slice(
    generatorSource.indexOf("RC_CARD = "),
    generatorSource.indexOf("RC_VOID_TAGS")
  );
  const rcAt = rcOrder.map((cls) => genRc.indexOf('class="' + cls));
  for (let i = 0; i < rcAt.length; i++) {
    if (rcAt[i] === -1) {
      throw new Error(
        "gen_pages.RC_CARD must render ." + rcOrder[i] + " (position " + i
        + " of " + rcOrder.join(" -> ") + ")"
      );
    }
  }
  for (let i = 1; i < rcAt.length; i++) {
    if (rcAt[i] < rcAt[i - 1]) {
      throw new Error(
        "related card order must be " + rcOrder.join(" -> ") + ", but ."
        + rcOrder[i - 1] + " comes after ." + rcOrder[i]
      );
    }
  }
  if (!genRc.includes('class="rc-rating kp rating-chip rating-chip--kp"')) {
    throw new Error("related rating chips must carry rating-chip so the pill"
      + " styling is shared with the rest of the site, not re-declared per card");
  }
  // The card and its poster are the two repeated shapes in a six-up row, and the
  // partner asked for 6px on both. The radius gate in verify.py only fails a
  // BARE value, so tokenising to --radius-m would pass it while shipping the
  // wrong radius; only an assertion on the token itself catches that.
  const styleSource = read("css/style.css");
  for (const sel of [".related a.rc", ".rc-poster"]) {
    const block = styleSource.match(
      new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{([^}]*)\\}")
    );
    if (!block) {
      throw new Error("css/style.css has no rule for " + sel);
    }
    if (!/border-radius:\s*var\(--radius-s\)/.test(block[1])) {
      throw new Error(
        sel + " must use var(--radius-s) (6px). A bare value is caught by"
        + " verify.py, but a different token is not: --radius-m is 7px and"
        + " --radius-l is 8px, and the partner asked for 6"
      );
    }
  }
  if (!generatorSource.includes('<h1 class="film-title">')) {
    throw new Error("generated film pages must carry the title as the card's h1"
      + " (their header carries the site name, not the film)");
  }
  if (generatorSource.includes('film-header-title')) {
    throw new Error("generated film pages must not repeat the film title in the header");
  }
  if (!/class="film-poster">\\n[\s\S]{0,300}?\{fav_badge\}/.test(generatorSource)) {
    throw new Error("the generated no-JS author-pick badge belongs inside the poster figure");
  }
  if ((generatorSource.match(/\{fav_badge\}/g) || []).length !== 1) {
    throw new Error("fav_badge must be interpolated exactly once, into the poster figure;"
      + " anywhere else it would put the badge back in the info column");
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
  if (generatorSource.includes('relatedPool')) {
    throw new Error("gen_pages.py must not build a relatedPool: the client renders"
      + " FILM_PAGE.related verbatim, and a pool costs 622979 B across 154 pages");
  }
  const capture = bootApp();
  eval(
    jsSrc("i18n.js") + "\n" +
    jsSrc("common.js") + "\n" +
    read("js/data.js") + "\n" +
    jsSrc("film.js")
  );
  const relA = global.CATALOG.slice(1, 5);
  const relB = global.CATALOG.slice(6, 10);
  global.FILM_PAGE = {
    item: global.CATALOG[0],
    related: relA,
    posterW: null,
    posterH: null,
  };
  const setup = capture();
  const state = setup();
  if (!state || !Array.isArray(state.related)) {
    throw new Error("film.js setup() returned invalid state");
  }
  if (state.desc.value === "") {
    throw new Error("film.js desc is empty");
  }
  const slugs = state.related.map((r) => global.ITMoviesCommon.itemSlug(r));
  const want = relA.map((r) => global.ITMoviesCommon.itemSlug(r));
  if (slugs.join(",") !== want.join(",")) {
    throw new Error("film.js must render FILM_PAGE.related verbatim, got " + slugs.join(","));
  }
  for (let i = 0; i < 5; i++) {
    const again = setup();
    const againSlugs = again.related.map((r) => global.ITMoviesCommon.itemSlug(r));
    if (againSlugs.join(",") !== want.join(",")) {
      throw new Error("film.js related must be stable across setup() calls");
    }
  }
  global.FILM_PAGE = { item: global.CATALOG[0], related: relB, posterW: null, posterH: null };
  const otherSlugs = setup().related.map((r) => global.ITMoviesCommon.itemSlug(r));
  const otherWant = relB.map((r) => global.ITMoviesCommon.itemSlug(r));
  if (otherSlugs.join(",") !== otherWant.join(",")) {
    throw new Error("film.js must follow FILM_PAGE.related, not a fixed list");
  }
  global.FILM_PAGE = {
    item: global.CATALOG[0],
    related: relA,
    relatedPool: global.CATALOG.slice(1, 10),
    posterW: null,
    posterH: null,
  };
  const pooledSlugs = setup().related.map((r) => global.ITMoviesCommon.itemSlug(r));
  if (pooledSlugs.join(",") !== want.join(",")) {
    throw new Error("film.js must ignore FILM_PAGE.relatedPool, got " + pooledSlugs.join(","));
  }
  global.FILM_PAGE = {
    item: global.CATALOG[0],
    related: [],
    relatedPool: global.CATALOG.slice(1, 10),
    posterW: null,
    posterH: null,
  };
  const emptySlugs = setup().related.map((r) => global.ITMoviesCommon.itemSlug(r));
  if (emptySlugs.length !== 0) {
    throw new Error("film.js must tolerate an empty related array even when a pool is"
      + " present, got " + emptySlugs.join(","));
  }
  global.FILM_PAGE = { item: global.CATALOG[0], posterW: null, posterH: null };
  if (!Array.isArray(setup().related)) {
    throw new Error("film.js must default related to an array when FILM_PAGE omits it");
  }
  console.log("film.js smoke (FILM_PAGE, no data.js load on film page): OK" + MIN_LABEL);
} else {
  console.error("usage: node tools/smoke.js <app|slug|film>");
  process.exit(2);
}