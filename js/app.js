const { createApp, computed, reactive, ref, watch, onMounted, onUnmounted } = Vue;

const I18N = {
  ru: {
    title: "IT Movies",
    titleFull: "IT Movies - Список фильмов и сериалов о компьютерах, технологиях и искусственном интеллекте",
    subtitle: "Подборка фильмов и сериалов о компьютерах, технологиях, ИИ и т.д.",
    invite: "Предложить фильм, сериал - <img src=\"static/telegram_32.png\" alt=\"\" width=\"16\" height=\"16\" class=\"tg-icon\"> <a href=\"https://t.me/wh_lab\" target=\"_blank\" rel=\"noopener\">Whitehat Lab</a> или в <a href=\"https://t.me/whitehat_chat\" target=\"_blank\" rel=\"noopener\">чат</a>",
    search: "Поиск по названию, жанру, году",
    movies: "Фильмы",
    series: "Сериалы",
    documentaries: "Документальные",
    name: "Название",
    genre: "Жанр",
    year: "Год",
    kp: "Кинопоиск",
    imdb: "IMDb",
    recommend: "Рекомендую",
    empty: "Ничего не найдено",
    codedWith: "Сделано с",
    total: "Всего фильмов",
    loadLabel: "Загрузка",
    scrollTop: "Наверх",
    close: "Закрыть",
    theme: "Тема",
    themeDark: "Тёмная тема",
    themeLight: "Светлая тема",
    genres: {
      crime: "Криминал",
      ai: "ИИ",
      drama: "Драма",
      thriller: "Триллер",
      romance: "Мелодрама",
      comedy: "Комедия",
      mystery: "Детектив",
      action: "Боевик",
      history: "История",
      biography: "Биография",
      slasher: "Слэшер",
      fantasy: "Фэнтези",
      scifi: "Фантастика",
      animation: "Анимация",
      documentary: "Документальный",
      short: "Короткометражка",
      indie: "Инди",
      tvfilm: "ТВ-фильм",
      docudrama: "Докудрама",
      docuseries: "Документальный сериал",
      cyberpunk: "Киберпанк",
      adventure: "Приключения",
    },
  },
  en: {
    title: "IT Movies",
    titleFull: "IT Movies - A curated list of films and series about computers, technology and AI",
    subtitle: "A curated list of films and series about computers, technology, AI, etc",
    invite: "Suggest a film, series - <img src=\"static/telegram_32.png\" alt=\"\" width=\"16\" height=\"16\" class=\"tg-icon\"> <a href=\"https://t.me/wh_lab\" target=\"_blank\" rel=\"noopener\">Whitehat Lab</a> or in <a href=\"https://t.me/whitehat_chat\" target=\"_blank\" rel=\"noopener\">chat</a>",
    search: "Search title, genre, year",
    movies: "Movies",
    series: "Series",
    documentaries: "Documentaries",
    name: "Title",
    genre: "Genre",
    year: "Year",
    kp: "Kinopoisk",
    imdb: "IMDb",
    recommend: "Recommended",
    empty: "Nothing found",
    codedWith: "Coded with",
    total: "Total titles",
    loadLabel: "Load",
    scrollTop: "Back to top",
    close: "Close",
    theme: "Theme",
    themeDark: "Dark theme",
    themeLight: "Light theme",
    genres: {
      crime: "Crime",
      ai: "AI",
      drama: "Drama",
      thriller: "Thriller",
      romance: "Romance",
      comedy: "Comedy",
      mystery: "Mystery",
      action: "Action",
      history: "History",
      biography: "Biography",
      slasher: "Slasher",
      fantasy: "Fantasy",
      scifi: "Science fiction",
      animation: "Animation",
      documentary: "Documentary",
      short: "Short",
      indie: "Indie",
      tvfilm: "TV film",
      docudrama: "Docudrama",
      docuseries: "Documentary series",
      cyberpunk: "Cyberpunk",
      adventure: "Adventure",
    },
  },
};

