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
     scroller with a 156px track below lg (390 and 576 checked) and a
     six-column grid from 1024 up (1024 and 1280 checked), with no
     document-level horizontal overflow at any of them; the meta row on the
     poster's scrim, one line, never overflowing its box
  3a. featured poster: 2:3 at 320/375/576/768/1024/1280/1440, and its box
     measured against the `sizes` slot index.html declares -- the 156px below
     lg exactly, and never wider than 194px from lg up. The `height`
     attribute in the markup is a definite height, which is why it beats
     `aspect-ratio` and the card measured 1.009 wide at 1440
  3b. header controls: one shared height across .tool-buttons at every tier, the
     icon buttons one shared width, a .lang wider than a square tap target
     because it is the only one carrying a label, and the xs burger at or above
     44px

  --only <scenario> runs a single named scenario. Proving a guard is live means
  breaking the code and re-reading the verdict; a full sweep per mutation turns
  that into an unusable ritual.
  3c. nav lands clear: clicking a nav anchor moves the marker to that section
     on the click rather than at the end of the smooth scroll, and the section
     comes to rest below the sticky header, at 320 through 1280
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
     label and the related titles; the header carries the site name and no h1,
     and the rail's arrow labels follow the language
 11. mobile layout at 390px: exactly one h1, inside .film-info, 6 related cards
     in one horizontal row, the rail's arrows and dots walked to the end and
     back, the ratings asserted on one line, 2:3 poster boxes reported with the
     area they discard, the selected file verified against disk, related slugs
     drawn from FILM_PAGE.related, and a related-card srcset that offers the
     whole ladder with each candidate's own width. At desktop width the rail is
     checked too, and then with narrowed cards -- the only way to reach the
     "the strip fits, so no controls" branch, which the shipped six cards
     overflow past at every width
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
from lib import FEATURED_BOX_DESKTOP, FEATURED_BOX_MOBILE, POSTER_VARIANT_WIDTHS, ROOT, variant_name, webp_size  # noqa: E402

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

# One row, and one chip baseline, read off the live layout. `chipSpread` is
# UNROUNDED on purpose: the six-column grid deals fractional tracks, so the
# cards' border boxes land on different sub-pixel phases, and rounding that
# 0.03px phase to whole pixels invents a 1px stagger that is not on the page.
RELATED_ROW_PROBE = """() => {
  const cards = [...document.querySelectorAll('.related li')];
  const tops = [...new Set(cards.map(c => Math.round(c.getBoundingClientRect().y)))];
  const firstRow = cards.filter(c => Math.round(c.getBoundingClientRect().y) === tops[0]);
  const chipY = firstRow
    .map(c => c.querySelector('.rc-rating.kp'))
    .filter(Boolean)
    .map(el => el.getBoundingClientRect().y);
  const spread = chipY.length
    ? Math.round((Math.max(...chipY) - Math.min(...chipY)) * 1000) / 1000
    : -1;
  return {
    rows: tops.length,
    inRow: firstRow.length,
    cards: cards.length,
    chipSpread: spread,
    cardW: Math.round(firstRow[0].getBoundingClientRect().width * 100) / 100,
  };
}"""

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


def assert_rows_align_to_the_title(page):
    """A one-line column must not read as belonging to the alt title.

    The title cell carries two lines -- the title and the alt title in the other
    language -- while genre, year and ratings carry one each. With the two-line
    block top-aligned, a one-line cell lands between them and closer to the alt:
    measured 17.6px below the primary title and only 2.6px above the alt, so the
    row read as "title, then the numbers belong to the second line". Centring the
    block puts the one-line cells at the midpoint, 10.2px from each.

    The invariant is deliberately the RELATION, not a fixed offset: the partner
    chose a centred block over a top-aligned one (which would put the numbers on
    the title line exactly, at 0.5px), so this asserts the defect is gone rather
    than that a number I proposed is reproduced.

    Read through Range rects, not through the cells' own boxes: a td is stretched
    to the whole row, so its bounding box says nothing about where its text is.
    """
    rows = page.evaluate(
        """() => {
          const textRect = (el) => {
            const r = document.createRange();
            r.selectNodeContents(el);
            const b = r.getBoundingClientRect();
            return { center: b.top + b.height / 2 };
          };
          return [...document.querySelectorAll('#movies tbody tr')]
            .filter(row => row.querySelector('.title-primary') && row.querySelector('.alt-title'))
            .slice(0, 6)
            .map(row => {
              const poster = row.querySelector('.poster-wrap');
              const pb = poster ? poster.getBoundingClientRect() : null;
              return {
                primary: textRect(row.querySelector('.title-primary')).center,
                alt: textRect(row.querySelector('.alt-title')).center,
                genre: textRect(row.querySelector('.genre')).center,
                year: textRect(row.querySelector('.year')).center,
                kp: textRect(row.querySelector('.num')).center,
                poster: pb ? pb.top + pb.height / 2 : null,
              };
            });
        }"""
    )
    assert rows, "expected catalog rows carrying both a title and an alt title"
    for row in rows:
        to_primary = abs(row["genre"] - row["primary"])
        to_alt = abs(row["genre"] - row["alt"])
        assert to_primary <= to_alt + 6, (
            f"the genre column sits {to_primary:.1f}px from the title but only"
            f" {to_alt:.1f}px from the alt title, so the row reads as if the"
            f" numbers belonged to the alt title"
        )
        for col in ("year", "kp"):
            assert abs(row[col] - row["genre"]) <= 2, (
                f"the {col} column is {row[col] - row['genre']:+.1f}px off the"
                f" genre column; they share a line"
            )
        if row["poster"] is not None:
            midpoint = (row["primary"] + row["alt"]) / 2
            assert abs(row["poster"] - midpoint) <= 3, (
                f"the poster icon sits {row['poster'] - midpoint:+.1f}px off the"
                f" centre of the two title lines, so the title block is not centred"
            )


