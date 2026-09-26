#!/usr/bin/env python3
"""Repeatable UI invariant audit for the IT Movies static site.

Runs a real Chromium against a served copy of the site and asserts the
accessibility, responsive and data-integrity invariants that the redesign
must not regress. Hard failures and advisory findings are reported in
separate sections; only hard failures affect the exit code.

Exit codes: 0 all hard invariants hold, 1 hard failure(s), 2 usage error.

Usage:
    python -m http.server 8008        # from the repo root, in another shell
    python tools/ui_audit.py
    python tools/ui_audit.py --only cls-zero,tap-targets
    python tools/ui_audit.py --json

Checks that are declared by the plan but not yet implemented are a usage
error, never a silent pass.

Output stability: every section from HARD FAILURES onward is byte-stable
across runs and can be diffed. The MEASUREMENTS section above it contains
the cls column, which is a live PerformanceObserver reading and varies
between runs by nature.
"""
import argparse
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8008"
CATALOG = "/"
FILM_PAGES = [
    "/films/tt1219827-ghost-in-the-shell/",
    "/films/tt9055630-h0us3/",
    "/films/tt8488126-the-inventor-out-for-blood-in-silicon-valley/",
    "/films/tt39150120-the-ai-doc-or-how-i-became-an-apocaloptimist/",
    "/films/kp-11442722-how-to-access-everything-reverse-engineering/",
    "/films/tt2085059-black-mirror/",
    "/films/tt8879940-mythic-quest/",
    "/films/tt2693776-intelligence/",
]
PAGES = [CATALOG] + FILM_PAGES
WIDTHS = [(375, 812), (576, 900), (767, 1024), (768, 1024), (1024, 900), (1280, 900)]

TAP_HARD_MIN = 24
TAP_ADVISORY_MIN = 44
CONTRAST_FLOOR = 4.5
CLS_CEILING = 1e-3
INNER_OVERFLOW_WIDTHS = (375, 767)
CONTRAST_WIDTH = 1280
CONTRAST_HEIGHT = 900
NON_MATCHING_QUERY = "zzqqxx-no-such-title-42"
EXPECTED_STATUS = 200

IMAGE_VIEWPORTS = (("desktop", 1280, 900), ("mobile", 375, 812))
RELATED_STABLE_PATH = "/films/tt2085059-black-mirror/"
RELATED_STABLE_LOADS = 4
RELATED_STABLE_WAIT = 500
RELATED_TITLE_SELECTOR = ".related .rc-title"
JSONLD_RENDER_SELECTOR = ".rc .rc-title"
JSONLD_RENDER_WAIT = 600
POSTER_IMG_SELECTORS = (
    ".poster-modal-inner > img",
    ".film-poster img",
    ".poster-wrap img",
    ".rc-poster",
)
POSTER_ASPECT_TOLERANCE = 0.02
CROPPING_OBJECT_FIT = "cover"
NOT_PROBED = "not probed"
COVERAGE_OWNERS = (
    ("inspected", "no-broken-srcset"),
    ("defects", "no-broken-srcset"),
    ("compared", "poster-aspect"),
    ("cropped", "poster-aspect"),
)
DATA_COVERAGE_OWNERS = (
    ("ldNames", "jsonld-matches-render"),
    ("cards", "jsonld-matches-render"),
    ("pool", "jsonld-matches-render"),
)

PAGE_SENTINELS = {CATALOG: ".search"}
FILM_SENTINEL = ".back-catalog a"

DELIBERATE_TRUNCATORS = (".alt-title", ".rc-info", ".featured-card-meta",
                         ".film-header-alt")
DELIBERATE_SCROLLERS = (".table-wrap", ".featured-grid")

LAYOUT_CHECKS = ("no-h-overflow", "cls-zero", "tap-targets", "no-inner-overflow")
IMAGE_CHECKS = ("no-broken-srcset", "poster-aspect")
STABILITY_CHECKS = ("related-stable",)
DATA_CHECKS = ("jsonld-matches-render",)
IMPLEMENTED_CHECKS = (LAYOUT_CHECKS + IMAGE_CHECKS + STABILITY_CHECKS + DATA_CHECKS
                      + ("contrast-floor",))
DECLARED_NOT_IMPLEMENTED = (
    "sort-controls-reachable",
    "live-region-persistent",
    "skip-link-present",
    "focus-ring-visible",
    "no-star-rating-when-unrated",
)

TAP_TARGETS = [
    ".fav-filter", ".lucky", ".theme-toggle", ".lang", ".reset-filters",
    ".scroll-top", ".search", ".genre-filter", ".nav a", ".th-sort",
    ".breadcrumb a", "summary", ".share-btn", ".back-catalog a",
    ".poster-close", ".mobile-sort",
]
CONDITIONAL_STATES = {
    "filtered": [".reset-filters", ".catalog-status"],
    "lightbox": [".poster-close"],
}
CONDITIONAL_MARKERS = [".catalog-status", ".poster-modal"]
WATCHED = sorted(set(TAP_TARGETS + CONDITIONAL_MARKERS))

TEXT_TOKENS = ["--ink", "--muted", "--accent", "--kp", "--imdb"]
SCHEMES = ("light", "dark")

