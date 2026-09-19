#!/usr/bin/env python3
"""Shared helpers for the IT Movies Python scripts (gen_pages.py, verify.py)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_BASE = "https://akhomlyuk.github.io/IT_movies"


def load_catalog(root=ROOT):
    raw = (root / "js" / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[raw.index("[") : raw.rindex("]") + 1])


def make_slug(text):
    s = re.sub(r"\s+", "-", text.lower())
    s = re.sub(r"[^a-z0-9-]+", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def item_slug(item):
    base = item.get("imdbId") or "kp-" + str(item.get("kpId"))
    return f"{base}-{make_slug(item['titleEn'])}"


def ru_genres(root=ROOT):
    i18n_raw = (root / "js" / "i18n.js").read_text(encoding="utf-8")
    m = re.search(r"ru:\s*\{.*?genres:\s*\{(.*?)\n\s*\},", i18n_raw, re.S)
    return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", m.group(1)))


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