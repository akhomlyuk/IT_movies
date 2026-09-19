#!/usr/bin/env python3
"""Standalone data integrity and reference check for the IT Movies project."""
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

import gen_pages
from lib import ROOT, SITE_BASE, make_slug, item_slug, load_catalog, known_genres

sys.stdout.reconfigure(encoding="utf-8")
errors = []
NO_WRITE = "--no-write" in sys.argv

# 1. Parse data.js as JSON (array between the first '[' and last ']')
raw = (ROOT / "js" / "data.js").read_text(encoding="utf-8")
catalog = load_catalog()

types = {}
for item in catalog:
    types[item["type"]] = types.get(item["type"], 0) + 1
print(f"Total records: {len(catalog)}; by type: {types}")

# 2. Duplicate imdbId/kpId
for key in ("imdbId", "kpId"):
    seen = {}
    for item in catalog:
        v = item.get(key)
        if v is None:
            continue
        if v in seen:
            errors.append(f"Duplicate {key}={v}: {seen[v]} and {item['titleEn']}")
        seen[v] = item["titleEn"]

# 3. Whitespace in titles
for item in catalog:
    for f in ("titleEn", "titleRu"):
        if item.get(f) and item[f] != item[f].strip():
            errors.append(f"Whitespace in {f}: {item['titleEn']!r}")

# 3b. titleEn must be Latin script only (AGENTS.md contract)
def is_latin_script(text):
    return all(
        ord(ch) < 128 or "LATIN" in unicodedata.name(ch, "") for ch in text
    )

for item in catalog:
    if not is_latin_script(item.get("titleEn", "")):
        errors.append(f"titleEn is not Latin script: {item['titleEn']!r} ({item['titleRu']})")

# 3c. IDs: at least one must be present and match the expected format
for item in catalog:
    if not item.get("imdbId") and not item.get("kpId"):
        errors.append(f"Neither imdbId nor kpId: {item['titleEn']}")
    imdb = item.get("imdbId")
    if imdb and not re.fullmatch(r"tt\d+", imdb):
        errors.append(f"Invalid imdbId: {imdb} ({item['titleEn']})")
    kp = item.get("kpId")
    if kp and not (isinstance(kp, int) or str(kp).isdigit()):
        errors.append(f"kpId is not a number: {kp} ({item['titleEn']})")

# 3d. Descriptions required for film pages
for item in catalog:
    d = item.get("desc")
    ok = (
        isinstance(d, dict)
        and isinstance(d.get("ru"), str)
        and isinstance(d.get("en"), str)
        and len(d["ru"].strip()) >= 20
        and len(d["en"].strip()) >= 20
    )
    if not ok:
        errors.append(f"Missing/short desc (ru/en): {item['titleEn']}")

# 3e. Slug uniqueness and format (film pages must map 1:1)
slugs = [item_slug(item) for item in catalog]
dups = sorted({s for s in slugs if slugs.count(s) > 1})
if dups:
    errors.append(f"Duplicate slugs: {dups}")
for item in catalog:
    s = item_slug(item)
    if not re.fullmatch(r"(?:tt\d+|kp-\d+)(?:-[a-z0-9]+)+", s):
        errors.append(f"Unexpected slug format: {s} ({item['titleEn']})")

# 4. Poster files exist
for item in catalog:
    p = (item.get("poster") or "").lstrip("/")
    if p and not (ROOT / p).exists():
        errors.append(f"Poster file missing: {item['poster']} ({item['titleEn']})")

# 4b. Film pages exist and match the current generator (gen_pages.py)
for item in catalog:
    slug = item_slug(item)
    page = ROOT / "films" / slug / "index.html"
    if not page.exists():
        errors.append(f"Missing film page: films/{slug}/ ({item['titleEn']})")
        continue
    expected = gen_pages.render(item, gen_pages.related_to(item, catalog))
    if page.read_text(encoding="utf-8") != expected:
        errors.append(f"Stale film page: films/{slug}/ — run gen_pages.py ({item['titleEn']})")

