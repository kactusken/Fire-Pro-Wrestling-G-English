#!/usr/bin/env python3
"""Re-enable the developer mode-select menu (EXE 0x80017974) for debug builds.

The retail EXE still holds the menu (" < SELECT >", 0x800101fc) and the code
for each mode, but nothing calls it. Its number input 0x80015270 and the debug
printf 0x800146e8 are stubs: on the dev kit both went to the PC console.

This patch:
- reuses the hidden combo check in the main loop (0x8001c6e4: after the
  title screen, held pad == 0x4816 = L1+R2+Triangle+Down+Start opens the
  test-pattern viewer) but tests for Select instead, so holding Select while
  pressing Start or Circle on the title screen opens the menu (the viewer is
  still reachable as mode 13). The check runs only after the title has faded
  out and its music stopped, by which time players have let go, so the title
  (ov2 0x8005d238) now records the held buttons at the Start press (LATCH)
  and the check reads that record;
- replaces the menu's input call with a pad-driven selector: Up/Down picks,
  Circle or Start runs. The selection is printed through the BIOS printf
  (A0h:3Fh), which DuckStation shows as TTY output in its log;
- forwards the printf stubs 0x800146e8 and 0x80015280 to the BIOS printf, but
  only between entering the menu and choosing EXIT, so normal play (which
  calls them too) stays quiet.

Code goes into dead EXE code: a second, unreferenced debug select
(0x8001ef00, "yone process select") and an uncalled function after it; the
mode names go where that select's banner and jump table were (0x80010a10).

The yone select ran four test programs in overlay 003, which nothing else
loads. They are on the menu as ids 0x300-0x303 (OV3_ENTRIES), run by the
selector itself: load overlay 003, call the entry, show the menu again. All
four leave with Square+Cross held. One is the shell of a developer move and
animation editor ("GED", "anime tool"); in retail its per-frame calls are
empty stubs, so patch_ov003 wires the editor's init and update into them.
Modes 7, 20, 21, 70 and 80 read or write files on the developers' PC and are
left out; the menu now branches past the 20/21 cases, and their code holds
the selector's tables.
"""
import struct

import codepatch
from mips_asm import assemble

EXE_BASE = 0x80010000
AREA = (0x8001EF00, 0x8001F0C8)
DATA_AREA = (0x80017C1C, 0x80017C84)  # DOS LOAD/SAVE cases 0x20, 0x21
NAMES_AREA = (0x80010A10, 0x80010AE4)  # yone select banner and jump table
LOAD_OVERLAY = 0x800128FC  # (overlay number, load address)
FRAME = 0x80014700        # wait for vsync, read pads
PAD_PRESSED = 0x80054134  # u16, buttons newly pressed this frame

MODES = [
    (0x00, "00 DATABASE"),
    (0x02, "02 RING"),
    (0x03, "03 SOUND TEST"),
    (0x04, "04 FR DEBUG"),
    (0x05, "05 BATTLE SELECT"),
    (0x06, "06 HIT EFFECT"),
    (0x08, "08 TITLE"),
    (0x10, "10 EDIT"),
    (0x11, "11 MC EDIT LOAD"),
    (0x12, "12 ?"),
    (0x13, "13 TEST PATTERNS"),
    (0x40, "40 STORY ?"),
    (0x200, "200 FLAGS ?"),
    (0x300, "OV3 ANIME TOOL"),
    (0x301, "OV3 TEST 11"),
    (0x302, "OV3 TEST 12"),
    (0x303, "OV3 SE TEST"),
    (-1, "EXIT"),
]
# overlay 003 programs, by id - 0x300 (yone select cases 0x10, 0x11, 0x12, 0)
OV3_ENTRIES = [0x800747B0, 0x8007610C, 0x800758C0, 0x800769D0]

# (address, original word, replacement source)
PATCHES = [
    # main loop: trigger = Select held (was held == 0x4816);
    # ov5 test-pattern viewer -> debug menu
    (0x8001C6C8, 0x24114816, "addiu s1, zero, 0x100"),
    # s0 = 0x80010000; 0x8001c6e8 stays a nop (load delay slot)
    (0x8001C6E4, 0x9642410A, "lhu v0, %lo(HELD)(s0)"),
    (0x8001C6F8, 0x0C004A3F, "jal 0x80017974"),
    (0x8001C6FC, 0x24040005, "nop"),
    (0x8001C700, 0x0C017186, "nop"),
    # debug menu: number input stub -> selector
    (0x800179B4, 0x0C00549C, "jal SEL"),
    # printf stubs -> gated BIOS printf
    (0x800146E8, 0xAFA40000, "j PRINTF"),
    (0x800146EC, 0xAFA50004, "nop"),
    (0x80015280, 0x03E00008, "j PRINTF"),
    # debug menu: skip the DOS LOAD/SAVE cases (v0 = next case value, 0x40)
    (0x80017C14, 0x1602000C, "b 0x80017C84"),
    (0x80017C18, 0x24020021, "addiu v0, zero, 0x40"),
]

