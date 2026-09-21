#!/usr/bin/env python3
"""Collect Kinopoisk ratingCount (kpVotes) for catalog records via Playwright.

Visits each /film/<kpId>/ page directly (ids already present in js/data.js),
reads kpRating + ratingCount from the page JSON-LD and saves the result map.
Output file doubles as resume state: ids already saved are skipped.

Usage:
    python tools/kp_votes.py                 # all records
    python tools/kp_votes.py --limit 5       # only first 5 (smoke test)
    python tools/kp_votes.py --out _tmp/kp_votes.json

Result JSON: {"<kpId>": {"ok": <bool>, "kpVotes": ..., ...}}. "ok": true means
the film page loaded real content (a rating may still be absent); "ok": false
means the page was not verified (blocked/error) and will be retried on re-run.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import ROOT, load_catalog  # noqa: E402
from pw_kp import fetch_film_ld, polite_sleep  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="process only first N records")
    ap.add_argument("--out", default=str(ROOT / "_tmp" / "kp_votes.json"))
    ap.add_argument("--reset-null", action="store_true", help="retry ids previously marked without rating")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    saved = {}
    if out.exists():
        saved = json.loads(out.read_text(encoding="utf-8"))
        if args.reset_null:
            for key in [k for k, v in saved.items() if v.get("kpVotes") is None]:
                del saved[key]
            print(f"reset {len(saved)} remaining ids that were saved")
        print(f"resume: {len(saved)} ids already saved")

    catalog = load_catalog()
    targets = []
    for item in catalog:
        kpid = item.get("kpId")
        if not kpid:
            continue
        entry = saved.get(str(kpid))
        if entry is not None and (entry.get("ok") is True or entry.get("kpVotes") is not None):
            continue
        if args.limit > 0 and len(targets) >= args.limit:
            break
        targets.append((str(kpid), item["titleRu"]))

    if not targets:
        print("nothing to fetch")
        return

    print(f"targets: {len(targets)}")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="ru-RU")
        page = ctx.new_page()
        try:
            for i, (kpid, title) in enumerate(targets, 1):
                if i > 1:
                    polite_sleep()
                info = None
                error = None
                for attempt in range(3):
                    try:
                        info = fetch_film_ld(kpid, page)
                        if not info.get("titleRu"):
                            raise RuntimeError("no ld+json content on the page")
                        error = None
                        break
                    except Exception as e:
                        error = e
                        if attempt < 2:
                            time.sleep(2 ** attempt * 2)
                if error is not None:
                    saved[kpid] = {
                        "ok": False,
                        "kpVotes": None,
                        "titleRu": title,
                        "error": repr(error),
                    }
                    print(f"[{i}/{len(targets)}] {kpid}  {title}: UNVERIFIED {error!r}", flush=True)
                elif info["kpVotes"]:
                    saved[kpid] = {
                        "ok": True,
                        "kpRating": info["kpRating"],
                        "kpVotes": info["kpVotes"],
                        "imdbRating": info.get("imdbRating"),
                        "imdbVotes": info.get("imdbVotes"),
                        "titleRu": info["titleRu"],
                    }
                    imdb = f", imdb {info.get('imdbRating')} ({info.get('imdbVotes')})" if info.get("imdbVotes") else ""
                    print(f"[{i}/{len(targets)}] {kpid}  {info['titleRu']}  "
                          f"{info['kpRating']}  ({info['kpVotes']} votes){imdb}", flush=True)
                else:
                    saved[kpid] = {
                        "ok": True,
                        "kpRating": None,
                        "kpVotes": None,
                        "imdbRating": info.get("imdbRating"),
                        "imdbVotes": info.get("imdbVotes"),
                        "titleRu": info["titleRu"],
                    }
                    imdb = f", imdb {saved[kpid]['imdbRating']} ({saved[kpid]['imdbVotes']})" if saved[kpid].get("imdbVotes") else ""
                    print(f"[{i}/{len(targets)}] {kpid}  {title}: no kp rating{imdb}", flush=True)
                out.write_text(json.dumps(saved, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        finally:
            ctx.close()
            browser.close()
    print(f"saved: {len(saved)}")


if __name__ == "__main__":
    main()