def test_main_filter(page, base):
    page.goto(base + "index.html", wait_until="domcontentloaded")
    assert_rows_align_to_the_title(page)
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
    """Below lg the block is a rail, from lg up it is a six-column grid.

    `.related` also switches at 1024px, but the two are NOT the same shape of
    tier and the arithmetic is not the same. This block's card is 156px below lg
    and a grid FRACTION above it, so the card grows with the container -- 194px
    at 1280 against 156 on the phone. The related card instead has a px width on
    both sides: 160px, capped above by `minmax(0, 160px)` rather than `1fr`, and
    below lg it is a scroller because six 160px cards do not fit below 1024.
    Both land on the same 1024 edge because six cards of a readable size is the
    same arithmetic, but the card size does not grow above it on the film pages,
    and `test_related_one_row_and_level_chips` is what holds that.

    The one place this test differs from a plain tier check is that it also
    reads the RENDERED card width, because the track is 156px below lg and a grid
    FRACTION above it -- so the lg side of the `sizes` slot in index.html has no
    declaration in the stylesheet to be compared against, and this measurement is
    the only witness it has.
    """
    for width, tier in ((390, "rail"), (576, "rail"), (1024, "grid"), (1280, "grid")):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(base + "index.html", wait_until="domcontentloaded")
        grid = page.locator(".featured-grid")
        expect(page.locator(".featured-card")).to_have_count(6)
        hrefs = page.locator(".featured-card").evaluate_all(
            "els => els.map(el => el.getAttribute('href'))"
        )
        assert len(set(hrefs)) == 6, f"@{width}: featured cards must be 6 distinct films: {hrefs}"
        expect(page.locator(".featured-card img")).to_have_count(6)
        rows = page.locator(".featured-grid > li").evaluate_all(
            "els => [...new Set(els.map(el => Math.round(el.getBoundingClientRect().top)))]"
        )
        assert len(rows) == 1, f"@{width}: the featured block must be one horizontal row, card tops {rows}"

        if tier == "rail":
            expect(grid).to_have_css("display", "flex")
            expect(grid).to_have_css("overflow-x", "auto")
            expect(grid).to_have_css("scroll-snap-type", "x mandatory")
            snap = page.locator(".featured-grid > li").evaluate_all(
                "els => els.every(el => getComputedStyle(el).scrollSnapAlign === 'start')"
            )
            assert snap, f"@{width}: every rail card must snap to the start of the track"
        else:
            expect(grid).to_have_css("overflow-x", "visible")
            expect(grid).to_have_css("scroll-snap-type", "none")
            cols = grid.evaluate(
                "el => getComputedStyle(el).gridTemplateColumns.split(' ').length")
            assert cols == 6, f"@{width}: lg tier must be a 6-column grid, got {cols}"

        # The meta line lives on the scrim over the poster now, so the guard is
        # no longer a line clamp. `scrollWidth <= clientWidth` would be the wrong
        # test here: a label that ellipsizes is SUPPOSED to report a scrollWidth
        # past its clientWidth, so that assertion would only ever pass while
        # nothing is truncated. The invariant that actually matters is the one
        # way round -- anything clipped must be marked as clipped, and nothing
        # may spill out of the scrim it sits on.
        assert page.locator(".featured-card-meta").evaluate_all(
            "els => els.every(el => getComputedStyle(el).fontSize === '12px'"
            " && el.scrollWidth <= el.clientWidth)"
        ), f"@{width}: the featured meta line must be 12px and fit the scrim"
        for part in (".featured-card-year", ".featured-card-genre"):
            assert page.locator(part).evaluate_all(
                "els => els.every(el => el.scrollWidth <= el.clientWidth"
                " || getComputedStyle(el).textOverflow === 'ellipsis')"
            ), (f"@{width}: {part} is clipped without an ellipsis, so the reader loses "
                f"the rest of the label with nothing marking that it was cut")
        assert page.locator(".featured-card-overlay").evaluate_all(
            "els => els.every(el => el.scrollWidth <= el.clientWidth)"
        ), f"@{width}: the scrim's contents overflow it"
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        ), f"@{width}: the featured block overflows the document horizontally"

        # The poster, the scrim and the chips must sit on the same line in every
        # card of a row, whatever the title does -- see `.featured-card-media`'s
        # comment. The scrim is anchored to `.featured-card-media`'s bottom, so
        # the thing to measure is the MEDIA box's spread, not the poster's: the
        # image is width x 3/2 in every card and proved equal (0.1px) while the
        # defect was live, which is why a poster-box assertion stays green
        # through it.
        #
        # `pickFeatured` is random, and that is exactly what makes a SAMPLE
        # useless here. 37 of 155 titles wrap to two lines at 1280 and 65 at
        # 1024, so a row of six frequently holds none of them, every spread
        # reads 0, and the assertion passes having measured nothing. So the
        # condition is FORCED rather than hoped for: a title that measurably
        # wraps at this column width goes into card 1, the row is measured, and
        # the original text is put back.
        #
        # `titleTop` and `gap` are asserted as well, and they are what pins
        # `flex: none` rather than a `justify-content`: the media out of the flex
        # flow puts the copy's TOP on one line, so the gap between poster and
        # title is 0 in every card. `justify-content: space-between` was
        # measured and rejected -- it levels the copy's bottom instead and gives
        # this gap an 18.2px spread of its own.
        forced = page.evaluate(
            """() => {
              const cards = [...document.querySelectorAll('.featured-card')];
              if (!cards.length) return { ok: false, why: 'no cards' };
              const first = cards[0].querySelector('.featured-card-title');
              const copy = cards[0].querySelector('.featured-card-copy');
              const cs = getComputedStyle(first);
              const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.3;
              const w = copy.getBoundingClientRect().width;
              const lines = (el, text) => {
                el.textContent = text;
                return Math.max(1, Math.round(el.getBoundingClientRect().height / lh));
              };
              // The probe is a REAL `.featured-card-title` at the real width, so
              // the shipped cascade decides its wrapping rather than a
              // reconstruction of four properties, which is what made an earlier
              // version of this report all 155 titles as two lines.
              const host = document.createElement('span');
              host.className = 'featured-card-copy';
              host.style.cssText = 'display:block;position:absolute;left:-9999px;'
                + 'width:' + w + 'px;';
              const probe = document.createElement('span');
              probe.className = 'featured-card-title';
              host.appendChild(probe);
              document.body.appendChild(host);
              let chosen = null;
              for (const item of (window.CATALOG || [])) {
                if (lines(probe, item.titleRu) >= 2) { chosen = item.titleRu; break; }
              }
              host.remove();
              if (!chosen) return { ok: false, why: 'no title wraps at ' + w + 'px' };
              const was = first.textContent;
              first.textContent = chosen;
              const got = Math.round(first.getBoundingClientRect().height / lh);
              const spread = (sel, edge) => {
                const v = [...document.querySelectorAll(sel)]
                  .map((e) => e.getBoundingClientRect()[edge]);
                return v.length ? Math.max(...v) - Math.min(...v) : 0;
              };
              const gap = (() => {
                const v = cards.map((c) => {
                  const img = c.querySelector('.featured-card-media img');
                  const cp = c.querySelector('.featured-card-copy');
                  if (!img || !cp) return null;
                  return cp.getBoundingClientRect().top
                       - img.getBoundingClientRect().bottom;
                }).filter((x) => x !== null);
                return v.length ? Math.max(...v) - Math.min(...v) : 0;
              })();
              const out = {
                ok: got >= 2, title: chosen, lines: got,
                media: spread('.featured-card-media', 'height'),
                overlay: spread('.featured-card-overlay', 'top'),
                chip: spread('.rating-chip', 'bottom'),
                titleTop: spread('.featured-card-title', 'top'),
                gap: gap,
              };
              first.textContent = was;
              return out;
            }""")
        assert forced["ok"], (
            f"@{width}: could not put a two-line title into the row to measure against "
            f"({forced.get('why', 'the forced title did not wrap')}). This check is "
            f"about the two-line case and `pickFeatured` is random, so the row will "
            f"not supply one on its own"
        )
        for key, label in (("media", "the .featured-card-media box"),
                           ("overlay", "the poster scrim"),
                           ("chip", "the rating chips"),
                           ("titleTop", "the top of the featured titles"),
                           ("gap", "the gap between poster and title")):
            assert forced[key] < 0.5, (
                f"@{width}: {label} differs by {forced[key]:.2f}px across the row with a "
                f"two-line title forced into card 1 (media {forced['media']:.2f}, scrim "
                f"{forced['overlay']:.2f}, chips {forced['chip']:.2f}, title top "
                f"{forced['titleTop']:.2f}, gap {forced['gap']:.2f}). "
                f"`.featured-card-media` must be `flex: none`: at `flex: 1` it absorbs "
                f"whatever the copy block does not use, so a two-line title makes the "
                f"media box 18.2px shorter and everything anchored to its bottom rides "
                f"with it. Do NOT reach for `justify-content: space-between` instead -- "
                f"it was measured and gives this gap an 18.2px spread of its own, and "
                f"shrinking the font or clamping the title to one line would mask the "
                f"defect rather than fix it"
            )