function compare(a, b, key, dir, lang) {
  const mul = dir === "desc" ? -1 : 1;
  if (key === "title") {
    const av = lang === "ru" ? a.titleRu : a.titleEn;
    const bv = lang === "ru" ? b.titleRu : b.titleEn;
    return av.localeCompare(bv, lang === "ru" ? "ru" : "en") * mul;
  }
  if (key === "genre") {
    return a.genres.join(" ").localeCompare(b.genres.join(" ")) * mul;
  }
  if (key === "year") return ((a.year || 0) - (b.year || 0)) * mul;
  if (key === "kp" || key === "imdb") {
    const av = a[key + "Rating"] == null ? -1 : a[key + "Rating"];
    const bv = b[key + "Rating"] == null ? -1 : b[key + "Rating"];
    return (av - bv) * mul;
  }
  return 0;
}

function formatRating(value) {
  if (value == null || value === "") return "❓";
  return Number(value).toFixed(1);
}

function isHighRating(value) {
  return value != null && value !== "" && Number(value) >= 7;
}

const DESKTOP_QUERY = "(hover: hover) and (pointer: fine) and (min-width: 720.02px)";

function useIsDesktop() {
  const mq = window.matchMedia(DESKTOP_QUERY);
  const isDesktop = ref(mq.matches);
  const onChange = (event) => {
    isDesktop.value = event.matches;
  };
  onMounted(() => mq.addEventListener("change", onChange));
  onUnmounted(() => mq.removeEventListener("change", onChange));
  return isDesktop;
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
    withPosters: Boolean
  },
  emits: ["sort"],
  data() {
    return {
      selectedPoster: null,
    };
  },
  watch: {
    selectedPoster(open) {
      if (open) {
        this._onKeydown = (e) => {
          if (e.key === "Escape") this.closePoster();
        };
        window.addEventListener("keydown", this._onKeydown);
      } else if (this._onKeydown) {
        window.removeEventListener("keydown", this._onKeydown);
        this._onKeydown = null;
      }
    },
  },
  beforeUnmount() {
    if (this._onKeydown) {
      window.removeEventListener("keydown", this._onKeydown);
      this._onKeydown = null;
    }
  },
  methods: {
    formatRating,
    isHighRating,
    imdbUrl,
    kpUrl,
    displayTitle(item) {
      return this.lang === "ru" ? item.titleRu : item.titleEn;
    },
    altTitle(item) {
      const primary = this.displayTitle(item);
      const other = this.lang === "ru" ? item.titleEn : item.titleRu;
      return other && other !== primary ? other : "";
    },
    genreLabel(item) {
      return item.genres.map((g) => this.t.genres[g] || g).join(" / ");
    },
    thClass(key) {
      return {
        sortable: true,
        "is-asc": this.sort.key === key && this.sort.dir === "asc",
        "is-desc": this.sort.key === key && this.sort.dir === "desc",
      };
    },
    ariaSort(key) {
      if (this.sort.key !== key) return "none";
      return this.sort.dir === "asc" ? "ascending" : "descending";
    },
    arrow(key) {
      if (this.sort.key !== key) return "↕";
      return this.sort.dir === "asc" ? "↑" : "↓";
    },
    openPoster(item) {
      this.selectedPoster = item;
    },
    closePoster() {
      this.selectedPoster = null;
    },
  },
  computed: {
    favIcon() {
      return "static/favorite_32.png";
    },
  },
  template: `
    <section :id="id">
      <h2>{{ title }}</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th :class="thClass('title')" :aria-sort="ariaSort('title')" tabindex="0" @click="$emit('sort', typeKey, 'title')" @keydown.enter="$emit('sort', typeKey, 'title')">{{ t.name }} <span class="arrow">{{ arrow('title') }}</span></th>
              <th :class="thClass('genre')" :aria-sort="ariaSort('genre')" tabindex="0" @click="$emit('sort', typeKey, 'genre')" @keydown.enter="$emit('sort', typeKey, 'genre')">{{ t.genre }} <span class="arrow">{{ arrow('genre') }}</span></th>
              <th :class="thClass('year')" :aria-sort="ariaSort('year')" tabindex="0" @click="$emit('sort', typeKey, 'year')" @keydown.enter="$emit('sort', typeKey, 'year')">{{ t.year }} <span class="arrow">{{ arrow('year') }}</span></th>
              <th :class="thClass('kp')" :aria-sort="ariaSort('kp')" tabindex="0" @click="$emit('sort', typeKey, 'kp')" @keydown.enter="$emit('sort', typeKey, 'kp')"><span class="th-label"><img class="col-icon" src="static/favicon_kp.png" alt="" width="14" height="14"><span class="th-text">{{ t.kp }}</span></span> <span class="arrow">{{ arrow('kp') }}</span></th>
              <th :class="thClass('imdb')" :aria-sort="ariaSort('imdb')" tabindex="0" @click="$emit('sort', typeKey, 'imdb')" @keydown.enter="$emit('sort', typeKey, 'imdb')"><span class="th-label"><img class="col-icon" src="static/favicon_imdb.png" alt="" width="14" height="14"><span class="th-text">{{ t.imdb }}</span></span> <span class="arrow">{{ arrow('imdb') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.imdbId || item.kpId">
              <td class="title-cell">
                <span class="poster-wrap" v-if="withPosters && item.poster">
                  <img class="poster-icon" src="static/poster_icon.png" alt="" width="24" height="24" @click.stop="openPoster(item)">
                </span>
                <span class="fav-icon" :title="t.recommend" v-if="item.fav"><img :src="favIcon" :alt="t.recommend" width="24" height="24"></span>
                <a v-if="item.imdbId" :href="imdbUrl(item)" target="_blank" rel="noopener">{{ displayTitle(item) }}</a>
                <span v-else>{{ displayTitle(item) }}</span>
                <span class="alt-title" v-if="altTitle(item)">{{ altTitle(item) }}</span>
              </td>
              <td class="genre">{{ genreLabel(item) }}</td>
              <td class="year">{{ item.year }}</td>
              <td class="num">
                <img class="ext-icon" src="static/external_link_icon.png" alt=""><a class="kp" :href="kpUrl(item)" target="_blank" rel="noopener"><span>{{ formatRating(item.kpRating) }}</span><span class="star" v-if="isHighRating(item.kpRating)" aria-hidden="true">★</span></a>
              </td>
              <td class="num">
                <img class="ext-icon" src="static/external_link_icon.png" alt=""><a class="imdb" :href="imdbUrl(item)" target="_blank" rel="noopener"><span>{{ formatRating(item.imdbRating) }}</span><span class="star" v-if="isHighRating(item.imdbRating)" aria-hidden="true">★</span></a>
              </td>
            </tr>
            <tr v-if="!items.length">
              <td colspan="5" class="empty">{{ t.empty }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <Teleport to="body">
        <div class="poster-modal" v-if="selectedPoster" role="dialog" aria-modal="true" :aria-label="displayTitle(selectedPoster)" @click.self="closePoster">
          <div class="poster-modal-inner">
            <img :src="selectedPoster.poster" :alt="displayTitle(selectedPoster)">
            <button class="poster-close" :aria-label="t.close" @click="closePoster">x</button>
          </div>
        </div>
      </Teleport>
    </section>
  `,
};

const app = createApp({
  components: { CatalogTable },
  setup() {
    const lang = ref(localStorage.getItem("it-movies-lang") || "ru");
    const theme = ref(localStorage.getItem("it-movies-theme") || "dark");
    const query = ref("");
    const showScrollTop = ref(false);
    const loadTime = ref(null);
    const isDesktop = useIsDesktop();

    const sorts = reactive({
      series: { key: "title", dir: "asc" },
      movie: { key: "title", dir: "asc" },
      documentary: { key: "title", dir: "asc" },
    });

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
        localStorage.setItem("it-movies-theme", value);
        document.documentElement.classList.toggle("dark", value === "dark");
      },
      { immediate: true }
    );

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
      if (document.readyState === "complete") {
        measureLoadTime();
      } else {
        window.addEventListener("load", measureLoadTime, { once: true });
      }
    });

    onUnmounted(() => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("load", measureLoadTime);
    });

    const t = computed(() => I18N[lang.value]);

    const filtered = computed(() => {
      const q = query.value.trim().toLowerCase();
      if (!q) return window.CATALOG;
      return window.CATALOG.filter((item) => {
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
      showScrollTop,
      loadTime,
      isDesktop,
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
