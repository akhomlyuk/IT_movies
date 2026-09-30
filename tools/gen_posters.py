import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import POSTER_MAX_HEIGHT, POSTER_VARIANT_WIDTHS, ROOT, load_catalog, variant_path

from PIL import Image

HEAVY_BYTES = 100_000
TARGET_BYTES = 50_000
VARIANT_QUALITY = 78
SQUEEZE_QUALITIES = (80, 72, 64, 56, 48)


def scaled_height(w, h, width):
    return max(1, round(h * width / w))


def squeeze(src):
    """Re-encode a heavy original in place, or leave it ALONE.

    The first version of this wrote every attempt straight back to `src` and
    then raised if the last one still missed TARGET_BYTES. That destroyed the
    source before it knew whether it could succeed: a 1920x2843 poster went
    718 770 B -> 276 408 B at quality 48 and the run still failed, leaving a
    generational-lossy file behind and no way back, because the original was
    never committed.

    So the encode now goes to a temporary file and is moved into place ONLY when
    it reaches the target. A source that cannot be squeezed is left
    byte-identical and reported, because a size policy is not a correctness
    property: the ladder is what the site serves, and losing the master to
    enforce a byte count on an asset the ladder never needs at full size is the
    wrong trade in both directions.
    """
    with Image.open(src) as im:
        im.load()
        fd, tmp = tempfile.mkstemp(suffix=".webp", dir=str(src.parent))
        os.close(fd)
        tmp = Path(tmp)
        try:
            for quality in SQUEEZE_QUALITIES:
                im.save(tmp, "WEBP", quality=quality, method=6)
                if tmp.stat().st_size < TARGET_BYTES:
                    os.replace(tmp, src)
                    return True
            return False
        finally:
            if tmp.exists():
                tmp.unlink()


def normalise_height(src):
    """Bring a master down to lib.POSTER_MAX_HEIGHT, proportions kept.

    This is the partner's own manual practice, run for them: they reduced every
    master to 600px by hand with the proportions kept, and 85 of 86 measured
    exactly 600 before this existed. A downscale from the pixels AS PLACED, so
    the master is resampled once, and the ladder is then cut from the rescaled
    file.

    It also REPLACES the master, which is destructive if a source ever arrives
    larger than 600px -- and that is the one thing to know before running this.
    Measured 2026-09-30: with masters at 338-464px wide, the hero (320px box) and
    the lightbox (400px box) are both sharp at DPR 1 and both upscale from DPR
    1.5 on, and the ceiling is the source material, not the ladder -- a wider
    rung cut from a 405px master is an upsample with no extra detail. The partner
    confirmed no larger source exists. **So if a larger one ever does, raise
    lib.POSTER_MAX_HEIGHT FIRST, or this will quietly cut it.** The report line
    below is the warning, and it names the before/after so a rescale is never
    silent.
    """
    with Image.open(src) as im:
        im.load()
        w, h = im.size
        if h <= POSTER_MAX_HEIGHT:
            return None
        target = (max(1, round(w * POSTER_MAX_HEIGHT / h)), POSTER_MAX_HEIGHT)
        fd, tmp = tempfile.mkstemp(suffix=".webp", dir=str(src.parent))
        os.close(fd)
        tmp = Path(tmp)
        try:
            im.resize(target, Image.LANCZOS).save(tmp, "WEBP", quality=90, method=6)
            os.replace(tmp, src)
        finally:
            if tmp.exists():
                tmp.unlink()
    return (w, h), target


def main():
    catalog = load_catalog()
    posters = sorted({i["poster"].lstrip("/") for i in catalog if i.get("poster")})
    created = 0
    recompressed = 0
    rescaled = []
    unreached = []
    for poster in posters:
        src = ROOT / poster
        if not src.exists():
            raise SystemExit(f"missing poster file: {poster}")
        was = normalise_height(src)
        if was:
            rescaled.append((poster,) + was)
        if src.stat().st_size >= HEAVY_BYTES:
            if squeeze(src):
                recompressed += 1
            else:
                unreached.append((poster, src.stat().st_size))
        for width in POSTER_VARIANT_WIDTHS:
            dst = variant_path(poster, width)
            if dst.exists():
                continue
            with Image.open(src) as im:
                w, h = im.size
                im.resize((width, scaled_height(w, h, width)), Image.LANCZOS).save(
                    dst, "WEBP", quality=VARIANT_QUALITY, method=6
                )
            created += 1
    print(
        f"posters: {len(posters)} total, {created} variants created, "
        f"{recompressed} originals recompressed"
    )
    if rescaled:
        print(
            f"rescaled {len(rescaled)} master(s) down to {POSTER_MAX_HEIGHT}px high, "
            f"proportions kept (nothing above the ladder's top rung is ever "
            f"fetched, so the extra pixels had no consumer):"
        )
        for poster, (fw, fh), (tw, th) in rescaled:
            print(f"  {poster}  {fw}x{fh} -> {tw}x{th}")
    if unreached:
        print(
            f"WARNING: {len(unreached)} original(s) are over {HEAVY_BYTES} B and could "
            f"not be squeezed under {TARGET_BYTES} B at any quality in "
            f"{SQUEEZE_QUALITIES}. They are left UNCHANGED -- the previous version of "
            f"this tool overwrote them first and then failed, which destroyed the "
            f"source. Nothing above the ladder's top rung is ever fetched, so this is "
            f"repo weight rather than a served cost, but it is your call:"
        )
        for poster, size in unreached:
            with Image.open(ROOT / poster) as im:
                dims = f"{im.size[0]}x{im.size[1]}"
            print(f"  {poster}  {size} B  {dims}")


if __name__ == "__main__":
    main()
