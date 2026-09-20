#!/usr/bin/env python3
"""Generate a static SEO page per catalog record into films/<slug>/index.html.

Each page shares the look of the main page (css/style.css) and is rendered
by the shared Vue app in js/film.js. A <noscript> block keeps key content
visible to crawlers without JS. JSON-LD and meta are emitted statically.
"""
import html
import json
import re
import shutil
import sys

from lib import ROOT, SITE_BASE, load_catalog, make_slug, item_slug, ru_genres, has_rating, fmt_rating, webp_size

sys.stdout.reconfigure(encoding="utf-8")

OUT = ROOT / "films"
TYPE_LABELS = {"movie": "Фильм", "series": "Сериал", "documentary": "Документальный"}

catalog = load_catalog()

RU_GENRES = ru_genres()

def star(v):
    return " ★" if has_rating(v) and float(v) >= 7 else ""

def related_to(item, catalog, n=5):
    gs = set(item["genres"])
    scored = sorted(
        (
            (sum(1 for g in other["genres"] if g in gs), other)
            for other in catalog
            if other is not item
        ),
        key=lambda t: t[0],
        reverse=True,
    )
    top = [other for score, other in scored if score > 0]
    rest = [other for score, other in scored if score == 0]
    return (top + rest)[: max(n, 1)]

def esc(s):
    return html.escape(str(s), quote=True)

THEME_SCRIPT = """  <script>
    (function () {
      var t;
      try { t = new URLSearchParams(location.search).get("theme"); } catch (e) {}
      if (t !== "dark" && t !== "light") {
        try { t = localStorage.getItem("it-movies-theme"); } catch (e) { t = null; }
      }
      if (t !== "dark" && t !== "light") {
        t = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
      }
      if (t === "dark") {
        document.documentElement.classList.add("dark");
        var m = document.querySelector('meta[name="theme-color"]');
        if (m) m.setAttribute("content", "#1a1a1f");
      }
    })();
  </script>"""

THEME_MARK = ("<!-- begin:theme-script -->", "<!-- end:theme-script -->")
NSCRIPT_MARK = ("<!-- begin:catalog-noscript -->", "<!-- end:catalog-noscript -->")
LD_MARK = ("<!-- begin:index-ld -->", "<!-- end:index-ld -->")
METRIKA_MARK = ("<!-- begin:metrika -->", "<!-- end:metrika -->")

METRIKA_ID = "112571181"
METRIKA_SCRIPT = """  <!-- Yandex.Metrika counter -->
  <script type="text/javascript">
    (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id={id}', 'ym');

    ym({id}, 'init', {ssr:true, clickmap:true, referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
  </script>
  <noscript><div><img src="https://mc.yandex.ru/watch/{id}" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
  <!-- /Yandex.Metrika counter -->""".replace("{id}", METRIKA_ID)