PROBE = """
(arg) => {
  const cfg = arg.cfg, sels = arg.sels;
  const out = { overflow: [], inner: [], taps: [], presence: {}, cls: 0 };
  const name = (el) => el.tagName.toLowerCase() +
    (el.className ? "." + String(el.className).trim().split(/\\s+/).join(".") : "");
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth) {
    out.overflow.push({ selector: "html", scrollW: de.scrollWidth, clientW: de.clientWidth });
  }
  if (cfg.inner) {
    for (const el of document.querySelectorAll("#app *")) {
      if (el.clientWidth <= 1) continue;
      if (el.scrollWidth <= el.clientWidth + 1) continue;
      const cs = getComputedStyle(el);
      let a = el.parentElement, clips = [];
      while (a && a !== document.documentElement && clips.length < 4) {
        const acs = getComputedStyle(a);
        if (acs.overflowX !== "visible") clips.push(name(a) + "[" + acs.overflowX + "]");
        a = a.parentElement;
      }
      out.inner.push({
        selector: name(el), scrollW: el.scrollWidth, clientW: el.clientWidth,
        overflowX: cs.overflowX, textOverflow: cs.textOverflow,
        clamp: cs.webkitLineClamp, clips: clips,
      });
    }
  }
  for (const sel of sels) {
    const nodes = document.querySelectorAll(sel);
    out.presence[sel] = nodes.length;
    if (!cfg.taps || !nodes.length) continue;
    for (const el of nodes) {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      out.taps.push({ selector: sel, w: Math.round(r.width), h: Math.round(r.height) });
    }
  }
  out.cls = window.__cls || 0;
  return out;
}
"""

INIT = """
window.__cls = 0;
new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; })
  .observe({ type: 'layout-shift', buffered: true });
"""

CONTRAST = """
(tokens) => {
  const lum = (rgb) => {
    const c = rgb.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const parse = (s) => (s.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
  const ratio = (a, b) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const cs = getComputedStyle(document.documentElement);
  const read = (name) => cs.getPropertyValue(name).trim();
  const VAR_REF = /var\\(\\s*(--[A-Za-z0-9_-]+)/g;
  const refsResolved = (name, depth) => {
    if (depth > 8) return true;
    const raw = read(name);
    if (!raw) return false;
    let m;
    VAR_REF.lastIndex = 0;
    while ((m = VAR_REF.exec(raw)) !== null) {
      if (!refsResolved(m[1], depth + 1)) return false;
    }
    return true;
  };
  const RGB = /^rgba?\\(/i;
  const resolve = (name) => {
    const raw = read(name);
    if (!raw) return { state: "undefined", raw: raw, computed: "", rgb: null };
    if (!refsResolved(name, 0)) return { state: "unresolved", raw: raw, computed: "", rgb: null };
    const probe = document.createElement("span");
    probe.style.color = raw;
    document.body.appendChild(probe);
    const computed = getComputedStyle(probe).color;
    probe.remove();
    const rgb = parse(computed);
    if (!RGB.test(computed) || rgb.length < 3 || rgb.some((v) => !isFinite(v))) {
      return { state: "unmeasurable", raw: raw, computed: computed, rgb: null };
    }
    return { state: "ok", raw: raw, computed: computed, rgb: rgb };
  };
  const surfaces = {};
  for (const name of ["--bg", "--paper"]) surfaces[name.slice(2)] = resolve(name);
  const out = {};
  for (const name of tokens) {
    const r = resolve(name);
    const entry = { state: r.state, raw: r.raw, computed: r.computed, ratios: {} };
    if (r.state === "ok") {
      for (const sname of Object.keys(surfaces)) {
        const sval = surfaces[sname];
        entry.ratios[sname] = sval.state === "ok" ? ratio(r.rgb, sval.rgb) : null;
      }
    }
    out[name] = entry;
  }
  return { out, surfaces };
}
"""

IMAGES = """
(cfg) => {
  const name = (el) => el.tagName.toLowerCase() +
    (el.className ? "." + String(el.className).trim().split(/\\s+/).join(".") : "");
  const out = { srcset: [], srcsetInspected: 0, poster: [] };
  const carriers = [
    ["img[srcset]", (el) => el.getAttribute("srcset")],
    ["link[imagesrcset]", (el) => el.getAttribute("imagesrcset")],
  ];
  for (const [sel, read] of carriers) {
    for (const el of document.querySelectorAll(sel)) {
      const raw = read(el) || "";
      out.srcsetInspected += 1;
      const seen = [], problems = [];
      let parsed = 0;
      for (const part of raw.split(",")) {
        const cand = part.trim();
        if (!cand) continue;
        const m = cand.match(/\\s(\\d+(?:\\.\\d+)?)([wx])$/);
        if (!m) {
          problems.push("candidate without a width or density descriptor: " + cand);
          continue;
        }
        parsed += 1;
        if (m[2] === "x") continue;
        const w = Number(m[1]);
        if (!Number.isInteger(w) || w <= 0) {
          problems.push("width descriptor is not a positive integer: " + cand);
        } else if (seen.indexOf(w) !== -1) {
          problems.push("duplicate width descriptor " + w + "w");
        } else {
          seen.push(w);
        }
      }
      if (parsed < 1 && problems.length < 1) {
        problems.push("no candidate carries a width or density descriptor");
      }
      if (problems.length) {
        out.srcset.push({ selector: sel + " " + name(el), raw: raw, problems: problems });
      }
    }
  }
  for (const sel of cfg.posters) {
    for (const img of document.querySelectorAll(sel)) {
      const cs = getComputedStyle(img);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const nw = img.naturalWidth, nh = img.naturalHeight;
      if (!nw || !nh) continue;
      const r = img.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      out.poster.push({
        selector: sel,
        rendered: +(r.width / r.height).toFixed(4),
        natural: +(nw / nh).toFixed(4),
        delta: +Math.abs(r.width / r.height - nw / nh).toFixed(4),
        objectFit: cs.objectFit,
        naturalSize: nw + "x" + nh,
        renderedSize: Math.round(r.width) + "x" + Math.round(r.height),
      });
    }
  }
  return out;
}
"""

