#!/usr/bin/env python3
"""Generate a static SEO page per catalog record into films/<slug>/index.html.

Each page shares the look of the main page (css/style.css) and is rendered
by the shared Vue app in js/film.js. A <noscript> block keeps key content
visible to crawlers without JS. JSON-LD and meta are emitted statically.
"""
import hashlib
import html
import json
import random
import re
import shutil
import subprocess
import sys

from datetime import datetime

from lib import ROOT, SITE_BASE, POSTER_VARIANT_WIDTHS, load_catalog, make_slug, item_slug, ru_genres, has_rating, fmt_rating, variant_name, webp_size, poster_sizes

sys.stdout.reconfigure(encoding="utf-8")

OUT = ROOT / "films"

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

def _scored_candidates(item, catalog):
    gs = set(item["genres"])
    is_doc = item.get("type") == "documentary"
    slug = item_slug(item)
    return sorted(
        (
            (sum(1 for g in other["genres"] if g in gs), other)
            for other in catalog
            if item_slug(other) != slug and (is_doc or other.get("type") != "documentary")
        ),
        key=lambda t: t[0],
        reverse=True,
    )

def _related_seed(item):
    digest = hashlib.sha256(item_slug(item).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def related_to(item, catalog, n=4):
    want = max(n, 1)
    pool = related_pool(item, catalog)
    if not pool:
        return []
    genres = set(item.get("genres", []))
    bands = {}
    for other in pool:
        overlap = len(genres & set(other.get("genres", [])))
        bands.setdefault(overlap, []).append(other)
    rng = random.Random(_related_seed(item))
    picked = []
    for score in sorted(bands, reverse=True):
        band = bands[score]
        rng.shuffle(band)
        picked += band[: want - len(picked)]
        if len(picked) >= want:
            break
    return picked[:want]

def related_pool(item, catalog, cap=16, min_n=6):
    scored = _scored_candidates(item, catalog)
    pool = [other for score, other in scored if score > 0][:cap]
    if len(pool) >= min_n:
        return pool
    rest = [other for score, other in scored if score == 0]
    return (pool + rest)[: max(min_n, 1)]

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


POSTER_SIZES = poster_sizes()
FILMS_PREFIX = "../../"


def poster_candidates(poster, prefix, single=False, widths=None):
    """srcset candidates for a poster, each carrying its own measured width.

    `widths` selects which ladder rungs to offer, and each one is named and
    described by the file that is actually on disk, never by the rung's nominal
    width -- that is the bug Stage 0 fixed on the full-poster path and the same
    rule applies to a variant. A rung whose file is missing or whose measured
    width is not the rung's is dropped here and reported by verify.py, so a
    partial ladder cannot produce a srcset that lies about what it offers.

    `single=True` omits the full poster, which is what the related card wants:
    its 96px box never selects a file wider than the 400w variant. The full
    poster is only offered when its own width differs from the last rung's,
    because two candidates on the same width descriptor make the srcset invalid.
    """
    if widths is None:
        widths = POSTER_VARIANT_WIDTHS[-1:]
    candidates = []
    last = None
    for width in widths:
        name = variant_name(poster, width)
        dims = webp_size(ROOT / name)
        if dims and dims[0] == width:
            candidates.append(f"{prefix}{name} {dims[0]}w")
            last = dims[0]
    if single:
        return candidates
    full = webp_size(ROOT / poster)
    if full and full[0] != last:
        candidates.append(f"{prefix}{poster} {full[0]}w")
    return candidates


def poster_srcset_attr(poster, sizes, prefix, single=False):
    candidates = poster_candidates(poster, prefix, single)
    if not candidates:
        return ""
    return ' srcset="%s" sizes="%s"' % (", ".join(candidates), sizes)


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
        '  "background_color": "#F4F2ED",\n'
        '  "theme_color": "#F4F2ED",\n'
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


# The related card has ONE hand-maintained source: the Vue fragment below.
# js/film.js receives it verbatim as window.FILM_RC_CARD and splices it into its
# own template, so the client keeps owning every value it displays -- what
# crosses into the page is a template with Vue bindings in it, never
# interpolated text. The no-JS card all 154 film pages ship is the same
# fragment with every expression resolved from RC_STATIC, which is keyed by the
# exact expression text: an expression the table does not know, or a table
# entry the fragment no longer uses, stops the generator instead of letting the
# two renderings drift apart in silence.
RC_CARD = """<a class="rc" :href="'../' + itemSlug(r) + '/'">
  <img v-if="relatedPoster(r)" class="rc-poster" :src="relatedPoster(r)" :srcset="relatedPosterSrcset(r)" sizes="104px" alt="" width="120" height="180" loading="lazy" decoding="async">
  <span class="rc-content">
    <span class="rc-head">
      <span class="rc-title">{{ relatedTitle(r) }}</span>
    </span>
    <span class="rc-info">{{ relatedInfo(r) }}</span>
    <span class="rc-meta">
      <span class="rc-rating kp" v-if="hasRating(r.kpRating)">{{ t.kpShort }} {{ formatRating(r.kpRating) }}</span>
      <span class="rc-rating imdb" v-if="r.imdbId && hasRating(r.imdbRating)">{{ t.imdb }} {{ formatRating(r.imdbRating) }}</span>
    </span>
  </span>
</a>"""

RC_VOID_TAGS = frozenset((
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
))
RC_TAG_RE = re.compile(r"""<(/?)([a-zA-Z][^\s/>]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(/?)>""")
RC_ATTR_RE = re.compile(r"""([^\s=/>]+)(?:\s*=\s*"([^"]*)")?""")
RC_MUSTACHE_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}")


