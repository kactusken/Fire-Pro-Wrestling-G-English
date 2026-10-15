#!/usr/bin/env python3
"""Story-mode font (FPG.BIN entry 128).

Header: u32 map_off, u32 data_off, u32 end (x4).
map:  u16 per linear SJIS index -> glyph number
      linear = (hi - 0x81) * 188 + (lo - 0x40 - (lo >= 0x80)); hi >= 0xE0 maps as hi - 0x40
data: u32 offsets (relative to data) per glyph, then per-glyph streams
      compressed with the 32-byte-ring LZ (decoder at 0x80012e0c), unpacking
      to 0x140 bytes.
"""
import struct

GLYPH_BYTES = 0x140


def sjis_linear(hi, lo):
    if hi >= 0x88 and hi >= 0xE0:
        hi -= 0x40
    return (hi - 0x81) * 188 + (lo - 0x40 - (1 if lo >= 0x80 else 0))


def unpack_glyph(src):
    """Decoder at 0x80012e0c: 32-byte ring, start 0x17.
    Flag bit 1 -> ref byte: pos = (b >> 3) & 0x1F, len = (b & 7) + 2."""
    ring = bytearray(32)
    r = 0x17
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        flags = src[i]
        i += 1
        for bit in range(8):
            if i >= n:
                break
            b = src[i]
            i += 1
            if flags >> bit & 1:
                pos = (b >> 3) & 0x1F
                for _ in range((b & 7) + 2):
                    c = ring[pos]
                    pos = (pos + 1) & 0x1F
                    out.append(c)
                    ring[r] = c
                    r = (r + 1) & 0x1F
            else:
                out.append(b)
                ring[r] = b
                r = (r + 1) & 0x1F
    return bytes(out)


class Font:
    def __init__(self, data):
        self.data = data
        self.map_off, self.data_off = struct.unpack_from("<II", data, 0)
        first = struct.unpack_from("<I", data, self.data_off)[0]
        self.count = first // 4 - 1

    def glyph_number(self, hi, lo):
        return struct.unpack_from("<H", self.data, self.map_off + 2 * sjis_linear(hi, lo))[0]

    def raw_glyph(self, g):
        a, b = struct.unpack_from("<II", self.data, self.data_off + 4 * g)
        return self.data[self.data_off + a:self.data_off + b]

    def glyph(self, g):
        return unpack_glyph(self.raw_glyph(g))


GLYPH_W, GLYPH_H = 20, 32

# Full-width SJIS stand-ins for printable ASCII.
ASCII_FULLWIDTH = {" ": "　", "!": "！", '"': "”", "#": "＃", "$": "＄", "%": "％",
                   "&": "＆", "'": "’", "\\": "￥", "`": "‘", "~": "￣"}


def ascii_sjis(c):
    ch = chr(c)
    fw = ASCII_FULLWIDTH.get(ch) or chr(c - 0x21 + 0xFF01)
    return fw.encode("cp932")


def pixels(glyph):
    """4bpp, low nibble first, 20 px per row."""
    return [[(glyph[(y * GLYPH_W + x) // 2] >> ((x & 1) * 4)) & 0xF for x in range(GLYPH_W)]
            for y in range(GLYPH_H)]


def ink_bounds(px, threshold=3):
    cols = [x for x in range(GLYPH_W) if any(px[y][x] >= threshold for y in range(GLYPH_H))]
    return (cols[0], cols[-1]) if cols else None


def write_png(path, rows, scale=1):
    """rows: list of lists of 0..255 grey values."""
    import struct as st
    import zlib
    h, w = len(rows) * scale, len(rows[0]) * scale
    raw = bytearray()
    for r in rows:
        line = bytearray()
        for v in r:
            line += bytes([v]) * scale
        for _ in range(scale):
            raw += b"\0" + line

    def chunk(t, d):
        c = st.pack(">I", len(d)) + t + d
        return c + st.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", st.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)
