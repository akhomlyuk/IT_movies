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
from lib import ROOT, SITE_BASE, item_slug, load_catalog, known_genres, parse_i18n, i18n_key_paths, has_rating, webp_size

sys.stdout.reconfigure(encoding="utf-8")
errors = []
NO_WRITE = "--no-write" in sys.argv
STRICT = "--strict" in sys.argv
POSTER_VARIANT_WIDTH = 400
RELATED_MEAN_OVERLAP = 1.513
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
variant_paths = {
    p: ROOT / (p[: -len(".webp")] + "_400.webp") for p in catalog_posters
}
missing_variants = [p for p, path in variant_paths.items() if not path.exists()]
if missing_variants:
    errors.append(
        f"poster _400 variants missing: {len(missing_variants)} — run tools/gen_posters.py"
    )
else:
    print(
        f"Poster variants: _400 present for {len(catalog_posters)} posters (gen_posters.py)"
    )
    wrong_width = []
    for p, path in variant_paths.items():
        dims = webp_size(path)
        if not dims or dims[0] != POSTER_VARIANT_WIDTH:
            wrong_width.append((p, dims[0] if dims else "unreadable"))
    if wrong_width:
        errors.append(
            f"poster _400 variants not exactly {POSTER_VARIANT_WIDTH}px wide: "
            f"{len(wrong_width)} of {len(catalog_posters)} — "
            + ", ".join("%s (%s)" % (p, w) for p, w in wrong_width[:5])
        )
    else:
        print(
            f"Poster variants: all {len(catalog_posters)} _400 files exactly "
            f"{POSTER_VARIANT_WIDTH}px wide"
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
        rel = gen_pages.related_to(item, catalog, 4)
        if len(rel) != min(4, len(pool)):
            problems.append(f"{slug}: related_to returned {len(rel)}, expected 4")
        if {item_slug(r) for r in rel} - {item_slug(r) for r in pool}:
            problems.append(f"{slug}: related_to escaped the pool")
        if item["type"] != "documentary" and any(r["type"] == "documentary" for r in rel):
            problems.append(f"{slug}: documentary leaked into related")
        if gen_pages.related_to(item, catalog, 4) != rel:
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
            f"{len(picks)} distinct 4-sets across {len(catalog)} items, "
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
            f"{len(picks)} distinct 4-sets floor {floor}, "
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