JSONLD_RENDER = """
(cfg) => {
  const out = { itemLists: 0, names: null, cards: [], pool: 0, unparsable: 0 };
  const nodes = Array.prototype.slice.call(
    document.querySelectorAll('script[type="application/ld+json"]'));
  const graphs = [];
  for (const node of nodes) {
    let doc = null;
    try {
      doc = JSON.parse(node.textContent);
    } catch (e) {
      out.unparsable += 1;
      continue;
    }
    if (doc && Array.isArray(doc["@graph"])) graphs.push.apply(graphs, doc["@graph"]);
    else if (doc) graphs.push(doc);
  }
  const lists = graphs.filter((n) => n && n["@type"] === "ItemList");
  out.itemLists = lists.length;
  if (lists.length === 1) {
    const elements = lists[0].itemListElement;
    out.names = Array.isArray(elements)
      ? elements.map((e) => (e && typeof e.name === "string") ? e.name : "")
      : null;
  }
  out.cards = Array.prototype.slice.call(document.querySelectorAll(cfg.selector))
    .map((el) => el.textContent.trim());
  const payload = window.FILM_PAGE || null;
  out.pool = (payload && Array.isArray(payload.relatedPool)) ? payload.relatedPool.length : 0;
  return out;
}
"""

COLOUR_STATE_TEXT = {
    "undefined": "is not defined on :root",
    "unresolved": "references an undefined custom property (declared as %r)",
    "unmeasurable": "computes to unmeasurable colour syntax %r",
}


def is_hard_overflow(overflow_x):
    return overflow_x == "visible"


def is_allowlisted_overflow(selector, overflow_x, text_overflow, clamp):
    classes = set(selector.split(".")[1:])
    truncating = (text_overflow == "ellipsis") or (clamp not in ("none", ""))
    for entry in DELIBERATE_TRUNCATORS:
        if entry.lstrip(".") in classes:
            return truncating and overflow_x != "visible"
    for entry in DELIBERATE_SCROLLERS:
        if entry.lstrip(".") in classes:
            return overflow_x in ("auto", "scroll")
    return False


def sentinel_for(path):
    return PAGE_SENTINELS.get(path, FILM_SENTINEL)


def rgb_text(rgb):
    return "rgb(%d, %d, %d)" % tuple(rgb) if rgb else "unresolved"


def group_inner(entries):
    groups = {}
    for e in entries:
        if is_allowlisted_overflow(e["selector"], e["overflowX"],
                                   e["textOverflow"], e["clamp"]):
            continue
        key = (e["selector"], e["overflowX"], tuple(e["clips"]))
        cur = groups.get(key)
        delta = e["scrollW"] - e["clientW"]
        if cur is None:
            groups[key] = {
                "selector": e["selector"], "overflowX": e["overflowX"],
                "clips": list(e["clips"]), "scrollW": e["scrollW"],
                "clientW": e["clientW"], "delta": delta, "instances": 1,
            }
        else:
            cur["instances"] += 1
            if delta > cur["delta"]:
                cur["scrollW"] = e["scrollW"]
                cur["clientW"] = e["clientW"]
                cur["delta"] = delta
    return [groups[k] for k in sorted(groups)]


def classify_overflow(group):
    if group["clips"]:
        return "advisory"
    return "hard" if is_hard_overflow(group["overflowX"]) else "advisory"


def check_page_response(key, response, sentinel_found, path, hard):
    status = response.status if response is not None else None
    if status != EXPECTED_STATUS:
        hard.append("[%s] page-load: %s returned HTTP %s, expected %d"
                    % (key, path, status, EXPECTED_STATUS))
        return False
    if not sentinel_found:
        hard.append("[%s] page-load: sentinel %s not found on %s"
                    % (key, sentinel_for(path), path))
        return False
    return True


