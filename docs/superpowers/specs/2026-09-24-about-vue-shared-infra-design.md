# Дизайн: about.html на общей инфраструктуре (Vue-паттерн фильм-страниц)

Дата: 2026-09-24. Статус: подтверждён пользователем, ожидает review спеку.

## Контекст

`about.html` — единственная страница сайта, собранная по «старому» изолированному паттерну:

- свой inline-словарь `I18N` в `<script>` (дублирует `js/i18n.js`),
- два дублирующихся блока контента `data-lang-block="ru"` / `"en"` (без JS видны оба — баг),
- свой IIFE-скрипт, повторяющий логику `js/common.js` (lang/theme),
- свой `<style>` c `.wrap` / `.privacy` / `.profile` / `.sr-only` (классы `.privacy` также продублированы в `privacy.html`).

Главная (`index.html`) и все фильм-страницы — Vue-приложения на общих модулях (`js/i18n.js`, `js/common.js`, `css/style.css`). Цель: привести about к общему паттерну, чтобы отличался только центральный контент.

## Принятые решения (из диалога с пользователем)

1. **Навигация**: категорийную полосу `nav.nav` (Фильмы/Сериалы/Документальные) НЕ выводим — на about нет соответствующих секций. Вместо неё — breadcrumb `Главная › О сайте` (маркап как в `js/film.js`: `nav.breadcrumb` + `t.home`).
2. **Реализация**: Vue-приложение в паттерне `film.js` — новый `js/about.js`, минифицируется в `js/about.min.js` через `tools/gen_pages.py`. `about.html` статически содержит `#app`, noscript-фолбэк и подключает `vue.global.prod.js` + `i18n.min.js` + `common.min.js` + `about.min.js`.
3. **Шапка**: как на фильм-страницах — лого (ссылка на `./`), `h1 = about.heading` («О сайте» / «About the site») + altTitle другим языком (`p[altTitle]`), тулбар только с переключателями языка/темы. Без подзаголовка и без invite.
4. **Заголовок контента**: «О сайте» переезжает из h1 контента в h1 шапки (как у фильмов). Секции контента остаются `h2`. Это чинит давнюю асимметрию RU h1 / EN h2.
5. **Футер**: 2 строки `.footer-line` как на фильм-страницах: (1) «Сделано с ♥ Exited3n», (2) ссылки `.footer-privacy`: `IT Movies` (`t.title`, href `./`) · «Политика конфиденциальности» (`t.privacy`, href `privacy.html`). Строки метрик (`🎬 всего`, `⚡ загрузка`, дата обновления) НЕ переносятся — на about нет каталога. Вместо ссылки «О проекте» (сама на себя) — ссылка «IT Movies» на главную.

## Изменения по файлам

### 1. `js/i18n.js` — новый namespace `about` (ru + en паритет)

Ключи (RU-тексты — байт-в-байт из текущего `about.html`, строки 241–273):

