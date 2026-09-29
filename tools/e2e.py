#!/usr/bin/env python3
"""Optional real-browser E2E smoke for the static site.

Local-only: Playwright + chromium are not installed in CI, so this harness is
run on demand (python tools/e2e.py) and stays out of the verify gate. It spins
up a throwaway http.server on a free port and runs the scenarios listed in
main():

Every run prints the genre-collation branch it resolved and, for the two film-page
scenarios, the DISCARDED AREA the related posters lose to the box they are
rendered into -- the fraction of each selected file's area that `object-fit: cover`
throws away, computed by tools/poster_crop.py, which owns the bound
(POSTER_CROP_CEILING, the old aspect-ratio proxy, is gone; see poster_crop.py).
This harness reports that number and does not gate on it: a 4-poster ceiling is
how the previous one sat 3.1x above its own worst sample. What it does assert is
the two things only a browser can see -- the rendered box is 2:3, and the file the
browser selected is a real file on disk.

main page
  1. search: typing "матриц" leaves exactly the two Matrix films
  2. genre filter: ?genre=ai is preselected, option labels are sorted the way
     js/app.js sorts them, the result count disappears when no filter is active
  3. featured grid: 6 distinct cards each with a poster; a horizontal snap
     scroller at 390px (xs) and a 2-column grid at 576px (sm), with no
     document-level horizontal overflow
  4. lang toggle: document.title switches to the English variant
  5. boot fallback: blocking js/catalog.js reveals the #boot-fallback message
  6. lucky button: navigates to a film page whose title leads with its card h1
  7. poster modal: the lightbox img matches its natural size and the _400 src
about page
  8. structure: one article, six sections, one svg per toolbar button
film page
  9. theme toggle flips html.dark; theme-color is declared statically as
     light + dark (media) metas, not swapped by JS; breadcrumb, share hrefs
     carrying the film slug and the encoded title, 4 related cards at 1280px
 10. lang toggle switches html.lang, the card h1, the alt title, the breadcrumb
     label and the related titles; the header carries the site name and no h1
 11. mobile layout at 390px: exactly one h1, inside .film-info, 4 related cards
     in one horizontal row, 2:3 poster boxes reported with the area they discard,
     the selected file verified against disk, related slugs drawn from
     FILM_PAGE.related, and a related-card srcset that offers the whole ladder with
     each candidate's own width
  12. nav tier: exactly one navigation affordance reachable at 320/375/575/576/
      768/1280 -- burger below xs, inline row above it, never both and never
      neither; the xs dialog is a real modal (showModal) whose focus trap holds
      and whose Esc returns focus to the burger; and with JavaScript DISABLED the
      burger is absent and the inline row still carries all three anchors, so a
      JS-only control cannot lock the no-JS reader out of the nav
  13. no-JS cloak: with JavaScript DISABLED no rendered text on /index.html
      contains a {{ }} placeholder, the generated noscript catalogue renders all
      154 of its links, and the pre-mount brand and the three static nav labels
      read as content -- the cloak is unconditional, so the no-JS reader gets the
      catalogue rather than the template source

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
import poster_crop  # noqa: E402
from lib import POSTER_VARIANT_WIDTHS, ROOT, variant_name, webp_size  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

FILM_PAGE = "films/tt0133093-the-matrix/index.html"
FILM_MOBILE_PAGE = "films/tt8488126-the-inventor-out-for-blood-in-silicon-valley/index.html"
RELATED_COUNT = 6
I18N_RU_SUBTITLE = "Подборка фильмов и сериалов о компьютерах, технологиях, ИИ и т.д."
META_DARK = "#14120F"
META_LIGHT = "#F4F2ED"
DESKTOP = {"width": 1280, "height": 800}
XS = {"width": 390, "height": 900}
SM = {"width": 576, "height": 900}
RU_COLLATE_LOCALES = ("ru_RU.UTF-8", "ru_RU.utf8", "Russian_Russia.1251", "ru_RU")
RU_COLLATE_PROBES = ((("яблоко", "Яблоко"), -1), (("ёлка", "елка"), 1))
CYRILLIC_FOLD = str.maketrans({"ё": "е", "й": "и"})
POSTER_ASPECT = 2 / 3
POSTER_ASPECT_TOLERANCE = 0.02
RELATED_POSTER_RENDERED = """() => {
  const out = [];
  for (const el of document.querySelectorAll('.related .rc-poster')) {
    const r = el.getBoundingClientRect();
    out.push([r.width, r.height, el.currentSrc.split('/').pop(), el.complete]);
  }
  return out;
}"""
RU_SORT_KEY = None

NOJS_RENDER = r"""() => {
  const painted = (el) => !!el && el.checkVisibility({checkVisibilityCSS: true});
  const potential = (el) => {
    if (!el) return false;
    let p = el;
    while (p && p !== document.documentElement) {
      const cs = getComputedStyle(p);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      p = p.parentElement;
    }
    return true;
  };
  const leaked = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = n.nodeValue || '';
    if (t.indexOf('{{') === -1 && t.indexOf('}}') === -1) continue;
    if (potential(n.parentElement)) {
      leaked.push(n.parentElement.tagName + '.' + (n.parentElement.className || '')
        + ' -> ' + t.trim());
    }
  }
  const nosc = document.querySelector('noscript.no-js-catalog');
  const links = nosc ? Array.prototype.slice.call(nosc.querySelectorAll('a')) : [];
  const nav = document.querySelector('nav.nav:not(.nav--dialog)');
  const anchors = nav ? Array.prototype.slice.call(nav.querySelectorAll('a')) : [];
  return {
    innerText: document.body.innerText || '',
    leaked: leaked,
    catalogLinks: links.length,
    catalogLinksRendered: links.filter(painted).length,
    navRendered: painted(nav),
    navAnchors: anchors.length,
    navLabels: anchors.map((a) => (a.innerText || '').replace(/\s+/g, ' ').trim()),
    brandRendered: painted(document.querySelector('.brand')),
    h1: ((document.querySelector('#app h1') || {}).innerText || '').trim(),
  };
}"""

AFFORDANCES = """() => {
  const shown = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const burger = document.querySelector('button.menu-toggle');
  const inline = document.querySelector('nav.nav:not(.nav--dialog)');
  return {
    burger: shown(burger),
    burgerExpanded: burger ? burger.getAttribute('aria-expanded') : null,
    burgerControls: burger ? burger.getAttribute('aria-controls') : null,
    burgerHaspopup: burger ? burger.getAttribute('aria-haspopup') : null,
    burgerLabel: burger ? burger.getAttribute('aria-label') : null,
    inline: shown(inline),
    inlineAnchors: shown(inline) ? inline.querySelectorAll('a').length : 0,
    dialogInDom: !!document.getElementById('nav-dialog'),
  };
}"""


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
    expect(page.locator(".featured-card")).to_have_count(6)
    hrefs = page.locator(".featured-card").evaluate_all(
        "els => els.map(el => el.getAttribute('href'))"
    )
    assert len(set(hrefs)) == 6, f"featured cards must be 6 distinct films: {hrefs}"
    expect(page.locator(".featured-card img")).to_have_count(6)
    expect(grid).to_have_css("grid-auto-flow", "column")
    expect(grid).to_have_css("overflow-x", "auto")
    expect(grid).to_have_css("scroll-snap-type", "x mandatory")
    rows = page.locator(".featured-grid > li").evaluate_all(
        "els => [...new Set(els.map(el => Math.round(el.getBoundingClientRect().top)))]"
    )
    assert len(rows) == 1, f"xs tier must be one horizontal row, card tops {rows}"
    assert page.locator(".featured-card-meta").evaluate_all(
        "els => els.every(el => getComputedStyle(el).whiteSpace === 'normal'"
        " && getComputedStyle(el).webkitLineClamp === '2'"
        " && getComputedStyle(el).webkitBoxOrient === 'vertical')"
    ), "the featured meta line must wrap, clamped to 2 lines"
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


HEADER_TOOLS_GAP = """
  () => document.querySelector('.catalog-tools').getBoundingClientRect().top
       - document.querySelector('header.top').getBoundingClientRect().bottom