def test_featured_poster_shape(page, base):
    """The featured poster must render 2:3 at EVERY tier, and its box must be the
    one index.html's `sizes` describes.

    `aspect-ratio` only fills an automatic dimension, so a presentational
    `height` attribute on the <img> silently wins and the rule below it becomes
    dead. That is how a 2:3 card shipped rendering 0.60 wide at sm, 0.76 at lg
    and wider than square at xl while every other guard stayed green.

    The second half is the check the stylesheet cannot make. The 156px track
    below lg IS a declaration and verify.py reads it, but the lg box is one
    track of `repeat(6, minmax(0, 1fr))` -- arithmetic over the container, not a
    number anyone wrote. So the direction the slot has to be right in is
    asserted here: the rendered box is never WIDER than the declared slot (a
    wider slot only costs bytes) and below lg it is exactly it.
    """
    slot_m, slot_d = FEATURED_BOX_MOBILE, FEATURED_BOX_DESKTOP
    for width in (320, 375, 576, 768, 1023, 1024, 1280, 1440, 1600, 1920):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(base + "index.html", wait_until="domcontentloaded")
        expect(page.locator(".featured-card img").first).to_be_visible()
        boxes = page.locator(".featured-card-media img").evaluate_all(
            "els => els.map(el => { const r = el.getBoundingClientRect();"
            " return [Math.round(r.width * 100) / 100, Math.round(r.height * 100) / 100]; })"
        )
        off = [b for b in boxes if abs(b[0] / b[1] - 2 / 3) > 0.01]
        assert not off, f"@{width}: featured poster must be 2:3, got {off}"
        widest = max(b[0] for b in boxes)
        slot = slot_d if width >= 1024 else slot_m
        assert widest <= slot + 0.5, (
            f"@{width}: the rendered poster is {widest}px wide but index.html declares a "
            f"{slot}px slot -- a slot narrower than its box makes the browser fetch a "
            f"source smaller than the box renders and scale it up into a blur, and the "
            f"stylesheet cannot see it because the lg box is a grid fraction"
        )
        if width < 1024:
            assert abs(widest - slot_m) <= 0.5, (
                f"@{width}: below lg the card is a flex item with a {slot_m}px basis, so "
                f"the rendered poster must be exactly that, got {widest}px"
            )


