#!/usr/bin/env python3
"""Standalone data integrity and reference check for the IT Movies project."""
import collections
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import unicodedata
from html.parser import HTMLParser
from xml.etree import ElementTree

import gen_pages
import poster_crop
from lib import BELOW_MD_MAX, ROOT, SITE_BASE, BREAKPOINT_SCALE, CSS_MEDIA_EDGES, FEATURED_BOX_DESKTOP, FEATURED_BOX_MOBILE, FEATURED_SLOT_CONDITION, POSTER_BOX_DESKTOP, POSTER_BOX_MOBILE, POSTER_VARIANT_WIDTHS, featured_poster_sizes, hero_poster_widths, item_slug, load_catalog, known_genres, parse_i18n, i18n_key_paths, has_rating, poster_sizes, variant_name, variant_path, webp_size

sys.stdout.reconfigure(encoding="utf-8")
errors = []
NO_WRITE = "--no-write" in sys.argv
STRICT = "--strict" in sys.argv
RELATED_COUNT = 6
RELATED_MEAN_OVERLAP = 1.410
RELATED_MEAN_TOLERANCE = 0.04

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
# The whole ladder is required, from lib.POSTER_VARIANT_WIDTHS, not a hand-typed
# 400. A gate that named one rung would stay green while 96w or 192w silently
# stopped being generated, which is the only way an incomplete ladder is visible
# to a reviewer reading a diff.
missing_variants = []
wrong_width = []
wrong_ratio = []
for p in catalog_posters:
    src_dims = webp_size(ROOT / p)
    for width in POSTER_VARIANT_WIDTHS:
        path = variant_path(p, width)
        if not path.exists():
            missing_variants.append((p, width))
            continue
        dims = webp_size(path)
        if not dims or dims[0] != width:
            wrong_width.append((p, width, dims[0] if dims else "unreadable"))
        elif src_dims:
            want_h = max(1, round(src_dims[1] * width / src_dims[0]))
            if dims[1] != want_h:
                wrong_ratio.append((p, width, dims[1], want_h))
if missing_variants:
    per_width = collections.Counter(w for _, w in missing_variants)
    errors.append(
        "poster variants missing: %d file(s), by width %s — run tools/gen_posters.py"
        % (len(missing_variants),
           ", ".join("%dw:%d" % (w, per_width[w]) for w in POSTER_VARIANT_WIDTHS
                     if per_width[w]))
        + " first: " + ", ".join("%s@%dw" % (p, w) for p, w in missing_variants[:5])
    )
else:
    print(
        "Poster variants: ladder %s present for %d posters (%d files)"
        % (", ".join("%dw" % w for w in POSTER_VARIANT_WIDTHS), len(catalog_posters),
           len(catalog_posters) * len(POSTER_VARIANT_WIDTHS))
    )
if wrong_width:
    errors.append(
        "poster variants not exactly their rung width: %d of %d — "
        % (len(wrong_width), len(catalog_posters) * len(POSTER_VARIANT_WIDTHS))
        + ", ".join("%s@%dw is %s" % (p, w, got) for p, w, got in wrong_width[:5])
    )
if wrong_ratio:
    errors.append(
        "poster variants whose height is not the source ratio rounded to its rung: "
        "%d of %d — "
        % (len(wrong_ratio), len(catalog_posters) * len(POSTER_VARIANT_WIDTHS))
        + ", ".join("%s@%dw is %spx tall, ratio wants %spx" % r
                    for r in wrong_ratio[:5])
    )
if not (missing_variants or wrong_width or wrong_ratio):
    print(
        "Poster variants: all %d files at their rung width and the source aspect ratio"
        % (len(catalog_posters) * len(POSTER_VARIANT_WIDTHS))
    )

# The ladder is one definition in lib.py, mirrored into js/film.js and js/app.js
# because the client builds the related card's and the featured card's srcsets
# itself. A mirror nobody checks is a second definition, so the two are compared
# here, in both shipped copies of each file.
ladder_re = re.compile(
    r"POSTER_VARIANT_WIDTHS\s*=\s*\[([0-9,\s]*)\]"
)
for js_name in ("js/film.js", "js/film.min.js", "js/app.js", "js/app.min.js"):
    js_text = (ROOT / js_name).read_text(encoding="utf-8")
    m = ladder_re.search(js_text)
    if not m:
        errors.append(
            f"{js_name}: POSTER_VARIANT_WIDTHS not found — the related card's "
            f"and the featured card's srcset candidates come from this mirror, "
            f"and a mirror that is not there is a mirror that has stopped being read"
        )
        continue
    js_widths = tuple(int(n) for n in m.group(1).replace(" ", "").split(",") if n)
    if js_widths != POSTER_VARIANT_WIDTHS:
        errors.append(
            f"{js_name}: POSTER_VARIANT_WIDTHS is {list(js_widths)} but "
            f"lib.POSTER_VARIANT_WIDTHS is {list(POSTER_VARIANT_WIDTHS)} - one "
            f"definition is the whole point; fix the mirror, not the ladder"
        )
    else:
        print(f"Poster ladder: {js_name} mirrors {list(POSTER_VARIANT_WIDTHS)}")

# The hero's candidate set is the SECOND implementation of the ladder rule, and
# it is the one every reader gets: `posterSrcset` in js/film.js binds to the
# hero's `:srcset` and overwrites what gen_pages.py wrote into the HTML. So the
# committed pages can carry a correct srcset while the browser is handed a stale
# one -- which is exactly what happened for the whole life of the 256w rung, on
# both sides, with nothing comparing them. The set itself is derived in lib from
# the hero's smallest box, so what is compared here is that derivation's result
# against the client's copy, in both shipped files.
hero_re = re.compile(r"HERO_POSTER_WIDTHS\s*=\s*\[([0-9,\s]*)\]")
for js_name in ("js/film.js", "js/film.min.js"):
    js_text = (ROOT / js_name).read_text(encoding="utf-8")
    mh = hero_re.search(js_text)
    if not mh:
        errors.append(
            f"{js_name}: HERO_POSTER_WIDTHS not found - the hero's srcset is built "
            f"in the client and overwrites the generated one, so its candidate set "
            f"is a second definition of lib.hero_poster_widths() and a mirror that "
            f"is not there is a mirror that has stopped being read"
        )
        continue
    js_hero = tuple(int(n) for n in mh.group(1).replace(" ", "").split(",") if n)
    if js_hero != hero_poster_widths():
        errors.append(
            f"{js_name}: HERO_POSTER_WIDTHS is {list(js_hero)} but "
            f"lib.hero_poster_widths() is {list(hero_poster_widths())} - the hero's "
            f"box is {POSTER_BOX_MOBILE}px at its narrowest, so a rung narrower than "
            f"that can never be selected and the set is derived, not chosen. Fix the "
            f"mirror, not the derivation"
        )
    else:
        print(f"Hero srcset candidates: {js_name} mirrors {list(js_hero)} "
              f"(derived from the {POSTER_BOX_MOBILE}px box)")

# 4c. Poster crop: the discarded-AREA bound, REPORTED and no longer gating.
# The arithmetic lives in poster_crop.py and is imported, never re-derived here,
# so the number printed below and the number `python tools/poster_crop.py` prints
# cannot drift. That tool still EXITS 1 when the bound is exceeded, and the bound
# is still 0.02; only this run's exit code is no longer derived from it.
#
# This is the successor to the browser probe's `POSTER_CROP_CEILING`, which was
# 3.1x above the worst value in its own 4-poster sample and was an aspect-ratio
# deviation rather than an area loss, so it bounded nothing anybody assumed it
# bounded. Fixing the QUANTITY was correct and stands. But the library does not
# meet the resulting bound, and on 2026-09-28 the partner viewed the rendered
# cover-vs-frame comparison and ruled that the discarded area is not a visible
# defect. A gate that fails on harm the product does not have is not a gate, it
# is a veto on the wrong question, so it reports and no longer fails. The
# offenders are still printed by name, one line each, in the same order and
# wording as when this failed: the record has to stay readable, because a number
# that can only be re-found by git archaeology is a number that has gone quiet.
crop_records = poster_crop.measure_library()
crop_failing = poster_crop.over_ceiling(crop_records, poster_crop.DISCARDED_AREA_CEILING)
crop_proxy = poster_crop.describe([r.proxy for r in crop_records])
crop_discarded = poster_crop.describe([r.discarded for r in crop_records])
crop_box = poster_crop.RELATED_BOX_DESKTOP
print(
    "Poster crop: %d posters measured from real file dimensions, no browser; box "
    "%dx%d (%.6f, exactly 2:3: %s)"
    % (len(crop_records), crop_box[0], crop_box[1], crop_box[0] / crop_box[1],
       poster_crop.is_two_by_three(crop_box))
)
print(
    "  PROXY |w/h-2/3|      2:3 %d, lose area %d, over %g %d, median %.5f, p90 %.5f, max %.5f"
    % (crop_proxy["exact"], crop_proxy["loses"], poster_crop.PROXY_ASPECT_STANDARD,
       crop_proxy["over_standard"], crop_proxy["median"], crop_proxy["p90"],
       crop_proxy["max"])
)
print(
    "  DISCARDED AREA      2:3 %d, lose area %d, over %g %d, median %.5f, p90 %.5f, max %.5f"
    % (crop_discarded["exact"], crop_discarded["loses"],
       poster_crop.REPORT_TOLERANCE, crop_discarded["over_standard"],
       crop_discarded["median"], crop_discarded["p90"], crop_discarded["max"])
)
print(
    "  worst %d by PROXY:          %s"
    % (poster_crop.WORST_N,
       ", ".join("%s %dx%d %.5f" % (r.poster, r.width, r.height, r.proxy)
                 for r in poster_crop.worst(crop_records, "proxy")))
)
print(
    "  worst %d by DISCARDED AREA: %s"
    % (poster_crop.WORST_N,
       ", ".join("%s %dx%d %.5f" % (r.poster, r.width, r.height, r.discarded)
                 for r in poster_crop.worst(crop_records, "discarded")))
)
if crop_failing:
    print(
        "  BOUND NOT MET: %d of %d posters (%.1f%%) exceed DISCARDED_AREA_CEILING "
        "%s, worst %.5f"
        % (len(crop_failing), len(crop_records),
           len(crop_failing) * 100.0 / len(crop_records),
           poster_crop.DISCARDED_AREA_CEILING, crop_failing[0].discarded)
    )
    print(
        "  NOT A GATE FAILURE, AND NOT REPAIRED. The ceiling is unchanged at %s and "
        "every offender below is still over it. The partner ruled on 2026-09-28, "
        "having viewed the rendered comparison in _tmp/frame-preview.html, that "
        "cover with no frame is the intended rendering and that the discarded "
        "pixels do not read as damage; framing (one CSS declaration, zero discarded "
        "area on all 154) and re-encoding 135 sources to 2:3 were both declined. "
        "This gate was silenced because it measures harm the product does not "
        "have, NOT because the library passes. Do not read the green run as a "
        "repair, and do not raise the ceiling to make the wording match."
        % poster_crop.DISCARDED_AREA_CEILING
    )
    print("  the %d offenders, by name, as they were when this failed:"
          % len(crop_failing))
    for record in crop_failing:
        print(
            "    poster discards %.5f of its area into a %dx%d box (%dx%d source, "
            "proxy %.5f) - over DISCARDED_AREA_CEILING %s: %s"
            % (record.discarded, crop_box[0], crop_box[1], record.width,
               record.height, record.proxy, poster_crop.DISCARDED_AREA_CEILING,
               record.poster)
        )
else:
    print("  BOUND: every poster is within DISCARDED_AREA_CEILING %s"
          % poster_crop.DISCARDED_AREA_CEILING)

# 4b. Film pages exist and match the current generator (gen_pages.py)
for item in catalog:
    slug = item_slug(item)
    page = ROOT / "films" / slug / "index.html"
    if not page.exists():
        errors.append(f"Missing film page: films/{slug}/ ({item['titleEn']})")
        continue
    rel = gen_pages.related_to(item, catalog)
    pool = gen_pages.related_pool(item, catalog)
    if len(pool) < 6:
        errors.append(f"related pool too small ({len(pool)}): {item['titleEn']}")
    if item["type"] != "documentary" and any(p["type"] == "documentary" for p in pool):
        errors.append(f"documentary leaked into related pool: {item['titleEn']}")
    if not {item_slug(r) for r in rel} <= {item_slug(r) for r in pool}:
        errors.append(f"static related not inside related pool: {item['titleEn']}")
    expected = gen_pages.render(item, rel)
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
    # A reference may carry a fragment -- `static/share.svg#icon-telegram` is an
    # SVG sprite lookup, and the film's own `<use>` elements are full of them.
    # This gate used to hand the WHOLE string to `exists()`, so any fragment read
    # as a broken path. It had simply never been shown one: the film's `<use>`
    # lives inside the escaped `window.FILM_RC_CARD` string, whose `\"` does not
    # match the `href="` pattern this scans for, and about.html's sprite is an
    # inline `<symbol>` referenced as `#i-tg` with no path to check. The header's
    # channel link put a literal sprite reference in static markup for the first
    # time, and the gate reported it -- correctly diagnosing its own blindness
    # rather than a bad link.
    #
    # Splitting it also buys the half that matters: a wrong fragment is a silent
    # failure. The file loads, the page looks right in a screenshot, and the glyph
    # is simply absent, so the fragment is resolved against the file's own ids.
    ref, _, frag = r.partition("#")
    if ref.startswith("../../"):
        path = ROOT / ref[6:]
    elif ref.startswith("../static"):
        path = ROOT / ref.replace("../static", "static", 1)
    else:
        path = ROOT / ref
    if not path.exists():
        errors.append(f"Broken file reference: {r}")
    elif frag and path.suffix == ".svg":
        body = path.read_text(encoding="utf-8")
        if ('id="%s"' % frag) not in body:
            errors.append(
                "Broken file reference: %s -- %s exists but carries no id=%r, so "
                "the reference resolves to nothing and the icon renders as an "
                "empty box rather than an error" % (r, ref, frag)
            )

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

# 6d. Stage 2a dead-literal gate. Values are compared after resolution to px,
# not as text: `12px` and `0.75rem` are the same length, so one of them is a
# regression against the other. Two scopes, because the two kinds of scale are
# different shapes:
#   scope "any"   radius, z-index -- the scale is CLOSED. Every value this design
#                 uses is a token, so any bare value is a defect and the ceiling
#                 is an absolute 0. It must not be raised: a bare value means a
#                 token is missing, and the fix is the token, not the ceiling.
#   scope "token" spacing -- the scale is OPEN. `0.1em` badge padding, `15vh`
#                 boot centring, `-6px` hit-area bleed are legitimate and no
#                 token can or should cover them, so only a value that
#                 duplicates a token counts, against a stated ceiling.
STYLE_LITERAL_CEILING = {"spacing": 6, "radius": 0, "z-index": 0}
STYLE_LITERAL_SCOPE = {"spacing": "token", "radius": "any", "z-index": "any"}
STYLE_LITERAL_PROPS = {
    "spacing": {
        prop
        for base in ("margin", "padding", "inset", "scroll-margin", "scroll-padding")
        for prop in (
            base,
            *(
                f"{base}-{suffix}"
                for suffix in (
                    "top", "right", "bottom", "left",
                    "block", "block-start", "block-end",
                    "inline", "inline-start", "inline-end",
                )
            ),
        )
    }
    | {"gap", "row-gap", "column-gap", "top", "right", "bottom", "left"},
    "radius": {"border-radius"},
    "z-index": {"z-index"},
}
STYLE_TOKEN_MEMBERS = {
    "spacing": lambda name: name.startswith("--space-") or name == "--tap",
    "radius": lambda name: name.startswith("--radius-"),
    "z-index": lambda name: name.startswith("--z-"),
}
STYLE_NON_LENGTH = {
    "auto", "none", "inherit", "initial", "unset", "revert", "normal",
    "thin", "medium", "thick", "solid", "dashed", "dotted", "groove",
}
STYLE_DERIVED_FUNCTIONS = ("calc(", "clamp(", "min(", "max(", "env(")
STYLE_CALC_FUNCTIONS = ("calc(", "min(", "max(")
STYLE_VAR = "var("
STYLE_BARE_LENGTH = re.compile(
    r"^-?(?:\d+\.?\d*|\.\d+)(px|rem|em|ex|ch|vh|vw|vmin|vmax|pt|q|%)?$"
)
STYLE_CALC_TERM = re.compile(r"(-?(?:\d+\.?\d*|\.\d+))(px|rem)")
STYLE_NESTING_AT_RULES = ("@media", "@supports", "@container", "@layer", "@document")
STYLE_CSS_INITIAL_FONT_PX = 16.0
STYLE_PX_EPSILON = 0.0001


