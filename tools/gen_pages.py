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
import subprocess
import sys

from datetime import datetime

from lib import ROOT, SITE_BASE, load_catalog, make_slug, item_slug, ru_genres, has_rating, fmt_rating, webp_size

sys.stdout.reconfigure(encoding="utf-8")

OUT = ROOT / "films"
TYPE_LABELS = {"movie": "Фильм", "series": "Сериал", "documentary": "Документальный"}

catalog = load_catalog()

RU_GENRES = ru_genres()


def catalog_git_date():
    try:
        shallow = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        ).stdout.strip()
        if shallow != "true":
            out = subprocess.run(
                ["git", "log", "-1", "--format=%cs", "--", "js/data.js"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            ).stdout.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", out):
                return out
    except (OSError, subprocess.SubprocessError):
        pass
    sitemap = ROOT / "sitemap.xml"
    if sitemap.exists():
        dates = re.findall(
            r"<lastmod>(\d{4}-\d{2}-\d{2})</lastmod>",
            sitemap.read_text(encoding="utf-8", errors="replace"),
        )
        if dates:
            return max(dates)
    return datetime.fromtimestamp((ROOT / "js" / "data.js").stat().st_mtime).date().isoformat()


CATALOG_DATE = catalog_git_date()

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
      var t, src = "system";
      try { t = new URLSearchParams(location.search).get("theme"); } catch (e) {}
      if (t === "dark" || t === "light") {
        src = "url";
      } else {
        try { t = localStorage.getItem("it-movies-theme"); } catch (e) { t = null; }
        if (t === "dark" || t === "light") {
          src = "store";
        } else {
          t = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
        }
      }
      document.documentElement.classList.add(t);
      var m = document.querySelector('meta[name="color-scheme"]');
      if (m) m.setAttribute("content", src === "system" ? "light dark" : t);
    })();
  </script>"""

THEME_MARK = ("<!-- begin:theme-script -->", "<!-- end:theme-script -->")
NSCRIPT_MARK = ("<!-- begin:catalog-noscript -->", "<!-- end:catalog-noscript -->")
LD_MARK = ("<!-- begin:index-ld -->", "<!-- end:index-ld -->")
METRIKA_MARK = ("<!-- begin:metrika -->", "<!-- end:metrika -->")

METRIKA_ID = "112571181"
METRIKA_SCRIPT = """  <!-- Yandex.Metrika counter --> <script type="text/javascript">     (function() {         var q = false;         function go() {             if (q) { return; }             q = true;             (function(m,e,t,r,i,k,a){                 m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};                 m[i].l=1*new Date();                 for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}                 k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)             })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id={id}', 'ym');             ym({id}, 'init', {ssr:true, clickmap:true, referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});         }         if (document.readyState === "complete") {             go();         } else {             window.addEventListener("load", go);             setTimeout(go, 3000);         }     })(); </script> <noscript><div><img src="https://mc.yandex.ru/watch/{id}" style="position:absolute; left:-9999px;" alt="" /></div></noscript> <!-- /Yandex.Metrika counter -->""".replace("{id}", METRIKA_ID)


def seo_desc(text):
    return _seo_desc(text).rstrip(" \t,;:…–—")


def _seo_desc(text):
    text = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    acc = ""
    for s in sentences:
        cand = s if not acc else acc + " " + s
        if len(cand) > 160:
            break
        acc = cand
        if len(acc) >= 120:
            return acc
    if len(acc) >= 120:
        return acc
    words = text.split(" ")
    acc = ""
    for w in words:
        cand = w if not acc else acc + " " + w
        if len(cand) > 160:
            break
        acc = cand
    if len(acc) >= 120:
        return acc
    acc = ""
    for w in words:
        acc = w if not acc else acc + " " + w
        if len(acc) >= 120:
            return acc
    return text


POSTER_SIZES = "(max-width: 720px) 92vw, 300px"


