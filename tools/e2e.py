#!/usr/bin/env python3
"""Optional real-browser E2E smoke for the static site.

Local-only: Playwright + chromium are not installed in CI, so this harness is
run on demand (python tools/e2e.py) and stays out of the verify gate. It spins
up a throwaway http.server on a free port and runs the scenarios listed in
main():

Every run prints the genre-collation branch it resolved and, for the two film-page
scenarios, the worst related-poster crop found in the 4 shipped related posters
(FILM_PAGE.related, the complete list the generator chose — not a wider pool).

main page
  1. search: typing "матриц" leaves exactly the two Matrix films
  2. genre filter: ?genre=ai is preselected, option labels are sorted the way
     js/app.js sorts them, the result count disappears when no filter is active
  3. featured grid: 8 distinct cards each with a poster; a horizontal snap
     scroller at 390px (xs) and a 2-column grid at 576px (sm), with no
     document-level horizontal overflow
  4. lang toggle: document.title switches to the English variant
  5. boot fallback: blocking js/catalog.js reveals the #boot-fallback message
  6. lucky button: navigates to a film page whose title leads with its h1
  7. poster modal: the lightbox img matches its natural size and the _400 src
about page
  8. structure: one article, six sections, one svg per toolbar button
film page
  9. theme toggle flips html.dark; theme-color is declared statically as
     light + dark (media) metas, not swapped by JS; breadcrumb, share hrefs
     carrying the film slug and the encoded title, 4 related cards at 1280px
 10. lang toggle switches html.lang, the h1, the alt title, the breadcrumb
     label and the related titles
 11. mobile layout at 390px: single h1 in the header, 4 related cards in one
     horizontal row, 2:3 poster boxes that are not cropped past the recorded
     ceiling, related slugs drawn from FILM_PAGE.related, and a related-card
     srcset that offers the whole ladder with each candidate's own width

Each scenario uses a fresh browser context (localStorage is not shared,
so the lang/theme persistence cannot leak between tests). Exits non-zero
when at least one scenario fails.
"""

import functools
import locale
import re
import sys
import threading
import unicodedata
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import POSTER_VARIANT_WIDTHS, ROOT, variant_name, webp_size  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

FILM_PAGE = "films/tt0133093-the-matrix/index.html"
FILM_MOBILE_PAGE = "films/tt8488126-the-inventor-out-for-blood-in-silicon-valley/index.html"
RELATED_COUNT = 4
META_DARK = "#171b2d"
META_LIGHT = "#eef1f6"
DESKTOP = {"width": 1280, "height": 800}
XS = {"width": 390, "height": 900}
SM = {"width": 576, "height": 900}
RU_COLLATE_LOCALES = ("ru_RU.UTF-8", "ru_RU.utf8", "Russian_Russia.1251", "ru_RU")
RU_COLLATE_PROBES = ((("яблоко", "Яблоко"), -1), (("ёлка", "елка"), 1))
CYRILLIC_FOLD = str.maketrans({"ё": "е", "й": "и"})
POSTER_ASPECT = 2 / 3
POSTER_ASPECT_TOLERANCE = 0.02
POSTER_CROP_CEILING = 0.16
RELATED_POSTER_RATIOS = """async () => {
  const related = window.FILM_PAGE.related;
  const out = [];
  for (const r of related) {
    if (!r.poster) { out.push(['', null]); continue; }
    const src = '../../' + r.poster.replace(/^\\//, '').replace(/\\.webp$/, '_400.webp');
    const nat = await new Promise((res) => {
      const im = new Image();
      im.onload = () => res([im.naturalWidth, im.naturalHeight]);
      im.onerror = () => res(null);
      im.src = src;
    });
    out.push([r.poster.split('/').pop(), nat]);
  }
  return out;
}"""
RU_SORT_KEY = None


def is_latin_script(text):
    return all(ord(ch) < 128 or "LATIN" in unicodedata.name(ch, "") for ch in text)


def cyrillic_fold_key(label):
    return (label.lower().translate(CYRILLIC_FOLD), label)


