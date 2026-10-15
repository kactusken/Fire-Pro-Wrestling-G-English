#!/usr/bin/env python3
"""Offline test of the tiled VWF hook: runs the patched overlay code (and the
game's glyph unpacker from the EXE) in tools/mipsim.py against a mock text
box, emulating the typewriter, per-frame upload and slot rendering.

Usage: test_vwf.py [text] [--exe PATH] [--ov002 PATH] [--font PATH] [--out PATH]
  defaults: extracted/SLPS_020.65, extracted/fpg/002.bin (compressed),
            extracted/fpg/128.bin -> review/vwf_test.png
Text uses '\\n' for line breaks.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font as fontmod  # noqa: E402
import paths  # noqa: E402
import vwf_patch as V  # noqa: E402
from lzss import decompress  # noqa: E402
from mipsim import CPU  # noqa: E402

FONT_AT, FONTOBJ = 0x80100000, 0x80180000
CTX, BOX, WIN, POOL = 0x80181000, 0x80181800, 0x80181C00, 0x80182000
SLOTS, STAGING = 0x80184000, 0x80190000
LINE_H, WIN_SLOTS = 40, 80
REG = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split())}


def setup(exe, ov, font):
    cpu = CPU()
    cpu.load(0x80010000, exe[0x800:])
    cpu.load(V.BASE, ov)
    cpu.load(FONT_AT, font)
    cpu.w32(FONTOBJ, FONT_AT + 0x18)
    cpu.w32(FONTOBJ + 4, FONT_AT + struct.unpack_from("<I", font, 4)[0])
    cpu.w32(CTX, FONTOBJ)
    cpu.w32(CTX + 0x30, POOL)
    cpu.w32(CTX + 0x34, SLOTS)
    cpu.w32(POOL + 8, STAGING)
    cpu.w16(BOX + 0x12, 0)
    cpu.w16(WIN + 2, 0)
    cpu.w16(WIN + 6, WIN_SLOTS)
    cpu.stops = {V.NEXT_CHAR, V.NEWLINE}
    return cpu


def run_text(cpu, text):
    vram = {}
    sentinel = 0xDEADBEEF
    for ch in text:
        # typewriter: start chunk, record this chunk's slot
        n = cpu.r32(POOL + 0x14)
        cpu.w16(POOL + 0x18 + 2 * n, cpu.r16(BOX + 0x12))
        cpu.w32(POOL + 0x14, n + 1)
        r = cpu.r
        r[REG["a2"]] = 0x0A if ch == "\n" else ord(ch)
        r[REG["v0"]] = 0x0A
        r[REG["s1"]], r[REG["s2"]], r[REG["s3"]], r[REG["s5"]] = CTX, BOX, WIN, POOL
        r[REG["s4"]] = 0
        r[REG["sp"]] = 0x801FF000
        for name in ("s0", "s6", "s7", "fp"):
            r[REG[name]] = sentinel
        stop = cpu.run(V.HOOK_SITE)
        assert r[REG["sp"]] == 0x801FF000, "stack not balanced"
        for name in ("s6", "s7", "fp"):
            assert r[REG[name]] == sentinel, f"{name} clobbered"
        if stop == V.NEWLINE:
            cpu.w16(CTX + 0x18, 0)
            cpu.w16(CTX + 0x1A, cpu.r16(CTX + 0x1A) + LINE_H)
        # typewriter: chunk end, count = s4
        n = cpu.r32(POOL + 0x14)
        cpu.w16(POOL + 0x18 + 2 * n, r[REG["s4"]])
        cpu.w32(POOL + 0x14, n + 1)
        assert n + 1 <= 32, "staging list overflow"
        # frame end: upload staged images
        n = cpu.r32(POOL + 0x14)
        src = STAGING
        for k in range(0, n, 2):
            slot, count = cpu.r16(POOL + 0x18 + 2 * k), cpu.r16(POOL + 0x1A + 2 * k)
            for j in range(count):
                vram[slot + j] = bytes(cpu.mem[src - 0x80000000:src - 0x80000000 + 320])
                src += 320
        assert src == cpu.r32(POOL + 8), "staging pointer mismatch"
        cpu.w32(POOL + 0x14, 0)
        cpu.w32(POOL + 8, STAGING)
    return vram


SPRITE_W, SPRITE_H = 20, 31  # as set by the (patched) slot init at 0x80062964


def render(cpu, vram, width=480, height=140):
    canvas = [[0] * width for _ in range(height)]
    used = cpu.r16(WIN + 4)
    for slot in range(used):
        x, y = cpu.r16(SLOTS + 44 * slot, True), cpu.r16(SLOTS + 44 * slot + 2, True)
        px = fontmod.pixels(vram.get(slot, bytes(320)))
        for yy in range(SPRITE_H):
            for xx in range(SPRITE_W):
                v = px[yy][xx]
                if v and 0 <= y + yy < height and 0 <= x + xx < width:
                    canvas[y + yy][x + xx] = max(canvas[y + yy][x + xx], v * 17)
    return canvas, used


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline test of the story text (tiled VWF) hook.")
    ap.add_argument("text", nargs="?", help="text to draw; '\\n' breaks lines (default: a sample)")
    paths.add(ap, "--exe", os.path.join(paths.EXTRACTED, "SLPS_020.65"), "original executable")
    paths.add(ap, "--ov002", os.path.join(paths.EXTRACTED, "fpg", "002.bin"), "overlay 002 as stored (compressed)")
    paths.add(ap, "--font", os.path.join(paths.EXTRACTED, "fpg", "128.bin"), "story font (FPG 128)")
    paths.add(ap, "--out", os.path.join(paths.REVIEW, "vwf_test.png"), "output PNG")
    args = ap.parse_args(argv)
    exe = open(args.exe, "rb").read()
    font = open(args.font, "rb").read()
    ov, _ = V.patch_overlay(decompress(open(args.ov002, "rb").read()), font)
    text = args.text.replace("\\n", "\n") if args.text else \
        ('"I can hear the roar of the crowd... So many\n people, all of them cheering for me.\n'
         'ABCDEFGHIJKLM nopqrstuvwxyz 0123456789 !?.,\'-:')
    cpu = setup(exe, ov, font)
    vram = run_text(cpu, text)
    canvas, used = render(cpu, vram)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fontmod.write_png(args.out, canvas, 2)
    chars = sum(1 for c in text if c not in " \n")
    print(f"{chars} visible characters, {used} slots used, {cpu.steps} instructions")


if __name__ == "__main__":
    main()
