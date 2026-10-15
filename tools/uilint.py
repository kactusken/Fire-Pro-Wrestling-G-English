#!/usr/bin/env python3
"""Estimate how much room translated UI strings need (menu renderer + tiling hook).

A menu window shows at most a fixed number of 12 px cells, sized for the
Japanese text. Japanese takes one cell per character. With the tiling hook,
a run of ASCII letters/punctuation takes ceil(width / 12) cells, and a
space takes no cell (it only moves the pen). "#xN," moves the pen N px.

Usage: uilint.py <text/ovNNN.txt> [--all] [--font PATH]
  --font defaults to extracted/fpg/009.bin (the menu font as stored)
Lists strings whose English needs more cells or pixels than the Japanese.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import menufont  # noqa: E402
import paths  # noqa: E402
import strtab  # noqa: E402
from lzss import decompress  # noqa: E402

CODE = re.compile(r"#x(-?\d+),")
RUN = re.compile(r"[\x28-\x7e]+")  # drawn by the tiling hook as one run


def measure(text, font):
    """Return (cells, pixels) of the widest line of text (EN or JP)."""
    best = (0, 0)
    for line in text.replace("\\n", "\n").split("\n"):
        cells = px = 0
        pad = sum(int(n) for n in CODE.findall(line))
        line = CODE.sub("", line)
        i = 0
        while i < len(line):
            ch = line[i]
            m = RUN.match(line, i) if ch not in strtab.FULLWIDTH else None
            if m:
                w = menufont.text_width(font, m.group(), space=menufont_space)
                cells += -(-w // 12)
                px += w
                i = m.end()
            elif ch == " ":
                px += menufont_space
                i += 1
            else:
                cells += 1
                px += 12
                i += 1
        best = max(best, (cells, px + pad))
    return best


menufont_space = 4


def game_cells(data, font):
    """Cells the patched EXE counter (0x800167d0 + menu hook `measure`)
    reserves for encoded string bytes: one per SJIS character except the
    full-width space, one per half-width kana, ceil((width + 1) / 12) per
    ASCII run of 0x28..0x7E (the +1 is the drop shadow), control codes none."""
    widths = {}
    import menu_vwf_patch
    for i, w in enumerate(menu_vwf_patch.ascii_widths(font)):
        widths[0x28 + i] = w
    cells = i = 0
    while i < len(data):
        c = data[i]
        if c & 0xE0 in (0x80, 0xE0):
            cells += data[i:i + 2] != b"\x81\x40"
            i += 2
        elif c == 0x23:
            m = re.match(rb"#[a-z]-?\d+,", data[i:])
            i += m.end() if m else 1
        elif 0x28 <= c < 0x7F:
            w = 0
            while i < len(data) and 0x28 <= data[i] < 0x7F:
                w += widths[data[i]]
                i += 1
            cells += (w + 12) // 12
        else:
            cells += 0xA1 <= c < 0xE0
            i += 1
    return cells


def load_font(path):
    f = bytearray(decompress(open(path, "rb").read()))
    menufont.patch_glyphs(f)
    menufont.patch_widths(f)
    return f


def lint(font, path, show_all=False):
    jp = {}
    cur = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("@ "):
            cur = int(line.split()[1], 16)
        elif line.startswith("JP "):
            jp[cur] = line[3:]
    problems = 0
    for addr, en in sorted(strtab.parse(path).items()):
        jc, jpx = measure(jp.get(addr, ""), font)
        ec, epx = measure(en, font)
        over = ec > jc or epx > jpx
        if over or show_all:
            problems += over
            print(f"{addr:08x} {'OVER' if over else 'ok  '} cells {ec:2d}/{jc:2d} px {epx:3d}/{jpx:3d}  {en}")
    return problems


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="List UI strings whose English needs more room than the Japanese.")
    ap.add_argument("text", help="a strtab text file, e.g. text/ov001.txt")
    ap.add_argument("--all", action="store_true", help="list every string, not only the ones that need more room")
    paths.add(ap, "--font", os.path.join(paths.EXTRACTED, "fpg", "009.bin"), "menu font (FPG 009, as stored)")
    args = ap.parse_args()
    n = lint(load_font(args.font), args.text, args.all)
    print(f"{n} strings need more room than the Japanese")
