#!/usr/bin/env python3
"""Tiled ASCII rendering for menu text (EXE renderer 0x80015f5c).

Menu text is drawn a whole string at a time. Every glyph takes one 12x14
4bpp cell ("slot"); a window shows at most its slot budget, which was sized
for Japanese, so English got cut off after a few letters.

The renderer's ASCII path calls the glyph draw 0x80015c90 at 0x80016094.
We redirect that call to `hook`. At the first letter of a run of ASCII
letters it reads ahead through the string, lets the game draw each letter
into a private scratch cell (so shadow/outline effects apply), blends the
letters into private 12 px tiles at their pen positions, and copies each
finished tile into the staging buffer exactly once. The caller's string
pointer and cell count are then advanced past the run.

Writing only finished tiles matters: the game queues each frame's cell
uploads and the GPU can read the staging buffer while the next frame is
being drawn, so a cell must never hold a half-built image.
Tiles past the window's cell budget are dropped: text that is too long is
cut off rather than written into the next window's cells (or past the end
of the cell pool, which can crash the game).
Spaces are narrowed from 8 to SPACE px (0x80016108).

The hook is appended to each overlay that uses the menu text API
(000, 001, 004, 005), assembled at that overlay's original end address
(anything an overlay adds, like a string pool, goes after the hook).
The renderer's ASCII branch is rewritten to look up the resident
overlay's end in the EXE table at 0x80010000 (indexed by the overlay ID
word at 0x8005A718) and call it. Only overlays call that API, so one of
them is always resident when the hook runs. (An earlier version used one
fixed address, but zero-padding every overlay up to it cost about 2 KB
of compressed space each.)
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mips_asm import assemble  # noqa: E402

OVERLAY_BASE = 0x8005A718
OVERLAY_LIMIT = 0x80092000
OVERLAY_ID = 0x8005A718         # first word of each overlay: its ID (4..9)
END_TABLE = 0x80010000          # EXE: base, then end address of overlay ID 4, 5, ...
MENU_OVERLAYS = ("000", "001", "004", "005")

EXE_LOAD = 0x80010000
EXE_HEADER = 0x800
GLYPH_DRAW = 0x80015C90
CALL_SITE = 0x80016094          # jal 0x80015c90 ; addiu s4, s4, 1
ASCII_BRANCH = 0x80016058       # .. 0x8001609c: convert byte, draw, j 0x80016790
SPACE_SITE = 0x80016108         # addiu v0, v0, 8
SPACE = 4
FW_TABLE = 0x80048CDC           # ASCII 0x28.. -> full-width SJIS pairs (EXE)

CELL_W, CELL_H, ROW_BYTES = 12, 14, 6
IMAGE_BYTES = CELL_H * ROW_BYTES  # 84
PRIM_BYTES = 0x2C

# Replaces the renderer's ASCII branch (a3 = v0 = the string byte) and holds
# `lookup`, which the measure patch below shares.
ASCII_BRANCH_ASM = """
    sltiu v0, v0, 0xa1
    bnez  v0, conv
    move  a2, s1
    addiu a3, a3, -0x20          ; half-width kana follow the ASCII range
conv:
    bal   lookup
    addiu a3, a3, -0x28          ; table index (the hook masks it)
    addiu s4, s4, 1              ; (load delay after lookup)
    addiu t9, t9, 8              ; draw hook = overlay end + 8
    jalr  t9
    nop
    j     0x80016790
    nop
; lookup: t9 = original end of the resident overlay (= hook blob). Uses t8.
lookup:
    lui   t9, %hi(OVERLAY_ID)
    lw    t9, %lo(OVERLAY_ID)(t9)
    lui   t8, %hi(END_TABLE)
    sll   t9, t9, 2
    addu  t8, t8, t9
    jr    ra
    lw    t9, %lo(END_TABLE-12)(t8)
"""

# Replaces the non-SJIS case of the cell counter 0x800167d0 (v1 = byte,
# a0 = next byte, t3 = cells). That function sizes windows automatically
# (EXE 0x80017424) and counted one cell per ASCII letter, which doubled the
# windows on English screens and overran the cell pool (Skill Edit crashed).
# It is a leaf function, so ra is kept in t7 around `lookup`.
MEASURE_SITE_ASM = """
    move  t7, ra
    bal   LOOKUP
    nop
    nop                          ; load delay: lookup loads t9 in its last slot
    jr    t9                     ; measure = overlay end + 0
    move  ra, t7
    nop