SOURCE = """
FLAG:   .half 0, 0
IDX:    .half 0, 0
PRINTF: lui   t0, %hi(FLAG)
        lw    t0, %lo(FLAG)(t0)
        nop
        beqz  t0, pret
        li    t2, 0xA0
        jr    t2
        li    t1, 0x3F
pret:   jr    ra
        nop
SEL:    addiu sp, sp, -0x20
        sw    ra, 0x10(sp)
        sw    s0, 0x14(sp)
        sw    s1, 0x18(sp)
        li    t0, 1
        lui   at, %hi(FLAG)
        sw    t0, %lo(FLAG)(at)
        lui   a0, %hi(HELP)
        jal   PRINTF
        addiu a0, a0, %lo(HELP)
show:   lui   t0, %hi(IDX)
        lw    s0, %lo(IDX)(t0)
        lui   a1, %hi(NAMES)
        addiu a1, a1, %lo(NAMES)
        move  t1, s0
skip:   beqz  t1, found
        nop
skip1:  lbu   t2, 0(a1)
        addiu a1, a1, 1
        bnez  t2, skip1
        nop
        b     skip
        addiu t1, t1, -1
found:  lui   a0, %hi(FMT)
        jal   PRINTF
        addiu a0, a0, %lo(FMT)
wait:   jal   FRAME
        nop
        lui   t0, %hi(PAD_PRESSED)
        lhu   v0, %lo(PAD_PRESSED)(t0)
        nop
        andi  t1, v0, 0x4000
        bnez  t1, down
        andi  t1, v0, 0x1000
        bnez  t1, up
        andi  t1, v0, 0x0820
        beqz  t1, wait
        sll   t1, s0, 1
        lui   v0, %hi(IDS)
        addu  v0, v0, t1
        lh    v0, %lo(IDS)(v0)
        nop
        slti  t1, v0, 0x300
        bnez  t1, mode
        sll   t1, v0, 2
        lui   t0, %hi(OV3 - 0xC00)
        addu  t0, t0, t1
        lw    s1, %lo(OV3 - 0xC00)(t0)
        lui   a1, 0x8001
        lw    a1, 0(a1)                  ; overlay load address
        jal   LOAD_OVERLAY
        li    a0, 3
        jalr  s1
        nop
        b     show
        nop
mode:   li    t0, -1
        bne   v0, t0, ret
        nop
        lui   at, %hi(FLAG)
        sw    zero, %lo(FLAG)(at)
ret:    lw    ra, 0x10(sp)
        lw    s0, 0x14(sp)
        lw    s1, 0x18(sp)
        jr    ra
        addiu sp, sp, 0x20
down:   addiu s0, s0, 1
        slti  t1, s0, COUNT
        bnez  t1, store
        nop
        b     store
        move  s0, zero
up:     bnez  s0, store
        addiu s0, s0, -1
        addiu s0, zero, COUNT-1
store:  lui   at, %hi(IDX)
        b     show
        sw    s0, %lo(IDX)(at)
OV3:    .word {ov3}
; overlay 003 editor, each frame: unless port 2 holds a mouse, its D-pad
; becomes that port's mouse movement (2 per frame; the editor doubles it)
MOUSE:  lui   t0, 0x8005
        lbu   t2, 0x413E(t0)             ; port 2 device type (1 = mouse)
        lhu   t1, 0x410C(t0)             ; port 2 held buttons
        li    t4, 1
        bne   t2, t4, mpad
        srl   t3, t1, 13                 ; right
        jr    ra
        nop
mpad:
        andi  t3, t3, 1
        srl   t4, t1, 15                 ; left
        subu  t3, t3, t4
        sll   t3, t3, 1
        sb    t3, 0x4123(t0)             ; port 2 mouse dx
        srl   t3, t1, 14                 ; down
        andi  t3, t3, 1
        srl   t4, t1, 12                 ; up
        andi  t4, t4, 1
        subu  t3, t3, t4
        sll   t3, t3, 1
        jr    ra
        sb    t3, 0x412A(t0)             ; port 2 mouse dy
"""

NAMES = """
NAMES:  .byte {names}
"""

DATA = """
IDS:    .half {ids}
FMT:    .byte {fmt}
HELP:   .byte {help}
        .align 2
LATCH:  lui   t0, 0x8005
        lhu   t0, 0x410A(t0)
        lui   at, %hi(HELD)
        andi  t0, t0, 0x100              ; Select only: the check compares with 0x100
        j     0x80013FE0
        sh    t0, %lo(HELD)(at)
HELD:   .half 0, 0
"""


