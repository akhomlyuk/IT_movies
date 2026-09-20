window.ITMoviesCommon = (function () {
  const SUPPORTED = { lang: ["ru", "en"], theme: ["dark", "light"] };

  function safeRead(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }

  function safeWrite(key, value) {
    try { localStorage.setItem(key, value); } catch {}
  }

  function makeSlug(titleEn) {
    return titleEn
      .toLowerCase()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]+/g, "")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "");
  }

  function itemSlug(item) {
    const base = item.imdbId || `kp-${item.kpId}`;
    return `${base}-${makeSlug(item.titleEn)}`;
  }

  function filmUrl(item) {
    return `films/${itemSlug(item)}/`;
  }

  function kpUrl(item) {
    return `https://www.kinopoisk.ru/film/${item.kpId}/`;
  }

  function imdbUrl(item) {
    return item.imdbId ? `https://www.imdb.com/title/${item.imdbId}/` : null;
  }

  function hasRating(value) {
    return value != null && value !== "";
  }

  function isHighRating(value) {
    return hasRating(value) && Number(value) >= 7;
  }

  function formatRating(value, noDataText) {
    return hasRating(value) ? Number(value).toFixed(1) : noDataText;
  }

  function displayTitle(item, lang) {
    return lang === "ru" ? item.titleRu : item.titleEn;
  }

  function altTitle(item, lang) {
    const primary = displayTitle(item, lang);
    const other = lang === "ru" ? item.titleEn : item.titleRu;
    return other && other !== primary ? other : "";
  }

  function genreLabel(item, t) {
    return item.genres.map((g) => t.genres[g] || g).join(" / ");
  }

  function langFrom(urlParams, read) {
    const param = urlParams.get("lang");
    if (SUPPORTED.lang.includes(param)) return param;
    const saved = read("it-movies-lang");
    return SUPPORTED.lang.includes(saved)
      ? saved
      : navigator.language.startsWith("ru")
        ? "ru"
        : "en";
  }

  function themeFrom(urlParams, read) {
    const param = urlParams.get("theme");
    if (SUPPORTED.theme.includes(param)) return param;
    const saved = read("it-movies-theme");
    return SUPPORTED.theme.includes(saved)
      ? saved
      : window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
  }

  function toggleThemeClass(value, metaThemeColor) {
    document.documentElement.classList.toggle("dark", value === "dark");
    if (metaThemeColor) {
      metaThemeColor.setAttribute(
        "content",
        value === "dark" ? "#1a1a1f" : "#f4f3ef"
      );
    }
  }

  function updateScrollState(showRef) {
    showRef.value = window.scrollY > 300;
  }

  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function installErrorHandler(app, getCurrentLang, getI18N) {
    if (app.config) {
      app.config.errorHandler = (err, instance, info) => {
        console.error("[Vue error]", err, info);
        const main = document.querySelector("#app main");
        if (main) {
          main.innerHTML = `<p class="empty">${getI18N()[getCurrentLang()].fatalError}</p>`;
        }
      };
    }
  }

  return {
    SUPPORTED,
    safeRead,
    safeWrite,
    makeSlug,
    itemSlug,
    filmUrl,
    kpUrl,
    imdbUrl,
    hasRating,
    isHighRating,
    formatRating,
    displayTitle,
    altTitle,
    genreLabel,
    langFrom,
    themeFrom,
    toggleThemeClass,
    updateScrollState,
    scrollToTop,
    installErrorHandler,
  };
})();