"""
MEASURE_SITE = 0x80016830        # .. 0x80016848; 0x8001684c is a branch target
MEASURE_NEXT = 0x80016BAC        # loop: next byte
MEASURE_CODE = 0x8001685C        # '#' control code parser

HOOK_ASM = """
entry:
    b     measure                ; overlay end + 0: cell counter
    nop
; overlay end + 8: draw
; hook(a3 = full-width table index, a2 = text context)
; Caller (renderer 0x80015f5c): s0 = next string byte, s1 = context,
; s4 = cells used (already incremented for this glyph).
hook:
    andi  a3, a3, 0xff
    sll   a3, a3, 1
    lui   t3, %hi(FW_TABLE)
    addu  t3, t3, a3
    lbu   a0, %lo(FW_TABLE)(t3)
    lbu   a1, %lo(FW_TABLE+1)(t3)
    addiu sp, sp, -0x40
    sw    ra, 0x3c(sp)
    sw    s0, 0x10(sp)
    sw    s1, 0x14(sp)
    sw    s2, 0x18(sp)
    sw    s3, 0x1c(sp)
    sw    s5, 0x20(sp)
    sw    s6, 0x24(sp)
    sw    s7, 0x28(sp)
    lbu   t0, -1(s0)             ; the byte being drawn
    move  s7, s0                 ; read pointer for look-ahead
    sltiu t1, t0, 0x80
    bnez  t1, ascii
    nop
    jal   GLYPH_DRAW             ; half-width kana: draw as usual
    nop
    b     restore
    nop
ascii:
    move  s2, a2                 ; context
    lw    s3, 0x30(s2)           ; pool
    lh    s5, 0x18(s2)           ; tile x
    lh    s6, 0x1a(s2)           ; line y
    move  s1, zero               ; cells written
    ; cells left in this window's budget: tiles past it are dropped, so long
    ; text is cut off instead of spilling into other windows (or past the pool)
    lh    t0, 0x118(s3)          ; window index (set by the wrapper 0x80016cf8)
    lw    t1, 0x38(s2)           ; window array
    sll   t0, t0, 6
    addu  t1, t1, t0
    lh    t0, 6(t1)              ; budget
    addiu t1, s4, -1             ; cells this string used before the run
    subu  t0, t0, t1
    sw    t0, 0x38(sp)
    sw    a0, 0x30(sp)
    sw    a1, 0x34(sp)
    lui   a0, %hi(CUR)
    jal   clear2                 ; clear CUR and NEXT, reset used flags
    addiu a0, a0, %lo(CUR)
    lw    a0, 0x30(sp)
    b     draw_char
    lw    a1, 0x34(sp)

next_char:
    lbu   t0, 0(s7)
    nop
    addiu t1, t0, -0x28
    sltiu t2, t1, 0x57
    beqz  t2, finish             ; letters, digits and the punctuation the renderer converts
    sll   t1, t1, 1
    lui   t3, %hi(FW_TABLE)
    addu  t3, t3, t1
    lbu   a0, %lo(FW_TABLE)(t3)
    lbu   a1, %lo(FW_TABLE+1)(t3)
    addiu s7, s7, 1
draw_char:
    ; draw into the scratch cell, not the staging buffer
    lw    t0, 8(s3)
    lw    t1, 4(s3)
    lui   t9, %hi(SAVE8)
    sw    t0, %lo(SAVE8)(t9)
    sw    t1, %lo(SAVE4)(t9)
    lui   t0, %hi(SCRATCH)
    addiu t0, t0, %lo(SCRATCH)
    sw    t0, 8(s3)
    lui   t1, %hi(SCRPRIM)
    addiu t1, t1, %lo(SCRPRIM)
    sw    t1, 4(s3)
    lh    s0, 0x18(s2)           ; pen x of this glyph
    jal   GLYPH_DRAW
    move  a2, s2
    lui   t9, %hi(SAVE8)
    lw    t0, %lo(SAVE8)(t9)
    lw    t1, %lo(SAVE4)(t9)
    sw    t0, 8(s3)
    sw    t1, 4(s3)