| Ключ | ru | en |
|---|---|---|
| `about.heading` | О сайте | About the site |
| `about.title` | О сайте — IT Movies | About the site — IT Movies |
| `about.desc` | О сайте IT Movies: кто создал каталог кино о компьютерах и ИИ, как отбираются фильмы и как предложить свой. | About the IT Movies site: who curates the catalog, how titles are selected and how to suggest one. |
| `about.lead` | IT Movies — вручную собранный и поддерживаемый мной каталог фильмов, сериалов и документалок о компьютерах, киберпанке, интернете, ИИ и т.д. Без алгоритмов и ссылок на стриминги (не маленькие, сами найдете) | IT Movies is a hand-curated catalog of films, series and documentaries about computers, cyberpunk, the internet, AI and more, which I collect and maintain myself. No algorithms, no streaming links (they are not hard to find). |
| `about.ideaH` | Для кого это всё | Who it's for |
| `about.ideaP` | Для тех кто постоянно пишет мне в личку и/или чатах, форумах, что бы такого "хакерского" посмотреть. Тут все собрано в одном месте — это список, который я реально порекомендовал бы товарищам. | For everyone who keeps writing to me in DMs and/or chats and forums asking what "hacker" stuff to watch. Everything is gathered in one place — this is a list I would genuinely recommend to friends. |
| `about.whoH` | Кто за этим стоит и как отбираются фильмы | Who's behind it and how titles are selected |
| `about.whoP` | Подборку веду сам, мой канал \<a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Whitehat Lab\</a>. Это некоммерческий pet-проект, написать мне можно по ссылкам выше. | I curate the selection myself — my channel is \<a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Whitehat Lab\</a>. It's a non-commercial pet project; you can write to me via the links above. |
| `about.recordH` | Что внутри каждой записи | What each record contains |
| `about.recordP` | Английское и русское название, год, жанры, короткое описание на двух языках и постер. Рейтинги \<b>КиноПоиска\</b> и \<b>IMDB\</b> — ровно такие, какими были на момент обновления: без накрутки в ту или иную сторону. | English and Russian titles, year, genres, a short description in both languages and a poster. \<b>Kinopoisk\</b> and \<b>IMDb\</b> ratings are exactly as they were at the time of the update — not inflated in either direction. |
| `about.siteH` | Как устроен сайт | How the site works |
| `about.siteP` | Статическая сборка без бекенда, аккаунтов и комментариев. Есть фильтры по типу, жанру, году и рейтингу, сортировка, русский и английский интерфейс, светлая и тёмная тема — и всё работает даже без JavaScript. Все данные в одном открытом файле, дата обновления берётся из истории Git. | A static build with no backend, accounts or comments. Filters by type, genre, year and rating, sorting, RU/EN interface, light and dark theme — and everything works even without JavaScript. All data lives in one open file; the update date comes straight from Git history. |
| `about.suggestH` | Как предложить фильм | How to suggest a film |
| `about.suggestP` | Нашли ошибку или знаете отличный фильм? Пишите в \<a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Telegram\</a> или открывайте pull request на \<a href='https://github.com/akhomlyuk/IT_movies' target='_blank' rel='noopener noreferrer'>GitHub\</a> — проверяю и публикую без долгих очередей. | Found an error or know a great film? Write on \<a href='https://t.me/wh_lab' target='_blank' rel='noopener noreferrer'>Telegram\</a> or open a pull request on \<a href='https://github.com/akhomlyuk/IT_movies' target='_blank' rel='noopener noreferrer'>GitHub\</a> — I review and publish them without long queues. |
| `about.principlesH` | Принципы | Principles |
| `about.principlesP` | Никаких партнёрских ссылок и трекинга сверх того, что собирает яндекс метрика, описано в \<a href='privacy.html'>политике конфиденциальности\</a>. Код открыт — любое утверждение на сайте можно проверить в репозитории. | No affiliate links and no tracking beyond what Yandex Metrika collects, as described in the \<a href='privacy.html'>privacy policy\</a>. The code is open — any claim on this site can be verified in the repository. |
| `about.linksLabel` | Ссылки | Links |

Формат в `js/i18n.js`:
- обычные строки — двойные кавычки (`"..."`), кавычки внутри экранируются (`\"хакерского\"`);
- строки с HTML (`whoP`, `recordP`, `suggestP`, `principlesP`) — шаблонные литералы в бэктиках с одинарными кавычками в атрибутах (как `invite`).

Примечание: `about.title`/`about.desc` нужны для `watch(lang)` (см. `js/about.js`). Паритет ru/en проверяется автоматически блоком 5b в `verify.py`.

### 2. `js/about.js` — новый Vue-приложение (зеркало `film.js`)

