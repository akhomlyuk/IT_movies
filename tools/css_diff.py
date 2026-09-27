#!/usr/bin/env python3
"""Computed-style baseline harness for css/style.css.

Stage 2a migrates roughly 200 hardcoded values onto design tokens and then
wraps the sheet in cascade layers. The only acceptable evidence that neither
changed anything is a computed-style diff of every element on the site, before
and after, byte for byte. This harness produces that diff.

What it captures, per (page, width, scheme):

  * one record per element under ``#app``: a stable selector path, the tag,
    the id, the sorted class list, ``getBoundingClientRect()`` in DOCUMENT
    coordinates, and every computed property that differs from the browser's
    initial value for that property
  * a synthetic ``:root`` element carrying the ``html`` computed properties and
    every ``--*`` custom property declared on the root
  * a synthetic ``body`` element carrying the ``document.body`` computed
    properties, which is where the ``document.body`` background lives
  * the ``::before`` / ``::after`` computed style of every element whose
    generated content is not ``none``
  * the scroll offset, the running-animation count and the resolved colour
    scheme, so a non-deterministic capture is visible in the snapshot itself
  * a focus pass: every selector in ``FOCUS_TARGETS`` is read twice, once
    blurred and once focused via ``focus({preventScroll: true})``, storing the
    element's FULL non-initial computed style both times -- not only the outline
    properties, so a focus state that also moves ``background`` or
    ``border-color`` is caught too. The 13 rules in ``css/style.css`` that carry
    an ``outline`` declaration all sit behind ``:focus`` / ``:focus-visible``,
    and an unfocused element resolves ``outline-width: 0px`` and
    ``outline-style: none``, so without this pass every outline in the snapshot
    reads ``none 0px`` and a green compare says nothing about the focus-ring
    migration while appearing to cover it.

The focus pass targets that are not in the DOM as loaded are reached by driving
the page into the state that renders them, the same way ``ui_audit.py`` does:
filling the search box with a non-matching query for ``.reset-filters``, then
clicking a ``.poster-icon`` to open the lightbox for ``.poster-close``. Each
phase opens with a bare ``Shift`` keypress, which sets the keyboard modality
without moving focus or scrolling. That prime is required, not decorative:
Chromium suppresses ``:focus-visible`` on a programmatic focus when the last
interaction was a pointer one, so ``.poster-close`` -- reachable only after a
real click -- does not match without it. Each phase first restores the pinned
scroll offset, because Playwright's ``click()`` auto-scrolls its target into
view. A target that is present but does NOT match ``:focus-visible`` after
focusing is a hard capture error, never a silent pass, because a focus pass that
stopped matching would otherwise go green while observing no ring.

``FOCUS_TARGETS`` is the list of 19 selectors the pass reads. It is built from the
13 rules in ``css/style.css`` that actually carry an ``outline`` declaration --
``.reset-filters``, ``.theme-toggle``/``.lang``, ``.genre-filter``, ``.search``,
``.fav-filter``, ``.lucky``, ``.featured-card``, ``th.sortable .th-sort``,
``.poster-icon``, ``.poster-close``, ``.skip-link``, ``#main`` and
``.related a.rc`` -- plus ``.nav a`` and a few other interactive controls with no
author ring, so the absence of a ring is proved as well as its presence. Each
entry's ``state`` names the phase that can reach the target: ``"default"`` when it
is in the DOM as loaded, otherwise the phase that drives the page into the state
rendering it.

Two things are pruned, both recorded in the snapshot so the exclusion is
auditable rather than silent:

  * a property whose computed value equals the browser's initial value is
    dropped. This is lossless in the strong sense: an authored change makes the
    value differ from the initial value again, so the property reappears.
  * a property that holds one identical value on EVERY element of a record is
    hoisted out of the per-element dicts into ``record.pruned``. The hoisted
    value is compared, so a change that moves every element at once is still
    caught. If a hoisted property stops being uniform the live capture keeps it
    and the comparison reports the asymmetry and exits 1.

Chromium's indexed computed-style list carries longhands only. It never lists
``border-radius``, ``padding``, ``margin``, ``gap`` or ``outline``, even though
the CSSOM getters for them resolve correctly, so ``SHORTHANDS`` below is read
explicitly and pruned against its own initial serialisation. Without it the
snapshot cannot name one of the 32 ``border-radius`` declarations, nor one
spacing shorthand, which is exactly what Stage 2a is about.

``compare`` refuses to compare two snapshots whose ``pages``, ``widths``,
``height``, ``schemes`` or ``pseudo`` settings differ: exit 2, not a diff. With
no explicit flags it adopts the baseline's own settings, so the ordinary
``compare baseline.json`` is never a footgun. The scroll offset is deliberately
NOT in that list, because it changes no record set and each record carries its
own ``scrollY``.

Everything else is captured. What is NOT captured is listed in
``meta.notProbed`` and printed by ``compare``, because a name you do not know
about is worse than a name you do.

Determinism: fonts are force-loaded, every image is forced eager and decoded,
the page is scrolled to a fixed offset with ``behavior: 'instant'`` (the
stylesheet sets ``scroll-behavior: smooth``), two animation frames plus a settle
wait elapse before anything is read, and the capture aborts if a CSS animation
or transition is still running, or if the requested scroll offset is not
reachable. ``html { scrollbar-gutter: stable }`` reserves gutter space and is NOT
worked around: the snapshot records what the browser actually computed. The
reservation does not show up in ``documentElement.clientWidth``, which still
reports the full viewport width; it shows up in ``documentElement.offsetWidth``
and ``body.clientWidth``, so both are recorded per record as
``documentOffsetWidth`` and ``bodyClientWidth``.

Geometry is captured in DOCUMENT coordinates (viewport rect plus scroll offset)
so it does not move with the scroll position, and rounded to 4 decimal places.
That rounding is deliberately finer than the noise floor: SVG sub-element rects
shift by about 1e-4 px when the scroll offset changes, so the pinned offset is
load-bearing rather than merely tidy, and this harness reports that movement
instead of hiding it.

Usage:
    python -m http.server 8008                  # from the repo root, elsewhere
    python tools/css_diff.py capture --out _tmp/css-base.json
    python tools/css_diff.py compare _tmp/css-base.json
    python tools/css_diff.py compare _tmp/css-base-a.json _tmp/css-base-b.json
    python tools/css_diff.py capture --out _tmp/one.json --pages /about.html --widths 1280
    python tools/css_diff.py capture --out _tmp/dark.json --schemes dark
    python tools/css_diff.py capture --out _tmp/c.json --print-census
    python tools/css_diff.py capture --out _tmp/both.json --schemes light,dark
    python tools/css_diff.py capture --out _tmp/p.json --sentinel /index.html=.featured-card

Exit codes: 0 identical, 1 differences found, 2 usage, settings or capture error.
A page with no sentinel of its own is waited on for ``#app`` instead, so any
static page in the repository can be captured without extra configuration. The
three pages this plan migrates rules for -- the catalog, two film pages, and the
long-description case -- are the built-in defaults.
"""

