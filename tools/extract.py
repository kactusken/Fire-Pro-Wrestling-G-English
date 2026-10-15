#!/usr/bin/env python3
"""Unpack the original disc into extracted/ for the checking and research tools.

    python3 tools/extract.py [--rom PATH] [--out PATH] [--xa]

Writes:
  SLPS_020.65, SYSTEM.CNF, FPG.BIN   files from the disc (FPG.XA only with --xa: 221 MB of audio)
  fpg/NNN.bin                        every FPG.BIN entry as stored (most are LZSS-compressed)
  ovl/NNN.bin                        the code overlays (entries 000-005), decompressed

build.py does not need this; it reads the disc image directly.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discfs  # noqa: E402
import fpgbin  # noqa: E402
import lzss  # noqa: E402
import paths  # noqa: E402

OVERLAYS = ["000", "001", "002", "003", "004", "005"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    paths.add(ap, "--rom", paths.ROM, "original Japanese disc image (.bin)")
    paths.add(ap, "--out", paths.EXTRACTED, "output folder")
    ap.add_argument("--xa", action="store_true", help="also extract FPG.XA (audio, 221 MB)")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    with open(args.rom, "rb") as f:
        for name, lba, size, is_dir in discfs.walk(f):
            if is_dir or (name == "/FPG.XA" and not args.xa):
                continue
            with open(os.path.join(args.out, name.lstrip("/")), "wb") as o:
                o.write(discfs.read_extent(f, lba, size))
            print(f"{name} ({size} bytes)")
    fpg = os.path.join(args.out, "fpg")
    fpgbin.unpack(os.path.join(args.out, "FPG.BIN"), fpg)
    print(f"FPG.BIN entries -> {fpg}")
    ovl = os.path.join(args.out, "ovl")
    os.makedirs(ovl, exist_ok=True)
    for entry in OVERLAYS:
        data = lzss.decompress(open(os.path.join(fpg, f"{entry}.bin"), "rb").read())
        open(os.path.join(ovl, f"{entry}.bin"), "wb").write(data)
    print(f"overlays {OVERLAYS[0]}-{OVERLAYS[-1]} decompressed -> {ovl}")


if __name__ == "__main__":
    main()