advance:
    subu  t8, s0, s5             ; d = pen - tile x
    slti  t0, t8, 12
    bnez  t0, place
    nop
    jal   flush_shift            ; tile full: emit CUR, NEXT becomes CUR
    nop
    b     advance
    nop
place:
    lui   t0, %hi(SCRPRIM)
    lh    t0, %lo(SCRPRIM+2)(t0)
    nop
    subu  a3, t0, s6             ; dy (lowercase is drawn 1 px lower)
    sw    a3, 0x2c(sp)
    lui   a0, %hi(SCRATCH)
    addiu a0, a0, %lo(SCRATCH)
    lui   a1, %hi(CUR)
    addiu a1, a1, %lo(CUR)
    jal   blend
    move  a2, t8
    subu  t8, s0, s5
    blez  t8, wrapped
    lw    a3, 0x2c(sp)
    lui   a0, %hi(SCRATCH)
    addiu a0, a0, %lo(SCRATCH)
    lui   a1, %hi(NEXT)
    addiu a1, a1, %lo(NEXT)
    jal   blend
    addiu a2, t8, -12
wrapped:
    lh    t0, 0x1a(s2)
    nop
    beq   t0, s6, next_char      ; stop if the glyph draw wrapped the line
    nop

finish:
    jal   flush_shift            ; emit CUR (if used) ...
    nop
    jal   flush_shift            ; ... and NEXT (if used)
    nop
    addu  s4, s4, s1
    addiu s4, s4, -1             ; caller already counted one cell
    sw    s7, 0x10(sp)           ; caller resumes after the consumed bytes
restore:
    lw    ra, 0x3c(sp)
    lw    s0, 0x10(sp)
    lw    s1, 0x14(sp)
    lw    s2, 0x18(sp)
    lw    s3, 0x1c(sp)
    lw    s5, 0x20(sp)
    lw    s6, 0x24(sp)
    lw    s7, 0x28(sp)
    jr    ra
    addiu sp, sp, 0x40

; flush_shift: if CUR is used, copy it to the staging buffer as a cell at
; (s5, s6); then NEXT -> CUR, clear NEXT, s5 += 12.
flush_shift:
    lui   t9, %hi(CUR_USED)
    lw    t0, %lo(CUR_USED)(t9)
    nop
    beqz  t0, fs_shift
    lw    t1, 8(s3)              ; staging write pointer
    lw    t2, 0x38(sp)           ; hook frame (flush_shift has none)
    nop
    slt   t2, s1, t2
    beqz  t2, fs_shift           ; over budget: drop the tile
    nop
    lui   t2, %hi(CUR)
    addiu t2, t2, %lo(CUR)
    addiu t3, t2, 84
fs_copy:
    lw    t4, 0(t2)
    addiu t2, t2, 4
    sw    t4, 0(t1)
    bne   t2, t3, fs_copy
    addiu t1, t1, 4
    sw    t1, 8(s3)
    lw    t1, 4(s3)              ; cell record
    nop
    sh    s5, 0(t1)
    sh    s6, 2(t1)
    addiu t1, t1, 0x2c
    sw    t1, 4(s3)
    addiu s1, s1, 1
fs_shift:
    lui   t2, %hi(CUR)
    addiu t2, t2, %lo(CUR)
    addiu t3, t2, 84
fs_move:
    lw    t4, 84(t2)             ; NEXT follows CUR
    sw    zero, 84(t2)
    sw    t4, 0(t2)
    addiu t2, t2, 4
    bne   t2, t3, fs_move
    nop
    lw    t0, %lo(NEXT_USED)(t9)
    sw    zero, %lo(NEXT_USED)(t9)
    sw    t0, %lo(CUR_USED)(t9)
    jr    ra
    addiu s5, s5, 12

; clear2(a0 = CUR): zero CUR and NEXT, clear both used flags
clear2:
    addiu t1, a0, 168
c2_loop:
    sw    zero, 0(a0)
    addiu a0, a0, 4
    bne   a0, t1, c2_loop
    nop
    lui   t9, %hi(CUR_USED)
    sw    zero, %lo(CUR_USED)(t9)
    jr    ra
    sw    zero, %lo(NEXT_USED)(t9)