# 5. Genres must come from the I18N dictionary (keys extracted from i18n.js)
known = known_genres()
used = {g for item in catalog for g in item["genres"]}
unknown = used - known
if unknown:
    errors.append(f"Genres without a translation: {sorted(unknown)}")
unused = known - used
print(f"Genres: {len(used)} used, {len(known)} declared; unused: {sorted(unused) or '-'}")

# 6. All static/ references in html/app/css exist
i18n_src = (ROOT / "js" / "i18n.js").read_text(encoding="utf-8")
film_js = (ROOT / "js" / "film.js").read_text(encoding="utf-8")
app_js = (ROOT / "js" / "app.js").read_text(encoding="utf-8")
refs = {
    r[:-1] if r.endswith("\\") else r
    for r in re.findall(r"""['"]((?:static|\.\./static)/[^'"]+)['"]""", i18n_src + raw + app_js + film_js)
}
for name in ("index.html", "404.html"):
    text = (ROOT / name).read_text(encoding="utf-8")
    for v in re.findall(r'(?:content|src|href)="([^"]+)"', text):
        m = re.search(r'(?:static|\.\./static|css|js)/[^"\')\s]+', v)
        if m:
            refs.add(m.group(0))
for page in (ROOT / "films").glob("*/index.html"):
    text = page.read_text(encoding="utf-8")
    for v in re.findall(r'(?:content|src|href)="([^"]+)"', text):
        if v.startswith("http://") or v.startswith("https://"):
            continue
        if v.startswith("../../"):
            refs.add(v)
            continue
        m = re.search(r'(?:static|\.\./static|css|js)/[^"\')\s]+', v)
        if m:
            refs.add(m.group(0))
for r in refs:
    if r.startswith("../../"):
        path = ROOT / r[6:]
    elif r.startswith("../static"):
        path = ROOT / r.replace("../static", "static", 1)
    else:
        path = ROOT / r
    if not path.exists():
        errors.append(f"Broken file reference: {r}")

# 6b. url(...) in styles resolve relative to css/
css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
css_urls = {u for u in re.findall(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", css)}
for u in sorted(css_urls):
    if u.startswith(("data:", "http://", "https://", "#")):
        continue
    if not (ROOT / "css" / u).resolve().exists():
        errors.append(f"Broken url() in CSS: {u} (expected css/{u})")
print(f"url() references in style.css: {len(css_urls)}")

# 6c. Sitemap: regeneration (lastmod from git) and robots.txt cross-check
def site_lastmod():
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--",
             "js/data.js", "js/i18n.js", "tools/gen_pages.py", "tools/lib.py"],
            capture_output=True,
            text=True,
            errors="replace",
            cwd=ROOT,
        )
        m = res.stdout.strip()
        if res.returncode == 0 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", m):
            return m
    except OSError:
        pass
    return date.today().isoformat()

lastmod = site_lastmod()
def alt_links(url):
    return (
        f'    <xhtml:link rel="alternate" hreflang="ru" href="{url}"/>\n'
        f'    <xhtml:link rel="alternate" hreflang="en" href="{url}"/>\n'
        f'    <xhtml:link rel="alternate" hreflang="x-default" href="{url}"/>\n'
    )


film_urls = "".join(
    "  <url>\n"
    f"    <loc>{SITE_BASE}/films/{slug}/</loc>\n"
    + alt_links(f"{SITE_BASE}/films/{slug}/")
    + f"    <lastmod>{lastmod}</lastmod>\n"
    "    <changefreq>monthly</changefreq>\n"
    "    <priority>0.7</priority>\n"
    "  </url>\n"
    for slug in sorted(slugs)
)
sitemap_xml = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    ' xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
    "  <url>\n"
    f"    <loc>{SITE_BASE}/</loc>\n"
    + alt_links(SITE_BASE + "/")
    + f"    <lastmod>{lastmod}</lastmod>\n"
    "    <changefreq>monthly</changefreq>\n"
    "    <priority>1.0</priority>\n"
    "  </url>\n"
    + film_urls
    + "</urlset>\n"
)
sitemap_file = ROOT / "sitemap.xml"
sitemap_note = "up to date"
if not sitemap_file.exists():
    sitemap_note = "missing"
    errors.append("sitemap.xml is missing")
