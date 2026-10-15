#!/usr/bin/env python3
"""Export the unused illustrations in FPG 275 to PNG (docs/HIDDEN_CONTENT.md).

FPG 275: u32 offset table (14 entries, the last empty), each entry an
LZSS-compressed 8-bit TIM: entries 3-7 are 640x480, the rest 320x240. Nothing
in the game loads the file.

Usage: unused_art.py [--src PATH] [--out PATH]
  defaults: extracted/fpg/275.bin -> extracted/images/fpg275/
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lzss  # noqa: E402
import paths  # noqa: E402
import tim  # noqa: E402


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Export the unused illustrations in FPG 275 to PNG.")
    paths.add(ap, "--src", os.path.join(paths.EXTRACTED, "fpg", "275.bin"), "FPG entry 275 as stored")
    paths.add(ap, "--out", os.path.join(paths.EXTRACTED, "images", "fpg275"), "output folder")
    args = ap.parse_args(argv)
    src, outdir = args.src, args.out
    data = open(src, "rb").read()
    count = struct.unpack_from("<I", data, 0)[0] // 4
    offs = list(struct.unpack_from(f"<{count}I", data, 0)) + [len(data)]
    os.makedirs(outdir, exist_ok=True)
    for i in range(count):
        packed = data[offs[i]:offs[i + 1]]
        if not packed:
            continue
        image = tim.Tim(lzss.decompress(packed))
        # colour 0x0000 means transparent to the GPU; these are full-screen pictures
        rows = [[(r, g, b, 255) for r, g, b, _ in row] for row in image.rgba()]
        path = os.path.join(outdir, f"{i:02d}.png")
        tim.write_png_rgba(path, rows)
        print(f"{path}: {image.width}x{image.height}")


if __name__ == "__main__":
    main()
