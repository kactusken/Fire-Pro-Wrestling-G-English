#!/usr/bin/env python3
"""FPG.BIN archive tool.

Format: table of (offset u32, size u32) little-endian pairs at file start,
terminated by a zero-size entry whose offset equals the archive end.
Offsets are 2048-byte aligned.

Usage:
  fpgbin.py unpack <FPG.BIN> <outdir>
  fpgbin.py pack   <indir> <FPG.BIN>
"""
import os
import struct

ALIGN = 0x800
TOC_SIZE = 0x1000


def read_toc(data):
    ents = []
    for i in range(TOC_SIZE // 8):
        o, s = struct.unpack_from("<II", data, i * 8)
        ents.append((o, s))
        if s == 0:
            break
    return ents


def unpack(src, outdir):
    data = open(src, "rb").read()
    ents = read_toc(data)
    os.makedirs(outdir, exist_ok=True)
    for i, (o, s) in enumerate(ents[:-1]):
        with open(os.path.join(outdir, f"{i:03d}.bin"), "wb") as f:
            f.write(data[o:o + s])
    print(f"unpacked {len(ents) - 1} files")


def replace(data, index, blob):
    """Put a new entry into the archive bytearray `data` in its own space, without
    moving the others (it must fit up to the next entry's offset)."""
    ents = read_toc(data)
    o = ents[index][0]
    room = ents[index + 1][0] - o
    if len(blob) > room:
        raise SystemExit(f"FPG entry {index}: {len(blob)} bytes, its space holds {room}")
    data[o:o + room] = blob + bytes(room - len(blob))
    struct.pack_into("<I", data, index * 8 + 4, len(blob))


def pack(indir, dst):
    names = sorted(n for n in os.listdir(indir) if n.endswith(".bin"))
    toc = bytearray(TOC_SIZE)
    body = bytearray()
    pos = TOC_SIZE
    for i, n in enumerate(names):
        blob = open(os.path.join(indir, n), "rb").read()
        if not blob:   # a size of 0 marks the end of the table
            raise SystemExit(f"{n}: FPG.BIN entries can't be empty")
        struct.pack_into("<II", toc, i * 8, pos, len(blob))
        pad = (-len(blob)) % ALIGN
        body += blob + b"\0" * pad
        pos += len(blob) + pad
    struct.pack_into("<II", toc, len(names) * 8, pos, 0)
    with open(dst, "wb") as f:
        f.write(toc + body)
    print(f"packed {len(names)} files, {pos} bytes")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Unpack or pack the FPG.BIN archive.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("unpack", help="FPG.BIN -> one NNN.bin per entry")
    p.add_argument("src", metavar="FPG.BIN")
    p.add_argument("outdir")
    p = sub.add_parser("pack", help="a folder of NNN.bin -> FPG.BIN")
    p.add_argument("indir")
    p.add_argument("dst", metavar="FPG.BIN")
    args = ap.parse_args()
    if args.cmd == "unpack":
        unpack(args.src, args.outdir)
    else:
        pack(args.indir, args.dst)
