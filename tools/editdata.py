#!/usr/bin/env python3
"""Edit-format wrestler records outside the roster (text/edit_wrestlers.tsv) and
the bonus edit wrestlers' profiles (text/edit_profiles.txt).

Edit records are 512 bytes. The names sit where the roster has them (+1 flags,
+2 short 14 B, +16 second part 20 B, +36 nickname 26 B; tools/roster.py) and
+0x1C8 holds the custom finisher name, which EXE 0x800186f4 returns in place
of a move-table name, so it is drawn like the move names. The field runs to
+0x1F2, but overlay 001 copies only 28 bytes, so names stay under that.

  FPG 013 (raw, loaded into the save block by EXE 0x8001b5cc): 30 bonus edit
          wrestlers at 0x4E28, then their profiles at 0x8A28 (29 big-endian u16
          offsets from 0x8A28, NUL-terminated text, CR LF lines) up to the end.
  FPG 016 (raw): a sample wrestler and Coach Yamamoto.
  FPG 127 (compressed, loaded by overlay 002): story starting templates, Sakagami.
  Overlay 004 0x800755E8: the record a new edit wrestler starts from.
  EXE 0x8004980C (read at 0x8001aefc): the story hero's default record.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roster  # noqa: E402
import strtab  # noqa: E402

RECORD = 0x200
FINISHER, FINISHER_SIZE = 0x1C8, 28
FINISHER_FIELD = 42           # zero up to +0x1F2 (the Japanese could run past 28 bytes)
BASES = {"013": 0x4E28, "016": 0, "127": 0}
OV004_AT = 0x800755E8 - 0x8005A718
EXE_AT = 0x8004980C - 0x80010000 + 0x800   # in SLPS_020.65 (with its header)
PROFILES, PROFILE_COUNT, PROFILE_END = 0x8A28, 29, 0x9220
PROFILE_CELLS = 54            # Edit Ranking profile window (overlay 004 0x8006c080); no bounds check
# The window starts at x 108 and auto-wraps when the pen passes x 308 (EXE 0x80017928, ctx+0x26 = 320);
# the box's inner edge is at about x 303, and it shows 3 lines.
PROFILE_PX, PROFILE_LINES = 195, 3


def load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or line.startswith("id\t") or not line.strip():
            continue
        rid, jp, short, full, nick, fin = line.rstrip("\n").split("\t")
        rows.append((rid, jp, short, full, nick, fin))
    return rows


def patch_record(buf, o, row):
    rid, jp, short, full, nick, fin = row
    s, second, flag = roster.fields(short, full)
    data = [strtab.encode_en(t) for t in (s, second, nick)]
    data = [d + roster.PAD * (len(d) % 2) for d in data]
    for d, off, size, what in zip(data, (2, 16, 36), (14, 20, 26), ("short", "name", "nickname")):
        if len(d) >= size:
            raise SystemExit(f"edit record {rid}: {what} {d!r} longer than {size - 1} bytes")
        buf[o + off:o + off + size] = d + bytes(size - len(d))
    buf[o + 1] = (buf[o + 1] & 0x70) | flag
    f = strtab.encode_en(fin)
    if len(f) >= FINISHER_SIZE:
        raise SystemExit(f"edit record {rid}: finisher {fin!r} longer than {FINISHER_SIZE - 1} bytes")
    buf[o + FINISHER:o + FINISHER + FINISHER_FIELD] = f + bytes(FINISHER_FIELD - len(f))


def check_jp(buf, o, row):
    """The record must still hold the Japanese the row was written for."""
    def field(a, n):
        return bytes(buf[a:a + n]).split(b"\0")[0].decode("cp932")
    names = [n for n in (field(o + 2, 14), field(o + 16, 20)) if n.strip("　")]
    if not names or not all(n.strip("　") in row[1] for n in names):
        raise SystemExit(f"edit record {row[0]}: expected {row[1]}, found {names}")


def apply(files, rows):
    """files: {entry: bytearray} for any of '013', '016', '127' (decompressed)
    and '004'; rows for other entries are skipped. Returns the count patched."""
    done = 0
    for row in rows:
        rid = row[0]
        entry, _, n = rid.partition(":")
        if entry not in files:
            continue
        buf = files[entry]
        o = {"004": OV004_AT, "exe": EXE_AT}.get(entry)
        if o is None:
            o = BASES[entry] + int(n) * RECORD
        check_jp(buf, o, row)
        patch_record(buf, o, row)
        done += 1
    return done


def load_profiles(path):
    out = {}
    cur = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("@ "):
            cur = int(line[2:])
        elif line.startswith("EN "):
            out[cur] = line[3:]
    if sorted(out) != list(range(PROFILE_COUNT)):
        raise SystemExit("edit_profiles.txt: needs EN for profiles 0-28")
    return [out[i] for i in range(PROFILE_COUNT)]


def menu_px(data, font):
    """Pen advance of one encoded line in the menu renderer (with the tiling hook)."""
    import menu_vwf_patch
    from font import sjis_linear
    widths = struct.unpack_from("<I", font, 8)[0]
    ascii = menu_vwf_patch.ascii_widths(font)
    px = i = 0
    while i < len(data):
        c = data[i]
        if c & 0xE0 in (0x80, 0xE0):
            idx = sjis_linear(c, data[i + 1])
            px += font[widths + idx] if idx < 0x2F0 else 12
            i += 2
            continue
        px += 4 if c == 0x20 else ascii[c - 0x28] if 0x28 <= c < 0x7F else 0
        i += 1
    return px


def apply_profiles(buf, texts, font):
    """font: the patched menu font (FPG 009), to count the window cells and widths."""
    import uilint
    over = [f"profile {i}: {c} cells" for i, t in enumerate(texts)
            if (c := uilint.game_cells(strtab.encode_en(t), font)) > PROFILE_CELLS]
    for i, t in enumerate(texts):
        lines = t.split("\\n")
        if len(lines) > PROFILE_LINES:
            over.append(f"profile {i}: {len(lines)} lines (box shows {PROFILE_LINES})")
        over += [f"profile {i}: line {n + 1} is {w} px (max {PROFILE_PX}): {ln}"
                 for n, ln in enumerate(lines)
                 if (w := menu_px(strtab.encode_en(ln), font)) > PROFILE_PX]
    if over:
        raise SystemExit("edit profiles do not fit their window:\n  " + "\n  ".join(over))
    table = 2 * PROFILE_COUNT
    blob, offs = bytearray(), []
    for t in texts:
        offs.append(table + len(blob))
        blob += strtab.encode_en(t).replace(b"\n", b"\r\n") + b"\0"
    data = struct.pack(f">{PROFILE_COUNT}H", *offs) + bytes(blob)
    room = PROFILE_END - PROFILES
    if len(data) > room:
        raise SystemExit(f"edit profiles: {len(data)} bytes, room for {room}")
    buf[PROFILES:PROFILE_END] = data + bytes(room - len(data))
    return len(data)