def index_ld_json(catalog):
    base = SITE_BASE + "/"
    items = []
    for i, item in enumerate(catalog):
        entry = {
            "@type": "TVSeries" if item["type"] == "series" else "Movie",
            "position": i + 1,
            "name": item["titleRu"],
            "alternateName": item["titleEn"],
            "url": base + "films/" + item_slug(item) + "/",
        }
        if item.get("year"):
            entry["datePublished"] = str(item["year"])
        items.append(entry)
    graph = [
        {
            "@type": "WebSite",
            "@id": base,
            "url": base,
            "name": "IT Movies",
            "inLanguage": ["ru", "en"],
            "potentialAction": {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": base + "?q={search_term_string}",
                },
                "query-input": "required name=search_term_string",
            },
        },
        {
            "@type": "ItemList",
            "name": "Фильмы и сериалы о компьютерах, технологиях и искусственном интеллекте",
            "numberOfItems": len(catalog),
            "itemListElement": items,
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("<", "\\u003c")


def inject_ld(src, catalog):
    n = src.count(LD_MARK[0]) + src.count(LD_MARK[1])
    if n != 2:
        raise SystemExit(f"index-ld markers ({n}/2) not found in index.html")
    block = (
        LD_MARK[0]
        + '\n  <script type="application/ld+json">'
        + index_ld_json(catalog)
        + "</script>\n"
        + LD_MARK[1]
    )
    return re.sub(
        re.escape(LD_MARK[0]) + r".*?" + re.escape(LD_MARK[1]),
        lambda m: block,
        src,
        count=1,
        flags=re.S,
    )


def slim_catalog(catalog):
    return [{k: v for k, v in item.items() if k != "desc"} for item in catalog]


def catalog_js(catalog):
    body = json.dumps(slim_catalog(catalog), ensure_ascii=False, separators=(",", ":"))
    return "window.CATALOG = " + body + ";\n"


_OPS = (
    "**=", ">>>=", "<<=", ">>=", "===", "!==",
    "**", "&&", "||", "??", "?.", "=>", ">=", "<=",
    "==", "!=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
    "<<", ">>", ">>>", "++", "--",
)
_OP_START = frozenset("+-*/%=&|<>!?:^~")
_WORD_CHAR = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)
_VERB = {"return", "typeof", "in", "of", "new", "delete", "void", "yield", "case",
         "throw", "do", "else", "instanceof", "await", "extends"}


def _min_need_space(prev, tok):
    l = prev[-1]
    f = tok[0]
    if l in _WORD_CHAR and f in _WORD_CHAR:
        return True
    if (l, f) in (("+", "+"), ("-", "-"), ("*", "*"), ("/", "/"), ("/", "*"), ("*", "/")):
        return True
    return False


def minify_js(src):
    """Conservative JS minifier: strips comments and non-semantic whitespace.

    Tokenizer that keeps strings, template literals (incl. ${...}) and regex
    literals intact; inserts a single space only where adjacent tokens would
    otherwise merge into a different token. Deliberately does not reflow, so
    ASI/newline semantics are preserved.
    """
    words = ""
    i = 0
    n = len(src)
    out = []
    prev = ""
    expr = False  # True when the next '/' must be a regex, not a division

    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i + 2)
            i = n if j == -1 else j
            continue
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c in "\"'`":
            if c == "`":
                tok, i = _read_template(src, i)
            else:
                tok, i = _read_string(src, i)
        elif c in _WORD_CHAR:
            j = i
            while j < n and src[j] in _WORD_CHAR:
                j += 1
            tok = src[i:j]
            i = j
            expr = tok not in _VERB
        elif c == "/" and expr:
            tok, i = _read_regex(src, i)
            expr = True
        elif c in _OP_START:
            tok = next((op for op in _OPS if src.startswith(op, i)), c)
            i += len(tok)
            expr = False
        else:
            tok = c
            i += 1
            expr = tok in "([{,:;=!&|?^~<>"

        if out and _min_need_space(prev, tok):
            out.append(" ")
        out.append(tok)
        prev = tok

    return "".join(out)


def _read_string(src, i):
    q = src[i]
    j = i + 1
    while j < len(src):
        if src[j] == "\\":
            j += 2
            continue
        if src[j] == q:
            return src[i : j + 1], j + 1
        j += 1
    raise ValueError("unterminated string literal while minifying")


def _read_template(src, i):
    j = i + 1
    interp = 0
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if interp:
            if c in "\"'`":
                if c == "`":
                    _, j = _read_template(src, j)
                else:
                    _, j = _read_string(src, j)
                continue
            if c == "{":
                interp += 1
            elif c == "}":
                interp -= 1
            j += 1
            continue
        if c == "$" and src.startswith("${", j):
            interp = 1
            j += 2
            continue
        if c == "`":
            return src[i : j + 1], j + 1
        j += 1
    raise ValueError("unterminated template literal while minifying")


def _read_regex(src, i):
    j = i + 1
    in_class = False
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            break
        elif c == "\n":
            break
        j += 1
    while j < len(src) and src[j].isalpha():
        j += 1
    return src[i:j], j