def rc_attrs(raw):
    return RC_ATTR_RE.findall(raw)


def rc_operands(expr):
    return [part.strip() for part in expr.split("&&")]


def rc_expressions(fragment):
    """Every Vue expression the fragment binds, with && compounds split into
    their operands so the set can be compared with RC_STATIC's keys."""
    found = set()
    for m in RC_TAG_RE.finditer(fragment):
        for name, value in rc_attrs(m.group(3)):
            if value is not None and (name == "v-if" or name.startswith(":")):
                found.update(rc_operands(value))
    for m in RC_MUSTACHE_RE.finditer(fragment):
        found.update(rc_operands(m.group(1)))
    return found


RC_EXPRESSIONS = rc_expressions(RC_CARD)


def rc_value(expr, values):
    parts = rc_operands(expr)
    if len(parts) > 1:
        return all(rc_value(part, values) for part in parts)
    if expr not in values:
        raise SystemExit(
            f"related card: RC_CARD binds {expr!r} and RC_STATIC has no static value "
            f"for it, so the no-JS card cannot be rendered from the one source. Add "
            f"the value it stands for, or drop the binding -- do not let one "
            f"rendering fall back to a value of its own"
        )
    return values[expr]


def rc_matching_close(fragment, pos, name):
    """Index just past the tag closing <name>, or None if it never closes."""
    depth = 1
    for m in RC_TAG_RE.finditer(fragment, pos):
        closing, tag, _, selfclose = m.groups()
        if closing:
            depth -= 1
            if depth == 0:
                return m.end()
        elif not selfclose and tag.lower() not in RC_VOID_TAGS:
            depth += 1
    return None


def rc_interpolate(text, values):
    return RC_MUSTACHE_RE.sub(lambda m: esc(rc_value(m.group(1), values)), text)


def rc_render_tag(tag, attrs, values):
    parts = []
    for name, value in attrs:
        if name == "v-if":
            continue
        if value is None:
            parts.append(name)
        elif name.startswith(":"):
            parts.append(f'{name[1:]}="{esc(rc_value(value, values))}"')
        else:
            parts.append(f'{name}="{value}"')
    name = RC_TAG_RE.match(tag).group(2)
    return f"<{name} " + " ".join(parts) + ">"


