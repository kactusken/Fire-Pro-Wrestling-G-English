#!/usr/bin/env python3
"""Variable-width, tiled ASCII rendering for the story text box (overlay 002).

Background
  The story renderer (draw loop in 0x80063344) only handles two-byte SJIS
  and newline (0x0A); other single bytes are skipped. Each SJIS glyph takes
  one 20x32 "slot" (VRAM cell); a text window owns a ring of slots (80 for
  the story box) out of a pool of 96 (one 256x256 4bpp texture page).

What this patch does
  Hooks the single-byte branch at 0x8006368c. For bytes 0x21-0x7E it unpacks
  the font's matching full-width glyph and blends its ink columns into a
  20 px wide tile at the exact pen position, starting a new slot only when a
  tile is full. A line of English therefore uses about as many slots as a
  line of Japanese. Spaces only advance the pen.
  Tiles are (re)uploaded through the game's own per-frame staging list.

  New code, metrics table and buffers are appended after the overlay's end
  (0x80077be0). The overlay area runs to 0x80092000 (heap start), and nothing
  references memory past overlay 002 while it is loaded.

  Glyph sprites are widened from 19 to 20 px so tile edges are not clipped.

  The fast-forward loops are reduced from 8 to 4 typewriter steps per frame,
  so the 32-entry staging list cannot overflow (up to 6 entries per letter).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font as fontmod  # noqa: E402
import paths  # noqa: E402
from mips_asm import assemble  # noqa: E402

BASE = 0x8005a718           # load address of all overlays
ORIGINAL_END = 0x80077be0
OVERLAY_LIMIT = 0x80092000  # heap starts here

UNPACK_GLYPH = 0x80012e0c   # (src, dst, len) 32-byte-ring LZ
HOOK_SITE = 0x8006368c      # bne a2, v0(0x0A), 0x800636ac ; nop
NEWLINE = 0x80063694
NEXT_CHAR = 0x800636ac
FAST_LOOP_LIMITS = (0x8005ec48, 0x8005ed18, 0x8005ee04)  # slti v0, s0, 8
SPRITE_WIDTH_SITE = 0x80062964  # addiu v0, zero, 0x13 -- glyph sprites are 19 px wide

SPACE_WIDTH = 7
GAP = 2  # pixels between letters

EXPECT = {
    HOOK_SITE: (0x14C20007, 0x00000000),
    FAST_LOOP_LIMITS[0]: (0x2A020008,),
    FAST_LOOP_LIMITS[1]: (0x2A020008,),
    FAST_LOOP_LIMITS[2]: (0x2A020008,),
    SPRITE_WIDTH_SITE: (0x24020013,),
}

# Registers inside the typewriter (0x80063344) at the hook site:
#   a2 = byte, v0 = 0x0A, s0 = chunk read pointer
#   s1 = text context (+0x00 font, +0x18 pen x, +0x1a pen y, +0x34 slot records)
#   s2 = textbox (+0x12 next slot), s3 = window (+2 first slot, +4 used, +6 size)
#   s5 = pool (+0x08 staging write ptr, +0x14 staging list length, +0x18 list)
CODE_ASM = """
hook:
    beq   a2, v0, to_newline
    addiu t0, a2, -0x20
    sltiu t1, t0, 0x5f
    beqz  t1, to_next
    nop
    addiu sp, sp, -0x28
    sw    ra, 0x10(sp)
    sw    s6, 0x14(sp)
    sw    s7, 0x18(sp)
    jal   vwf_char
    move  a0, t0
    lw    ra, 0x10(sp)
    lw    s6, 0x14(sp)
    lw    s7, 0x18(sp)
    j     NEXT
    addiu sp, sp, 0x28
to_newline:
    j     NEWLINE
    nop
to_next:
    j     NEXT
    nop

