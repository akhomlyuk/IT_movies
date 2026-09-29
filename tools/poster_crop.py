#!/usr/bin/env python3
"""Poster crop measurement: two quantities, one of which is the one that costs area.

`object-fit: cover` into a fixed box discards image AREA. The project has been
tuning a number called "crop" that is not that area, so this module names both
quantities, keeps them apart, and bounds the one that is about area:

    PROXY          = |source_w / source_h - 2/3|
    DISCARDED_AREA = 1 - (bw / scale) * (bh / scale) / (sw * sh)

with `scale = max(bw / sw, bh / sh)`. Both are arithmetic on the real file
dimensions, so no browser is involved: the previous "harness" was a Playwright
probe over 4 posters, which is how a ceiling 3.1x above its own worst sample
survived a stage.

They are not interchangeable and they do not rank alike. A source wider than 2:3
loses `1 - (2/3) / ratio` of its area; a taller one loses `1 - 1.5 * ratio`, so a
tall narrow poster (theperipheral, 338x600) discards MORE area than a wide one
(hacker, 464x600) while ranking LOWER on the proxy. A bound fitted on the proxy
therefore under-bounds exactly the worst-shaped posters.

THE BOX. The arithmetic needs a box, and the one the related card renders into was
measured on a live film page on 2026-09-28 with Playwright at
device_scale_factor 1: `getBoundingClientRect()` of `.rc-poster` reads 96x144 at
1280 and 84x126 at 375 (`css/style.css` sets `.rc-poster` to 96x144 and the
<=767px block overrides it to 84x126). Both are exactly 2:3, which is the premise.
Discarded area is a function of the box's aspect ratio alone, so the two boxes
give identical figures for all 154 posters; both are measured by the tests below
rather than that claim being asserted here.

The hero is a different box and is never cropped: `.film-poster img` is
`height: auto` at a fixed width, so the frame takes the fetched file's own ratio
and its computed `object-fit` is `fill`. Measured on the same page, 240x355.797 at
375 and 320x474.391 at 1280 against the 400x593 rung (0.674536) -- the box ratio
IS the file ratio, so the hero's discarded area is 0 at every width and every
rung.

THE BOUND. `DISCARDED_AREA_CEILING = 0.02` is a discarded-area fraction, and the
name says so; a future reader must not mistake it for the old `POSTER_CROP_CEILING`,
which was the proxy. 0.02 is not fitted to a sample: it is the one poster-fidelity
standard this project has ever declared, and it is applied here to the quantity
that costs the reader image. That is a deliberate tightening rather than a
translation -- 0.02 on the proxy admits a discarded area of up to 0.0291, so this
bound names 8 posters the old standard would have passed, and the exact area
equivalent of the old standard, 0.02 / (2/3 + 0.02) = 0.02912, fails 46 instead of
54. The library does NOT meet 0.02 and that is the finding; 0.16 on the proxy
permitted a discarded area of 0.1935, so any bound near the current worst would
have been the same leniency under a new name.

Usage:

    python tools/poster_crop.py                  # report over the library
    python tools/poster_crop.py --box 84 126     # a different box
    python tools/poster_crop.py --dir <folder>   # any folder of webp files
    python tools/poster_crop.py --json           # machine-readable

Exit 0 when every poster is within the ceiling, 1 when at least one is not, 2 on a
usage error. `verify.py` imports this module instead of re-deriving the
arithmetic, so the gate's number and the report's number cannot drift apart.
"""
import argparse
import json
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import POSTER_VARIANT_WIDTHS, ROOT, load_catalog, variant_path  # noqa: E402

from PIL import Image  # noqa: E402

POSTER_ASPECT = 2 / 3
DISCARDED_AREA_CEILING = 0.02
PROXY_ASPECT_STANDARD = 0.02
REPORT_TOLERANCE = 0.02
RELATED_BOX_DESKTOP = (120, 180)
# There is no separate mobile box. These two constants said 96x144 and 84x126
# while the rendered card measured 104x156 at every width, because the xs
# override that produced the small box was deleted on 2026-09-29. The related
# card renders ONE box, now 120x180 after the rail change moved the poster above
# the text.
RELATED_BOX_MOBILE = RELATED_BOX_DESKTOP
HERO_BOX_WIDTH_MOBILE = 240
HERO_BOX_WIDTH_DESKTOP = 320
WORST_N = 5

Record = namedtuple("Record", "poster width height proxy discarded")


def poster_files(root=ROOT, directory=None):
    if directory is not None:
        folder = Path(directory)
        return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix == ".webp")
    catalog = load_catalog(root)
    relative = sorted({i["poster"].lstrip("/") for i in catalog if i.get("poster")})
    missing = [p for p in relative if not (root / p).exists()]
    if missing:
        raise SystemExit(f"poster file missing: {missing[0]}")
    return [root / p for p in relative]


