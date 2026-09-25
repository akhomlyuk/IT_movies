#!/usr/bin/env python3
"""Standalone data integrity and reference check for the IT Movies project."""
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from xml.etree import ElementTree

import gen_pages
from lib import ROOT, SITE_BASE, item_slug, load_catalog, known_genres, parse_i18n, i18n_key_paths, has_rating

sys.stdout.reconfigure(encoding="utf-8")
errors = []
NO_WRITE = "--no-write" in sys.argv
STRICT = "--strict" in sys.argv

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

# 4a. Poster naming convention: lowercase [a-z0-9_] and no case-only collisions
# (git on case-insensitive filesystems won't notice renames that only change case)
POSTER_RE = re.compile(r"^[a-z0-9_]+\.webp$")
posters_dir = ROOT / "static" / "posters"
name_groups: dict[str, list[str]] = {}
for name in sorted(p.name for p in posters_dir.iterdir() if p.is_file()):
    if not POSTER_RE.fullmatch(name):
        errors.append(f"Poster name breaks the lowercase convention: {name}")
    name_groups.setdefault(name.lower(), []).append(name)
for key, group in name_groups.items():
    if len(group) > 1:
        errors.append(f"Posters differing only by case: {sorted(group)}")

catalog_posters = sorted({i["poster"].lstrip("/") for i in catalog if i.get("poster")})
missing_variants = [
    p
    for p in catalog_posters
    if not (ROOT / (p[: -len(".webp")] + "_400.webp")).exists()
]
if missing_variants:
    errors.append(
        f"poster _400 variants missing: {len(missing_variants)} — run tools/gen_posters.py"
    )
else:
    print(
        f"Poster variants: _400 present for {len(catalog_posters)} posters (gen_posters.py)"
    )

# 4b. Film pages exist and match the current generator (gen_pages.py)
for item in catalog:
    slug = item_slug(item)
    page = ROOT / "films" / slug / "index.html"
    if not page.exists():
        errors.append(f"Missing film page: films/{slug}/ ({item['titleEn']})")
        continue
    rel = gen_pages.related_to(item, catalog, 4)
    pool = gen_pages.related_pool(item, catalog)
    if len(pool) < 6:
        errors.append(f"related pool too small ({len(pool)}): {item['titleEn']}")
    if item["type"] != "documentary" and any(p["type"] == "documentary" for p in pool):
        errors.append(f"documentary leaked into related pool: {item['titleEn']}")
    if not {item_slug(r) for r in rel} <= {item_slug(r) for r in pool}:
        errors.append(f"static related not inside related pool: {item['titleEn']}")
    expected = gen_pages.render(item, rel, pool)
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

doc_missing = sorted(
    item["titleEn"]
    for item in catalog
    if item["type"] == "documentary" and "documentary" not in item["genres"]
)
if doc_missing:
    errors.append(
        f"Documentary records missing the 'documentary' genre ({len(doc_missing)}): {doc_missing}"
    )

# 5c. Ratings need a vote count (AggregateRating.ratingCount): KP when present,
# otherwise IMDb. Records without any votes simply get no aggregateRating.
for item in catalog:
    if has_rating(item.get("kpRating")) and not item.get("kpVotes"):
        errors.append(f"kpRating without kpVotes (AggregateRating.ratingCount would be missing): {item['titleEn']}")
    elif not has_rating(item.get("kpRating")) and has_rating(item.get("imdbRating")) and not item.get("imdbVotes"):
        errors.append(f"imdbRating without imdbVotes (AggregateRating.ratingCount would be missing): {item['titleEn']}")

# 5b. i18n ru/en key parity (all keys incl. nested typeLabels/genres)
try:
    i18n = parse_i18n()
    ru_paths = i18n_key_paths(i18n["ru"])
    en_paths = i18n_key_paths(i18n["en"])
    only_ru = ru_paths - en_paths
    only_en = en_paths - ru_paths
    if only_ru:
        errors.append(f"i18n keys present only in ru: {sorted('.'.join(p) for p in only_ru)}")
    if only_en:
        errors.append(f"i18n keys present only in en: {sorted('.'.join(p) for p in only_en)}")
    if not only_ru and not only_en:
        print(f"i18n ru/en parity: OK ({len(ru_paths)} keys, {len(en_paths)} en)")
    else:
        print(f"i18n ru/en parity: MISMATCH")