def resolve_russian_sort_key():
    rejected = []
    for candidate in RU_COLLATE_LOCALES:
        try:
            locale.setlocale(locale.LC_COLLATE, candidate)
        except locale.Error:
            rejected.append(f"{candidate}: not available on this machine")
            continue
        probed = all(
            (locale.strcoll(a, b) < 0) == (want < 0) for (a, b), want in RU_COLLATE_PROBES
        )
        if probed:
            return functools.cmp_to_key(locale.strcoll), f"locale {candidate}", rejected
        rejected.append(f"{candidate}: accepted by the OS but rejected by the collation probe")
    return (
        cyrillic_fold_key,
        "FALLBACK cyrillic-fold + codepoint tie-break (diverges from ICU on letter case)",
        rejected,
    )


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def start_server():
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.handle_error = lambda *args: None
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
    if RU_SORT_KEY is None:
        raise RuntimeError(
            "RU_SORT_KEY is unresolved: main() must resolve_russian_sort_key() first,"
            " otherwise the genre order silently degrades to codepoint collation"
        )
    ru_order = sorted(labels, key=RU_SORT_KEY)
    assert labels == ru_order, (
        f"genre options must be sorted the way js/app.js sorts them"
        f" (localeCompare ru): {labels} != {ru_order}"
    )
    assert page.locator("#genre-filter").evaluate("el => !!el.closest('.catalog-tools')"), (
        "the genre filter must live inside .catalog-tools"
    )
    expect(page.locator(".result-count")).to_have_text(f"Найдено: {expected}")
    page.locator("#genre-filter").select_option("")
    expect(page.locator(".result-count")).to_have_count(0)


def test_featured_breakpoints(page, base):
    page.set_viewport_size(XS)
    page.goto(base + "index.html", wait_until="domcontentloaded")
    grid = page.locator(".featured-grid")
    expect(page.locator(".featured-card")).to_have_count(8)
    hrefs = page.locator(".featured-card").evaluate_all(
        "els => els.map(el => el.getAttribute('href'))"
    )
    assert len(set(hrefs)) == 8, f"featured cards must be 8 distinct films: {hrefs}"
    expect(page.locator(".featured-card img")).to_have_count(8)
    expect(grid).to_have_css("grid-auto-flow", "column")
    expect(grid).to_have_css("overflow-x", "auto")
    expect(grid).to_have_css("scroll-snap-type", "x mandatory")
    rows = page.locator(".featured-grid > li").evaluate_all(
        "els => [...new Set(els.map(el => Math.round(el.getBoundingClientRect().top)))]"
    )
    assert len(rows) == 1, f"xs tier must be one horizontal row, card tops {rows}"
    assert page.locator(".featured-card-meta").evaluate_all(
        "els => els.every(el => getComputedStyle(el).textOverflow === 'ellipsis'"
        " && getComputedStyle(el).whiteSpace === 'nowrap')"
    ), "the featured meta line must stay on one line with an ellipsis"
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), (
        "xs tier overflows the document horizontally"
    )
    page.set_viewport_size(SM)
    expect(grid).to_have_css("grid-auto-flow", "row")
    expect(grid).to_have_css("overflow-x", "visible")
    expect(grid).to_have_css("scroll-snap-type", "none")
    cols = grid.evaluate("el => getComputedStyle(el).gridTemplateColumns.split(' ').length")
    assert cols == 2, f"sm tier must be a 2-column grid, got {cols} columns"
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), (
        "sm tier overflows the document horizontally"
    )


def test_about_page(page, base):
    page.goto(base + "about.html", wait_until="domcontentloaded")
    expect(page.locator("h1")).to_have_text("О сайте")
    assert page.locator(".about-article").count() == 1, "expected exactly one .about-article"
    assert page.locator(".about-section").count() == 6, "expected six .about-section blocks"
    assert page.locator(".theme-toggle svg").count() == 1, "theme toggle must render one icon"
    assert page.locator(".lang svg").count() == 1, "lang toggle must render one icon"
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), (
        "about page overflows the document horizontally"
    )


def test_main_lang(page, base):
    page.goto(base + "index.html", wait_until="domcontentloaded")
    expect(page).to_have_title(
        "Фильмы и сериалы о компьютерах, технологиях и ИИ — IT Movies"
    )
    page.locator(".lang").click()
    expect(page).to_have_title(
        "Films and series on computers, technology and AI — IT Movies"
    )


def report_related_crop(page):
    rows = page.evaluate(RELATED_POSTER_RATIOS)
    measured = [(name, nat[0] / nat[1]) for name, nat in rows if nat and nat[1]]
    unmeasured = [name for name, nat in rows if not nat or not nat[1]]
    assert len(measured) >= RELATED_COUNT, (
        f"only {len(measured)} of {len(rows)} related posters could be measured;"
        f" unloaded or broken: {unmeasured}"
    )
    deltas = [(name, abs(ratio - POSTER_ASPECT)) for name, ratio in measured]
    worst_name, worst = max(deltas, key=lambda d: d[1])
    over = [name for name, d in deltas if d > POSTER_ASPECT_TOLERANCE]
    print(
        f"    related-crop: worst {worst:.4f} ({worst_name}),"
        f" {len(over)}/{RELATED_COUNT} off the {POSTER_ASPECT_TOLERANCE} project standard"
        f" [{len(over) * 100 // RELATED_COUNT}%], target {POSTER_ASPECT:.4f}"
        f" (complete sample: all {RELATED_COUNT} shipped related posters)"
    )
    assert worst <= POSTER_CROP_CEILING, (
        f"related-crop {worst:.4f} ({worst_name}) exceeds the recorded ceiling"
        f" {POSTER_CROP_CEILING}; the 2:3 crop defect is owned by Stage 2 and must not worsen"
    )


