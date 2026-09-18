const { createApp, computed, reactive, ref, watch, onMounted, onUnmounted, nextTick } = Vue;

const SUPPORTED = { lang: ["ru", "en"], theme: ["dark", "light"] };

function safeRead(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function safeWrite(key, value) {
  try { localStorage.setItem(key, value); } catch {}
}

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
    const av = a[key + "Rating"] == null ? -1 : a[key + "Rating"];
    const bv = b[key + "Rating"] == null ? -1 : b[key + "Rating"];
    return (av - bv) * mul;
  }
  return 0;
}

function hasRating(value) {
  return value != null && value !== "";
}

function formatRating(value, t) {
  if (!hasRating(value)) return t.noData;
  return Number(value).toFixed(1);
}

function isHighRating(value) {
  return hasRating(value) && Number(value) >= 7;
}

function imdbUrl(item) {
  return `https://www.imdb.com/title/${item.imdbId}/`;
}

function kpUrl(item) {
  return `https://www.kinopoisk.ru/film/${item.kpId}/`;
}

function buildLdJson(catalog) {
  const base = location.origin + location.pathname;
  const itemListElement = catalog.map((item, i) => {
    const out = {
      "@type": item.type === "series" ? "TVSeries" : "Movie",
      position: i + 1,
      name: item.titleRu,
      alternateName: item.titleEn,
      url: item.imdbId ? imdbUrl(item) : item.kpId ? kpUrl(item) : "",
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
  script.textContent = JSON.stringify(data);
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
      return props.lang === "ru" ? item.titleRu : item.titleEn;
    }

    function altTitle(item) {
      const primary = displayTitle(item);
      const other = props.lang === "ru" ? item.titleEn : item.titleRu;
      return other && other !== primary ? other : "";
    }

    function genreLabel(item) {
      return item.genres.map((g) => props.t.genres[g] || g).join(" / ");
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
      formatRating,
      hasRating,
      isHighRating,
      imdbUrl,
      kpUrl,
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
    const defaultLang = navigator.language.startsWith("ru") ? "ru" : "en";
    const urlParams = new URLSearchParams(location.search);
    const paramLang = urlParams.get("lang");
    const savedLang = safeRead("it-movies-lang");
    const lang = ref(
      SUPPORTED.lang.includes(paramLang)
        ? paramLang
        : SUPPORTED.lang.includes(savedLang)
          ? savedLang
          : defaultLang
    );
    const paramTheme = urlParams.get("theme");
    const savedTheme = safeRead("it-movies-theme");
    const colorScheme = window.matchMedia("(prefers-color-scheme: light)");
    const theme = ref(
      SUPPORTED.theme.includes(paramTheme)
        ? paramTheme
        : SUPPORTED.theme.includes(savedTheme)
          ? savedTheme
          : colorScheme.matches
            ? "light"
            : "dark"
    );
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    const query = ref(urlParams.get("q") || "");
    const onlyFav = ref(
      urlParams.get("fav") === "1" ||
        localStorage.getItem("it-movies-only-fav") === "1"
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
        safeWrite("it-movies-lang", value);
        document.documentElement.lang = value;
        document.title = I18N[value].titleFull;
      },
      { immediate: true }
    );

    watch(
      theme,
      (value) => {
        document.documentElement.classList.toggle("dark", value === "dark");
        if (metaThemeColor) {
          metaThemeColor.setAttribute(
            "content",
            value === "dark" ? "#1a1a1f" : "#f4f3ef"
          );
        }
      },
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

    function handleScroll() {
      showScrollTop.value = window.scrollY > 300;
    }

    function measureLoadTime() {
      const nav = performance.getEntriesByType("navigation")[0];
      const ms = nav ? nav.loadEventEnd || nav.loadEventStart || performance.now() : performance.now();
      loadTime.value = Math.round(ms);
    }

    onMounted(() => {
      window.addEventListener("scroll", handleScroll);
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
      window.removeEventListener("scroll", handleScroll);
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

    function scrollToTop() {
      window.scrollTo({ top: 0, behavior: "smooth" });
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

if (app.config) {
  app.config.errorHandler = (err, instance, info) => {
    console.error("[Vue error]", err, info);
    const root = document.querySelector("#app");
    if (root) {
      root.innerHTML =
        "<p style=\"padding:2rem;text-align:center\">Что-то пошло не так — перезагрузите страницу.</p>";
    }
  };
}

app.mount("#app");