def run_layout(browser, base, enabled, hard, advisory, results, coverage, taps):
    for path in PAGES:
        for width, height in WIDTHS:
            key = "%s@%d" % (path, width)
            ctx = browser.new_context(
                viewport={"width": width, "height": height}, color_scheme="light"
            )
            page = ctx.new_page()
            page.add_init_script(INIT)
            response = page.goto(base + path, wait_until="load")
            page.wait_for_timeout(2200)
            sentinel_found = page.query_selector(sentinel_for(path)) is not None
            if not check_page_response(key, response, sentinel_found, path, hard):
                ctx.close()
                continue
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(900)

            want_inner = (enabled("no-inner-overflow")
                          and width in INNER_OVERFLOW_WIDTHS)
            base_probe = page.evaluate(PROBE, {
                "cfg": {"inner": want_inner, "taps": enabled("tap-targets")},
                "sels": WATCHED,
            })
            record(results, coverage, key, "base", base_probe, base_probe["cls"],
                   want_inner, enabled)
            if enabled("cls-zero"):
                if base_probe["cls"] > CLS_CEILING:
                    hard.append("[%s] cls-zero: CLS=%r exceeds the %g ceiling"
                                % (key, base_probe["cls"], CLS_CEILING))
            for o in sorted(base_probe["overflow"],
                            key=lambda e: (e["selector"], e["scrollW"])):
                if enabled("no-h-overflow"):
                    hard.append("[%s] no-h-overflow: %s scrollW=%d > clientW=%d"
                                % (key, o["selector"], o["scrollW"], o["clientW"]))
            if want_inner:
                emit_inner(key, base_probe["inner"], hard, advisory)
            if enabled("tap-targets"):
                emit_taps(key, base_probe["taps"], taps)

            if path == CATALOG:
                drive_conditional(page, key, results, coverage, taps, enabled)
            ctx.close()


def drive_conditional(page, key, results, coverage, taps, enabled):
    want_taps = enabled("tap-targets")
    cfg = {"cfg": {"inner": False, "taps": want_taps}, "sels": WATCHED}
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)
    page.fill(".search", NON_MATCHING_QUERY)
    page.wait_for_timeout(500)
    probe = page.evaluate(PROBE, cfg)
    record(results, coverage, key, "filtered", probe, None, False, enabled)
    if want_taps:
        emit_taps(key, probe["taps"], taps)

    page.fill(".search", "")
    page.wait_for_timeout(500)
    icons = page.locator(".poster-icon")
    if icons.count():
        icons.first.click()
        page.wait_for_timeout(600)
        probe = page.evaluate(PROBE, cfg)
        record(results, coverage, key, "lightbox", probe, None, False, enabled)
        if want_taps:
            emit_taps(key, probe["taps"], taps)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def run_related_stable(browser, base, hard):
    path = RELATED_STABLE_PATH
    ctx = browser.new_context(
        viewport={"width": CONTRAST_WIDTH, "height": CONTRAST_HEIGHT},
        color_scheme="light",
    )
    page = ctx.new_page()
    runs = []
    for _ in range(RELATED_STABLE_LOADS):
        response = page.goto(base + path, wait_until="load")
        sentinel_found = page.query_selector(sentinel_for(path)) is not None
        if not check_page_response(path, response, sentinel_found, path, hard):
            ctx.close()
            return
        page.wait_for_timeout(RELATED_STABLE_WAIT)
        runs.append(page.eval_on_selector_all(
            RELATED_TITLE_SELECTOR, "e => e.map((x) => x.textContent.trim())"))
    ctx.close()
    if not runs[0]:
        hard.append("[%s] related-stable: %s matched no related card title"
                    % (path, RELATED_TITLE_SELECTOR))
        return
    for load_no, titles in enumerate(runs[1:], start=2):
        if titles != runs[0]:
            hard.append("[%s] related-stable: load %d rendered %r, load 1 rendered %r"
                        % (path, load_no, titles, runs[0]))
            return


def run_jsonld_render(browser, base, hard, data_coverage):
    for path in FILM_PAGES:
        ctx = browser.new_context(
            viewport={"width": CONTRAST_WIDTH, "height": CONTRAST_HEIGHT},
            color_scheme="light",
        )
        page = ctx.new_page()
        response = page.goto(base + path, wait_until="load")
        sentinel_found = page.query_selector(sentinel_for(path)) is not None
        if not check_page_response(path, response, sentinel_found, path, hard):
            ctx.close()
            continue
        page.wait_for_timeout(JSONLD_RENDER_WAIT)
        got = page.evaluate(JSONLD_RENDER, {"selector": JSONLD_RENDER_SELECTOR})
        ctx.close()
        names = got["names"]
        cards = got["cards"]
        data_coverage[path] = {
            "ldNames": len(names) if names is not None else 0,
            "cards": len(cards),
            "pool": got["pool"],
        }
        if got["unparsable"]:
            hard.append("[%s] jsonld-matches-render: %d JSON-LD script(s) did not "
                        "parse as JSON" % (path, got["unparsable"]))
        if got["itemLists"] != 1 or names is None:
            hard.append("[%s] jsonld-matches-render: the page carries %d JSON-LD "
                        "ItemList node(s), expected exactly 1 with a name list"
                        % (path, got["itemLists"]))
            continue
        if not names:
            hard.append("[%s] jsonld-matches-render: the JSON-LD ItemList has an "
                        "empty itemListElement, so the comparison would be vacuous"
                        % path)
            continue
        if not cards:
            hard.append("[%s] jsonld-matches-render: %s matched no related card "
                        "title" % (path, JSONLD_RENDER_SELECTOR))
            continue
        if cards != names:
            hard.append("[%s] jsonld-matches-render: the DOM rendered %r, the "
                        "JSON-LD ItemList lists %r" % (path, cards, names))
            continue
        if got["pool"]:
            hard.append("[%s] jsonld-matches-render: the served payload still "
                        "carries a relatedPool of %d item(s); the client must "
                        "render FILM_PAGE.related, a pool only reopens the "
                        "shuffled-subset defect" % (path, got["pool"]))


