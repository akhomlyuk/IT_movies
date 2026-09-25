#!/usr/bin/env python3
"""Optional real-browser E2E smoke for the static site.

Local-only: Playwright + chromium are not installed in CI, so this harness is
run on demand (python tools/e2e.py) and stays out of the verify gate. It spins
up a throwaway http.server on a free port and runs four scenarios:

1. main page: typing "матриц" leaves exactly the two Matrix films
2. main page: the EN toggle switches document.title to the English variant
3. film page: the theme toggle flips html.dark; theme-color is declared
   statically as light + dark (media) metas, not swapped by JS
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

FILM_PAGE = "films/tt0133093-the-matrix/index.html"
META_DARK = "#171b2d"
META_LIGHT = "#eef1f6"


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


def test_genre_filter(page, base):
    page.goto(base + "index.html?genre=ai", wait_until="domcontentloaded")
    expected = page.evaluate(
        "window.CATALOG.filter((item) => item.genres.includes('ai')).length"
    )
    expect(page.locator("#genre-filter")).to_have_value("ai")
    labels = page.locator("#genre-filter option").all_text_contents()[1:]
    assert labels == sorted(labels)
    assert page.locator("#genre-filter").evaluate("el => !!el.closest('.catalog-tools')")
    expect(page.locator(".result-count")).to_have_text(f"Найдено: {expected}")
    page.locator("#genre-filter").select_option("")
    expect(page.locator(".result-count")).to_have_count(0)


def test_featured_mobile_limit(page, base):
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(base + "index.html", wait_until="domcontentloaded")
    assert page.locator(".featured-card").count() == 8
    assert page.locator(".featured-card:visible").count() == 4
    assert page.locator(".featured-grid").evaluate(
        "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
    ) == 2
    assert page.locator(".featured-card-title").evaluate_all(
        "els => els.every(el => getComputedStyle(el).textOverflow === 'ellipsis' && getComputedStyle(el).whiteSpace === 'nowrap')"
    )
    assert page.locator(".featured-card-meta").evaluate_all(
        "els => els.every(el => getComputedStyle(el).textOverflow === 'ellipsis' && getComputedStyle(el).whiteSpace === 'nowrap')"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def test_main_lang(page, base):
    page.goto(base + "index.html", wait_until="domcontentloaded")
    expect(page).to_have_title(
        "Фильмы и сериалы о компьютерах, технологиях и ИИ — IT Movies"
    )
    page.locator(".lang").click()
    expect(page).to_have_title(
        "Films and series on computers, technology and AI — IT Movies"
    )


def test_film_theme(page, base):
    page.goto(base + FILM_PAGE, wait_until="domcontentloaded")
    light = page.locator('meta[name="theme-color"]:not([media])')
    dark = page.locator('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]')
    expect(light).to_have_attribute("content", META_LIGHT)
    expect(dark).to_have_attribute("content", META_DARK)
    expect(page.locator("html.dark")).to_have_count(0)
    page.locator(".theme-toggle").click()
    expect(page.locator("html.dark")).to_have_count(1)
    page.locator(".share-row").wait_for(state="visible")
    assert page.locator(".share-row a.share-btn[data-net]").count() >= 3
    assert page.locator(".related ul li a").count() >= 1
    bc = page.locator("nav.breadcrumb")
    expect(bc).to_be_visible()
    expect(bc.locator("a")).to_have_attribute("href", "../../")
    expect(bc.locator("a")).to_have_text("Главная")
    expect(page.locator(".bc-current .bc-type")).to_have_text("Фильм")
    expect(page.locator(".bc-current .visually-hidden")).to_contain_text("Матрица")


def test_film_mobile_header(page, base):
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(base + "films/tt8488126-the-inventor-out-for-blood-in-silicon-valley/index.html", wait_until="domcontentloaded")
    assert page.locator("h1").count() == 1
    assert page.locator(".film-info h1").count() == 0
    assert page.locator(".related .rc").count() == 6
    assert page.locator(".related .rc:visible").count() == 4
    assert page.locator(".related .rc-poster").first.evaluate("el => getComputedStyle(el).display") == "none"
    assert page.locator(".related .star").count() == 0
    assert page.locator(".related .fav-icon").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def test_boot_fallback(page, base):
    page.route(re.compile(r"js/catalog\.js$"), lambda route: route.abort())
    page.goto(base + "index.html", wait_until="domcontentloaded")
    expect(page.locator("#boot-fallback")).to_be_visible()
    expect(page.locator("#movies tbody tr")).to_have_count(0)


def test_lucky(page, base):
    page.goto(base + "index.html", wait_until="domcontentloaded")
    btn = page.locator("button.lucky")
    expect(btn).to_have_attribute("aria-label", "Мне повезёт")
    btn.click()
    page.wait_for_url(re.compile(r"/films/[^/]+/$"))
    assert page.title()


def test_poster_modal(page, base):
    page.goto(base + "index.html", wait_until="domcontentloaded")
    page.locator(".poster-icon").first.click()
    page.locator(".poster-modal[open]").wait_for(state="visible")
    img = page.locator(".poster-modal-inner > img")
    page.wait_for_function(
        "sel => { const el = document.querySelector(sel);"
        " return el && el.complete && el.naturalWidth > 0; }",
        arg=".poster-modal-inner > img",
    )
    dims_ok = img.evaluate(
        "el => +el.getAttribute('width') === el.naturalWidth"
        " && +el.getAttribute('height') === el.naturalHeight"
    )
    assert dims_ok, "modal img width/height attrs must match natural dims (CLS0)"
    src = img.get_attribute("src")
    assert src and "_400" in src, f"modal src must be _400 variant, got {src!r}"
    page.locator(".poster-close").click()


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
            scenarios = [test_main_filter, test_genre_filter, test_featured_mobile_limit, test_main_lang, test_film_theme, test_film_mobile_header, test_boot_fallback, test_lucky, test_poster_modal]
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