def assert_related_posters(page):
    posters = page.locator(".related .rc-poster")
    expect(posters.first).to_have_css("display", "block")
    ratios = posters.evaluate_all(
        "els => els.map(el => { const r = el.getBoundingClientRect();"
        " return r.height ? r.width / r.height : 0; })"
    )
    for ratio in ratios:
        assert abs(ratio - POSTER_ASPECT) <= POSTER_ASPECT_TOLERANCE, (
            f"related poster box must keep the {POSTER_ASPECT:.4f} aspect ratio"
            f" (tolerance {POSTER_ASPECT_TOLERANCE}), got {ratio:.4f}"
        )
    naturals = posters.evaluate_all(
        "els => els.map(el => el.naturalWidth && el.naturalHeight"
        " ? el.naturalWidth / el.naturalHeight : null)"
    )
    unmeasured = sum(1 for n in naturals if not n)
    assert unmeasured < RELATED_COUNT, (
        f"{unmeasured} of {len(naturals)} related posters never loaded,"
        f" so their crop cannot be judged"
    )
    for ratio in (n for n in naturals if n):
        assert abs(ratio - POSTER_ASPECT) <= POSTER_CROP_CEILING, (
            f"a rendered related poster is cropped by {abs(ratio - POSTER_ASPECT):.4f},"
            f" past the recorded ceiling {POSTER_CROP_CEILING}"
        )
    srcsets = posters.evaluate_all("els => els.map(el => el.getAttribute('srcset'))")
    for srcset in srcsets:
        parts = [p.strip() for p in (srcset or "").split(",")]
        assert len(parts) == len(POSTER_VARIANT_WIDTHS), (
            f"related poster srcset must offer the whole ladder "
            f"{list(POSTER_VARIANT_WIDTHS)}, got {srcset!r}"
        )
        for part, width in zip(parts, POSTER_VARIANT_WIDTHS):
            url, _, descriptor = part.rpartition(" ")
            assert descriptor == f"{width}w", (
                f"candidate {part!r} must carry its own width {width}w, ascending"
            )
            name = url.rsplit("/", 1)[-1]
            dims = webp_size(ROOT / "static/posters" / name)
            assert dims and dims[0] == width, (
                f"candidate {name!r} is not a {width}px-wide file, so its descriptor "
                f"lies about the file the browser would fetch"
            )


def test_film_theme(page, base):
    page.set_viewport_size(DESKTOP)
    page.goto(base + FILM_PAGE, wait_until="domcontentloaded")
    light = page.locator('meta[name="theme-color"]:not([media])')
    dark = page.locator('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]')
    expect(light).to_have_attribute("content", META_LIGHT)
    expect(dark).to_have_attribute("content", META_DARK)
    expect(page.locator("html.dark")).to_have_count(0)
    page.locator(".theme-toggle").click()
    expect(page.locator("html.dark")).to_have_count(1)
    page.locator(".share-row").wait_for(state="visible")
    share = page.locator(".share-row a.share-btn[data-net]")
    expect(share).to_have_count(6)
    slug = page.evaluate("() => window.ITMoviesCommon.itemSlug(window.FILM_PAGE.item)")
    title_ru = page.evaluate("() => window.FILM_PAGE.item.titleRu")
    encoded_title = quote(title_ru, safe="!'()*")
    share_hrefs = share.evaluate_all("els => els.map(el => [el.dataset.net, el.href])")
    for net, href in share_hrefs:
        assert slug in href, f"{net} share href must carry the film slug {slug!r}: {href}"
    without_title = sorted(net for net, href in share_hrefs if encoded_title not in href)
    assert without_title == ["linkedin"], (
        f"every share endpoint except LinkedIn's, which takes a URL only, must carry"
        f" the encoded RU title {title_ru!r}; missing from {without_title}"
    )
    expect(page.locator(".related a.rc")).to_have_count(RELATED_COUNT)
    assert_related_posters(page)
    report_related_crop(page)
    assert page.locator(".related .fav-icon").count() == 0, (
        "related cards must not repeat the author's-pick heart"
    )
    assert page.locator(".related .star").count() == 0, (
        "related cards must not repeat the high-rating star that catalog rows show"
    )
    bc = page.locator("nav.breadcrumb")
    expect(bc).to_be_visible()
    expect(bc).to_have_attribute("aria-label", "Главная")
    expect(bc.locator("a")).to_have_count(1)
    expect(bc.locator("a")).to_have_attribute("href", "../../")
    expect(bc.locator("a")).to_have_text("Главная")
    # The current crumb carries the record title; Stage 3 owns turning it into
    # a type label (see .superpowers/sdd/.../task-4-report.md).
    expect(bc.locator(".bc-type")).to_have_text("Матрица")
    expect(bc.locator(".bc-current")).to_have_text("Матрица")


