import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import ROOT, load_catalog

from PIL import Image

VARIANT_W = 400
VARIANT_SUFFIX = "_400"
HEAVY_BYTES = 100_000
TARGET_BYTES = 50_000
VARIANT_QUALITY = 78


def variant_path(poster):
    return ROOT / (poster[: -len(".webp")] + f"{VARIANT_SUFFIX}.webp")


def main():
    catalog = load_catalog()
    posters = sorted({i["poster"].lstrip("/") for i in catalog if i.get("poster")})
    created = 0
    recompressed = 0
    for poster in posters:
        src = ROOT / poster
        if not src.exists():
            raise SystemExit(f"missing poster file: {poster}")
        if src.stat().st_size >= HEAVY_BYTES:
            with Image.open(src) as im:
                im.load()
                for quality in (80, 72, 64, 56, 48):
                    im.save(src, "WEBP", quality=quality, method=6)
                    if src.stat().st_size < TARGET_BYTES:
                        break
                else:
                    raise SystemExit(
                        f"cannot squeeze {poster} under {TARGET_BYTES} bytes"
                    )
            recompressed += 1
        dst = variant_path(poster)
        if dst.exists():
            continue
        with Image.open(src) as im:
            w, h = im.size
            vh = max(1, round(h * VARIANT_W / w))
            im.resize((VARIANT_W, vh), Image.LANCZOS).save(
                dst, "WEBP", quality=VARIANT_QUALITY, method=6
            )
        created += 1
    print(
        f"posters: {len(posters)} total, {created} variants created, "
        f"{recompressed} originals recompressed"
    )


if __name__ == "__main__":
    main()
