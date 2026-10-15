#!/usr/bin/env python3
"""Write files back into a raw MODE2/2352 PS1 image in place.

Each replacement must fit in the sectors the original file occupies.
EDC/ECC are regenerated for every rewritten Mode 2 Form 1 sector, and
the directory record's size field is updated.

Usage:
  discpatch.py <image.bin> /PATH/ON/DISC=<local file> [...]
  discpatch.py <image.bin> --verify [count]   (self-test EDC/ECC on existing sectors)
"""
import struct
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
import discfs  # noqa: E402

SECTOR = discfs.SECTOR
DATA = discfs.DATA_LEN

# --- EDC / ECC (ECMA-130) -------------------------------------------------

EDC_TABLE = []
for i in range(256):
    e = i
    for _ in range(8):
        e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
    EDC_TABLE.append(e)

ECC_F = [0] * 256
ECC_B = [0] * 256
for i in range(256):
    j = (i << 1) ^ (0x11D if i & 0x80 else 0)
    ECC_F[i] = j
    ECC_B[i ^ j] = i


def edc(data):
    e = 0
    for b in data:
        e = (e >> 8) ^ EDC_TABLE[(e ^ b) & 0xFF]
    return e


def ecc_compute(sector, major_count, minor_count, major_mult, minor_inc, dest):
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = sector[0xC + index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = ECC_F[a]
        a = ECC_B[ECC_F[a] ^ b]
        sector[dest + major] = a
        sector[dest + major + major_count] = a ^ b


def fix_sector(sector):
    """Recompute EDC and ECC of a Mode 2 Form 1 sector (bytearray, 2352)."""
    struct.pack_into("<I", sector, 0x818, edc(sector[0x10:0x818]))
    saved = bytes(sector[0xC:0x10])
    sector[0xC:0x10] = b"\0\0\0\0"  # header is zeroed for Mode 2 ECC
    ecc_compute(sector, 86, 24, 2, 86, 0x81C)
    ecc_compute(sector, 52, 43, 86, 88, 0x8C8)
    sector[0xC:0x10] = saved


# --- patching -------------------------------------------------------------

def find_record(f, path):
    """Locate the directory record for path; return (record file offset, lba, size)."""
    pvd = discfs.read_sector(f, 16)
    root = pvd[156:156 + 34]
    lba = struct.unpack_from("<I", root, 2)[0]
    size = struct.unpack_from("<I", root, 10)[0]
    parts = [p for p in path.strip("/").upper().split("/") if p]
    for depth, part in enumerate(parts):
        data = discfs.read_extent(f, lba, size)
        pos = 0
        found = None
        while pos < len(data):
            rlen = data[pos]
            if rlen == 0:
                pos = (pos // DATA + 1) * DATA
                continue
            nlen = data[pos + 32]
            name = data[pos + 33:pos + 33 + nlen].decode("ascii", "replace").split(";")[0]
            if name.upper() == part:
                found = pos
                break
            pos += rlen
        if found is None:
            raise SystemExit(f"{path}: not found on disc")
        rec_lba = lba + found // DATA
        rec_off = rec_lba * SECTOR + discfs.DATA_OFF + found % DATA
        lba = struct.unpack_from("<I", data, found + 2)[0]
        size = struct.unpack_from("<I", data, found + 10)[0]
        if depth == len(parts) - 1:
            return rec_off, rec_lba, lba, size


def rewrite_sector(f, lba, payload):
    f.seek(lba * SECTOR)
    sector = bytearray(f.read(SECTOR))
    sector[discfs.DATA_OFF:discfs.DATA_OFF + DATA] = payload.ljust(DATA, b"\0")
    fix_sector(sector)
    f.seek(lba * SECTOR)
    f.write(sector)


def patch_file(f, disc_path, data):
    rec_off, rec_lba, lba, size = find_record(f, disc_path)
    capacity = (size + DATA - 1) // DATA * DATA
    if len(data) > capacity:
        raise SystemExit(f"{disc_path}: {len(data)} bytes exceeds {capacity} allocated")
    for i in range(0, max(len(data), 1), DATA):
        rewrite_sector(f, lba + i // DATA, data[i:i + DATA])
    if len(data) != size:
        f.seek(rec_off + 10)
        f.write(struct.pack("<I", len(data)) + struct.pack(">I", len(data)))
        f.seek(rec_lba * SECTOR)
        sector = bytearray(f.read(SECTOR))
        fix_sector(sector)
        f.seek(rec_lba * SECTOR)
        f.write(sector)
    print(f"patched {disc_path}: {len(data)} bytes at LBA {lba}")


def verify(img, count):
    bad = 0
    with open(img, "rb") as f:
        for lba in range(16, 16 + count):
            f.seek(lba * SECTOR)
            orig = f.read(SECTOR)
            if orig[0x12] & 0x20:  # Form 2 sector, skip
                continue
            s = bytearray(orig)
            fix_sector(s)
            if bytes(s) != orig:
                bad += 1
    print(f"verify: {bad} mismatching sectors of {count}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Write files back into a MODE2/2352 PS1 image in place.")
    ap.add_argument("image")
    ap.add_argument("files", nargs="*", metavar="/PATH/ON/DISC=LOCAL", help="replacements")
    ap.add_argument("--verify", nargs="?", type=int, const=200, metavar="COUNT",
                    help="instead, self-test EDC/ECC on COUNT existing sectors (default: 200)")
    args = ap.parse_args()
    if args.verify is not None:
        verify(args.image, args.verify)
    else:
        img = args.image
        with open(img, "r+b") as f:
            for arg in args.files:
                disc_path, local = arg.split("=", 1)
                patch_file(f, disc_path, open(local, "rb").read())
