const bootOk = window.Vue && typeof I18N !== "undefined" && window.ITMoviesCommon && Array.isArray(window.CATALOG);
if (!bootOk) {
  console.error("[IT Movies] bootstrap failed", {
    vue: !!window.Vue,
    i18n: typeof I18N !== "undefined",
    common: !!window.ITMoviesCommon,
    catalog: Array.isArray(window.CATALOG),
  });
  const fb = document.getElementById("boot-fallback");
  if (fb) fb.hidden = false;
}

const { createApp, computed, reactive, ref, watch, onMounted, onUnmounted, nextTick } = Vue;

const {
  safeRead,
  safeWrite,
  filmUrl,
  kpUrl,
  imdbUrl,
  hasRating,
  isHighRating,
  formatRating,
  displayTitle: displayTitleC,
  altTitle: altTitleC,
  genreLabel: genreLabelC,
  langFrom,
  themeFrom,
  toggleThemeClass,
  scrollToTop,
  installErrorHandler,
} = window.ITMoviesCommon;

// The poster variant ladder, mirrored from tools/lib.py POSTER_VARIANT_WIDTHS.
// verify.py parses this line and fails if the two ever disagree, so the copy in
// JS cannot drift from the one gen_posters.py writes and gen_pages.py emits.
const POSTER_VARIANT_WIDTHS = [96, 192, 400];

let currentLang = "ru";

function compare(a, b, key, dir, lang) {
  const mul = dir === "desc" ? -1 : 1;
  if (key === "title") {
    const av = lang === "ru" ? a.titleRu : a.titleEn;
    const bv = lang === "ru" ? b.titleRu : b.titleEn;
    return av.localeCompare(bv, lang === "ru" ? "ru" : "en") * mul;
  }
  if (key === "genre") {
    const g = (item) =>
      item.genres.map((g) => I18N[lang].genres[g] || g).join(" ");
    return g(a).localeCompare(g(b), lang === "ru" ? "ru" : "en") * mul;
  }
  if (key === "year") return ((a.year || 0) - (b.year || 0)) * mul;
  if (key === "kp" || key === "imdb") {
    const av = hasRating(a[key + "Rating"]) ? a[key + "Rating"] : null;
    const bv = hasRating(b[key + "Rating"]) ? b[key + "Rating"] : null;
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return (av - bv) * mul;
  }
  return 0;
}

function shuffle(items, random) {
  const copy = items.slice();
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    const tmp = copy[i];
    copy[i] = copy[j];
    copy[j] = tmp;
  }
  return copy;
}

function pickFeatured(catalog, random = Math.random) {
  const favorites = catalog.filter((item) => item.fav);
  const selected = ["movie", "documentary", "series"].flatMap((type) =>
    shuffle(favorites.filter((item) => item.type === type), random).slice(0, 2)
  );
  const shuffled = shuffle(selected, random);
  if (shuffled.length < 6) {
    const picked = new Set(shuffled);
    for (const item of favorites) {
      if (shuffled.length >= 6) break;
      if (!picked.has(item)) {
        picked.add(item);
        shuffled.push(item);
      }
    }
  }
  return shuffled.slice(0, 6);
}

