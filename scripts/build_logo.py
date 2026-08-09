"""Generate the app's logo and favicon assets from images/Logo.png.

The source is a wide 3:2 render on a black field. Three things have to happen before it
works as a round mark:

  1. Crop to the artwork. The glow fades into black, so the subject is found by
     thresholding brightness rather than trusting the canvas bounds.
  2. Pad to a square around the subject's centre, so the round mask does not slice the
     nose and rear wing off a car that is much wider than it is tall.
  3. Mask to a circle with a transparent surround, so the mark composites cleanly on any
     panel colour instead of carrying a black box with it.

Run:  uv run python -m scripts.build_logo
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "images" / "Logo.png"
PUBLIC = ROOT / "web" / "public"
APP = ROOT / "web" / "app"

# Pixels above this luminance count as artwork rather than background glow falloff.
CONTENT_THRESHOLD = 26
# Breathing room around the subject inside the circle, as a fraction of its longest side.
# The subject is far wider than it is tall, so a square crop around it already leaves
# generous vertical margin; this only needs to keep the nose and rear wing off the rim.
PADDING = 0.04
# The disc colour, matching the app's --color-void so the frame reads as part of the page.
VOID = (8, 9, 10)


def subject_box(image: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of the artwork, found by luminance."""
    grey = image.convert("L")
    mask = grey.point(lambda v: 255 if v > CONTENT_THRESHOLD else 0)
    box = mask.getbbox()
    return box if box else (0, 0, image.width, image.height)


def square_around(box: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Smallest square centred on the subject, clamped to the canvas."""
    left, top, right, bottom = box
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    side = max(right - left, bottom - top) * (1 + PADDING * 2)

    half = side / 2
    x0 = int(round(cx - half))
    y0 = int(round(cy - half))
    return x0, y0, int(round(x0 + side)), int(round(y0 + side))


def circular(image: Image.Image, size: int) -> Image.Image:
    """Resize to `size` and mask to a circle with an antialiased edge."""
    resized = image.resize((size, size), Image.LANCZOS).convert("RGBA")

    # Draw the mask at 4x and downsample: PIL's ellipse has no antialiasing of its own,
    # and a hard-edged circle looks obviously jagged at favicon sizes.
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS).filter(ImageFilter.SMOOTH)

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(resized, (0, 0), mask)
    return out


def main() -> int:
    if not SOURCE.exists():
        print(f"Source not found: {SOURCE}")
        return 1

    source = Image.open(SOURCE).convert("RGBA")
    box = subject_box(source)
    x0, y0, x1, y1 = square_around(box, source.size)

    # Compose onto an opaque square first, so a crop reaching past the canvas edge
    # extends the background instead of failing.
    #
    # The source is pasted USING ITS OWN ALPHA AS THE MASK. Its background is transparent
    # rather than black, and a plain paste copies that transparency straight through the
    # backing colour, leaving the artwork floating on a hole.
    side = x1 - x0
    canvas = Image.new("RGBA", (side, side), VOID + (255,))
    canvas.paste(source, (-x0, -y0), source)

    PUBLIC.mkdir(parents=True, exist_ok=True)
    outputs = {
        PUBLIC / "logo.png": 512,      # nav and UI
        APP / "icon.png": 256,         # Next.js file-convention favicon
        APP / "apple-icon.png": 180,   # iOS home screen
    }
    for path, size in outputs.items():
        circular(canvas, size).save(path, "PNG", optimize=True)
        print(f"wrote {path.relative_to(ROOT)} ({size}x{size})")

    # A leftover favicon.ico would take precedence over icon.png in Next.js.
    stale = APP / "favicon.ico"
    if stale.exists():
        stale.unlink()
        print(f"removed {stale.relative_to(ROOT)} (superseded by icon.png)")

    print(f"\nsubject box {box} -> square crop {(x0, y0, x1, y1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
