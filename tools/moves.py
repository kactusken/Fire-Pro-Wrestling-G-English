#!/usr/bin/env python3
"""Move names (text/moves.tsv) -> FPG 011.

011 (decompressed) has a table at 0x30A38 of 1,592 u16 offsets, relative to
the table, into NUL-terminated strings at 0x316A8..0x34694 (840 distinct
names). The EXE looks names up through this table (e.g. 0x80018670), so the
strings can be laid out freely: identical names share one copy and a name
that is the end of a longer one points into it.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strtab  # noqa: E402

TABLE, COUNT = 0x30A38, 1592
AREA = (0x316A8, 0x34694)


def load(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        _, jp, en = line.rstrip("\n").split("\t")
        out[jp.encode("cp932")] = en
    return out


def apply(buf, names):
    """buf: bytearray of 011 decompressed (original strings)."""
    offs = struct.unpack_from(f"<{COUNT}H", buf, TABLE)
    jp = [bytes(buf[TABLE + o:buf.index(b"\0", TABLE + o)]) for o in offs]
    missing = sorted({j.decode("cp932") for j in jp if j not in names})
    if missing:
        raise SystemExit(f"moves: no translation for {missing[:5]}...")
    en = [strtab.encode_en(names[j]) for j in jp]
    # lay out longest first (ties in byte order, so builds are reproducible);
    # a string that ends another shares its tail
    blob, where = bytearray(), {}
    for s in sorted(set(en), key=lambda s: (-len(s), s)):
        hit = next((a + len(t) - len(s) for t, a in where.items() if t.endswith(s)), None)
        if hit is None:
            hit = AREA[0] + len(blob)
            blob += s + b"\0"
        where[s] = hit
    if AREA[0] + len(blob) > AREA[1]:
        raise SystemExit(f"moves: {len(blob)} bytes, area holds {AREA[1] - AREA[0]}")
    buf[AREA[0]:AREA[1]] = blob + bytes(AREA[1] - AREA[0] - len(blob))
    struct.pack_into(f"<{COUNT}H", buf, TABLE, *[where[s] - TABLE for s in en])
    return len(blob)