import argparse
import collections
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STYLESHEET = ROOT / "css" / "style.css"

SCHEMA = "css-diff/1"
DEFAULT_BASE = "http://127.0.0.1:8008"
DEFAULT_PAGES = [
    "/index.html",
    "/films/tt2085059-black-mirror/index.html",
    "/films/tt2543312-halt-and-catch-fire/index.html",
]
DEFAULT_WIDTHS = [375, 576, 768, 1024, 1280]
DEFAULT_HEIGHT = 900
DEFAULT_SCROLL = 0
DEFAULT_SCHEMES = ["light"]
DEFAULT_SETTLE_MS = 900

CATALOG = "/index.html"
APP_ROOT = "#app"
DEFAULT_SENTINELS = {
    CATALOG: ".search",
    "/films/tt2085059-black-mirror/index.html": ".back-catalog a",
    "/films/tt2543312-halt-and-catch-fire/index.html": ".back-catalog a",
}

SNAPSHOT_ROOT = ":root"
SNAPSHOT_BODY = "body"

SHORTHANDS = [
    "padding", "padding-block", "padding-inline",
    "margin", "margin-block", "margin-inline",
    "gap",
    "border-radius", "border-width",
    "outline", "outline-width", "outline-style", "outline-color", "outline-offset",
    "inset", "inset-block", "inset-inline",
    "overflow", "overflow-x", "overflow-y",
    "place-items", "place-content",
    "flex", "flex-flow",
    "grid-area", "grid-template", "grid-template-columns", "grid-template-rows",
    "font", "background", "text-decoration", "list-style", "column-rule",
    "transform", "translate", "transform-origin", "perspective-origin",
    "transition", "animation",
    "contain", "container", "container-type", "container-name",
    "scrollbar-gutter", "scroll-margin", "scroll-padding", "overscroll-behavior",
    "mask", "filter", "backdrop-filter", "will-change", "size",
    "min-width", "min-height", "max-width", "max-height",
    "block-size", "inline-size",
    "flex-basis", "border-image", "word-break", "white-space",
]
SHORTHANDS = sorted(set(SHORTHANDS))

COMPARED_SETTINGS = ("pages", "widths", "height", "schemes", "pseudo", "focus",
                     "focusConditional", "focusTargets")

FOCUS_TARGETS = [
    {"key": "fav-filter", "selector": ".fav-filter", "state": "default"},
    {"key": "lucky", "selector": ".lucky", "state": "default"},
    {"key": "theme-toggle", "selector": ".theme-toggle", "state": "default"},
    {"key": "lang", "selector": ".lang", "state": "default"},
    {"key": "nav-a", "selector": ".nav a", "state": "default"},
    {"key": "search", "selector": ".search", "state": "default"},
    {"key": "genre-filter", "selector": ".genre-filter", "state": "default"},
    {"key": "th-sort", "selector": "th.sortable .th-sort", "state": "default"},
    {"key": "poster-icon", "selector": ".poster-icon", "state": "default"},
    {"key": "featured-card", "selector": ".featured-card", "state": "default"},
    {"key": "skip-link", "selector": ".skip-link", "state": "default"},
    {"key": "main", "selector": "#main", "state": "default"},
    {"key": "breadcrumb-a", "selector": ".breadcrumb a", "state": "default"},
    {"key": "summary", "selector": "summary", "state": "default"},
    {"key": "share-btn", "selector": ".share-btn", "state": "default"},
    {"key": "rc", "selector": ".related a.rc", "state": "default"},
    {"key": "back-catalog-a", "selector": ".back-catalog a", "state": "default"},
    {"key": "reset-filters", "selector": ".reset-filters", "state": "filtered"},
    {"key": "poster-close", "selector": ".poster-close", "state": "lightbox"},
]
FOCUS_TARGET_KEYS = [t["key"] for t in FOCUS_TARGETS]
OUTLINE_PROPS = ("outline", "outline-width", "outline-style", "outline-offset", "outline-color")
NON_MATCHING_QUERY = "zzqqxx-no-such-title-42"
FILTERED_WAIT_MS = 500
LIGHTBOX_WAIT_MS = 600

NOT_PROBED = [
    {"what": "::backdrop",
     "why": "a dialog backdrop's computed style is not reachable from JavaScript; "
            "the :root-wide backdrop declarations on the poster modal are unprobed"},
    {"what": "::marker and ::selection",
     "why": "not generated by the stylesheet, and not readable as element styles"},
    {"what": "which declaration won",
     "why": "only resolved values are compared, never the cascade. A swap between "
            "two declarations that resolve to the same value is invisible, which is "
            "also why a correct token substitution reads as no change"},
    {"what": "prefers-reduced-motion: reduce and forced-colors",
     "why": "the media context is pinned to no-preference / none, so those branches "
            "of css/style.css are never evaluated"},
    {"what": "scroll offsets other than the captured one",
     "why": "html { container-type: scroll-state } makes .scroll-top visibility a "
            "function of scroll position; only the single captured offset is probed"},
    {"what": "interaction states other than :focus-visible",
     "why": "the focus pass covers the 20 selectors in FOCUS_TARGETS under "
            ":focus-visible and blurred, which is every rule in css/style.css that "
            "carries an outline declaration; :hover, :active and [open] are still "
            "never entered, so the hover, active and lightbox-open visual states "
            "are unproved"},
    {"what": "outline declarations on a selector not in FOCUS_TARGETS",
     "why": "the focus pass reads a fixed target list, not every focusable element; "
            "a new :focus-visible rule on a selector outside that list is unproved "
            "until the list is extended"},
    {"what": "the dark palette in the default capture",
     "why": "the default scheme is light, matching ui_audit.py; pass "
            "--schemes light,dark to cover both, which is required before the "
            "outline and token migrations are believed in either theme"},
    {"what": "custom properties on descendants that merely inherit",
     "why": "an inherited token is byte-identical to its :root value by definition; "
            "only tokens whose value differs from :root are recorded per element"},
    {"what": "paint output",
     "why": "gradients, shadows and images are compared as computed values, not as "
            "pixels, so a rendering-engine difference would not be seen"},
    {"what": "structural CSS (a renamed or merged rule)",
     "why": "a structural edit that resolves to identical computed values reads as no "
            "change, by design: the guarantee this harness offers is about computed styles"},
]