def rc_values(r):
    """The values one no-JS related card binds, keyed by the Vue expression the
    client binds in the same place. The page is lang="ru" and static, so a
    title is the Russian one and a label is the Russian one; the client
    resolves the same bindings against I18N[lang] and the current language."""
    poster = (r.get("poster") or "").lstrip("/")
    genres = " / ".join(sorted(RU_GENRES.get(g, g) for g in r.get("genres", [])))
    values = {
        "'../' + itemSlug(r) + '/'": f"../{item_slug(r)}/",
        "relatedPoster(r)": f"{FILMS_PREFIX}{poster}" if poster else "",
        "relatedPosterSrcset(r)": ", ".join(
            poster_candidates(poster, FILMS_PREFIX, single=True,
                              widths=POSTER_VARIANT_WIDTHS)
        ),
        "relatedTitle(r)": r["titleRu"],
        "relatedInfo(r)": " · ".join(
            p for p in (genres, str(r.get("year") or "")) if p
        ),
        "hasRating(r.kpRating)": has_rating(r.get("kpRating")),
        "r.imdbId": bool(r.get("imdbId")),
        "hasRating(r.imdbRating)": has_rating(r.get("imdbRating")),
        "t.kpShort": "КП",
        "formatRating(r.kpRating)": fmt_rating(r.get("kpRating")),
        "t.imdb": "IMDb",
        "formatRating(r.imdbRating)": fmt_rating(r.get("imdbRating")),
    }
    if set(values) != RC_EXPRESSIONS:
        unknown = sorted(RC_EXPRESSIONS - set(values))
        unused = sorted(set(values) - RC_EXPRESSIONS)
        raise SystemExit(
            f"related card: RC_CARD and RC_STATIC disagree. RC_CARD binds nothing "
            f"for {unknown}; RC_STATIC carries {unused}, which RC_CARD no longer "
            f"binds. The card has one source, so this is a generation error, not a "
            f"warning"
        )
    return values


def rc_card_html(r):
    """RC_CARD with every binding resolved to its no-JS value and every element "
    "whose v-if is false dropped with its subtree."""
    values = rc_values(r)
    out = []
    pos = 0
    for m in RC_TAG_RE.finditer(RC_CARD):
        closing, name, raw, selfclose = m.groups()
        if not closing:
            out.append(rc_interpolate(RC_CARD[pos:m.start()], values))
            attrs = rc_attrs(raw)
            cond = next((v for k, v in attrs if k == "v-if"), None)
            if cond is not None and not rc_value(cond, values):
                if name.lower() in RC_VOID_TAGS or selfclose:
                    pos = m.end()
                    continue
                end = rc_matching_close(RC_CARD, m.end(), name)
                if end is None:
                    raise SystemExit(
                        f"related card: <{name} v-if=\"{cond}\"> in RC_CARD is never "
                        f"closed, so the no-JS card could not be cut out of it"
                    )
                pos = end
                continue
            out.append(rc_render_tag(m.group(0), attrs, values))
        else:
            out.append(rc_interpolate(RC_CARD[pos:m.start()], values))
            out.append(m.group(0))
        pos = m.end()
    out.append(rc_interpolate(RC_CARD[pos:], values))
    return "".join(out)


def rc_cards_html(related):
    lis = []
    for r in related:
        lines = rc_card_html(r).split("\n")
        lis.append(
            '        <li>' + lines[0]
            + "".join("\n          " + line for line in lines[1:])
            + "</li>\n"
        )
    return "".join(lis)


