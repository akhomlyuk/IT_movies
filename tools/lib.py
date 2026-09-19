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