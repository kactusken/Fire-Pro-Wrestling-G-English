#!/usr/bin/env python3
"""PS1 TIM image reading and PNG export.

TIM: u32 0x10, u32 flags (bits 0-1: 0=4bpp 1=8bpp 2=16bpp 3=24bpp; bit 3: CLUT)
     [CLUT block: u32 len, u16 x, y, w, h, colours...]
     image block: u32 len, u16 x, y, w (in 16-bit units), h, pixels...
"""
import struct
import zlib


class Tim:
    def __init__(self, data, off=0):
        magic, flags = struct.unpack_from("<II", data, off)
        if magic != 0x10 or flags & ~0xB or (flags & 3) == 3:
            raise ValueError("not a TIM")
        self.bpp = (4, 8, 16, 24)[flags & 3]
        p = off + 8
        self.cluts = []
        self.clut_pos = None
        if flags & 8:
            ln, cx, cy, cw, ch = struct.unpack_from("<IHHHH", data, p)
            if ln != 12 + cw * ch * 2 or cw == 0 or ch == 0:
                raise ValueError("bad CLUT")
            self.clut_pos = (cx, cy, cw, ch)
            cols = struct.unpack_from(f"<{cw * ch}H", data, p + 12)
            per = 16 if self.bpp == 4 else 256
            self.cluts = [cols[i:i + per] for i in range(0, len(cols), per)]
            p += ln
        ln, x, y, w, h = struct.unpack_from("<IHHHH", data, p)
        if ln != 12 + w * h * 2 or w == 0 or h == 0 or w > 1024 or h > 512:
            raise ValueError("bad image block")
        self.vram = (x, y, w, h)
        self.pixels_raw = data[p + 12:p + ln]
        self.width = w * 16 // self.bpp
        self.height = h
        self.size = p + ln - off

    def rgba(self, clut_index=0):
        """Return rows of (r, g, b, a) tuples."""
        def c15(v):
            r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
            a = 0 if v == 0 else 255  # colour 0x0000 is transparent on PS1
            return (r * 255 // 31, g * 255 // 31, b * 255 // 31, a)
        raw = self.pixels_raw
        rows = []
        if self.bpp == 16:
            vals = struct.unpack_from(f"<{len(raw) // 2}H", raw)
            for y in range(self.height):
                rows.append([c15(v) for v in vals[y * self.width:(y + 1) * self.width]])
            return rows
        clut = self.cluts[clut_index] if self.cluts else None
        pal = [c15(v) for v in clut] if clut else [(i * 17, i * 17, i * 17, 255) for i in range(16)]
        stride = self.vram[2] * 2
        for y in range(self.height):
            line = raw[y * stride:(y + 1) * stride]
            if self.bpp == 4:
                idx = [n for b in line for n in (b & 15, b >> 4)]
            else:
                idx = list(line)
            rows.append([pal[i] if i < len(pal) else (255, 0, 255, 255) for i in idx[:self.width]])
        return rows


def write_png_rgba(path, rows):
    h, w = len(rows), len(rows[0])
    raw = bytearray()
    for r in rows:
        raw.append(0)
        for px in r:
            raw += bytes(px)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


def find_tims(data, step=4):
    """Yield (offset, Tim) for every TIM found at step-aligned offsets."""
    i = 0
    n = len(data) - 20
    while i < n:
        if data[i] == 0x10 and data[i + 1:i + 4] == b"\0\0\0" and data[i + 5:i + 8] == b"\0\0\0":
            try:
                t = Tim(data, i)
                yield i, t
                i += (t.size + step - 1) // step * step
                continue
            except (ValueError, struct.error):
                pass
        i += step