def poster_size(path):
    with Image.open(path) as im:
        return im.size


def aspect_deviation(width, height):
    return abs(width / height - POSTER_ASPECT)


def cover_scale(source_w, source_h, box_w, box_h):
    return max(box_w / source_w, box_h / source_h)


def discarded_area(source_w, source_h, box_w, box_h):
    scale = cover_scale(source_w, source_h, box_w, box_h)
    return 1 - (box_w / scale) * (box_h / scale) / (source_w * source_h)


def is_two_by_three(box):
    return box[0] * 3 == box[1] * 2


def measure(path, box):
    width, height = poster_size(path)
    return Record(
        poster=Path(path).name,
        width=width,
        height=height,
        proxy=aspect_deviation(width, height),
        discarded=discarded_area(width, height, *box),
    )


def measure_library(root=ROOT, box=RELATED_BOX_DESKTOP, directory=None):
    return [measure(p, box) for p in poster_files(root, directory)]


def quantile(values, q):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def median(values):
    return quantile(values, 0.5)


def describe(values):
    return {
        "n": len(values),
        "exact": sum(1 for v in values if v == 0.0),
        "loses": sum(1 for v in values if v > 0.0),
        "over_standard": sum(1 for v in values if v > REPORT_TOLERANCE),
        "median": median(values),
        "p90": quantile(values, 0.9),
        "max": max(values) if values else 0.0,
    }


def over_ceiling(records, ceiling=DISCARDED_AREA_CEILING):
    return sorted((r for r in records if r.discarded > ceiling),
                  key=lambda r: (-r.discarded, r.poster))


def worst(records, field, n=WORST_N):
    return sorted(records, key=lambda r: (-getattr(r, field), r.poster))[:n]


def variant_records(root=ROOT, records=None, box=RELATED_BOX_DESKTOP):
    if records is None:
        records = measure_library(root, box)
    out = []
    for record in records:
        relative = f"static/posters/{record.poster}"
        for width in POSTER_VARIANT_WIDTHS:
            path = variant_path(relative, width)
            if not path.exists():
                continue
            vw, vh = poster_size(path)
            out.append({
                "poster": record.poster,
                "rung": width,
                "width": vw,
                "height": vh,
                "discarded": discarded_area(vw, vh, *box),
                "source_discarded": record.discarded,
            })
    return out


def divergent(records, n=WORST_N):
    """How the two rankings of the worst n differ, as a set and as an order.

    Both halves matter and they fail differently. A poster missing from one list
    entirely is under-bounded by a bound fitted on the other quantity; a poster
    that is present in both but at a worse rank is the case this stage is about,
    because a proxy-fitted ceiling would send someone to fix the wrong file
    first.
    """
    n = min(n, len(records))
    by_proxy = [r.poster for r in worst(records, "proxy", n)]
    by_area = [r.poster for r in worst(records, "discarded", n)]
    only_one = sorted(set(by_proxy) ^ set(by_area))
    reordered = []
    for index, poster in enumerate(by_area):
        if by_proxy[index] != poster:
            reordered.append((poster, by_proxy.index(poster) + 1, index + 1))
    return only_one, reordered, n


def _row(label, stats):
    return (f"{label:<26}{stats['exact']:>6}{stats['loses']:>7}"
            f"{stats['over_standard']:>7}{stats['median']:>10.5f}"
            f"{stats['p90']:>10.5f}{stats['max']:>10.5f}")


