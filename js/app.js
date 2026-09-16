const { createApp, computed, reactive, ref, watch, onMounted, onUnmounted } = Vue;

const I18N = {
  ru: {
    title: "IT Movies",
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
    recommend:"I recommend",
    empty: "Nothing found",
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
  if (key === "kp") {
    const av = a.kpRating == null ? -1 : a.kpRating;
    const bv = b.kpRating == null ? -1 : b.kpRating;
    return (av - bv) * mul;
  }
  if (key === "imdb") {
    const av = a.imdbRating == null ? -1 : a.imdbRating;
    const bv = b.imdbRating == null ? -1 : b.imdbRating;
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

const DESKTOP_QUERY = "(hover: hover) and (pointer: fine) and (min-width: 721px)";

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
              <th :class="thClass('title')" @click="$emit('sort', typeKey, 'title')">{{ t.name }} <span class="arrow">{{ arrow('title') }}</span></th>
              <th :class="thClass('genre')" @click="$emit('sort', typeKey, 'genre')">{{ t.genre }} <span class="arrow">{{ arrow('genre') }}</span></th>
              <th :class="thClass('year')" @click="$emit('sort', typeKey, 'year')">{{ t.year }} <span class="arrow">{{ arrow('year') }}</span></th>
              <th :class="thClass('kp')" @click="$emit('sort', typeKey, 'kp')"><span class="th-label"><img class="col-icon" src="static/favicon_kp.png" alt="" width="14" height="14"><span class="th-text">{{ t.kp }}</span></span> <span class="arrow">{{ arrow('kp') }}</span></th>
              <th :class="thClass('imdb')" @click="$emit('sort', typeKey, 'imdb')"><span class="th-label"><img class="col-icon" src="static/favicon_imdb.png" alt="" width="14" height="14"><span class="th-text">{{ t.imdb }}</span></span> <span class="arrow">{{ arrow('imdb') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.imdbId">
              <td class="title-cell">
                <span class="poster-wrap" v-if="withPosters && item.poster">
                  <img class="poster-icon" src="static/poster_icon.png" alt="" width="24" height="24" @click.stop="openPoster(item)">
                </span>
                <span class="fav-icon" :title="t.recommend" v-if="item.fav"><img :src="favIcon" :alt="t.recommend" width="24" height="24"></span>
                <a :href="imdbUrl(item)" target="_blank" rel="noopener">{{ displayTitle(item) }}</a>
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
        <div class="poster-modal" v-if="selectedPoster" @click.self="closePoster">
          <img :src="selectedPoster.poster" :alt="displayTitle(selectedPoster)">
          <button class="poster-close" @click="closePoster">✕</button>
        </div>
      </Teleport>
    </section>
  `,
};

const start = performance.now();
const app = createApp({
  components: { CatalogTable },
  setup() {
    const lang = ref(localStorage.getItem("it-movies-lang") || "ru");
    const theme = ref(localStorage.getItem("it-movies-theme") || "dark");
    const query = ref("");
    const showScrollTop = ref(false);
    const renderTime = ref(null);
    const isDesktop = useIsDesktop();

    onMounted(() => {
      renderTime.value = (performance.now() - start).toFixed(1);
    });
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
        document.title = I18N[value].title;
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

    onMounted(() => {
      window.addEventListener("scroll", handleScroll);
    });

    onUnmounted(() => {
      window.removeEventListener("scroll", handleScroll);
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
      renderTime,
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