def _css_brace_end(src, start):
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(src) - 1


def _css_declarations(src, context=()):
    prelude = []
    i = 0
    while i < len(src):
        ch = src[i]
        if ch == "{":
            end = _css_brace_end(src, i)
            head = " ".join("".join(prelude).split())
            body = src[i + 1 : end]
            prelude = []
            i = end + 1
            if head.startswith("@"):
                if head.split(None, 1)[0].lower() in STYLE_NESTING_AT_RULES:
                    yield from _css_declarations(body, context + (head,))
                else:
                    for m in re.finditer(r"([-\w]+)\s*:\s*([^;]+);", body):
                        yield context, head, m.group(1).lower(), " ".join(m.group(2).split())
            else:
                for m in re.finditer(r"([-\w]+)\s*:\s*([^;]+);", body):
                    yield context, head, m.group(1).lower(), " ".join(m.group(2).split())
        elif ch == ";":
            prelude = []
            i += 1
        else:
            prelude.append(ch)
            i += 1


def _top_level_parts(value):
    parts, depth, current = [], 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch.isspace() and depth == 0:
            if current:
                parts.append("".join(current))
                current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _style_calc_px(part, root):
    name, sep, rest = part.partition("(")
    if not sep or not rest.endswith(")"):
        return None
    body = rest[:-1]
    pos = 0

    def skip():
        nonlocal pos
        while pos < len(body) and body[pos].isspace():
            pos += 1

    def primary():
        nonlocal pos
        skip()
        if pos < len(body) and body[pos] == "(":
            pos += 1
            value = expression()
            skip()
            if pos >= len(body) or body[pos] != ")":
                raise ValueError(part)
            pos += 1
            return value
        term = STYLE_CALC_TERM.match(body, pos)
        if not term:
            raise ValueError(part)
        pos = term.end()
        return float(term.group(1)) * (root if term.group(2) == "rem" else 1.0)

    def term():
        nonlocal pos
        value = primary()
        while True:
            skip()
            if pos < len(body) and body[pos] in "*/":
                operator = body[pos]
                pos += 1
                operand = primary()
                value = value * operand if operator == "*" else value / operand
            else:
                return value

    def expression():
        nonlocal pos
        value = term()
        while True:
            skip()
            if pos < len(body) and body[pos] in "+-":
                operator = body[pos]
                pos += 1
                operand = term()
                value = value + operand if operator == "+" else value - operand
            else:
                return value

    try:
        result = expression()
    except (ValueError, ZeroDivisionError):
        return None
    skip()
    return round(result, 4) if pos == len(body) else None


def _style_classify(part, root):
    low = part.lower()
    if low in STYLE_NON_LENGTH:
        return "keyword", None
    if low.startswith(STYLE_VAR):
        return "token", None
    if low.startswith(STYLE_DERIVED_FUNCTIONS):
        if low.startswith(STYLE_CALC_FUNCTIONS):
            return "derived", _style_calc_px(part, root)
        return "derived", None
    match = STYLE_BARE_LENGTH.match(part)
    if not match:
        return "other", None
    unit = match.group(1) or ""
    digits = match.group(0)[: len(match.group(0)) - len(unit)]
    number = float(digits)
    if unit == "%":
        return "percent", None
    if number == 0:
        return "zero", None
    if unit in ("px", ""):
        return "length", round(number, 4)
    if unit == "rem":
        return "length", round(number * root, 4)
    return "relative", number


def _style_root_font_px(src):
    declared = {}
    for context, selector, prop, value in _css_declarations(src):
        if prop != "font-size":
            continue
        if any(s.strip() in ("html", ":root") for s in selector.split(",")):
            declared[selector] = value
    if not declared:
        return (
            STYLE_CSS_INITIAL_FONT_PX,
            "css/style.css declares no font-size on html or :root, so the root "
            "font-size is the CSS initial value for font-size:medium. Not "
            "measured in this process: verify.py runs no browser and takes no "
            "dev-server dependency by design",
        )
    resolved = {}
    for selector, value in declared.items():
        kind, px = _style_classify(value, STYLE_CSS_INITIAL_FONT_PX)
        resolved[selector] = px if kind == "length" and "%" not in value else None
    distinct = {v for v in resolved.values() if v is not None}
    if len(distinct) == 1:
        return (
            distinct.pop(),
            "read from css/style.css: "
            + ", ".join(f"{s} {{ font-size: {v} }}" for s, v in resolved.items()),
        )
    return (
        STYLE_CSS_INITIAL_FONT_PX,
        "css/style.css declares "
        + str(len(resolved))
        + " conflicting or unresolvable root font-size value(s) ("
        + ", ".join(f"{s}: {v}" for s, v in resolved.items())
        + "); falling back to the CSS initial value",
    )


def check_style_literals():
    plain = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    plain = re.sub(r"url\(\s*(?:\"[^\"]*\"|'[^']*'|[^)]*)\s*\)", "url(0)", plain)
    root, root_note = _style_root_font_px(plain)
    token_px = {family: {} for family in STYLE_LITERAL_PROPS}
    token_src = {family: {} for family in STYLE_LITERAL_PROPS}
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;{}]+);", plain):
        for family, member in STYLE_TOKEN_MEMBERS.items():
            if not member(m.group(1)):
                continue
            text = m.group(2).strip()
            kind, value = _style_classify(text, root)
            if kind == "zero":
                value = 0.0
            elif kind not in ("length", "percent", "relative"):
                continue
            token_px[family][m.group(1)] = value
            token_src[family][m.group(1)] = text
    token_names = {
        family: {value: sorted(n for n, v in tokens.items() if v == value) for value in set(tokens.values())}
        for family, tokens in token_px.items()
    }
    zero_is_token = {family: 0 in token_names[family] for family in token_px}
    dead = {family: [] for family in STYLE_LITERAL_PROPS}
    off_scale = {family: [] for family in STYLE_LITERAL_PROPS}
    derived = set()
    fallback = set()
    for context, selector, prop, value in _css_declarations(plain):
        for family, props in STYLE_LITERAL_PROPS.items():
            if prop not in props:
                continue
            for part in _top_level_parts(value):
                if part.startswith(STYLE_VAR):
                    if "," in part:
                        fallback.add((selector, prop, part))
                    continue
                kind, resolved = _style_classify(part, root)
                if kind in ("keyword", "token", "other"):
                    continue
                if kind == "zero" and not zero_is_token[family]:
                    continue
                if kind == "percent" and family != "radius":
                    continue
                if kind == "derived":
                    derived.add((selector, prop, part, resolved))
                duplicates = resolved is not None and resolved in token_names[family]
                if STYLE_LITERAL_SCOPE[family] == "any" or duplicates:
                    named = token_names[family].get(resolved, []) if duplicates else []
                    dead[family].append(
                        (
                            " ".join((*context, selector)),
                            prop,
                            part,
                            named or sorted(
                                n for n, v in token_src[family].items() if v == part
                            ),
                        )
                    )
                elif kind != "derived":
                    off_scale[family].append(part)
    for family, ceiling in STYLE_LITERAL_CEILING.items():
        found = dead[family]
        if len(found) <= ceiling:
            continue
        named = "; ".join(
            f"{where} {{ {prop}: {part} }} re-implements {', '.join(names) or 'a bare value'}"
            for where, prop, part, names in found[:6]
        )
        if len(found) > 6:
            named += f"; and {len(found) - 6} more"
        errors.append(
            f"style literals: {family} has {len(found)} literal value(s) against a "
            f"ceiling of {ceiling} — {named} — use var(<token>)"
            + (
                "; this family's scale is closed, so the ceiling is 0 and a bare "
                "value means a token is missing"
                if STYLE_LITERAL_SCOPE[family] == "any"
                else ""
            )
        )
    for family in STYLE_LITERAL_CEILING:
        print(
            f"Style literals: {family} {len(dead[family])}/{STYLE_LITERAL_CEILING[family]}"
            f" ({STYLE_LITERAL_SCOPE[family]} scope"
            + (", absolute: any bare value fails" if STYLE_LITERAL_SCOPE[family] == "any" else "")
            + ")"
        )
    for family in STYLE_LITERAL_CEILING:
        for where, prop, part, names in dead[family]:
            print(
                f"  {family} duplicate: {where} {{ {prop}: {part} }} = "
                f"{', '.join(names) or 'a bare value, no token carries it'}"
            )
    print(
        "Style literals: off-scale literal values "
        + ", ".join(
            f"{family} {len(off_scale[family])}"
            + (
                f" ({len(set(off_scale[family]))} distinct: "
                f"{', '.join(sorted(set(off_scale[family])))})"
                if off_scale[family]
                else ""
            )
            for family in STYLE_LITERAL_CEILING
        )
    )
    resolved_derived = sorted(f"{w} {{ {p}: {v} }} = {px}px" for w, p, v, px in derived if px is not None)
    print(
        f"Style literals: {len(derived)} calc()/clamp()/min()/max() value(s) in scope, "
        f"{len(resolved_derived)} of them resolved to a constant and compared"
        + (": " + "; ".join(resolved_derived) if resolved_derived else "")
        + f"; {len(fallback)} var() fallback(s) in scope"
    )
    print(f"Style literals: rem base {root:g}px — {root_note}")
    print(
        "Style literal scope: box spacing (margin, padding, gap, inset, "
        "scroll-margin, scroll-padding, top/right/bottom/left), border-radius, "
        "z-index. Box sizing (width, height, min-*, max-*, flex-basis) and the "
        "families Stage 2a never tokenised (color, font, letter-spacing, border "
        "and outline shorthand, box-shadow, transition, translate) are not "
        "examined."
    )


check_style_literals()

# 6e. The poster `sizes` attribute has exactly one definition, and it is policed as a
# whole value: the media condition AND the slot sizes after it. A computed-style
# comparison cannot see `sizes` at all, and `sizes` decides which image the
# browser fetches -- so a wrong breakpoint is a wrong band, and a wrong slot size is a
# proportionally wrong download inside a correct band. Only `sizes`/`imagesizes`
# attributes are read, and among those only the responsive ones (the ones carrying a
# media condition): a film page also declares `sizes="96px"` for the related thumbnail and
# `sizes="16x16"` and friends for its icons, and a `max-width` appearing anywhere else on
# a page says nothing about which poster width the browser will ask for. Freshness is
# 4b's job; this asks whether fresh is also right, and the answer has to hold for the slot
# sizes and not just for the edge.
#
# CONSISTENCY, AND WHAT IT CANNOT SEE. Comparing every emitted value to
# lib.poster_sizes() tells you the tree agrees with itself. It cannot tell you the
# agreed-on value is right: edit the value and every page follows it, and this check
# stays green through a change that is wrong in both directions at once -- which is what
# `(max-width: 767px) 92vw, 300px` was, +194% against the 240px mobile box at 767px and
# -6.25% against the 320px desktop box at 1280px. So the check that was missing is
# below, and it is a SHAPE check against the measured boxes, not a comparison to a
# literal: every slot must be a bare px length, and it must be at least as large as the
# box it describes. The direction is the whole point. A slot wider than its box only
# costs bytes; a slot narrower than it makes the browser fetch a source smaller than the
# box renders and scale it up into a blur, and that failure is invisible to every
# consistency gate in this file. A viewport-relative slot cannot be compared at all,
# which is why `92vw` is now an error and not a value: it is a guess about a box that is
# a fixed width, and it was wrong at both ends of its range.
POSTER_SIZES_ATTR = re.compile(
    r"""\b(?:image)?sizes\s*=\s*(?P<q>["'])(?P<value>[^"']*)(?P=q)""")
POSTER_SIZES_ASSIGNMENT = re.compile(r"^POSTER_SIZES\s*=\s*(?P<rhs>.+?)\s*$", re.MULTILINE)
POSTER_SLOT_LENGTH = re.compile(r"^(\d+(?:\.\d+)?)px$")
POSTER_SLOT_CONDITION = "(max-width: %dpx)" % BELOW_MD_MAX
POSTER_SIZES_PER_PAGE = 2
POSTER_SIZES_SLOTS = 2
POSTER_SIZES_SHADOW = re.compile(r"^\s*(?:def\s+poster_sizes|poster_sizes\s*[:=])", re.MULTILINE)
POSTER_BOX_SELECTOR = ".film-poster"
POSTER_BOX_DECLARATIONS = r"\b(?:min-)?(?:max-)?width\s*:\s*([^;]+);"
POSTER_BOX_PX = re.compile(r"(\d+(?:\.\d+)?)px")

# The main page's featured card is a second poster slot, not a second copy of the
# first: its boxes are FEATURED_BOX_* from lib, its band edge is the lg tier
# rather than the md one, and it lives on index.html rather than on the film
# pages. One per-page count because the main page carries exactly one of these
# posters, and one srcset because the candidates are built by featuredSrcset
# rather than written out.
FEATURED_SIZES_PER_PAGE = 1
FEATURED_SRCSETS_PER_PAGE = 1
FEATURED_SRCSET_ATTR = re.compile(
    r"""(?P<name>(?::|v-bind:)?srcset)\s*=\s*(?P<q>["'])(?P<value>[^"']*)(?P=q)""")
FEATURED_SRCSET_BINDING = ':srcset="featuredSrcset(item)"'


def sizes_attributes(text):
    found = collections.Counter()
    for match in POSTER_SIZES_ATTR.finditer(text):
        found[match.group("value")] += 1
    return found


def responsive_sizes(values):
    return {v: n for v, n in values.items() if POSTER_SLOT_CONDITION.split()[0] in v}


def poster_slot_slots(value):
    """(governing condition, [slot, ...]) for a `sizes` value.

    The condition is the value's own leading media condition, normalised to single
    spaces, or None when the value declares an unconditional slot. `(None, None)`
    means the leading condition never closes, so no slot can be attributed to a
    band and the caller must not go on to compare any of them.
    """
    text = value.strip()
    if text.startswith("("):
        depth = 0
        for i, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return " ".join(text[:i + 1].split()), [
                        p.strip() for p in text[i + 1:].split(",") if p.strip()]
        return None, None
    return None, [p.strip() for p in text.split(",") if p.strip()]


