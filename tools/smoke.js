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
  const total = state.movies.value.length + state.series.value.length + state.documentaries.value.length;
  if (total !== global.CATALOG.length) {
    throw new Error("sections total " + total + " != CATALOG.length " + global.CATALOG.length);
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
  const N = 4;
  const api = global.ITMoviesCommon;
  const out = cat.map((it) => global.__relatedItems(cat, it, N).map((r) => api.itemSlug(r)));
  console.log(JSON.stringify(out));
} else {
  console.error("usage: node tools/smoke.js <app|slug|film|related>");
  process.exit(2);
}