"""


def test_nav_tier(page, base):
    """Exactly one navigation affordance at every width, with and without JS.

    The invariant is reachability, not the mechanism: the burger and the inline
    row are two implementations of one affordance, and the page may use either,
    but never both at once and never neither. The dialog must be a real modal --
    the platform's own, so that Esc and the focus trap are the browser's.
    """
    xs = [320, 375, 575]
    above = [576, 768, 1280]
    for width in xs + above:
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(base + "index.html", wait_until="domcontentloaded")
        expect(page.locator("nav.nav:not(.nav--dialog) a")).to_have_count(3)
        d = page.evaluate(AFFORDANCES)
        assert d["dialogInDom"], f"@{width}: the dialog must exist in the DOM"
        total = int(d["burger"]) + int(d["inline"])
        assert total == 1, (
            f"@{width}: exactly one navigation affordance must be reachable, got "
            f"burger={d['burger']} inline={d['inline']} (both/neither is the defect)"
        )
        if width in xs:
            assert d["burger"], f"@{width}: xs must offer the burger, not the inline row"
            assert d["burgerExpanded"] == "false", (
                f"@{width}: a closed dialog must report aria-expanded=false, "
                f"got {d['burgerExpanded']!r}"
            )
            assert d["burgerHaspopup"] == "dialog", (
                f"@{width}: the burger must declare aria-haspopup=dialog, "
                f"got {d['burgerHaspopup']!r}"
            )
            assert d["burgerControls"], f"@{width}: the burger must name what it controls"
            assert d["burgerLabel"], f"@{width}: the burger needs an accessible name"
        else:
            assert d["inline"], f"@{width}: above xs the inline row is the affordance"
            assert d["inlineAnchors"] == 3, (
                f"@{width}: the inline row must keep all three anchors, "
                f"got {d['inlineAnchors']}"
            )
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        ), f"@{width}: the document overflows horizontally"
        assert page.evaluate(HEADER_TOOLS_GAP) >= 8, (
            f"@{width}: the header's accent rule must not touch the tools row; "
            f"measured {page.evaluate(HEADER_TOOLS_GAP):.2f}px. The separation is "
            f"declared nowhere in the stylesheet -- it arrived as nav.nav's own "
            f"margin, and display:none takes that margin with the element."
        )

    page.set_viewport_size(XS)
    page.goto(base + "index.html", wait_until="domcontentloaded")
    burger = page.locator("button.menu-toggle")
    expect(burger).to_have_attribute("aria-expanded", "false")
    burger.click()
    dialog = page.locator("dialog#nav-dialog")
    expect(dialog).to_have_attribute("open", "")
    assert page.evaluate("document.getElementById('nav-dialog').matches(':modal')"), (
        "the dialog must be a real modal (showModal), not a styled panel"
    )
    expect(burger).to_have_attribute("aria-expanded", "true")
    assert page.evaluate("document.activeElement.closest('dialog') !== null"), (
        "opening must move focus into the dialog"
    )
    inside = page.evaluate(
        "() => document.getElementById('nav-dialog')"
        ".querySelectorAll('a,button').length"
    )
    # The invariant is that no focusable control OUTSIDE the dialog ever takes
    # focus. The browser's modal cycle passes through <body> on its way back
    # around, so <body> is the seam, not an escape; a control outside is.
    for i in range(inside + 2):
        page.keyboard.press("Tab")
        escaped = page.evaluate("""
          () => {
            const a = document.activeElement;
            if (a === document.body || a === document.documentElement) return null;
            return a.closest('dialog') ? null : (a.className || a.tagName);
          }
        """)
        assert escaped is None, (
            f"Tab {i + 1} put focus on {escaped!r}, outside the open dialog; "
            f"the trap is the platform's to provide"
        )
    assert page.evaluate(
        "document.activeElement.closest('dialog') !== null"
    ), "the dialog's tab cycle must close back inside itself"
    page.keyboard.press("Escape")
    expect(dialog).not_to_have_attribute("open", "")
    assert page.evaluate("document.getElementById('nav-dialog').open") is False, (
        "Esc must close the dialog -- the browser's own, not a handler"
    )
    assert page.evaluate(
        "document.activeElement === document.querySelector('button.menu-toggle')"
    ), "Esc must return focus to the burger"
    expect(burger).to_have_attribute("aria-expanded", "false")

    nojs = page.context.browser.new_context(
        java_script_enabled=False, locale="ru-RU"
    )
    try:
        npage = nojs.new_page()
        for width in xs:
            npage.set_viewport_size({"width": width, "height": 900})
            npage.goto(base + "index.html", wait_until="domcontentloaded")
            d = npage.evaluate(AFFORDANCES)
            assert not d["burger"], (
                f"@{width} without JS: the burger cannot work, so it must not be shown"
            )
            assert d["inline"], (
                f"@{width} without JS: the inline nav is the only affordance left and "
                f"must stay visible -- a JS-only control would lock the nav out"
            )
            assert d["inlineAnchors"] == 3, (
                f"@{width} without JS: expected 3 inline anchors, got {d['inlineAnchors']}"
            )
            assert npage.evaluate(HEADER_TOOLS_GAP) >= 8, (
                f"@{width} without JS: the accent rule must not touch the tools row; "
                f"measured {npage.evaluate(HEADER_TOOLS_GAP):.2f}px"
            )
    finally:
        nojs.close()


def test_nojs_cloak(page, base):
    """No rendered Vue placeholder anywhere on /index.html with JavaScript off.

    The cloak is unconditional, so the no-JS reader gets the noscript catalogue
    and the static pre-mount header, never the template source. The probe waits
    for `load`, not `domcontentloaded`: with scripting disabled Chromium can run
    DOMContentLoaded before the stylesheet is applied, and a probe that reads
    computed style in that window would measure the uncloaked DOM and pass.
    """
    nojs = page.context.browser.new_context(
        java_script_enabled=False, locale="ru-RU"
    )
    try:
        npage = nojs.new_page()
        for width in (320, 375, 575, 1280):
            npage.set_viewport_size({"width": width, "height": 900})
            npage.goto(base + "index.html", wait_until="load")
            d = npage.evaluate(NOJS_RENDER)
            assert not d["leaked"], (
                f"@{width} without JS: {len(d['leaked'])} rendered placeholder(s): "
                f"{d['leaked'][:4]}"
            )
            assert "{{" not in d["innerText"] and "}}" not in d["innerText"], (
                f"@{width} without JS: the rendered page text contains a template "
                f"placeholder"
            )
            assert d["catalogLinks"] > 0, (
                f"@{width} without JS: the noscript catalogue carries no links"
            )
            assert d["catalogLinksRendered"] == d["catalogLinks"], (
                f"@{width} without JS: {d['catalogLinks'] - d['catalogLinksRendered']}"
                f" of {d['catalogLinks']} catalogue links are not rendered -- the "
                f"cloak hides the <main> the <noscript> lives in"
            )
            assert d["navRendered"], (
                f"@{width} without JS: the inline nav row is the only affordance "
                f"left, so the cloak must not take it"
            )
            assert d["navAnchors"] == 3, (
                f"@{width} without JS: expected 3 inline anchors, got {d['navAnchors']}"
            )
            for label in d["navLabels"]:
                assert label, (
                    f"@{width} without JS: a nav anchor renders no text at all -- "
                    f"reachable but blank is not an affordance"
                )
                assert "{{" not in label and "}}" not in label, (
                    f"@{width} without JS: the nav label is template source: {label!r}"
                )
            assert d["brandRendered"], (
                f"@{width} without JS: the pre-mount brand must stay visible"
            )
            assert d["h1"] == "IT Movies", (
                f"@{width} without JS: the pre-mount h1 must read 'IT Movies', "
                f"got {d['h1']!r}"
            )
    finally:
        nojs.close()


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
    """Report the discarded area of the related posters AS RENDERED, and bound nothing.

    The bound lives in poster_crop.DISCARDED_AREA_CEILING and is measured there
    over all 154 posters from real file dimensions. A second ceiling over 4
    posters would be a second number meaning the same thing, so this function
    reports the same quantity with the same code and asserts nothing about it.

    What only a browser can see, and what this therefore checks, is that the
    RENDERED box is 2:3 and that the file the browser actually selected is a real
    file on disk. The old probe read neither: it built a bare `new Image()` on
    the `_400` rung, which is not necessarily the rung that was selected, and
    `assert_related_posters` read `naturalWidth` on a srcset image, which Chromium
    density-corrects (measured: 240x355 reported for the 400x593 rung in a 240px
    slot). Both are replaced by currentSrc plus the real file on disk.
    """
    rows = page.evaluate(RELATED_POSTER_RENDERED)
    assert len(rows) == RELATED_COUNT, (
        f"expected {RELATED_COUNT} rendered related posters, got {len(rows)}"
    )
    measured = []
    for box_w, box_h, name, complete in rows:
        assert complete and name, (
            "a related poster never finished loading, so what it lost to the box "
            "cannot be judged"
        )
        path = ROOT / "static" / "posters" / name
        assert path.exists(), f"the browser selected {name!r}, which is not on disk"
        width, height = poster_crop.poster_size(path)
        measured.append((
            name,
            box_w,
            box_h,
            width,
            height,
            poster_crop.aspect_deviation(width, height),
            poster_crop.discarded_area(width, height, box_w, box_h),
        ))
    worst_row = max(measured, key=lambda m: m[6])
    over = [m for m in measured if m[6] > poster_crop.REPORT_TOLERANCE]
    boxes = sorted({(round(m[1], 3), round(m[2], 3)) for m in measured})
    print(
        f"    related-crop: rendered box {boxes} (2:3: "
        f"{all(poster_crop.is_two_by_three((int(m[1]), int(m[2]))) for m in measured)}),"
        f" worst discarded {worst_row[6]:.4f} ({worst_row[0]}, selected file"
        f" {worst_row[3]}x{worst_row[4]}), {len(over)}/{RELATED_COUNT} over"
        f" {poster_crop.REPORT_TOLERANCE}"
    )
    print(
        f"      bound is poster_crop.DISCARDED_AREA_CEILING"
        f" {poster_crop.DISCARDED_AREA_CEILING}, owned by tools/poster_crop.py over all"
        f" 154 posters; this function reports and does not gate"
    )
    return measured


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
    loaded = posters.evaluate_all(
        "els => els.map(el => el.complete && el.naturalWidth > 0)"
    )
    unmeasured = sum(1 for ok in loaded if not ok)
    assert unmeasured == 0, (
        f"{unmeasured} of {len(loaded)} related posters never loaded, so the box they"
        f" are fitted into cannot be judged against what is in it"
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


def assert_rail_controls(page, expect_overflow):
    """The rail's controls must exist exactly when the strip scrolls.

    Asserted by measurement, not by markup: only a browser can say whether the
    track overflows, and controls for a strip that cannot be paged are worse
    than no controls. Six cards at 170px plus 12px gaps is 1080px of strip,
    which overflows the 1040px container at every width -- the arrows are not a
    narrow-viewport affordance.
    """
    track = page.locator(".related-track")
    overflows = track.evaluate("el => el.scrollWidth > el.clientWidth + 1")
    if overflows != expect_overflow:
        raise AssertionError(
            f"expected the rail to {'scroll' if expect_overflow else 'fit'} at this"
            f" width, but scrollWidth={track.evaluate('el => el.scrollWidth')}"
            f" clientWidth={track.evaluate('el => el.clientWidth')}"
        )
    nav = page.locator(".related-nav")
    dots = page.locator(".related-dot")
    if expect_overflow:
        expect(nav).to_have_count(2)
        assert dots.count() >= 1, "a scrolling rail must offer dots"
        expect(page.locator(".related-nav--prev")).to_be_disabled()
        expect(page.locator(".related-nav--next")).to_be_enabled()
        # Walk to the end one page at a time. How many clicks that takes depends
        # on the width -- two pages at 1280, four at 390 -- so a single click
        # only proves the arithmetic on the widest tier.
        next_btn = page.locator(".related-nav--next")
        for _ in range(dots.count() + 1):
            if next_btn.is_disabled():
                break
            next_btn.click()
            page.wait_for_timeout(120)
        # Reaching the end must enable "previous" again. The browser clamps
        # scrollLeft, so on a short last page the index has to be recognised
        # from the end position rather than read back from the offset.
        page.wait_for_function(
            "() => { const el = document.querySelector('.related-track');"
            " return el && el.scrollLeft >= el.scrollWidth - el.clientWidth - 2; }"
        )
        expect(next_btn).to_be_disabled()
        expect(page.locator(".related-nav--prev")).to_be_enabled()
        expect(page.locator(".related-dot.is-active")).to_have_count(1)
        # And back to the start, where the roles swap.
        prev_btn = page.locator(".related-nav--prev")
        for _ in range(dots.count() + 1):
            if prev_btn.is_disabled():
                break
            prev_btn.click()
            page.wait_for_timeout(120)
        page.wait_for_function(
            "() => { const el = document.querySelector('.related-track');"
            " return el && el.scrollLeft <= 2; }"
        )
        expect(prev_btn).to_be_disabled()
        expect(next_btn).to_be_enabled()
    else:
        expect(nav).to_have_count(0), (
            "a rail that fits must not offer arrows for scrolling it cannot do"
        )
        expect(dots).to_have_count(0)


def assert_ratings_on_one_line(page, max_height=32):
    """Both rating chips must share one line.

    The hole this replaced was a wrap, not empty space: .rc-content was a 102px
    column, so the two chips could not fit side by side and .rc-meta measured
    60px tall. One line is 24px; two was 60.
    """
    heights = page.locator(".related .rc-meta").evaluate_all(
        "els => [...new Set(els.map(el => Math.round(el.getBoundingClientRect().height)))]"
    )
    assert len(heights) == 1 and heights[0] <= max_height, (
        f"rating chips must share one line per card, got meta heights {heights}"
    )
    rows = page.locator(".related .rc-meta").evaluate_all(
        "els => els.map(el => new Set([...el.children].map(c =>"
        " Math.round(c.getBoundingClientRect().top))).size)"
    )
    assert set(rows) == {1}, f"every card's chips must be on one line, got {set(rows)} rows"


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
    expect(share).to_have_count(5)
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
    assert_badge_on_poster(page)
    assert_rail_controls(page, expect_overflow=True)
    assert_ratings_on_one_line(page)


def assert_badge_on_poster(page):
    """The author's pick is a badge ON the poster, not a chip in the info column.

    Asserted geometrically rather than by markup alone: only a browser can say the
    badge actually lands inside the poster's painted box, and the whole point of the
    change is where it renders. `.film-poster` is the positioned ancestor, so a
    regression that moves the badge out of the figure moves it out of the box.
    """
    poster = page.locator(".film-poster")
    badge = page.locator(".film-badge")
    assert page.locator(".film-info .film-badge").count() == 0, (
        "the author's-pick badge must not stay in .film-info"
    )
    if not badge.count():
        # A record without fav:true legitimately renders no badge. The Matrix has
        # one, so on the pages that use this the assertion is not vacuous.
        return
    p = poster.bounding_box()
    b = badge.bounding_box()
    assert b["x"] >= p["x"] and b["y"] >= p["y"], (
        f"the badge must sit inside the poster box, got badge {b} poster {p}"
    )
    assert b["x"] + b["width"] <= p["x"] + p["width"] + 0.5, (
        f"the badge must not overhang the poster's right edge, got badge {b} poster {p}"
    )
    assert b["y"] + b["height"] <= p["y"] + p["height"] + 0.5, (
        f"the badge must not overhang the poster's bottom edge, got badge {b} poster {p}"
    )


def test_film_lang(page, base):
    page.goto(base + FILM_PAGE, wait_until="domcontentloaded")
    ru = page.evaluate("() => window.FILM_PAGE.item.titleRu")
    en = page.evaluate("() => window.FILM_PAGE.item.titleEn")
    assert en.strip() and is_latin_script(en), f"titleEn must be Latin script: {en!r}"
    expect(page.locator("html")).to_have_attribute("lang", "ru")
    expect(page.locator(".brand .brand-name")).to_have_text("IT Movies")
    expect(page.locator(".brand-text p")).to_have_text(I18N_RU_SUBTITLE)
    expect(page.locator(".related-nav--prev")).to_have_attribute("aria-label", "Предыдущие")
    assert page.locator("header.top h1").count() == 0, (
        "the header carries the site name, so the film page's single h1 belongs to"
        " the card, not the header"
    )
    expect(page.locator("h1.film-title")).to_have_text(ru)
    expect(page.locator(".film-alt")).to_have_text(en)
    page.locator(".lang").click()
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(page.locator("h1.film-title")).to_have_text(en)
    expect(page.locator(".film-alt")).to_have_text(ru)
    expect(page.locator(".related-nav--prev")).to_have_attribute("aria-label", "Previous")
    expect(page.locator(".related-nav--next")).to_have_attribute("aria-label", "Next")
    expect(page.locator("nav.breadcrumb")).to_have_attribute("aria-label", "Home")
    expect(page).to_have_title(re.compile(rf"^{re.escape(en)}( \(\d{{4}}\))? — "))
    titles = page.locator(".related .rc-title").all_text_contents()
    bad = [t for t in titles if not (t.strip() and is_latin_script(t))]
    assert not bad, f"EN related titles must be non-empty Latin script: {bad}"


def test_film_mobile_layout(page, base):
    page.set_viewport_size(XS)
    page.goto(base + FILM_MOBILE_PAGE, wait_until="domcontentloaded")
    assert page.locator("h1").count() == 1, "the film page must have exactly one h1"
    assert page.locator(".film-info h1.film-title").count() == 1, (
        "the one h1 must be the card's film title, not a repeat of the header one"
    )
    assert page.locator("header.top h1").count() == 0, (
        "the header carries the site name, so it must not hold an h1"
    )
    assert_badge_on_poster(page)
    track = page.locator(".related-track")
    expect(track).to_have_css("overflow-x", "auto")
    expect(track).to_have_css("scroll-snap-type", "x mandatory")
    expect(page.locator(".related .rc")).to_have_count(RELATED_COUNT)
    assert_rail_controls(page, expect_overflow=True)
    assert_ratings_on_one_line(page)
    rows = page.locator(".related-track > li").evaluate_all(
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
    # The controls are computed on mount and on resize. Without the resize
    # handler they would keep describing a strip that stopped scrolling.
    # Six cards at 170px overflow the container at every real width, so the
    # "the strip fits, therefore no controls" branch is unreachable with the
    # shipped data. Narrowing the cards is what makes it reachable -- and it
    # exercises the resize handler at the same time, since the arrows can only
    # go away if measureRail re-runs.
    page.set_viewport_size(DESKTOP)
    page.wait_for_function(
        "() => { const t = document.querySelector('.related-track');"
        " return t && t.clientWidth > 800; }"
    )
    assert_rail_controls(page, expect_overflow=True)
    # min-width: 0 is load-bearing: a flex item's default min-width is auto, so
    # without it the card text holds the track open at its content width and the
    # strip never fits. The same is true of the shipped 170px track -- it is a
    # floor, not a width, and the container can be narrower.
    page.add_style_tag(
        content=".related li { flex: 0 0 100px; min-width: 0; }"
    )
    # A style change fires neither resize nor scroll, and the rail only
    # re-measures on those two. Nudging the viewport is what exercises the
    # handler this assertion exists for.
    page.set_viewport_size({"width": DESKTOP["width"] - 40, "height": DESKTOP["height"]})
    page.wait_for_function(
        "() => document.querySelectorAll('.related-nav').length === 0"
    )
    assert_rail_controls(page, expect_overflow=False)
    # The one-line check above passes at the shipped 170px card even with
    # flex-wrap: wrap, because the two chips do fit there -- it guards the
    # rendering, not the historical bug. Re-check it on the narrowed cards,
    # where wrapping is what the old CSS would do.
    assert_ratings_on_one_line(page)


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
    h1 = page.locator("h1.film-title")
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
                test_nav_tier,
                test_nojs_cloak,
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