except (ValueError, KeyError) as e:
    errors.append(f"i18n parse failed: {e}")

# 6. All static/ references in html/app/css exist
i18n_src = (ROOT / "js" / "i18n.js").read_text(encoding="utf-8")
film_js = (ROOT / "js" / "film.js").read_text(encoding="utf-8")
app_js = (ROOT / "js" / "app.js").read_text(encoding="utf-8")
about_js = (ROOT / "js" / "about.js").read_text(encoding="utf-8")
catalog_src = (ROOT / "js" / "catalog.js").read_text(encoding="utf-8")
refs = {
    r[:-1] if r.endswith("\\") else r
    for r in re.findall(r"""['"]((?:static|\.\./static)/[^'"]+)['"]""", i18n_src + raw + app_js + film_js + about_js + catalog_src)
}
for name in ("index.html", "404.html", "privacy.html", "about.html"):
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
data_re = r"""url\(\s*(?:"data:[^"]*"|'data:[^']*'|data:[^)\s]*)\s*\)"""
n_data = len(re.findall(data_re, css))
css_urls = {u for u in re.findall(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.sub(data_re, "", css))}
for u in sorted(css_urls):
    if u.startswith(("data:", "http://", "https://", "#")):
        continue
    if not (ROOT / "css" / u).resolve().exists():
        errors.append(f"Broken url() in CSS: {u} (expected css/{u})")
print(f"url() references in style.css: {len(css_urls) + n_data}")

# 6c. Sitemap / robots.txt / webmanifest: single source in gen_pages.py
sitemap_xml = gen_pages.generate_sitemap(catalog)
sitemap_file = ROOT / "sitemap.xml"
sitemap_note = "up to date"
if not sitemap_file.exists():
    sitemap_note = "missing"
    errors.append("sitemap.xml is missing")
elif sitemap_file.read_text(encoding="utf-8").strip() != sitemap_xml.strip():
    sitemap_note = "stale"
    if NO_WRITE:
        errors.append("sitemap.xml is stale — run verify.py without --no-write to regenerate")
    else:
        sitemap_file.write_text(sitemap_xml, encoding="utf-8")
        sitemap_note = "generated"

loc = ElementTree.fromstring(sitemap_xml).findtext(
    "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
    "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
)
if loc != f"{SITE_BASE}/":
    errors.append(f"Sitemap: invalid loc: {loc}")

ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
url_entries = ElementTree.fromstring(sitemap_xml).findall(f"{ns}url")
without_lastmod = [u.findtext(f"{ns}loc") for u in url_entries if u.find(f"{ns}lastmod") is None]
if without_lastmod:
    errors.append(
        f"Sitemap: {len(without_lastmod)} urls missing lastmod (first: {without_lastmod[0]})"
    )
if len(url_entries) != len(catalog) + 3:
    errors.append(f"Sitemap: expected {len(catalog) + 3} urls, got {len(url_entries)}")
print(f"Sitemap lastmod: {len(url_entries) - len(without_lastmod)}/{len(url_entries)} urls")

robots_path = ROOT / "robots.txt"
robots_target = gen_pages.generate_robots_txt()
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

webmanifest_path = ROOT / "static" / "site.webmanifest"
webmanifest_target = gen_pages.generate_webmanifest()
webmanifest_note = "up to date"
if not webmanifest_path.exists():
    webmanifest_note = "missing"
    errors.append("static/site.webmanifest is missing")
elif webmanifest_path.read_text(encoding="utf-8").strip() != webmanifest_target.strip():
    webmanifest_note = "stale"
    if NO_WRITE:
        errors.append("static/site.webmanifest is stale — run verify.py without --no-write to regenerate")
    else:
        webmanifest_path.write_text(webmanifest_target, encoding="utf-8")
        webmanifest_note = "generated"

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

for name in ("app.js", "i18n.js", "film.js", "common.js", "about.js"):
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
    for name in (
        "app.js", "i18n.js", "film.js", "common.js", "data.js", "about.js",
        "catalog.js", "i18n.min.js", "common.min.js", "app.min.js", "film.min.js", "about.min.js",
    ):
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
    msg = "node not found: JS syntax/smoke checks skipped"
    if STRICT:
        errors.append(msg)
    else:
        print(msg)

