#!/usr/bin/env python3
"""Wrestler roster names (text/wrestlers.csv) -> the three copies of the roster.

Records are 426 bytes: +1 name flags, +2 short name (14 B), +16 second name
part (20 B), +36 nickname (26 B), +62 height, +63 weight,
+64 birthplace, +65 birth year - 1900, +66 month, +67 day. The full name is built by
EXE 0x80018430: short name and second part, swapped when flags & 0x80, joined
by flags & 0x0F: 0 = space, 1 = "・", 2 = "＝", 3+ = nothing.

A patch to the name builder (NAME_PATCH) adds flag bit 0x20, "second part
only": the list shows the short name, and the full name is the second part
(max 18 bytes) on its own. The game never sets that bit, so player-made names
are unaffected.

Overlay 001 has its own builder (0x800771bc: the select screen's nickname
bar and the rename preview). It copies each field as count * 2 bytes, with
counts from 0x800823cc, which measures in 2-byte steps, so odd-length
English fields would carry their NUL into the result. Fields are therefore
padded to an even length with 0x01, which the menu renderer skips (no glyph,
no advance). OV001_PATCH makes that builder honour the 0x20 flag; such
records also set the swap bit (0xA3), so the second part comes first there.

Copies: FPG 010 (whole file, 194 records), 011 at +0x1046C (194) and overlay
005 at 0x8006B3B8 (195; the extra record is left alone).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strtab  # noqa: E402
import table  # noqa: E402

RECORD, COUNT = 426, 194
COPIES = {"010": 0, "011": 0x1046C}
OV005_AT = 0x8006B3B8 - 0x8005A718


LIST_PX = 52      # wrestler select list column
FULL_ONLY, NO_SEP, SWAP = 0x20, 0x03, 0x80
PAD = b"\x01"     # invisible to the menu renderer
# Overlay 001 0x80077424 (after "second part + separator" in the swap path):
#   lb v0, 0x3e5(a2) / nop / sll v0, v0, 1 / blez v0, done
# becomes
#   lbu v0, 0(a3) / nop / andi v0, v0, 0x20 / bnez v0, done
# (the copy loop below checks its count itself; an empty short name now
# copies one NUL byte, which is harmless)
OV001_PATCH = [(0x80077424, 0x80C203E5, 0x90E20000),
               (0x8007742C, 0x00021040, 0x30420020),
               (0x80077430, 0x1840FFC7, 0x1440FFC7)]
# EXE 0x80018460: swap step of the name builder.
#   andi v0, a2, 0x80 / beqz v0, +5 / addiu v1, v1, 0x301a /
#   move v0, a0 / move a0, a1 / move a1, v0
# becomes (a0 = short at +2, a1 = second part at +16):
#   andi v0, a2, 0xa0          ; swap or second-only
#   beqz v0, +5
#   addiu v1, v1, 0x301a
#   andi v0, a2, 0x20          ; 0 or 32
#   addu a1, a0, v0            ; second copy: short (+2), or +34 (a NUL)
#   addiu a0, a0, 14           ; first copy: second part (+16)
NAME_PATCH = [(0x80018460, 0x30C20080, 0x30C200A0),
              (0x8001846C, 0x00801021, 0x30C20020),
              (0x80018470, 0x00A02021, 0x00822821),
              (0x80018474, 0x00402821, 0x2484000E)]


def patch_exe(exe):
    """exe: bytearray of SLPS_020.65 (with its 0x800 header)."""
    import struct
    for addr, old, new in NAME_PATCH:
        off = addr - 0x80010000 + 0x800
        if struct.unpack_from("<I", exe, off)[0] != old:
            raise SystemExit(f"EXE differs at the name builder ({addr:#x})")
        struct.pack_into("<I", exe, off, new)


def patch_ov001(ov):
    """ov: bytearray of overlay 001."""
    import struct
    for addr, old, new in OV001_PATCH:
        off = addr - 0x8005A718
        if struct.unpack_from("<I", ov, off)[0] != old:
            raise SystemExit(f"overlay 001 differs at the name builder ({addr:#x})")
        struct.pack_into("<I", ov, off, new)


def load(path):
    rows = {}
    for c in table.read(path):
        if c and c[0].isdigit():
            rows[int(c[0])] = (c[6], c[7], c[8])
    return rows


def fields(short, full):
    """-> (short, second part, flag bits) for the record."""
    if full == short:
        return short, "", NO_SEP
    if full.endswith(" " + short):
        return short, full[:-len(short) - 1], 0x80    # second part first, space
    if full.startswith(short + " "):
        return short, full[len(short) + 1:], 0x00     # short first, space
    if len(full) <= 18:                               # +34 must stay NUL
        return short, full, SWAP | FULL_ONLY | NO_SEP  # list name differs
    raise SystemExit(f"roster: full name {full!r} is longer than 18 bytes and "
                     f"doesn't start or end with {short!r}")


def encode(rows):
    out = {}
    for i, (short, full, nick) in rows.items():
        s, second, flag = fields(short, full)
        data = [strtab.encode_en(t) for t in (s, second, nick)]
        data = [d + PAD * (len(d) % 2) for d in data]   # even lengths, see above
        for d, size, what in zip(data, (14, 20, 26), ("short", "name", "nickname")):
            if len(d) >= size:
                raise SystemExit(f"roster {i}: {what} {d!r} longer than {size - 1} bytes")
        out[i] = (data, flag)
    return out


def apply(buf, at, encoded, original):
    """Patch records at buf[at:]; original: the 010 records, to check the copy."""
    for i, (data, flag) in encoded.items():
        o = at + i * RECORD
        if buf[o + 2:o + 62] != original[i * RECORD + 2:i * RECORD + 62]:
            raise SystemExit(f"roster copy at {at:#x}: record {i} differs from FPG 010")
        buf[o + 1] = (buf[o + 1] & 0x70) | flag
        for d, off, size in zip(data, (2, 16, 36), (14, 20, 26)):
            buf[o + off:o + off + size] = d + bytes(size - len(d))