; blend(a0 = src cell, a1 = dst cell, a2 = column offset, a3 = row offset)
; dst[r+a3][c+a2] = max(dst, src[r][c]) for destinations inside the cell.
; Marks the destination used when anything non-zero is written.
blend:
    move  t9, zero               ; r
bd_row:
    addu  t8, t9, a3
    sltiu t7, t8, 14
    beqz  t7, bd_next_row
    move  t6, zero               ; c
bd_col:
    addu  t5, t6, a2             ; dst col
    sltiu t7, t5, 12
    beqz  t7, bd_skip
    sll   t4, t9, 1
    addu  t4, t4, t9
    sll   t4, t4, 1
    addu  t4, t4, a0
    srl   t3, t6, 1
    addu  t4, t4, t3
    lbu   t3, 0(t4)
    andi  t4, t6, 1
    sll   t4, t4, 2
    srlv  t3, t3, t4
    andi  t3, t3, 0xf
    beqz  t3, bd_skip
    sll   t4, t8, 1
    addu  t4, t4, t8
    sll   t4, t4, 1
    addu  t4, t4, a1
    srl   t2, t5, 1
    addu  t4, t4, t2
    lbu   t2, 0(t4)
    andi  t1, t5, 1
    sll   t1, t1, 2
    srlv  t0, t2, t1
    andi  t0, t0, 0xf
    sltu  v0, t0, t3
    beqz  v0, bd_mark
    addiu v1, zero, 0xf
    sllv  v1, v1, t1
    xori  v1, v1, 0xff
    and   t2, t2, v1
    sllv  t3, t3, t1
    or    t2, t2, t3
    sb    t2, 0(t4)
bd_mark:
    lui   t0, %hi(CUR)
    addiu t0, t0, %lo(CUR)
    lui   t1, %hi(CUR_USED)
    beq   a1, t0, bd_cur
    addiu t2, zero, 1
    b     bd_skip
    sw    t2, %lo(NEXT_USED)(t1)
bd_cur:
    sw    t2, %lo(CUR_USED)(t1)
bd_skip:
    addiu t6, t6, 1
    sltiu t7, t6, 12
    bnez  t7, bd_col
    nop
bd_next_row:
    addiu t9, t9, 1
    sltiu t7, t9, 14
    bnez  t7, bd_row
    nop
    jr    ra
    nop

; measure: count the cells of one character or ASCII run for 0x800167d0,
; the way `hook` draws them: a run of 0x28..0x7E takes ceil(width / 12).
measure:
    addiu t6, v1, -0x28
    sltiu t6, t6, 0x57
    bnez  t6, m_ascii
    addiu t6, v1, 0x5f
    andi  t6, t6, 0xff
    sltiu t6, t6, 0x3f
    beqz  t6, m_other
    nop
    j     MEASURE_NEXT           ; half-width kana: one cell
    addiu t3, t3, 1
m_other:
    addiu t6, zero, 0x23
    bne   v1, t6, m_skip
    nop
    j     MEASURE_CODE           ; control code: the original parser
    nop
m_skip:
    j     MEASURE_NEXT
    nop
m_ascii:
    addiu t8, a0, -1             ; run start
    move  t9, zero               ; width
m_loop:
    lbu   t6, 0(t8)
    nop
    addiu t7, t6, -0x28
    sltiu t7, t7, 0x57
    beqz  t7, m_end
    lui   t7, %hi(WIDTHS-0x28)
    addu  t7, t7, t6
    lbu   t7, %lo(WIDTHS-0x28)(t7)
    addiu t8, t8, 1
    b     m_loop
    addu  t9, t9, t7
m_end:
    addiu t9, t9, 12             ; +1: the drop shadow reaches 1 px past the advance
    addiu t6, zero, 12
    divu  t9, t6
    mflo  t9
    addu  t3, t3, t9
    j     MEASURE_NEXT
    move  a0, t8

    .align 2
CUR:
    .byte """ + ", ".join(["0"] * 84) + """
NEXT:
    .byte """ + ", ".join(["0"] * 84) + """
SCRATCH:
    .byte """ + ", ".join(["0"] * 84) + """
