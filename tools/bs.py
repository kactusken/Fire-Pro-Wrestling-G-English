#!/usr/bin/env python3
"""Decoder for PS1 BS (MDEC) still images, versions 2 and 3.

Header: u16 mdec_halfwords, u16 0x3800, u16 qscale, u16 version.
Bitstream: 16-bit little-endian units read MSB first. Blocks per
macroblock: Cr, Cb, Y1, Y2, Y3, Y4; macroblocks run top-to-bottom, then
left-to-right. AC coefficients use the MPEG-1 run/level table; escape is
000001 + 6-bit run + 10-bit signed level; end of block is "10".
v2: each block starts with a 10-bit signed DC. v3: DC is coded as an
MPEG-1 style differential (separate predictors for Y, Cb, Cr).
"""
import math
import struct

QUANT = [
    2, 16, 19, 22, 26, 27, 29, 34,
    16, 16, 22, 24, 27, 29, 34, 37,
    19, 22, 26, 27, 29, 34, 34, 38,
    22, 22, 26, 27, 29, 34, 37, 40,
    22, 26, 27, 29, 32, 35, 40, 48,
    26, 27, 29, 32, 35, 40, 48, 58,
    26, 27, 29, 34, 38, 46, 56, 69,
    27, 29, 35, 38, 46, 56, 69, 83]

ZIGZAG = [
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]

# MPEG-1 Table B.14 (dct_coef_next), codes without the sign bit.
AC_TABLE = {
    "11": (0, 1), "011": (1, 1), "0100": (0, 2), "0101": (2, 1),
    "00101": (0, 3), "00111": (3, 1), "00110": (4, 1),
    "000110": (1, 2), "000111": (5, 1), "000101": (6, 1), "000100": (7, 1),
    "0000110": (0, 4), "0000100": (2, 2), "0000111": (8, 1), "0000101": (9, 1),
    "00100110": (0, 5), "00100001": (0, 6), "00100101": (1, 3), "00100100": (3, 2),
    "00100111": (10, 1), "00100011": (11, 1), "00100010": (12, 1), "00100000": (13, 1),
    "0000001010": (0, 7), "0000001100": (1, 4), "0000001011": (2, 3), "0000001111": (4, 2),
    "0000001001": (5, 2), "0000001110": (14, 1), "0000001101": (15, 1), "0000001000": (16, 1),
    "000000011101": (0, 8), "000000011000": (0, 9), "000000010011": (0, 10), "000000010000": (0, 11),
    "000000011011": (1, 5), "000000010100": (2, 4), "000000011100": (3, 3), "000000010010": (4, 3),
    "000000011110": (6, 2), "000000010101": (7, 2), "000000010001": (8, 2), "000000011111": (17, 1),
    "000000011010": (18, 1), "000000011001": (19, 1), "000000010111": (20, 1), "000000010110": (21, 1),
    "0000000011010": (0, 12), "0000000011001": (0, 13), "0000000011000": (0, 14), "0000000010111": (0, 15),
    "0000000010110": (1, 6), "0000000010101": (1, 7), "0000000010100": (2, 5), "0000000010011": (3, 4),
    "0000000010010": (5, 3), "0000000010001": (9, 2), "0000000010000": (10, 2), "0000000011111": (22, 1),
    "0000000011110": (23, 1), "0000000011101": (24, 1), "0000000011100": (25, 1), "0000000011011": (26, 1),
}
for i, lv in enumerate(range(16, 32)):
    AC_TABLE[format(0b00000000011111 - i, "014b")] = (0, lv)
for code, rl in [("000000000011000", (0, 32)), ("000000000010111", (0, 33)), ("000000000010110", (0, 34)),
                 ("000000000010101", (0, 35)), ("000000000010100", (0, 36)), ("000000000010011", (0, 37)),
                 ("000000000010010", (0, 38)), ("000000000010001", (0, 39)), ("000000000010000", (0, 40)),
                 ("000000000011111", (1, 8)), ("000000000011110", (1, 9)), ("000000000011101", (1, 10)),
                 ("000000000011100", (1, 11)), ("000000000011011", (1, 12)), ("000000000011010", (1, 13)),
                 ("000000000011001", (1, 14)),
                 ("0000000000010011", (1, 15)), ("0000000000010010", (1, 16)), ("0000000000010001", (1, 17)),
                 ("0000000000010000", (1, 18)), ("0000000000010100", (6, 3)), ("0000000000011010", (11, 2)),
                 ("0000000000011001", (12, 2)), ("0000000000011000", (13, 2)), ("0000000000010111", (14, 2)),
                 ("0000000000010110", (15, 2)), ("0000000000010101", (16, 2)), ("0000000000011111", (27, 1)),
                 ("0000000000011110", (28, 1)), ("0000000000011101", (29, 1)), ("0000000000011100", (30, 1)),
                 ("0000000000011011", (31, 1))]:
    AC_TABLE[code] = rl