def test_header_controls(page, base):
    """Header controls: one shared size, and a label that fits.

    `.tool-buttons button` used to carry `width`/`height` at (0,1,1), which beat
    every component rule at (0,1,0) -- so the class meant to define the row did
    nothing, and the xs tier's `height: var(--tap)` could not reach the burger
    because Task 9 had raised it to (0,2,0).

    Widths are asserted equal for the icon buttons and separately for `.lang`:
    the human partner's requirement is one row of identical controls with the
    language toggle allowed to be wider, because it is the only one carrying a
    label. Asserting "all equal" would forbid the thing that makes the label
    fit, and asserting only "lang is wider" would let the other four drift apart.
    """
    for width in (320, 375, 575, 576, 768, 1280):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(base + "index.html", wait_until="domcontentloaded")
        # `> *` and not `button`: the row now holds an anchor as well as buttons
        # (the channel link), and a `button` selector would silently exclude it --
        # so a control added as anything other than a <button> would escape the
        # "one shared size" rule without anything failing.
        boxes = page.locator(".tool-buttons > *").evaluate_all(
            "els => els.filter(el => el.offsetParent !== null)"
            ".map(el => { const r = el.getBoundingClientRect();"
            " return { cls: el.className, w: Math.round(r.width),"
            " h: Math.round(r.height) }; })"
        )
        assert boxes, f"@{width}: no visible tool-buttons"
        heights = {b["h"] for b in boxes}
        assert len(heights) == 1, f"@{width}: tool-buttons heights differ: {boxes}"
        lang = next(b for b in boxes if "lang" in b["cls"])
        icons = [b for b in boxes if "lang" not in b["cls"]]
        icon_widths = {b["w"] for b in icons}
        assert len(icon_widths) == 1, (
            f"@{width}: the icon buttons are not one size: {sorted(icon_widths)} "
            f"({icons})"
        )
        assert lang["w"] > 44, f"@{width}: .lang must be wider than a square target, got {lang['w']}"
        for b in icons:
            if "menu-toggle" in b["cls"] and width <= 575:
                assert b["w"] >= 44 and b["h"] >= 44, (
                    f"@{width}: the xs burger is below the 44px floor: {b}"
                )


COLOUR_READ = """el => {
  const parse = (s) => {
    const m = s.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    return m[1].split(',').map(x => parseFloat(x)).slice(0, 3);
  };
  const lum = (c) => {
    const a = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92
      : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
  };
  const ratio = (a, b) => {
    const la = lum(a), lb = lum(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };
  // Walk up for the label's own painted background, and read `body` separately:
  // `body` carries a 1px dot grid, so it is a DIFFERENT colour from a flat --bg
  // and the worse of the two is what a reader can actually land on. Reporting
  // only one of them is how a colour that fails still measures as passing.
  // The mark is a SIBLING of the anchor, not a child (the partner's third
  // ruling), so it is reached through the row. Reading it off the anchor finds
  // nothing, and a null here would silently become a skipped measurement rather
  // than a failure -- so the row is required and a missing mark is returned as
  // such, not as `null` to be compared against.
  const row = el.closest('.tg-row');
  const label = el.querySelector('span') || el;
  const glyph = row ? row.querySelector('svg') : null;
  let node = label, own = null;
  while (node && node !== document.documentElement) {
    const raw = getComputedStyle(node).backgroundColor;
    const c = parse(raw);
    if (c && !/rgba\\([^)]*,\\s*0\\s*\\)/.test(raw)) { own = c; break; }
    node = node.parentElement;
  }
  const bodyBg = parse(getComputedStyle(document.body).backgroundColor);
  const bgs = [own, bodyBg].filter(Boolean);
  // A missing mark must be loud. getComputedStyle(null) throws, which surfaces as
  // an opaque harness error naming neither the element nor the ruling, so it is
  // turned into a value the assertions below can report in their own words.
  if (!row) return { row: false, theme: '?', fill: 'no .tg-row' };
  if (!glyph) return { row: true, theme: '?', fill: 'no mark in the row' };
  const fillRaw = getComputedStyle(glyph).fill;
  const fill = parse(fillRaw);
  const labelFg = parse(getComputedStyle(label).color);
  return {
    row: true,
    theme: document.documentElement.classList.contains('light') ? 'light' : 'dark',
    fill: fillRaw,
    // the label is the site's own link colour and the glyph is the brand one, so
    // they are two different colours against the same backgrounds and are held to
    // two different floors: 4.5:1 for text, 3:1 for non-text. They were one
    // number only while both were the same colour.
    label: Math.min(...bgs.map(b => ratio(labelFg, b))),
    glyph: fill ? Math.min(...bgs.map(b => ratio(fill, b))) : null,
    token: getComputedStyle(document.documentElement)
      .getPropertyValue('--telegram').trim(),
  };
}"""


