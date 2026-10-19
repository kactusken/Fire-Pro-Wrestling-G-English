#!/usr/bin/env python3
"""Export every roster wrestler's costumes and colours to CSV (docs/COSTUMES.md).

    python3 tools/costumes.py [--extracted PATH] [--text PATH] [--out FILE]

One row per wrestler and costume (194 x 4): stance, size, head, the eight body
parts (number, Wrestler Make name and build variant) and the 34 colours, as
#RRGGBB, with the preset set each colour group comes from. Reads the unpacked disc
(tools/extract.py): FPG 010 (roster), FPG 011 (colour table) and overlay 004
(Wrestler Make part lists), and the English names in text/.
"""
import argparse
import csv
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lzss  # noqa: E402
import paths  # noqa: E402
import roster  # noqa: E402
import strtab  # noqa: E402

RECORD, WRESTLERS, COSTUMES = 426, 194, 4
STANCE, SIZE = 0x5C, 0x5D          # roster record bytes
LOOKS = 0x182                      # 4 costumes x {u16 head, 8 part bytes}
COLOUR_TABLE = 0x24740             # in FPG 011, unpacked
GROUP_SIZES = [4, 3, 3, 3, 3, 3, 5, 3, 3, 4]   # EXE 0x80048F68; 34 colours in all
OVERLAY_BASE = 0x8005A718
ROWS = 0x80076478                  # Wrestler Make rows, 20 bytes each
STANCES = ["Strong", "Technic", "Amateur", "Power", "Lucha", "Shoot", "Mystery", "Koppo", "Kobudo"]
SIZES = ["S", "M", "L", "D"]
# part byte -> Wrestler Make row label (rows 3-10 hold the part lists)
SLOTS = ["chest", "waist", "bicep", "arm", "shin", "thigh", "wrist", "ankle"]


def colour_sets(fpg011):
    """-> function (wrestler, costume) -> [(set number, [10 colours]) per group]."""
    t = COLOUR_TABLE
    hw = struct.unpack_from("<32H", fpg011, t)
    counts = hw[hw[0]:hw[0] + 10]      # sets per group; 256 or more -> u16 indices

    def look(wrestler, costume):
        out = []
        for g in range(10):
            k = wrestler * COSTUMES + costume
            index_at = t + 2 * hw[1 + g]
            n = (struct.unpack_from("<H", fpg011, index_at + 2 * k)[0] if counts[g] >= 0x100
                 else fpg011[index_at + k])
            at = t + 2 * hw[11 + g] + 2 * n * GROUP_SIZES[g]
            out.append((n, list(struct.unpack_from(f"<{GROUP_SIZES[g]}H", fpg011, at))))
        return out
    return look


def part_names(ov004, en):
    """-> {(slot, part number): (name, variant)} from the Wrestler Make lists;
    variant is 1-4, or None for parts with a single version."""
    def word(a, fmt="<I"):
        return struct.unpack_from(fmt, ov004, a - OVERLAY_BASE)[0]

    names = {}
    for row in range(3, 11):
        r = ROWS + 20 * row
        lst, slot, total = word(r), ov004[r + 4 - OVERLAY_BASE], ov004[r + 18 - OVERLAY_BASE]
        for e in range(total):
            a = lst + 12 * e
            name_at, variants = word(a), ov004[a + 4 - OVERLAY_BASE]
            numbers = ov004[a + 5 - OVERLAY_BASE:a + 9 - OVERLAY_BASE]
            name = en.get(name_at)
            if name is None:
                o = name_at - OVERLAY_BASE
                name = ov004[o:ov004.index(b"\0", o)].decode("cp932")
            for v, p in enumerate(numbers[:max(variants, 1)]):
                names.setdefault((slot, p), (name, v + 1 if variants else None))
    return names


def rgb(c):
    """15-bit PlayStation colour (bits 0-4 red, 5-9 green, 10-14 blue) -> #RRGGBB."""
    r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
    return "#" + "".join(f"{(v << 3) | (v >> 2):02X}" for v in (r, g, b))


def header():
    cols = ["id", "name", "short", "costume", "stance", "size", "head"]
    for s in SLOTS:
        cols += [s, s + "_name", s + "_variant"]
    cols += [f"group{g}_set" for g in range(10)]
    cols += [f"group{g}_{i + 1}" for g in range(10) for i in range(GROUP_SIZES[g])]
    return cols


def rows(fpg010, fpg011, ov004, en, names_en):
    look = colour_sets(fpg011)
    names = part_names(ov004, en)
    for w in range(WRESTLERS):
        rec = fpg010[w * RECORD:(w + 1) * RECORD]
        short, full = names_en.get(w, ("", ""))[:2]
        for c in range(COSTUMES):
            at = LOOKS + 10 * c
            head = struct.unpack_from("<H", rec, at)[0]
            row = [w, full, short, c + 1, STANCES[rec[STANCE]], SIZES[rec[SIZE]], head]
            for s, p in enumerate(rec[at + 2:at + 10]):
                name, variant = names.get((s, p), ("", None))
                row += [p, name, variant or ""]
            groups = look(w, c)
            row += [n for n, _ in groups]
            row += [rgb(x) for _, cols in groups for x in cols]
            yield row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 2)[2])
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output")
    paths.add(ap, "--text", paths.TEXT, "translated text folder (English names)")
    paths.add(ap, "--out", os.path.join(paths.DOCS, "costumes.csv"), "CSV file to write")
    args = ap.parse_args(argv)

    def read(*parts):
        return open(os.path.join(args.extracted, *parts), "rb").read()
    fpg010 = lzss.decompress(read("fpg", "010.bin"))
    fpg011 = lzss.decompress(read("fpg", "011.bin"))
    ov004 = read("ovl", "004.bin")
    en = strtab.parse(os.path.join(args.text, "ov004.txt"))
    names_en = roster.load(os.path.join(args.text, "wrestlers.csv"))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(header())
        n = 0
        for row in rows(fpg010, fpg011, ov004, en, names_en):
            out.writerow(row)
            n += 1
    print(f"{args.out}: {n} rows")


if __name__ == "__main__":
    main()
