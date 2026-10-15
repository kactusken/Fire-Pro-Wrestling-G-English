#!/usr/bin/env python3
"""Move Edit (overlay 004): the button icons beside the move slot labels.

The icons are sprites listed in a table at 0x80079B80: 69 entries of five
signed bytes (texture column, slot row, x, -, palette). The game draws an
entry at x..x+15 on its row (0x80068DF8). The Japanese put each row's icons
right after its label, so their x varied from 92 to 127; here every row's
icons end at RIGHT instead, and the labels end just before them.

Labels are drawn by the game centred between x = 52 and 140 (0x80067CB0),
using the string's full pen advance, "#xN," gaps included. label() picks the
gap that puts the text's end at the given x.
"""
TABLE, COUNT = 0x80079B80, 69
RIGHT = 140                  # icons end here (frame inner edge is ~143)
CENTRE_LEFT, CENTRE_SPAN = 52, 88


def icons_left(n):
    """x of the first icon in a row with n icons."""
    return RIGHT - 16 * n


def apply(ov, base):
    """Move every row's icons to the right edge. ov: overlay 004 bytearray."""
    at = TABLE - base
    rows = {}
    for i in range(COUNT):
        rows.setdefault(ov[at + 5 * i + 1], []).append(i)
    for row, entries in rows.items():
        if len(entries) > 2:
            raise SystemExit(f"Move Edit: row {row} has {len(entries)} icons")
        entries.sort(key=lambda i: ov[at + 5 * i + 2])
        for k, i in enumerate(entries):
            ov[at + 5 * i + 2] = icons_left(len(entries)) + 16 * k


def label(text, width, icons):
    """'text' padded so that its end (width px of pen advance) lands 2 px
    before the row's first icon."""
    end = icons_left(icons) - 2

    def text_end(lead, trail):
        total = lead + width + trail
        return CENTRE_LEFT + (CENTRE_SPAN - total) // 2 + lead + width

    for gap in range(0, 120):
        if text_end(gap, 0) == end:
            return f"#x{gap},{text}" if gap else text
        if text_end(0, gap) == end:
            return f"{text}#x{gap},"
    raise SystemExit(f"Move Edit: no gap puts {text!r} at x={end}")


# Rows whose label string is shared with two-icon rows but which have one
# icon ("Grab" / "Back" + a button): they get their own copy of the label.
LABELS = 0x80079380          # u32 string pointers; row r uses entry r + 1
ONE_ICON_ROWS = {16: 0x8005BD44, 20: 0x8005BD44, 24: 0x8005BD44,     # 組み#x32,
                 29: 0x8005BD38, 30: 0x8005BD38, 31: 0x8005BD38}     # バｯｸ#x32,


def add_labels(ov, base, texts, encode):
    """Append a one-icon label per string and point ONE_ICON_ROWS at them.
    texts: {original string address: label text}."""
    import struct
    placed = {}
    ov += bytes((-len(ov)) % 4)
    for row, orig in ONE_ICON_ROWS.items():
        at = LABELS - base + 4 * (row + 1)
        if struct.unpack_from("<I", ov, at)[0] != orig:
            raise SystemExit(f"Move Edit: label pointer for row {row} differs")
        if orig not in placed:
            placed[orig] = base + len(ov)
            ov += encode(texts[orig]) + b"\0"
            ov += bytes((-len(ov)) % 4)
        struct.pack_into("<I", ov, at, placed[orig])