def test_channel_link(page, base):
    """The header's Telegram link must be on EVERY page type, in BOTH themes.

    The header is hand-maintained six times over and the film pages are generated
    from `FILM_TEMPLATE`, so a page type that lost the anchor would be a page with
    no channel link anywhere and nothing saying so -- the footer link is
    unchanged, so the page still looks complete. `verify.py` checks the markup of
    every copy; this checks that they RENDER, which is the half a static read
    cannot see.

    Placement is asserted, not just presence, because the placement is what the
    measurement decided. It was FIRST built as a sixth control in `.tool-buttons`,
    which is where the human partner's "all controls equal" rule puts a new
    control by default -- and six controls do not fit at 375: 296px of control
    plus five 8px gaps is 336px against 321px available, so the row wrapped and
    the header grew 52px at the two commonest phone widths. It lives under the
    brand subtitle instead, which costs the row nothing.

    The colour is asserted, not just present, for the reason that made this
    feature go wrong once already: the glyph painted BLACK in both themes because
    the share sprite declares no fill and this link does not inherit
    `.share-ico`'s, and the partner read that black blob wearing a Telegram logo
    as a request for a colour. A screenshot caught it once; this catches it
    always. The 4.5:1 floor is the brand blue's own weak point -- it measures
    7.15:1 on the dark header and 2.56:1 on the light one -- so both themes have
    to be visited or the assertion only ever checks the half that already passes.
    """
    PAGES = (
        ("index", "index.html"),
        ("film", "films/tt0133093-the-matrix/index.html"),
        ("about", "about.html"),
        ("404", "404.html"),
        ("privacy", "privacy.html"),
    )
    root = Path(__file__).resolve().parents[1]

    def serve_404(route):
        # 404.html carries <base href="https://akhomlyuk.github.io/IT_movies/">,
        # which is CORRECT for GitHub Pages -- it is what makes relative assets
        # resolve for any missing path -- and which makes a locally served 404
        # resolve every asset against the deployed domain instead. The
        # stylesheet then throws SecurityError on cssRules, nothing is styled,
        # and the link this test is here to check renders as unstyled text.
        #
        # The fix is to fulfil the route with the base rewritten to THIS run's
        # origin; nothing on disk changes. `route.continue_(url=...)` is NOT the
        # fix and looks like it: it re-issues the request against the URL passed
        # to it, i.e. against the real deployed origin, so the stylesheet still
        # comes from production and the test measures production.
        html = (root / "404.html").read_text(encoding="utf-8")
        html = html.replace(
            '<base href="https://akhomlyuk.github.io/IT_movies/">',
            '<base href="%s/">' % base)
        route.fulfill(status=200, content_type="text/html; charset=utf-8",
                      body=html)

    four_oh_four = re.compile(r"404\.html$")
    for theme in ("dark", "light"):
        for width in (320, 575, 768, 1280):
            for name, rel in PAGES:
                page.set_viewport_size({"width": width, "height": 900})
                page.add_init_script(
                    "localStorage.setItem('it-movies-theme', '%s');" % theme)
                if name == "404":
                    page.route(four_oh_four, serve_404)
                page.goto(base + rel, wait_until="domcontentloaded")
                page.wait_for_selector(".tg-link", timeout=5000)
                if name == "404":
                    page.unroute(four_oh_four)

                link = page.locator(".tg-link")
                assert link.get_attribute("href") == "https://t.me/wh_lab", (
                    f"{theme} @{width} {name}: the header link points at "
                    f"{link.get_attribute('href')!r}, not the channel"
                )
                assert link.get_attribute("target") == "_blank", (
                    f"{theme} @{width} {name}: the header link must open in a new tab"
                )
                # Placement: under the subtitle, out of the control row.
                assert link.evaluate("el => !!el.closest('.brand-text')"), (
                    f"{theme} @{width} {name}: the header link is not inside "
                    f".brand-text. It was rejected as a sixth control in "
                    f".tool-buttons because six controls do not fit at 375"
                )
                assert link.evaluate("el => !el.closest('.tool-buttons')"), (
                    f"{theme} @{width} {name}: the header link is back inside the "
                    f"control row"
                )
                # The mark is a SIBLING of the anchor, and that is the partner's
                # third ruling. It used to be a child, which put a border-bottom
                # under the glyph as well as under the label -- the border on an
                # inline-flex anchor spans the whole box. `previousElementSibling`
                # being the row rather than a <p> is exactly the shape that
                # settling wrong looks like, so both facts are asserted: the row
                # is a sibling of the subtitle paragraph, and the anchor's own
                # previous sibling is the MARK, not the row.
                assert link.evaluate(
                    "el => { const row = el.closest('.tg-row'); return !!row "
                    "&& !!row.previousElementSibling "
                    "&& row.previousElementSibling.tagName === 'P'; }"), (
                    f"{theme} @{width} {name}: the channel row must sit directly "
                    f"under the brand's subtitle paragraph"
                )
                assert link.evaluate(
                    "el => { const p = el.previousElementSibling; "
                    "return !!p && p.tagName === 'svg' "
                    "&& p.classList.contains('tg-mark'); }"), (
                    f"{theme} @{width} {name}: the mark must be the anchor's "
                    f"immediate previous sibling, not a child. Inside the <a> the "
                    f"border-bottom underlined the glyph as well as the label, and "
                    f"the partner ruled `you put the icon in the href too`"
                )
                assert link.evaluate("el => !el.querySelector('svg')"), (
                    f"{theme} @{width} {name}: the glyph is back inside the "
                    f"anchor. It ships as a sibling"
                )
                # A visible label, not an icon-only control.
                assert link.evaluate(
                    "el => el.textContent.trim() === 'Whitehat Lab'"), (
                    f"{theme} @{width} {name}: the header link's visible text is "
                    f"{link.text_content()!r}, expected 'Whitehat Lab'"
                )
                # The control row must be back to the widths it had before the
                # link existed: 40px squares, 76px for the labelled toggle.
                row = page.locator(".tool-buttons")
                if row.count():
                    widest = row.evaluate(
                        "el => Math.max(...[...el.children]"
                        ".filter(c => c.offsetParent !== null)"
                        ".map(c => c.getBoundingClientRect().width))")
                    assert widest <= 76.5, (
                        f"{theme} @{width} {name}: a control in the row is "
                        f"{widest:.1f}px wide, past the 76px language toggle. If the "
                        f"channel link went back into the row it would be a sixth "
                        f"control and the row would wrap at 375"
                    )
                # The glyph must resolve to something with size.
                painted = link.evaluate(
                    "el => { const row = el.closest('.tg-row');"
                    " if (!row) return 'no .tg-row';"
                    " const u = row.querySelector('use');"
                    " if (!u) return 'no <use>';"
                    " const r = u.getBoundingClientRect();"
                    " return r.width > 0 && r.height > 0 ? 'ok' : 'zero-sized'; }"
                )
                assert painted == "ok", (
                    f"{theme} @{width} {name}: the Telegram mark is not rendering "
                    f"({painted}). The sprite reference resolves to nothing, which "
                    f"looks like an empty box rather than an error. The mark is a "
                    f"sibling of the anchor, so a <use> looked up on the anchor "
                    f"itself finds nothing and reports the same thing"
                )
                colour = link.evaluate(COLOUR_READ)
                # `row` first, so a structural miss is reported as itself rather
                # than as a downstream `None >= 4.5` TypeError.
                assert colour["row"] and str(colour["fill"]).startswith("rgb"), (
                    f"{theme} @{width} {name}: the channel row or its mark is "
                    f"missing ({colour['fill']!r}); cannot measure a colour on a "
                    f"mark that is not there"
                )
                assert colour["fill"] != "rgb(0, 0, 0)", (
                    f"{theme} @{width} {name}: the glyph paints {colour['fill']}. "
                    f"The share sprite declares no fill on any symbol and every "
                    f"consumer inherits `fill: currentColor` from `.share-ico`, "
                    f"which this link is not a member of -- without the declaration "
                    f"on `.tg-link svg` the path falls back to the SVG default and "
                    f"paints black in BOTH themes. It shipped that way once and read "
                    f"as a colour problem rather than a missing rule"
                )
                assert colour["fill"] != "rgb(94, 106, 210)", (
                    f"{theme} @{width} {name}: the glyph paints {colour['fill']}, "
                    f"which is --accent. That is what `fill: currentColor` produces "
                    f"here: on the <svg> element currentColor resolves to THAT "
                    f"element's own colour, and `svg:not(.heart)` sets it to "
                    f"--accent. The token has to be named outright"
                )
                assert colour["label"] >= 4.5, (
                    f"{theme} @{width} {name}: the label is at "
                    f"{colour['label']:.2f}:1 against its background, under the "
                    f"4.5:1 text floor. The label is the site's own link colour, so "
                    f"this is about inheriting the right one, not about "
                    f"--telegram -- whose brand value measures 2.56:1 in light and "
                    f"is why the token is a pair"
                )
                assert colour["glyph"] is not None and colour["glyph"] >= 3.0, (
                    f"{theme} @{width} {name}: the glyph is at "
                    f"{colour['glyph']:.2f}:1, under the 3:1 non-text floor. The "
                    f"brand hex alone measures 2.56:1 on the light header, which is "
                    f"why --telegram is a darker shade of the same hue there and the "
                    f"brand value in dark"
                )