def record(results, coverage, key, state, probe, cls, want_inner, enabled):
    coverage.setdefault(state, {})[key] = probe["presence"]
    if state != "base":
        return
    row = {"cls": cls, "overflow": len(probe["overflow"])}
    if want_inner:
        counts = {"hard": 0, "advisory": 0}
        for g in group_inner(probe["inner"]):
            counts[classify_overflow(g)] += g["instances"]
        row["innerHard"] = counts["hard"]
        row["innerAdvisory"] = counts["advisory"]
    if enabled("tap-targets"):
        hard = adv = 0
        for t in probe["taps"]:
            if t["w"] < TAP_HARD_MIN or t["h"] < TAP_HARD_MIN:
                hard += 1
            elif t["w"] < TAP_ADVISORY_MIN or t["h"] < TAP_ADVISORY_MIN:
                adv += 1
        row["tapHard"] = hard
        row["tapAdvisory"] = adv
    results[key] = row


def emit_inner(key, entries, hard, advisory):
    for g in group_inner(entries):
        line = ("[%s] no-inner-overflow: %s overflow-x %s, scrollW=%d > clientW=%d "
                "(+%dpx), %d instance(s)%s"
                % (key, g["selector"], g["overflowX"], g["scrollW"], g["clientW"],
                   g["delta"], g["instances"],
                   ", clipped by ancestor " + " > ".join(g["clips"]) if g["clips"] else ""))
        if classify_overflow(g) == "hard":
            hard.append(line)
        else:
            advisory.append(line)


def emit_taps(key, taps, buckets):
    seen = set()
    for t in sorted(taps, key=lambda t: (t["selector"], t["w"], t["h"])):
        token = (t["selector"], t["w"], t["h"])
        if token in seen:
            continue
        seen.add(token)
        if t["w"] < TAP_HARD_MIN or t["h"] < TAP_HARD_MIN:
            tier = "hard"
        elif t["w"] < TAP_ADVISORY_MIN or t["h"] < TAP_ADVISORY_MIN:
            tier = "advisory"
        else:
            continue
        buckets.setdefault((tier, t["selector"], t["w"], t["h"]), set()).add(key)


def render_taps(buckets, total_combos, hard, advisory):
    for (tier, selector, w, h), keys in sorted(buckets.items()):
        where = "%d of %d page@width combos" % (len(keys), total_combos)
        if tier == "hard":
            hard.append("tap-targets: %s is %dx%d, below WCAG 2.2 SC 2.5.8 AA %dx%d (%s)"
                        % (selector, w, h, TAP_HARD_MIN, TAP_HARD_MIN, where))
        else:
            advisory.append("tap-targets: %s is %dx%d, below the project target %dx%d (%s)"
                            % (selector, w, h, TAP_ADVISORY_MIN, TAP_ADVISORY_MIN, where))


def colour_failures(key, role, name, entry):
    if entry["state"] == "ok":
        return []
    template = COLOUR_STATE_TEXT[entry["state"]]
    detail = template % entry["raw"] if "%r" in template else template
    return ["[%s] contrast-floor: %s %s %s" % (key, role, name, detail)]


def run_contrast(browser, base, hard, advisory, results):
    for path in PAGES:
        for scheme in SCHEMES:
            ctx = browser.new_context(viewport={"width": CONTRAST_WIDTH,
                                                "height": CONTRAST_HEIGHT},
                                      color_scheme=scheme)
            page = ctx.new_page()
            response = page.goto(base + path, wait_until="load")
            page.wait_for_timeout(1200)
            key = "%s@%s" % (path, scheme)
            sentinel_found = page.query_selector(sentinel_for(path)) is not None
            if not check_page_response(key, response, sentinel_found, path, hard):
                ctx.close()
                continue
            got = page.evaluate(CONTRAST, TEXT_TOKENS)
            ctx.close()
            results[key] = {
                "bgRaw": got["surfaces"]["bg"]["raw"],
                "bgRgb": rgb_text(got["surfaces"]["bg"]["rgb"]),
                "paperRaw": got["surfaces"]["paper"]["raw"],
            }
            for sname, sval in got["surfaces"].items():
                hard.extend(colour_failures(key, "surface", "--" + sname, sval))
            ratios = []
            for token in TEXT_TOKENS:
                entry = got["out"][token]
                failures = colour_failures(key, "token", token, entry)
                hard.extend(failures)
                if failures:
                    continue
                for sname in sorted(entry["ratios"]):
                    value = entry["ratios"][sname]
                    if value is None:
                        continue
                    ratios.append((value, token, sname))
                    if value < CONTRAST_FLOOR:
                        hard.append("[%s] contrast-floor: %s on %s is %s:1, below "
                                    "the %g:1 floor"
                                    % (key, token, sname, round(value, 2), CONTRAST_FLOOR))
            if ratios:
                low = min(ratios)
                results[key]["minRatio"] = round(low[0], 2)
                results[key]["minPair"] = "%s on %s" % (low[1], low[2])
                advisory.append("[%s] contrast-floor: lowest ratio %s:1 (%s on %s), "
                                "floor %g:1"
                                % (key, round(low[0], 2), low[1], low[2], CONTRAST_FLOOR))
    bgs = {s: results.get("%s@%s" % (CATALOG, s), {}).get("bgRgb") for s in SCHEMES}
    if None in bgs.values() or len(set(bgs.values())) != len(SCHEMES):
        hard.append("[contrast-floor] color_scheme did not resolve two distinct "
                    "palettes: %s" % bgs)


