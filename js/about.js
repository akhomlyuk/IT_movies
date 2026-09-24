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
      </div>
    </div>
    <div class="toolbar">
      <div class="tool-buttons">
        <button type="button" class="theme-toggle" :aria-label="theme === 'dark' ? t.themeToLight : t.themeToDark" :title="theme === 'dark' ? t.themeToLight : t.themeToDark" @click="setTheme(theme === 'dark' ? 'light' : 'dark')">{{ theme === 'dark' ? '🌙' : '☀️' }}</button>
        <button type="button" class="lang" :aria-label="t.swapLang + ': ' + (lang === 'ru' ? 'RU' : 'EN')" :title="t.swapLang" @click="setLang(lang === 'ru' ? 'en' : 'ru')">🌐 {{ lang === 'ru' ? 'RU' : 'EN' }}</button>
      </div>
    </div>
  </header>

  <main id="main" tabindex="-1">
    <nav class="breadcrumb" :aria-label="t.home">
      <a href="./">{{ t.home }}</a><span class="bc-sep"> › </span><span class="bc-current">{{ about.heading }}</span>
    </nav>

    <article class="privacy">
      <p>{{ about.lead }}</p>

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

      <h2>{{ about.ideaH }}</h2>
      <p>{{ about.ideaP }}</p>

      <h2>{{ about.whoH }}</h2>
      <p v-html="about.whoP"></p>

      <h2>{{ about.recordH }}</h2>
      <p v-html="about.recordP"></p>

      <h2>{{ about.siteH }}</h2>
      <p>{{ about.siteP }}</p>

      <h2>{{ about.suggestH }}</h2>
      <p v-html="about.suggestP"></p>

      <h2>{{ about.principlesH }}</h2>
      <p v-html="about.principlesP"></p>
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