CLICK_NAV = """
  async (id) => {
    const visible = () => [...document.querySelectorAll('.nav a')]
      .filter(a => a.offsetParent !== null);
    // Settle BEFORE clicking, not only after. The page sets
    // `scroll-behavior: smooth`, so a scroll still in flight swallows the next
    // fragment navigation: measured at 320, a click issued while the harness's own
    // reset was still animating left scrollY at exactly 0 with the target 1183px
    // below the fold, which reads exactly like a dead anchor. The page is fine --
    // every click scrolls when nothing else is animating, traced frame by frame
    // (0 -> 6 -> 25 -> 57 -> 102 over ~750ms) -- so the harness waits for the
    // stillness it needs instead of reporting a defect no reader can see.
    const still = async (cap) => {
      let same = 0, lastY = -1;
      const t = performance.now();
      while (performance.now() - t < cap) {
        await new Promise(r => requestAnimationFrame(r));
        const y = Math.round(window.scrollY);
        same = y === lastY ? same + 1 : 0;
        lastY = y;
        if (same >= 3) return true;
      }
      return false;
    };
    await still(1500);
    const burger = document.querySelector('.tool-buttons .menu-toggle');
    const opened = burger && getComputedStyle(burger).display !== 'none'
      && visible().length === 0;
    if (opened) { burger.click(); await new Promise(r => setTimeout(r, 250)); }
    const link = visible().find(a => a.getAttribute('href') === '#' + id);
    if (!link) return { ok: false, why: 'no visible anchor for #' + id };
    link.click();
    // And settle AFTER clicking, so the whole travel is measured rather than a
    // fixed prefix of it: a 300ms window is a 300ms sample of a ~750ms event,
    // which is the mistake the previous version of this test made.
    const t0 = performance.now();
    await still(3000);
    const header = document.querySelector('header.top').getBoundingClientRect();
    const target = document.getElementById(id).getBoundingClientRect();
    // Read BOTH nav copies, not only the visible ones. The anchors are rendered
    // twice on purpose -- the inline row and the xs dialog -- and below xs the
    // inline row is display:none while the dialog closes on the click, so a
    // visible-only read would find nothing and report a clean sheet on a page
    // that still sets the attribute.
    const marked = [...document.querySelectorAll('.nav a')]
      .filter(a => a.getAttribute('aria-current') !== null)
      .map(a => a.getAttribute('href') + '=' + a.getAttribute('aria-current'));
    const out = { ok: true, marked, readMs: Math.round(performance.now() - t0),
                  opened: !!opened, headerTop: header.top,
                  headerBottom: header.bottom, sectionTop: target.top,
                  scrollY: Math.round(window.scrollY) };
    if (opened) {
      const close = document.querySelector('.nav-dialog-close');
      if (close) close.click();
    }
    return out;
  }
"""


