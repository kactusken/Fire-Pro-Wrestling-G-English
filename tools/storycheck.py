#!/usr/bin/env python3
"""Lay out every story message the way the patched game draws it.

    python3 tools/storycheck.py [scene ...] [--long-names] [--png DIR] [--verify N]
                                [--extracted PATH] [--script PATH] [--text PATH]

storylint.py estimates widths with a flat allowance for name codes. This tool
expands the codes the way overlay 002's preprocessor (0x80061c90) does and
then places every letter with a Python model of the tiled VWF hook
(tools/vwf_patch.py): pen advance, tile spills, and the slot ring.

Code expansion
  #MS / #MF   the hero's short / full name (EXE 0x800193ac / 0x80018430 with id
              0x8000). Default: the story hero's default record, Yamashita /
              Yuji Yamashita. --long-names uses the longest a player could
              enter in the record's fields: 6 full-width letters for the short
              name (14-byte field), 9 for the second part (20 bytes), joined by
              a space. Name entry may limit them further.
  #PSnn/#PLnn promotion short / full name (EXE 0x80019cf4 / 0x80019c8c),
              from <text>/exe_promotions.py.
  #W..nnn     should no longer appear in the English (storylint checks).
  Anything else after '#' is copied as it is (the game prints an error
  through a stub and copies nothing; reported here).

Checks, per message
  - a line whose ink reaches past the visible box (455 px; warn past 440)
  - more than 4 lines (speaker + 3)
  - more glyph slots than the window's ring (80): the first tiles would be
    overwritten by the last ones while the message is on screen
Full-width (SJIS) characters take one slot each and advance 20 px, as the
game's own draw routine (0x80062e54; the story window has no spacing or
auto-wrap).

--png DIR    render each flagged message (2x) for a visual check
--verify N   run N random messages through the real hook code in tools/mipsim.py
             (tools/test_vwf.py) and compare slot counts and rendered pixels
             with the model, to make sure the model still matches the patch
"""
import glob
import os
import random
import re
import runpy
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font as fontmod  # noqa: E402
import paths  # noqa: E402
import vwf_patch  # noqa: E402

VISIBLE, WARN = 455, 440
MAX_LINES, RING = 4, 80
TILE, WIDE = 20, 20
LINE_H = 40

DEFAULT_NAMES = {"MS": "Yamashita", "MF": "Yuji Yamashita"}
LONG_NAMES = {"MS": "Ｗ" * 6, "MF": "Ｗ" * 6 + " " + "Ｗ" * 9}
CODE = re.compile(r"#(M[SFLN]|P[SL]\d\d|W[SFLN]\d{3})")
_promotions = None


def load_promotions(text_dir=paths.repo(paths.TEXT)):
    """Promotion names (full, short) from <text_dir>/exe_promotions.py, for #PS/#PL."""
    global _promotions
    _promotions = runpy.run_path(os.path.join(text_dir, "exe_promotions.py"))["NAMES"]
    return _promotions


def promotions():
    return _promotions if _promotions is not None else load_promotions()


def expand(text, names, bad):
    def sub(m):
        c = m.group(1)
        if c[0] == "M":
            if c not in names:
                bad.append(f"#{c} has no expansion here")
                return ""
            return names[c]
        if c[0] == "P":
            n = int(c[2:])
            if n >= len(promotions()):
                bad.append(f"#{c}: player-made promotion, length unknown")
                return "Ｗ" * 6
            full, short = promotions()[n]
            return short if c[1] == "S" else full
        bad.append(f"#{c} left in English")
        return ""
    out = CODE.sub(sub, text)
    if "#" in out:
        bad.append("'#' that is not a known code (the game drops it)")
    return out