def report(records, ceiling=DISCARDED_AREA_CEILING, box=RELATED_BOX_DESKTOP, root=ROOT):
    n = min(WORST_N, len(records))
    p_stats = describe([r.proxy for r in records])
    d_stats = describe([r.discarded for r in records])
    lines = [
        f"posters measured: {len(records)} from real file dimensions, no browser",
        f"box: {box[0]}x{box[1]} = {box[0] / box[1]:.6f}, target {POSTER_ASPECT:.6f},"
        f" exactly 2:3: {is_two_by_three(box)}",
        f"hero: {HERO_BOX_WIDTH_MOBILE}px/{HERO_BOX_WIDTH_DESKTOP}px wide at height auto,"
        f" so its box takes the file's own ratio and its discarded area is 0",
        "",
        f"{'quantity':<26}{'2:3':>6}{'loses':>7}{'>' + format(REPORT_TOLERANCE, 'g'):>7}"
        f"{'median':>10}{'p90':>10}{'max':>10}",
        _row("PROXY (|w/h - 2/3|)", p_stats),
        _row("DISCARDED AREA", d_stats),
        "",
        f"worst {n} by PROXY:",
    ]
    for r in worst(records, "proxy", n):
        lines.append(f"  {r.poster:<46} {r.width:>4}x{r.height:<4} {r.proxy:.5f}")
    lines.append(f"worst {n} by DISCARDED AREA:")
    for r in worst(records, "discarded", n):
        lines.append(f"  {r.poster:<46} {r.width:>4}x{r.height:<4} {r.discarded:.5f}")
    diverged, reordered, n = divergent(records, n)
    lines.append("")
    if diverged:
        lines.append(
            f"the two rankings disagree on {len(diverged)} of their {n} as sets:"
            f" {', '.join(diverged)} -- a bound fitted on the proxy under-bounds these"
        )
    else:
        lines.append(f"the two rankings name the same {n} posters")
    if reordered:
        for poster, proxy_rank, area_rank in reordered:
            lines.append(
                f"  {poster}: rank {proxy_rank} by PROXY, rank {area_rank} by"
                f" DISCARDED AREA -- the proxy ranks it {'worse' if proxy_rank > area_rank else 'better'}"
                f" than it deserves"
            )
    else:
        lines.append(f"  and agree on the order of all {n} of them")
    variants = variant_records(root, records, box)
    if variants:
        top = max(variants, key=lambda v: v["discarded"])
        spread = max(v["discarded"] - v["source_discarded"] for v in variants)
        lines += [
            "",
            f"ladder: {len(variants)} rungs, worst discarded {top['discarded']:.5f}"
            f" ({top['poster']} _{top['rung']} = {top['width']}x{top['height']}),"
            f" largest rung-vs-source delta {spread:+.5f}",
        ]
    failing = over_ceiling(records, ceiling)
    lines += [
        "",
        f"bound: DISCARDED_AREA_CEILING = {ceiling}, a discarded-area fraction"
        f" (not the proxy)",
        f"library position: {len(failing)} of {len(records)} posters exceed it"
        f" ({len(failing) * 100.0 / len(records):.1f}%)",
    ]
    if failing:
        lines += [
            f"worst offender: {failing[0].poster} {failing[0].width}x{failing[0].height}"
            f" discards {failing[0].discarded:.5f} of its area",
            "every offender, worst first:",
        ]
        for r in failing:
            lines.append(
                f"  {r.poster:<46} {r.width:>4}x{r.height:<4}"
                f" discarded {r.discarded:.5f}  proxy {r.proxy:.5f}"
            )
    return "\n".join(lines), failing


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure poster crop across the library.")
    parser.add_argument("--dir", dest="directory", help="folder of webp files to measure")
    parser.add_argument("--box", nargs=2, type=int, metavar=("W", "H"),
                        help="cover-fit box, default 96 144 (the related card)")
    parser.add_argument("--ceiling", type=float, default=DISCARDED_AREA_CEILING,
                        help=f"discarded-area bound, default {DISCARDED_AREA_CEILING}")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--quiet", action="store_true", help="summary line and offenders only")
    args = parser.parse_args(argv)
    box = tuple(args.box) if args.box else RELATED_BOX_DESKTOP
    if min(box) <= 0:
        print("poster_crop: the box must have positive dimensions", file=sys.stderr)
        return 2
    try:
        records = measure_library(ROOT, box, args.directory)
    except (OSError, ValueError) as exc:
        print(f"poster_crop: {exc}", file=sys.stderr)
        return 2
    if not records:
        print("poster_crop: no posters found", file=sys.stderr)
        return 2
    failing = over_ceiling(records, args.ceiling)
    if args.json:
        print(json.dumps({
            "box": list(box),
            "ceiling": args.ceiling,
            "n": len(records),
            "proxy": describe([r.proxy for r in records]),
            "discarded": describe([r.discarded for r in records]),
            "worst_by_proxy": [r._asdict() for r in worst(records, "proxy")],
            "worst_by_discarded": [r._asdict() for r in worst(records, "discarded")],
            "over_ceiling": [r._asdict() for r in failing],
        }, indent=2))
    elif args.quiet:
        print(f"poster_crop: {len(failing)} of {len(records)} posters discard more than"
              f" {args.ceiling} of their area into a {box[0]}x{box[1]} box")
        for r in failing:
            print(f"  {r.poster} {r.width}x{r.height} discarded {r.discarded:.5f}")
    else:
        text, failing = report(records, args.ceiling, box)
        print(text)
    if failing:
        print(f"\nFAIL: {len(failing)} poster(s) exceed DISCARDED_AREA_CEILING {args.ceiling};"
              f" worst {failing[0].poster} at {failing[0].discarded:.5f}")
        return 1
    print(f"\nPASS: every poster discards at most {args.ceiling} of its area")
    return 0


if __name__ == "__main__":
    sys.exit(main())