def test_nav_lands_at_top(page, base):
    """A nav click lands its target at the top of the viewport, and nothing marks
    the current section.

    Both halves are the partner's 2026-09-30 ruling, and both are here as
    regressions rather than as descriptions. The header is no longer sticky, so a
    nav target has nothing to hide under and must land AT the top: the
    `scroll-padding-top: var(--header-offset)` and the measured write that used to
    push it down are gone with it, and a surviving offset shows up here as a
    `sectionTop` far from zero. And no anchor may carry `aria-current` at all --
    the marker that attribute fed was three bugs deep (a 20-30% band observer that
    overwrote the click at 214ms, then a click lock to defeat that, then a latch
    that held #movies after scrolling back to the top) and the partner's call was
    that it is not worth a mechanism of that shape.

    The header assertion is the direct one for the sticky removal and is stated
    as a relation, not a number: a sticky header's bottom would sit at or below
    the target's top, because the target would be underneath it.
    """
    for width in (320, 360, 390, 575, 576, 767, 768, 1024, 1280):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(base + "index.html", wait_until="domcontentloaded")
        page.wait_for_selector(".featured-card")
        for target in ("series", "movies", "documentaries"):
            d = page.evaluate(CLICK_NAV, target)
            assert d["ok"], f"@{width}: {d.get('why')}"
            assert d["marked"] == [], (
                f"@{width}: after clicking #{target} these nav anchors still carry "
                f"aria-current: {d['marked']}. The section marker was removed by the "
                f"partner on 2026-09-30; nothing may set the attribute again"
            )
            assert abs(d["sectionTop"]) <= 2, (
                f"@{width}: #{target} landed at top {d['sectionTop']:.1f} with "
                f"scrollY {d['scrollY']} -- with no sticky header a nav target lands "
                f"at the top of the viewport, so a non-zero top means something is "
                f"still offsetting it (scroll-padding-top, or a .top that is "
                f"sticky again)"
            )
            assert d["headerBottom"] < d["sectionTop"], (
                f"@{width}: the header's bottom is {d['headerBottom']:.1f} and "
                f"#{target}'s top is {d['sectionTop']:.1f} -- the header is still "
                f"covering the target, so it is still sticky"
            )
            # Instant, not smooth: the page sets scroll-behavior: smooth, so a
            # smooth reset would still be animating when the next click lands and
            # that click would be swallowed (see CLICK_NAV's pre-click settle).
            page.evaluate("() => window.scrollTo({top: 0, behavior: 'instant'})")

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
    """The rail's dots must exist exactly when the strip scrolls.

    Asserted by measurement, not by markup: only a browser can say whether the
    track overflows, and dots for a strip that cannot be paged are worse than no
    dots. There are no arrow buttons -- the strip is dragged with a finger or a
    mouse and paged with the left/right keys, so the dots only jump.
    """
    track = page.locator(".related-track")
    overflows = track.evaluate("el => el.scrollWidth > el.clientWidth + 1")
    if overflows != expect_overflow:
        raise AssertionError(
            f"expected the rail to {'scroll' if expect_overflow else 'fit'} at this"
            f" width, but scrollWidth={track.evaluate('el => el.scrollWidth')}"
            f" clientWidth={track.evaluate('el => el.clientWidth')}"
        )

    # A scrolling strip must hold its cards OFF the scrollbar, and a strip that
    # does not scroll must not reserve room for one. Both halves are the same
    # declaration seen from two sides, and the defect this guards is a
    # specificity one that no stylesheet reading can catch: `ul.related-track`
    # carries both classes, `.related ul { padding: 0 }` is (0,1,1) and a
    # `padding-bottom` on a bare `.related-track` is (0,1,0), so the reset won
    # and the gap was worth 0px -- the cards sat flush against the bar while the
    # stylesheet appeared to declare a padding for exactly that.
    #
    # Asserted on the COMPUTED value, not on the declaration, because the whole
    # point is that a declaration can exist and be dead.
    gap = track.evaluate(
        "el => { const li = el.querySelector('li');"
        " if (!li) return null;"
        " const bar = el.offsetHeight - el.clientHeight;"
        " return Math.round((el.getBoundingClientRect().bottom - bar"
        "   - li.getBoundingClientRect().bottom) * 100) / 100; }"
    )
    if expect_overflow:
        assert gap is not None and gap > 0, (
            f"the strip scrolls but its cards are flush against the scrollbar "
            f"(gap {gap}px). `.related ul` and `.related-track` are the same "
            f"element, so a `padding-bottom` declared on `.related-track` loses "
            f"to the `padding: 0` reset at higher specificity and never applies -- "
            f"put it in the `.related ul` rule instead"
        )
    else:
        assert gap == 0, (
            f"the strip does not scroll but reserves {gap}px for a scrollbar that "
            f"is not there. The grid tier resets `padding-bottom` to 0 on the same "
            f"selector that declares it; a `.related-track` reset at (0,1,0) would "
            f"lose to the (0,1,1) base it is cancelling"
        )

    dots = page.locator(".related-dot")
    assert page.locator(".related-nav").count() == 0, (
        "the strip has no arrow buttons; it is dots, drag and the arrow keys"
    )
    if not expect_overflow:
        expect(dots).to_have_count(0), (
            "a rail that fits must not offer dots for a strip it cannot page"
        )
        return
    assert dots.count() >= 1, "a scrolling rail must offer dots"
    expect(dots.first).to_have_attribute("aria-label", re.compile(r"^.*\s1\s*/\s\d+$"))
    expect(page.locator(".related-dot.is-active")).to_have_count(1)
    # Every dot is reachable and lands somewhere real.
    for i in range(dots.count()):
        dots.nth(i).click()
        page.wait_for_timeout(120)
        expect(page.locator(".related-dot.is-active")).to_have_count(1)
    dots.first.click()
    page.wait_for_function(
        "() => { const el = document.querySelector('.related-track');"
        " return el && el.scrollLeft <= 2; }"
    )
    # The keyboard is the only non-pointer route left, so it has to work.
    track.focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_function(
        "() => { const el = document.querySelector('.related-track');"
        " return el && el.scrollLeft > 2; }"
    )
    page.keyboard.press("ArrowLeft")
    page.wait_for_function(
        "() => { const el = document.querySelector('.related-track');"
        " return el && el.scrollLeft <= 2; }"
    )


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
    # DESKTOP is 1280, so this is the grid tier: no scroll, no dots.
    assert_rail_controls(page, expect_overflow=False)
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
    # The dots are the only visible control on the xs tier, so their labels are
    # the only thing telling a screen reader how many pages the strip has. This
    # is the tier where they exist at all: from lg up it is a grid with no dots.
    expect(page.locator(".related-dot").first).to_have_attribute(
        "aria-label", re.compile(r"^Страница\s1\s*/\s\d+$")
    )
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
    # From md up the related block is a grid, so it does not scroll and carries
    # no dots at all. This is the second, and the stronger, statement of the
    # rule: the first checked it at the xs tier, where the strip really does
    # scroll and needs them.
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


