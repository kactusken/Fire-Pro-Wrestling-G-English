#!/usr/bin/env python3
"""Start with everything unlocked (EXE patch, applied by build.py unless --no-unlock).

Save/system block S = *(0x800541b4):
  S+0x13cd3..0x13ceb  194-bit set of locked wrestlers (25 start locked)
  S+0x13cec           story cleared: Title Match, FR:GOOD/BAD music, team presets
                      33-42, Options > Staff Credits, higher story edit points
  S+0x13ced           Edit Ranking reward level 0-11: edit parts, voices, hidden
                      moves, Musashi's / Hikawa's themes

0x8001a614 ("clear all", run by the game when Fighting Road is finished) clears
the lock set and sets the cleared flag. The setup after loading data
(0x8001a908, called from 0x80018358 on every pass through the title/mode flow)
and after a memory-card load (0x8001a2cc) re-run it only if the flag is set.
This patch runs it unconditionally and makes it also set the ranking level to
11, so new and loaded saves alike have everything. The story edit-point floor
(160/200/240/280) also wants 30% of the story scenes seen for 280; that check
is dropped so the floor is 280.
"""
import struct

from mips_asm import assemble

EXE_BASE = 0x80010000

CLEAR_ALL = 0x8001A614
CLEAR_ALL_SIZE = 18 * 4
CLEAR_ALL_SRC = """
        lui   v0, 0x8005
        lw    v0, 0x41B4(v0)
        lui   v1, 1
        addu  v0, v0, v1                 ; v0 = S + 0x10000
        addiu v1, v0, 0x3CD3             ; locked-wrestler bits
        addiu a0, v0, 0x3CEC
loop:   sb    zero, 0(v1)
        addiu v1, v1, 1
        bne   v1, a0, loop
        nop
        addiu v1, zero, 1
        sb    v1, 0x3CEC(v0)             ; story cleared
        addiu v1, zero, 11
        jr    ra
        sb    v1, 0x3CED(v0)             ; Edit Ranking rewards: all
"""

# (address, original word, replacement)
PATCHES = [
    (0x8001A3B8, 0x10400004, "nop"),     # after memory-card load: always clear all
    (0x8001A934, 0x10400003, "nop"),     # after data setup: always clear all
] + [
    # story edit points: skip "30% of scenes seen" (slti v0, s0, 30 -> v0 = 0)
    (a, 0x2A02001E, "move v0, zero") for a in (0x8001BBFC, 0x8001BCA8, 0x8001BE78, 0x8001C0A8)
]


def patch_exe(exe):
    """exe: bytearray of SLPS_020.65 (with its 0x800 header)."""
    def off(a):
        return a - EXE_BASE + 0x800
    if struct.unpack_from("<I", exe, off(CLEAR_ALL))[0] != 0x00001821:
        raise SystemExit("EXE differs at the unlock routine 0x8001a614")
    code, _ = assemble(CLEAR_ALL_SRC, CLEAR_ALL)
    if len(code) > CLEAR_ALL_SIZE:
        raise SystemExit("unlock routine does not fit")
    code += bytes(CLEAR_ALL_SIZE - len(code))  # nop padding
    exe[off(CLEAR_ALL):off(CLEAR_ALL) + CLEAR_ALL_SIZE] = code
    for addr, old, src in PATCHES:
        if struct.unpack_from("<I", exe, off(addr))[0] != old:
            raise SystemExit(f"EXE differs at {addr:#x} (unlock patch)")
        exe[off(addr):off(addr) + 4] = assemble(src, addr)[0]