def test_film_lang(page, base):
    page.goto(base + FILM_PAGE, wait_until="domcontentloaded")
    ru = page.evaluate("() => window.FILM_PAGE.item.titleRu")
    en = page.evaluate("() => window.FILM_PAGE.item.titleEn")
    assert en.strip() and is_latin_script(en), f"titleEn must be Latin script: {en!r}"
    expect(page.locator("html")).to_have_attribute("lang", "ru")
    expect(page.locator("h1.film-header-title")).to_have_text(ru)
    expect(page.locator(".film-header-alt")).to_have_text(en)
    page.locator(".lang").click()
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(page.locator("h1.film-header-title")).to_have_text(en)
    expect(page.locator(".film-header-alt")).to_have_text(ru)
    expect(page.locator("nav.breadcrumb")).to_have_attribute("aria-label", "Home")
    expect(page).to_have_title(re.compile(rf"^{re.escape(en)}( \(\d{{4}}\))? — "))
    titles = page.locator(".related .rc-title").all_text_contents()
    bad = [t for t in titles if not (t.strip() and is_latin_script(t))]
    assert not bad, f"EN related titles must be non-empty Latin script: {bad}"


def test_film_mobile_layout(page, base):
    page.set_viewport_size(XS)
    page.goto(base + FILM_MOBILE_PAGE, wait_until="domcontentloaded")
    assert page.locator("h1").count() == 1, "the film page must have exactly one h1"
    assert page.locator(".film-info h1").count() == 0, (
        "the film title must not be repeated inside .film-info"
    )
    ul = page.locator(".related ul")
    expect(ul).to_have_css("grid-auto-flow", "column")
    expect(ul).to_have_css("overflow-x", "auto")
    expect(page.locator(".related .rc")).to_have_count(RELATED_COUNT)
    rows = page.locator(".related > ul > li").evaluate_all(
        "els => [...new Set(els.map(el => Math.round(el.getBoundingClientRect().top)))]"
    )
    assert len(rows) == 1, f"xs tier must be one horizontal row, card tops {rows}"
    assert_related_posters(page)
    report_related_crop(page)
    hrefs = page.locator(".related a.rc").evaluate_all(
        "els => els.map(el => el.getAttribute('href'))"
    )
    related_slugs = page.evaluate(
        "() => window.FILM_PAGE.related"
        ".map(r => window.ITMoviesCommon.itemSlug(r))"
    )
    own = page.evaluate("() => window.ITMoviesCommon.itemSlug(window.FILM_PAGE.item)")
    assert own not in related_slugs, "related must not contain the current film"
    assert len(set(hrefs)) == RELATED_COUNT, f"related cards must be distinct: {hrefs}"
    for href in hrefs:
        assert re.fullmatch(r"\.\./[a-z0-9-]+/", href), f"bad related href {href!r}"
        assert href[3:-1] in related_slugs, f"{href} is not in related"
    titles = page.locator(".related .rc-title").all_text_contents()
    assert all(t.strip() for t in titles), f"every related card needs a title: {titles}"
    infos = page.locator(".related .rc-info").all_text_contents()
    bad = [i for i in infos if not re.fullmatch(r".+ · \d{4}", i.strip())]
    assert not bad, f"every related card needs genres and a 4-digit year: {bad}"
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), (
        "film page overflows the document horizontally at 390px"
    )


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
    h1 = page.locator("h1.film-header-title")
    expect(h1).to_be_visible()
    expect(page).to_have_title(re.compile(rf"^{re.escape(h1.inner_text().strip())}( \(\d{{4}}\))? — "))


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
    expect(page.locator(".poster-modal[open]")).to_have_count(0)


def main():
    global RU_SORT_KEY
    RU_SORT_KEY, branch, rejected = resolve_russian_sort_key()
    print(f"genre collation: {branch}")
    for note in rejected:
        print(f"  WARNING: {note}")
    headed = "--headed" in sys.argv
    shots = None
    for i, arg in enumerate(sys.argv):
        if arg == "--shots":
            shots = sys.argv[i + 1]
    httpd, base = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed)
            scenarios = [
                test_main_filter,
                test_genre_filter,
                test_featured_breakpoints,
                test_about_page,
                test_main_lang,
                test_film_theme,
                test_film_lang,
                test_film_mobile_layout,
                test_boot_fallback,
                test_lucky,
                test_poster_modal,
            ]
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