"""Search Kinopoisk via Playwright and extract kpId + rating from JSON-LD.

Usage:
    python tools/pw_kp.py "Терминатор"
    python tools/pw_kp.py "Я, робот" "Экзистенция"

For each query prints the first matching kpId, title and kpRating.
ratingCount (kpVotes) is extracted alongside the rating value.
"""

import json
import re
import sys
from urllib.parse import quote

from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

IMDB_SUB = """() => {
  const el = document.querySelector('.film-sub-rating');
  if (!el) return null;
  return Array.from(el.querySelectorAll('span')).map(s => s.innerText).filter(t => t.trim());
}"""


def search_kp(query, page):
    page.goto(
        "https://www.kinopoisk.ru/new-search/?text=" + quote(query),
        wait_until="domcontentloaded",
        timeout=45000,
    )
    page.wait_for_timeout(7000)
    links, seen = [], set()
    for a in page.locator("a").all():
        href = a.get_attribute("href") or ""
        if "/film/" in href and ".html" not in href and "hd.kinopoisk" not in href:
            key = href.split("?")[0]
            if key not in seen:
                seen.add(key)
                links.append(key)
    return links[:6]


def fetch_film_ld(fid, page):
    page.goto(
        f"https://www.kinopoisk.ru/film/{fid}/",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    page.wait_for_timeout(6000)
    ld = page.evaluate(
        """() => Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
                     .map(s => s.textContent)"""
    )
    imdb = page.evaluate(IMDB_SUB)
    info = {
        "kpId": fid,
        "titleRu": "",
        "titleEn": "",
        "kpRating": None,
        "kpVotes": None,
        "imdbRating": None,
        "imdbVotes": None,
        "year": "",
    }
    if imdb:
        for part in imdb:
            m = re.fullmatch(r"IMDb\s*:\s*([0-9.,]+)", part)
            if m:
                info["imdbRating"] = float(m.group(1).replace(",", "."))
                continue
            m = re.fullmatch(r"([\d ][\d ]*)\s*оцен\w*", part)
            if m:
                info["imdbVotes"] = int(m.group(1).replace(" ", ""))
    for blob in ld:
        try:
            data = json.loads(blob)
            if data.get("@type") in ("Movie", "TVSeries", "Series"):
                info["titleRu"] = info["titleRu"] or data.get("name", "")
                info["titleEn"] = info["titleEn"] or (data.get("alternativeHeadline") or data.get("alternateName", ""))
                info["year"] = info["year"] or data.get("datePublished", "")
                if "aggregateRating" in data:
                    ag = data["aggregateRating"]
                    info["kpRating"] = ag["ratingValue"]
                    info["kpVotes"] = ag.get("ratingCount")
        except Exception:
            continue
    return info


def main():
    queries = sys.argv[1:] if len(sys.argv) > 1 else ["Терминатор"]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="ru-RU", user_agent=UA)
        page = ctx.new_page()

        for query in queries:
            print(f"\n--- {query} ---")
            try:
                links = search_kp(query, page)
                if not links:
                    print("  no results")
                    continue
                print(f"  search results: {links[:4]}")
                fid = links[0].split("/film/")[1].strip("/").split("/")[0]
                info = fetch_film_ld(fid, page)
                if info:
                    print(f"  kpId:      {info['kpId']}")
                    print(f"  titleRu:   {info['titleRu']}")
                    print(f"  titleEn:   {info['titleEn']}")
                    print(f"  kpRating:  {info['kpRating']}")
                    print(f"  kpVotes:   {info['kpVotes']}")
                    print(f"  imdbRating:{info['imdbRating']}")
                    print(f"  imdbVotes: {info['imdbVotes']}")
                    print(f"  year:      {info['year']}")
                else:
                    print(f"  film page {fid} — no ld+json rating found")
            except Exception as e:
                print(f"  ERROR: {e}")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()