def check_poster_slot_shape(where, value, condition=POSTER_SLOT_CONDITION,
                            boxes=(POSTER_BOX_MOBILE, POSTER_BOX_DESKTOP),
                            label="poster"):
    """Every declared slot is a px length, and none is narrower than its box.

    `condition` and `boxes` are parameters because there is more than one poster
    slot in this project, not because this check got looser. The hero's two boxes
    are 240/320 keyed to the 767 edge; the featured card's are 156/194 keyed to
    the 1023 edge, and the two are different bands describing different boxes.
    Each is compared against its OWN pair, and each still fails a viewport-relative
    slot, a wrong edge, and a slot narrower than the box it names.
    """
    condition_wanted, boxes_wanted = condition, boxes
    condition, slots = poster_slot_slots(value)
    if slots is None:
        errors.append(
            f"Poster slot size: {where} declares sizes={value!r}, whose leading media "
            f"condition never closes, so no slot can be attributed to a band and this "
            f"check cannot tell which box it is describing"
        )
        return
    if condition is not None and condition != condition_wanted:
        errors.append(
            f"Poster slot size: {where} declares a responsive sizes={value!r} whose "
            f"condition is {condition!r}, not {condition_wanted!r}. The "
            f"breakpoint is the band the browser switches in"
        )
        return
    if len(slots) != POSTER_SIZES_SLOTS:
        errors.append(
            f"Poster slot size: {where} declares sizes={value!r} with {len(slots)} "
            f"slot(s), expected {POSTER_SIZES_SLOTS} -- one for the {boxes_wanted[0]}px "
            f"mobile box and one for the {boxes_wanted[1]}px desktop box. A single slot "
            f"describes neither band correctly"
        )
        return
    for slot, box, name in zip(slots, boxes_wanted, ("mobile", "desktop")):
        m = POSTER_SLOT_LENGTH.match(slot)
        if m is None:
            errors.append(
                f"Poster slot size: {where} declares the {name} slot as {slot!r}, which is "
                f"not a bare px length, so it cannot be compared with the {box}px {name} "
                f"box this {label} occupies. A viewport-relative or percentage slot is a "
                f"guess about a box that is a fixed width, and it is unbounded above, so "
                f"there is no value of it that this check could certify"
            )
            continue
        declared = float(m.group(1))
        if declared < box:
            errors.append(
                f"Poster slot size: {where} declares {slot} for the {name} {label} box, "
                f"which is {box}px -- {box - declared:g}px too narrow. A slot smaller than "
                f"its box makes the browser fetch a source smaller than the box renders "
                f"and scale it up, and no consistency check can see that: the emitted "
                f"value and lib.featured_poster_sizes() agree perfectly while both are "
                f"wrong. Declare {box}px or more"
            )


def check_poster_box_source():
    """The two box widths are measured facts, but they are facts about
    css/style.css, so the stylesheet is the witness. If the hero's caps move and
    lib.POSTER_BOX_MOBILE/POSTER_BOX_DESKTOP do not, every emitted slot is wrong
    and this says which px widths the hero rules actually carry. It reads
    declarations, not text, and it names what it found rather than only what it
    wanted."""
    path = ROOT / "css" / "style.css"
    if not path.exists():
        errors.append(
            f"Poster slot size: {path.name} is missing, so the box widths this check "
            f"compares slots against have no witness in the stylesheet at all"
        )
        return
    src = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    found = set()
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", src):
        if POSTER_BOX_SELECTOR not in m.group(1):
            continue
        for d in re.finditer(POSTER_BOX_DECLARATIONS, m.group(2)):
            found.update(float(px) for px in POSTER_BOX_PX.findall(d.group(1)))
    for name, box in (("POSTER_BOX_MOBILE", POSTER_BOX_MOBILE),
                      ("POSTER_BOX_DESKTOP", POSTER_BOX_DESKTOP)):
        if box not in found:
            errors.append(
                f"Poster slot size: lib.{name} is {box} but no {POSTER_BOX_SELECTOR} "
                f"width declaration in {path.name} carries {box:g}px -- the widths those "
                f"rules do carry are {sorted(found)}. The box is measured from the "
                f"stylesheet, so if the stylesheet moved the cap this constant is stale "
                f"and every slot compared against it is wrong"
            )


def check_poster_sizes():
    canonical = poster_sizes()
    check_poster_slot_shape("lib.poster_sizes()", canonical)
    check_poster_box_source()
    sources = [
        ("js/film.js", sizes_attributes((ROOT / "js" / "film.js").read_text(encoding="utf-8"))),
        ("js/film.min.js", sizes_attributes((ROOT / "js" / "film.min.js").read_text(encoding="utf-8"))),
    ]
    pages = sorted((ROOT / "films").glob("*/index.html"))
    if not pages:
        errors.append(
            "Poster sizes: films/ holds no index.html, so this check compared no page at "
            "all and would otherwise pass on an empty page set")
    stale = []
    responsive_total = 0
    fixed_total = 0
    for page in pages:
        values = sizes_attributes(page.read_text(encoding="utf-8"))
        fixed = sum(n for v, n in values.items() if "(max-width:" not in v)
        responsive = responsive_sizes(values)
        responsive_total += sum(responsive.values())
        fixed_total += fixed
        name = f"films/{page.parent.name}/index.html"
        if canonical not in responsive:
            stale.append((page.relative_to(ROOT).as_posix(), sorted(responsive) or ["none"]))
        for value in sorted(responsive):
            if value != canonical:
                check_poster_slot_shape(name, value)
        if sum(responsive.values()) != POSTER_SIZES_PER_PAGE:
            errors.append(
                f"Poster sizes: {name} declares {sum(responsive.values())} responsive "
                f"sizes attribute(s), expected {POSTER_SIZES_PER_PAGE} (a preload "
                f"imagesizes and an img sizes). A page with one site deleted still passes "
                f"every value check, so the count is checked, not printed")
    gen_src = (ROOT / "tools" / "gen_pages.py").read_text(encoding="utf-8")
    assignments = [m.group("rhs") for m in POSTER_SIZES_ASSIGNMENT.finditer(gen_src)]
    derived = bool(assignments) and all(
        rhs.split("#", 1)[0].strip() == "poster_sizes()" for rhs in assignments)
    if not derived:
        errors.append(
            f"Poster sizes: tools/gen_pages.py has {len(assignments)} POSTER_SIZES "
            f"assignment(s), {[a.strip() for a in assignments]}, and not all of them read "
            f"poster_sizes(). Only the LAST assignment takes effect, so a check that read "
            f"the first would certify a value that is never used and miss the one that is")
    shadows = [m.group(0).strip() for m in POSTER_SIZES_SHADOW.finditer(gen_src)]
    if shadows:
        errors.append(
            f"Poster sizes: tools/gen_pages.py binds the name poster_sizes itself -- "
            f"{shadows} -- so POSTER_SIZES = poster_sizes() reads that local and not the "
            f"lib import, and the structural check above passes while the value is no "
            f"longer the single source. gen_pages.py must only import the name")
    for where, values in sources:
        responsive = responsive_sizes(values)
        if canonical not in responsive:
            errors.append(
                f"Poster sizes: {where} carries {sorted(responsive) or ['no responsive sizes attribute']}"
                f", lib.poster_sizes() is {canonical!r}")
        for value in sorted(responsive):
            if value != canonical:
                check_poster_slot_shape(where, value)
    if stale:
        sample = "; ".join(f"{p} -> {f}" for p, f in stale[:3])
        errors.append(
            f"Poster sizes: {len(stale)} of {len(pages)} film pages do not carry exactly "
            f"{canonical!r} -- {sample} -- run gen_pages.py")
    print(
        f"Poster sizes: {canonical} -- single source lib.poster_sizes() on "
        f"BREAKPOINT_SCALE {list(BREAKPOINT_SCALE)}; slots {POSTER_BOX_MOBILE}px mobile / "
        f"{POSTER_BOX_DESKTOP}px desktop, each >= the measured box it describes; "
        f"{len(pages)} film page(s), "
        f"{responsive_total} responsive sizes attribute(s) checked "
        f"({len(pages) * POSTER_SIZES_PER_PAGE} expected) alongside {fixed_total} "
        f"fixed-size ones (related thumbnail, icons) deliberately ignored; "
        f"gen_pages.POSTER_SIZES "
        f"{'derived from lib' if derived else 'NOT derived from lib'} "
        f"({len(assignments)} assignment(s) in source)")


check_poster_sizes()


def check_featured_box_source():
    """The featured card's mobile box is a DERIVATION, not a literal, and its
    desktop box is not available to a stylesheet at all.

    Below lg the card is a flex item with an explicit basis, so the card's width
    IS written down in css/style.css. What is written down is the CARD, though,
    and the poster is the card's content box: the basis less one border width on
    each side. Reading the basis and comparing it to the slot directly would
    pass at 156 against a 154px poster and be 2px wrong in the direction that
    costs bytes, so this subtracts. From lg up the card is one track of
    `repeat(6, minmax(0, 1fr))` and its width is arithmetic over a container
    that is still growing at 1440 -- there is nothing here to read, which is why
    lib.FEATURED_BOX_DESKTOP is the maximum over the whole band and not any
    single width's measurement. That half is checked in tools/e2e.py against the
    rendered box, which is the only witness a computed box has.
    """
    path = ROOT / "css" / "style.css"
    if not path.exists():
        errors.append(
            f"Featured slot size: {path.name} is missing, so the mobile box this "
            f"check compares the emitted slot against has no witness at all"
        )
        return
    src = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    bases, borders = set(), set()
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", src):
        body = m.group(2)
        if ".featured-grid li" in m.group(1):
            for f in re.finditer(r"\bflex\s*:[^;]+;", body):
                bases.update(float(px) for px in POSTER_BOX_PX.findall(f.group(0)))
        if ".featured-card" in m.group(1) and ".featured-card-" not in m.group(1):
            for b in re.finditer(r"\bborder(?:-width)?\s*:\s*([^;]+);", body):
                borders.update(float(px) for px in POSTER_BOX_PX.findall(b.group(1)))
    if not bases:
        errors.append(
            f"Featured slot size: no `.featured-grid li` rule in {path.name} declares a "
            f"px `flex` basis, so the rail's track width has no witness and "
            f"lib.FEATURED_BOX_MOBILE cannot be derived from the stylesheet at all"
        )
        return
    border = max(borders) if borders else 0.0
    derived = sorted(b - 2 * border for b in bases)
    if FEATURED_BOX_MOBILE not in derived:
        errors.append(
            f"Featured slot size: lib.FEATURED_BOX_MOBILE is {FEATURED_BOX_MOBILE} but the "
            f"`flex` basis in `.featured-grid li` is {sorted(bases)} and the card's border "
            f"{border:g}px, which makes the poster {derived}px. The rail's poster box is "
            f"the track less the border on each side, so if the track or the border moved "
            f"this constant is stale and every slot compared against it is wrong. Note "
            f"that the DESKTOP box ({FEATURED_BOX_DESKTOP}) has no such witness: it is a "
            f"grid fraction, and tools/e2e.py measures the rendered box instead"
        )


def check_featured_poster_sizes():
    """The main page's featured card declares its own slot, and it is not the
    hero's. Two different posters, two different boxes, two different bands:
    the hero is 240/320 keyed to the 767 edge, the featured card is 156/194
    keyed to the 1023 edge. Each is checked against its OWN boxes, so a value
    lifted from the film pages onto index.html is caught rather than passed."""
    canonical = featured_poster_sizes()
    check_poster_slot_shape(
        "lib.featured_poster_sizes()", canonical,
        condition=FEATURED_SLOT_CONDITION,
        boxes=(FEATURED_BOX_MOBILE, FEATURED_BOX_DESKTOP),
        label="featured card")
    check_featured_box_source()
    path = ROOT / "index.html"
    if not path.exists():
        errors.append(
            f"Featured slot size: {path.name} is missing, so this check compared no "
            f"page at all and would otherwise pass on an empty page set")
        return
    text = path.read_text(encoding="utf-8")
    values = sizes_attributes(text)
    responsive = responsive_sizes(values)
    if canonical not in responsive:
        errors.append(
            f"Featured slot size: index.html carries {sorted(responsive) or ['no responsive sizes attribute']}, lib.featured_poster_sizes() is {canonical!r}"
        )
    for value in sorted(responsive):
        if value != canonical:
            check_poster_slot_shape(
                "index.html", value,
                condition=FEATURED_SLOT_CONDITION,
                boxes=(FEATURED_BOX_MOBILE, FEATURED_BOX_DESKTOP),
                label="featured card")
    total = sum(responsive.values())
    if total != FEATURED_SIZES_PER_PAGE:
        errors.append(
            f"Featured slot size: index.html declares {total} responsive sizes "
            f"attribute(s), expected {FEATURED_SIZES_PER_PAGE}. A card deleted down to a "
            f"bare `src` still passes every value check, so the count is checked, not "
            f"printed"
        )
    srcsets = [m.group(0).strip() for m in FEATURED_SRCSET_ATTR.finditer(text)]
    if len(srcsets) != FEATURED_SRCSETS_PER_PAGE:
        errors.append(
            f"Featured slot size: index.html declares {len(srcsets)} srcset attribute(s), "
            f"expected {FEATURED_SRCSETS_PER_PAGE}. Without one the card fetches the 400w "
            f"rung into a {FEATURED_BOX_DESKTOP}px box, and the slot above would describe "
            f"a choice the page never offers the browser"
        )
    elif srcsets[0] != FEATURED_SRCSET_BINDING:
        errors.append(
            f"Featured slot size: index.html binds srcset to {srcsets[0]!r}, not "
            f"{FEATURED_SRCSET_BINDING!r}. A renamed helper would leave the candidates "
            f"unbuilt and this page fetching its `src`, and every value check above would "
            f"still be green because a srcset with no candidates is not a sizes question"
        )
    for js_name in ("js/app.js", "js/app.min.js"):
        js_text = (ROOT / js_name).read_text(encoding="utf-8")
        if not re.search(r"function\s+featuredSrcset\s*\(", js_text):
            errors.append(
                f"Featured slot size: {js_name} does not define featuredSrcset, which is "
                f"what index.html binds the card's srcset to"
            )
    print(
        f"Featured slot size: {canonical} -- single source "
        f"lib.featured_poster_sizes() on the {FEATURED_SLOT_CONDITION} edge; slots "
        f"{FEATURED_BOX_MOBILE}px below lg / {FEATURED_BOX_DESKTOP}px from lg up, each "
        f">= the measured box it describes; index.html carries {total} responsive sizes "
        f"({FEATURED_SIZES_PER_PAGE} expected) bound to {FEATURED_SRCSET_BINDING}, and "
        f"the {FEATURED_BOX_MOBILE}px mobile box is derived from the `flex` basis less the "
        f"card's border in css/style.css; the {FEATURED_BOX_DESKTOP}px desktop box is a "
        f"grid fraction and is measured by tools/e2e.py instead")


check_featured_poster_sizes()


# 6e.2. The related card's own slot, and it is a FIXED one, so it is a different
# shape of gate from either existing poster: the hero and the featured card both
# declare a responsive `sizes` and are checked as such, while this card is
# 134px at 375 and 134px at 1920 and gets a bare `sizes="134px"`.
#
# The direction of the failure is the whole reason this check exists. A slot
# WIDER than the box only costs bytes, so the 27% over-declaration it shipped
# with (sizes="170px" for a 134px poster) was invisible. A slot NARROWER than
# the box makes the browser fetch a source smaller than the box renders and
# scale it up into a blur, and nothing else in the tree can see that: the emitted
# value and any canonical value agree perfectly while both are wrong.
RELATED_SIZES_BINDING = "gen_pages.RC_CARD"
RELATED_BOX = 134
RELATED_POSTER_ATTRS = re.compile(
    r'\bsizes="([^"]*)"[^>]*?\bwidth="(\d+)"[^>]*?\bheight="(\d+)"')


