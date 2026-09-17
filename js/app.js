const { createApp, computed, reactive, ref, watch, onMounted, onUnmounted } = Vue;

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
    let onKeydown = null;

    watch(selectedPoster, (open) => {
      if (open) {
        onKeydown = (e) => {
          if (e.key === "Escape") closePoster();
        };
        window.addEventListener("keydown", onKeydown);
      } else if (onKeydown) {
        window.removeEventListener("keydown", onKeydown);
        onKeydown = null;
      }
    });

    onUnmounted(() => {
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

    const favIcon = computed(() => "static/favorite_32.png");

    return {
      selectedPoster,
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
    const lang = ref(
      (paramLang === "ru" || paramLang === "en" ? paramLang : null) ||
        localStorage.getItem("it-movies-lang") ||
        defaultLang
    );
    const paramTheme = urlParams.get("theme");
    const savedTheme = localStorage.getItem("it-movies-theme");
    const colorScheme = window.matchMedia("(prefers-color-scheme: light)");
    const theme = ref(
      paramTheme === "dark" || paramTheme === "light"
        ? paramTheme
        : savedTheme || (colorScheme.matches ? "light" : "dark")
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
        localStorage.setItem("it-movies-lang", value);
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
        localStorage.setItem("it-movies-sorts", JSON.stringify(value));
      },
      { deep: true }
    );

    watch(
      onlyFav,
      (value) => {
        localStorage.setItem("it-movies-only-fav", value ? "1" : "0");
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
        if (!localStorage.getItem("it-movies-theme")) {
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
      localStorage.setItem("it-movies-theme", next);
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

app.mount("#app");