class Layout:
    """Model of the VWF hook's tile placement for one message."""

    def __init__(self, rows):
        self.rows = rows
        self.pen = self.y = 0
        self.tile_x = self.tile_y = None
        self.tile_valid = False
        self.slots = 0           # slots taken (not capped at the ring)
        self.tiles = []          # (x, y, [(src_glyph, src_col, dst_col, cols)])
        self.line_ink = [0]

    def new_tile(self, x):
        self.slots += 1
        self.tile_x, self.tile_y, self.tile_valid = x, self.y, True
        self.tiles.append((x, self.y, []))

    def ink_to(self, right):
        self.line_ink[-1] = max(self.line_ink[-1], right)

    def ascii(self, c):
        g, left, ink, adv = self.rows[c - 0x20]
        x = self.pen
        self.pen += adv
        if not g:
            return
        if not (self.tile_valid and self.tile_y == self.y and 0 <= x - self.tile_x < TILE):
            self.new_tile(x)
        dst = x - self.tile_x
        part = min(ink, TILE - dst)
        self.tiles[-1][2].append((g, left, dst, part))
        if ink - part > 0:
            self.new_tile(self.tile_x + TILE)
            self.tiles[-1][2].append((g, left + part, 0, ink - part))
        self.ink_to(x + ink)

    def wide(self, ch):
        # the game's own glyph path: one slot, 20 px; the next ASCII starts a new tile
        self.slots += 1
        self.tile_valid = False
        self.tiles.append((self.pen, self.y, [("sjis", ch)]))
        self.ink_to(self.pen + WIDE)
        self.pen += WIDE

    def newline(self):
        self.pen = 0
        self.y += LINE_H
        self.line_ink.append(0)

    def run(self, lines):
        for i, ln in enumerate(lines):
            if i:
                self.newline()
            for ch in ln:
                o = ord(ch)
                if o == 0x20 or 0x21 <= o < 0x7F:
                    self.ascii(o)
                elif o > 0x7F:
                    self.wide(ch)
        return self


def render(layout, font, width=480):
    height = LINE_H * len(layout.line_ink) + 8
    canvas = [[0] * width for _ in range(height)]
    cache = {}

    def px(g):
        if g not in cache:
            cache[g] = fontmod.pixels(font.glyph(g))
        return cache[g]
    for x0, y0, parts in layout.tiles:
        for part in parts:
            if part[0] == "sjis":
                s = part[1].encode("cp932")
                g = font.glyph_number(s[0], s[1])
                pieces = [(px(g), 0, 0, WIDE)] if g else []
            else:
                g, src, dst, cols = part
                pieces = [(px(g), src, dst, cols)]
            for p, src, dst, cols in pieces:
                for yy in range(31):
                    for c in range(cols):
                        v = p[yy][src + c]
                        x = x0 + dst + c
                        if v and x < width:
                            canvas[y0 + yy][x] = max(canvas[y0 + yy][x], v * 17)
    for y in range(height):          # the visible edge
        if canvas[y][VISIBLE] == 0:
            canvas[y][VISIBLE] = 90
    return canvas


def messages(path):
    cur, out = None, {}
    for line in open(path, encoding="utf-8").read().split("\n"):
        if line.startswith("@ "):
            cur = int(line[2:])
            out[cur] = []
        elif line.startswith("EN ") and cur is not None:
            out[cur].append(line[3:])
    return {k: v for k, v in out.items() if v}


def check(lines, rows, names):
    bad = []
    text = [expand(ln, names, bad) for ln in lines]
    lay = Layout(rows).run(text)
    for i, w in enumerate(lay.line_ink):
        if w > VISIBLE:
            bad.append(f"line {i + 1} ink ends at {w}px, past the box edge ({VISIBLE}): {text[i]}")
        elif w > WARN:
            bad.append(f"line {i + 1} ink ends at {w}px (warn > {WARN}): {text[i]}")
    if len(text) > MAX_LINES:
        bad.append(f"{len(text)} lines (max {MAX_LINES})")
    if lay.slots > RING:
        bad.append(f"{lay.slots} glyph slots (ring holds {RING}; the first tiles get overwritten)")
    return bad, text, lay