def check_related_poster_slot():
    """The related card's slot must be a bare px length no narrower than its box.

    And the box is not a constant here either -- it is DERIVED, from the card's
    width less its padding and its border, and the card's width is written down
    in two places in css/style.css with two different mechanisms: `flex: 0 0
    160px` for the scroller track below 1024, and `minmax(0, 160px)` for the
    six-column grid above it. Both state 160, so both are read and the smaller is
    used: the grid's six columns are ALLOWED to shrink to fit a 969px track at
    1024 (measured 151.5), so 160 is the widest this card ever renders, and
    certifying a slot against a larger number is how a blur ships.
    """
    path = ROOT / "css" / "style.css"
    if not path.exists():
        errors.append(
            f"Related slot size: {path.name} is missing, so the card width this "
            f"derives the box from has no witness at all"
        )
        return
    src = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    root, _ = _style_root_font_px(src)

    # `.related a.rc` declares `padding: var(--space-3)`, not a px literal, so
    # this check resolves the token exactly as the style-literal gate does: read
    # the declaration out of `:root` and convert against the root font-size. A
    # raw `POSTER_BOX_PX` scan finds nothing there and would raise, which is why
    # the literal path alone cannot be reused.
    tokens = {}
    for tname, tval in re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+);", src):
        kind, resolved = _style_classify(tval.strip(), root)
        if kind == "length":
            tokens[tname] = resolved

    def to_px(value):
        """The px a box-spacing value resolves to, or None if it has no length."""
        value = value.strip()
        var = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", value)
        if var:
            return tokens.get(var.group(1))
        px = POSTER_BOX_PX.fullmatch(value)
        if px:
            return float(px.group(1))
        kind, resolved = _style_classify(value, root)
        return resolved if kind == "length" else None

    def box_part(value):
        """The px length in `padding: <v>`-style shorthand: every side, and the
        box is symmetric here, so the max is the side. `0 12px` is a real
        possibility and 0 is a length too, hence no truthiness test."""
        found = [to_px(part) for part in value.split()]
        found = [f for f in found if f is not None]
        return max(found) if found else None

    widths, pad, border = set(), None, None
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", src):
        sel, body = m.group(1), m.group(2)
        # The card's own box and the width that tracks it are DIFFERENT rules --
        # `.related a.rc` carries the padding and border, `.related li` the flex
        # basis and the grid cap. Matching both against one selector would read
        # neither, which is what the first version of this check did.
        if ".related li" in sel:
            # The scroller's px basis and the grid's px track cap both state the
            # card's width; `flex: 1` / `auto` state nothing and the regexes skip
            # them, so a regression back to `1fr` fails this rather than passing.
            for f in re.finditer(r"\bflex\s*:\s*[^;]*?\b(\d+(?:\.\d+)?)px\s*;?", body):
                widths.add(float(f.group(1)))
            for g in re.finditer(r"minmax\(\s*0\s*,\s*(\d+(?:\.\d+)?)px\s*\)", body):
                widths.add(float(g.group(1)))
        if re.search(r"\.related\s+a\.rc(?![\w-])", sel):
            for p in re.finditer(r"\bpadding\s*:\s*([^;]+);", body):
                if pad is None:
                    pad = box_part(p.group(1))
            for b in re.finditer(r"\bborder(?:-width)?\s*:\s*([^;]+);", body):
                if border is None:
                    border = box_part(b.group(1))

    if not widths:
        errors.append(
            f"Related slot size: no `.related li` rule in {path.name} declares a px "
            f"card width -- no `flex: 0 0 <N>px` basis and no "
            f"`minmax(0, <N>px)` grid cap -- so the poster box cannot be derived from "
            f"the stylesheet and this constant has no witness"
        )
        return
    card = min(widths)
    if pad is None or border is None:
        errors.append(
            f"Related slot size: `.related a.rc` in {path.name} declares no padding or "
            f"border, so the poster box cannot be derived from the {card:g}px card "
            f"(the poster is the card's content box)"
        )
        return

    derived = card - 2 * pad - 2 * border
    if abs(derived - RELATED_BOX) > 0.01:
        errors.append(
            f"Related slot size: the card is {card:g}px in css/style.css and the poster "
            f"is the card's content box, {card:g} less {pad:g}px of padding and "
            f"{border:g}px of border on each side, which makes it {derived:g}px. "
            f"verify.RELATED_BOX is {RELATED_BOX}px. If the card, its padding or its "
            f"border moved, this constant is stale and every slot compared against it "
            f"is wrong"
        )

    owner = ROOT / "tools" / "gen_pages.py"
    found = RELATED_POSTER_ATTRS.findall(owner.read_text(encoding="utf-8")) \
        if owner.exists() else []
    if len(found) != 1:
        errors.append(
            f"Related slot size: {RELATED_SIZES_BINDING} carries {len(found)} "
            f"related-poster `sizes`/`width`/`height` attribute triples, expected 1. "
            f"The card has one source, so more than one means a second copy was "
            f"pasted into the fragment"
        )
        return
    sizes, w, h = found[0]
    px = POSTER_BOX_PX.search(sizes)
    slot = float(px.group(1)) if px else None
    if slot is None:
        errors.append(
            f"Related slot size: the related card declares sizes={sizes!r}, which is not "
            f"a px length. A viewport-relative slot is unbounded above, so no value of "
            f"it could be certified"
        )
        return
    if slot < RELATED_BOX:
        errors.append(
            f"Related slot size: the related card declares sizes={sizes!r} for a poster "
            f"that renders {RELATED_BOX}px wide. A slot NARROWER than its box makes the "
            f"browser fetch a source smaller than the box renders and scale it into a "
            f"blur; only a wider slot merely costs bytes. This is the direction "
            f"check_poster_slot_shape exists to stop, and the one the old 170px slot "
            f"got wrong in the other direction"
        )
    if (int(w), int(h)) != (RELATED_BOX, RELATED_BOX * 3 // 2):
        errors.append(
            f"Related slot size: the related card's width/height attributes are "
            f"{w}x{h}, expected {RELATED_BOX}x{RELATED_BOX * 3 // 2}. The intrinsic "
            f"ratio is what reserves the card's height before the poster loads, and it "
            f"must be the 2:3 the box renders"
        )
    print(
        f"Related slot size: sizes={sizes!r} -- bare px, no media condition, and "
        f"{'>=' if slot >= RELATED_BOX else '<'} the {RELATED_BOX}px box it describes, "
        f"derived in css/style.css from the {card:g}px card less {pad:g}px of padding "
        f"and {border:g}px of border on each side; the card states {card:g}px in both "
        f"its `flex` basis and its grid cap, and tools/e2e.py measures the rendered box "
        f"at both tiers"
    )


check_related_poster_slot()


# The channel link in the header. Five hand-maintained copies exist -- index.html,
# js/film.js's FILM_TEMPLATE (which generates 155 pages), and about/404/privacy --
# and nothing about the site's structure would notice if one of them lost the
# anchor, so this check is the only witness. Each copy is checked for the href, the
# new-tab rel pair, and a sprite reference that resolves to a symbol that exists;
# the relative prefix is checked per page because it is the one thing that differs
# between them and the one thing that fails silently (a wrong prefix 404s, and a
# missing icon glyph renders as an empty box rather than an error).
# The header's channels, as DATA. A second channel cannot be added to four
# parallel Telegram constants without a second copy of each, and parallel copies
# drift silently -- which is how an anchor reached about.html's dead noscript
# copy while the live page had none. One table, and the pattern below is built
# per row, so a third messenger is one row here plus one row of i18n.
CHANNELS = (
    {
        "brand": "tg",
        "url": "https://t.me/wh_lab",
        "symbol": "icon-telegram",
        "viewbox": "0 0 16 16",
        "key": "telegramChannel",
        "label_key": "telegramLabel",
        "aria_ru": "Канал в Telegram: Whitehat Lab",
        "colour": "--telegram",
    },
    {
        "brand": "max",
        "url": ("https://max.ru/join/"
                "ByzPb9lbZJwBbvKvRvi3ioBNaFF9TyuXDy5vrIX48vs"),
        "symbol": "icon-max",
        "viewbox": "0 0 1000 1000",
        "key": "maxChannel",
        "label_key": "maxLabel",
        "aria_ru": "Канал в Max: Whitehat Lab",
        "colour": "--max",
    },
)

CHANNEL_COPIES = (
    ("index.html", "static/share.svg"),
    ("js/film.js", "../../static/share.svg"),
    ("js/film.min.js", "../../static/share.svg"),
    # about.html carries a header inside <noscript> and the LIVE one is rendered
    # from js/about.js, so both are copies and both are needed: the first is what a
    # no-JS reader gets, the second is what everyone else gets. Reading only
    # about.html is how the anchor ended up in the noscript copy while the live
    # page had none -- and the regex could not tell, because both contain it.
    ("about.html", "static/share.svg"),
    ("js/about.js", "static/share.svg"),
    ("js/about.min.js", "static/share.svg"),
    ("404.html", "static/share.svg"),
    ("privacy.html", "static/share.svg"),
)


def channel_item_re(ch):
    """One channel's mark+anchor inside its `.ch-item`.

    Built per row rather than written once, because the three things that vary
    between channels -- the brand modifier, the viewBox and the href -- are
    exactly the things a hard-coded pattern would have frozen at Telegram's.
    """
    b, vb = ch["brand"], re.escape(ch["viewbox"])
    return re.compile(
        r'<span class="ch-item">'
        # the mark first, with its own sprite reference per depth
        r'<svg[^>]*class="icon ch-mark ch-mark--%s"[^>]*viewBox="%s"[^>]*>'
        r'<use href="([^"]+)"></use></svg>'
        # then the anchor IMMEDIATELY after it, with nothing in between
        r'<a[^>]*class="ch-link ch-link--%s"[^>]*href="([^"]+)"[^>]*target="_blank"'
        r'[^>]*rel="noopener noreferrer"[^>]*'
        # the STATIC label, not a `:aria-label` binding: the lookbehind is what
        # keeps a Vue page's binding from being read as the fallback
        r'(?<!:)aria-label="([^"]*)"'
        # text only: no second <use> may reopen inside the anchor
        r'[^>]*>(?:(?!</a>).)*?</a>'
        r'</span>' % (b, vb, b),
        re.S,
    )


# The row body, matched up to the `</div>` that closes `.brand-text` rather
# than to a fixed number of `</span>`: the row's children are `.ch-item`
# spans, so a terminator written for a fixed item count breaks the moment a
# channel is added. The first version ended on three closes and reported
# "no .ch-row" on every copy -- which reads like a missing row rather than
# like a wrong terminator, and the individual items are then checked inside.
CHANNEL_ROW_RE = re.compile(r'<span class="ch-row">(.*?)</div>', re.S)

# The static label is a FALLBACK for the moment before a page's own mechanism
# runs. A language-aware page that carries the fallback without overriding it
# reads one language forever, so each mechanism is named here and required in
# the file that owns it: a Vue binding on the two Vue pages, an explicit write on
# the two static pages that have their own inline translation table. The MAX
# copy is a second entry because a page can override Telegram and forget MAX --
# which is a real shape, since the two arrived together.
CHANNEL_OVERRIDES = (
    ("index.html", ':aria-label="t.telegramChannel"', ':aria-label="t.maxChannel"'),
    ("js/film.js", ':aria-label="t.telegramChannel"', ':aria-label="t.maxChannel"'),
    ("js/film.min.js", "t.telegramChannel", "t.maxChannel"),
    ("js/about.js", ':aria-label="t.telegramChannel"', ':aria-label="t.maxChannel"'),
    ("js/about.min.js", "t.telegramChannel", "t.maxChannel"),
    # about.html is the <noscript> tier: no script runs there to translate
    # anything, so a literal is correct rather than an oversight.
    ("about.html", None, None),
    ("404.html", 'chTelegram.setAttribute("aria-label", t.telegramChannel)',
     'chMax.setAttribute("aria-label", t.maxChannel)'),
    ("privacy.html", 'chTelegram.setAttribute("aria-label", t.telegramChannel)',
     'chMax.setAttribute("aria-label", t.maxChannel)'),
)


def _srgb_lum(rgb):
    """WCAG relative luminance of an (r, g, b) triple of 0-255 ints."""
    out = []
    for c in rgb:
        c = c / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def _contrast(a, b):
    la, lb = _srgb_lum(a), _srgb_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hex_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _over(fg_rgb, alpha, bg_rgb):
    """Alpha-composite `fg` at `alpha` over `bg`, which is what the dot grid does."""
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg_rgb, bg_rgb))


