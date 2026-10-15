#!/usr/bin/env python3
"""LZSS codec used by Fire Pro Wrestling G (decoder at 0x80012cdc in SLPS_020.65).

Ring buffer: 0x400 bytes (kept in the scratchpad), zero-filled, write position
starts at 0x3BE.
Stream: flag byte, read LSB first; bit 1 = reference, 0 = literal byte.
Reference: two bytes b0 b1
    pos    = (b0 | (b1 & 0xC0) << 2)     absolute ring position (10 bits)
    length = (b1 & 0x3F) + 3             (3..66)
There is no header; the game passes the compressed size.

Usage:
  lzss.py d <in> <out>
  lzss.py c <in> <out>
"""

RING = 0x400
RING_START = 0x3BE
MIN_LEN = 3
MAX_LEN = 0x3F + MIN_LEN


def decompress(src):
    ring = bytearray(RING)
    r = RING_START
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        flags = src[i]
        i += 1
        for bit in range(8):
            if i >= n:
                break
            if flags >> bit & 1:
                if i + 1 >= n:
                    i = n
                    break
                b0, b1 = src[i], src[i + 1]
                i += 2
                pos = b0 | (b1 & 0xC0) << 2
                for _ in range(MIN_LEN + (b1 & 0x3F)):
                    c = ring[pos]
                    pos = (pos + 1) & (RING - 1)
                    out.append(c)
                    ring[r] = c
                    r = (r + 1) & (RING - 1)
            else:
                c = src[i]
                i += 1
                out.append(c)
                ring[r] = c
                r = (r + 1) & (RING - 1)
    return bytes(out)


def compress(data):
    """LZSS with lazy matching. The 0x3BE zero bytes before the stream start
    are matchable (the ring starts zero-filled)."""
    pad = RING_START
    buf = bytes(pad) + data
    n = len(buf)
    heads = {}
    prev = [-1] * n
    inserted = [pad]  # next position to insert into the hash chains

    def insert_upto(pos):
        p = inserted[0]
        while p < pos and p + MIN_LEN <= n:
            key = buf[p:p + MIN_LEN]
            prev[p] = heads.get(key, -1)
            heads[key] = p
            p += 1
        inserted[0] = max(p, pos)

    def longest(i):
        insert_upto(i)
        limit = min(MAX_LEN, n - i)
        if limit < MIN_LEN:
            return 0, 0
        best_len, best_src = 0, 0
        cand = heads.get(buf[i:i + MIN_LEN], -1)
        tries = 512
        while cand >= 0 and i - cand < RING and tries:
            tries -= 1
            if buf[cand + best_len] == buf[i + best_len] if best_len < limit else False:
                ln = 0
                while ln < limit and buf[cand + ln] == buf[i + ln]:
                    ln += 1
                if ln > best_len:
                    best_len, best_src = ln, cand
                    if ln == limit:
                        break
            cand = prev[cand]
        return best_len, best_src

    # seed the chains with the zero prefix
    p = 0
    while p < pad:
        if p + MIN_LEN <= n:
            key = buf[p:p + MIN_LEN]
            prev[p] = heads.get(key, -1)
            heads[key] = p
        p += 1

    tokens = []
    i = pad
    while i < n:
        ln, src = longest(i)
        if ln >= MIN_LEN and i + 1 < n:
            ln2, _ = longest(i + 1)
            if ln2 > ln + 1:
                tokens.append(buf[i])
                i += 1
                continue
        if ln >= MIN_LEN:
            tokens.append((ln, src))
            i += ln
        else:
            tokens.append(buf[i])
            i += 1

    out = bytearray()
    for k in range(0, len(tokens), 8):
        group = tokens[k:k + 8]
        flags = 0
        body = bytearray()
        for bit, t in enumerate(group):
            if isinstance(t, tuple):
                ln, src = t
                pos = (src - pad + RING_START) & (RING - 1)
                body.append(pos & 0xFF)
                body.append((pos >> 2 & 0xC0) | (ln - MIN_LEN))
                flags |= 1 << bit
            else:
                body.append(t)
        out.append(flags)
        out += body
    return bytes(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Decompress (d) or compress (c) one file.")
    ap.add_argument("mode", choices=["d", "c"])
    ap.add_argument("src")
    ap.add_argument("dst")
    args = ap.parse_args()
    mode, src, dst = args.mode, args.src, args.dst
    data = open(src, "rb").read()
    result = decompress(data) if mode == "d" else compress(data)
    open(dst, "wb").write(result)
