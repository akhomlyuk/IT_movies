const { createApp, computed, ref, watch, onMounted, onUnmounted } = Vue;

const {
  safeRead,
  safeWrite,
  langFrom,
  themeFrom,
  toggleThemeClass,
  scrollToTop,
  installErrorHandler,
} = window.ITMoviesCommon;

let currentLang = "ru";

const ABOUT_TEMPLATE = `
  <header class="top">
    <div class="brand">
      <div class="logo">
        <a href="./"><img src="static/logo.webp" alt="IT Movies" fetchpriority="high" decoding="async" width="100" height="100"></a>
      </div>
      <div class="brand-text">
        <h1>{{ about.heading }}</h1>
        <p v-if="altTitle">{{ altTitle }}</p>
        <span class="ch-row"><span class="ch-item"><svg class="icon ch-mark ch-mark--tg" viewBox="0 0 16 16" aria-hidden="true"><use href="static/share.svg#icon-telegram"></use></svg><a class="ch-link ch-link--tg" href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer" aria-label="Канал в Telegram: Whitehat Lab" :aria-label="t.telegramChannel" :title="t.telegramChannel"><span><span class="pre-mount">в Telegram</span><span class="post-mount">{{ t.telegramLabel }}</span></span></a></span><span class="ch-item"><svg class="icon ch-mark ch-mark--max" viewBox="0 0 1000 1000" aria-hidden="true"><use href="static/share.svg#icon-max"></use></svg><a class="ch-link ch-link--max" href="https://max.ru/join/ByzPb9lbZJwBbvKvRvi3ioBNaFF9TyuXDy5vrIX48vs" target="_blank" rel="noopener noreferrer" aria-label="Канал в Max: Whitehat Lab" :aria-label="t.maxChannel" :title="t.maxChannel"><span><span class="pre-mount">в Max</span><span class="post-mount">{{ t.maxLabel }}</span></span></a></span></span>
      </div>
    </div>
    <div class="toolbar">
      <div class="tool-buttons">
        <button type="button" class="theme-toggle" :aria-label="theme === 'dark' ? t.themeToLight : t.themeToDark" :title="theme === 'dark' ? t.themeToLight : t.themeToDark" @click="setTheme(theme === 'dark' ? 'light' : 'dark')">
          <svg v-if="theme === 'dark'" class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 .278a.77.77 0 0 1 .08.858 7.2 7.2 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277q.792-.001 1.533-.16a.79.79 0 0 1 .81.316.73.73 0 0 1-.031.893A8.35 8.35 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.75.75 0 0 1 6 .278M4.858 1.311A7.27 7.27 0 0 0 1.025 7.71c0 4.02 3.279 7.276 7.319 7.276a7.32 7.32 0 0 0 5.205-2.162q-.506.063-1.029.063c-4.61 0-8.343-3.714-8.343-8.29 0-1.167.242-2.278.681-3.286M10.794 3.148a.217.217 0 0 1 .412 0l.387 1.162c.173.518.579.924 1.097 1.097l1.162.387a.217.217 0 0 1 0 .412l-1.162.387a1.73 1.73 0 0 0-1.097 1.097l-.387 1.162a.217.217 0 0 1-.412 0l-.387-1.162A1.73 1.73 0 0 0 9.31 6.593l-1.162-.387a.217.217 0 0 1 0-.412l1.162-.387a1.73 1.73 0 0 0 1.097-1.097zM13.863.099a.145.145 0 0 1 .274 0l.258.774c.115.346.386.617.732.732l.774.258a.145.145 0 0 1 0 .274l-.774.258a1.16 1.16 0 0 0-.732.732l-.258.774a.145.145 0 0 1-.274 0l-.258-.774a1.16 1.16 0 0 0-.732-.732l-.774-.258a.145.145 0 0 1 0-.274l.774-.258c.346-.115.617-.386.732-.732z" fill="currentColor"/></svg>
          <svg v-else class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6m0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8M8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0m0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13m8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5M3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8m10.657-5.657a.5.5 0 0 1 0 .707l-1.414 1.415a.5.5 0 1 1-.707-.708l1.414-1.414a.5.5 0 0 1 .707 0m-9.193 9.193a.5.5 0 0 1 0 .707L3.05 13.657a.5.5 0 0 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0m9.193 2.121a.5.5 0 0 1-.707 0l-1.414-1.414a.5.5 0 0 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .707M4.464 4.465a.5.5 0 0 1-.707 0L2.343 3.05a.5.5 0 1 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .708" fill="currentColor"/></svg>
        </button>
        <button type="button" class="lang" :aria-label="t.swapLang + ': ' + (lang === 'ru' ? 'RU' : 'EN')" :title="t.swapLang" @click="setLang(lang === 'ru' ? 'en' : 'ru')">
          <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3 12h18M12 3c2.4 2.5 3.5 5.5 3.5 9S14.4 18.5 12 21c-2.4-2.5-3.5-5.5-3.5-9S9.6 5.5 12 3Z" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>
          <span>{{ lang === 'ru' ? 'RU' : 'EN' }}</span>
        </button>
      </div>
    </div>
  </header>

  <main id="main" tabindex="-1">
    <nav class="breadcrumb" :aria-label="t.home">
      <a href="./">{{ t.home }}</a><span class="bc-sep"> › </span><span class="bc-current">{{ about.heading }}</span>
    </nav>

    <article class="about-article">
      <p class="about-lead">{{ about.lead }}</p>

      <div class="profile">
        <img class="profile-avatar" src="static/exited3n_avatar.png" alt="Exited3n" width="140" height="140" decoding="async">
        <nav class="profile-links">
          <span class="visually-hidden">{{ about.linksLabel }}</span>
          <a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer"><svg aria-hidden="true"><use href="#i-tg"></use></svg><span>Whitehat Lab</span></a>
          <a href="https://max.ru/join/ByzPb9lbZJwBbvKvRvi3ioBNaFF9TyuXDy5vrIX48vs" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-max"></use></svg><span>Whitehat Lab MAX</span></a>
          <a href="https://github.com/akhomlyuk" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-gh"></use></svg><span>GitHub</span></a>
          <a href="https://hackerlab.pro/users/Exited3n" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-hlab"></use></svg><span>Hackerlab</span></a>
          <a href="https://standoff365.com/profile/Exited3n/" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-standoff"></use></svg><span>Standoff 365</span></a>
          <a href="./"><svg aria-hidden="true"><use href="#i-movie"></use></svg><span>IT Movies</span></a>
        </nav>
      </div>

      <section class="about-section">
        <h2>{{ about.ideaH }}</h2>
        <p>{{ about.ideaP }}</p>
      </section>
      <section class="about-section">
        <h2>{{ about.whoH }}</h2>
        <p v-html="about.whoP"></p>
      </section>
      <section class="about-section">
        <h2>{{ about.recordH }}</h2>
        <p v-html="about.recordP"></p>
      </section>
      <section class="about-section">
        <h2>{{ about.siteH }}</h2>
        <p>{{ about.siteP }}</p>
      </section>
      <section class="about-section">
        <h2>{{ about.suggestH }}</h2>
        <p v-html="about.suggestP"></p>
      </section>
      <section class="about-section">
        <h2>{{ about.principlesH }}</h2>
        <p v-html="about.principlesP"></p>
      </section>
    </article>
  </main>

  <footer>
    <div class="footer-line">
      <span>{{ t.codedWith }}</span><span class="heart"> ♥ </span><a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer">Exited3n</a>
    </div>
    <div class="footer-line">
      <a class="footer-privacy" href="./">{{ t.title }}</a><span class="footer-privacy"> · </span><a class="footer-privacy" href="privacy.html">{{ t.privacy }}</a>
    </div>
  </footer>
  <button class="scroll-top" :aria-label="t.scrollTop" @click="scrollToTop">↑</button>
`;