def check_channel_colour():
    """Each channel's glyph must be painted in a colour that clears 3:1 against
    the surface it actually sits on, in BOTH themes, and each token must be
    declared as many times as its own contrast requires.

    Four defects this closes, all of which shipped at least once:

    1. **The glyph painted BLACK in both themes.** `static/share.svg` declares
       no fill on any of its symbols -- every consumer inherits
       `fill: currentColor` from `.share-ico`, and the header link is not a
       member of that class. With only `class="icon"` the path fell back to the
       SVG default, so a dark disc sat on a near-black header and the partner
       read it as "paint it in Telegram's colours" when the real complaint was a
       black blob wearing a Telegram logo. A screenshot is a poor guard, so the
       declaration is asserted here.

    2. **A brand hue that cannot carry its own glyph.** The Telegram brand hex
       measures 7.15:1 on the dark background and 2.56:1 on the light one, under
       the 4.5:1 text floor and the 3:1 graphics floor both -- so `--telegram` is
       a PAIR, a darker value of the same hue in light. MAX's three gradient
       stops each fail in one theme or the other, and one derived value clears
       3:1 in both, so `--max` is a SINGLE value. Those two shapes are different
       because their contrast is different, and the count is checked so a fourth
       declaration cannot quietly appear.

    3. **`currentColor` is wrong even once a fill exists.** On the `<svg>`
       element `currentColor` resolves to THAT element's own computed `color`,
       and `svg:not(.heart) { color: var(--accent) }` sets it -- so a mark
       written that way came out accent-purple beside a label in the site's own
       link colour. The token is named outright instead.

    4. **The selector must be the CLASS.** The mark moved out of the `<a>` (the
       partner's ruling: "but you put the icon in the href too"), so a
       descendant selector matches nothing -- silently, and with every other
       gate green. A selector that names a shape rather than an element stops
       working the moment the shape moves, and a dead fill declaration looks
       exactly like the colour defect it used to cause.

    And the sprite must PARSE. XML forbids a double hyphen inside a comment, and
    a sprite that breaks that way keeps every expected id while resolving nothing
    at all -- every `<use>` of it goes 0x0, silently. Grepping the file for the
    id cannot see it, which is how the first version of that note broke the
    sprite while describing how not to.
    """
    problems = []
    css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")

    def decls(tok):
        return re.findall(r"^\s*%s:\s*(#[0-9a-fA-F]{3,8})\s*;" % re.escape(tok),
                          css, re.M)

    # The DECLARED SHAPE, which differs per token and is checked per token.
    # "declared twice" is not a style preference, it is the record of which
    # brand values fail on which background; "declared once" is the record that
    # this brand needs no second value.
    expected_counts = {"--telegram": 2, "--max": 1}
    for tok, want in expected_counts.items():
        got = decls(tok)
        if len(got) != want:
            problems.append(
                f"{tok} is declared {len(got)} time(s), expected {want}. This is "
                f"not a style preference: --telegram is a PAIR because the brand "
                f"hex measures 2.56:1 on the light background, under both the 4.5:1 "
                f"text floor and the 3:1 graphics floor, and --max is a SINGLE "
                f"value because one derived value clears 3:1 in both themes. A "
                f"fourth declaration would be a value shipped with no defect to "
                f"justify it, which is the same mistake as re-adding a deleted "
                f"token"
            )
        elif want == 2 and got[0].lower() == got[1].lower():
            problems.append(
                f"{tok} is {got[0]} in BOTH themes, so one of them is carrying a "
                f"value measured to fail on its own background"
            )

    # The CONTRAST, computed rather than trusted. Both the glyph colour and the
    # surface it sits on are literal text in this file, so the ratio is
    # arithmetic and a browser is not required to be honest about it.
    # A glyph colour and the ground it is painted on are a PAIR, so the themes
    # and the surfaces are PAIRED rather than nested. The first version nested
    # them and therefore tested a dark value against the light background too:
    # `#26a5e4` came out "2.19:1 against the dark surface" when it measures
    # 7.15:1 there. A token declared once is active in BOTH themes; a token
    # declared twice is one value per theme, dark first because that is the
    # order they appear in `:root` then `:root.light`.
    bg_dark = decls("--bg")[0] if decls("--bg") else "#0a0a0b"
    bg_light = "#f5f6f6"
    dots = re.findall(r"^\s*--dot:\s*rgba\(([\d.]+),\s*([\d.]+),\s*([\d.]+),"
                      r"\s*([\d.]+)\)", css, re.M)
    surfaces = {
        "dark": [_hex_rgb(bg_dark)],
        "light": [_hex_rgb(bg_light)],
    }
    if dots:
        # body paints a 1px dot grid over --bg, and a 1px glyph stroke can land
        # on a dot, so the dot composite is a surface a reader can actually hit.
        # The blends are checked against the figures already measured in a
        # browser (22,22,23 dark and 228,229,229 light) by the caller.
        if len(dots) >= 2:
            surfaces["light"].append(_over(
                (0.0, 0.0, 0.0), float(dots[-1][3]), _hex_rgb(bg_light)))
        surfaces["dark"].append(_over(
            (float(dots[0][0]), float(dots[0][1]), float(dots[0][2])),
            float(dots[0][3]), _hex_rgb(bg_dark)))

    measured = {}
    for ch in CHANNELS:
        vals = decls(ch["colour"])
        if not vals:
            continue
        active = {"dark": vals[0],
                  "light": vals[1] if len(vals) > 1 else vals[0]}
        for theme, v in active.items():
            per_surface = {}
            for idx, srgb in enumerate(surfaces[theme]):
                per_surface["dot" if idx else "bg"] = _contrast(
                    _hex_rgb(v), srgb)
            measured[(ch["brand"], theme)] = per_surface
            worst = min(per_surface.values())
            if worst < 3.0:
                problems.append(
                    f"{ch['brand']}'s glyph colour {v} measures {worst:.2f}:1 in the "
                    f"{theme} theme, under the 3:1 floor that 1.4.11 sets for a "
                    f"non-text graphic. Measured on the page background AND on a "
                    f"composited dot pixel, because body paints a 1px dot grid "
                    f"over --bg and a 1px stroke can land on one"
                )

    # The fill, on the brand MODIFIER. A bare `.ch-mark` rule holding
    # var(--telegram) would paint the MAX glyph Telegram blue on every page,
    # which is the shape of defect 1 and 2 combined.
    for ch in CHANNELS:
        pat = r"\.ch-mark--%s\s*\{[^}]*fill:\s*var\(%s\)" % (
            re.escape(ch["brand"]), re.escape(ch["colour"]))
        if not re.search(pat, css, re.S):
            problems.append(
                f".ch-mark--{ch['brand']} has no `fill: var({ch['colour']})`. "
                f"Three defects hide here. With no fill at all the path falls back "
                f"to the SVG default and paints BLACK in both themes; with "
                f"`currentColor` it resolves to the <svg> element's own color, "
                f"which `svg:not(.heart)` sets to var(--accent), so the mark came "
                f"out accent-purple; and the fill must sit on the brand MODIFIER, "
                f"because a bare `.ch-mark` rule would paint every channel in one "
                f"brand's colour"
            )

    # The anchor keeps the site's own link colour and never a brand hue.
    for tok in expected_counts:
        tg_rule = re.search(r"^\.ch-link\s*\{([^}]*)\}", css, re.M)
        if tg_rule and re.search(r"color:\s*var\(%s\)" % re.escape(tok),
                                 tg_rule.group(1)):
            problems.append(
                f".ch-link sets `color: var({tok})`. The partner ruled twice on "
                f"this: the anchor is an ordinary link in the site's own idiom, "
                f"the same treatment `.title-cell a` gives a film title, and only "
                f"the GLYPH carries the brand colour. A coloured word beside the "
                f"site's link styling reads as a different kind of thing rather "
                f"than as a link to a channel"
            )

    # A descendant selector for the mark cannot match, and cannot be seen not to.
    if re.search(r"\.ch-link\s+svg\s*\{", css):
        problems.append(
            "there is a `.ch-link svg` rule, but the mark is no longer a "
            "descendant of the anchor -- it is its previous sibling. That "
            "selector matches nothing, so the fill would be gone and the path "
            "would fall back to the SVG default: BLACK, in both themes, reading "
            "as a colour problem rather than a dead rule. Style `.ch-mark`"
        )

    try:
        ET.fromstring((ROOT / "static" / "share.svg").read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        problems.append(
            f"static/share.svg does not parse as XML: {exc}. Every symbol in it "
            f"stops resolving while the ids are all still present, so every <use> "
            f"renders 0x0 and the page looks merely empty rather than broken"
        )

    for p in problems:
        errors.append(f"Channel colour: {p}")
    if not problems:
        bits = []
        for ch in CHANNELS:
            for theme in ("dark", "light"):
                m = measured.get((ch["brand"], theme), {})
                if m:
                    bits.append("%s %s %.2f:1" % (ch["brand"], theme,
                                                  min(m.values())))
        print(
            f"Channel colour: {len(CHANNELS)} channels painted through brand "
            f"modifiers, each token declared exactly as its own contrast "
            f"requires ({'; '.join('%s x%d' % (k, v) for k, v in expected_counts.items())}); "
            f"worst measured [{'; '.join(bits)}] against the worse of --bg and a "
            f"composited dot pixel, all clearing 3:1; the anchor inherits the "
            f"site's link colour; static/share.svg parses as XML"
        )


def check_channel_link():
    """Every channel in `CHANNELS` must be present, correct and resolvable on
    every page type that carries a header.

    The header is hand-maintained in EIGHT places -- `index.html`, the
    `FILM_TEMPLATE` in `js/film.js` (which generates all 156 film pages), the
    `<noscript>` copy in `about.html` beside the live one rendered from
    `js/about.js`, then `404.html` and `privacy.html`, plus both generated
    `.min.js` copies. Nothing else in the project compares them, so a copy that
    lost a link, kept a stale href, or pointed its `<use>` at a sprite path
    wrong for its own depth would ship silently.

    The assertions are per CHANNEL and per COPY, both from the table rather than
    from constants frozen at Telegram's values. That is the whole point of the
    table: a second channel used to be unrepresentable here, and adding one to
    the markup while these assertions still named Telegram would have left the
    run green with the new link unchecked.
    """
    problems = []
    sprite = (ROOT / "static" / "share.svg").read_text(encoding="utf-8")
    for ch in CHANNELS:
        if 'id="%s"' % ch["symbol"] not in sprite:
            problems.append(
                f"static/share.svg has no {ch['symbol']!r} symbol, so every copy "
                f"of the {ch['brand']} link points at a glyph that cannot resolve"
            )
        if ch["viewbox"] not in sprite:
            problems.append(
                f"static/share.svg does not declare viewBox {ch['viewbox']!r} "
                f"for {ch['symbol']!r}. The path is authored in those units, so a "
                f"different viewBox renders it at a fraction of its size, pinned "
                f"into a corner -- which is how the Telegram glyph once rendered "
                f"at 67%"
            )

    seen_labels = {ch["brand"]: {} for ch in CHANNELS}
    for rel, prefix in CHANNEL_COPIES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        row = CHANNEL_ROW_RE.search(text)
        if not row:
            problems.append(
                f"{rel}: no .ch-row. Expected <span class=\"ch-row\"> holding one "
                f".ch-item per channel: the mark's <use> pointing at "
                f"{prefix}#<symbol> followed IMMEDIATELY by <a class=\"ch-link "
                f"ch-link--<brand>\" href=... target=\"_blank\" "
                f"rel=\"noopener noreferrer\" aria-label=\"...\"> holding text "
                f"only. The mark is a SIBLING of the anchor, not a child: it used "
                f"to be inside the <a>, and then a border-bottom on the "
                f"inline-flex anchor underlined the glyph as well as the label. "
                f"The header is hand-maintained in eight places and nothing else "
                f"compares them"
            )
            continue
        body = row.group(1)
        for ch in CHANNELS:
            found = channel_item_re(ch).search(body)
            if not found:
                problems.append(
                    f"{rel}: the channel row has no {ch['brand']} item matching "
                    f"the expected shape. Every row in CHANNELS must be present, "
                    f"or losing one is a shorter row rather than a failure"
                )
                continue
            use, href, label = found.groups()
            if href != ch["url"]:
                problems.append(
                    f"{rel}: the {ch['brand']} link href is {href!r}, expected "
                    f"{ch['url']!r}")
            if use != "%s#%s" % (prefix, ch["symbol"]):
                problems.append(
                    f"{rel}: the {ch['brand']} sprite reference is {use!r}, "
                    f"expected {prefix + '#' + ch['symbol']!r}. The page's own "
                    f"depth decides the prefix and getting it wrong 404s silently"
                )
            if label != ch["aria_ru"]:
                problems.append(
                    f"{rel}: the {ch['brand']} static aria-label is {label!r}, "
                    f"expected {ch['aria_ru']!r}")
            seen_labels[ch["brand"]].setdefault(label, []).append(rel)

        # every item in the row must be one this gate knows about, so a THIRD
        # channel added to the markup without a row in CHANNELS is caught here
        # rather than sailing through as an unexamined item
        known = len(CHANNELS)
        found_items = len(re.findall(r'<span class="ch-item">', body))
        if found_items != known:
            problems.append(
                f"{rel}: the channel row holds {found_items} .ch-item(s) but "
                f"CHANNELS declares {known}. A channel present in the markup but "
                f"absent from the table is a link nothing checks -- its href, its "
                f"sprite and its label are all unverified. Add a row to CHANNELS"
            )

    for ch in CHANNELS:
        brands = seen_labels[ch["brand"]]
        if len(brands) > 1:
            problems.append(
                f"the copies disagree on the {ch['brand']} static aria-label, "
                + "; ".join(f"{v!r} in {', '.join(f)}" for v, f in brands.items())
                + ". One of them will read the wrong language to a screen reader"
            )

    for rel, needed_tg, needed_max in CHANNEL_OVERRIDES:
        if needed_tg is None:
            continue
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needed, ch in ((needed_tg, CHANNELS[0]), (needed_max, CHANNELS[1])):
            if needed not in text:
                problems.append(
                    f"{rel}: the {ch['brand']} static label is a fallback for the "
                    f"moment before this page's own mechanism runs, but nothing "
                    f"overrides it -- expected {needed!r} in the file. A page with "
                    f"a working language toggle that keeps the fallback reads one "
                    f"language forever, and the two channels arrived together, so "
                    f"one can be overridden while the other is forgotten"
                )

    for p in problems:
        errors.append(f"Channel link: {p}")
    if not problems:
        summary = ", ".join(
            f"{ch['brand']} -> {ch['url']}" for ch in CHANNELS)
        print(
            f"Channel link: {len(CHANNELS)} channels on {len(CHANNEL_COPIES)} "
            f"page type(s) [{summary}]; target=_blank rel=noopener noreferrer; "
            f"each mark is its anchor's previous sibling; both sprite symbols "
            f"resolve with the right prefix per depth; static labels agree; every "
            f"language-aware copy overrides BOTH fallbacks"
        )


check_channel_link()
check_channel_colour()


# 6f. The media-condition gate. A width edge is the only thing that decides which
# rule-set a viewport gets, and before this block the pre-Stage-2b ad-hoc set
# (480 / 525 / 720 / 721 / 950) could be reintroduced one literal at a time with
# every other check green: 6d only examines box-spacing properties and 6e only
# the `sizes` attribute, so neither ever reads an at-rule prelude. This block
# parses the preludes themselves, which is what the browser reads.
#
# SCOPE: the stylesheets named in CSS_MEDIA_FILES, and nothing else. It is
# deliberately not a repository grep. A bare 480 or 950 is equally at home in
# prose (this file's own docstring, AGENTS.md, the gitignored spec), in an SVG
# path (static/share.svg), and in a table of retired edges, so a repo-scoped
# version reports violations in files that are already correct, its remedy ("add
# the value to lib.CSS_MEDIA_EDGES") does not even apply outside a stylesheet,
# and every hit would need a human to decide whether it is prose. A second
# stylesheet is added by appending its path to CSS_MEDIA_FILES. The 720 edge also
# lived in js/film.js and gen_pages.POSTER_SIZES; those two are policed by 6e at
# the value level, by reading the emitted `sizes` attributes rather than the text.
CSS_MEDIA_FILES = ("css/style.css",)
CSS_MEDIA_PREFERS = ("@media (prefers-color-scheme: dark)", "@media (prefers-reduced-motion: reduce)")
CSS_MEDIA_CONTAINER = "@container scroll-state(scrollable: top)"
CSS_MEDIA_XS_EDGE = BREAKPOINT_SCALE[0]
CSS_MEDIA_XS_BLOCKS = 2
CSS_MEDIA_RETIRED_NOTE = {
    480: "480 was the pre-Stage-2b xs edge and collapses onto %d, which is BREAKPOINT_SCALE[0]" % BREAKPOINT_SCALE[0],
    525: "525 was the pre-Stage-2b featured/related edge and collapses onto %d, which is BREAKPOINT_SCALE[0]" % BREAKPOINT_SCALE[0],
    720: "720 was the pre-Stage-2b 'below md' ceiling; it is %d, lib.BELOW_MD_MAX" % BELOW_MD_MAX,
    721: "721 was the pre-Stage-2b 'md and up' floor; it is %d, BREAKPOINT_SCALE[2]" % BREAKPOINT_SCALE[2],
    950: "950 was the pre-Stage-2b band ceiling; the band is %d-%d, i.e. (min-width: %dpx) and (max-width: %dpx)"
          % (BREAKPOINT_SCALE[2], BREAKPOINT_SCALE[3] - 1, BREAKPOINT_SCALE[2], BREAKPOINT_SCALE[3] - 1),
}
CSS_MEDIA_WIDTH_FEATURE = re.compile(r"\(\s*(min-width|max-width|width)\s*:\s*([^)]+)\)")
CSS_MEDIA_WIDTH_TOKENS = re.compile(r"(min-width|max-width|width)")
CSS_MEDIA_LENGTH = re.compile(r"^(-?\d*\.?\d+)(px|em|rem|pt|pc|in|cm|mm|q|ex|ch|vw|vh|vmin|vmax|%)?$")
CSS_MEDIA_COVERAGE_LIMIT = 1500


def blank_css_comments(src):
    """Blank out comments without moving a byte or a line, so offsets and line
    numbers stay true to css/style.css while a commented-out @media cannot be
    mistaken for a live one."""
    return re.sub(r"/\*.*?\*/", lambda m: "".join("\n" if c == "\n" else " " for c in m.group(0)),
                  src, flags=re.S)


def at_rule_preludes(src, keyword):
    found = []
    for m in re.finditer(r"@" + keyword + r"\b", src):
        j = src.find("{", m.end())
        if j == -1:
            errors.append(
                f"Media conditions: {keyword} at line "
                f"{src.count(chr(10), 0, m.start()) + 1} has no '{{', so the gate cannot "
                f"tell where its condition ends and this run compared a file it did not read"
            )
            continue
        found.append((src.count(chr(10), 0, m.start()) + 1,
                      " ".join(src[m.start():j].split()), j))
    return found


def media_width_features(prelude):
    features, unreadable = [], []
    for fm in CSS_MEDIA_WIDTH_FEATURE.finditer(prelude):
        kind, raw = fm.group(1), fm.group(2).strip()
        lm = CSS_MEDIA_LENGTH.match(raw)
        if lm is None or lm.group(2) != "px":
            unreadable.append((kind, raw))
            continue
        value = float(lm.group(1))
        if value != int(value):
            unreadable.append((kind, raw))
            continue
        features.append((kind, int(value)))
    return features, unreadable


def check_media_scale():
    undeclared = sorted(set(BREAKPOINT_SCALE) - set(CSS_MEDIA_EDGES))
    if undeclared:
        errors.append(
            f"Media conditions: lib.CSS_MEDIA_EDGES {sorted(CSS_MEDIA_EDGES)} does not admit "
            f"{undeclared}, which lib.BREAKPOINT_SCALE {list(BREAKPOINT_SCALE)} declares. A tier "
            f"on the scale but missing from the gate is a correct rule this gate rejects, and "
            f"the remedy 6f offers for a rejected edge is to edit a constant that exists to be "
            f"derived from the tuple. Derive CSS_MEDIA_EDGES from BREAKPOINT_SCALE instead of "
            f"listing it"
        )
    if BELOW_MD_MAX not in CSS_MEDIA_EDGES:
        errors.append(
            f"Media conditions: lib.BELOW_MD_MAX is {BELOW_MD_MAX}, which lib.CSS_MEDIA_EDGES "
            f"{sorted(CSS_MEDIA_EDGES)} does not admit, so the poster `sizes` breakpoint 6e "
            f"enforces is a media edge this stylesheet is forbidden to use"
        )
    print(
        f"Media scale: BREAKPOINT_SCALE {list(BREAKPOINT_SCALE)} -> CSS_MEDIA_EDGES "
        f"{sorted(CSS_MEDIA_EDGES)} (each boundary, plus each boundary minus one for the "
        f"`max-width` form); superset of the tuple: "
        f"{'yes' if not undeclared else 'NO, missing ' + str(undeclared)}; "
        f"BELOW_MD_MAX {BELOW_MD_MAX} admitted: {BELOW_MD_MAX in CSS_MEDIA_EDGES}"
    )


def check_media_conditions():
    check_media_scale()
    for rel in CSS_MEDIA_FILES:
        path = ROOT / rel
        if not path.exists():
            errors.append(
                f"Media conditions: {rel} is missing, so the edge gate compared no "
                f"stylesheet at all and would pass on an empty file set"
            )
            continue
        src = blank_css_comments(path.read_text(encoding="utf-8"))
        medias = at_rule_preludes(src, "media")
        containers = at_rule_preludes(src, "container")
        if not medias:
            errors.append(
                f"Media conditions: {rel} declares no @media, so the edge gate compared "
                f"nothing and would pass on a stylesheet with no conditions"
            )
        found, intervals, xs_blocks, non_width = {}, [], [], []
        for line, prelude, brace in medias:
            if not CSS_MEDIA_WIDTH_TOKENS.search(prelude):
                non_width.append((line, prelude))
                continue
            features, unreadable = media_width_features(prelude)
            for kind, raw in unreadable:
                errors.append(
                    f"Media conditions: {rel}:{line} declares ({kind}: {raw}), which is "
                    f"not a plain px length. This gate compares width edges by resolved "
                    f"px value, the way 6d compares a literal against a token, so a "
                    f"width it cannot resolve to px is a width nothing else in the "
                    f"project can check either -- use a px edge from lib.CSS_MEDIA_EDGES"
                )
            if not features:
                errors.append(
                    f"Media conditions: {rel}:{line} is width-based ({prelude}) but "
                    f"carries no readable px width, so the edge gate cannot see it"
                )
                continue
            for value in {v for _, v in features}:
                found.setdefault(value, []).append(line)
            lows = [v for kind, v in features if kind == "min-width"]
            highs = [v for kind, v in features if kind == "max-width"]
            intervals.append((min(lows) if lows else 0, max(highs) if highs else None, line, prelude))
            if sorted(v for _, v in features) == [CSS_MEDIA_XS_EDGE]:
                body = src[brace + 1 : _css_brace_end(src, brace)]
                first = next((b.strip() for b in body.splitlines() if b.strip()), "(empty block)")
                xs_blocks.append((line, first, len([b for b in body.splitlines() if b.strip()])))
        if len(xs_blocks) != CSS_MEDIA_XS_BLOCKS:
            where = ", ".join(":%d %s" % (line, first) for line, first, _ in xs_blocks) or "none"
            gaps = [xs_blocks[i + 1][0] - xs_blocks[i][0] for i in range(len(xs_blocks) - 1)]
            errors.append(
                f"Media conditions: {rel} carries the xs edge max-width: {CSS_MEDIA_XS_EDGE}px "
                f"in {len(xs_blocks)} block(s) ({where}), expected {CSS_MEDIA_XS_BLOCKS}. "
                f"They are separate blocks on purpose: 480 and 525 both collapse onto "
                f"{CSS_MEDIA_XS_EDGE}, and media conditions cannot read a custom property, "
                f"so the spec's 'emit each boundary once' is realised as a canonical value "
                f"set plus this gate rather than as one definition. Merging them is not "
                f"tidying -- it moves rules across the source order of a stylesheet whose "
                f"media queries were deliberately left on their original lines in Stage 2a "
                f"so that source order could not shift, and it would promote or demote "
                f"every rule between the blocks"
                + (f"; the surviving block(s) sit at line(s) {[b[0] for b in xs_blocks]} "
                   f"with gaps of {gaps} physical lines and a span of "
                   f"{xs_blocks[-1][0] - xs_blocks[0][0]}"
                   if xs_blocks else "")
            )
        for line, first, lines in xs_blocks:
            if not lines:
                errors.append(
                    f"Media conditions: {rel}:{line} is an empty xs block, so a merged or "
                    f"truncated block would satisfy the count above and this run would "
                    f"certify rules that are not there"
                )
        rejected = sorted(set(found) - set(CSS_MEDIA_EDGES))
        for value in rejected:
            notes = []
            if value in CSS_MEDIA_RETIRED_NOTE:
                notes.append(CSS_MEDIA_RETIRED_NOTE[value])
            if value in found and value in BREAKPOINT_SCALE and value not in CSS_MEDIA_EDGES:
                notes.append(
                    f"{value} is a BREAKPOINT_SCALE member that lib.CSS_MEDIA_EDGES does not "
                    f"admit, which is a gap in lib.py rather than in the stylesheet"
                )
            errors.append(
                f"Media conditions: {rel}:{','.join(str(l) for l in sorted(set(found[value])))} "
                f"uses {value}px, which is not on the canonical scale "
                f"lib.CSS_MEDIA_EDGES {sorted(CSS_MEDIA_EDGES)}"
                + (" -- " + "; ".join(notes) if notes else "")
                + ". The assertion is a SUBSET relation, not equality: 1024 and 1200 are "
                f"permitted and currently unused because Stage 3 adds the lg and xl tiers, "
                f"and a gate that has to be edited before a legitimate tier can be added is a "
                f"gate that gets edited carelessly. If this value is a legitimate boundary, add "
                f"it to lib.BREAKPOINT_SCALE, which is what lib.CSS_MEDIA_EDGES is derived from; "
                f"if it is not, use a value that is. Do not add it to lib.CSS_MEDIA_EDGES and do "
                f"not edit this block"
            )
        prefers = sorted(prelude for _, prelude, _ in medias if "prefers-" in prelude)
        if prefers != sorted(CSS_MEDIA_PREFERS):
            errors.append(
                f"Media conditions: {rel} carries prefers- conditions {prefers}, expected "
                f"exactly {sorted(CSS_MEDIA_PREFERS)}, one each. These are not width edges "
                f"and must survive a re-key untouched: a second prefers-reduced-motion block "
                f"is a duplicated intent, and a renamed or removed one is a lost preference"
            )
        container_preludes = [prelude for _, prelude, _ in containers]
        if container_preludes.count(CSS_MEDIA_CONTAINER) != 1:
            errors.append(
                f"Media conditions: {rel} carries @container preludes {container_preludes}, "
                f"expected exactly one {CSS_MEDIA_CONTAINER!r} with its original condition. "
                f"It is a container query and not a width query, so anything that re-keys "
                f"'all breakpoints' must leave it alone, and this is what proves it did"
            )
        uncovered = [w for w in range(CSS_MEDIA_COVERAGE_LIMIT + 1)
                     if not any(lo <= w and (hi is None or w <= hi) for lo, hi, _, _ in intervals)]
        seams = [(w, w + 1) for w in range(CSS_MEDIA_COVERAGE_LIMIT)
                 if not any(lo <= w + 0.5 and (hi is None or w + 0.5 <= hi)
                            for lo, hi, _, _ in intervals)]
        print(
            f"Media conditions: {rel} -- {len(medias)} @media block(s), "
            f"{len(intervals)} width-based, {len(non_width)} non-width "
            f"({', '.join(prelude for _, prelude in non_width) or 'none'}); "
            f"{len(containers)} @container; edges found "
            f"{ {v: len(found[v]) for v in sorted(found)} }; rejected {rejected or 'none'}"
        )
        for line, prelude, _ in medias:
            if CSS_MEDIA_WIDTH_TOKENS.search(prelude):
                print(f"  media edge :{line} {prelude}")
        for line, first, _ in xs_blocks:
            print(f"  xs block   :{line} max-width: {CSS_MEDIA_XS_EDGE}px -> {first}")
        for value in rejected:
            print(f"  REJECTED   {value}px at {','.join(str(l) for l in sorted(set(found[value])))}")
        print(
            f"Media conditions: integer coverage of 0-{CSS_MEDIA_COVERAGE_LIMIT}: "
            f"{'every integer width is matched by at least one block' if not uncovered else 'UNMATCHED ' + str(uncovered)}"
        )
        print(
            f"Media conditions: seam (information, NOT gated): "
            + (
                "; ".join(f"the open interval ({a}, {b}) matches no width block, {b - a:.2f} CSS px wide"
                          for a, b in seams)
                + " -- a consequence of CSS, not a defect to fix. The conditions tile every "
                f"INTEGER width; the open interval between two integer edges is not a width "
                f"any harness here can ask about, because Playwright refuses a fractional "
                f"emulated viewport outright (Browser.setWindowBounds: Invalid parameters on "
                f"both new_context and set_viewport_size), and the pre-re-key sheet had the "
                f"identical 1px seam at (720, 721). Which way a browser rounds a genuinely "
                f"fractional viewport is NOT established by this project and is not claimed "
                f"here. Do not 'fix' this by asserting perfect tiling: a gate for it would fail "
                f"on a property CSS does not have, and it would fail on a correct stylesheet"
                if seams else
                "none -- every real width in 0-1500 matches at least one block"
            )
        )


# 6h. Token lifecycle and control boundaries. Two contracts from AGENTS.md had
# no gate at all, and both are the kind a stylesheet can violate silently:
#   - "do not add a token you do not use" -- an unreferenced --custom-property is
#     a palette entry that costs a line in every theme block and reads as an
#     intent nobody carried out. The Linear+Runway redesign shipped five.
#   - a control's visual boundary must clear WCAG 2.2 SC 1.4.11's 3:1. 6d caps
#     bare LENGTHS in border-radius and box-spacing; it has nothing to say about
#     which token a border is painted with, so deleting --line-control and
#     routing every control border to a hairline passed green at 1.50:1.
CONTROL_BOUNDARY_SELECTORS = (
    ".reset-filters",
    ".lang,\n.theme-toggle",
    ".search",
    ".genre-filter",
    ".tool-buttons .menu-toggle",
    ".nav-dialog-close",
    ".fav-filter",
    ".lucky",
    ".scroll-top",
    ".mobile-sort",
    ".ratings a",
    ".share-btn",
)
CONTROL_BOUNDARY_TOKEN = "--line-control"

CSS_TOKEN_DECL = re.compile(r"^[ \t]+(--[a-z0-9-]+)\s*:", re.M)
CSS_TOKEN_USE = re.compile(r"var\(\s*(--[a-z0-9-]+)")


def check_token_lifecycle():
    src = blank_css_comments((ROOT / "css/style.css").read_text(encoding="utf-8"))
    declared, seen = [], set()
    for name in CSS_TOKEN_DECL.findall(src):
        if name not in seen:
            seen.add(name)
            declared.append(name)
    used = set(CSS_TOKEN_USE.findall(src))
    orphans = [name for name in declared if name not in used]
    if orphans:
        errors.append(
            f"Token lifecycle: {len(orphans)} of {len(declared)} declared custom properties "
            f"are never referenced: {orphans}. AGENTS.md's CSS contract says do not add a "
            f"token you do not use. Either reference them or delete them; a token kept "
            f"alive by nothing is a palette entry that reads as an intent nobody finished"
        )
    for sel in CONTROL_BOUNDARY_SELECTORS:
        pattern = re.compile(re.escape(sel) + r"\s*\{([^}]*)\}", re.M)
        found = False
        for m in pattern.finditer(src):
            found = True
            for token in re.findall(r"border: 1px solid var\((--[a-z0-9-]+)\);", m.group(1)):
                if token != CONTROL_BOUNDARY_TOKEN:
                    errors.append(
                        f"Control boundary: {sel.splitlines()[0]} paints its border with "
                        f"var({token}), not var({CONTROL_BOUNDARY_TOKEN}). WCAG 2.2 SC 1.4.11 "
                        f"wants 3:1 for a control's visual boundary and --line/--line-strong "
                        f"are hairlines (1.21:1 and 1.50:1 dark). The fix is the token, not "
                        f"the selector"
                    )
        if not found:
            errors.append(
                f"Control boundary: selector {sel.splitlines()[0]!r} is not in "
                f"css/style.css, so this gate checked one fewer control than it claims"
            )
    print(
        f"Token lifecycle: {len(declared)} declared, {len(declared) - len(orphans)} referenced, "
        f"{len(orphans)} orphan(s){': ' + str(orphans) if orphans else ''}"
    )
    print(
        f"Control boundary: {len(CONTROL_BOUNDARY_SELECTORS)} control selectors, every border "
        f"painted with var({CONTROL_BOUNDARY_TOKEN})"
    )


check_token_lifecycle()


check_media_conditions()


# 6i. The sticky header and the section marker are gone (partner ruling,
# 2026-09-30), and this gate is INVERTED with them: it asserts the mechanism
# STAYS gone. It used to assert the opposite -- that something writes
# `--header-offset` and that `scroll-padding-top` exists -- and that inversion is
# the point worth recording. The old gate existed because the header's height is
# content-driven and took six distinct values between 320 and 1280, so no per-tier
# token could replace the measured write. With no sticky header there is nothing
# for an offset to clear, and a surviving one pushes every nav target down the
# viewport for no reason. A check that fails when the old mechanism is missing and
# passes when it is present is a check that has to be deleted in order to make the
# ruling -- the wrong order of events, and the reason this block asserts absence.
#
# Placed after check_media_conditions() rather than where the old check lived,
# because it needs blank_css_comments() (defined above) to tell a live
# declaration from the comment that explains why it is gone. A gate that greps raw
# text trips on its own documentation, which is the surest way to get a
# documentation comment deleted a year later.
def _rule_bodies(src):
    """(selector_part, declarations, at_rule_path) for every style rule.

    Not a general CSS parser: it walks brace depth, which is all this needs. It
    carries two scars, both of which made a gate green for the wrong reason, so
    neither is optional:

    DESCEND into an at-rule body rather than stepping over it. The first version
    stepped over, and because the sheet opens with
    `@layer reset, tokens, base, components, utilities;` followed by five
    `@layer X {` blocks, every real rule in the file lives inside one of them --
    stepping over found 0 rules and 6i.1 proved nothing.

    REPORT the enclosing at-rules, because "found a `.top` rule" and "found the
    `.top` rule" are different claims. The second version returned pairs, and the
    zero-match guard below counted the two `.top` rules that live inside
    `@media` blocks, so DELETING the base `.top` rule outright left the guard
    satisfied and 6i.1 silent. That is not hypothetical: it is what happened while
    a comment was being written with its opening `/*` missing, which turned a
    block of prose into a qualified rule and swallowed `.top`'s declarations. A
    guard that can be satisfied by a conditional copy cannot be trusted to notice
    the unconditional one is gone, so the path is returned and the guard filters
    on it. `@layer` is deliberately NOT treated as conditional: it wraps every
    rule in this sheet, so treating it as one would make the filter reject
    everything."""
    out, i, n = [], 0, len(src)
    stack = []  # (at-rule prelude, index just past its closing brace)
    while i < n:
        brace = src.find("{", i)
        if brace == -1:
            return out
        head = src[i:brace].strip()
        if head.startswith("@"):
            stack.append((head, _css_brace_end(src, brace) + 1))
            i = brace + 1
            continue
        end = _css_brace_end(src, brace)
        path = tuple(p for p, _ in stack)
        for part in head.split(","):
            out.append((part.strip(), src[brace + 1:end], path))
        i = end + 1
        while stack and i >= stack[-1][1]:
            stack.pop()
    return out


# At-rules that make a rule conditional. A `.top` copy inside one of these does
# not stand in for the base rule: it applies at some widths only, and the base
# rule is what governs every other width.
_CONDITIONAL_AT = ("@media", "@container", "@supports")


_6I_SHEET = blank_css_comments((ROOT / "css" / "style.css").read_text(encoding="utf-8"))

# 6i.1 The header must not be sticky. Scoped to the `.top` CLASS, matched as a
# whole selector part so `.scroll-top` (a fixed button, legitimately kept) is not
# caught by a substring. A gate that banned `position: sticky` as a property would
# have to be edited before any legitimate sticky element could exist, and a gate
# that must be edited before a legitimate addition gets edited carelessly.
#
# The zero-match guard below demands an UNCONDITIONAL `.top` rule, which is why
# _rule_bodies returns the at-rule path. Satisfying it with one of the two `.top`
# rules inside `@media` blocks would leave this green after the base rule was
# deleted, and that is not a theoretical failure -- see _rule_bodies' docstring.
_ALL_TOP = [(sel, d) for sel, d, _ in _rule_bodies(_6I_SHEET)
            if re.fullmatch(r"\.top", sel)]
_TOP_RULES = [d for sel, d in _ALL_TOP]
_TOP_BASE = [(sel, d) for sel, d, path in _rule_bodies(_6I_SHEET)
             if re.fullmatch(r"\.top", sel)
             and not any(p.startswith(_CONDITIONAL_AT) for p in path)]
if not _TOP_BASE:
    errors.append(
        "css/style.css: no UNCONDITIONAL `.top` rule was found"
        + (f" ({len(_ALL_TOP)} conditional one(s) matched: "
           f"{[sel for sel, _ in _ALL_TOP]})" if _ALL_TOP else " at all")
        + ", so 6i.1 proved nothing. A `.top` rule inside @media applies at some "
        "widths only and cannot stand in for the base rule, which governs every "
        "other width -- the two in the xs/767 blocks are exactly that. The header "
        "is the subject of the partner's 2026-09-30 removal, and a gate that "
        "matches nothing is green for the wrong reason: find out whether the "
        "selector was renamed, or whether a comment lost its opening /* and "
        "turned its own prose into a qualified rule, rather than concluding the "
        "check is satisfied"
    )
for _body in _TOP_RULES:
    if re.search(r"position\s*:\s*sticky", _body):
        errors.append(
            "css/style.css: .top is sticky again. Partner ruling 2026-09-30: the "
            "header does not stick. Sticky is also the only reason "
            "`scroll-padding-top: var(--header-offset)` existed, so restoring it "
            "means restoring the whole measured-offset mechanism this ruling "
            "removed, and a nav target starts landing under the header again "
            "(measured 58-185px short at 320-768 on the tree that had it)"
        )

# 6i.2 No scroll offset at all: the property, and the writer that fed it.
if re.search(r"scroll-padding-top", _6I_SHEET):
    errors.append(
        "css/style.css: scroll-padding-top is back. It existed only to keep a nav "
        "target from landing under the sticky header; with the header no longer "
        "sticky it offsets every section for nothing. A sticky header again is a "
        "change to make with the partner, and it needs the measured "
        "--header-offset write back with it"
    )
for _js in ("js/app.js", "js/app.min.js"):
    if "header-offset" in (ROOT / _js).read_text(encoding="utf-8"):
        errors.append(
            f"{_js}: still mentions --header-offset. The token was deleted with the "
            f"sticky header and the property it fed is gone, so a surviving write is "
            f"a dead mechanism kept alive by nothing"
        )

# 6i.3 The section marker. Scoped to the MAIN page's nav, and deliberately not a
# repo-wide ban: `js/film.js` binds aria-current on the related-rail pagination
# dots, where it is correct -- it names which page of the rail you are on, a
# position the reader chose by clicking rather than a scroll-derived guess. What
# is gone is the scroll-derived marker on the catalog nav, which took a 20-30%
# band observer, then a click lock, then a third fix for the band latching while
# empty, and still misread after returning to the top. Matched on `aria-current`
# followed by `=` and a quote, the shape both the Vue binding
# (`:aria-current="expr"`) and a hand-written attribute take, so the prose in
# app.js that names the mechanism does not trip this.
for _name in ("index.html", "js/app.js", "js/app.min.js"):
    _m = re.search(
        r"""aria-current\s*=\s*["']""", (ROOT / _name).read_text(encoding="utf-8")
    )
    if _m:
        errors.append(
            f"{_name}: aria-current is set again ({_m.group(0)}). Partner ruling "
            f"2026-09-30: the catalog nav does not mark the current section, so the "
            f"three anchors and every mechanism behind them (a 20-30% band "
            f"observer, a click lock, a latch) are gone. If the marker is wanted "
            f"back that is a new feature, and the band scheme is the wrong shape for "
            f"it: a scroll indicator cannot say 'above all sections', which is "
            f"exactly the state the partner hit"
        )

# 6i.4 The header paints no panel. Same ruling class as 6i.1 and the same
# reason it is worth a gate: `background: var(--surface-1)` on `.top` is what
# made the header read as a raised block, and it was the only paint between
# `body` and the header content.
#
# It protects the INVARIANT rather than the syntax: `background: none` and
# `background-color: transparent` also paint nothing, so they pass. What fails
# is any value that puts ink behind the header. Scoped to the `.top` class and
# to the same zero-match guard as 6i.1 -- a renamed selector must fail loudly
# rather than leave this check vacuously green. Unlike 6i.1 this scans EVERY
# `.top` rule including the conditional copies, because a panel that appears at
# one width is still a panel at that width.
_NO_PAINT = {"none", "transparent", "initial", "unset", "revert", "revert-layer"}
for _sel, _body in _ALL_TOP:
    for _decl in _body.split(";"):
        if ":" not in _decl:
            continue
        _prop, _val = (p.strip() for p in _decl.split(":", 1))
        _prop_l, _val_l = _prop.lower(), _val.lower()
        if _prop_l in ("background", "background-color", "background-image"):
            if _prop_l == "background-image":
                _paints = _val_l != "none"
            else:
                # A shorthand may carry a colour in any position, so check the
                # whole value rather than assuming it leads with the colour.
                _paints = not all(
                    tok.strip() in _NO_PAINT or tok.strip().startswith("url(")
                    for tok in _val_l.replace("/", " / ").split()
                ) and _val_l not in _NO_PAINT
            if _paints:
                errors.append(
                    f"css/style.css: .top paints a background again "
                    f"(`{_prop}: {_val}`). Partner ruling 2026-09-30: the header has "
                    f"no panel. Note this is not a flat-colour swap -- `body` carries "
                    f"a 1px dot grid at 20px and .top was the only paint masking it "
                    f"at the top of the page, so any value here also decides whether "
                    f"the grid shows through the header. Measured cost of removing it: "
                    f"the 8 icons painted on the header go 3.95 -> 4.02 dark and "
                    f"4.70 -> 4.60 light, the tightest header text 5.77 -> 5.33 light "
                    f"-- nothing crosses a floor. `background: none` also passes; what "
                    f"is banned is putting ink behind the header"
                )

# 6g. Related-card markup parity. The .rc card has ONE hand-maintained source,
# gen_pages.RC_CARD, and two renderings of it: the no-JS card that
# gen_pages.render() puts in the <noscript> of all 154 film pages, and the Vue
# template the same function emits into each page as window.FILM_RC_CARD for
# js/film.js to splice into its own. Their element trees must be identical --
# same tags, same classes, same nesting, same document order -- or the JS and
# no-JS renderings differ.
#
# WHY THIS COMPARES TREES, NOT STRINGS. The two renderings cannot be compared as
# strings at all: the clean-tree fragments are 602 and 832 bytes and differ in
# indentation, in text, and in how every value is bound. Normalising that away
# is the whole normalisation problem, and the shape it converges on is a tree.
# So each side is flattened depth-first into an ordered list of
# (tag, classes, parent-index), and the comparison is equality of those lists.
# The parent index is an explicit field, so a re-nesting changes the list while
# the set of nodes does not: same nine tags, same nine class lists, different
# parents. Measured: a set-of-(tag, classes) comparison is EQUAL on that
# mutation, and any document-order-preserving comparison is DIFFERENT, so the
# representation is what makes the verdict legible (node 5, parent 2 vs parent
# 3) rather than what makes it possible. The alternative -- reading the Python
# list the generator interpolated -- is the B1 trap from Stage 0-1: sources
# derived from one list agree by construction and prove nothing. So no text and
# no attribute value participates here. What the two sides have independently
# is the RENDERING, which is what this compares.
#
# BOTH SIDES ARE RENDERED IN MEMORY, from gen_pages.render(), and neither is
# read off disk. That is deliberate and it is the only thing that can see a
# generator-side change: the client card is decoded out of the same render
# output that produced the no-JS card, so deleting an element from RC_CARD, or
# breaking the renderer, or mangling the emitted string all fail here. Had this
# read the committed films/*/index.html instead, a generator-side change would
# leave it green and only the freshness check above would notice.
#
# Classes are compared as a sorted tuple: the order of a class attribute is not
# observable in the rendered page, and a gate that fails on it would be crying
# wolf. Document order IS observable, and it is what the list index carries.
#
# THE PROBE IS A COMPLETE CARD. The no-JS side is one real card, so it is one
# rendering of the conditionals the template expresses with v-if. The probe
# selector below mirrors the generator's own three guards and picks the first
# card with all of them, so both sides show nine nodes. If the card ever grows a
# fourth branch this selector can miss, and it misses LOUDLY: the no-JS card
# would then be short a node the template still carries, and the comparison
# fails. The failure direction of a stale probe is a false alarm, never a
# silent pass.
#
# BLINDNESS, AND IT CHANGED SHAPE WHEN THE SECOND COPY WENT AWAY. While the card
# was hand-maintained twice, this block caught divergence and could not catch a
# change applied to both copies. With one source there is nothing left to
# diverge: a change to RC_CARD moves both sides at once and is invisible here by
# construction, and no gate over a single source can see it -- the source is
# exactly what this block treats as the truth. What it can still catch is the
# thing a single source creates: a renderer that resolves a binding wrongly, an
# emitted template mangled in transit, a v-if dropped on one side only. Read 6g
# as "the two renderings of this source agree", never as "this card is
# correct". The two checks below cover the two ways the single source could be
# undone silently: a second copy reappearing somewhere, and Russian text baked
# into the client card.
RELATED_CARD_ANCHOR = '<a class="rc"'
# The card is 8 nodes after the 2026-09-29 rail change dropped the .rc-head
# wrapper, which existed only to group the title and now has one child. The
# count is a collapse alarm for the extractor, not a style preference: equal
# trees of 8 nodes are the correct shape for the card as authored.
RELATED_CARD_MIN_NODES = 8
RELATED_CARD_OWNER = "tools/gen_pages.py"
RELATED_CARD_GLOBAL = "window.FILM_RC_CARD = "
RELATED_CARD_CYRILLIC = re.compile(r"[\u0400-\u04FF]+")
RELATED_CARD_SOURCE_SCOPE = (
    "js/film.js",
    "js/film.min.js",
    "js/app.js",
    "js/app.min.js",
    "js/about.js",
    "js/common.js",
    "js/i18n.js",
    "js/data.js",
    "index.html",
    "404.html",
    "about.html",
    "privacy.html",
)
RC_TAG = re.compile(r"""<(/?)([a-zA-Z][^\s/>]*)((?:"[^"]*"|'[^']*'|[^>"'])*)(/?)>""")
RC_VOID_TAGS = frozenset((
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
))


def check_related_card_single_source():
    """The card must exist once. RC_CARD is the authoring site, and no other
    hand-maintained file may carry the markup, or the two copies this stage
    deleted come back with nothing watching them."""
    owner = ROOT / RELATED_CARD_OWNER
    copies = []
    if not owner.exists():
        errors.append(
            f"related-card markup: {RELATED_CARD_OWNER} is missing, so the one source "
            f"of the card cannot be read"
        )
    elif owner.read_text(encoding="utf-8").count(RELATED_CARD_ANCHOR) != 1:
        errors.append(
            f"related-card markup: {RELATED_CARD_OWNER} carries "
            f"{owner.read_text(encoding='utf-8').count(RELATED_CARD_ANCHOR)} copies of "
            f"{RELATED_CARD_ANCHOR!r} and the card is meant to have exactly one "
            f"authoring site (gen_pages.RC_CARD)"
        )
    scope = list(RELATED_CARD_SOURCE_SCOPE)
    scope += sorted(
        p.relative_to(ROOT).as_posix() for p in (ROOT / "tools").glob("*.py")
    )
    for rel in scope:
        if rel in (RELATED_CARD_OWNER, "tools/verify.py"):
            continue
        path = ROOT / rel
        if path.exists() and RELATED_CARD_ANCHOR in path.read_text(encoding="utf-8"):
            copies.append(rel)
    if copies:
        errors.append(
            f"related-card markup: {len(copies)} hand-maintained file(s) carry "
            f"{RELATED_CARD_ANCHOR!r} besides {RELATED_CARD_OWNER}: {copies}. The card "
            f"has one source, gen_pages.RC_CARD; a second copy is the divergence this "
            f"stage removed, and it comes back unobserved"
        )


def rc_client_card(page_html, label):
    """The client card exactly as the rendered page carries it: the JSON string
    literal assigned to window.FILM_RC_CARD, decoded the way the browser
    decodes it, so what is compared is what Vue compiles."""
    found = page_html.count(RELATED_CARD_GLOBAL)
    if found != 1:
        errors.append(
            f"related-card markup: {label} appears {found} time(s) in the rendered "
            f"page, expected 1. js/film.js renders the card from exactly one global, "
            f"so a page that carries it twice or not at all is a page whose hydrated "
            f"related section and no-JS card are not the same card"
        )
        return None
    start = page_html.index(RELATED_CARD_GLOBAL) + len(RELATED_CARD_GLOBAL)
    try:
        value, _ = json.JSONDecoder().raw_decode(page_html, start)
    except ValueError as exc:
        errors.append(
            f"related-card markup: {label} is not decodable as a JSON string ({exc}), "
            f"so the client card could not be read out of the page that ships it"
        )
        return None
    if not isinstance(value, str):
        errors.append(
            f"related-card markup: {label} decoded to {type(value).__name__} rather "
            f"than a string, so this run compared something other than a card"
        )
        return None
    return value


def rc_card_fragments(src, label):
    """Every <a class="rc">...</a> in src, cut by tag depth rather than by a
    regex over the body, so nesting cannot end the slice early."""
    found = []
    for m in re.finditer(re.escape(RELATED_CARD_ANCHOR), src):
        depth = 0
        for t in RC_TAG.finditer(src, m.start()):
            closing, name, _, selfclose = t.groups()
            if closing:
                depth -= 1
                if depth == 0:
                    found.append(src[m.start():t.end()])
                    break
            elif not selfclose and name.lower() not in RC_VOID_TAGS:
                depth += 1
        else:
            errors.append(
                f"related-card markup: {label} opens {RELATED_CARD_ANCHOR!r} and never "
                f"closes it, so this run could not cut a card out of the file it was "
                f"supposed to read"
            )
    return found


class RcCardTree(HTMLParser):
    """Depth-first (tag, classes, parent-index) list of one card's elements."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.nodes = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        classes = ()
        for key, value in attrs:
            if key == "class" and value:
                classes = tuple(sorted(value.split()))
        self.nodes.append((tag, classes, self.stack[-1] if self.stack else None))
        if tag not in RC_VOID_TAGS:
            self.stack.append(len(self.nodes) - 1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in RC_VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()


def rc_card_nodes(fragment, label):
    tree = RcCardTree()
    tree.feed(fragment)
    tree.close()
    nodes = tree.nodes
    if not nodes or nodes[0] != ("a", ("rc",), None):
        errors.append(
            f"related-card markup: {label} extracted {len(nodes)} node(s) from the "
            f"{RELATED_CARD_ANCHOR!r} fragment and its first node is "
            f"{nodes[0] if nodes else None} rather than the card root ('a', ('rc',), "
            f"None). An extraction that is empty, or that does not begin at the card "
            f"root, is an extractor failure and is reported as one: two sides that both "
            f"fail to extract are two failures and never a match"
        )
    return nodes


def rc_first_divergence(left, right):
    for i in range(max(len(left), len(right))):
        a = left[i] if i < len(left) else None
        b = right[i] if i < len(right) else None
        if a != b:
            return i, a, b
    return None


def check_related_card_classes(nodes):
    """Every class the card puts on an element, checked against the stylesheet.

    This is the witness that replaced the second copy. While the card was
    hand-maintained twice, a class renamed in one copy was caught by the
    comparison; renamed in the source it now moves both renderings at once and
    that comparison is blind to it by construction. css/style.css is the one
    file in the project that did not come out of RC_CARD, so it can still say
    whether the card and its styling still meet."""
    stylesheet = ROOT / "css" / "style.css"
    if not stylesheet.exists():
        errors.append("related-card markup: css/style.css is missing, so the card's classes cannot be checked")
        return []
    css = stylesheet.read_text(encoding="utf-8")
    used = set()
    for _tag, classes, _parent in nodes:
        used.update(classes)
    return sorted(name for name in used if ("." + name) not in css)


def check_related_card_markup():
    probe = None
    for item in catalog:
        rel = gen_pages.related_to(item, catalog)
        if not rel:
            continue
        r = rel[0]
        if (
            (r.get("poster") or "").lstrip("/")
            and has_rating(r.get("kpRating"))
            and r.get("imdbId")
            and has_rating(r.get("imdbRating"))
        ):
            probe = (item, rel)
            break
    if probe is None:
        errors.append(
            "related-card markup: no catalog record renders a card carrying every "
            "branch (poster + kpRating + imdbId + imdbRating), so there is no "
            "complete card to compare the authored one against. Either the catalog "
            "no longer fills all the branches, or the emitted card grew a branch "
            "this probe selector does not know about"
        )
        return
    item, rel = probe
    page_slug = item_slug(item)

    emitted_label = f"gen_pages.render() no-JS card in /films/{page_slug}/"
    client_label = f"client card {RELATED_CARD_GLOBAL.strip()} in /films/{page_slug}/"
    rendered = gen_pages.render(item, rel)
    emitted_frags = rc_card_fragments(rendered, emitted_label)
    client_card = rc_client_card(rendered, client_label)
    client_frags = rc_card_fragments(client_card or "", client_label)
    if client_card is not None:
        cyrillic = sorted(set(RELATED_CARD_CYRILLIC.findall(client_card)))
        if cyrillic:
            errors.append(
                f"related-card markup: the client card carries Cyrillic text "
                f"{cyrillic} with no binding around it. The client renders in two "
                f"languages, so any value it displays has to come from a binding; "
                f"text baked into the template is Russian whatever lang says, and only "
                f"the language switch on a film page would show it"
            )

    trees = {}
    for label, frags, want in ((emitted_label, emitted_frags, len(rel)),
                               (client_label, client_frags, 1)):
        if len(frags) != want:
            errors.append(
                f"related-card markup: {label} extracted {len(frags)} card(s) from "
                f"{RELATED_CARD_ANCHOR!r}, expected {want}. The card is the unit of "
                f"comparison, so 0 of them means the extractor did not recognise the "
                f"markup and the wrong number means the loop that produces them "
                f"changed. An extraction of nothing is an extractor failure and is "
                f"reported as one: two sides that both extracted nothing are two "
                f"failures, never a match"
            )
            continue
        nodes = rc_card_nodes(frags[0], label)
        trees[label] = nodes

    if len(trees) != 2:
        return

    emitted = trees[emitted_label]
    client = trees[client_label]
    counts = f"{len(emitted)} no-JS node(s) vs {len(client)} client node(s)"
    diff = rc_first_divergence(emitted, client)
    if diff:
        i, a, b = diff
        errors.append(
            f"related-card markup: the two renderings of the one source diverge at "
            f"node {i} of the depth-first tree, {counts}. {emitted_label}[{i}] = {a}; "
            f"{client_label}[{i}] = {b}. (tag, classes, parent-index) -- the parent "
            f"index is what makes a re-nesting visible: identical nodes with a "
            f"different parent are a different tree. Both sides come from "
            f"gen_pages.RC_CARD, so the fix is in the source or in the renderer that "
            f"resolves it, not in this block"
        )
        return
    if min(len(emitted), len(client)) < RELATED_CARD_MIN_NODES:
        errors.append(
            f"related-card markup: both sides extracted {len(emitted)} node(s) and the "
            f"trees are equal, but a complete card is {RELATED_CARD_MIN_NODES} nodes. "
            f"Equal-and-tiny is the silent collapse this guard exists for: a broken "
            f"extractor agrees with itself. If the card legitimately lost nodes, change "
            f"it in RC_CARD on purpose and raise RELATED_CARD_MIN_NODES with it"
        )
        return
    unstyled = check_related_card_classes(client)
    if unstyled:
        print(
            f"Related-card markup parity: WARN -- {counts}, the trees agree, but "
            f"{len(unstyled)} class(es) the card uses have no rule in css/style.css: "
            f"{unstyled}"
        )
        errors.append(
            f"related-card markup: the card uses {unstyled}, which css/style.css never "
            f"mentions. One source means a class renamed in RC_CARD moves both "
            f"renderings at once and is invisible to the comparison above, so the "
            f"stylesheet is the only independent witness left that the card and its "
            f"styling still meet. A class that is meant to be unstyled does not belong "
            f"on this card"
        )
        return
    print(
        f"Related-card markup parity: OK -- {counts}, identical tags, identical class "
        f"sets and identical parent indices. Probe /films/{page_slug}/, related "
        f"{item_slug(rel[0])}, every branch present"
    )
    print(f"  no-JS   {emitted}")
    print(f"  client  {client}")
    print(
        "  one source (gen_pages.RC_CARD), two renderings compared in memory: a change "
        "to the source itself is invisible here by construction"
    )


check_related_card_single_source()
check_related_card_markup()


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
#
# A coarse check, and it has to know three things a naive brace counter does
# not, or it reports a file `node --check` accepts:
#   * strings and template literals, which is what it already handled;
#   * comments, because a backticked identifier in a `//` line is an ordinary
#     way to write one and otherwise opens a string that runs to the next
#     backtick and swallows real code;
#   * regex literals, because `/^\//` ends in an escaped slash immediately
#     followed by its own closer, so a `//` test alone reads `^\//` as a
#     comment and drops the rest of the line, and because a `/` inside a
#     character class does not close the literal, so `/[a-z/]+/g` closes early.
#     Telling a regex from a division is the usual heuristic: a `/` opens a
#     regex where a value cannot already have ended.
def balance(src):
    stack = []
    i = 0
    prev = ""  # last significant char, outside comments and strings
    word = ""  # last significant identifier
    pairs = {")": "(", "]": "[", "}": "{"}
    value_end = set(")]}")  # chars after which a `/` is division, not a regex
    regex_after = set("(,=:[!&|?{};+-*%~^<>")
    regex_words = {
        "return", "typeof", "case", "in", "of", "new", "delete", "void",
        "instanceof", "do", "else", "yield", "await", "throw",
    }
    while i < len(src):
        c = src[i]
        if c.isspace():
            i += 1
            continue
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            i = len(src) if j == -1 else j + 1
            continue
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = len(src) if j == -1 else j + 2
            continue
        if c == "/" and prev not in value_end and (
            prev == "" or prev in regex_after or word in regex_words
        ):
            j = i + 1
            in_class = False
            while j < len(src):
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if in_class:
                    # A `]` straight after `[` is a literal, not the close.
                    if ch == "]" and src[j - 1] != "[":
                        in_class = False
                    j += 1
                    continue
                if ch == "[":
                    in_class = True
                    j += 1
                    continue
                if ch == "/":
                    break
                j += 1
            i = j + 1
            prev = "/"  # a regex is a value, so the next `/` is division
            word = ""
            continue
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
            prev = "x"  # a string is a value
            word = ""
        elif c.isalnum() or c in "_$":
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            word = src[i:j]
            prev = src[j - 1]
            i = j
            continue
        elif c in "([{":
            stack.append(c)
        elif c in ")]}":
            if not stack or stack[-1] != pairs[c]:
                return f"Unbalanced near position {i}: {c!r}"
            stack.pop()
        if not (c.isalnum() or c in "_$"):
            word = ""
        prev = c
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

# 9b. Related selection rules + three-way source parity + client fidelity (Python only, node-independent)
RELATED_ITEMLIST_NAME = "Похожее в каталоге IT Movies"
CLIENT_RELATED_BANNED = ("relatedPool", "Math.random")


def check_related():
    problems = []
    parity = []
    picks = set()
    overlaps = []
    pages_checked = 0
    for item in catalog:
        slug = item_slug(item)
        pool = gen_pages.related_pool(item, catalog)
        if len(pool) < 6:
            problems.append(f"{slug}: related pool too small ({len(pool)})")
            continue
        rel = gen_pages.related_to(item, catalog)
        if len(rel) != min(RELATED_COUNT, len(pool)):
            problems.append(
                f"{slug}: related_to returned {len(rel)}, expected {RELATED_COUNT}"
            )
        if {item_slug(r) for r in rel} - {item_slug(r) for r in pool}:
            problems.append(f"{slug}: related_to escaped the pool")
        if item["type"] != "documentary" and any(r["type"] == "documentary" for r in rel):
            problems.append(f"{slug}: documentary leaked into related")
        if gen_pages.related_to(item, catalog) != rel:
            problems.append(f"{slug}: related_to is not deterministic")
        picks.add(tuple(item_slug(r) for r in rel))
        genres = set(item["genres"])
        overlaps.extend(len(genres & set(r["genres"])) for r in rel)

        page = gen_pages.OUT / slug / "index.html"
        if not page.exists():
            parity.append(
                f"{slug}: film page missing — JSON-LD, noscript and FILM_PAGE "
                f"cannot be compared (run gen_pages.py)"
            )
            continue
        pages_checked += 1
        text = page.read_text(encoding="utf-8")
        expected = [r["titleRu"] for r in rel]
        expected_ld = [
            {
                "position": i + 1,
                "name": r["titleRu"],
                "url": f"{SITE_BASE}/films/{item_slug(r)}/",
            }
            for i, r in enumerate(rel)
        ]

        ld = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', text, re.S
        )
        if not ld:
            parity.append(f"{slug}: no JSON-LD block")
        else:
            try:
                graph = json.loads(ld.group(1)).get("@graph", [])
            except json.JSONDecodeError:
                graph = []
                parity.append(f"{slug}: JSON-LD is not valid JSON")
            lists = [
                n
                for n in graph
                if n.get("@type") == "ItemList"
                and n.get("name") == RELATED_ITEMLIST_NAME
                and n.get("numberOfItems") == len(expected)
            ]
            if not lists:
                parity.append(
                    f"{slug}: no related ItemList ({RELATED_ITEMLIST_NAME!r}, "
                    f"numberOfItems {len(expected)}) in JSON-LD"
                )
            else:
                got_items = [
                    {
                        "position": e.get("position"),
                        "name": e.get("name"),
                        "url": e.get("url"),
                    }
                    for e in lists[0].get("itemListElement", [])
                ]
                if got_items != expected_ld:
                    names = [e["name"] for e in got_items]
                    if names != expected:
                        parity.append(
                            f"{slug}: JSON-LD {names} != generated {expected}"
                        )
                    else:
                        parity.append(
                            f"{slug}: JSON-LD itemListElement {got_items} != "
                            f"generated {expected_ld}"
                        )

        payload = re.search(
            r"window\.FILM_PAGE = (.*?);\s*</script>", text, re.S
        )
        if not payload:
            parity.append(f"{slug}: no FILM_PAGE payload")
        else:
            try:
                page_data = json.loads(payload.group(1))
            except json.JSONDecodeError:
                page_data = {}
                parity.append(f"{slug}: FILM_PAGE is not valid JSON")
            if "relatedPool" in page_data:
                parity.append(
                    f"{slug}: FILM_PAGE carries a relatedPool key "
                    f"({len(page_data.get('relatedPool') or [])} items) — the "
                    f"client must render pageData.related, a pool only "
                    f"reopens the shuffled-4-of-16 defect"
                )
            got = [r.get("titleRu") for r in page_data.get("related", [])]
            if got != expected:
                parity.append(
                    f"{slug}: FILM_PAGE.related {got} != generated {expected}"
                )

        noscript = re.findall(r'<span class="rc-title">(.*?)</span>', text, re.S)
        if noscript != expected:
            parity.append(
                f"{slug}: noscript cards {noscript} != generated {expected}"
            )
        for r in rel:
            if f'href="../{item_slug(r)}/"' not in text:
                parity.append(
                    f"{slug}: noscript is missing a link to {item_slug(r)}"
                )
                break

    if pages_checked != len(catalog):
        parity.append(
            f"three-way source parity compared {pages_checked} of "
            f"{len(catalog)} pages"
        )

    client_checked = []
    for path in (ROOT / "js" / "film.js", ROOT / "js" / "film.min.js"):
        if not path.exists():
            parity.append(f"js/{path.name}: missing — cannot check the client")
            continue
        src = path.read_text(encoding="utf-8")
        hits = sorted({b for b in CLIENT_RELATED_BANNED if b in src})
        if hits:
            parity.append(
                f"js/{path.name} still references {', '.join(hits)} — the film-page "
                f"client must render FILM_PAGE.related verbatim, never a random "
                f"subset of a larger pool"
            )
        elif not re.search(r"pageData\s*\.\s*related", src):
            parity.append(
                f"js/{path.name} does not read pageData.related — it must render "
                f"the generator's list, not a list of its own"
            )
        else:
            client_checked.append(path.name)

    floor = max(3, len(catalog) * 3 // 5)
    if len(picks) < floor:
        problems.append(
            f"{len(picks)} distinct {RELATED_COUNT}-sets across {len(catalog)} items, "
            f"floor {floor} — collapsed toward the 83 distinct sets of the "
            f"pre-Task-5 deterministic selection"
        )
    relevance = RELATED_MEAN_OVERLAP
    if overlaps and relevance - sum(overlaps) / len(overlaps) > RELATED_MEAN_TOLERANCE:
        problems.append(
            f"mean genre overlap {sum(overlaps) / len(overlaps):.3f} per pick over "
            f"{len(overlaps)} picks, floor {relevance - RELATED_MEAN_TOLERANCE:.3f} "
            f"(expected {relevance:.3f}) — relevance regressed toward 1.265, the "
            f"whole-pool shuffle that discarded the score ranking"
        )
    for p in problems[:5]:
        errors.append(f"related selection: {p}")
    if len(problems) > 5:
        errors.append(f"related selection: {len(problems) - 5} more problems")
    if not problems:
        print(
            f"Related selection rules: OK ({len(catalog)} items, "
            f"{len(picks)} distinct {RELATED_COUNT}-sets floor {floor}, "
            f"mean overlap {sum(overlaps) / len(overlaps):.3f} "
            f"floor {relevance - RELATED_MEAN_TOLERANCE:.3f})"
        )
    for p in parity[:5]:
        errors.append(f"related parity: {p}")
    if len(parity) > 5:
        errors.append(f"related parity: {len(parity) - 5} more problems")
    if not parity:
        print(
            f"Related three-way source parity JSON-LD<->noscript<->FILM_PAGE: OK "
            f"({pages_checked}/{len(catalog)} pages, no FILM_PAGE.relatedPool)"
        )
        print(
            f"Client renders FILM_PAGE.related verbatim: OK "
            f"({', '.join(client_checked)}: no relatedPool, no Math.random, "
            f"reads pageData.related)"
        )


check_related()


# 9b1. Node smoke harnesses: app.js / slug / film.js (tools/smoke.js)
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

    # 9b2. Repeat the smokes on the minified JS actually shipped (*.min.js),
    # so a semantics-changing bug in gen_pages.minify_js is caught by the tests
    for name in ("app", "slug", "film"):
        if name == "slug":
            check_slugs("--min")
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