def _bytes(s):
    return ", ".join(str(b) for b in s.encode("ascii") + b"\0")


def assemble_blob():
    data, symbols = assemble(DATA.format(
        ids=", ".join(str(i & 0xFFFF) for i, _ in MODES),
        fmt=_bytes("> %s\n"),
        help=_bytes("\nDEBUG MENU (Up/Down, O)\n")), DATA_AREA[0])
    names, more = assemble(NAMES.format(names=", ".join(_bytes(n) for _, n in MODES)),
                           NAMES_AREA[0])
    symbols.update(more)
    symbols.update(FRAME=FRAME, PAD_PRESSED=PAD_PRESSED, COUNT=len(MODES),
                   LOAD_OVERLAY=LOAD_OVERLAY)
    code, symbols = assemble(SOURCE.format(ov3=", ".join(str(a) for a in OV3_ENTRIES)),
                             AREA[0], symbols)
    for blob, (lo, hi) in ((code, AREA), (data, DATA_AREA), (names, NAMES_AREA)):
        if lo + len(blob) > hi:
            raise SystemExit(f"debug menu: {len(blob)} bytes at {lo:#x}; only {hi - lo} are free")
    return code, data, names, symbols


OV002_BASE = 0x8005A718
OV002_PATCH = (0x8005D238, 0x0C004FF8, "jal LATCH")  # title: Start pressed, jal 0x80013fe0


def patch_ov002(ov):
    """ov: bytearray of the decompressed overlay 002 (title)."""
    *_, symbols = assemble_blob()
    addr, old, src = OV002_PATCH
    o = addr - OV002_BASE
    if struct.unpack_from("<I", ov, o)[0] != old:
        raise SystemExit(f"overlay 002 differs at {addr:#x} (debug menu patch)")
    ov[o:o + 4] = assemble(src, addr, symbols)[0]


def patch_exe(exe):
    """exe: bytearray of SLPS_020.65 (with its 0x800 header)."""
    def off(a):
        return a - EXE_BASE + 0x800
    code, data, names, symbols = assemble_blob()
    # the areas must still hold the original dead code and data (no other patch uses them)
    if struct.unpack_from("<I", exe, off(AREA[0]))[0] != 0x27BDFFE0:
        raise SystemExit("EXE differs at the debug menu code area")
    if exe[off(NAMES_AREA[0]):off(NAMES_AREA[0]) + 20] != b"\nyone process select":
        raise SystemExit("EXE differs at the yone select banner")
    exe[off(AREA[0]):off(AREA[0]) + len(code)] = code
    exe[off(DATA_AREA[0]):off(DATA_AREA[0]) + len(data)] = data
    exe[off(NAMES_AREA[0]):off(NAMES_AREA[0]) + len(names)] = names
    for addr, old, src in PATCHES:
        if struct.unpack_from("<I", exe, off(addr))[0] != old:
            raise SystemExit(f"EXE differs at {addr:#x} (debug menu patch)")
        word, _ = assemble(src, addr, symbols)
        exe[off(addr):off(addr) + 4] = word


