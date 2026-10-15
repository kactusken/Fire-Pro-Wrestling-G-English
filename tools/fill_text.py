#!/usr/bin/env python3
"""Fill EN lines of a strtab text file from a JP -> EN table.

Usage: fill_text.py <text/ovNNN.txt> <table.py> [--overwrite]
The table module defines EN = {jp: en}. Strings with no English yet get it from the
table; strings that already have English keep it unless --overwrite is given
(the text file is the one the build reads, and may hold later hand fits).
Prints the JP strings that are still untranslated.
"""
import runpy


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Fill EN lines of a strtab text file from a JP -> EN table.")
    ap.add_argument("path", help="text file to update, e.g. text/ov005.txt")
    ap.add_argument("table", help="Python file defining EN = {jp: en}, e.g. text/ov005_en.py")
    ap.add_argument("--overwrite", action="store_true",
                    help="also replace existing English with the table's")
    args = ap.parse_args(argv)
    en = runpy.run_path(args.table)["EN"]

    # blocks start at "@" lines; each holds one JP line and its EN lines
    blocks = [[]]
    with open(args.path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    for line in lines:
        if line.startswith("@"):
            blocks.append([])
        blocks[-1].append(line)
    out, missing, filled = [], [], 0
    for block in blocks:
        jp = next((ln[3:] for ln in block if ln.startswith("JP ")), None)
        has_en = any(ln.startswith("EN ") or ln == "EN" for ln in block)
        if jp is not None and jp in en and (args.overwrite or not has_en):
            block = [ln for ln in block if not (ln.startswith("EN ") or ln == "EN")]
            at = max(i for i, ln in enumerate(block) if ln.startswith("JP ")) + 1
            block.insert(at, f"EN {en[jp]}")
            filled += 1
        elif jp is not None and not has_en:
            missing.append(jp)
        out += block
    with open(args.path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))
    for m in missing:
        print("untranslated:", m)
    print(f"{filled} filled, {len(missing)} untranslated")


if __name__ == "__main__":
    main()