# 9b. Derived JS files (js/catalog.js + js/*.min.js) must match gen_pages.py
for rel, content in (
    ("js/catalog.js", gen_pages.catalog_js(catalog)),
) + tuple(
    (
        "js/" + name.replace(".js", ".min.js"),
        gen_pages.minify_js((ROOT / "js" / name).read_text(encoding="utf-8")),
    )
    for name in ("i18n.js", "common.js", "app.js", "film.js", "about.js")
):
    path = ROOT / rel
    if not path.exists():
        errors.append(f"{rel} is missing — run gen_pages.py")
    elif path.read_text(encoding="utf-8") != content:
        errors.append(f"{rel} is stale — run gen_pages.py")
print("Derived JS files (catalog.js, .min.js): checked against gen_pages.py")

# 9b1. Node smoke harnesses: app.js / slug / film.js / related parity (tools/smoke.js)
def run_smoke(*args):
    res = subprocess.run(
        ["node", str(ROOT / "tools" / "smoke.js"), *args],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError((res.stdout + res.stderr).strip())
    return res.stdout.strip()


if shutil.which("node"):
    def check_slugs(*args):
        label = ", minified" if args else ""
        try:
            js_slugs = json.loads(run_smoke("slug", *args))
        except (RuntimeError, json.JSONDecodeError) as e:
            errors.append(f"slug parity: node harness failed:\n{e}")
            return
        py_slugs = [item_slug(i) for i in catalog]
        diffs = [
            (i, catalog[i]["titleEn"], js, py)
            for i, (js, py) in enumerate(zip(js_slugs, py_slugs))
            if js != py
        ]
        if len(js_slugs) != len(py_slugs) or diffs:
            if len(js_slugs) != len(py_slugs):
                errors.append(f"slug parity: size mismatch JS={len(js_slugs)} Python={len(py_slugs)}")
            for i, title, js, py in diffs:
                errors.append(f"slug mismatch ({title}): JS={js} Python={py}")
        else:
            print(f"Slug parity JS<->Python: OK ({len(js_slugs)} items{label})")

    def check_related(*args):
        label = ", minified" if args else ""
        try:
            js_related = json.loads(run_smoke("related", *args))
        except (RuntimeError, json.JSONDecodeError) as e:
            errors.append(f"related parity: node harness failed:\n{e}")
            return
        py_related = [
            [item_slug(r) for r in gen_pages.related_to(i, catalog, 6)]
            for i in catalog
        ]
        if len(js_related) != len(py_related):
            errors.append(
                f"related parity: size mismatch JS={len(js_related)} Python={len(py_related)}"
            )
            js_related = js_related[: len(py_related)]
        diffs = [
            (i, catalog[i]["titleEn"], js, py)
            for i, (js, py) in enumerate(zip(js_related, py_related))
            if js != py
        ]
        if diffs:
            for i, title, js, py in diffs[:5]:
                errors.append(f"related mismatch ({title}): JS={js} Python={py}")
            if len(diffs) > 5:
                errors.append(f"related parity: {len(diffs) - 5} more mismatches")
        else:
            print(f"Related parity JS<->Python: OK ({len(py_related)} items, n=6{label})")

    # app.js smoke test: boots the catalog app with mocked Vue globals
    try:
        print(run_smoke("app"))
    except RuntimeError as e:
        errors.append(f"app.js smoke failed:\n{e}")

    # Slug parity: Python item_slug must equal common.js itemSlug for every record
    check_slugs()

    # film.js smoke test: boots with window.FILM_PAGE (works without data.js on the page)
    try:
        print(run_smoke("film"))
    except RuntimeError as e:
        errors.append(f"film.js smoke failed:\n{e}")

    # Related parity: JS relatedItems must equal Python gen_pages.related_to
    check_related()

    # 9b2. Repeat the smokes on the minified JS actually shipped (*.min.js),
    # so a semantics-changing bug in gen_pages.minify_js is caught by the tests
    for name in ("app", "slug", "film", "related"):
        if name == "slug":
            check_slugs("--min")
            continue
        if name == "related":
            check_related("--min")
            continue
        try:
            print(run_smoke(name, "--min"))
        except RuntimeError as e:
            errors.append(f"{name} (minified): smoke failed:\n{e}")
else:
    if not STRICT:
        print("node not found, JS smoke checks skipped")

# 9c. Theme head-script must stay in sync across pages and scripts
def _norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def _theme_block(src):
    m = re.search(
        r"<!-- begin:theme-script -->(.*?)<!-- end:theme-script -->", src, re.S
    )
    return _norm_ws(re.sub(r"</?script>", "", m.group(1))) if m else None


def _mark_block(src, begin, end):
    m = re.search(re.escape(begin) + r"(.*?)" + re.escape(end), src, re.S)
    return _norm_ws(m.group(1)) if m else None


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
privacy_src = (ROOT / "privacy.html").read_text(encoding="utf-8")
if _theme_block(privacy_src) != theme_core:
    errors.append(
        "privacy.html theme block differs from gen_pages.THEME_SCRIPT — run gen_pages.py"
    )
about_src = (ROOT / "about.html").read_text(encoding="utf-8")
if _theme_block(about_src) != theme_core:
    errors.append(
        "about.html theme block differs from gen_pages.THEME_SCRIPT — run gen_pages.py"
    )

# 9c2. Yandex.Metrika: single source (gen_pages.METRIKA_SCRIPT) on every page
metrika_needle = f"mc.yandex.ru/metrika/tag.js?id={gen_pages.METRIKA_ID}"
metrika_core = _norm_ws(gen_pages.METRIKA_SCRIPT)
metrika_checked = 0
for fname, src in (
    ("index.html", index_src),
    ("404.html", notfound_src),
    ("privacy.html", privacy_src),
    ("about.html", about_src),
):
    if metrika_needle not in src:
        errors.append(f"{fname}: Yandex.Metrika snippet missing")
    if _mark_block(src, "<!-- begin:metrika -->", "<!-- end:metrika -->") != metrika_core:
        errors.append(f"{fname} metrika block differs from gen_pages.METRIKA_SCRIPT — run gen_pages.py")
for page in sorted((ROOT / "films").glob("*/index.html")):
    metrika_checked += 1
    fsrc = page.read_text(encoding="utf-8")
    if metrika_needle not in fsrc:
        errors.append(f"metrika snippet missing on {page}")
    fm = re.search(r'<script type="application/ld\+json">(.*?)</script>', fsrc, re.S)
    if fm is None:
        errors.append(f"film JSON-LD missing on {page}")
    else:
        try:
            fgraph = json.loads(fm.group(1)).get("@graph", [])
            fmovie = next(
                (n for n in fgraph if n.get("@type") in ("Movie", "TVSeries")), None
            )
            if (
                not fmovie
                or fmovie.get("@id") != fmovie.get("url")
                or fmovie.get("inLanguage") != "ru"
            ):
                errors.append(f"film JSON-LD: @id/inLanguage broken on {page}")
        except json.JSONDecodeError:
            errors.append(f"film JSON-LD: invalid JSON on {page}")
    if "srcset=" not in fsrc or "_400.webp 400w" not in fsrc or "imagesrcset" not in fsrc:
        errors.append(f"poster srcset/preload missing on {page}")
print(f"Metrika: present on {metrika_checked} film pages + index/404/privacy/about (single source)")

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

lastupd_m = re.search(
    r"<!-- begin:last-updated -->(.*?)<!-- end:last-updated -->", index_src, re.S
)
if lastupd_m is None or _norm_ws(lastupd_m.group(1)) != _norm_ws(
    gen_pages.last_updated_block()
):
    errors.append("index.html last-updated widget block is stale — run gen_pages.py")
else:
    print(f"Last-updated widget: OK ({gen_pages.CATALOG_DATE})")

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
        org = next((n for n in graph if n.get("@type") == "Organization"), None)
        wp = next((n for n in graph if n.get("@type") == "WebPage"), None)
        if (
            not ws
            or not ws.get("potentialAction")
            or not il
            or il.get("numberOfItems") != len(catalog)
            or not il.get("@id")
            or not org
            or not org.get("@id")
            or not wp
            or wp.get("isPartOf", {}).get("@id") != ws.get("@id")
            or wp.get("mainEntity", {}).get("@id") != il.get("@id")
            or wp.get("publisher", {}).get("@id") != org.get("@id")
        ):
            errors.append("index.html JSON-LD: unexpected structure")
        else:
            print(f"JSON-LD index: OK ({len(catalog)} items, Organization/WebPage linked, static)")

pm = re.search(r'<script type="application/ld\+json">(.*?)</script>', privacy_src, re.S)
if pm is None:
    errors.append("privacy.html: JSON-LD block missing")
else:
    try:
        pgraph = json.loads(pm.group(1)).get("@graph", [])
        pwp = next((n for n in pgraph if n.get("@type") == "WebPage"), None)
        if not pwp or pwp.get("isPartOf", {}).get("@id") != SITE_BASE + "/":
            errors.append("privacy.html JSON-LD: WebPage/isPartOf broken")
        else:
            print("JSON-LD privacy: OK (WebPage -> WebSite)")
    except json.JSONDecodeError:
        errors.append("privacy.html JSON-LD: invalid JSON")

# 9e. Hardcoded site URLs must stay under lib.SITE_BASE (single source)
for fname, txt in (
    ("index.html", index_src),
    ("404.html", notfound_src),
    ("privacy.html", privacy_src),
    ("about.html", about_src),
):
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
# privacy.html — canonical to its own URL, same on every lang/theme variant
_canonical_check("privacy.html", privacy_src, SITE_BASE + "/privacy.html")
# about.html — canonical to its own URL, same on every lang/theme variant
_canonical_check("about.html", about_src, SITE_BASE + "/about.html")
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
print(f"webmanifest: {webmanifest_note}")
print(f"Canonical: checked ({canon_checked} pages + index/404/privacy/about)")

# 9g. Static language coherence (runtime switches derive from one source — the
# <html lang>/<title>/<meta description> markup is what crawlers read pre-JS):
#   * <html lang> must match the language of the static <title> and <meta name="description">
#   * og:locale must match the language of og:description
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def _text_lang(s):
    return "ru" if CYRILLIC.search(s) else "en"


def _lang_coherence(fname, text):
    html = re.search(r'<html lang="([^"]+)"\s*>', text)
    if not html:
        errors.append(f"{fname}: <html lang> attribute missing")
        return
    page_lang = html.group(1)
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S)
    if not m:
        errors.append(f"{fname}: <title> missing")
        return
    title_lang = _text_lang(m.group(1))
    if CYRILLIC.search(m.group(1)) and title_lang != page_lang:
        # Cyrillic title on an otherwise-EN page, or non-Cyrillic lang mismatch;
        # a Latin-only title is language-ambiguous (untranslated film titles on RU pages)
        errors.append(
            f"{fname}: <html lang=\"{page_lang}\"> conflicts with <title> ({title_lang})"
        )
    d = re.search(r'<meta name="description" content="([^"]*)"', text)
    if d and _text_lang(d.group(1)) != page_lang:
        errors.append(
            f"{fname}: <html lang=\"{page_lang}\"> conflicts with meta description "
            f"({_text_lang(d.group(1))})"
        )
    ogl = re.search(r'<meta property="og:locale" content="([^"]+)"', text)
    ogd = re.search(r'<meta property="og:description" content="([^"]*)"', text)
    if ogl and ogd:
        loc_lang = ogl.group(1).split("_")[0]
        if _text_lang(ogd.group(1)) != loc_lang:
            errors.append(
                f"{fname}: og:locale={ogl.group(1)} conflicts with og:description "
                f"({_text_lang(ogd.group(1))})"
            )


lang_checked = 0
for fname, src in (
    ("index.html", index_src),
    ("404.html", notfound_src),
    ("privacy.html", privacy_src),
    ("about.html", about_src),
):
    _lang_coherence(fname, src)
    lang_checked += 1
for slug in sorted(slugs):
    _lang_coherence(
        f"films/{slug}/index.html",
        (ROOT / "films" / slug / "index.html").read_text(encoding="utf-8"),
    )
    lang_checked += 1
print(f"Language/OG coherence: checked ({lang_checked} pages)")
if (ROOT / ".nojekyll").exists():
    print(".nojekyll: present")
print()
if errors:
    print("ERRORS:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("✅ All good")