#!/usr/bin/env python3
"""Offline test of the menu tiling hook: runs the EXE menu renderer
(0x80015f5c) with font 009 and the patched call site in tools/mipsim.py,
then composites the staged cells at their slot positions.

Usage: test_menu_vwf.py [strings...] [--exe PATH] [--ov001 PATH] [--font PATH] [--text PATH] [--out PATH]
  defaults: extracted/SLPS_020.65, extracted/ovl/001.bin (decompressed),
            extracted/fpg/009.bin, text/ -> review/menu_vwf_test.png
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import menu_vwf_patch as M  # noqa: E402
import paths  # noqa: E402
from font import write_png  # noqa: E402
from lzss import decompress  # noqa: E402
from mipsim import CPU  # noqa: E402

FONT_AT, FONTOBJ = 0x80100000, 0x80180000
CTX, POOL, WINDOWS = 0x80181000, 0x80182000, 0x80185000
SLOTS, STAGING, STR = 0x80184000, 0x80190000, 0x80186000
STOP = 0x80000100
REG = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split())}


def setup(exe, ov, font, patched):
    cpu = CPU()
    cpu.load(0x80010000, (M.patch_exe(exe) if patched else exe)[0x800:])
    cpu.load(M.OVERLAY_BASE, M.append_hook(ov, exe, M.ascii_widths(font)) if patched else ov)
    cpu.load(FONT_AT, font)
    hdr = struct.unpack_from("<5I", font, 0)
    for i, v in enumerate(hdr):
        cpu.w32(FONTOBJ + 4 * i, FONT_AT + v)
    cpu.w32(CTX, FONTOBJ)
    cpu.w16(CTX + 0x1E, 2)       # shadow on, as in the menus
    cpu.w16(CTX + 0x28, 16)
    cpu.w32(CTX + 0x30, POOL)
    cpu.w32(CTX + 0x34, SLOTS)
    cpu.w32(CTX + 0x38, WINDOWS)
    cpu.w32(POOL + 4, SLOTS)
    cpu.w32(POOL + 8, STAGING)
    cpu.w16(WINDOWS + 6, 99)
    cpu.stops = {STOP}
    return cpu


def watch_staging(cpu):
    """Record which staging cells get written, to catch half-built cells."""
    writes = {}
    orig = cpu.wr

    def wr(a, n, v):
        if STAGING <= a < STAGING + 84 * 400:
            cell = (a - STAGING) // 84
            writes.setdefault(cell, []).append((a, v))
        orig(a, n, v)
    cpu.wr = wr
    return writes


def draw(cpu, text, y):
    data = b"".join(ch.encode("cp932") for ch in text) + b"\0"
    cpu.load(STR, data)
    cpu.w16(CTX + 0x18, 0)
    cpu.w16(CTX + 0x1A, y)
    first_slot = (cpu.r32(POOL + 4) - SLOTS) // 0x2C
    r = cpu.r
    r[REG["a0"]], r[REG["a1"]] = STR, CTX
    r[REG["sp"]], r[REG["ra"]] = 0x801FF000, STOP
    for n in ("s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "fp"):
        r[REG[n]] = 0x1234
    cpu.run(0x80015F5C)
    count = r[REG["v0"]]
    assert r[REG["sp"]] == 0x801FF000, "stack not balanced"
    return first_slot, count


def measure(cpu, text):
    """Run the EXE cell counter 0x800167d0 (sizes windows automatically)."""
    data = text if isinstance(text, bytes) else b"".join(ch.encode("cp932") for ch in text)
    cpu.load(STR, data + b"\0")
    r = cpu.r
    r[REG["a0"]], r[REG["sp"]], r[REG["ra"]] = STR, 0x801FF000, STOP
    cpu.run(0x800167D0)
    return r[REG["v0"]]


def check_measure(exe, ov, font, paths):
    """The counter must reserve at least the cells the hook draws."""
    import strtab
    cpu = setup(exe, ov, font, True)
    bad = n = 0
    for path in paths:
        for en in strtab.parse(path).values():
            data = strtab.encode_en(en)
            if b"\n" in data or b"%" in data:
                continue
            cpu.w16(WINDOWS + 6, 99)
            cpu.w32(POOL + 4, SLOTS)
            cpu.w32(POOL + 8, STAGING)
            cpu.load(STR, data + b"\0")
            r = cpu.r
            r[REG["a0"]], r[REG["a1"]] = STR, CTX
            r[REG["sp"]], r[REG["ra"]] = 0x801FF000, STOP
            cpu.w16(CTX + 0x18, 0)
            cpu.w16(CTX + 0x1A, 0)
            cpu.run(0x80015F5C)
            drawn = r[REG["v0"]]
            counted = measure(cpu, data)
            n += 1
            if counted < drawn:
                bad += 1
                print(f"  counter {counted} < drawn {drawn}: {en!r}")
    print(f"cell counter: {n} strings checked, {bad} under-counted")
    return bad


def composite(cpu, total, width=360, height=200):
    canvas = [[0] * width for _ in range(height)]
    for k in range(total):
        x, y = cpu.r16(SLOTS + 0x2C * k, True), cpu.r16(SLOTS + 0x2C * k + 2, True)
        img = cpu.mem[STAGING - 0x80000000 + 84 * k:STAGING - 0x80000000 + 84 * k + 84]
        for row in range(14):
            for col in range(12):
                v = (img[row * 6 + col // 2] >> ((col & 1) * 4)) & 15
                if v and 0 <= x + col < width and 0 <= y + row < height:
                    canvas[y + row][x + col] = max(canvas[y + row][x + col], 255 if v == 1 else 120)
    return canvas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline test of the menu tiling hook.")
    ap.add_argument("strings", nargs="*", help="strings to draw (default: a sample set)")
    paths.add(ap, "--exe", os.path.join(paths.EXTRACTED, "SLPS_020.65"), "original executable")
    paths.add(ap, "--ov001", os.path.join(paths.EXTRACTED, "ovl", "001.bin"), "overlay 001, decompressed")
    paths.add(ap, "--font", os.path.join(paths.EXTRACTED, "fpg", "009.bin"), "menu font (FPG 009, as stored)")
    paths.add(ap, "--text", paths.TEXT, "text folder (ov001.txt, ov004.txt are measured)")
    paths.add(ap, "--out", os.path.join(paths.REVIEW, "menu_vwf_test.png"), "output PNG")
    args = ap.parse_args(argv)
    exe = open(args.exe, "rb").read()
    ov = open(args.ov001, "rb").read()
    font = decompress(open(args.font, "rb").read())
    texts = args.strings or ["Blue Corner", "Lumberjack", "Ring-out Count", "Nippon Budokan",
                             "Free match vs. players or the CPU.", "Panther Tottori"]
    rows = []
    for patched in (False, True):
        cpu = setup(exe, ov, font, patched)
        writes = watch_staging(cpu)
        total = 0
        for i, t in enumerate(texts):
            writes.clear()
            first, n = draw(cpu, t, 16 * i)
            if patched and t.isascii():
                # each tiled cell must be written in one pass: never overwritten
                # later (cells of Japanese glyphs come from the game's own draw)
                for cell, ws in writes.items():
                    addrs = [a for a, _ in ws]
                    assert len(addrs) == len(set(addrs)), f"cell {cell} rewritten while drawing {t!r}"
            total = first + n
            print(f"{'tiled' if patched else 'orig '} {n:3d} cells  {t}")
        if patched:
            # a window budget smaller than the text: the hook must stop there
            cpu.w16(WINDOWS + 6, 4)
            writes.clear()
            first, n = draw(cpu, "Ring Return Count", 16 * len(texts))
            used = {c for c in writes}
            assert len(used) <= 4, f"wrote {len(used)} cells into a 4-cell window"
            print(f"budget 4: {len(used)} cells written, renderer count {n}")
            cpu.w16(WINDOWS + 6, 99)
        rows += composite(cpu, total)
        rows += [[60] * 360 for _ in range(4)]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_png(args.out, rows, 2)
    assert not check_measure(exe, ov, font, [os.path.join(args.text, f) for f in ("ov001.txt", "ov004.txt")])


if __name__ == "__main__":
    main()