elif sitemap_file.read_text(encoding="utf-8").strip() != sitemap_xml.strip():
    sitemap_note = f"stale (lastmod={lastmod})"
    if NO_WRITE:
        errors.append("sitemap.xml is stale — run verify.py without --no-write to regenerate")
    else:
        sitemap_file.write_text(sitemap_xml, encoding="utf-8")
        sitemap_note = f"generated (lastmod={lastmod})"

loc = ElementTree.fromstring(sitemap_xml).findtext(
    "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
    "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
)
if loc != f"{SITE_BASE}/":
    errors.append(f"Sitemap: invalid loc: {loc}")

robots_path = ROOT / "robots.txt"
robots_target = (
    "User-agent: *\n"
    "Allow: /\n"
    f"\nSitemap: {SITE_BASE}/sitemap.xml\n"
)
robots_note = "up to date"
if not robots_path.exists():
    robots_note = "missing"
    errors.append("robots.txt is missing")
elif robots_path.read_text(encoding="utf-8").strip() != robots_target.strip():
    robots_note = "stale"
    if NO_WRITE:
        errors.append("robots.txt is stale — run verify.py without --no-write to regenerate")
    else:
        robots_path.write_text(robots_target, encoding="utf-8")
        robots_note = "generated"
robots_txt = robots_path.read_text(encoding="utf-8")
if f"Sitemap: {SITE_BASE}/sitemap.xml" not in robots_txt:
    errors.append(f"robots.txt: missing 'Sitemap: {SITE_BASE}/sitemap.xml'")

if not (ROOT / ".nojekyll").exists():
    errors.append(".nojekyll is missing — add it to keep GitHub Pages from running Jekyll")

# 7. Bracket balance in JS outside strings (coarse syntax check)
def balance(src):
    stack = []
    i = 0
    pairs = {")": "(", "]": "[", "}": "{"}
    while i < len(src):
        c = src[i]
        if c in "\"'`":
            q = c
            i += 1
            while i < len(src):
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == q:
                    break
                i += 1
        elif c in "([{":
            stack.append(c)
        elif c in ")]}":
            if not stack or stack[-1] != pairs[c]:
                return f"Unbalanced near position {i}: {c!r}"
            stack.pop()
        i += 1
    return "OK" if not stack else f"Unclosed brackets: {stack}"

for name in ("app.js", "i18n.js", "film.js", "common.js"):
    src = (ROOT / "js" / name).read_text(encoding="utf-8")
    res = balance(src)
    print(f"Bracket balance {name}: {res}")
    if res != "OK":
        errors.append(f"{name}: {res}")

# 8. Records grouped by type in consecutive blocks
order = [item["type"] for item in catalog]
switches = sum(1 for a, b in zip(order, order[1:]) if a != b)
print(f"Consecutive type switches in file: {switches} (expected 2: movie -> documentary -> series)")

# Lines declaring each record's type + its title
loc = []
for m in re.finditer(r'"type"\s*:\s*"([^"]+)"', raw):
    p = raw.find('"titleEn"', m.end())
    title = "?"
    if p != -1:
        q = raw.index('"', p + len('"titleEn"') + 1)
        title = raw[q + 1 : raw.index('"', q + 1)]
    loc.append((raw.count("\n", 0, m.start()) + 1, m.group(1), title))