def test_related_one_row_and_level_chips(page, base):
    """The two things the 2026-09-30 related rework promises, swept, not sampled.

    Both are absolute claims, so both are stated as absolutes here:

    * the six cards never occupy more than one row at ANY width, and
    * the rating chips share a baseline across the cards of a row, so they do
      not "dance" when one neighbour's title runs to a second line.

    The width sweep is the point. `test_film_mobile_layout` already asserted one
    row at xs and `test_film_theme` asserted it at 1280, and both were green
    while the 768-1023 band put six cards in FOUR columns -- two rows, two
    orphans, an 807px block. The defect lived entirely between the two tested
    widths. A guard that only samples will keep finding the widths it already
    looked at, so this walks 320..1600 on one page and resizes: the layout is
    pure CSS, so a viewport change reflows it without a reload.

    The chip baseline is measured UNROUNDED and against a half-pixel floor. The
    grid deals fractional tracks, so the six cards' border boxes land on
    different sub-pixel phases, and rounding a 0.03px phase to whole pixels
    fabricates a 1px "stagger" that is not there. A stagger a reader could see
    is at least half a pixel; anything under it is rounding, not alignment.
    """
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(base + FILM_MOBILE_PAGE, wait_until="domcontentloaded")
    page.wait_for_selector(".related li")

    multi_row, dancing = [], []
    worst = (0.0, None)
    for width in range(320, 1601):
        page.set_viewport_size({"width": width, "height": 1000})
        m = page.evaluate(RELATED_ROW_PROBE)
        if m["rows"] != 1:
            multi_row.append((width, m["rows"]))
        if m["chipSpread"] > 0.5:
            dancing.append((width, m["chipSpread"]))
        if m["chipSpread"] > worst[0]:
            worst = (m["chipSpread"], width)

    assert not multi_row, (
        f"the related strip broke into more than one row at {len(multi_row)} widths, "
        f"first at {multi_row[0] if multi_row else None}. Six cards must always be one "
        f"row; where they do not fit the strip scrolls. This is the 768-1023 four-column "
        f"band's defect returning"
    )
    assert not dancing, (
        f"the rating chips are not on a shared baseline at {len(dancing)} widths, "
        f"first at {dancing[0] if dancing else None} -- worst spread {worst[0]:.3f}px at "
        f"@{worst[1]}. `.rc-title` must stay clamped to one line; a two-line title "
        f"pushes its own chips 22px below its neighbour's"
    )
    # The card is one size everywhere, which is what "same at every resolution"
    # means -- and the one place it is allowed to be narrower is the 1024 band,
    # where six columns have to share a 969px track.
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.wait_for_timeout(200)
    wide = page.evaluate(RELATED_ROW_PROBE)
    page.set_viewport_size({"width": 375, "height": 1000})
    page.wait_for_timeout(200)
    narrow = page.evaluate(RELATED_ROW_PROBE)
    assert abs(wide["cardW"] - narrow["cardW"]) < 1.0, (
        f"the related card is not one size: {narrow['cardW']}px at 375 against "
        f"{wide['cardW']}px at 1280. Above lg the grid cap is `minmax(0, 160px)` and "
        f"NOT `1fr` -- a fraction grows the card with the container, which is how the "
        f"desktop cards became 194px against the phone's 160"
    )


def main():
    global RU_SORT_KEY
    RU_SORT_KEY, branch, rejected = resolve_russian_sort_key()
    print(f"genre collation: {branch}")
    for note in rejected:
        print(f"  WARNING: {note}")
    headed = "--headed" in sys.argv
    shots = None
    only = None
    for i, arg in enumerate(sys.argv):
        if arg == "--shots":
            shots = sys.argv[i + 1]
        if arg == "--only":
            only = sys.argv[i + 1]
    httpd, base = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed)
            scenarios = [
                test_main_filter,
                test_genre_filter,
                test_featured_breakpoints,
                test_featured_poster_shape,
                test_header_controls,
                test_channel_link,
                test_nav_lands_at_top,
                test_nav_tier,
                test_nojs_cloak,
                test_about_page,
                test_main_lang,
                test_film_theme,
                test_film_lang,
                test_film_mobile_layout,
                test_related_one_row_and_level_chips,
                test_boot_fallback,
                test_lucky,
                test_poster_modal,
            ]
            if only:
                # Mutation testing needs one scenario per run: proving a guard is
                # live means breaking the code and re-reading its verdict, and a
                # full sweep per mutation turns that into an unusable ritual.
                named = [f for f in scenarios if f.__name__ == only]
                if not named:
                    raise SystemExit(
                        f"--only {only}: no such scenario; pick one of "
                        + ", ".join(f.__name__ for f in scenarios)
                    )
                scenarios = named
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
