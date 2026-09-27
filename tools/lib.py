#!/usr/bin/env python3
"""Shared helpers for the IT Movies Python scripts (gen_pages.py, verify.py)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_BASE = "https://akhomlyuk.github.io/IT_movies"


def load_catalog(root=ROOT):
    raw = (root / "js" / "data.js").read_text(encoding="utf-8")
    return parse_catalog(raw)


def parse_catalog(raw):
    marker = "window.CATALOG"
    pos = raw.find(marker)
    if pos == -1:
        raise ValueError("js/data.js: expected 'window.CATALOG' assignment")
    pos = raw.find("[", pos)
    if pos == -1:
        raise ValueError("js/data.js: catalog array '[' not found")
    value, _ = json.JSONDecoder().raw_decode(raw, pos)
    return value


def make_slug(text):
    s = re.sub(r"\s+", "-", text.lower())
    s = re.sub(r"[^a-z0-9-]+", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def item_slug(item):
    base = item.get("imdbId") or "kp-" + str(item.get("kpId"))
    return f"{base}-{make_slug(item['titleEn'])}"


def parse_i18n(root=ROOT):
    src = (root / "js" / "i18n.js").read_text(encoding="utf-8")
    pos = src.find("const I18N")
    if pos == -1:
        raise ValueError("js/i18n.js: 'const I18N' not found")
    pos = src.find("{", pos)
    if pos == -1:
        raise ValueError("js/i18n.js: I18N object literal not found")
    obj, _ = _js_object(src, pos)
    return obj


def _js_skip(src, i):
    while i < len(src) and src[i] in " \t\r\n":
        i += 1
    return i


def _js_scalar(src, i):
    q = src[i]
    j = i + 1
    buf = []
    while j < len(src):
        if src[j] == "\\" and j + 1 < len(src):
            buf.append(src[j : j + 2])
            j += 2
            continue
        if src[j] == q:
            return "".join(buf), j + 1
        buf.append(src[j])
        j += 1
    raise ValueError("js/i18n.js: unterminated string/template literal")


def _js_value(src, i):
    i = _js_skip(src, i)
    c = src[i]
    if c == "{":
        return _js_object(src, i)
    if c == "[":
        arr = []
        i = _js_skip(src, i + 1)
        while src[i] != "]":
            val, i = _js_value(src, i)
            arr.append(val)
            i = _js_skip(src, i)
            if src[i] == ",":
                i += 1
        return arr, i + 1
    if c in "\"'`":
        return _js_scalar(src, i)
    j = i
    while j < len(src) and src[j] not in " \t\r\n,:;}{][":
        j += 1
    return src[i:j], j


def _js_object(src, i):
    obj = {}
    i = _js_skip(src, i + 1)
    while src[i] != "}":
        i = _js_skip(src, i)
        if src[i] in "\"'`":
            key, i = _js_scalar(src, i)
        else:
            j = i
            while j < len(src) and src[j] not in " \t\r\n:{}":
                j += 1
            key = src[i:j]
            i = j
        i = _js_skip(src, i)
        if src[i] == ":":
            i += 1
        val, i = _js_value(src, i)
        obj[key] = val
        i = _js_skip(src, i)
        if src[i] == ",":
            i = _js_skip(src, i + 1)
            if src[i] == "}":
                break
    return obj, i + 1


def i18n_key_paths(tree, prefix=()):
    paths = set()
    for key, value in tree.items():
        path = prefix + (key,)
        if isinstance(value, dict):
            paths |= i18n_key_paths(value, path)
        else:
            paths.add(path)
    return paths


def ru_genres(root=ROOT):
    return dict(parse_i18n(root)["ru"]["genres"])


def known_genres(root=ROOT):
    return set(ru_genres(root))


def has_rating(v):
    return v is not None and v != ""


def fmt_rating(v):
    return "—" if not has_rating(v) else f"{float(v):.1f}"


def webp_size(path):
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        return (
            int.from_bytes(data[24:27], "little") + 1,
            int.from_bytes(data[27:30], "little") + 1,
        )
    if chunk == b"VP8 ":
        return (
            int.from_bytes(data[26:28], "little") & 0x3FFF,
            int.from_bytes(data[28:30], "little") & 0x3FFF,
        )
    if chunk == b"VP8L":
        if len(data) < 26 or data[20] != 0x2F:
            return None
        b0, b1, b2, b3 = data[21:25]
        w = 1 + (((b1 & 0x3F) << 8) | b0)
        h = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return w, h
    return None


BREAKPOINT_SCALE = (575, 576, 768, 1024, 1200)

# Every tier boundary in both spellings a media condition can use: the `min-width`
# form (the boundary itself) and the `max-width` form ("below the next tier", the
# boundary minus one). Derived, never listed -- a listed copy omitted 576 once.
CSS_MEDIA_EDGES = frozenset(
    set(BREAKPOINT_SCALE) | {boundary - 1 for boundary in BREAKPOINT_SCALE}
)

BELOW_MD_MAX = BREAKPOINT_SCALE[2] - 1


def poster_sizes():
    return "(max-width: %dpx) 92vw, 300px" % BELOW_MD_MAX


# The poster variant ladder, in one place. Widths are the source of truth and a
# file's suffix is derived from its width, so a width cannot be added without its
# naming. gen_posters.py writes the ladder, gen_pages.py emits it as srcset
# candidates, verify.py gates on it and re-checks the copy js/film.js carries.
# 96 and 192 are the related card's 96px box at 1x and 2x; 400 is the width the
# lightbox and the catalog table already select.
POSTER_VARIANT_WIDTHS = (96, 192, 400)


def variant_suffix(width):
    return "_%d" % width


def variant_name(poster, width):
    return poster[: -len(".webp")] + variant_suffix(width) + ".webp"


def variant_path(poster, width, root=ROOT):
    return root / variant_name(poster, width)