- Структура: `ABOUT_TEMPLATE` + `createApp` + `installErrorHandler(app, () => currentLang, () => I18N)` + `app.mount("#app")`.
- `setup()`: `langFrom(urlParams, safeRead)`, `themeFrom(urlParams, safeRead)`, `watch(theme, toggleThemeClass, { immediate: true })`, слушатель `prefers-color-scheme` + `onMounted`/`onUnmounted` (как в `film.js`), `setLang`/`setTheme`, `t = computed(() => I18N[lang.value])`, `about = computed(() => I18N[lang.value].about)`, `heading = computed(() => about.value.heading)`, `altTitle = computed(() => lang.value === "ru" ? I18N.en.about.heading : I18N.ru.about.heading)`.
- `watch(lang, ..., { immediate: true })`: `safeWrite("it-movies-lang", value)`, `document.documentElement.lang = value`, `document.title = I18N[value].about.title`, `meta[name="description"]` → `I18N[value].about.desc`.
- `ABOUT_TEMPLATE` (без skip-link — фильм-хром его не имеет; `main#main` остаётся):
  ```html
  <header class="top"> … logo (./ + alt "IT Movies") + brand-text: <h1>{{ about.heading }}</h1><p v-if="altTitle">{{ altTitle }}</p> …
    <div class="toolbar"><div class="switchers"> lang + theme кнопки (как в film.js) </div></div>
  </header>
  <main id="main" tabindex="-1">
    <nav class="breadcrumb" :aria-label="t.home"><a href="./">{{ t.home }}</a><span class="bc-sep"> › </span><span class="bc-current">{{ about.heading }}</span></nav>
    <article class="privacy">
      <p>{{ about.lead }}</p>
      <div class="profile"> аватар img (static/exited3n_avatar.png, alt "Exited3n") + nav.profile-links: span.visually-hidden {{ about.linksLabel }} + 6 ссылок со спрайтом (Whitehat Lab, Whitehat Lab MAX, GitHub, Hackerlab, Standoff 365, IT Movies → ./) </div>
      <h2>{{ about.ideaH }}</h2><p>{{ about.ideaP }}</p>
      <h2>{{ about.whoH }}</h2><p v-html="about.whoP"></p>
      <h2>{{ about.recordH }}</h2><p v-html="about.recordP"></p>
      <h2>{{ about.siteH }}</h2><p>{{ about.siteP }}</p>
      <h2>{{ about.suggestH }}</h2><p v-html="about.suggestP"></p>
      <h2>{{ about.principlesH }}</h2><p v-html="about.principlesP"></p>
    </article>
  </main>
  <footer>
    <div class="footer-line"><span>{{ t.codedWith }}</span><span class="heart"> ♥ </span><a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer">Exited3n</a></div>
    <div class="footer-line"><a class="footer-privacy" href="./">{{ t.title }}</a><span class="footer-privacy"> · </span><a class="footer-privacy" href="privacy.html">{{ t.privacy }}</a></div>
  </footer>
  <button class="scroll-top" :aria-label="t.scrollTop" @click="scrollToTop">↑</button>
  ```
- Ключи с HTML — через `v-html` (паттерн `t.invite` на главной).

### 3. `about.html` — пересборка

- **Head**: SEO-часть остаётся без изменений (RU-дефолты): `<title>О сайте — IT Movies</title>`, meta description, og:title/og:description/og:locale/og:locale:alternate, canonical `SITE_BASE + "/about.html"` (все проверки verify.py 9e/9f/9g проходят как раньше). Блоки `<!-- begin:theme-script -->…<!-- end:theme-script -->` и JSON-LD `AboutPage` — дословно как сейчас. `<style>` удаляется полностью.
- **Body**:
  - SVG-спрайт (6 символов `i-tg`, `i-max`, `i-gh`, `i-hlab`, `i-standoff`, `i-movie`) — остаётся, вне `#app`;
  - `<div id="app" v-cloak>` — внутри только `<noscript>` с RU-фолбэком (ниже); Vue-шаблон рендерится в `#app` поверх, как на фильм-страницах; skip-link не добавляем (решение 3);
  - `<noscript>` — статический RU-фолбэк (см. ниже);
  - скрипты: `<script src="js/vue.global.prod.js" defer>`, `<script src="js/i18n.min.js" defer>`, `<script src="js/common.min.js" defer>`, `<script src="js/about.min.js" defer>`;
  - `<!-- begin:metrika -->…<!-- end:metrika -->` — дословно как сейчас.
