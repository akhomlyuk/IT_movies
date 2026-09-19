const { createApp, computed, ref, watch, onMounted, onUnmounted } = Vue;

const {
  safeRead,
  safeWrite,
  itemSlug,
  kpUrl,
  imdbUrl,
  formatRating,
  langFrom,
  themeFrom,
  toggleThemeClass,
  updateScrollState,
  scrollToTop,
  installErrorHandler,
} = window.ITMoviesCommon;

let currentLang = "ru";

function itemBySlug(catalog, name) {
  return catalog.find((item) => itemSlug(item) === name) || null;
}

function relatedItems(catalog, item, limit) {
  const gs = new Set(item.genres);
  const scored = catalog
    .filter((o) => o !== item)
    .map((o) => ({ item: o, overlap: o.genres.filter((g) => gs.has(g)).length }))
    .sort((a, b) => b.overlap - a.overlap);
  const top = scored.filter((s) => s.overlap > 0).map((s) => s.item);
  const rest = scored.filter((s) => s.overlap === 0).map((s) => s.item);
  return [...top, ...rest].slice(0, Math.max(limit, 1));
}

const FILM_TEMPLATE = `
  <header class="top">
    <div class="brand">
      <div class="logo">
        <a href="../../"><img src="../../static/logo.webp" alt="IT Movies" fetchpriority="high" width="100" height="100"></a>
      </div>
      <div class="brand-text">
        <h1>{{ title }}</h1>
        <p v-if="altTitle">{{ altTitle }}</p>
      </div>
    </div>
    <div class="toolbar">
      <div class="lang" role="group" :aria-label="lang === 'ru' ? 'Язык / Language' : 'Language / Язык'">
        <button type="button" :class="{ active: lang === 'ru' }" :aria-pressed="lang === 'ru'" @click="setLang('ru')">RU</button>
        <button type="button" :class="{ active: lang === 'en' }" :aria-pressed="lang === 'en'" @click="setLang('en')">EN</button>
      </div>
      <div class="theme-toggle" role="group" :aria-label="t.theme">
        <button type="button" :class="{ active: theme === 'dark' }" :aria-pressed="theme === 'dark'" :aria-label="t.themeDark" @click="setTheme('dark')">🌙</button>
        <button type="button" :class="{ active: theme === 'light' }" :aria-pressed="theme === 'light'" :aria-label="t.themeLight" @click="setTheme('light')">☀️</button>
      </div>
    </div>
  </header>

  <main>
    <article class="film-main">
      <figure class="film-poster" v-if="posterSrc">
        <img :src="posterSrc" :alt="title" :width="posterW" :height="posterH" loading="eager" fetchpriority="high" decoding="async">
      </figure>
      <div class="film-info">
        <p class="meta-row">{{ typeLabel }} · {{ year }} · {{ genreLabel }}</p>
        <p class="film-desc">{{ desc }}</p>
        <div class="ratings">
          <a class="kp" :href="kpHref" target="_blank" rel="noopener">{{ t.kp }}: {{ kpRating }}</a>
          <a class="imdb" v-if="hasImdb" :href="imdbHref" target="_blank" rel="noopener">{{ t.imdb }}: {{ imdbRating }}</a>
        </div>
        <p class="btn-back"><a href="../../">← {{ t.backToCatalog }}</a></p>
      </div>
    </article>

    <section class="related" :aria-label="t.relatedH">
      <h2>{{ t.relatedH }}</h2>
      <ul v-if="related.length">
        <li v-for="r in related" :key="itemSlug(r)"><a :href="'../' + itemSlug(r) + '/'">{{ relatedTitle(r) }}</a></li>
      </ul>
      <p class="empty" v-else>{{ t.empty }}</p>
    </section>
  </main>

  <footer>
    <span>{{ t.codedWith }}</span><span class="heart"> ♥ </span><a href="https://t.me/wh_lab" target="_blank" rel="noopener">Exited3n</a>
  </footer>
  <button class="scroll-top" :aria-label="t.scrollTop" @click="scrollToTop" v-show="showScrollTop">↑</button>
`;

const app = createApp({
  setup() {
    const parts = location.pathname.split("/").filter(Boolean);
    const pageData = window.FILM_PAGE || null;
    const item = pageData
      ? pageData.item || null
      : window.CATALOG
        ? itemBySlug(window.CATALOG, parts[parts.length - 1] || "")
        : null;

    const urlParams = new URLSearchParams(location.search);
    const lang = ref(langFrom(urlParams, safeRead));

    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    const colorScheme = window.matchMedia("(prefers-color-scheme: light)");
    const theme = ref(themeFrom(urlParams, safeRead));
    const showScrollTop = ref(false);
    let cleanupColorScheme = null;

    watch(
      theme,
      (value) => toggleThemeClass(value, metaThemeColor),
      { immediate: true }
    );

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
    });

    onUnmounted(() => {
      window.removeEventListener("scroll", onScroll);
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

    const title = computed(() =>
      item ? (lang.value === "ru" ? item.titleRu : item.titleEn) : ""
    );
    const altTitle = computed(() => {
      if (!item) return "";
      const primary = lang.value === "ru" ? item.titleRu : item.titleEn;
      const other = lang.value === "ru" ? item.titleEn : item.titleRu;
      return other && other !== primary ? other : "";
    });
    const desc = computed(() =>
      item ? item.desc[lang.value === "ru" ? "ru" : "en"] : I18N[lang.value].fatalError
    );
    const typeLabel = computed(() =>
      item ? t.value.typeLabels[item.type] || item.type : ""
    );
    const genreLabel = computed(() =>
      item ? item.genres.map((g) => t.value.genres[g] || g).join(" / ") : ""
    );
    const year = computed(() => (item ? item.year : ""));
    const posterSrc = computed(() =>
      item && item.poster ? "../../" + item.poster.replace(/^\//, "") : ""
    );
    const posterW = computed(() => (pageData && pageData.posterW) || null);
    const posterH = computed(() => (pageData && pageData.posterH) || null);
    const kpHref = computed(() => (item ? kpUrl(item) : ""));
    const imdbHref = computed(() => (item && item.imdbId ? imdbUrl(item) : ""));
    const hasImdb = computed(() => !!(item && item.imdbId));
    const kpRating = computed(() =>
      item ? formatRating(item.kpRating, "—") : "—"
    );
    const imdbRating = computed(() =>
      item ? formatRating(item.imdbRating, "—") : "—"
    );
    const related = pageData
      ? pageData.related || []
      : item && window.CATALOG
        ? relatedItems(window.CATALOG, item, 4)
        : [];

    watch(
      lang,
      (value) => {
        currentLang = value;
        safeWrite("it-movies-lang", value);
        document.documentElement.lang = value;
        document.title = `${title.value} — ${I18N[value].title}`;
      },
      { immediate: true }
    );

    function relatedTitle(r) {
      return lang.value === "ru" ? r.titleRu : r.titleEn;
    }

    return {
      lang,
      theme,
      t,
      title,
      altTitle,
      desc,
      typeLabel,
      genreLabel,
      year,
      posterSrc,
      posterW,
      posterH,
      kpHref,
      imdbHref,
      hasImdb,
      kpRating,
      imdbRating,
      related,
      itemSlug,
      relatedTitle,
      showScrollTop,
      setLang,
      setTheme,
      scrollToTop,
    };
  },
  template: FILM_TEMPLATE,
});

installErrorHandler(app, () => currentLang, () => I18N);

app.mount("#app");