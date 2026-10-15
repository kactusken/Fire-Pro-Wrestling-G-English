#!/usr/bin/env python3
"""Check every story scene: python3 tools/storylint.py [scene...] [--extracted PATH] [--script PATH]

Reports messages without English (other than 削除), leftover #W codes or Japanese in the
English, more than 3 text lines (+ speaker), speaker-label mismatches, and lines too wide
for the box (via script.check_message)."""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import script  # noqa: E402
import vwf_patch  # noqa: E402

JP_IN_EN = re.compile(r"[぀-ヿ一-鿿！-～]")
CODES_ONLY = re.compile(r"^(?:#[A-Z]+\d*|[\s　])*$")   # e.g. save-slot lines "　#S00"


def messages(path):
    cur, out = None, {}
    for line in open(path, encoding="utf-8").read().split("\n"):
        if line.startswith("@ "):
            cur = int(line[2:])
            out[cur] = ([], [])
        elif line.startswith("JP "):
            out[cur][0].append(line[3:])
        elif line.startswith("EN "):
            out[cur][1].append(line[3:])
    return out


def lint_file(path, metrics=None):
    """Problems in one scene file, as "NNN @MMM: ..." strings. With the story font's
    metrics, lines that are too wide are reported too (as warnings, printed by
    script.check_message, not counted here)."""
    name = os.path.basename(path)[:3]
    problems = []
    for m, (jp, en) in messages(path).items():
        where = f"{name} @{m:03d}"
        if not en:
            if jp != ["削除"] and not CODES_ONLY.match("".join(jp)):
                problems.append(f"{where}: no English")
            continue
        text = " ".join(en)
        if re.search(r"#W[SLFN]\d", text):
            problems.append(f"{where}: wrestler code left in English")
        if JP_IN_EN.search(text.replace("・", "").replace("　", "")):
            problems.append(f"{where}: Japanese in English: {text[:60]}")
        label = en[0].endswith(":") and len(en[0]) < 40
        jp_label = jp[0].rstrip().endswith(("：", ":"))
        if label != jp_label:
            problems.append(f"{where}: speaker label mismatch")
        if len(en) - label > 3:
            problems.append(f"{where}: {len(en) - label} text lines")
        if metrics:
            script.check_message(en, metrics, where)
    return problems


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Check every story scene for missing or badly formed English.")
    ap.add_argument("scenes", nargs="*", metavar="scene", help="scene numbers (default: all)")
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output (for the font)")
    paths.add(ap, "--script", paths.SCRIPT, "story script folder")
    args = ap.parse_args(argv)
    metrics = vwf_patch.metrics(open(os.path.join(args.extracted, "fpg", "128.bin"), "rb").read())
    files = [os.path.join(args.script, f"{int(s):03d}.txt") for s in args.scenes] or \
        sorted(glob.glob(os.path.join(args.script, "[0-9][0-9][0-9].txt")))
    problems = 0
    for f in files:
        for p in lint_file(f, metrics):
            print(p)
            problems += 1
    print(f"{len(files)} scenes checked, {problems} problems (plus any width warnings above)")
    return problems


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