; vwf_char(a0 = byte - 0x20)
vwf_char:
    addiu sp, sp, -0x20
    sw    ra, 0x10(sp)
    sll   t0, a0, 3
    lui   s6, %hi(TABLE)
    addiu s6, s6, %lo(TABLE)
    addu  s6, s6, t0             ; s6 = {u16 glyph, u8 left, u8 ink, u8 advance}
    lhu   s7, 0x18(s1)           ; s7 = pen x for this glyph
    lbu   t1, 4(s6)
    lhu   t2, 0(s6)
    addu  t1, s7, t1
    beqz  t2, vc_ret             ; no glyph: advance only
    sh    t1, 0x18(s1)
    lw    t3, 0(s1)              ; font object
    nop
    lw    t3, 4(t3)              ; glyph offset table
    sll   t4, t2, 2
    addu  t4, t4, t3
    lw    t5, 0(t4)
    lw    t6, 4(t4)
    addu  a0, t3, t5
    subu  a2, t6, t5
    lui   a1, %hi(GLYPHBUF)
    jal   UNPACK
    addiu a1, a1, %lo(GLYPHBUF)
    jal   tile_check
    nop
    lui   t0, %hi(T_X)
    lh    t0, %lo(T_X)(t0)
    lbu   a1, 2(s6)              ; source column
    subu  a2, s7, t0             ; destination column in tile
    lbu   t1, 3(s6)              ; ink width
    addiu t2, zero, 20
    subu  t2, t2, a2             ; room left in tile
    slt   t3, t1, t2
    beqz  t3, vc_part1
    move  a3, t2
    move  a3, t1
vc_part1:
    sw    a3, 0x14(sp)
    jal   blit
    nop
    jal   stage_tile
    nop
    lw    a3, 0x14(sp)
    lbu   t1, 3(s6)
    nop
    subu  t1, t1, a3
    blez  t1, vc_ret             ; glyph fitted in one tile
    nop
    lui   t0, %hi(T_X)
    lh    a0, %lo(T_X)(t0)
    jal   new_tile
    addiu a0, a0, 20
    lw    a3, 0x14(sp)
    lbu   a1, 2(s6)
    lbu   t1, 3(s6)
    addu  a1, a1, a3
    subu  a3, t1, a3
    jal   blit
    move  a2, zero
    jal   stage_tile
    nop
vc_ret:
    lw    ra, 0x10(sp)
    nop
    jr    ra
    addiu sp, sp, 0x20

; Ensure the current tile belongs to this textbox/line and covers pen x (s7).
tile_check:
    lui   t0, %hi(T_BOX)
    lw    t1, %lo(T_BOX)(t0)
    lhu   t2, %lo(T_NEXT)(t0)
    lhu   t3, 0x12(s2)
    bne   t1, s2, tc_new
    lh    t4, %lo(T_Y)(t0)
    bne   t2, t3, tc_new
    lh    t5, 0x1a(s1)
    lh    t6, %lo(T_X)(t0)
    bne   t4, t5, tc_new
    subu  t7, s7, t6
    sltiu t8, t7, 20
    beqz  t8, tc_new
    nop
    jr    ra
    nop
tc_new:
    j     new_tile
    move  a0, s7

; new_tile(a0 = x): take the next slot of the window, place it, clear TILEBUF.
new_tile:
    lui   t0, %hi(T_BOX)
    lhu   t1, 0x12(s2)
    lh    t2, 0x1a(s1)
    sw    s2, %lo(T_BOX)(t0)
    sh    a0, %lo(T_X)(t0)
    sh    t2, %lo(T_Y)(t0)
    sh    t1, %lo(T_SLOT)(t0)
    lw    t3, 0x34(s1)           ; slot records, 0x2c bytes each
    sll   t4, t1, 1
    addu  t4, t4, t1
    sll   t5, t4, 2
    subu  t5, t5, t1
    sll   t5, t5, 2
    addu  t3, t3, t5
    sh    a0, 0(t3)
    sh    t2, 2(t3)
    lh    t6, 2(s3)              ; first slot of window
    lh    t7, 6(s3)              ; window size
    addiu t1, t1, 1
    addu  t8, t6, t7
    slt   t9, t1, t8
    bnez  t9, nt_nowrap
    nop
    move  t1, t6
nt_nowrap:
    sh    t1, 0x12(s2)
    sh    t1, %lo(T_NEXT)(t0)
    lh    t8, 4(s3)              ; slots in use (capped at size)
    nop
    addiu t8, t8, 1
    slt   t9, t7, t8
    beqz  t9, nt_used
    nop
    move  t8, t7