BUILD_INITIAL = """
(cfg) => {
  const f = document.createElement('iframe');
  f.setAttribute('aria-hidden', 'true');
  f.style.cssText = 'position:absolute;left:-99999px;top:0;width:1200px;height:800px;border:0;visibility:hidden';
  document.documentElement.appendChild(f);
  const d = f.contentDocument;
  const el = d.createElement('div');
  d.body.appendChild(el);
  const cs = f.contentWindow.getComputedStyle(el);
  const out = {};
  for (let i = 0; i < cs.length; i++) {
    const n = cs[i];
    if (n.slice(0, 2) === '--') continue;
    out[n] = cs.getPropertyValue(n);
  }
  for (const s of cfg.shorthands) out[s] = cs.getPropertyValue(s);
  f.remove();
  return out;
}
"""

SETTLE = """
async (cfg) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const report = {};

  if (document.fonts) {
    const faces = Array.prototype.slice.call(document.fonts);
    await Promise.all(faces.map((f) => f.load().catch(() => null)));
    const deadline = Date.now() + 8000;
    while (Date.now() < deadline) {
      const pending = Array.prototype.some.call(document.fonts, (f) => f.status !== 'loaded');
      if (document.fonts.status === 'loaded' && !pending) break;
      await sleep(50);
    }
    report.fonts = document.fonts.status;
    report.faces = Array.prototype.map.call(document.fonts, (f) => f.family + '/' + f.weight + '/' + f.status);
  } else {
    report.fonts = 'no-fonts-api';
    report.faces = [];
  }

  const imgs = Array.prototype.slice.call(document.images);
  for (const im of imgs) {
    if (im.getAttribute('loading') === 'lazy') im.setAttribute('loading', 'eager');
  }
  await Promise.all(imgs.map((im) => (im.complete
    ? Promise.resolve()
    : new Promise((res) => {
        const done = () => res();
        im.addEventListener('load', done, { once: true });
        im.addEventListener('error', done, { once: true });
        setTimeout(done, 4000);
      }))));
  report.images = imgs.length;
  report.imagesLoaded = imgs.filter((im) => im.complete && im.naturalWidth > 0).length;
  await Promise.all(imgs.map((im) => (im.decode ? im.decode().catch(() => null) : null)));

  window.scrollTo({ top: cfg.scroll, left: 0, behavior: 'instant' });
  await frame();
  await sleep(cfg.settleMs);
  if (window.scrollY !== cfg.scroll || window.scrollX !== 0) {
    window.scrollTo({ top: cfg.scroll, left: 0, behavior: 'instant' });
    await frame();
    await sleep(200);
  }

  report.scrollX = window.scrollX;
  report.scrollY = window.scrollY;
  report.scrollHeight = document.documentElement.scrollHeight;
  report.viewportInnerWidth = window.innerWidth;
  report.documentClientWidth = document.documentElement.clientWidth;
  report.documentOffsetWidth = document.documentElement.offsetWidth;
  report.bodyClientWidth = document.body.clientWidth;
  report.colorScheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  report.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const anims = document.getAnimations ? document.getAnimations() : [];
  report.animations = anims.map((a) => ({
    state: a.playState,
    name: (a.animationName === undefined) ? null : a.animationName,
    transition: a.transitionProperty === undefined ? null : a.transitionProperty,
  }));
  return report;
}
"""

JS_HELPERS = """
  const q = (v) => Math.round(v * 10000) / 10000 + 0;

  const collect = (cs, into) => {
    for (let i = 0; i < cs.length; i++) {
      const n = cs[i];
      if (n.slice(0, 2) === '--') continue;
      const v = cs.getPropertyValue(n);
      if (initial[n] === v) continue;
      into[n] = v;
    }
    for (const s of cfg.shorthands) {
      const v = cs.getPropertyValue(s);
      if (!v || initial[s] === v) continue;
      into[s] = v;
    }
  };
  const tokens = (cs) => {
    const out = {};
    for (let i = 0; i < cs.length; i++) {
      const n = cs[i];
      if (n.slice(0, 2) !== '--') continue;
      out[n] = cs.getPropertyValue(n).trim();
    }
    return out;
  };

  const step = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const c = Array.prototype.slice.call(el.classList).sort();
    if (c.length) s += '.' + c.join('.');
    const parent = el.parentElement;
    if (parent) {
      const kids = Array.prototype.slice.call(parent.children);
      const twins = kids.filter((x) => x.tagName === el.tagName && String(x.getAttribute('class') || '') === String(el.getAttribute('class') || ''));
      if (twins.length > 1) {
        s += ':nth-of-type(' + (kids.filter((x) => x.tagName === el.tagName).indexOf(el) + 1) + ')';
      }
    }
    return s;
  };
  const pathOf = (el, root) => {
    const parts = [];
    let cur = el;
    while (cur) {
      parts.unshift(step(cur));
      if (cur === root) break;
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  };
  const readProps = (el) => {
    const into = {};
    collect(getComputedStyle(el), into);
    return into;
  };
  const readPseudo = (el) => {
    if (!cfg.pseudo) return null;
    let pseudo = null;
    for (const which of ['before', 'after']) {
      let pcs;
      try { pcs = getComputedStyle(el, '::' + which); } catch (e) { continue; }
      const content = pcs.getPropertyValue('content');
      if (!content || content === 'none' || content === 'normal') continue;
      const p = { content: content };
      collect(pcs, p);
      pseudo = pseudo || {};
      pseudo[which] = p;
    }
    return pseudo;
  };
"""

