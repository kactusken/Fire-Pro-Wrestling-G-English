#!/usr/bin/env python3
"""Dojo tutorial (FPG 017, shown by overlay 000) and its button icons.

FPG 017 is raw: a table of big-endian u16 offsets (one per message) followed by
the NUL-terminated SJIS messages, lines separated by CR LF. Overlay 000 loads
it (0x8007850c), fetches message n through the table (0x800793ec) and draws it
with the EXE menu text routine 0x80017490, so English goes through the menu
tiling hook like the other menus.

The button icons are sprites, not text: the table at 0x80084290 has 22 entries
of (message, line, icon, x) and the game draws icon u = icon * 16 at
x .. x + 15, y = 0xB2 + 16 * line (0x80078dac). In the Japanese the icon sits on
a full-width space, at x = pen position of that space + 5. text/tutorial.txt
marks icons with {}; build() leaves a gap there and works out each icon's line
and x from the English pen positions.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import menu_vwf_patch  # noqa: E402
import menufont  # noqa: E402
import strtab  # noqa: E402
import uilint  # noqa: E402

ICONS = 0x80084290            # overlay 000: 22 x (message, line, icon, x)
ICON_COUNT = 22
ICON_OFFSET = 5               # icon x - pen x of its gap (fitted to the Japanese)
GAP = 16                      # extra pen advance for an icon, besides the spaces around it
MAX_WIDTH = 210               # widest Japanese line; something slides in at x 204
MAX_LINES = 3                 # line 4 would start at y 225, off the bottom
CELLS = 56                    # the message window's cell budget (0x80016bc8 call at 0x800785ac)


def load(path):
    """[(jp, en)] in message order; \\n separates lines."""
    out, cur = [], {}
    for line in open(path, encoding="utf-8").read().split("\n"):
        if line.startswith("@ "):
            cur = {"n": int(line[2:])}
            out.append(cur)
        elif line[:3] in ("JP ", "EN "):
            cur[line[:2]] = line[3:]
    for k, m in enumerate(out):
        if m["n"] != k or "EN" not in m:
            raise SystemExit(f"tutorial.txt: message {k} missing or out of order")
    return [(m["JP"], m["EN"]) for m in out]


def pen_width(text, font):
    """Pen advance of one line of (already encoded) English, as the menu
    renderer + tiling hook draw it."""
    ascii_w = menu_vwf_patch.ascii_widths(font)
    width_off = struct.unpack_from("<I", font, 8)[0]
    x, i = 0, 0
    while i < len(text):
        c = text[i]
        if c == 0x23:
            m = re.match(rb"#x(-?\d+),", text[i:])
            if m:
                x += int(m.group(1))
                i += m.end()
                continue
        if c == 0x20:
            x += menu_vwf_patch.SPACE
            i += 1
        elif 0x28 <= c < 0x7F:
            x += ascii_w[c - 0x28]
            i += 1
        elif c & 0xE0 in (0x80, 0xE0):
            idx = menufont.sjis_linear(c, text[i + 1])
            x += font[width_off + idx] if idx < 0x2F0 else 12
            i += 2
        else:
            raise SystemExit(f"tutorial: unexpected byte {c:#x}")
    return x


def build(messages, font):
    """-> (FPG 017 bytes, [(message, line, x)] for every icon in reading order)."""
    bodies, icons, problems = [], [], []
    for n, (_jp, en) in enumerate(messages):
        lines = en.split("\\n")
        if len(lines) > MAX_LINES:
            problems.append(f"message {n}: {len(lines)} lines (max {MAX_LINES})")
        enc_lines = []
        for li, line in enumerate(lines):
            parts = line.split("{}")
            enc = b""
            for k, part in enumerate(parts):
                enc += strtab.encode_en(part)
                if k < len(parts) - 1:
                    icons.append((n, li, pen_width(enc, font) + ICON_OFFSET + (GAP - 12) // 2))
                    enc += f"#x{GAP},".encode()
            w = pen_width(enc, font)
            if w > MAX_WIDTH:
                problems.append(f"message {n} line {li + 1}: {w} px (max {MAX_WIDTH}): {line}")
            enc_lines.append(enc)
        body = b"\r\n".join(enc_lines)
        cells = uilint.game_cells(body, font)
        if cells > CELLS:
            problems.append(f"message {n}: needs {cells} cells, the window has {CELLS}")
        bodies.append(body + b"\0")
    if problems:
        raise SystemExit("tutorial:\n  " + "\n  ".join(problems))
    table = 2 * len(bodies)
    out, offs = bytearray(), []
    for b in bodies:
        offs.append(table + len(out))
        out += b
    data = b"".join(struct.pack(">H", o) for o in offs) + bytes(out)
    if len(data) > 0xFFFF:
        raise SystemExit("tutorial: too big for 16-bit offsets")
    return data, icons


def apply_icons(ov, base, icons):
    """Move the icon table entries onto the English gaps (same order: message,
    then reading order within it)."""
    at = ICONS - base
    old = [tuple(ov[at + 4 * k:at + 4 * k + 4]) for k in range(ICON_COUNT)]
    if [m for m, _, _, _ in old] != [m for m, _, _ in icons]:
        raise SystemExit("tutorial: the English has {} icons in different messages than the game's table:\n"
                         f"  game {[m for m, *_ in old]}\n  text {[m for m, *_ in icons]}")
    for k, ((m, _, icon, _), (_, line, x)) in enumerate(zip(old, icons)):
        if not 0 <= x <= 255:
            raise SystemExit(f"tutorial: icon x {x} out of range in message {m}")
        ov[at + 4 * k:at + 4 * k + 4] = bytes((m, line, icon, x))