def render(item, related):
    slug = item_slug(item)
    page_url = f"{SITE_BASE}/films/{slug}/"
    home_url = f"{SITE_BASE}/"
    title_ru = item["titleRu"]
    title_en = item["titleEn"]
    desc_ru = item["desc"]["ru"]
    desc_en = item["desc"]["en"]
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

    SLIM_KEYS = (
        "type",
        "titleEn",
        "titleRu",
        "imdbId",
        "kpId",
        "year",
        "genres",
        "kpRating",
        "imdbRating",
        "fav",
        "poster",
        "poster400",
        "posterW",
        "posterH",
    )
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
            candidates = poster_candidates(poster, FILMS_PREFIX)
            if candidates:
                preload_attrs = (
                    f' imagesrcset="{", ".join(candidates)}"'
                    f' imagesizes="{POSTER_SIZES}"'
                )
        preload_poster = (
            f'  <link rel="preload" as="image" href="../../{poster}"'
            f'{preload_attrs} fetchpriority="high">\n'
        )

    fav_badge = (
        '\n            <span class="film-badge">Выбор автора</span>'
        if item.get("fav")
        else ""
    )

    # The client hides the alt line when the two titles are identical; the no-JS
    # card must agree, or 9 documentaries print their title twice.
    noscript_alt = (
        f'            <p class="film-alt">{esc(title_en)}</p>\n'
        if title_en and title_en != title_ru
        else ""
    )

    noscript_poster = ""
    if poster:
        dims = f' width="{poster_dims[0]}" height="{poster_dims[1]}"' if poster_dims else ""
        srcset_attr = poster_srcset_attr(poster, POSTER_SIZES, FILMS_PREFIX)
        noscript_poster = (
            f'      <figure class="film-poster">\n'
            f'        <img src="../../{poster}"{srcset_attr} alt="{esc(title_ru)}"{dims} decoding="async">'
            f'{fav_badge}\n'
            "      </figure>\n"
        )

    related_items = rc_cards_html(related)
    rc_card_js = json.dumps(RC_CARD, ensure_ascii=False).replace("<", "\\u003c")

    rat_tiles = (
        f'        <div class="ratings">\n'
        f'          <a class="kp rating-chip rating-chip--kp" href="https://www.kinopoisk.ru/film/{item["kpId"]}/" target="_blank" rel="noopener noreferrer">Кинопоиск: {esc(fmt_rating(item.get("kpRating")))}{esc(star(item.get("kpRating")))}</a>\n'
    )
    if item.get("imdbId"):
        rat_tiles += (
            f'          <a class="imdb rating-chip rating-chip--imdb" href="https://www.imdb.com/title/{item["imdbId"]}/" target="_blank" rel="noopener noreferrer">IMDb: {esc(fmt_rating(item.get("imdbRating")))}{esc(star(item.get("imdbRating")))}</a>\n'
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
  <meta name="theme-color" content="#F4F2ED">
  <meta name="theme-color" content="#14120F" media="(prefers-color-scheme: dark)">
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
  <meta name="msapplication-TileColor" content="#F4F2ED">
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
            <div class="brand-name">IT Movies</div>
            <p>Подборка фильмов и сериалов о компьютерах, технологиях, ИИ и т.д.</p>
          </div>
        </div>
      </header>
      <main>
        <nav class="breadcrumb" aria-label="Главная">
          <a href="../../">Главная</a><span class="bc-sep"> › </span><span class="bc-current"><span class="bc-type">{esc(title_ru)}</span></span>
        </nav>
        <article class="film-main">
{noscript_poster}          <div class="film-info">
            <h1 class="film-title">{esc(title_ru)}</h1>
{noscript_alt}            <div class="film-meta">
              <span class="film-meta-item">{esc(str(item["year"]))}</span>
              <span class="film-meta-item">{esc(genre_list)}</span>
            </div>
{rat_tiles}            <p class="film-desc">{esc(desc_ru)}</p>
            <details class="film-desc-alt-wrap">
              <summary>Описание на английском</summary>
              <p class="film-desc film-desc-alt">{esc(desc_en)}</p>
            </details>
          </div>
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
  <script>window.FILM_RC_CARD = {rc_card_js};</script>
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
        for name in ("i18n.js", "common.js", "app.js", "film.js", "about.js")
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