COLLECT = """
(cfg) => {
  const initial = cfg.initial;
  const wantPseudo = cfg.pseudo;
  const app = document.querySelector('#app');
""" + JS_HELPERS + """

  const rootEl = document.documentElement;
  const bodyEl = document.body;
  const rootTokens = tokens(getComputedStyle(rootEl));

  const elements = [];

  const rootCs = getComputedStyle(rootEl);
  const rootProps = {};
  collect(rootCs, rootProps);
  elements.push({
    path: cfg.snapshotRoot, synthetic: true, tag: 'html', id: '', classes: [],
    rect: { x: 0, y: 0, width: q(rootEl.scrollWidth), height: q(rootEl.scrollHeight) },
    props: rootProps, tokens: rootTokens, pseudo: null,
  });

  const bodyCs = getComputedStyle(bodyEl);
  const bodyProps = {};
  collect(bodyCs, bodyProps);
  elements.push({
    path: cfg.snapshotBody, synthetic: true, tag: 'body', id: bodyEl.id || '', classes: [],
    rect: (function () {
      const r = bodyEl.getBoundingClientRect();
      return { x: q(r.x + window.scrollX), y: q(r.y + window.scrollY), width: q(r.width), height: q(r.height) };
    })(),
    props: bodyProps, tokens: null, pseudo: null,
  });

  const nodes = [];
  if (app) {
    nodes.push(app);
    for (const el of app.querySelectorAll('*')) nodes.push(el);
  }

  const sx = window.scrollX, sy = window.scrollY;
  for (const el of nodes) {
    const cs = getComputedStyle(el);
    const props = {};
    collect(cs, props);
    const over = {};
    for (const name in rootTokens) {
      if (cs.getPropertyValue(name).trim() !== rootTokens[name]) over[name] = cs.getPropertyValue(name).trim();
    }
    const r = el.getBoundingClientRect();
    elements.push({
      path: pathOf(el, app),
      synthetic: false,
      tag: el.tagName.toLowerCase(),
      id: el.id || '',
      classes: Array.prototype.slice.call(el.classList).sort(),
      rect: { x: q(r.x + sx), y: q(r.y + sy), width: q(r.width), height: q(r.height) },
      props: props,
      tokens: Object.keys(over).length ? over : null,
      pseudo: wantPseudo ? readPseudo(el) : null,
    });
  }

  return {
    elements: elements,
    rootTokens: rootTokens,
    propertyNamesRead: Object.keys(initial).length,
  };
}
"""

FOCUS_PASS = """
(cfg) => {
  const initial = cfg.initial;
  const app = document.querySelector('#app');
""" + JS_HELPERS + """
  const out = {};
  const missed = [];
  for (const target of cfg.targets) {
    const el = document.querySelector(target.selector);
    if (!el) {
      out[target.key] = { selector: target.selector, present: false };
      continue;
    }
    if (document.activeElement && document.activeElement !== document.body) {
      document.activeElement.blur();
    }
    const noFocus = { props: readProps(el), pseudo: cfg.pseudo ? readPseudo(el) : null };
    el.focus({ preventScroll: true });
    const matched = el.matches(':focus-visible');
    if (!matched) missed.push(target.selector);
    out[target.key] = {
      selector: target.selector,
      present: true,
      focusVisibleMatched: matched,
      path: pathOf(el, app),
      rect: (function () {
        const r = el.getBoundingClientRect();
        return { x: q(r.x + window.scrollX), y: q(r.y + window.scrollY),
                 width: q(r.width), height: q(r.height) };
      })(),
      noFocus: noFocus,
      focused: { props: readProps(el), pseudo: cfg.pseudo ? readPseudo(el) : null },
    };
  }
  if (document.activeElement && document.activeElement !== document.body) {
    document.activeElement.blur();
  }
  return { targets: out, focusVisibleMissed: missed, scrollY: window.scrollY };
}
"""


def prune_record(record):
    pruned = dict(record["uniform"])
    for el in record["elements"]:
        props = el["props"]
        for name in pruned:
            props.pop(name, None)
    record["pruned"] = pruned or None
    del record["uniform"]
    return record


def compute_uniformity(record, uniform_min):
    seen = {}
    for el in record["elements"]:
        for name, value in (el.get("props") or {}).items():
            entry = seen.get(name)
            if entry is None:
                seen[name] = [value, 1]
            elif entry[0] == value:
                entry[1] += 1
    count = len(record["elements"])
    return {n: v[0] for n, v in seen.items() if v[1] == count and count >= uniform_min}


def fetch_record(page, cfg, initial):
    report = page.evaluate(SETTLE, {"scroll": cfg["scroll"], "settleMs": cfg["settleMs"]})
    if report["scrollY"] != cfg["scroll"] or report["scrollX"] != 0:
        raise RuntimeError(
            "scroll position did not settle at (%d, %d): got (%d, %d)"
            % (cfg["scroll"], 0, report["scrollX"], report["scrollY"]))
    running = [a for a in report["animations"] if a["state"] == "running"]
    if running:
        raise RuntimeError(
            "%d CSS animation(s)/transition(s) still running at capture time: %s"
            % (len(running), json.dumps(running, sort_keys=True)))
    if report["colorScheme"] != cfg["scheme"]:
        raise RuntimeError("colour scheme resolved to %r, expected %r"
                           % (report["colorScheme"], cfg["scheme"]))
    got = page.evaluate(COLLECT, {
        "initial": initial,
        "pseudo": cfg["pseudo"],
        "shorthands": SHORTHANDS,
        "snapshotRoot": SNAPSHOT_ROOT,
        "snapshotBody": SNAPSHOT_BODY,
    })
    record = {
        "page": cfg["page"],
        "width": cfg["width"],
        "height": cfg["height"],
        "scheme": cfg["scheme"],
        "scrollY": report["scrollY"],
        "colorScheme": report["colorScheme"],
        "reducedMotion": report["reducedMotion"],
        "animationsRunning": len(report["animations"]),
        "images": report["images"],
        "imagesLoaded": report["imagesLoaded"],
        "fonts": report["fonts"],
        "documentHeight": report["scrollHeight"],
        "viewportInnerWidth": report["viewportInnerWidth"],
        "documentClientWidth": report["documentClientWidth"],
        "documentOffsetWidth": report["documentOffsetWidth"],
        "bodyClientWidth": report["bodyClientWidth"],
        "propertyNamesRead": got["propertyNamesRead"],
        "rootTokens": got["rootTokens"],
        "elements": got["elements"],
    }
    if cfg["focus"]:
        record["focusRing"] = {"default": run_focus_pass(page, cfg, initial, "default")}
    if cfg["focusConditional"]:
        record["focusRingConditional"] = run_conditional_focus(page, cfg, initial)
    return record