const CatalogTable = {
  props: {
    id: String,
    typeKey: String,
    title: String,
    items: Array,
    t: Object,
    lang: String,
    sort: Object,
    withPosters: { type: Boolean, default: true }
  },
  emits: ["sort"],
  setup(props, { emit }) {
    const selectedPoster = ref(null);
    const closeBtn = ref(null);
    const modalEl = ref(null);

    watch(selectedPoster, async (open) => {
      if (open) {
        await nextTick();
        modalEl.value?.showModal();
        document.body.style.overflow = "hidden";
        closeBtn.value?.focus();
      } else {
        modalEl.value?.close();
        document.body.style.overflow = "";
      }
    });

    function onDialogClose() {
      selectedPoster.value = null;
    }

    onUnmounted(() => {
      document.body.style.overflow = "";
    });

    function displayTitle(item) {
      return displayTitleC(item, props.lang);
    }

    function altTitle(item) {
      return altTitleC(item, props.lang);
    }

    function genreLabel(item) {
      return genreLabelC(item, props.t);
    }

    function thClass(key) {
      return {
        sortable: true,
        "is-asc": props.sort.key === key && props.sort.dir === "asc",
        "is-desc": props.sort.key === key && props.sort.dir === "desc",
      };
    }

    function ariaSort(key) {
      if (props.sort.key !== key) return "none";
      return props.sort.dir === "asc" ? "ascending" : "descending";
    }

    function arrow(key) {
      if (props.sort.key !== key) return "↕";
      return props.sort.dir === "asc" ? "↑" : "↓";
    }

    function openPoster(item) {
      selectedPoster.value = item;
    }

    function closePoster() {
      selectedPoster.value = null;
    }

    return {
      selectedPoster,
      closeBtn,
      modalEl,
      onDialogClose,
      formatRating: (value, t_) => formatRating(value, t_.noData),
      hasRating,
      isHighRating,
      imdbUrl,
      kpUrl,
      filmUrl,
      displayTitle,
      altTitle,
      genreLabel,
      thClass,
      ariaSort,
      arrow,
      openPoster,
      closePoster,
    };
  },
  template: "#tpl-catalog",
};

