#!/usr/bin/env python3
"""English example renders of the catalogue images (needs Pillow: pip install -r requirements.txt).

    render.py [--font-dir PATH] [--images PATH] [--extracted PATH] [--review PATH] [image ...]
        -> review/english/<image>.png (all todo/done rows by default)

Each example is drawn in the original's own palette and style, read from the
Japanese image: its background colour, the colour of each text row (so vertical
gradients carry over), and its outline colour. The text is the row's `english`
(' / ' forces a line break) in a system font chosen per category, as large as
fits. These are starting points for hand editing (edit.py), not shipped as-is:
the build only uses hand-made and approved images.
"""
import os
import sys
from collections import Counter

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    raise SystemExit("needs Pillow: python3 -m pip install -r requirements.txt") from None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx  # noqa: E402

# The Ubuntu font family (variable versions; on Debian/Ubuntu: fonts-ubuntu)
FONT_DIR = "/usr/share/fonts/truetype/ubuntu/"
# category: (font file, variation name, outline, max text height as a share of the image)
#   outline "ring": 1 px all round, "shadow": 1 px below right, None: no outline
STYLES = {
    "mode": ("Ubuntu-Italic[wdth,wght].ttf", "Condensed Extra Bold Italic", "shadow", 1.0),
    "victory": ("UbuntuSans[wdth,wght].ttf", "Condensed ExtraBold", "ring", 0.75),
    "label": ("UbuntuSans[wdth,wght].ttf", "Condensed SemiBold", "shadow", 0.85),
    "mark": ("UbuntuSans[wdth,wght].ttf", "Condensed ExtraBold", "ring", 0.85),
}


def english_dir():
    return os.path.join(gfx.REVIEW, "english")


def add_options(parser):
    parser.add_argument("--font-dir", default=FONT_DIR, metavar="PATH",
                        help=f"folder with the Ubuntu fonts (default: {FONT_DIR})")


def background(w, h, pix):
    at = lambda x, y: pix[y * w + x]
    border = [at(x, y) for x in range(w) for y in (0, h - 1)] + [at(x, y) for y in range(h) for x in (0, w - 1)]
    return Counter(border).most_common(1)[0][0]


def style_of(pieces):
    """Style shared by same-sized images of a category: (per-row text colour, default text
    colour, outline colour or None). pieces: [(w, h, pix)]; rows are voted on across them."""
    inner, edge, rows = Counter(), Counter(), {}
    for w, h, pix in pieces:
        bg = background(w, h, pix)
        for y in range(h):
            for x in range(w):
                v = pix[y * w + x]
                if v == bg:
                    continue
                near = [pix[(y + dy) * w + x + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                        if 0 <= x + dx < w and 0 <= y + dy < h]
                if bg in near:
                    edge[v] += 1
                else:
                    inner[v] += 1
                    rows.setdefault(y, Counter())[v] += 1
    fill = inner.most_common(1)[0][0] if inner else (edge.most_common(1)[0][0] if edge else 1)
    outline = edge.most_common(1)[0][0] if edge else None
    per_row = {y: c.most_common(1)[0][0] for y, c in rows.items()}
    return per_row, fill, (None if outline == fill else outline)


def category_style(r):
    group = [x for x in gfx.rows() if x["category"] == r["category"] and (x["w"], x["h"]) == (r["w"], r["h"])
             and x["palette"] == r["palette"]]
    return style_of([gfx.piece(x)[:3] for x in group])


def fit_font(path, variation, lines, w, h):
    for size in range(64, 5, -1):
        f = ImageFont.truetype(path, size)
        f.set_variation_by_name(variation)
        boxes = [f.getbbox(t) for t in lines]
        tw = max(b[2] - b[0] for b in boxes)
        lh = max(b[3] - b[1] for b in boxes)
        if tw <= w and lh * len(lines) + (len(lines) - 1) <= h:
            return f, boxes, lh
    raise SystemExit(f"text does not fit: {lines}")


def render(r):
    w, h, pix, pal = gfx.piece(r)
    font_file, variation, kind, share = STYLES.get(r["category"], STYLES["mark"])
    bg = background(w, h, pix)
    per_row, fill, outline = category_style(r)
    if not kind:
        outline = None
    pad = 1 if outline is not None else 0
    lines = [t.strip() for t in r["english"].split(" / ")]
    f, boxes, lh = fit_font(os.path.join(FONT_DIR, font_file), variation, lines,
                            w - 2 * pad - 1, int(h * share) - 2 * pad)
    # draw the text as a 1-bit mask, centred (mode names: left, like the originals)
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    total = lh * len(lines) + (len(lines) - 1)
    y = (h - total) // 2
    for t, b in zip(lines, boxes):
        tw = b[2] - b[0]
        x = pad if r["category"] == "mode" else (w - tw) // 2
        d.text((x - b[0], y - b[1]), t, font=f, fill=255)
        y += lh + 1
    mask = mask.point(lambda v: 255 if v >= 110 else 0)
    # text colours: the original's row colours, stretched over the new text's rows
    src_rows = sorted(per_row)
    new_rows = [yy for yy in range(h) if any(mask.getpixel((xx, yy)) for xx in range(w))]
    out = [bg] * (w * h)
    if outline is not None:
        if kind == "shadow":
            ring = Image.new("L", (w, h), 0)
            ring.paste(mask, (1, 1))
        else:
            ring = mask.filter(ImageFilter.MaxFilter(3))
        for yy in range(h):
            for xx in range(w):
                if ring.getpixel((xx, yy)):
                    out[yy * w + xx] = outline
    for yy in new_rows:
        if src_rows:
            k = (yy - new_rows[0]) * (len(src_rows) - 1) // max(1, new_rows[-1] - new_rows[0])
            colour = per_row[src_rows[k]]
        else:
            colour = fill
        for xx in range(w):
            if mask.getpixel((xx, yy)):
                out[yy * w + xx] = colour
    gfx.write_png(os.path.join(english_dir(), f"{r['image']}.png"), w, h, bytes(out), pal)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="English example renders of the catalogue images.")
    ap.add_argument("names", nargs="*", metavar="image", help="images to render (default: all todo/done)")
    add_options(ap)
    gfx.add_options(ap)
    args = ap.parse_args(argv)
    global FONT_DIR
    FONT_DIR = args.font_dir
    gfx.configure(args.images, args.extracted, args.review)
    names = args.names
    table = [r for r in gfx.rows() if r["status"] != "keep" and r["english"]]
    if names:
        table = [r for r in table if r["image"] in names]
    for r in table:
        render(r)
    print(f"{len(table)} English examples -> {english_dir()}/")


if __name__ == "__main__":
    main()