const app = createApp({
  setup() {
    const urlParams = new URLSearchParams(location.search);
    const lang = ref(langFrom(urlParams, safeRead));

    const colorScheme = window.matchMedia("(prefers-color-scheme: light)");
    const theme = ref(themeFrom(urlParams, safeRead));
    let cleanupColorScheme = null;

    watch(
      theme,
      (value) => toggleThemeClass(value),
      { immediate: true }
    );

    onMounted(() => {
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
    const about = computed(() => I18N[lang.value].about);
    const altTitle = computed(() =>
      lang.value === "ru" ? I18N.en.about.heading : I18N.ru.about.heading
    );

    watch(
      lang,
      (value) => {
        currentLang = value;
        safeWrite("it-movies-lang", value);
        document.documentElement.lang = value;
        document.title = I18N[value].about.title;
        const metaDesc = document.querySelector('meta[name="description"]');
        if (metaDesc) metaDesc.setAttribute("content", I18N[value].about.desc);
      },
      { immediate: true }
    );

    return {
      lang,
      theme,
      t,
      about,
      altTitle,
      setLang,
      setTheme,
      scrollToTop,
    };
  },
  template: ABOUT_TEMPLATE,
});

installErrorHandler(app, () => currentLang, () => I18N);

app.mount("#app");