def run_focus_pass(page, cfg, initial, phase, targets=None):
    targets = targets if targets is not None else FOCUS_TARGETS
    page.evaluate(
        "(y) => window.scrollTo({ top: y, left: 0, behavior: 'instant' })", cfg["scroll"])
    page.wait_for_timeout(150)
    page.keyboard.press("Shift")
    page.wait_for_timeout(60)
    if page.evaluate("() => window.scrollY") != cfg["scroll"]:
        raise RuntimeError(
            "the keyboard-modality prime moved the scroll position to %s, expected %d"
            % (page.evaluate("() => window.scrollY"), cfg["scroll"]))
    got = page.evaluate(FOCUS_PASS, {
        "initial": initial,
        "pseudo": cfg["pseudo"],
        "shorthands": SHORTHANDS,
        "targets": targets,
    })
    if got["focusVisibleMissed"]:
        raise RuntimeError(
            "%d focus target(s) did not match :focus-visible after focus({preventScroll:true}): "
            "%s. The focus pass would go green while observing no ring, so this is a hard error."
            % (len(got["focusVisibleMissed"]), ", ".join(got["focusVisibleMissed"])))
    if got["scrollY"] != cfg["scroll"]:
        raise RuntimeError(
            "the focus pass moved the scroll position to %s, expected %d; "
            "preventScroll was not sufficient" % (got["scrollY"], cfg["scroll"]))
    return got["targets"]


def run_conditional_focus(page, cfg, initial):
    out = {"filtered": {}, "lightbox": {}}
    if page.query_selector(".search") is None:
        return out
    page.fill(".search", NON_MATCHING_QUERY)
    page.wait_for_timeout(FILTERED_WAIT_MS)
    out["filtered"] = run_focus_pass(page, cfg, initial, "filtered", [
        t for t in FOCUS_TARGETS if t["state"] == "filtered"])
    page.fill(".search", "")
    page.wait_for_timeout(FILTERED_WAIT_MS)
    icon = page.locator(".poster-icon")
    if icon.count():
        icon.first.click()
        page.wait_for_timeout(LIGHTBOX_WAIT_MS)
        out["lightbox"] = run_focus_pass(page, cfg, initial, "lightbox", [
            t for t in FOCUS_TARGETS if t["state"] == "lightbox"])
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    return out


