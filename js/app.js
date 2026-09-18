const { createApp, computed, reactive, ref, watch, onMounted, onUnmounted, nextTick } = Vue;

const {
  safeRead,
  safeWrite,
  itemSlug,
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
  updateScrollState,
  scrollToTop,
  installErrorHandler,
} = window.ITMoviesCommon;

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

function buildLdJson(catalog) {
  const base = location.origin + location.pathname.replace(/\/$/, "") + "/";
  const itemListElement = catalog.map((item, i) => {
    const out = {
      "@type": item.type === "series" ? "TVSeries" : "Movie",
      position: i + 1,
      name: item.titleRu,
      alternateName: item.titleEn,
      url: base + filmUrl(item),
    };
    if (item.year) out.datePublished = String(item.year);
    return out;
  });
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": base,
        url: base,
        name: "IT Movies",
        inLanguage: ["ru", "en"],
        potentialAction: {
          "@type": "SearchAction",
          target: {
            "@type": "EntryPoint",
            urlTemplate: base + "?q={search_term_string}",
          },
          "query-input": "required name=search_term_string",
        },
      },
      {
        "@type": "ItemList",
        name: "Фильмы и сериалы о компьютерах, технологиях и искусственном интеллекте",
        numberOfItems: catalog.length,
        itemListElement,
      },
    ],
  };
}

function injectLdJson(data) {
  const script = document.createElement("script");
  script.type = "application/ld+json";
  script.textContent = JSON.stringify(data).replace(/</g, "\\u003c");
  document.head.appendChild(script);
}

injectLdJson(buildLdJson(window.CATALOG));

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
    let onKeydown = null;
    let lastFocus = null;

    watch(selectedPoster, async (open) => {
      if (open) {
        lastFocus = document.activeElement;
        document.body.style.overflow = "hidden";
        onKeydown = (e) => {
          if (e.key === "Escape") closePoster();
          else if (e.key === "Tab") {
            const modal = document.querySelector(".poster-modal");
            if (!modal) return;
            const focusables = modal.querySelectorAll(
              'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
            );
            if (!focusables.length) return;
            const first = focusables[0];
            const last = focusables[focusables.length - 1];
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }
        };
        window.addEventListener("keydown", onKeydown);
        await nextTick();
        closeBtn.value?.focus();
      } else {
        document.body.style.overflow = "";
        lastFocus?.focus();
        lastFocus = null;
        if (onKeydown) {
          window.removeEventListener("keydown", onKeydown);
          onKeydown = null;
        }
      }
    });

    onUnmounted(() => {
      document.body.style.overflow = "";
      if (onKeydown) {
        window.removeEventListener("keydown", onKeydown);
        onKeydown = null;
      }
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

    const favIcon = "static/favorite_32.png";

    return {
      selectedPoster,
      closeBtn,
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
      favIcon,
    };
  },
  template: "#tpl-catalog",
};

const app = createApp({
  components: { CatalogTable },
  setup() {
    const urlParams = new URLSearchParams(location.search);
    const lang = ref(langFrom(urlParams, safeRead));
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    const colorScheme = window.matchMedia("(prefers-color-scheme: light)");
    const theme = ref(themeFrom(urlParams, safeRead));
    const query = ref(urlParams.get("q") || "");
    const onlyFav = ref(
      urlParams.get("fav") === "1" || safeRead("it-movies-only-fav") === "1"
    );
    const showScrollTop = ref(false);
    const loadTime = ref(null);
    let cleanupColorScheme = null;

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
      try {
        return normalizeSort(JSON.parse(localStorage.getItem("it-movies-sorts")));
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
      },
      { immediate: true }
    );

    watch(
      theme,
      (value) => toggleThemeClass(value, metaThemeColor),
      { immediate: true }
    );

    watch(
      sorts,
      (value) => {
        safeWrite("it-movies-sorts", JSON.stringify(value));
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
      if (onlyFav.value) p.set("fav", "1");
      p.set("lang", lang.value);
      p.set("theme", theme.value);
      const qs = p.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    }

    watch([query, onlyFav, lang, theme], syncUrl);

    function measureLoadTime() {
      const nav = performance.getEntriesByType("navigation")[0];
      const ms = nav ? nav.loadEventEnd || nav.loadEventStart || performance.now() : performance.now();
      loadTime.value = Math.round(ms);
    }

    const onScroll = () => updateScrollState(showScrollTop);

    onMounted(() => {
      window.addEventListener("scroll", onScroll);
      const onColorScheme = (e) => {
        if (!safeRead("it-movies-theme")) {
          theme.value = e.matches ? "light" : "dark";
        }
      };
      colorScheme.addEventListener("change", onColorScheme);
      cleanupColorScheme = () =>
        colorScheme.removeEventListener("change", onColorScheme);
      if (document.readyState === "complete") {
        measureLoadTime();
      } else {
        window.addEventListener("load", measureLoadTime, { once: true });
      }
    });

    onUnmounted(() => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("load", measureLoadTime);
      if (cleanupColorScheme) cleanupColorScheme();
    });

    const t = computed(() => I18N[lang.value]);

    const filtered = computed(() => {
      const q = query.value.trim().toLowerCase();
      const favOnly = onlyFav.value;
      return window.CATALOG.filter((item) => {
        if (favOnly && !item.fav) return false;
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
    }

    return {
      lang,
      theme,
      query,
      onlyFav,
      showScrollTop,
      loadTime,
      sorts,
      t,
      series,
      movies,
      documentaries,
      counts,
      setLang,
      setTheme,
      sortBy,
      scrollToTop,
    };
  },
});

installErrorHandler(app, () => currentLang, () => I18N);

app.mount("#app");