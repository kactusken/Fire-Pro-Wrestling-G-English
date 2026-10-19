#!/usr/bin/env python3
"""Extra edit graphics: the unused heads and body parts become regular Wrestler Make choices.

FPG 251 holds heads and body parts that no list, roster wrestler or preset uses
(docs/HIDDEN_CONTENT.md, "Unused wrestler graphics"; docs/PATCHES.md,
"Extra Wrestler Make parts"). Applied by build.py unless --no-extra-parts.

Body parts
  Each body-part list (12-byte entries {name, variant count, 4 part bytes, pad},
  found through the Wrestler Make rows at 0x80076478) is copied to the end of the
  overlay with the extra parts inserted after the items available from the start,
  and every per-level count (row +6..+17) and the total (+18) grow by the same
  number, so the extras are there at every unlock level. The game finds a
  record's list position by value (0x800628ac), so saved wrestlers are unaffected.

Heads
  List positions >= 194 also copy a preset (position - 194) from FPG 015, which
  only has presets for the existing positions. The head list (0x80076220, u16
  head ids) is copied to the end of the overlay with the extra heads appended,
  its three references are repointed, and the row 2 counts for the last unlock
  level and the total grow by 13. A small patch (TRAMPOLINE) skips the preset
  copy for positions past the original list, so an extra head keeps the current
  body and colours. The extra heads therefore come with the last Edit Ranking
  reward (always, in the default unlocked build).
"""
import struct

import codepatch
from mips_asm import assemble

ROWS = 0x80076478           # Wrestler Make rows: 20 bytes, +0 list, +4 slot, +6.. counts by level, +18 total
ENTRY = 12
HEAD_LIST, HEAD_COUNT = 0x80076220, 299
HEAD_REFS = [(0x800617A8, 0x800617AC), (0x80061938, 0x8006193C), (0x800628D0, 0x800628D4)]
HEAD_ROW = 2
EXTRA_HEADS = [305] + list(range(308, 320))
# slot -> [(part number, name)]; copies of other parts are left out
EXTRA_PARTS = {
    0: [(74, "Extra 1"), (75, "Extra 2")],      # chest
    1: [(120, "Extra 1"), (121, "Extra 2")],    # waist (trunks)
    2: [(69, "Extra 1"), (70, "Extra 2")],      # bicep (upper arm)
    3: [(64, "Extra 1"), (65, "Extra 2")],      # arm (forearm)
    4: [(56, "Extra 1"), (57, "Extra 2")],      # shin
    5: [(95, "Extra 1"), (96, "Extra 2")],      # thigh
    7: [(36, "Extra 1")],                       # ankle (feet)
}
# Preset copy for heads with id >= 194 (0x80062704): the branch to it is sent
# through TRAMPOLINE, which returns to the preset code only for positions
# inside the original list.
PRESET_BRANCH = 0x80062738   # beqz v0, 0x80062754 (delay slot: lui v0, 0x8005)
PRESET_CODE, PRESET_SKIP = 0x80062754, 0x80062870
TRAMPOLINE = """
        lw    v0, 0x41C8(v0)
        nop
        lh    v1, 0x1576(v0)             ; head list position
        nop
        slti  v1, v1, COUNT
        bnez  v1, preset
        nop
        j     SKIP                       ; extra head: keep body and colours
        nop
preset: j     PRESET
        lui   v0, 0x8005
"""


def _align(ov):
    ov += bytes((-len(ov)) % 4)


def apply(ov, base, encode):
    """ov: overlay 004 bytearray; the new lists, names and code are appended."""
    def off(a):
        return a - base

    def word(a):
        return struct.unpack_from("<I", ov, off(a))[0]

    notes = []
    rows = {}
    for r in range(3, 11):
        rows[ov[off(ROWS) + 20 * r + 4]] = off(ROWS) + 20 * r
    for slot, parts in EXTRA_PARTS.items():
        row = rows[slot]
        lst, total, first = struct.unpack_from("<I", ov, row)[0], ov[row + 18], ov[row + 6]
        entries = [bytes(ov[off(lst) + ENTRY * k:off(lst) + ENTRY * (k + 1)]) for k in range(total)]
        extra = []
        for part, name in parts:
            _align(ov)
            ptr = base + len(ov)
            ov += encode(name) + b"\0"
            extra.append(struct.pack("<IB4B3x", ptr, 0, *[part] * 4))
        _align(ov)
        new = base + len(ov)
        ov += b"".join(entries[:first] + extra + entries[first:])
        struct.pack_into("<I", ov, row, new)
        for i in range(6, 19):
            ov[row + i] += len(parts)
        notes.append(f"slot {slot}: {len(parts)} extra part(s) after item {first}")

    # heads
    heads = list(struct.unpack_from(f"<{HEAD_COUNT}H", ov, off(HEAD_LIST)))
    row = off(ROWS) + 20 * HEAD_ROW
    if ov[row + 18] + 256 != HEAD_COUNT or ov[row + 17] + 255 != HEAD_COUNT - 1:
        raise SystemExit("extra parts: unexpected head list counts")
    _align(ov)
    new = base + len(ov)
    ov += struct.pack(f"<{HEAD_COUNT + len(EXTRA_HEADS)}H", *heads, *EXTRA_HEADS)
    for lui, lo in HEAD_REFS:
        codepatch.set_pair(ov, base, lui, lo, new, expect=HEAD_LIST)
    ov[row + 17] += len(EXTRA_HEADS)
    ov[row + 18] += len(EXTRA_HEADS)

    if word(PRESET_BRANCH) != 0x10400006:
        raise SystemExit("extra parts: unexpected code at the head preset branch")
    _align(ov)
    tramp = base + len(ov)
    code, _ = assemble(TRAMPOLINE, tramp, {"COUNT": HEAD_COUNT, "SKIP": PRESET_SKIP,
                                           "PRESET": PRESET_CODE})
    ov += code
    disp = (tramp - (PRESET_BRANCH + 4)) // 4
    if not -0x8000 <= disp < 0x8000:
        raise SystemExit("extra parts: trampoline out of branch range")
    struct.pack_into("<I", ov, off(PRESET_BRANCH), 0x10400000 | (disp & 0xFFFF))
    notes.append(f"heads: {len(EXTRA_HEADS)} extra at list positions {HEAD_COUNT + 1}-"
                 f"{HEAD_COUNT + len(EXTRA_HEADS)} (last unlock level)")
    return notes