nt_used:
    sh    t8, 4(s3)
    lui   t3, %hi(TILEBUF)
    addiu t3, t3, %lo(TILEBUF)
    addiu t4, t3, 320
nt_clear:
    sw    zero, 0(t3)
    addiu t3, t3, 4
    bne   t3, t4, nt_clear
    nop
    jr    ra
    nop

; blit(a1 = src column, a2 = dst column, a3 = columns): GLYPHBUF -> TILEBUF, max blend
blit:
    blez  a3, bl_ret
    lui   t0, %hi(GLYPHBUF)
    addiu t0, t0, %lo(GLYPHBUF)
    lui   t1, %hi(TILEBUF)
    addiu t1, t1, %lo(TILEBUF)
    addiu t9, zero, 32
bl_row:
    move  t2, zero
bl_col:
    addu  t3, a1, t2
    srl   t4, t3, 1
    addu  t4, t4, t0
    lbu   t5, 0(t4)
    andi  t6, t3, 1
    sll   t6, t6, 2
    srlv  t5, t5, t6
    andi  t5, t5, 0xf
    beqz  t5, bl_skip
    addu  t3, a2, t2
    srl   t4, t3, 1
    addu  t4, t4, t1
    lbu   t7, 0(t4)
    andi  t6, t3, 1
    sll   t6, t6, 2
    srlv  t8, t7, t6
    andi  t8, t8, 0xf
    sltu  v0, t8, t5
    beqz  v0, bl_skip
    addiu v1, zero, 0xf
    sllv  v1, v1, t6
    xori  v1, v1, 0xff
    and   t7, t7, v1
    sllv  t5, t5, t6
    or    t7, t7, t5
    sb    t7, 0(t4)
bl_skip:
    addiu t2, t2, 1
    bne   t2, a3, bl_col
    nop
    addiu t0, t0, 10
    addiu t9, t9, -1
    bnez  t9, bl_row
    addiu t1, t1, 10
bl_ret:
    jr    ra
    nop

; stage_tile(): queue TILEBUF for upload to slot T_SLOT this frame.
; The typewriter has already written this chunk's slot at list[n-1]; we
; overwrite it, add a count of 1, then leave a dummy slot entry for the
; typewriter's own count (which stays 0 for ASCII chunks).
stage_tile:
    lw    t0, 0x14(s5)
    lui   t2, %hi(T_SLOT)
    lhu   t3, %lo(T_SLOT)(t2)
    sll   t1, t0, 1
    addu  t1, t1, s5
    addiu t4, zero, 1
    sh    t3, 0x16(t1)
    sh    t4, 0x18(t1)
    sh    zero, 0x1a(t1)
    addiu t0, t0, 2
    sw    t0, 0x14(s5)
    lw    t5, 8(s5)
    lui   t6, %hi(TILEBUF)
    addiu t6, t6, %lo(TILEBUF)
    addiu t7, t6, 320
st_copy:
    lw    t8, 0(t6)
    addiu t6, t6, 4
    sw    t8, 0(t5)
    bne   t6, t7, st_copy
    addiu t5, t5, 4
    jr    ra
    sw    t5, 8(s5)

    .align 3
TABLE:
"""

DATA_ASM = """
T_BOX:
    .half 0, 0
T_X:
    .half 0
T_Y:
    .half 0
T_SLOT:
    .half 0
T_NEXT:
    .half 0xffff
