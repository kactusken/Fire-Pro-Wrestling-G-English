#!/usr/bin/env python3
"""Menu font (12x13, 1bpp): proportional widths for Latin glyphs.

The font lives in FPG entry 009 (decompressed; header: map 0x18, glyphs
0x3818 at 26 bytes each, widths 0x10164 indexed by *linear SJIS index* < 0x2f0,
i.e. the first four SJIS rows) and a second
copy inside entry 011 (decompressed, at +0x18). The EXE glyph draw
(0x80015c90) advances the pen by widths[glyph] + spacing unless the window
forces a fixed pitch. Glyphs are left-aligned in their 12 px cell, and the
original table gives Latin letters a full 12 px. We set them to their ink
width plus a gap, and redraw a few glyphs (GLYPHS) to remove blank columns.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from font import ascii_sjis, sjis_linear  # noqa: E402

GAP = 1
MIN_WIDTH = 3

# Glyphs redrawn for proportional text ('#' = ink, 13 rows of 12 columns).
# The original 'j' has three blank columns before its stem.
GLYPHS = {
    "j": ["..#", "..#", "", ".##", "..#", "..#", "..#", "..#", "..#", "..#", "..#", "#.#", ".#."],
}
# Widths set by hand where ink width + GAP looks too loose.
WIDTHS = {"r": 7}  # thin top hook: no extra gap needed


def glyph_number(font, base, hi, lo):
    map_off = base + struct.unpack_from("<I", font, base)[0]
    return struct.unpack_from("<H", font, map_off + 2 * sjis_linear(hi, lo))[0]


def ink_right(font, base, g):
    data_off = base + struct.unpack_from("<I", font, base + 4)[0]
    rows = struct.unpack_from("<13H", font, data_off + 26 * g)
    cols = [x for x in range(12) if any(r >> x & 1 for r in rows)]
    return cols[-1] if cols else None


def patch_glyphs(font, base=0):
    """Redraw the glyphs in GLYPHS. Returns the characters changed."""
    data_off = base + struct.unpack_from("<I", font, base + 4)[0]
    changed = []
    for ch, rows in GLYPHS.items():
        g = glyph_number(font, base, *ascii_sjis(ord(ch)))
        bits = [sum(1 << x for x, c in enumerate(r) if c == "#") for r in rows]
        new = struct.pack("<13H", *bits)
        if font[data_off + 26 * g:data_off + 26 * g + 26] != new:
            font[data_off + 26 * g:data_off + 26 * g + 26] = new
            changed.append(ch)
    return changed


def patch_widths(font, base=0):
    """font: bytearray containing a menu font header at `base`. Returns changes.
    Call patch_glyphs first so redrawn glyphs get their new ink width."""
    width_off = base + struct.unpack_from("<I", font, base + 8)[0]
    changes = {}
    for c in range(0x21, 0x7F):
        hi, lo = ascii_sjis(c)
        g = glyph_number(font, base, hi, lo)
        idx = sjis_linear(hi, lo)
        if not g or idx >= 0x2F0:
            continue
        right = ink_right(font, base, g)
        if right is None:
            continue
        w = WIDTHS.get(chr(c), max(MIN_WIDTH, right + 1 + GAP))
        if font[width_off + idx] != w:
            changes[chr(c)] = (font[width_off + idx], w)
            font[width_off + idx] = w
    return changes


def text_width(font, text, base=0, spacing=0, space=8):
    """Approximate pixel width of ASCII text in a proportional menu window."""
    width_off = base + struct.unpack_from("<I", font, base + 8)[0]
    total = 0
    for ch in text:
        if ch == " ":
            total += space + spacing
            continue
        hi, lo = ascii_sjis(ord(ch)) if ord(ch) < 0x80 else ch.encode("cp932")
        idx = sjis_linear(hi, lo)
        total += (font[width_off + idx] if idx < 0x2F0 else 12) + spacing
    return total


if __name__ == "__main__":
    # Shows what the patch changes (build.py applies it)
    import argparse
    from lzss import decompress
    ap = argparse.ArgumentParser(description="Show the menu font glyph and width changes.")
    paths.add(ap, "--font", os.path.join(paths.EXTRACTED, "fpg", "009.bin"), "menu font (FPG 009, as stored)")
    args = ap.parse_args()
    f = bytearray(decompress(open(args.font, "rb").read()))
    print("redrawn:", patch_glyphs(f))
    for ch, (old, new) in sorted(patch_widths(f).items()):
        print(f"{ch!r}: {old} -> {new}")