const app = createApp({
  components: { CatalogTable },
  setup() {
    const urlParams = new URLSearchParams(location.search);
    const lang = ref(langFrom(urlParams, safeRead));
    const colorScheme = window.matchMedia("(prefers-color-scheme: light)");
    const theme = ref(themeFrom(urlParams, safeRead));
    const query = ref(urlParams.get("q") || "");
    const onlyFav = ref(
      urlParams.get("fav") === "1" || safeRead("it-movies-only-fav") === "1"
    );
    const genre = ref(
      I18N.en.genres[urlParams.get("genre")] ? urlParams.get("genre") : ""
    );
    let cleanupColorScheme = null;
    let urlSyncTimer = null;

    const SORT_DEFAULTS = {
      series: { key: "title", dir: "asc" },
      movie: { key: "title", dir: "asc" },
      documentary: { key: "title", dir: "asc" },
    };
    const SORT_KEYS = ["title", "genre", "year", "kp", "imdb"];

    function normalizeSort(raw) {
      const out = {};
      for (const key of Object.keys(SORT_DEFAULTS)) {
        const d = SORT_DEFAULTS[key];
        const r = raw && raw[key];
        out[key] =
          r && SORT_KEYS.includes(r.key) && (r.dir === "asc" || r.dir === "desc")
            ? { key: r.key, dir: r.dir }
            : { key: d.key, dir: d.dir };
      }
      return out;
    }

    function loadSorts() {
      // URL params take precedence (?sort[movie]=year:desc)
      const params = new URLSearchParams(location.search);
      const urlSorts = {};
      for (const type of Object.keys(SORT_DEFAULTS)) {
        const raw = params.get(`sort[${type}]`);
        if (raw) {
          const parts = raw.split(":");
          const key = parts[0];
          const dir = parts[1];
          if (key && SORT_KEYS.includes(key) && (dir === "asc" || dir === "desc")) {
            urlSorts[type] = { key, dir };
          }
        }
      }
      if (Object.keys(urlSorts).length > 0) {
        return normalizeSort(urlSorts);
      }
      try {
        return normalizeSort(JSON.parse(safeRead("it-movies-sorts") ?? "null"));
      } catch {
        return normalizeSort(null);
      }
    }

    const sorts = reactive(loadSorts());

    watch(
      lang,
      (value) => {
        currentLang = value;
        safeWrite("it-movies-lang", value);
        document.documentElement.lang = value;
        document.title = I18N[value].titleFull;
        const metaDesc = document.querySelector('meta[name="description"]');
        if (metaDesc) metaDesc.setAttribute("content", I18N[value].descSeo);
      },
      { immediate: true }
    );

    watch(
      theme,
      (value) => toggleThemeClass(value),
      { immediate: true }
    );

    watch(
      sorts,
      (value) => {
        safeWrite("it-movies-sorts", JSON.stringify(value));
        syncUrl();
      },
      { deep: true }
    );

    watch(
      onlyFav,
      (value) => {
        safeWrite("it-movies-only-fav", value ? "1" : "0");
      }
    );

    function syncUrl() {
      const p = new URLSearchParams();
      if (query.value) p.set("q", query.value);
      if (genre.value) p.set("genre", genre.value);
      if (onlyFav.value) p.set("fav", "1");
      for (const [type, s] of Object.entries(sorts)) {
        if (s.key !== "title" || s.dir !== "asc") {
          p.set(`sort[${type}]`, `${s.key}:${s.dir}`);
        } else {
          p.delete(`sort[${type}]`);
        }
      }
      const qs = p.toString();
      const url = location.pathname + (qs ? "?" + qs : "") + location.hash;
      clearTimeout(urlSyncTimer);
      urlSyncTimer = setTimeout(() => {
        try {
          history.replaceState(null, "", url);
        } catch {}
      }, 200);
    }

    watch([query, genre, onlyFav], syncUrl);

    onMounted(() => {
      const onColorScheme = (e) => {
        if (!safeRead("it-movies-theme")) {
          theme.value = e.matches ? "light" : "dark";
        }
      };
      colorScheme.addEventListener("change", onColorScheme);
      cleanupColorScheme = () =>
        colorScheme.removeEventListener("change", onColorScheme);
      const el = navDialog();
      if (el) {
        el.addEventListener("close", onDialogClose);
        cleanupMenu = () => el.removeEventListener("close", onDialogClose);
      }
    });

    onUnmounted(() => {
      if (cleanupColorScheme) cleanupColorScheme();
      if (cleanupMenu) cleanupMenu();
      clearTimeout(urlSyncTimer);
    });

    const t = computed(() => I18N[lang.value]);
    const genreOptions = computed(() =>
      Object.entries(t.value.genres).sort(([, a], [, b]) =>
        a.localeCompare(b, lang.value === "ru" ? "ru" : "en")
      )
    );

    const filtered = computed(() => {
      const q = query.value.trim().toLowerCase();
      const favOnly = onlyFav.value;
      const selectedGenre = genre.value;
      return window.CATALOG.filter((item) => {
        if (favOnly && !item.fav) return false;
        if (selectedGenre && !item.genres.includes(selectedGenre)) return false;
        if (!q) return true;
        const genres = item.genres
          .map((g) => `${I18N.ru.genres[g] || g} ${I18N.en.genres[g] || g}`)
          .join(" ");
        const hay = [item.titleEn, item.titleRu, String(item.year), genres, item.imdbId]
          .join(" ")
          .toLowerCase();
        return hay.includes(q);
      });
    });

    function sectionItems(type) {
      const rows = filtered.value.filter((item) => item.type === type);
      const { key, dir } = sorts[type];
      return [...rows].sort((a, b) => compare(a, b, key, dir, lang.value));
    }

    const series = computed(() => sectionItems("series"));
    const movies = computed(() => sectionItems("movie"));
    const documentaries = computed(() => sectionItems("documentary"));
    const counts = computed(() => ({
      series: series.value.length,
      movies: movies.value.length,
      documentaries: documentaries.value.length,
      all: series.value.length + movies.value.length + documentaries.value.length,
    }));

    const featured = computed(() => pickFeatured(window.CATALOG));
    const hasActiveFilters = computed(
      () => query.value.trim() !== "" || genre.value !== "" || onlyFav.value
    );

    function resetFilters() {
      query.value = "";
      genre.value = "";
      onlyFav.value = false;
      for (const type of Object.keys(SORT_DEFAULTS)) {
        sorts[type] = { ...SORT_DEFAULTS[type] };
      }
    }

    function genreLabel(item) {
      return item.genres.map((genre) => I18N[lang.value].genres[genre] || genre).join(" · ");
    }

    function firstGenre(item) {
      const genre = item.genres && item.genres[0];
      return genre ? (I18N[lang.value].genres[genre] || genre) : "";
    }

    function altTitle(item) {
      return altTitleC(item, lang.value);
    }

    // The featured card's poster box is 156px below lg and at most 194px from
    // lg up, so the 400w rung it used to fetch unconditionally is 2-2.5x the
    // slot at DPR 1. The ladder is the same one js/film.js offers the related
    // card, and verify.py checks that this tuple mirrors lib.POSTER_VARIANT_
    // WIDTHS -- a Vue template attribute cannot read a Python value, so this is
    // a deliberate second copy tied to that one by a gate.
    function featuredSrcset(item) {
      const src = item.poster;
      if (!src) return null;
      const path = src.replace(/^\//, "");
      return POSTER_VARIANT_WIDTHS.map(
        (w) => `${path.replace(/\.webp$/, "_" + w + ".webp")} ${w}w`
      ).join(", ");
    }

    function setLang(next) {
      lang.value = next;
    }

    function setTheme(next) {
      theme.value = next;
      safeWrite("it-movies-theme", next);
    }

    function sortBy(type, key) {
      const current = sorts[type];
      if (current.key === key) {
        current.dir = current.dir === "asc" ? "desc" : "asc";
      } else {
        current.key = key;
        current.dir = key === "title" || key === "genre" ? "asc" : "desc";
      }
      // Persist to localStorage after every change
      safeWrite("it-movies-sorts", JSON.stringify(sorts));
    }

    function goLucky() {
      if (!window.CATALOG || window.CATALOG.length === 0) return;
      const pick = window.CATALOG[Math.floor(Math.random() * window.CATALOG.length)];
      location.href = filmUrl(pick);
    }

    const menuOpen = ref(false);

    function navDialog() {
      return document.getElementById("nav-dialog");
    }

    function openMenu() {
      const el = navDialog();
      if (!el) return;
      if (typeof el.showModal === "function") el.showModal();
      menuOpen.value = true;
    }

    function closeMenu() {
      const el = navDialog();
      if (el && el.open && typeof el.close === "function") el.close();
      menuOpen.value = false;
    }

    function onDialogClose() {
      menuOpen.value = false;
    }

    // There is no `goSection`, no `currentSection` and no section observer.
    // Partner ruling, 2026-09-30: the nav no longer marks the current section,
    // so `aria-current` is gone from the markup and nothing in this file writes
    // it. The mechanism it used to need is recorded here because it was three
    // real bugs deep and a re-implementer would walk into the same three:
    //
    //   1. an IntersectionObserver on a band at 20-30% of the viewport height
    //      overwrote the click's marker mid-flight -- measured at 320 the marker
    //      read #series for 197ms and flipped to #movies at 214ms, on a scroll
    //      running 0 -> 5436 over ~700ms, during which #movies genuinely was the
    //      section in the band. The observer was not wrong, it was early.
    //   2. `sectionLock` held the click's marker until the scroll arrived, which
    //      fixed (1) and introduced (3).
    //   3. the observer latched: `first ? first.id : currentSection.value` kept
    //      the last answer when the band was empty, so after scrolling back to
    //      the top -- above all three sections, band empty -- the marker stayed
    //      on #movies. Reproduced at 1280 by all three ways of returning to the
    //      top (scrollTo, Home, wheel).
    //
    // A "current section" indicator needs to answer "which section am I in", and
    // a band-and-observer scheme cannot answer it above the first section or
    // during a smooth scroll without a lock that is itself a source of bugs. The
    // partner's call is that the indicator is not worth any of that.
    //
    // The anchors are unchanged: `href="#series"` still scrolls, and
    // `scroll-behavior: smooth` still animates it. What changed is that a target
    // now lands at the top of the viewport, because the header is no longer
    // sticky and there is no `scroll-padding-top` to push it down.

    let cleanupMenu = null;

    return {
      lang,
      theme,
      query,
      genre,
      onlyFav,
      sorts,
      t,
      genreOptions,
      series,
      movies,
      documentaries,
      counts,
      featured,
      pickFeatured,
      hasActiveFilters,
      resetFilters,
      setLang,
      setTheme,
      sortBy,
      filmUrl,
      genreLabel,
      firstGenre,
      altTitle,
      featuredSrcset,
      goLucky,
      scrollToTop,
      hasRating,
      menuOpen,
      openMenu,
      closeMenu,
      onDialogClose,
      formatRating: (value) => formatRating(value, t.value.noData),
    };
  },
});

if (bootOk) {
  installErrorHandler(app, () => currentLang, () => I18N);
  app.mount("#app");
}