def inject_theme(src):
    n = src.count(THEME_MARK[0]) + src.count(THEME_MARK[1])
    if n != 2:
        raise SystemExit(f"theme markers ({n}/2) not found in index/404 source")
    return re.sub(
        re.escape(THEME_MARK[0]) + r".*?" + re.escape(THEME_MARK[1]),
        THEME_MARK[0] + "\n" + THEME_SCRIPT + "\n" + THEME_MARK[1],
        src,
        count=1,
        flags=re.S,
    )


def inject_metrika(src):
    n = src.count(METRIKA_MARK[0]) + src.count(METRIKA_MARK[1])
    if n != 2:
        raise SystemExit(f"metrika markers ({n}/2) not found in index/404 source")
    return re.sub(
        re.escape(METRIKA_MARK[0]) + r".*?" + re.escape(METRIKA_MARK[1]),
        METRIKA_MARK[0] + "\n" + METRIKA_SCRIPT + "\n" + METRIKA_MARK[1],
        src,
        count=1,
        flags=re.S,
    )


def index_noscript(catalog):
    out = []
    for t, label in (
        ("movie", "Фильмы"),
        ("documentary", "Документальные"),
        ("series", "Сериалы"),
    ):
        rows = [i for i in catalog if i["type"] == t]
        lis = "".join(
            f'          <li><a href="films/{item_slug(i)}/">{esc(i["titleRu"])}</a></li>\n'
            for i in rows
        )
        out.append(f'        <h3>{label}</h3>\n        <ul>\n{lis}        </ul>\n')
    return "".join(out)


def inject_noscript(src, catalog):
    n = src.count(NSCRIPT_MARK[0]) + src.count(NSCRIPT_MARK[1])
    if n != 2:
        raise SystemExit(f"noscript markers ({n}/2) not found in index.html")
    return re.sub(
        re.escape(NSCRIPT_MARK[0]) + r".*?" + re.escape(NSCRIPT_MARK[1]),
        NSCRIPT_MARK[0] + "\n" + index_noscript(catalog) + NSCRIPT_MARK[1],
        src,
        count=1,
        flags=re.S,
    )