DC_LUMA = {"100": 0, "00": 1, "01": 2, "101": 3, "110": 4, "1110": 5, "11110": 6, "111110": 7, "1111110": 8}
DC_CHROMA = {"00": 0, "01": 1, "10": 2, "110": 3, "1110": 4, "11110": 5, "111110": 6, "1111110": 7, "11111110": 8}


class Bits:
    def __init__(self, data):
        self.bits = "".join(format(struct.unpack_from("<H", data, i)[0], "016b")
                            for i in range(0, len(data) - 1, 2))
        self.pos = 0

    def read(self, n):
        v = int(self.bits[self.pos:self.pos + n], 2)
        self.pos += n
        return v

    def peek_code(self, table, maxlen):
        for ln in range(1, maxlen + 1):
            c = self.bits[self.pos:self.pos + ln]
            if c in table:
                self.pos += ln
                return table[c]
        raise ValueError(f"bad code at bit {self.pos}")

    def left(self):
        return len(self.bits) - self.pos


def signed(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def read_block(bs, version, qscale, dc_pred, kind):
    coef = [0] * 64
    if version == 2:
        dc = signed(bs.read(10), 10)
    else:
        size = bs.peek_code(DC_LUMA if kind == "y" else DC_CHROMA, 8)
        diff = 0
        if size:
            v = bs.read(size)
            diff = v if v >> (size - 1) else v - (1 << size) + 1
        dc_pred[kind] += diff * 4
        dc = dc_pred[kind]
    coef[0] = dc * QUANT[0]
    i = 0
    while True:
        if bs.bits.startswith("10", bs.pos):
            bs.pos += 2
            break
        if bs.bits.startswith("000001", bs.pos):
            bs.pos += 6
            run = bs.read(6)
            level = signed(bs.read(10), 10)
        else:
            run, level = bs.peek_code(AC_TABLE, 16)
            if bs.read(1):
                level = -level
        i += run + 1
        if i > 63:
            raise ValueError("coefficient overflow")
        z = ZIGZAG[i]
        coef[z] = (level * QUANT[z] * qscale + 4) // 8
    return coef


COS = [[math.cos((2 * x + 1) * u * math.pi / 16) * (math.sqrt(0.5) if u == 0 else 1) for u in range(8)]
       for x in range(8)]


def idct(c):
    tmp = [[sum(COS[x][u] * c[v * 8 + u] for u in range(8)) / 2 for x in range(8)] for v in range(8)]
    return [[sum(COS[y][v] * tmp[v][x] for v in range(8)) / 2 for x in range(8)] for y in range(8)]


def decode(data, width=None, height=None):
    mdec, magic, qscale, version = struct.unpack_from("<HHHH", data, 0)
    if magic != 0x3800 or version not in (2, 3):
        raise ValueError("not a BS v2/v3 image")
    bs = Bits(data[8:])
    dc_pred = {"y": 0, "cb": 0, "cr": 0}
    mbs = []
    while bs.left() > 32 and (width is None or len(mbs) < (width // 16) * (height // 16)):
        try:
            blocks = [read_block(bs, version, qscale, dc_pred, k) for k in ("cr", "cb", "y", "y", "y", "y")]
        except (ValueError, IndexError):
            break
        mbs.append(blocks)
    return mbs, qscale, version


def to_rgb(mbs, height):
    rows_mb = height // 16
    cols_mb = len(mbs) // rows_mb
    w, h = cols_mb * 16, rows_mb * 16
    img = [[(0, 0, 0, 255)] * w for _ in range(h)]
    for n, blocks in enumerate(mbs):
        mx, my = (n // rows_mb) * 16, (n % rows_mb) * 16
        cr, cb = idct(blocks[0]), idct(blocks[1])
        ys = [idct(b) for b in blocks[2:]]
        for by in range(16):
            for bx in range(16):
                yb = ys[(by // 8) * 2 + bx // 8]
                Y = yb[by % 8][bx % 8] + 128
                Cr = cr[by // 2][bx // 2]
                Cb = cb[by // 2][bx // 2]
                r = Y + 1.402 * Cr
                g = Y - 0.344 * Cb - 0.714 * Cr
                b = Y + 1.772 * Cb
                img[my + by][mx + bx] = tuple(max(0, min(255, int(v))) for v in (r, g, b)) + (255,)
    return img


if __name__ == "__main__":
    import argparse
    from tim import write_png_rgba
    ap = argparse.ArgumentParser(description="Decode a BS (MDEC) picture to PNG.")
    ap.add_argument("src", help="BS file")
    ap.add_argument("out", help="output PNG")
    ap.add_argument("height", nargs="?", type=int, default=240, help="picture height (default: 240)")
    ap.add_argument("--width", type=int, help="picture width (story backgrounds: 512 x 320)")
    args = ap.parse_args()
    data = open(args.src, "rb").read()
    mbs, q, ver = decode(data, args.width, args.height if args.width else None)
    print(f"v{ver} q{q}: {len(mbs)} macroblocks")
    write_png_rgba(args.out, to_rgb(mbs, args.height))
