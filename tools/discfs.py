#!/usr/bin/env python3
"""Minimal ISO9660 reader for raw MODE2/2352 PS1 disc images.

Usage:
  discfs.py list    <image.bin>
  discfs.py extract <image.bin> <outdir>
"""
import os
import struct

SECTOR = 2352
DATA_OFF = 24  # Mode 2 Form 1: 12 sync + 4 header + 8 subheader
DATA_LEN = 2048


def read_sector(f, lba):
    f.seek(lba * SECTOR)
    raw = f.read(SECTOR)
    return raw[DATA_OFF:DATA_OFF + DATA_LEN]


def read_extent(f, lba, size):
    out = bytearray()
    n = (size + DATA_LEN - 1) // DATA_LEN
    for i in range(n):
        out += read_sector(f, lba + i)
    return bytes(out[:size])


def parse_dir(f, lba, size, path=""):
    data = read_extent(f, lba, size)
    pos = 0
    while pos < len(data):
        rlen = data[pos]
        if rlen == 0:
            pos = (pos // DATA_LEN + 1) * DATA_LEN
            continue
        rec = data[pos:pos + rlen]
        ext_lba = struct.unpack_from("<I", rec, 2)[0]
        ext_size = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        nlen = rec[32]
        name = rec[33:33 + nlen]
        pos += rlen
        if name in (b"\x00", b"\x01"):
            continue
        name = name.decode("ascii", "replace").split(";")[0]
        full = f"{path}/{name}"
        if flags & 2:
            yield (full + "/", ext_lba, ext_size, True)
            yield from parse_dir(f, ext_lba, ext_size, full)
        else:
            yield (full, ext_lba, ext_size, False)


def walk(f):
    pvd = read_sector(f, 16)
    assert pvd[1:6] == b"CD001", "not an ISO9660 image"
    root = pvd[156:156 + 34]
    lba = struct.unpack_from("<I", root, 2)[0]
    size = struct.unpack_from("<I", root, 10)[0]
    yield from parse_dir(f, lba, size)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="List or extract the files of a MODE2/2352 PS1 disc image.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="print LBA, size and path of every file").add_argument("image")
    p = sub.add_parser("extract", help="copy every file into a folder")
    p.add_argument("image")
    p.add_argument("outdir")
    args = ap.parse_args(argv)
    cmd, img = args.cmd, args.image
    with open(img, "rb") as f:
        if cmd == "list":
            for name, lba, size, _is_dir in walk(f):
                print(f"{lba:8d} {size:10d}  {name}")
        elif cmd == "extract":
            out = args.outdir
            for name, lba, size, is_dir in walk(f):
                dst = os.path.join(out, name.lstrip("/"))
                if is_dir:
                    os.makedirs(dst, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, "wb") as o:
                        o.write(read_extent(f, lba, size))


if __name__ == "__main__":
    main()