def run_images(browser, base, enabled, hard, image_coverage, per_selector):
    want_srcset = enabled("no-broken-srcset")
    want_aspect = enabled("poster-aspect")
    for path in PAGES:
        for label, width, height in IMAGE_VIEWPORTS:
            key = "%s@%s" % (path, label)
            ctx = browser.new_context(viewport={"width": width, "height": height},
                                      color_scheme="light")
            page = ctx.new_page()
            response = page.goto(base + path, wait_until="load")
            page.wait_for_timeout(2000)
            sentinel_found = page.query_selector(sentinel_for(path)) is not None
            if not check_page_response(key, response, sentinel_found, path, hard):
                ctx.close()
                continue
            if want_aspect and path == CATALOG:
                icons = page.locator(".poster-icon")
                if icons.count():
                    icons.first.click()
                    page.wait_for_timeout(600)
            probe = page.evaluate(IMAGES, {"posters": list(POSTER_IMG_SELECTORS)})
            ctx.close()
            stats = image_coverage.setdefault(key, {})
            if want_srcset:
                stats["inspected"] = probe["srcsetInspected"]
                stats["defects"] = len(probe["srcset"])
                for e in probe["srcset"]:
                    hard.append("[%s] no-broken-srcset: %s declares srcset %r: %s"
                                % (key, e["selector"], e["raw"], "; ".join(e["problems"])))
            if want_aspect:
                stats.setdefault("compared", 0)
                stats.setdefault("cropped", 0)
                for e in probe["poster"]:
                    sel = per_selector.setdefault(
                        e["selector"], {"matched": 0, "compared": 0, "cropped": 0})
                    sel["matched"] += 1
                    if e["objectFit"] == CROPPING_OBJECT_FIT:
                        stats["cropped"] += 1
                        sel["cropped"] += 1
                        continue
                    stats["compared"] += 1
                    sel["compared"] += 1
                    if e["delta"] > POSTER_ASPECT_TOLERANCE:
                        hard.append("[%s] poster-aspect: %s renders %s (%s) against a "
                                    "natural %s (%s), off by %g which exceeds the %g "
                                    "tolerance and object-fit is %s"
                                    % (key, e["selector"], e["renderedSize"],
                                       e["rendered"], e["naturalSize"], e["natural"],
                                       e["delta"], POSTER_ASPECT_TOLERANCE,
                                       e["objectFit"]))
    if want_aspect:
        for sel in POSTER_IMG_SELECTORS:
            per_selector.setdefault(sel, {"matched": 0, "compared": 0, "cropped": 0})


def cell(row, name, fmt):
    return fmt % row[name] if name in row else "-"


def tier_legend(executed):
    parts = []
    if "tap-targets" in executed:
        parts.append("tap hard %dx%d (WCAG 2.2 SC 2.5.8 AA)"
                     % (TAP_HARD_MIN, TAP_HARD_MIN))
        parts.append("tap advisory %dx%d (SC 2.5.5 AAA)"
                     % (TAP_ADVISORY_MIN, TAP_ADVISORY_MIN))
    if "contrast-floor" in executed:
        parts.append("contrast floor %g:1" % CONTRAST_FLOOR)
    if "cls-zero" in executed:
        parts.append("cls ceiling %g" % CLS_CEILING)
    if "no-inner-overflow" in executed:
        parts.append("inner overflow at %s"
                     % ", ".join("%dpx" % x for x in INNER_OVERFLOW_WIDTHS))
    if "poster-aspect" in executed:
        parts.append("poster aspect tolerance %g" % POSTER_ASPECT_TOLERANCE)
    if "related-stable" in executed:
        parts.append("related stability %d loads of %s"
                     % (RELATED_STABLE_LOADS, RELATED_STABLE_PATH))
    if any(c in executed for c in DATA_CHECKS):
        parts.append("jsonld ItemList == rendered related cards on %d film page(s)"
                     % len(FILM_PAGES))
    return "tiers: " + " | ".join(parts) if parts else ""


def coverage_cell(executed, owner, value, width):
    if owner not in executed:
        return ("%%%ds" % width) % NOT_PROBED
    return ("%%%dd" % width) % value