def verify(samples, rows, font_data, extracted=paths.repo(paths.EXTRACTED)):
    """Compare the model with the real hook in the simulator (ASCII messages)."""
    import test_vwf
    from lzss import decompress
    exe = open(os.path.join(extracted, "SLPS_020.65"), "rb").read()
    ov, _ = vwf_patch.patch_overlay(
        decompress(open(os.path.join(extracted, "fpg", "002.bin"), "rb").read()), font_data)
    font = fontmod.Font(font_data)
    test_vwf.WIN_SLOTS = 1000        # no wrap, so every tile survives for the pixel compare
    failures = 0
    for where, text in samples:
        cpu = test_vwf.setup(exe, ov, font_data)
        vram = test_vwf.run_text(cpu, "\n".join(text))
        sim, used = test_vwf.render(cpu, vram, width=480, height=LINE_H * len(text) + 8)
        lay = Layout(rows).run(text)
        mine = render(lay, font)
        diff = sum(1 for y in range(len(sim)) for x in range(480)
                   if x != VISIBLE and sim[y][x] != mine[y][x])
        ok = used == lay.slots and diff == 0
        failures += not ok
        print(f"verify {where}: sim {used} slots, model {lay.slots}, {diff} pixels differ"
              + ("" if ok else "  <-- MISMATCH"))
    return failures


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Lay out every story message the way the patched game draws it.")
    ap.add_argument("scenes", nargs="*", metavar="scene", help="scene numbers (default: all, plus ov002_scene.txt)")
    ap.add_argument("--long-names", action="store_true", help="expand #MS/#MF to the longest names a player can enter")
    ap.add_argument("--png", metavar="DIR", help="write a PNG of each flagged message here")
    ap.add_argument("--verify", type=int, default=0, metavar="N",
                    help="check N random ASCII messages against the MIPS simulator")
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output")
    paths.add(ap, "--script", paths.SCRIPT, "story script folder")
    paths.add(ap, "--text", paths.TEXT, "text folder (ov002_scene.txt, exe_promotions.py)")
    args = ap.parse_args(argv)
    names = LONG_NAMES if args.long_names else DEFAULT_NAMES
    png_dir, n_verify, scenes = args.png, args.verify, args.scenes
    load_promotions(args.text)
    font_data = open(os.path.join(args.extracted, "fpg", "128.bin"), "rb").read()
    rows = vwf_patch.metrics(font_data)
    font = fontmod.Font(font_data)
    if scenes:
        files = [os.path.join(args.script, f"{int(s):03d}.txt") for s in scenes]
    else:
        files = sorted(glob.glob(os.path.join(args.script, "[0-9][0-9][0-9].txt")))
        files.append(os.path.join(args.text, "ov002_scene.txt"))
    if png_dir:
        os.makedirs(png_dir, exist_ok=True)

    flagged = total = max_slots = 0
    widest = (0, "")
    pool = []
    for f in files:
        name = os.path.basename(f)[:-4]
        for m, lines in messages(f).items():
            total += 1
            where = f"{name} @{m:03d}"
            bad, text, lay = check(lines, rows, names)
            max_slots = max(max_slots, lay.slots)
            widest = max(widest, (max(lay.line_ink), where))
            if all(ord(c) < 0x80 for t in text for c in t):
                pool.append((where, text))
            if bad:
                flagged += 1
                for b in bad:
                    print(f"{where}: {b}")
                if png_dir:
                    fontmod.write_png(os.path.join(png_dir, f"{name}_{m:03d}.png"), render(lay, font), 2)
    print(f"{total} messages, {flagged} flagged; widest line {widest[0]}px ({widest[1]}), "
          f"most slots {max_slots} (ring {RING})")
    if n_verify:
        random.seed(1)
        picks = random.sample(pool, min(n_verify, len(pool)))
        bad = verify(picks, rows, font_data, args.extracted)
        print(f"model vs simulator: {len(picks) - bad}/{len(picks)} match")
        return 1 if bad else 0
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
