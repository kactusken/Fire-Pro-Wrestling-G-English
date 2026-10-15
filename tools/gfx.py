#!/usr/bin/env python3
"""Game images with Japanese text: catalogue, export and import (no dependencies).

images/graphics.csv lists every image (a rectangle of a source texture):
  image      name used for every file of this image
  source     where it lives (SOURCES below)
  x,y,w,h    the rectangle in the source, in pixels of the image's colour depth
  palette    clut:ROW:X   16 colours at row ROW, halfword X of a sheet source
             ramp:RRGGBB:RRGGBB   made-up palette (dark..light, last colour = second value)
             colors:RRGGBB,...    made-up palette, 16 colours (the first is transparent)
             gray         made-up grey ramp (the real palette isn't known yet)
             (empty)      the TIM's own palette
  category, japanese, english, notes
  status     todo (needs an English image) / done (approved) / keep (stays Japanese)

    python3 tools/gfx.py export [--extracted PATH] [--images PATH] [--review PATH]
        -> review/japanese/<image>.png (+ review/full/ sources)

At build time (apply), images/handmade/<image>.png (work in progress) or else
images/approved/<image>.png replaces the image in every entry of its source.
"""
import csv
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pngread  # noqa: E402
from lzss import compress, decompress  # noqa: E402
from tim import Tim  # noqa: E402

ROOT = paths.ROOT


def configure(images=None, extracted=None, review=None):
    """Set the folders the image tools use (None keeps the current one)."""
    global CSV, HANDMADE, APPROVED, FPG, REVIEW, JAPANESE
    if images:
        CSV = os.path.join(images, "graphics.csv")
        HANDMADE = os.path.join(images, "handmade")
        APPROVED = os.path.join(images, "approved")
    if extracted:
        FPG = os.path.join(extracted, "fpg")
    if review:
        REVIEW = review
        JAPANESE = os.path.join(review, "japanese")


def add_options(parser):
    """The folder options shared by gfx.py, edit.py and render.py."""
    paths.add(parser, "--images", paths.IMAGES, "image catalogue folder (graphics.csv, handmade/, approved/)")
    paths.add(parser, "--extracted", paths.EXTRACTED, "tools/extract.py output")
    paths.add(parser, "--review", paths.REVIEW, "folder for exported and preview images")


configure(paths.repo(paths.IMAGES), paths.repo(paths.EXTRACTED), paths.repo(paths.REVIEW))

# kind "sheet": a 16bpp TIM that is really a VRAM area of 4bpp textures and CLUTs
# kind "tim":   an ordinary TIM (4 or 8bpp) with its own palette; offset = where its
#               compressed data starts in the raw entry
SOURCES = {
    "sheet277": {"entries": ["277"], "kind": "sheet"},
    "victory": {"entries": [str(e) for e in range(279, 286)], "kind": "sheet"},  # same captions in all 7
    "tim093": {"entries": ["093"], "kind": "tim", "offset": 0},
    "tim012": {"entries": ["012"], "kind": "tim", "offset": 9518, "no_import": True},
    "tim018": {"entries": ["018"], "kind": "tim", "offset": 0},
}


def rows():
    with open(CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(table):
    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)


def row(name):
    r = next((r for r in rows() if r["image"] == name), None)
    if r is None:
        raise SystemExit(f"unknown image {name!r} (see images/graphics.csv)")
    return r