def render(item, related):
    slug = item_slug(item)
    page_url = f"{SITE_BASE}/films/{slug}/"
    home_url = f"{SITE_BASE}/"
    title_ru = item["titleRu"]
    title_en = item["titleEn"]
    desc_ru = item["desc"]["ru"]
    desc_en = item["desc"]["en"]
    type_label = TYPE_LABELS.get(item["type"], item["type"])
    poster = (item.get("poster") or "").lstrip("/")
    poster_dims = webp_size(ROOT / poster) if poster else None
    genres_ru = sorted(RU_GENRES.get(g, g) for g in item["genres"])
    genre_list = ", ".join(genres_ru)

    schema_type = "TVSeries" if item["type"] == "series" else "Movie"
    og_type = "video.tv_show" if item["type"] == "series" else "video.movie"
    graph = []
    movie = {
        "@type": schema_type,
        "name": title_ru,
        "alternateName": title_en,
        "url": page_url,
        "description": desc_ru,
        "datePublished": str(item["year"]),
        "genre": genres_ru,
        "sameAs": [],
    }
    if item.get("imdbId"):
        movie["sameAs"].append(f"https://www.imdb.com/title/{item['imdbId']}/")
    movie["sameAs"].append(f"https://www.kinopoisk.ru/film/{item['kpId']}/")
    if poster:
        movie["image"] = f"{SITE_BASE}/{poster}"
    for key, best in (("imdbRating", 10), ("kpRating", 10)):
        if has_rating(item.get(key)):
            movie["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": float(item[key]),
                "bestRating": 10,
                "worstRating": 1,
            }
            break
    graph.append(movie)

    graph.append({
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "IT Movies", "item": home_url},
            {"@type": "ListItem", "position": 2, "name": title_ru, "item": page_url},
        ],
    })

    if related:
        graph.append({
            "@type": "ItemList",
            "name": "Похожее в каталоге IT Movies",
            "numberOfItems": len(related),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "name": r["titleRu"],
                    "url": f"{SITE_BASE}/films/{item_slug(r)}/",
                }
                for i, r in enumerate(related)
            ],
        })

    json_ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("<", "\\u003c")

    page_data = json.dumps(
        {
            "item": item,
            "related": related,
            "posterW": poster_dims[0] if poster_dims else None,
            "posterH": poster_dims[1] if poster_dims else None,
        },
        ensure_ascii=False,
    ).replace("<", "\\u003c")

    poster_abs = f"{SITE_BASE}/{poster}" if poster else f"{SITE_BASE}/static/ogimage.webp"

    preload_poster = ""
    if poster:
        preload_poster = f'  <link rel="preload" as="image" href="../../{poster}" fetchpriority="high">\n'

    noscript_poster = ""
    if poster:
        dims = f' width="{poster_dims[0]}" height="{poster_dims[1]}"' if poster_dims else ""
        noscript_poster = (
            f'      <figure class="film-poster">\n'
            f'        <img src="../../{poster}" alt="{esc(title_ru)}"{dims}>\n'
            "      </figure>\n"
        )

    related_items = "".join(
        f'        <li><a href="../{item_slug(r)}/">{esc(r["titleRu"])}</a></li>\n'
        for r in related
    )

    rat_tiles = (
        f'        <div class="ratings">\n'
        f'          <a class="kp" href="https://www.kinopoisk.ru/film/{item["kpId"]}/" target="_blank" rel="noopener">Кинопоиск: {esc(fmt_rating(item.get("kpRating")))}{esc(star(item.get("kpRating")))}</a>\n'
    )
    if item.get("imdbId"):
        rat_tiles += (
            f'          <a class="imdb" href="https://www.imdb.com/title/{item["imdbId"]}/" target="_blank" rel="noopener">IMDb: {esc(fmt_rating(item.get("imdbRating")))}{esc(star(item.get("imdbRating")))}</a>\n'
        )
    rat_tiles += "        </div>\n"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title_ru)} — IT Movies</title>
  <meta name="description" content="{esc(desc_ru)}">
  <meta property="og:title" content="{esc(title_ru)} — IT Movies">
  <meta property="og:description" content="{esc(desc_ru)}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:locale:alternate" content="en_US">
  <meta property="og:url" content="{page_url}">
  <meta property="og:site_name" content="IT Movies">
  <meta property="og:image" content="{poster_abs}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{poster_abs}">
  <link rel="canonical" href="{page_url}">
  <meta name="theme-color" content="#f4f3ef">
{preload_poster}{THEME_SCRIPT}
  <link rel="manifest" href="../../static/site.webmanifest">
  <link rel="icon" href="../../static/favicons/favicon.ico" sizes="48x48">
  <link rel="icon" type="image/png" sizes="16x16" href="../../static/favicons/favicon-16x16.png">
  <link rel="icon" type="image/png" sizes="32x32" href="../../static/favicons/favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="48x48" href="../../static/favicons/favicon-48x48.png">
  <link rel="icon" type="image/png" sizes="64x64" href="../../static/favicons/favicon-64x64.png">
  <link rel="icon" type="image/png" sizes="128x128" href="../../static/favicons/favicon-128x128.png">
  <link rel="icon" type="image/png" sizes="256x256" href="../../static/favicons/favicon-256x256.png">
  <link rel="apple-touch-icon" sizes="57x57" href="../../static/favicons/apple-touch-icon-57x57.png">
  <link rel="apple-touch-icon" sizes="114x114" href="../../static/favicons/apple-touch-icon-114x114.png">
  <link rel="apple-touch-icon" sizes="120x120" href="../../static/favicons/apple-touch-icon-120x120.png">
  <link rel="apple-touch-icon" href="../../static/favicons/apple-touch-icon.png">
  <meta name="msapplication-TileColor" content="#f4f3ef">
  <link rel="stylesheet" href="../../css/style.css">
  <link rel="preload" href="../../static/fonts/roboto-cyrillic.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="preload" href="../../static/fonts/roboto-latin.woff2" as="font" type="font/woff2" crossorigin>
  <script type="application/ld+json">{json_ld}</script>
{METRIKA_SCRIPT}
</head>
<body>
  <div id="app">
    <noscript>
      <header class="top">
        <div class="brand">
          <div class="logo">
            <a href="../../"><img src="../../static/logo.webp" alt="IT Movies" width="100" height="100"></a>
          </div>
          <div class="brand-text">
            <h1>{esc(title_ru)}</h1>
            <p>{esc(title_en)}</p>
          </div>
        </div>
      </header>
      <main>
        <article class="film-main">
{noscript_poster}          <div class="film-info">
            <p class="meta-row">{esc(type_label)} · {esc(str(item["year"]))} · {esc(genre_list)}</p>
            <p class="film-desc">{esc(desc_ru)}</p>
            <p class="film-desc film-desc-alt">{esc(desc_en)}</p>
{rat_tiles}            <p class="btn-back"><a href="../../">← Вернуться в каталог IT Movies</a></p>
          </div>
        </article>
        <section class="related">
          <h2>Похожее в каталоге</h2>
          <ul>
{related_items}          </ul>
        </section>
      </main>
      <footer>
        <span>Сделано с</span><span class="heart"> ♥ </span><a href="https://t.me/wh_lab" target="_blank" rel="noopener">Exited3n</a>
      </footer>
    </noscript>
  </div>

  <script>window.FILM_PAGE = {page_data};</script>
  <script src="../../js/vue.global.prod.js" defer></script>
  <script src="../../js/i18n.min.js" defer></script>
  <script src="../../js/common.min.js" defer></script>
  <script src="../../js/film.min.js" defer></script>