- **Noscript-фолбэк** (ручной, RU): header.top (лого h1 «О сайте» + p «About the site»), breadcrumb `Главная › О сайте` (статичный), `article.privacy` с полным RU-контентом (lead → карточка профиля с 6 ссылками → h2+p секции, HTML-ссылки реальными `a href`), футер 2 строки. Копия нынешнего RU-блока с поправкой на новую структуру. Спрайт вне `#app` — SVG `<use>` резолвится по документу, работает и в noscript.

### 4. `css/style.css` — перенос стилей (общие css)

Перенести из `about.html` `<style>` (убрать `<style>` из about.html полностью):
- `.privacy` (карточка контента: фон var(--paper), border var(--line), radius 8px) и связанные `.privacy h1/h2/p/ul/li/code/a` — те же правила, что сейчас в about.html (идентичны privacy.html);
- `.profile`, `.profile-avatar`, `.profile-links`, `.profile-links a`, `a:hover/:focus-visible`, `.profile-links svg`, `.profile-links span`, media-query 480px;
- убрать `.sr-only` и `.wrap` — использовать готовые `.visually-hidden` (style.css:974) и контейнер `#app`;
- НЕ трогать privacy.html (вне скоупа; свой inline-копия остаётся как есть — визуально идентично).

### 5. `tools/gen_pages.py` — минификация

- В `main()` список `("i18n.js", "common.js", "app.js", "film.js")` (строка ~793) → добавить `"about.js"`. `js/about.min.js` начнёт генерироваться.
- Остальная генерация (index/404/films/sitemap/robots) не меняется.

### 6. `tools/verify.py` — списки файлов

Добавить `"about.js"` (и `about.min.js` где нужно):
- строка ~310: bracket-balance — `("app.js", "i18n.js", "film.js", "common.js", "about.js")`;
- строки ~355–356: node --check — `"about.js"` и `"about.min.js"`;
- строка ~382: производные `.min.js` — `for name in ("i18n.js", "common.js", "app.js", "film.js", "about.js")`;
- строка ~176: сканирование static-ссылок — включить `about_js` в конкатенацию (чтобы `static/...` из about-шаблона проверялось).

### 7. Не трогаем

`index.html`, `privacy.html`, `js/data.js`, `js/app.js`, `js/film.js`, `js/common.js`, JSON-LD, метрика, canonical, sitemap/robots (URLы не меняются).

## Проверка (гейт)

1. `python tools/gen_pages.py` — регенерирует `js/about.min.js`, `js/i18n.min.js` (контент i18n.js изменился).
2. `python tools/verify.py --strict` — финальный вывод `✅ All good`.
3. Ручной smoke (опционально): `python -m http.server 8000`, проверить about.html — переключение языка/темы, breadcrumb, карточка профиля, noscript-фолбэк.

## Известные риски / замечания

- RU-тексты обязаны сохраниться дословно (пользователь их выверял). Контроль: diff контента до/после.
- `js/i18n.min.js` изменится (новые ключи) — это ожидаемая регенерация.
- `about.js` обязан проходить `node --check` и bracket-balance; `ABOUT_TEMPLATE` — строка шаблон в бэктиках, кавычки/бэктики внутри осторожно.
- Skip-link (как на главной) сознательно НЕ добавляем: фильм-шаблоны его не имеют, «шапка как на фильм-страницах» — согласованное решение; `main#main tabindex="-1"` для a11y сохраняется.

## Вне скоупа (follow-ups)

- Конвертация `privacy.html` на тот же Vue-паттерн (сейчас — старый паттерн с inline-словарём; `.privacy` уже станет общим в style.css).
- Smoke-харнесс для `about.js` в `tools/smoke.js` (не обязателен — покрыт node --check + паритет ключей).