def render_image_coverage(executed, image_coverage, per_selector, out):
    if not any(c in executed for c in IMAGE_CHECKS):
        return
    w = out.write
    widths = {"inspected": 11, "defects": 11, "compared": 11, "cropped": 11}
    w("\nCHECK COVERAGE (image checks)\n")
    w("  %-58s %10s %10s %10s %10s\n"
      % ("page@viewport", "inspected", "defects", "compared", "cropped"))
    for key in sorted(image_coverage):
        s = image_coverage[key]
        cells = "".join(
            coverage_cell(executed, owner, s.get(name, 0), widths[name])
            for name, owner in COVERAGE_OWNERS)
        w("  %-58s%s\n" % (key, cells))
    w("  every column reads \"%s\" unless its owning check ran in this invocation:\n"
      % NOT_PROBED)
    for owner in sorted({o for _, o in COVERAGE_OWNERS}):
        names = ", ".join(n for n, o in COVERAGE_OWNERS if o == owner)
        w("    %-18s owns %s\n" % (owner, names))
    w("  a probed 0 means the page genuinely offered nothing; an unprobed column "
      "is not a pass\n")
    w("  inspected = srcset/imagesrcset attributes read; defects = inspected "
      "attributes that failed\n")
    w("  compared = poster images whose rendered ratio was compared against "
      "natural; cropped = poster images skipped because object-fit is %s\n"
      % CROPPING_OBJECT_FIT)
    if "poster-aspect" not in executed:
        return
    w("\n  per-selector poster coverage, summed over every page@viewport probe\n")
    w("  %-28s %8s %9s %8s\n" % ("selector", "matched", "compared", "cropped"))
    for sel in POSTER_IMG_SELECTORS:
        s = per_selector.get(sel, {"matched": 0, "compared": 0, "cropped": 0})
        w("  %-28s %8d %9d %8d%s\n"
          % (sel, s["matched"], s["compared"], s["cropped"],
             "   DEAD SELECTOR" if s["matched"] == 0 else ""))


def render_data_coverage(executed, data_coverage, out):
    w = out.write
    widths = {"ldNames": 11, "cards": 11, "pool": 11}
    w("\nCHECK COVERAGE (related data checks)\n")
    w("  %-58s %10s %10s %10s\n"
      % ("page", "ldNames", "cards", "pool"))
    for key in FILM_PAGES:
        s = data_coverage.get(key)
        if s is None:
            cells = "".join(("%%%ds" % widths[name]) % NOT_PROBED
                            for name, _ in DATA_COVERAGE_OWNERS)
        else:
            cells = "".join(
                coverage_cell(executed, owner, s.get(name, 0), widths[name])
                for name, owner in DATA_COVERAGE_OWNERS)
        w("  %-58s%s\n" % (key, cells))
    w("  every column reads \"%s\" unless its owning check ran in this invocation:\n"
      % NOT_PROBED)
    for owner in sorted({o for _, o in DATA_COVERAGE_OWNERS}):
        names = ", ".join(n for n, o in DATA_COVERAGE_OWNERS if o == owner)
        w("    %-18s owns %s\n" % (owner, names))
    w("  a probed 0 means the page genuinely offered nothing; an unprobed column "
      "is not a pass\n")
    w("  a page that failed to load also reads \"%s\" and raises page-load above\n"
      % NOT_PROBED)
    w("  ldNames = names read from the JSON-LD ItemList; cards = %s nodes in the "
      "hydrated DOM;\n" % JSONLD_RENDER_SELECTOR)
    w("  pool = items still shipped in window.FILM_PAGE.relatedPool\n")
    w("  sample: the %d film pages this harness probes, the same list the layout "
      "sweep uses\n" % len(FILM_PAGES))


def render(results, hard, advisory, executed, coverage, image_coverage,
           per_selector, data_coverage, out):
    w = out.write
    layout = {k: v for k, v in results.items() if "cls" in v}
    contrast = {k: v for k, v in results.items() if "cls" not in v}
    w("checks executed: %s\n" % ", ".join(executed))
    w("(MEASUREMENTS holds live timings and differs between runs;"
      " every section from HARD FAILURES onward is byte-stable)\n")
    if layout:
        w("layout matrix: %d page(s) x width(s) %s\n"
          % (len({k.rsplit("@", 1)[0] for k in layout}),
             ", ".join(str(x) for x in sorted({int(k.rsplit("@", 1)[1]) for k in layout}))))
    if contrast:
        w("contrast matrix: %d page(s) x scheme(s) %s at %dpx\n"
          % (len({k.rsplit("@", 1)[0] for k in contrast}),
             ", ".join(s for s in SCHEMES if any(k.endswith("@" + s) for k in contrast)),
             CONTRAST_WIDTH))
    legend = tier_legend(executed)
    if legend:
        w(legend + "\n")
    render_image_coverage(executed, image_coverage, per_selector, out)
    render_data_coverage(executed, data_coverage, out)

    w("\nMEASUREMENTS\n")
    if layout:
        w("%-58s %9s %5s %7s %6s %5s %5s\n"
          % ("page@width", "cls", "ovf", "inHard", "inAdv", "tapH", "tapA"))
        for key in sorted(layout):
            r = layout[key]
            w("%-58s %9s %5s %7s %6s %5s %5s\n"
              % (key, cell(r, "cls", "%.2e"), cell(r, "overflow", "%d"),
                 cell(r, "innerHard", "%d"), cell(r, "innerAdvisory", "%d"),
                 cell(r, "tapHard", "%d"), cell(r, "tapAdvisory", "%d")))
    if contrast:
        w("\n%-58s %-6s %-18s %7s  %s\n"
          % ("page", "scheme", "resolved --bg", "min", "lowest pair"))
        for key in sorted(contrast):
            r = contrast[key]
            w("%-58s %-6s %-18s %7s  %s\n"
              % (key.rsplit("@", 1)[0], key.rsplit("@", 1)[1], r["bgRgb"],
                 ("%.2f" % r["minRatio"]) if "minRatio" in r else "-",
                 r.get("minPair", "-")))

    w("\nHARD FAILURES: %d\n" % len(hard))
    for line in sorted(set(hard)):
        w("  " + line + "\n")
    if not hard:
        w("  (none)\n")

    w("\nADVISORY: %d\n" % len(advisory))
    for line in sorted(set(advisory)):
        w("  " + line + "\n")
    if not advisory:
        w("  (none)\n")

    w("\nCONDITIONAL STATE VERIFICATION\n")
    for state in sorted(CONDITIONAL_STATES):
        expected = CONDITIONAL_STATES[state]
        got = coverage.get(state, {})
        if not got:
            w("  %-9s %-18s NOT EXERCISED\n" % (state, ", ".join(expected)))
            continue
        for sel in expected:
            ok = sum(1 for pres in got.values() if pres.get(sel, 0) > 0)
            w("  %-9s %-18s present in %d/%d probes\n" % (state, sel, ok, len(got)))

    w("\nSELECTOR COVERAGE\n")
    total = total_probes(coverage)
    if not total:
        w("  not measured (the layout sweep did not run in this invocation)\n")
    for sel in WATCHED:
        n = rendered_count(coverage, sel)
        w("  %-18s rendered in %d/%d probes%s\n"
          % (sel, n, total,
             "" if not total else "   DEAD SELECTOR" if n == 0 else ""))


