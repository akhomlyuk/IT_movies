#!/usr/bin/env python3
"""Optional real-browser E2E smoke for the static site.

Local-only: Playwright + chromium are not installed in CI, so this harness is
run on demand (python tools/e2e.py) and stays out of the verify gate. It spins
up a throwaway http.server on a free port and runs four scenarios:

1. main page: typing "матриц" leaves exactly the two Matrix films
2. main page: the EN toggle switches document.title to the English variant
3. film page: the theme toggle flips html.dark and meta[name=theme-color]
4. main page: blocking js/catalog.js reveals the #boot-fallback message

Each scenario uses a fresh browser context (localStorage is not shared,
so the lang/theme persistence cannot leak between tests). Exits non-zero
when at least one scenario fails.
"""

import functools
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import ROOT  # noqa: E402

FILM_PAGE = "films/tt0133093-the-matrix/index.html"
META_DARK = "#1a1a1f"
META_LIGHT = "#f4f3ef"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def start_server():
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{port}/"


def test_main_filter(page, base):
    page.goto(base + "index.html", wait_until="domcontentloaded")
    page.locator("#srch").fill("матриц")
    expect(page.locator("#movies tbody tr")).to_have_count(2)


def test_main_lang(page, base):
    page.goto(base + "index.html", wait_until="domcontentloaded")
    expect(page).to_have_title(
        "IT Movies - Каталог фильмов и сериалов о компьютерах, технологиях и искусственном интеллекте"
    )
    page.locator(".lang button", has_text="EN").click()
    expect(page).to_have_title(
        "IT Movies - A catalog of films and series about computers, technology and AI"
    )


def test_film_theme(page, base):
    page.goto(base + FILM_PAGE, wait_until="domcontentloaded")
    meta = page.locator('meta[name="theme-color"]')
    expect(page.locator("html.dark")).to_have_count(0)
    expect(meta).to_have_attribute("content", META_LIGHT)
    page.locator('.theme-toggle button[aria-label="Тёмная тема"]').click()
    expect(page.locator("html.dark")).to_have_count(1)
    expect(meta).to_have_attribute("content", META_DARK)
    page.locator(".share-row").wait_for(state="visible")
    assert page.locator(".share-row a.share-btn[data-net]").count() >= 3
    assert page.locator(".related ul li a").count() >= 1


def test_boot_fallback(page, base):
    page.route(re.compile(r"js/catalog\.js$"), lambda route: route.abort())
    page.goto(base + "index.html", wait_until="domcontentloaded")
    expect(page.locator("#boot-fallback")).to_be_visible()
    expect(page.locator("#movies tbody tr")).to_have_count(0)


def main():
    headed = "--headed" in sys.argv
    shots = None
    for i, arg in enumerate(sys.argv):
        if arg == "--shots":
            shots = sys.argv[i + 1]
    httpd, base = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed)
            scenarios = [test_main_filter, test_main_lang, test_film_theme, test_boot_fallback]
            failed = 0
            if shots:
                Path(shots).mkdir(parents=True, exist_ok=True)
            for fn in scenarios:
                ctx = browser.new_context(locale="ru-RU")
                page = ctx.new_page()
                try:
                    fn(page, base)
                    if shots:
                        page.screenshot(path=str(Path(shots) / f"{fn.__name__}.png"), full_page=True)
                    print(f"PASS {fn.__name__}")
                except Exception as e:
                    failed += 1
                    print(f"FAIL {fn.__name__}: {e}")
                finally:
                    ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    if failed:
        print(f"FAILED: {failed} of {len(scenarios)} scenarios")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())