def capture(base, pages, widths, height, scroll, schemes, pseudo, settle_ms,
            uniform_min, out_path, quiet, sentinels, focus, focus_conditional):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        records = []
        all_pruned = {}
        try:
            for scheme in schemes:
                for page_path in pages:
                    sentinel = sentinels.get(page_path)
                    for width in widths:
                        ctx = browser.new_context(
                            viewport={"width": width, "height": height},
                            color_scheme=scheme,
                            locale="ru-RU",
                            reduced_motion="no-preference",
                            forced_colors="none",
                        )
                        page = ctx.new_page()
                        try:
                            response = page.goto(base + page_path, wait_until="load")
                            if response is not None and response.status != 200:
                                raise RuntimeError("%s returned HTTP %s" % (page_path, response.status))
                            page.wait_for_selector(sentinel or APP_ROOT,
                                                   state="attached", timeout=20000)
                            page.wait_for_timeout(400)
                            initial = page.evaluate(BUILD_INITIAL, {"shorthands": SHORTHANDS})
                            cfg = {
                                "page": page_path, "width": width, "height": height,
                                "scroll": scroll, "scheme": scheme, "settleMs": settle_ms,
                                "pseudo": pseudo, "focus": focus,
                                "focusConditional": focus_conditional,
                            }
                            record = fetch_record(page, cfg, initial)
                        finally:
                            ctx.close()
                        record["uniform"] = compute_uniformity(record, uniform_min)
                        for name, value in record["uniform"].items():
                            all_pruned.setdefault(name, set()).add(value)
                        prune_record(record)
                        records.append(record)
                        if not quiet:
                            print("captured %-52s @%4d %s  %5d elements, %d props read"
                                  % (page_path, width, scheme, len(record["elements"]),
                                     record["propertyNamesRead"]), file=sys.stderr)
        finally:
            browser.close()

    records.sort(key=lambda r: (r["page"], r["width"], r["scheme"]))
    pruned_names = sorted(all_pruned)
    snapshot = {
        "schema": SCHEMA,
        "meta": {
            "settings": {
                "base": base,
                "pages": list(pages),
                "widths": list(widths),
                "height": height,
                "scroll": scroll,
                "schemes": list(schemes),
                "pseudo": bool(pseudo),
                "focus": bool(focus),
                "focusConditional": bool(focus_conditional),
                "focusTargets": list(FOCUS_TARGET_KEYS),
            },
            "pruneUniformOnEveryElement": sorted(
                name for name in pruned_names if len(all_pruned[name]) == 1),
            "pruneValuesVaryByRecord": sorted(
                name for name in pruned_names if len(all_pruned[name]) > 1),
            "pruneRule": ("a property is omitted from props when its value equals the "
                          "browser's initial value, or when it holds one identical value "
                          "on every element of the record; hoisted values live in "
                          "record.pruned and are compared"),
            "notProbed": NOT_PROBED,
            "provenance": {
                "stylesheetSha256": hashlib.sha256(STYLESHEET.read_bytes()).hexdigest(),
                "stylesheetBytes": STYLESHEET.stat().st_size,
                "note": ("provenance is excluded from the comparison on purpose: a "
                         "whitespace-only or comment-only edit to css/style.css must "
                         "read as no change, and it changes this hash"),
            },
        },
        "records": records,
    }
    payload = json.dumps(snapshot, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(payload.encode("utf-8"))
    return snapshot, len(payload.encode("utf-8"))


def record_key(rec):
    return "%s @%d %s" % (rec["page"], rec["width"], rec["scheme"])


def scalar_diffs(label, left, right, out):
    for name in sorted(set(left) | set(right)):
        a = left.get(name)
        b = right.get(name)
        if a == b:
            continue
        if a is None:
            out.append("    %s.%s added: %r" % (label, name, b))
        elif b is None:
            out.append("    %s.%s removed: %r" % (label, name, a))
        else:
            out.append("    %s.%s %r -> %r" % (label, name, a, b))


def element_diffs(left, right, out):
    scalar_diffs("rect", left.get("rect") or {}, right.get("rect") or {}, out)
    scalar_diffs("prop", left.get("props") or {}, right.get("props") or {}, out)
    scalar_diffs("token", left.get("tokens") or {}, right.get("tokens") or {}, out)
    lp = left.get("pseudo") or {}
    rp = right.get("pseudo") or {}
    for which in sorted(set(lp) | set(rp)):
        if which not in lp:
            out.append("    ::%s appeared: %d propert(ies)" % (which, len(rp[which])))
        elif which not in rp:
            out.append("    ::%s disappeared: %d propert(ies)" % (which, len(lp[which])))
        else:
            scalar_diffs("::" + which, lp[which], rp[which], out)
    for field in ("tag", "id"):
        if left.get(field) != right.get(field):
            out.append("    %s %r -> %r" % (field, left.get(field), right.get(field)))
    if (left.get("classes") or []) != (right.get("classes") or []):
        out.append("    classes %r -> %r" % (left.get("classes"), right.get("classes")))


def focus_diffs(b, l, out):
    if b is None and l is None:
        return
    if b is None or l is None:
        out.append("    %s present in only one snapshot" % ("focus" if b else "focus(live)"))
        return
    for phase in sorted(set(b) | set(l)):
        left = b.get(phase) or {}
        right = l.get(phase) or {}
        for key in sorted(set(left) | set(right)):
            if key not in left:
                out.append("    focus[%s].%s only in live" % (phase, key))
                continue
            if key not in right:
                out.append("    focus[%s].%s only in baseline" % (phase, key))
                continue
            one, two = left[key], right[key]
            if bool(one.get("present")) != bool(two.get("present")):
                out.append("    focus[%s].%s present %r -> %r"
                           % (phase, key, one.get("present"), two.get("present")))
                continue
            if not one.get("present"):
                continue
            if bool(one.get("focusVisibleMatched")) != bool(two.get("focusVisibleMatched")):
                out.append("    focus[%s].%s focusVisibleMatched %r -> %r"
                           % (phase, key, one.get("focusVisibleMatched"),
                              two.get("focusVisibleMatched")))
            scalar_diffs("focus[%s].%s.rect" % (phase, key),
                         one.get("rect") or {}, two.get("rect") or {}, out)
            for state in ("noFocus", "focused"):
                scalar_diffs("focus[%s].%s.%s" % (phase, key, state),
                             (one.get(state) or {}).get("props") or {},
                             (two.get(state) or {}).get("props") or {}, out)
                lp = (one.get(state) or {}).get("pseudo") or {}
                rp = (two.get(state) or {}).get("pseudo") or {}
                for which in sorted(set(lp) | set(rp)):
                    scalar_diffs("focus[%s].%s.%s::%s" % (phase, key, state, which),
                                 lp.get(which) or {}, rp.get(which) or {}, out)


def diff_snapshots(base, live):
    lines = []
    changed_records = 0
    changed_elements = 0
    changed_values = 0

    bkeys = {record_key(r): r for r in base["records"]}
    lkeys = {record_key(r): r for r in live["records"]}
    for key in sorted(set(bkeys) | set(lkeys)):
        if key not in bkeys:
            lines.append("%s  RECORD ONLY IN LIVE (%d elements)" % (key, len(lkeys[key]["elements"])))
            changed_records += 1
            continue
        if key not in lkeys:
            lines.append("%s  RECORD ONLY IN BASELINE (%d elements)" % (key, len(bkeys[key]["elements"])))
            changed_records += 1
            continue
        b = bkeys[key]
        l = lkeys[key]
        local = []
        for field in ("page", "width", "height", "scheme", "scrollY", "colorScheme",
                      "reducedMotion", "animationsRunning", "images", "imagesLoaded",
                      "fonts", "documentHeight", "viewportInnerWidth",
                      "documentClientWidth", "documentOffsetWidth", "bodyClientWidth",
                      "propertyNamesRead"):
            if b.get(field) != l.get(field):
                local.append("    %s %r -> %r" % (field, b.get(field), l.get(field)))
        bp = b.get("pruned") or {}
        lp = l.get("pruned") or {}
        for name in sorted(set(bp) | set(lp)):
            if name in bp and name in lp:
                if bp[name] != lp[name]:
                    local.append("    pruned-uniform %s %r -> %r" % (name, bp[name], lp[name]))
            elif name in bp:
                local.append("    PRUNE ASYMMETRY %s was hoisted as uniform (%r) in the "
                             "baseline and is no longer uniform; its per-element values "
                             "are in the live record, the baseline has none"
                             % (name, bp[name]))
            else:
                local.append("    PRUNE ASYMMETRY %s is uniform in the live record (%r) "
                             "but the baseline kept it per element"
                             % (name, lp[name]))
        scalar_diffs("rootToken", b.get("rootTokens") or {}, l.get("rootTokens") or {}, local)
        for field in ("focusRing", "focusRingConditional"):
            focus_diffs(b.get(field), l.get(field), local)

        bmap = {e["path"]: e for e in b["elements"]}
        lmap = {e["path"]: e for e in l["elements"]}
        for path in sorted(set(bmap) - set(lmap)):
            local.append("  - element removed: %s" % path)
        for path in sorted(set(lmap) - set(bmap)):
            local.append("  + element added: %s" % path)
        for path in sorted(set(bmap) & set(lmap)):
            sub = []
            element_diffs(bmap[path], lmap[path], sub)
            if not sub:
                continue
            changed_elements += 1
            block = ["%s" % key, "  %s" % path]
            block.extend(sub)
            lines.append("\n".join(block))
        if local:
            changed_records += 1
            changed_values += sum(1 for ln in local if ln.startswith("    "))
            lines.append("%s  %d change(s) outside per-element props" % (key, len(local)))
            lines.extend(local)
    return lines, changed_records, changed_elements, changed_values


def check_settings(base, live):
    problems = []
    b = base["meta"]["settings"]
    l = live["meta"]["settings"]
    for name in COMPARED_SETTINGS:
        if b.get(name) != l.get(name):
            problems.append("  %s: baseline %r, live %r" % (name, b.get(name), l.get(name)))
    if base.get("schema") != live.get("schema"):
        problems.append("  schema: baseline %r, live %r" % (base.get("schema"), live.get("schema")))
    return problems


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def print_header(title, base, live, verbose):
    w = sys.stderr.write
    w("css_diff: %s\n" % title)
    bs = base["meta"]["settings"]
    ls = live["meta"]["settings"]
    w("  pages   %s\n" % ", ".join(bs["pages"]))
    w("  widths  %s at %dpx, scroll offset %d, scheme(s) %s\n"
      % (", ".join(str(x) for x in bs["widths"]), bs["height"], bs["scroll"],
         ", ".join(bs["schemes"])))
    if bs["base"] != ls["base"]:
        w("  base    baseline %s, live %s\n" % (bs["base"], ls["base"]))
    w("  records %d baseline, %d live\n" % (len(base["records"]), len(live["records"])))
    w("  hoisted as uniform on every element, excluded from props: %d -- %s\n"
      % (len(base["meta"]["pruneUniformOnEveryElement"]),
         ", ".join(base["meta"]["pruneUniformOnEveryElement"]) or "none"))
    w("  hoisted per record only: %d -- %s\n"
      % (len(base["meta"]["pruneValuesVaryByRecord"]),
         ", ".join(base["meta"]["pruneValuesVaryByRecord"]) or "none"))
    not_probed = base["meta"]["notProbed"]
    if verbose:
        w("  not probed:\n")
        for entry in not_probed:
            w("    %s -- %s\n" % (entry["what"], entry["why"]))
    else:
        w("  not probed: %d named exclusions, listed in meta.notProbed (%s)\n"
          % (len(not_probed), "; ".join(e["what"] for e in not_probed)))


def run_capture(args, out_path):
    snapshot, size = capture(
        base=args.base, pages=args.pages, widths=args.widths, height=args.height,
        scroll=args.scroll, schemes=args.schemes, pseudo=not args.no_pseudo,
        settle_ms=args.settle, uniform_min=args.uniform_min, out_path=out_path,
        quiet=args.quiet, sentinels=resolve_sentinels(args),
        focus=not args.no_focus, focus_conditional=not args.no_focus_conditional)
    total_elements = sum(len(r["elements"]) for r in snapshot["records"])
    total_props = sum(len(e.get("props") or {}) for r in snapshot["records"] for e in r["elements"])
    total_rect = len(snapshot["records"]) * 4
    print("css_diff: captured %d record(s), %d element record(s), %d propert(y|ies) per element, %d bytes"
          % (len(snapshot["records"]), total_elements, total_props, size), file=sys.stderr)
    if args.print_census:
        census(snapshot, args.census_top)
    return 0


def census(snapshot, top):
    counter = collections.Counter()
    focus_counter = collections.Counter()
    rects = 0
    pseudo_props = 0
    pseudo_els = 0
    token_names = set()
    focus_present = 0
    focus_absent = 0
    focus_values = {}
    for rec in snapshot["records"]:
        counter.update((rec.get("pruned") or {}).keys())
        token_names.update((rec.get("rootTokens") or {}).keys())
        for el in rec["elements"]:
            counter.update(el["props"].keys())
            counter.update((el.get("tokens") or {}).keys())
            rects += 1
            if el.get("pseudo"):
                pseudo_els += 1
                for bucket in el["pseudo"].values():
                    pseudo_props += len(bucket)
        for field in ("focusRing", "focusRingConditional"):
            for phase, targets in (rec.get(field) or {}).items():
                for entry in targets.values():
                    if not entry.get("present"):
                        focus_absent += 1
                        continue
                    focus_present += 1
                    for state in ("noFocus", "focused"):
                        bucket = (entry.get(state) or {}).get("props") or {}
                        focus_counter.update(bucket.keys())
                        for name in OUTLINE_PROPS:
                            if name in bucket:
                                focus_values.setdefault(name, collections.Counter())[
                                    bucket[name]] += 1
    watch = ["padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
             "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
             "gap", "row-gap", "column-gap", "border-radius",
             "border-top-left-radius", "border-bottom-left-radius",
             "z-index", "outline", "outline-width", "outline-style", "outline-color",
             "outline-offset", "container-type", "scrollbar-gutter"]
    print("PROPERTY CENSUS over %d record(s)" % len(snapshot["records"]))
    print("  element records: %d" % rects)
    print("  pseudo-element styles captured: %d properties on %d elements"
          % (pseudo_props, pseudo_els))
    print("  :root custom properties captured: %d" % len(token_names))
    print("  watched properties (count = element records carrying the property):")
    for name in watch:
        print("    %-16s %d" % (name, counter.get(name, 0)))
    print("  focus pass: %d target/phase observations present, %d absent in this state"
          % (focus_present, focus_absent))
    print("  focus pass watched properties (count = focused/blurred observations carrying it):")
    for name in OUTLINE_PROPS:
        print("    %-16s %d" % (name, focus_counter.get(name, 0)))
    print("  focus pass distinct values actually observed:")
    for name in OUTLINE_PROPS:
        vals = focus_values.get(name) or collections.Counter()
        print("    %-16s %d distinct: %s"
              % (name, len(vals),
                 ", ".join("%r x%d" % (v, n) for v, n in vals.most_common(6))))
    print("  all properties, %d most common:" % top)
    for name, count in counter.most_common(top):
        print("    %-34s %d" % (name, count))


def run_compare(args, paths):
    base = load(paths[0])
    if len(paths) == 2:
        live = load(paths[1])
        title = "comparing two snapshot files"
    else:
        out = Path(args._scratch)
        if not args.quiet:
            print("css_diff: re-capturing live against %s" % paths[0], file=sys.stderr)
        live, _ = capture(
            base=args.base, pages=args.pages, widths=args.widths, height=args.height,
            scroll=args.scroll, schemes=args.schemes, pseudo=not args.no_pseudo,
            settle_ms=args.settle, uniform_min=args.uniform_min, out_path=out,
            quiet=args.quiet, sentinels=resolve_sentinels(args),
            focus=not args.no_focus, focus_conditional=not args.no_focus_conditional)
        title = "comparing live capture against %s" % paths[0]

    problems = check_settings(base, live)
    if not problems:
        _, changed_records, changed_elements, _ = diff_snapshots(base, live)
    else:
        changed_records = -1
    print_header(title, base, live, verbose=bool(changed_records))
    if problems:
        print("css_diff: NOT COMPARABLE, the two snapshots were taken with different settings")
        for line in problems:
            print(line, file=sys.stderr)
        return 2

    lines, changed_records, changed_elements, changed_values = diff_snapshots(base, live)
    if not lines:
        print("css_diff: IDENTICAL -- %d record(s), no computed style and no geometry differs"
              % len(base["records"]))
        return 0
    print("css_diff: DIFFERENT -- %d record(s) changed, %d element(s) changed, "
          "%d value(s) changed outside per-element props"
          % (changed_records, changed_elements, changed_values))
    shown = lines[:args.max_lines]
    for line in shown:
        print(line)
    if len(lines) > len(shown):
        print("... %d more line(s) suppressed by --max-lines %d" % (len(lines) - len(shown), args.max_lines))
    return 1


def parse_list(text, cast=str):
    if not isinstance(text, str):
        return list(text)
    return [cast(part.strip()) for part in text.split(",") if part.strip()]


def resolve_sentinels(args):
    sentinels = dict(DEFAULT_SENTINELS)
    for pair in parse_list(args.sentinel):
        if "=" not in pair:
            raise ValueError("--sentinel wants path=selector pairs, got %r" % pair)
        path, selector = pair.split("=", 1)
        sentinels[path.strip()] = selector.strip() or None
    return sentinels


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("capture", "compare"))
    ap.add_argument("paths", nargs="*",
                    help="compare: the baseline snapshot, and optionally a second "
                         "snapshot to diff against it offline")
    ap.add_argument("--out", default="",
                    help="capture: destination JSON file")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--pages", default=None,
                    help="comma-separated site paths; defaults to the built-in list "
                         "for capture and to the baseline's own list for compare")
    ap.add_argument("--widths", default=None,
                    help="comma-separated viewport widths; defaults to the built-in "
                         "list for capture and to the baseline's list for compare")
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--scroll", type=int, default=None,
                    help="scroll offset the capture is pinned to")
    ap.add_argument("--schemes", default=None)
    ap.add_argument("--settle", type=int, default=DEFAULT_SETTLE_MS)
    ap.add_argument("--sentinel", default="",
                    help="comma-separated path=selector readiness pairs; a page with "
                         "no sentinel falls back to waiting for %s" % APP_ROOT)
    ap.add_argument("--no-pseudo", action="store_true",
                    help="skip ::before / ::after computed styles")
    ap.add_argument("--no-focus", action="store_true",
                    help="skip the focus pass, which is the only way this harness can "
                         "observe the 13 focus-carried outline declarations")
    ap.add_argument("--no-focus-conditional", action="store_true",
                    help="skip the filtered and lightbox phases of the focus pass")
    ap.add_argument("--uniform-min", type=int, default=1,
                    help="minimum elements in a record before uniform hoisting applies")
    ap.add_argument("--max-lines", type=int, default=500)
    ap.add_argument("--print-census", action="store_true")
    ap.add_argument("--census-top", type=int, default=25)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.command == "capture":
        args.pages = parse_list(args.pages) if args.pages else list(DEFAULT_PAGES)
        args.widths = parse_list(args.widths, int) if args.widths else list(DEFAULT_WIDTHS)
        args.schemes = parse_list(args.schemes) if args.schemes else list(DEFAULT_SCHEMES)
        args.height = DEFAULT_HEIGHT if args.height is None else args.height
        args.scroll = DEFAULT_SCROLL if args.scroll is None else args.scroll
        if args.paths or not args.out:
            print("css_diff: capture takes no positional file; pass --out FILE",
                  file=sys.stderr)
            return 2
        return run_capture(args, Path(args.out))

    if len(args.paths) not in (1, 2):
        print("css_diff: compare needs one baseline file, or two files to diff offline",
              file=sys.stderr)
        return 2
    for path in args.paths:
        if not Path(path).is_file():
            print("css_diff: no such snapshot: %s" % path, file=sys.stderr)
            return 2
    base_settings = load(args.paths[0])["meta"]["settings"]
    if args.pages is None:
        args.pages = list(base_settings["pages"])
    if args.widths is None:
        args.widths = list(base_settings["widths"])
    if args.schemes is None:
        args.schemes = list(base_settings["schemes"])
    if args.height is None:
        args.height = base_settings["height"]
    if args.scroll is None:
        args.scroll = base_settings["scroll"]
    args.pages = parse_list(args.pages)
    args.widths = parse_list(args.widths, int)
    args.schemes = parse_list(args.schemes)
    args._scratch = str(Path(tempfile.gettempdir()) / "css_diff_live.json")
    return run_compare(args, args.paths)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, PlaywrightError) as exc:
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        print("css_diff: %s" % first, file=sys.stderr)
        sys.exit(2)