if [t for _, t, _ in loc] == order:
    blocks = list(dict.fromkeys(order))
    start_lines = {}
    for line, t, _ in loc:
        start_lines.setdefault(t, line)
    expected_idx = 0
    for line, t, title in loc:
        expected_idx = max(expected_idx, blocks.index(t))
        if blocks.index(t) < expected_idx:
            expected = blocks[expected_idx]
            errors.append(
                f"Record outside its block: js/data.js:{line} {t} \"{title}\" — "
                f"expected {expected} (its block starts at line {start_lines[expected]})"
            )
else:
    errors.append("Could not map catalog records to js/data.js lines")

if switches != 2:
    errors.append(f"Records not grouped by type: {switches} switches")

# 9. JS syntax check via node --check (if node is installed)
if shutil.which("node"):
    for name in ("app.js", "i18n.js", "film.js", "common.js", "data.js"):
        res = subprocess.run(
            ["node", "--check", str(ROOT / "js" / name)],
            capture_output=True,
            text=True,
            errors="replace",
        )
        if res.returncode != 0:
            errors.append(f"{name}: node --check failed:\n{res.stderr.strip()}")
    print("node --check js/*.js: OK")
else:
    print("node not found, JS syntax check skipped")

# 9b. app.js smoke test: boots the catalog app setup with mocked Vue globals
if shutil.which("node"):
    harness = r'''
        const fs = require("fs");
        const ROOT = __ROOT_PATH__;
        function read(p) { return fs.readFileSync(ROOT + "/" + p, "utf8"); }
        global.window = global;
        global.location = {
          pathname: "/IT_movies/",
          search: "",
          href: "https://example.org/IT_movies/",
        };
        global.navigator = { language: "ru" };
        global.document = {
          querySelector: () => ({ setAttribute() {} }),
          documentElement: { classList: { add() {}, toggle() {} }, lang: "" },
          title: "",
          body: {},
        };
        global.history = { replaceState() {} };
        global.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
        const noop = () => {};
        let captured;
        global.Vue = {
          createApp: (opts) => { captured = opts.setup; return { components: {}, config: {}, mount: noop }; },
          computed: (fn) => ({ value: fn() }),
          reactive: (o) => o,
          ref: (v) => ({ value: v }),
          watch: noop,
          onMounted: noop,
          onUnmounted: noop,
          nextTick: () => Promise.resolve(),
        };
        eval(
          read("js/i18n.js") + "\n" +
          read("js/common.js") + "\n" +
          read("js/data.js") + "\n" +
          read("js/app.js")
        );
        const state = captured();
        if (!state || typeof state.movies.value.length !== "number" || !state.setLang) {
          throw new Error("app.js setup() returned invalid state");
        }
        const total = state.movies.value.length + state.series.value.length + state.documentaries.value.length;
        if (total !== global.CATALOG.length) {
          throw new Error("sections total " + total + " != CATALOG.length " + global.CATALOG.length);
        }
        console.log("app.js smoke (sections sum == CATALOG): OK");
    '''.replace("__ROOT_PATH__", json.dumps(ROOT.as_posix()))
    res = subprocess.run(
        ["node", "-e", harness],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if res.returncode != 0:
        errors.append(f"app.js smoke failed:\n{(res.stdout + res.stderr).strip()}")
    else:
        print(res.stdout.strip())
else:
    print("node not found, app.js smoke check skipped")

# 9b2. Slug parity: Python item_slug must equal common.js itemSlug for every record
if shutil.which("node"):
    harness = r'''
        const fs = require("fs");
        function read(p) { return fs.readFileSync("__ROOT__" + "/" + p, "utf8"); }
        global.window = global;
        eval(read("js/data.js"));
        eval(read("js/common.js"));
        const api = global.ITMoviesCommon;
        console.log(JSON.stringify(global.CATALOG.map((it) => api.itemSlug(it))));
    '''.replace("__ROOT__", ROOT.as_posix())
    res = subprocess.run(
        ["node", "-e", harness],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if res.returncode != 0:
        errors.append(f"slug parity: node harness failed:\n{(res.stdout + res.stderr).strip()}")
    else:
        js_slugs = json.loads(res.stdout.strip())
        py_slugs = [item_slug(i) for i in catalog]
        diffs = [
            (i, catalog[i]["titleEn"], js, py)
            for i, (js, py) in enumerate(zip(js_slugs, py_slugs))
            if js != py
        ]
        if diffs:
            for i, title, js, py in diffs:
                errors.append(f"slug mismatch ({title}): JS={js} Python={py}")
        else:
            print(f"Slug parity JS<->Python: OK ({len(js_slugs)} items)")
else:
    print("node not found, slug parity check skipped")

# 9b3. film.js smoke test: boots with window.FILM_PAGE (works without data.js on the page)
if shutil.which("node"):
    harness = r'''
        const fs = require("fs");
        const ROOT = __ROOT_PATH__;
        function read(p) { return fs.readFileSync(ROOT + "/" + p, "utf8"); }
        global.window = global;
        global.location = {
          pathname: "/IT_movies/films/tt0133093-the-matrix/",
          search: "",
          href: "https://example.org/IT_movies/films/tt0133093-the-matrix/",
        };
        global.navigator = { language: "ru" };
        global.document = {
          querySelector: () => ({ setAttribute() {} }),
          documentElement: { classList: { add() {}, toggle() {} }, lang: "" },
          title: "",
          body: {},
        };
        global.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
        const noop = () => {};
        let captured;
        global.Vue = {
          createApp: (opts) => { captured = opts.setup; return { config: {}, mount: noop }; },
          computed: (fn) => ({ value: fn() }),
          ref: (v) => ({ value: v }),
          watch: noop,
          onMounted: noop,
          onUnmounted: noop,
        };
        eval(
          read("js/i18n.js") + "\n" +
          read("js/common.js") + "\n" +
          read("js/data.js") + "\n" +
          read("js/film.js")
        );
        global.FILM_PAGE = {
          item: window.CATALOG[0],
          related: window.CATALOG.slice(1, 3),
        };
        const state = captured();
        if (!state || typeof state.related.length !== "number" || !state.itemSlug) {
          throw new Error("film.js setup() returned invalid state");
        }
        console.log("film.js smoke (FILM_PAGE, no data.js on page): OK");
    '''.replace("__ROOT_PATH__", json.dumps(ROOT.as_posix()))
    res = subprocess.run(
        ["node", "-e", harness],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if res.returncode != 0:
        errors.append(f"film.js smoke failed:\n{(res.stdout + res.stderr).strip()}")
    else:
        print(res.stdout.strip())
else:
    print("node not found, film.js smoke check skipped")

# 9c. Theme head-script must stay in sync across pages and scripts
def _norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def _theme_block(src):
    m = re.search(
        r"<!-- begin:theme-script -->(.*?)<!-- end:theme-script -->", src, re.S
    )
    return _norm_ws(re.sub(r"</?script>", "", m.group(1))) if m else None


theme_core = _norm_ws(re.sub(r"</?script>", "", gen_pages.THEME_SCRIPT))
index_src = (ROOT / "index.html").read_text(encoding="utf-8")
if _theme_block(index_src) != theme_core:
    errors.append(
        "index.html theme block differs from gen_pages.THEME_SCRIPT — run gen_pages.py"
    )
notfound_src = (ROOT / "404.html").read_text(encoding="utf-8")
if _theme_block(notfound_src) != theme_core:
    errors.append(
        "404.html theme block differs from gen_pages.THEME_SCRIPT — run gen_pages.py"
    )

# 9d. index.html noscript catalog block must match the catalog (gen_pages.py)
nscript_m = re.search(
    r"<!-- begin:catalog-noscript -->(.*?)<!-- end:catalog-noscript -->",
    index_src,
    re.S,
)
expected_nscript = gen_pages.index_noscript(catalog)
if nscript_m is None or _norm_ws(nscript_m.group(1)) != _norm_ws(expected_nscript):
    errors.append(
        "index.html noscript catalog block is stale — run gen_pages.py"
    )

ld_m = re.search(r"<!-- begin:index-ld -->(.*?)<!-- end:index-ld -->", index_src, re.S)
if ld_m is None:
    errors.append("index.html: index-ld markers not found")
else:
    inner = re.sub(r"<script[^>]*>|</script>", "", ld_m.group(1)).strip()
    if inner != gen_pages.index_ld_json(catalog):
        errors.append("index.html JSON-LD block is stale — run gen_pages.py")
    else:
        graph = json.loads(inner).get("@graph", [])
        ws = next((n for n in graph if n.get("@type") == "WebSite"), None)
        il = next((n for n in graph if n.get("@type") == "ItemList"), None)
        if (
            not ws
            or not ws.get("potentialAction")
            or not il
            or il.get("numberOfItems") != len(catalog)
        ):
            errors.append("index.html JSON-LD: unexpected structure")
        else:
            print(f"JSON-LD index: OK ({len(catalog)} items, static)")

# 9e. Hardcoded site URLs must stay under lib.SITE_BASE (single source)
for fname, txt in (("index.html", index_src), ("404.html", notfound_src)):
    if SITE_BASE not in txt:
        errors.append(f"{fname}: SITE_BASE ({SITE_BASE}) URL not found")
    for m in re.finditer(r"https://[^\s\"'<>]+", txt):
        u = m.group(0)
        if "github.io" in u and u != SITE_BASE and not u.startswith(SITE_BASE + "/"):
            errors.append(f"{fname}: hardcoded URL not under SITE_BASE: {u}")

# 9f. Canonical links: single, parameterless, and equal to the page's own URL
# (?q=/?fav= filter variants must consolidate onto the clean URL, no duplicate content)
def _canonical_hrefs(text):
    return [
        m.group(1)
        for tag in re.findall(r"<link\b[^>]*>", text)
        if re.search(r'\brel\s*=\s*"canonical"', tag)
        for m in [re.search(r'\bhref\s*=\s*"([^"]+)"', tag)]
        if m
    ]


def _canonical_check(fname, text, expected):
    hrefs = _canonical_hrefs(text)
    if expected is None:
        if len(hrefs) > 1:
            errors.append(f"{fname}: more than one canonical link: {hrefs}")
        elif hrefs and ("?" in hrefs[0] or "#" in hrefs[0]):
            errors.append(f"{fname}: canonical must be parameterless: {hrefs[0]}")
        return
    if len(hrefs) != 1:
        errors.append(f"{fname}: expected exactly one canonical link, found {len(hrefs)}")
        return
    href = hrefs[0]
    if "?" in href or "#" in href:
        errors.append(f"{fname}: canonical must be parameterless: {href}")
    if href != expected:
        errors.append(f"{fname}: canonical mismatch: got {href}, expected {expected}")


# index.html — the catalog root: ?q=/?fav= variants must consolidate onto it
_canonical_check("index.html", index_src, SITE_BASE + "/")
# 404.html — unique error content, indexing discouraged; canonical may be absent
_canonical_check("404.html", notfound_src, None)
canon_checked = 0
for slug in sorted(slugs):
    _canonical_check(
        f"films/{slug}/index.html",
        (ROOT / "films" / slug / "index.html").read_text(encoding="utf-8"),
        f"{SITE_BASE}/films/{slug}/",
    )
    canon_checked += 1

print(f"Sitemap: {sitemap_note}")
print(f"robots.txt: {robots_note}")
print(f"Canonical: checked ({canon_checked} pages + index/404)")
if (ROOT / ".nojekyll").exists():
    print(".nojekyll: present")
print()
if errors:
    print("ERRORS:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("✅ All good")