</body>
</html>
"""

def main():
    derived = [
        ("js/catalog.js", catalog_js(catalog)),
    ] + [
        ("js/" + name.replace(".js", ".min.js"), minify_js((ROOT / "js" / name).read_text(encoding="utf-8")))
        for name in ("i18n.js", "common.js", "app.js", "film.js")
    ]
    for rel, content in derived:
        target = ROOT / rel
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
            print(f"{rel}: generated")
        else:
            print(f"{rel}: up to date")

    written = 0
    for item in catalog:
        rel = related_to(item, catalog)
        html_out = render(item, rel)
        out_dir = OUT / item_slug(item)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "index.html"
        if not target.exists() or target.read_text(encoding="utf-8") != html_out:
            target.write_text(html_out, encoding="utf-8")
            written += 1

    desired = {item_slug(item) for item in catalog}
    stale = [d for d in OUT.iterdir() if d.is_dir() and d.name not in desired]
    for d in stale:
        shutil.rmtree(d, ignore_errors=True)
    film_note = f"Film pages: {len(catalog)} total, {written} written/updated, {len(stale)} stale dirs removed"
    print(film_note)

    index_path = ROOT / "index.html"
    if index_path.exists():
        idx_src = index_path.read_text(encoding="utf-8")
        idx_new = inject_metrika(inject_noscript(inject_ld(inject_theme(idx_src), catalog), catalog))
        if idx_new != idx_src:
            index_path.write_text(idx_new, encoding="utf-8")
            print("index.html: theme + JSON-LD + noscript + metrika blocks updated")
        else:
            print("index.html: up to date")
    else:
        print("index.html: not found, skipped")

    nf_path = ROOT / "404.html"
    if nf_path.exists():
        nf_src = nf_path.read_text(encoding="utf-8")
        nf_new = inject_metrika(inject_theme(nf_src))
        if nf_new != nf_src:
            nf_path.write_text(nf_new, encoding="utf-8")
            print("404.html: theme + metrika blocks updated")
        else:
            print("404.html: up to date")
    else:
        print("404.html: not found, skipped")

if __name__ == "__main__":
    main()