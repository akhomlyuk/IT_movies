"""Search Kinopoisk via Playwright and extract kpId + rating from JSON-LD.

Usage:
    python scripts/pw_kp.py "Терминатор"
    python scripts/pw_kp.py "Я, робот" "Экзистенция"

For each query prints the first matching kpId, title and kpRating.
"""

import json
import sys
from urllib.parse import quote

from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


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
    for blob in ld:
        try:
            data = json.loads(blob)
            if data.get("@type") == "Movie" and "aggregateRating" in data:
                return {
                    "kpId": fid,
                    "titleRu": data.get("name", ""),
                    "titleEn": data.get("alternativeHeadline") or data.get("alternateName", ""),
                    "kpRating": data["aggregateRating"]["ratingValue"],
                    "year": data.get("datePublished", ""),
                }
        except Exception:
            continue
    return None


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
                    print(f"  year:      {info['year']}")
                else:
                    print(f"  film page {fid} — no ld+json rating found")
            except Exception as e:
                print(f"  ERROR: {e}")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()