GLYPHBUF:
"""


def word(buf, addr):
    return struct.unpack_from("<I", buf, addr - BASE)[0]


def put(buf, addr, data):
    buf[addr - BASE:addr - BASE + len(data)] = data


def metrics(font_data):
    """95 entries (glyph, left, ink, advance) for 0x20..0x7E.

    left/ink cover every non-zero pixel column so anti-aliasing is kept; the
    pen sits at that left edge. advance runs to the solid ink's right edge
    (threshold 3) plus GAP."""
    f = fontmod.Font(font_data)
    rows = []
    for c in range(0x20, 0x7F):
        s = fontmod.ascii_sjis(c)
        g = f.glyph_number(s[0], s[1])
        px = fontmod.pixels(f.glyph(g)) if g else None
        solid = fontmod.ink_bounds(px) if px else None
        if c == 0x20 or solid is None:
            rows.append((0, 0, 0, SPACE_WIDTH))
            continue
        left, right = fontmod.ink_bounds(px, 1)
        rows.append((g, left, right - left + 1, solid[1] - left + 1 + GAP))
    return rows


def pack_table(rows):
    return b"".join(struct.pack("<HBBBxxx", *r) for r in rows)


def line_width(text, rows):
    """Pixel width of a line of ASCII text."""
    return sum(rows[ord(c) - 0x20][3] for c in text if 0x20 <= ord(c) < 0x7F)


def build_blob(start, table):
    syms = {"UNPACK": UNPACK_GLYPH, "NEXT": NEXT_CHAR, "NEWLINE": NEWLINE,
            "T_BOX": 0, "T_X": 0, "T_Y": 0, "T_SLOT": 0, "T_NEXT": 0,
            "GLYPHBUF": 0, "TILEBUF": 0}
    for _ in range(2):  # second pass sees the final data addresses
        code, csyms = assemble(CODE_ASM, start, syms)
        data_base = csyms["TABLE"] + len(table)
        data, dsyms = assemble(DATA_ASM, data_base, syms)
        for k in ("T_BOX", "T_X", "T_Y", "T_SLOT", "T_NEXT", "GLYPHBUF"):
            syms[k] = dsyms[k]
        syms["GLYPHBUF"] = (syms["GLYPHBUF"] + 3) & ~3
        syms["TILEBUF"] = syms["GLYPHBUF"] + fontmod.GLYPH_BYTES
    end = syms["TILEBUF"] + fontmod.GLYPH_BYTES
    blob = bytearray(end - start)
    blob[:len(code)] = code
    t = csyms["TABLE"] - start
    blob[t:t + len(table)] = table
    blob[data_base - start:data_base - start + len(data)] = data
    syms.update(csyms)
    return bytes(blob), syms


def patch_overlay(ov_data, font_data):
    ov = bytearray(ov_data)
    if BASE + len(ov) != ORIGINAL_END:
        raise SystemExit("unexpected overlay 002 size")
    for addr, words in EXPECT.items():
        got = tuple(word(ov, addr + 4 * i) for i in range(len(words)))
        if got != words:
            raise SystemExit(f"overlay 002 differs at {addr:#x}: " + " ".join(f"{w:08x}" for w in got))

    blob, syms = build_blob(ORIGINAL_END, pack_table(metrics(font_data)))
    if ORIGINAL_END + len(blob) > OVERLAY_LIMIT:
        raise SystemExit("patched overlay does not fit below the heap")
    ov += blob

    hook, _ = assemble("j HOOK\nnop", HOOK_SITE, {"HOOK": syms["hook"]})
    put(ov, HOOK_SITE, hook)
    for site in FAST_LOOP_LIMITS:
        put(ov, site, struct.pack("<I", 0x2A020004))  # slti v0, s0, 4
    # Tiles use all 20 columns (Japanese glyphs never touched the last one).
    put(ov, SPRITE_WIDTH_SITE, struct.pack("<I", 0x24020014))
    return bytes(ov), syms


if __name__ == "__main__":
    # Prints where the patch puts its code and buffers (build.py applies it)
    import argparse
    from lzss import decompress
    ap = argparse.ArgumentParser(description="Patch overlay 002 for VWF text and print the new symbols.")
    paths.add(ap, "--ov002", os.path.join(paths.EXTRACTED, "fpg", "002.bin"), "overlay 002 as stored (compressed)")
    paths.add(ap, "--font", os.path.join(paths.EXTRACTED, "fpg", "128.bin"), "story font (FPG 128)")
    args = ap.parse_args()
    ov = decompress(open(args.ov002, "rb").read())
    out, syms = patch_overlay(ov, open(args.font, "rb").read())
    for k in ("hook", "vwf_char", "TABLE", "T_BOX", "GLYPHBUF", "TILEBUF"):
        print(k, hex(syms[k]))