def c15(v):
    return ((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31)


def to15(rgb):
    r, g, b = (c * 31 // 255 for c in rgb)
    return 0x8000 | r | g << 5 | b << 10


def _load(entry_path, src):
    raw = open(entry_path, "rb").read()
    data = decompress(raw[src.get("offset", 0):])
    return data, Tim(data, 0)


def _pixels(t, kind):
    """The TIM's pixels as rows of colour indices (4bpp for sheets)."""
    stride = t.vram[2] * 2
    lines = [t.pixels_raw[y * stride:(y + 1) * stride] for y in range(t.height)]
    if kind == "sheet" or t.bpp == 4:
        return [[n for b in line for n in (b & 15, b >> 4)] for line in lines]
    return [list(line) for line in lines]


def _palette(r, t):
    spec = r["palette"]
    if not spec:
        return list(t.cluts[0])
    kind, *a = spec.split(":")
    if kind == "colors":
        return [0] + [to15(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))) for h in a[0].split(",")[1:]]
    if kind == "clut":
        y, x = int(a[0]), int(a[1])
        return list(struct.unpack_from("<16H", t.pixels_raw, y * t.vram[2] * 2 + x * 2))
    if kind == "gray":
        a = ["000000", "ffffff"]
    dark, light = (tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for h in a)
    return [0] + [to15(tuple(d + (l - d) * k // 15 for d, l in zip(dark, light))) for k in range(1, 16)]


def piece(r, fpg=None):
    """(width, height, indices as bytes, palette as PS1 colours) of a catalogue row."""
    src = SOURCES[r["source"]]
    _, t = _load(os.path.join(fpg or FPG, f"{src['entries'][0]}.bin"), src)
    x, y, w, h = (int(r[k]) for k in "xywh")
    px = _pixels(t, src["kind"])
    return w, h, bytes(n for line in px[y:y + h] for n in line[x:x + w]), _palette(r, t)


def bpp(r):
    src = SOURCES[r["source"]]
    if src["kind"] == "sheet":
        return 4
    _, t = _load(os.path.join(FPG, f"{src['entries'][0]}.bin"), src)
    return t.bpp


def write_png(path, width, height, indices, palette15):
    """Indexed PNG with the PS1 palette; colour 0x0000 is transparent."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += indices[y * width:(y + 1) * width]
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
    png += chunk(b"PLTE", b"".join(bytes(c15(v)) for v in palette15))
    png += chunk(b"tRNS", bytes(0 if v == 0 else 255 for v in palette15))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(png)


def to_indices(name, png, width, height, palette15):
    """An edited PNG as indices of the game palette: an indexed PNG whose palette
    matches is taken index for index, anything else is snapped colour by colour
    (alpha < 128 -> the palette's transparent entry)."""
    if (png.width, png.height) != (width, height):
        raise SystemExit(f"{name}.png is {png.width}x{png.height}; it must stay {width}x{height}")
    game = [c15(v) for v in palette15]
    if png.indexed and png.palette[:len(game)] == game[:len(png.palette)]:
        out = [i for line in png.rows for i in line]
        if max(out) >= len(game):
            raise SystemExit(f"{name}.png uses palette entries past the game's {len(game)}")
        return out
    # transparent = the palette's colour 0x0000 (index 0 for most images, 15 for the
    # select labels); every other entry can be snapped to
    clear = next((i for i, v in enumerate(palette15) if v == 0), 0)
    opaque = [(i, game[i]) for i, v in enumerate(palette15) if v]
    cache = {}

    def nearest(px):
        if px[3] < 128:
            return clear
        if px not in cache:
            cache[px] = min(opaque, key=lambda e: sum((a - b) ** 2 for a, b in zip(e[1], px)))[0]
        return cache[px]

    out = []
    for line in png.rows:
        for px in line:
            if png.indexed:
                a = png.alpha[px] if png.alpha and px < len(png.alpha) else 255
                px = png.palette[px] + (a,)
            out.append(nearest(px))
    return out


def english_file(name):
    """The PNG the build uses for this image: hand-made (in progress) beats approved."""
    for d in (HANDMADE, APPROVED):
        p = os.path.join(d, f"{name}.png")
        if os.path.exists(p):
            return p
    return None


def apply(unpacked, write=None):
    """Put every hand-made/approved image into the unpacked FPG entries."""
    buffers, done = {}, []
    for r in rows():
        path = english_file(r["image"])
        if not path:
            continue
        src = SOURCES[r["source"]]
        if src.get("no_import"):
            raise SystemExit(f"{r['image']}: importing into {r['source']} is not supported yet")
        w, h, old, pal = piece(r, unpacked)
        new = to_indices(r["image"], pngread.read(path), w, h, pal)
        x0, y0 = int(r["x"]), int(r["y"])
        for entry in src["entries"]:
            if entry not in buffers:
                buffers[entry] = bytearray(decompress(open(os.path.join(unpacked, f"{entry}.bin"), "rb").read()))
            data = buffers[entry]
            t = Tim(bytes(data), 0)
            start, stride = t.size - len(t.pixels_raw), t.vram[2] * 2
            for y in range(h):
                line = new[y * w:(y + 1) * w]
                if src["kind"] == "sheet" or t.bpp == 4:
                    if x0 % 2 or w % 2:
                        raise SystemExit(f"{r['image']}: 4bpp images must start and end on an even x")
                    at = start + (y0 + y) * stride + x0 // 2
                    data[at:at + w // 2] = bytes(line[k] | line[k + 1] << 4 for k in range(0, w, 2))
                else:
                    at = start + (y0 + y) * stride + x0
                    data[at:at + w] = bytes(line)
        changed = sum(a != b for a, b in zip(old, new))
        done.append(r["image"])
        print(f"image {r['image']}: {changed} pixels changed ({os.path.basename(os.path.dirname(path))})")
    for entry, data in buffers.items():
        path = os.path.join(unpacked, f"{entry}.bin")
        (write or (lambda p, d: open(p, "wb").write(compress(d))))(path, bytes(data))
    return done


def export():
    """review/japanese/<image>.png for every row, and the whole sources in review/full/."""
    table = rows()
    for r in table:
        w, h, pix, pal = piece(r)
        write_png(os.path.join(JAPANESE, f"{r['image']}.png"), w, h, pix, pal)
    for name, src in SOURCES.items():
        _, t = _load(os.path.join(FPG, f"{src['entries'][0]}.bin"), src)
        px = _pixels(t, src["kind"])
        if src["kind"] == "sheet":
            pal = [0] + [to15((k * 17,) * 3) for k in range(1, 16)]
        else:
            pal = list(t.cluts[0])
        write_png(os.path.join(REVIEW, "full", f"{name}.png"), len(px[0]), len(px),
                  bytes(n for line in px for n in line), pal)
    print(f"{len(table)} images -> {JAPANESE}/, sources -> {os.path.join(REVIEW, 'full')}/")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Export the catalogued images with Japanese text.",
                                 epilog="The build imports images itself (build.py --images).")
    ap.add_argument("command", choices=["export"])
    add_options(ap)
    args = ap.parse_args(argv)
    configure(args.images, args.extracted, args.review)
    export()


if __name__ == "__main__":
    main()
