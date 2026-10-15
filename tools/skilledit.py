#!/usr/bin/env python3
"""Skill Edit screen (overlay 004): row table, value box sizes and slot checks.

Each row is a 20-byte record in overlay 004 at 0x80076954..0x80076be8:
    +0  flags   byte 0 = value box size in cells, byte 3 = last option index
    +4  option list (pointers to strings), or 0 for numbers
    +8  suffix appended to numbers (cm, kg, ...)
    +12 label
    +16 offset of the value in the wrestler record
The screen shows 6 rows at a time; each visible row has an auto-sized label
window and a value window of the box size. The menu cell pool has 378 slots
with no bounds check, and this screen opens on top of the Edit menu, so
there is almost no headroom: the English labels crashed it when they needed
more cells than the Japanese.

We shrink value boxes whose English options are shorter (letter grades need
one cell) and spend those cells on clearer labels. The build checks that every
option fits its box and that any 7 consecutive rows (6 visible plus one being
scrolled in) need no more cells than in Japanese.
"""
import struct

import strtab
import uilint

OVERLAY_BASE = 0x8005A718
FIRST_ROW, LAST_ROW = 0x80076954, 0x80076BD4
WINDOW_ROWS = 7

# record address -> (original box, new box)
BOXES = {
    0x800769F4: (8, 7),   # Fight Style
    0x80076A08: (8, 7),   # Reversal
    0x80076A30: (8, 7),   # Special
    0x80076A44: (2, 1),   # Recovery          (grades A/B/C)
    0x80076A58: (2, 1),   # Recovery, bleeding
    0x80076A6C: (3, 1),   # Breathing
    0x80076A80: (3, 1),   # Breathing, bleeding
    0x80076A94: (2, 1),   # Spirit
    0x80076AA8: (2, 1),   # Spirit, bleeding
    0x80076ABC: (2, 1),   # Neck
    0x80076AD0: (2, 1),   # Arms
    0x80076AE4: (2, 1),   # Back
    0x80076AF8: (2, 1),   # Legs
    0x80076B0C: (4, 2),   # Speed            (grades up to C+/B+)
    0x80076B20: (4, 2),   # Climb
    0x80076B5C: (2, 1),   # Tagging
}


def _rows(ov):
    a = FIRST_ROW
    while a <= LAST_ROW:
        yield a, struct.unpack_from("<5I", ov, a - OVERLAY_BASE)
        a += 0x14


def _string(ov, addr):
    off = addr - OVERLAY_BASE
    return bytes(ov[off:ov.index(b"\0", off)])


def apply_boxes(ov):
    """Patch the box sizes in place (ov: bytearray of the original overlay)."""
    for addr, (old, new) in BOXES.items():
        off = addr - OVERLAY_BASE
        if ov[off] != old:
            raise SystemExit(f"Skill Edit row {addr:#x}: box is {ov[off]}, expected {old}")
        ov[off] = new


def check(ov, entries, font):
    """ov: the overlay with its original (Japanese) strings; entries: {addr: EN}.
    Returns a list of problems."""
    def en(addr):
        return strtab.encode_en(entries[addr]) if addr in entries else _string(ov, addr)

    problems, jp_cost, en_cost = [], [], []
    for addr, (flags, options, _suffix, label, _off) in _rows(ov):
        box = BOXES.get(addr, (flags & 0xFF, flags & 0xFF))[1]
        if options and OVERLAY_BASE <= options < OVERLAY_BASE + len(ov):
            for k in range((flags >> 24) + 1):
                p = struct.unpack_from("<I", ov, options + 4 * k - OVERLAY_BASE)[0]
                if p and uilint.game_cells(en(p), font) > box:
                    problems.append(f"option {entries.get(p, p)!r} needs "
                                    f"{uilint.game_cells(en(p), font)} cells, box {box} (row {addr:#x})")
        jp_cost.append(uilint.game_cells(_string(ov, label), font) + (flags & 0xFF))
        en_cost.append(uilint.game_cells(en(label), font) + box)
    for i in range(len(jp_cost) - WINDOW_ROWS + 1):
        j, e = sum(jp_cost[i:i + WINDOW_ROWS]), sum(en_cost[i:i + WINDOW_ROWS])
        if e > j:
            problems.append(f"rows {i}..{i + WINDOW_ROWS - 1} need {e} cells, Japanese {j}")
    return problems