def dead_selector_failures(coverage):
    if not total_probes(coverage):
        return []
    return ["selector-coverage: %s rendered in 0 probes (dead selector)" % sel
            for sel in WATCHED if rendered_count(coverage, sel) == 0]


def run(base, requested, as_json):
    executed = list(IMPLEMENTED_CHECKS) if requested is None else list(requested)
    enabled = lambda n: n in executed

    hard, advisory, results, coverage, taps = [], [], {}, {}, {}
    image_coverage, per_selector, data_coverage = {}, {}, {}
    total_combos = len(PAGES) * len(WIDTHS)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        if any(enabled(c) for c in LAYOUT_CHECKS):
            run_layout(browser, base, enabled, hard, advisory, results, coverage, taps)
        if any(enabled(c) for c in IMAGE_CHECKS):
            run_images(browser, base, enabled, hard, image_coverage, per_selector)
        if enabled("related-stable"):
            run_related_stable(browser, base, hard)
        if any(enabled(c) for c in DATA_CHECKS):
            run_jsonld_render(browser, base, hard, data_coverage)
        if enabled("contrast-floor"):
            run_contrast(browser, base, hard, advisory, results)
        browser.close()

    if taps:
        render_taps(taps, total_combos, hard, advisory)
    hard += dead_selector_failures(coverage)

    if as_json:
        probes = total_probes(coverage)
        payload = {
            "checksExecuted": executed,
            "measurements": results,
            "hardFailures": sorted(set(hard)),
            "advisory": sorted(set(advisory)),
            "selectorCoverageProbes": probes,
            "selectorCoverage": {
                sel: (rendered_count(coverage, sel) if probes else None)
                for sel in WATCHED
            },
            "imageCoverage": image_coverage,
            "posterCoverageBySelector": per_selector,
            "summary": {
                "hardFailures": len(set(hard)),
                "advisory": len(set(advisory)),
            },
        }
        if any(enabled(c) for c in DATA_CHECKS):
            payload["relatedDataCoverage"] = data_coverage
        print(json.dumps(payload, indent=1, sort_keys=True))
    else:
        render(results, hard, advisory, executed, coverage, image_coverage,
               per_selector, data_coverage, sys.stdout)

    if hard:
        print("ui_audit: %d hard failure(s), %d advisory"
              % (len(set(hard)), len(set(advisory))), file=sys.stderr)
        return 1
    print("ui_audit: all executed invariants hold (%d advisory)" % len(set(advisory)),
          file=sys.stderr)
    return 0


def rendered_count(coverage, sel):
    n = 0
    for per_key in coverage.values():
        for pres in per_key.values():
            if pres.get(sel, 0) > 0:
                n += 1
    return n


def total_probes(coverage):
    return sum(len(per_key) for per_key in coverage.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of the text report")
    ap.add_argument("--only", default="",
                    help="comma-separated subset of implemented check names")
    args = ap.parse_args()

    requested = [n.strip() for n in args.only.split(",") if n.strip()]
    unknown = sorted({n for n in requested if n not in IMPLEMENTED_CHECKS})
    if unknown:
        print("ui_audit: unknown or not-yet-implemented check(s): %s"
              % ", ".join(unknown), file=sys.stderr)
        print("  implemented here: %s" % ", ".join(IMPLEMENTED_CHECKS),
              file=sys.stderr)
        print("  declared by the plan, not implemented yet: %s"
              % ", ".join(DECLARED_NOT_IMPLEMENTED), file=sys.stderr)
        return 2
    if requested and len(set(requested)) != len(requested):
        print("ui_audit: duplicate check name(s) in --only", file=sys.stderr)
        return 2
    return run(args.base, requested or None, args.json)


if __name__ == "__main__":
    sys.exit(main())