def index_ld_json(catalog):
    base = SITE_BASE + "/"
    items = []
    for i, item in enumerate(catalog):
        url = base + "films/" + item_slug(item) + "/"
        entry = {
            "@type": "TVSeries" if item["type"] == "series" else "Movie",
            "position": i + 1,
            "name": item["titleRu"],
            "alternateName": item["titleEn"],
            "url": url,
            "@id": url,
        }
        if item.get("poster"):
            entry["image"] = f"{SITE_BASE}/{item['poster'].lstrip('/')}"
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
            "@type": "Organization",
            "@id": base + "#organization",
            "name": "IT Movies",
            "url": base,
            "logo": base + "static/logo.webp",
        },
        {
            "@type": "WebPage",
            "@id": base + "#webpage",
            "url": base,
            "name": "IT Movies",
            "inLanguage": ["ru", "en"],
            "isPartOf": {"@id": base},
            "mainEntity": {"@id": base + "#catalog"},
            "publisher": {"@id": base + "#organization"},
        },
        {
            "@type": "ItemList",
            "@id": base + "#catalog",
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
    slim = []
    for item in catalog:
        entry = {k: v for k, v in item.items() if k != "desc"}
        poster = (item.get("poster") or "").lstrip("/")
        if poster:
            poster400 = poster[: -len(".webp")] + "_400.webp"
            dims = webp_size(ROOT / poster400) or webp_size(ROOT / poster)
            if dims:
                entry["poster400"] = poster400
                entry["posterW"] = dims[0]
                entry["posterH"] = dims[1]
        slim.append(entry)
    return slim


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


def generate_webmanifest():
    """static/site.webmanifest — generated from SITE_BASE (single source)."""
    return (
        '{\n'
        '  "name": "IT Movies",\n'
        '  "short_name": "IT Movies",\n'
        '  "start_url": "/IT_movies/",\n'
        '  "display": "standalone",\n'
        '  "background_color": "#eef1f6",\n'
        '  "theme_color": "#eef1f6",\n'
        '  "description": "Каталог фильмов и сериалов о компьютерах, технологиях и ИИ",\n'
        '  "icons": [\n'
        '    { "src": "favicons/favicon-16x16.png", "sizes": "16x16", "type": "image/png" },\n'
        '    { "src": "favicons/favicon-32x32.png", "sizes": "32x32", "type": "image/png" },\n'
        '    { "src": "favicons/favicon-48x48.png", "sizes": "48x48", "type": "image/png" },\n'
        '    { "src": "favicons/favicon-64x64.png", "sizes": "64x64", "type": "image/png" },\n'
        '    { "src": "favicons/favicon-128x128.png", "sizes": "128x128", "type": "image/png" },\n'
        '    { "src": "favicons/favicon-256x256.png", "sizes": "256x256", "type": "image/png" },\n'
        '    { "src": "favicons/favicon-512x512.png", "sizes": "512x512", "type": "image/png" }\n'
        '  ]\n'
        '}\n'
    )


def generate_robots_txt():
    """robots.txt with the Sitemap link from SITE_BASE."""
    return (
        "User-agent: *\n"
        "Allow: /\n"
        f"\nSitemap: {SITE_BASE}/sitemap.xml\n"
    )


def generate_sitemap(catalog):
    """sitemap.xml with changefreq and priority (no hreflang: language is client-side, no separate EN URLs)."""
    slugs_sorted = sorted(item_slug(item) for item in catalog)
    film_urls = "".join(
        "  <url>\n"
        f"    <loc>{SITE_BASE}/films/{slug}/</loc>\n"
        f"    <lastmod>{CATALOG_DATE}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.7</priority>\n"
        "  </url>\n"
        for slug in slugs_sorted
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        f"    <loc>{SITE_BASE}/</loc>\n"
        f"    <lastmod>{CATALOG_DATE}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{SITE_BASE}/privacy.html</loc>\n"
        f"    <lastmod>{CATALOG_DATE}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.3</priority>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{SITE_BASE}/about.html</loc>\n"
        f"    <lastmod>{CATALOG_DATE}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.5</priority>\n"
        "  </url>\n"
        + film_urls
        + "</urlset>\n"
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
        out.append(f'        <h2>{label}</h2>\n        <ul>\n{lis}        </ul>\n')
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


LASTUPD_MARK = ("<!-- begin:last-updated -->", "<!-- end:last-updated -->")


def last_updated_block():
    human_date = f"{CATALOG_DATE[8:10]}.{CATALOG_DATE[5:7]}.{CATALOG_DATE[:4]}"
    return (
        f'\n        <span> · </span><span class="last-updated">{{{{ t.lastUpdated }}}}'
        f'<time datetime="{CATALOG_DATE}">{human_date}</time></span>\n        '
    )


def inject_last_updated(src):
    n = src.count(LASTUPD_MARK[0]) + src.count(LASTUPD_MARK[1])
    if n != 2:
        raise SystemExit(f"last-updated markers ({n}/2) not found in index.html")
    return re.sub(
        re.escape(LASTUPD_MARK[0]) + r".*?" + re.escape(LASTUPD_MARK[1]),
        LASTUPD_MARK[0] + last_updated_block() + LASTUPD_MARK[1],
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
        "@id": page_url,
        "inLanguage": "ru",
        "description": desc_ru,
        "datePublished": str(item["year"]),
        "dateModified": CATALOG_DATE,
        "genre": genres_ru,
        "sameAs": [],
    }
    if item.get("imdbId"):
        movie["sameAs"].append(f"https://www.imdb.com/title/{item['imdbId']}/")
    movie["sameAs"].append(f"https://www.kinopoisk.ru/film/{item['kpId']}/")
    if poster:
        movie["image"] = f"{SITE_BASE}/{poster}"
    cr, cv = None, None
    if has_rating(item.get("kpRating")) and item.get("kpVotes"):
        cr, cv = float(item["kpRating"]), int(item["kpVotes"])
    elif has_rating(item.get("imdbRating")) and item.get("imdbVotes"):
        cr, cv = float(item["imdbRating"]), int(item["imdbVotes"])
    if cr is not None and cv is not None:
        movie["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": cr,
            "ratingCount": cv,
            "bestRating": 10,
            "worstRating": 1,
        }
    graph.append(movie)

    graph.append({
        "@type": "BreadcrumbList",
        "@id": page_url + "#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "IT Movies", "item": home_url},
            {"@type": "ListItem", "position": 2, "name": title_ru, "item": page_url},
        ],
    })

    if related:
        graph.append({
            "@type": "ItemList",
            "@id": page_url + "#related",
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

    SLIM_KEYS = ("type", "titleEn", "titleRu", "imdbId", "kpId")
    page_data = json.dumps(
        {
            "item": {**item, "descSeo": {"ru": seo_desc(desc_ru), "en": seo_desc(desc_en)}},
            "related": [{k: r[k] for k in SLIM_KEYS if k in r} for r in related],
            "posterW": poster_dims[0] if poster_dims else None,
            "posterH": poster_dims[1] if poster_dims else None,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")

    poster_abs = f"{SITE_BASE}/{poster}" if poster else f"{SITE_BASE}/static/ogimage.webp"

    preload_poster = ""
    if poster:
        preload_attrs = ""
        if poster_dims:
            v400 = poster[: -len(".webp")] + "_400.webp"
            preload_attrs = (
                f' imagesrcset="../../{v400} 400w, ../../{poster} {poster_dims[0]}w"'
                f' imagesizes="{POSTER_SIZES}"'
            )
        preload_poster = (
            f'  <link rel="preload" as="image" href="../../{poster}"'
            f'{preload_attrs} fetchpriority="high">\n'
        )

    noscript_poster = ""
    if poster:
        dims = f' width="{poster_dims[0]}" height="{poster_dims[1]}"' if poster_dims else ""
        srcset_attr = ""
        if poster_dims:
            v400 = poster[: -len(".webp")] + "_400.webp"
            srcset_attr = (
                f' srcset="../../{v400} 400w, ../../{poster} {poster_dims[0]}w"'
                f' sizes="{POSTER_SIZES}"'
            )
        noscript_poster = (
            f'      <figure class="film-poster">\n'
            f'        <img src="../../{poster}"{srcset_attr} alt="{esc(title_ru)}"{dims} decoding="async">\n'
            "      </figure>\n"
        )

    related_items = "".join(
        f'        <li><a href="../{item_slug(r)}/">{esc(r["titleRu"])}</a></li>\n'
        for r in related
    )

    rat_tiles = (
        f'        <div class="ratings">\n'
        f'          <a class="kp" href="https://www.kinopoisk.ru/film/{item["kpId"]}/" target="_blank" rel="noopener noreferrer">Кинопоиск: {esc(fmt_rating(item.get("kpRating")))}{esc(star(item.get("kpRating")))}</a>\n'
    )
    if item.get("imdbId"):
        rat_tiles += (
            f'          <a class="imdb" href="https://www.imdb.com/title/{item["imdbId"]}/" target="_blank" rel="noopener noreferrer">IMDb: {esc(fmt_rating(item.get("imdbRating")))}{esc(star(item.get("imdbRating")))}</a>\n'
        )
    rat_tiles += "        </div>\n"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title_ru)} ({item["year"]}) — IT Movies</title>
  <meta name="description" content="{esc(seo_desc(desc_ru))}">
  <meta property="og:title" content="{esc(title_ru)} ({item["year"]}) — IT Movies">
  <meta property="og:description" content="{esc(seo_desc(desc_ru))}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:locale:alternate" content="en_US">
  <meta property="og:url" content="{page_url}">
  <meta property="og:site_name" content="IT Movies">
  <meta property="og:image" content="{poster_abs}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{poster_abs}">
  <link rel="canonical" href="{page_url}">
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" content="#eef1f6">
  <meta name="theme-color" content="#171b2d" media="(prefers-color-scheme: dark)">
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
  <meta name="msapplication-TileColor" content="#eef1f6">
  <link rel="stylesheet" href="../../css/style.css">
  <link rel="preload" href="../../static/fonts/ubuntu-cyrillic-400-normal.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="preload" href="../../static/fonts/ubuntu-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
  <script type="application/ld+json">{json_ld}</script>
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
        <nav class="breadcrumb" aria-label="Главная">
          <a href="../../">Главная</a><span class="bc-sep"> › </span><span class="bc-current">{esc(title_ru)}</span>
        </nav>
        <article class="film-main">
{noscript_poster}          <div class="film-info">
            <p class="meta-row">{esc(type_label)} · {esc(str(item["year"]))} · {esc(genre_list)}</p>
            <p class="film-desc">{esc(desc_ru)}</p>
            <p class="film-desc film-desc-alt">{esc(desc_en)}</p>
{rat_tiles}          </div>
        </article>
        <section class="related">
          <h2>Похожее в каталоге</h2>
          <ul>
{related_items}          </ul>
        </section>
        <p class="back-catalog"><a href="../../">← Вернуться на главную</a></p>
      </main>
      <footer>
        <div class="footer-line">
          <span>Сделано с</span><span class="heart"> ♥ </span><a href="https://t.me/wh_lab" target="_blank" rel="noopener noreferrer">Exited3n</a>
        </div>
        <div class="footer-line">
          <a class="footer-privacy" href="../../privacy.html">Политика конфиденциальности</a>
        </div>
      </footer>
    </noscript>
  </div>

  <script>window.FILM_PAGE = {page_data};</script>
  <script src="../../js/vue.global.prod.js" defer></script>
  <script src="../../js/i18n.min.js" defer></script>
  <script src="../../js/common.min.js" defer></script>
  <script src="../../js/film.min.js" defer></script>
{METRIKA_SCRIPT}
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

    # Static config files: generated from SITE_BASE (single source)
    webmanifest = ROOT / "static" / "site.webmanifest"
    webmanifest_data = generate_webmanifest()
    if not webmanifest.exists() or webmanifest.read_text(encoding="utf-8") != webmanifest_data:
        webmanifest.write_text(webmanifest_data, encoding="utf-8")
        print("static/site.webmanifest: generated")
    else:
        print("static/site.webmanifest: up to date")

    robots_txt = ROOT / "robots.txt"
    robots_data = generate_robots_txt()
    if not robots_txt.exists() or robots_txt.read_text(encoding="utf-8") != robots_data:
        robots_txt.write_text(robots_data, encoding="utf-8")
        print("robots.txt: generated")
    else:
        print("robots.txt: up to date")

    sitemap = ROOT / "sitemap.xml"
    sitemap_data = generate_sitemap(catalog)
    if not sitemap.exists() or sitemap.read_text(encoding="utf-8") != sitemap_data:
        sitemap.write_text(sitemap_data, encoding="utf-8")
        print("sitemap.xml: generated")
    else:
        print("sitemap.xml: up to date")

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
        idx_new = inject_metrika(inject_last_updated(inject_noscript(inject_ld(inject_theme(idx_src), catalog), catalog)))
        if idx_new != idx_src:
            index_path.write_text(idx_new, encoding="utf-8")
            print("index.html: theme + JSON-LD + noscript + last-updated + metrika blocks updated")
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

    priv_path = ROOT / "privacy.html"
    if priv_path.exists():
        priv_src = priv_path.read_text(encoding="utf-8")
        priv_new = inject_metrika(inject_theme(priv_src))
        if priv_new != priv_src:
            priv_path.write_text(priv_new, encoding="utf-8")
            print("privacy.html: theme + metrika blocks updated")
        else:
            print("privacy.html: up to date")
    else:
        print("privacy.html: not found, skipped")

    about_path = ROOT / "about.html"
    if about_path.exists():
        about_src = about_path.read_text(encoding="utf-8")
        about_new = inject_metrika(inject_theme(about_src))
        if about_new != about_src:
            about_path.write_text(about_new, encoding="utf-8")
            print("about.html: theme + metrika blocks updated")
        else:
            print("about.html: up to date")
    else:
        print("about.html: not found, skipped")

if __name__ == "__main__":
    main()