# Overlay 003, the GED harness (0x800747b0): it sets up the editor's buffers
# (GEDDB0/1, GEDFONT = FPG 276, ...) and then each frame calls two empty
# stubs where the editor was called. The editor's own entry points are
# 0x8005f0a0 (init), 0x8005f154 (per frame) and 0x8005f134 (exit); nothing
# calls them. Its 8x8 text (0x80074ff0) takes glyph slots from a counter
# (0x8007db74) and links them into the order table at 0x8007db6c; only the
# uncalled 0x80074f0c(ot) resets the counter and sets that table, so without
# it the text never shows and soon runs past its buffer over the stack.
# Init goes in place of the frame wait after the harness setup; each frame,
# after the buffer swap, TEXT_RESET (written over 0x80074f0c) points the text
# at this frame's order table (the one the harness's own sprites use), then
# the editor runs. TEXT_RESET ends in MOUSE (EXE): the editor takes mouse
# movement and clicks from controller slot +0x28 - 1, which it sets to 5 each
# frame: port 2 behind a multitap in port 1, presumably the developers' setup.
# It is set to 2 (port 2, no multitap), and MOUSE turns a pad in port 2 into
# a mouse: D-pad moves, Cross and Circle click (the editor's own button masks).
# The glyph code itself is broken in retail: it keeps only char & 0x50 and
# never sets u, so every letter is one of four wrong glyphs and spaces are
# drawn too. FPG 276 is a 16x16 grid of 8x8 ASCII glyphs at v 0x80 of the
# texture page; GLYPH_UV (written over the editor's uncalled exit routine)
# gives u = (c & 15) * 8 and v = 0x80 + (c >> 4) * 8. The harness setup also
# uploads FPG 250 (hit-effect sprites for its own effect test) at (961, 380),
# over the font it has just put at (960, 384); that upload is skipped.
GLYPH_UV = 0x8005F134
GLYPH_UV_SRC = """
        andi  v1, s2, 0xF
        sll   v1, v1, 3                  ; u
        andi  t0, s2, 0xF0
        jr    ra
        srl   t0, t0, 1                  ; v - 0x80
"""
OV3_BASE = 0x8005A718
TEXT_RESET = """
        lui   v0, 0x8008
        lw    a0, -0x2498(v0)            ; editor state
        sw    zero, -0x248C(v0)          ; glyph count
        lw    a0, 0(a0)                  ; this frame's draw buffer
        sw    zero, -0x2490(v0)          ; colour
        lw    a0, 0x1364(a0)             ; its order table
        sw    zero, -0x2484(v0)          ; cursor x, y
        sw    zero, -0x2480(v0)
        j     MOUSE
        sw    a0, -0x2494(v0)
"""
OV3_PATCHES = [
    (0x800747C4, 0x0C0051C0, "jal 0x80074B18"),   # was jal 0x80014700 (frame wait)
    (0x80074B18, 0x03E00008, "j 0x8005F0A0"),     # stub 2 -> editor init
    (0x800747D8, 0x0C01D2C4, "jal 0x80074F0C"),   # was jal 0x80074B10 (stub 1)
    (0x800747E0, 0x0C01D2C6, "jal 0x8005F154"),   # was jal 0x80074B18 (stub 2)
    (0x800749B8, 0x0C0053B2, "nop"),              # was jal 0x80014ec8 (upload FPG 250)
    (0x8005F42C, 0x24020005, "addiu v0, zero, 2"),  # mouse slot: port 2
    (0x80075064, 0x30920050, "andi s2, a0, 0xFF"),  # character (was & 0x50)
    (0x80075078, 0x30920050, "andi s2, a0, 0xFF"),
    (0x8007510C, 0x00001821, "jal 0x8005F134"),   # was move v1, zero (u = 0)
    (0x8007511C, 0x00121042, "move v0, t0"),      # was srl v0, s2, 1
]


def patch_ov003(ov):
    """ov: bytearray of the decompressed overlay 003."""
    for addr, old, src in OV3_PATCHES:
        o = addr - OV3_BASE
        if struct.unpack_from("<I", ov, o)[0] != old:
            raise SystemExit(f"overlay 003 differs at {addr:#x} (debug menu patch)")
        ov[o:o + 4] = assemble(src, addr, {})[0]
    o = GLYPH_UV - OV3_BASE
    if struct.unpack_from("<I", ov, o)[0] != 0x27BDFFE8:
        raise SystemExit("overlay 003 differs at the editor exit routine (debug menu patch)")
    code = assemble(GLYPH_UV_SRC, GLYPH_UV, {})[0]
    ov[o:o + len(code)] = code
    o = 0x80074F0C - OV3_BASE
    if struct.unpack_from("<I", ov, o + 0x28)[0] != 0xAC44DB6C:   # sw a0, -0x2494(v0)
        raise SystemExit("overlay 003 differs at the text reset (debug menu patch)")
    code = assemble(TEXT_RESET, 0x80074F0C, {"MOUSE": assemble_blob()[3]["MOUSE"]})[0]
    assert len(code) <= 0x2C
    ov[o:o + len(code)] = code


# Test option (build.py --route5, implies the debug menu): the graduation offer
# (scene 3, script opcode 0x21 at ov2 0x8005e848) always comes out as route 5,
# the cut New Japan offer with Liger. Jump to scene 3 with debug mode 4.
#   bne v1, v0, 0x8005e9a0 / addiu v1, zero, 6   (non-heavyweight -> 6)
# becomes
#   b 0x8005e9a0 / addiu v1, zero, 5
ROUTE5 = [(0x8005E8C8, 0x14620035, 0x10000035), (0x8005E8CC, 0x24030006, 0x24030005)]


def patch_route5(ov, base=0x8005A718):
    codepatch.patch_words(ov, base, ROUTE5, "route 5 test")


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description="Assemble the debug menu code and report how much of "
                                        "its EXE space it uses (a self-check; build.py applies it).").parse_args()
    code, data, names, symbols = assemble_blob()
    print(f"code {len(code)} of {AREA[1] - AREA[0]} bytes, "
          f"data {len(data)} of {DATA_AREA[1] - DATA_AREA[0]}, "
          f"names {len(names)} of {NAMES_AREA[1] - NAMES_AREA[0]}; "
          f"SEL {symbols['SEL']:#x}, PRINTF {symbols['PRINTF']:#x}")