SCRPRIM:
    .byte """ + ", ".join(["0"] * 0x2C) + """
CUR_USED:
    .half 0, 0
NEXT_USED:
    .half 0, 0
SAVE8:
    .half 0, 0
SAVE4:
    .half 0, 0
WIDTHS:
    .byte WIDTH_BYTES
"""


def ascii_widths(font):
    """Pen advance of ASCII 0x28..0x7E in the (patched) menu font 009.
    Menu contexts use no extra letter spacing (ctx+0x2a = 0, ov004 0x80063c88)."""
    from font import ascii_sjis, sjis_linear
    width_off = struct.unpack_from("<I", font, 8)[0]
    out = []
    for c in range(0x28, 0x7F):
        idx = sjis_linear(*ascii_sjis(c))
        out.append(font[width_off + idx] if idx < 0x2F0 else 12)
    return out


def hook_blob(base, widths):
    syms = {"GLYPH_DRAW": GLYPH_DRAW, "FW_TABLE": FW_TABLE,
            "MEASURE_NEXT": MEASURE_NEXT, "MEASURE_CODE": MEASURE_CODE}
    asm = HOOK_ASM.replace("WIDTH_BYTES", ", ".join(str(w) for w in widths))
    code, syms = assemble(asm, base, syms)
    if syms["hook"] != base + 8:
        raise SystemExit("draw hook must be at overlay end + 8")
    return code, syms


def overlay_end(exe, ov):
    """Original end address of overlay image `ov` (from the EXE end table)."""
    ov_id = struct.unpack_from("<I", ov, 0)[0]
    return struct.unpack_from("<I", exe, END_TABLE - 12 + 4 * ov_id - EXE_LOAD + EXE_HEADER)[0]


def append_hook(ov, exe, widths):
    """Append the hook at the overlay's original end (ov must not have grown yet).
    widths: ascii_widths() of the patched menu font."""
    end = overlay_end(exe, ov)
    if OVERLAY_BASE + len(ov) != end:
        raise SystemExit(f"overlay is {len(ov):#x} bytes, expected it to end at {end:#x}")
    code, _ = hook_blob(end, widths)
    return bytes(ov) + code


def patch_exe(exe):
    exe = bytearray(exe)
    def word(a):
        return struct.unpack_from("<I", exe, a - EXE_LOAD + EXE_HEADER)[0]
    def put(a, w):
        struct.pack_into("<I", exe, a - EXE_LOAD + EXE_HEADER, w)
    expect_call = (3 << 26) | ((GLYPH_DRAW >> 2) & 0x3FFFFFF)
    if word(CALL_SITE) != expect_call or word(SPACE_SITE) != 0x24420008 or word(0x8001609C) != 0x080059E4:
        raise SystemExit("EXE differs at the menu hook sites")
    if word(MEASURE_SITE) != 0x2C420057 or word(0x8001684C) != 0x08005AEB:
        raise SystemExit("EXE differs at the cell counter")
    code, syms = assemble(ASCII_BRANCH_ASM, ASCII_BRANCH,
                          {"OVERLAY_ID": OVERLAY_ID, "END_TABLE": END_TABLE})
    if len(code) > 0x800160A4 - ASCII_BRANCH:
        raise SystemExit("ASCII branch replacement too long")
    code += bytes(0x800160A4 - ASCII_BRANCH - len(code))  # nop padding
    for i in range(0, len(code), 4):
        put(ASCII_BRANCH + i, struct.unpack_from("<I", code, i)[0])
    code, _ = assemble(MEASURE_SITE_ASM, MEASURE_SITE, {"LOOKUP": syms["lookup"]})
    if len(code) != 0x8001684C - MEASURE_SITE:
        raise SystemExit("cell counter patch has the wrong size")
    for i in range(0, len(code), 4):
        put(MEASURE_SITE + i, struct.unpack_from("<I", code, i)[0])
    put(SPACE_SITE, 0x24420000 | SPACE)
    return bytes(exe)


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description="Assemble the menu tiling hook and report its size "
                                        "(a self-check; build.py applies it).").parse_args()
    code, syms = hook_blob(0x80089744, [8] * 87)
    print(f"hook {len(code)} bytes (assembled for ov001 at 0x80089744); CUR {syms['CUR']:#x}")
