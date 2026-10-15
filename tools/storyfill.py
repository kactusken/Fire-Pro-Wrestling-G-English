#!/usr/bin/env python3
"""Put English into a story scene: python3 tools/storyfill.py <scene> <draft.txt> [--nowrap]
                                  [--script PATH] [--extracted PATH]

draft.txt has one block per message:
    @ NNN
    Speaker:            (optional; a line ending in ':')
    "Dialogue as one or more lines..."
Lines are re-wrapped to the 440 px story box (dialogue continuation lines get a
one-space indent) unless --nowrap; choices (lines starting with ・) are kept as is.
The EN lines of script/<scene>.txt are replaced; widths, line counts (3 + speaker)
and speaker labels are checked. Messages left out keep their Japanese.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import script  # noqa: E402
import vwf_patch  # noqa: E402


def load_draft(path):
    tr, cur = {}, None
    for ln in open(path, encoding="utf-8").read().split("\n"):
        if ln.startswith("@ "):
            cur = int(ln[2:])
            tr[cur] = []
        elif cur is not None and ln.strip():
            tr[cur].append(ln)
    return tr


def width(ln, metrics):
    codes = len(script.CODE_RE.findall(ln))
    plain = script.CODE_RE.sub("", ln)
    wide = sum(1 for ch in plain if ord(ch) > 0x7F)
    return vwf_patch.line_width(plain, metrics) + codes * script.CODE_WIDTH + wide * 20


def wrap(lines, metrics):
    if not lines or any(ln.startswith("・") for ln in lines):
        return lines
    label = [lines[0]] if lines[0].endswith(":") and len(lines[0]) < 40 else []
    words = " ".join(ln.strip() for ln in lines[len(label):]).split()
    quoted = bool(words) and words[0].startswith('"')
    out, cur = [], ""
    for w in words:
        cand = (cur + " " + w) if cur else ((" " if out and quoted else "") + w)
        if cur and width(cand, metrics) > script.LINE_LIMIT:
            out.append(cur)
            cur = (" " if quoted else "") + w
        else:
            cur = cand
    if cur:
        out.append(cur)
    return label + out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Put English from a draft into a story scene file.")
    ap.add_argument("scene", help="scene number as in the file name, e.g. 012")
    ap.add_argument("draft", help="draft text file")
    ap.add_argument("--nowrap", action="store_true", help="keep the draft's line breaks")
    paths.add(ap, "--script", paths.SCRIPT, "story script folder")
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output (for the font)")
    args = ap.parse_args(argv)

    metrics = vwf_patch.metrics(open(os.path.join(args.extracted, "fpg", "128.bin"), "rb").read())
    tr = load_draft(args.draft)
    if not args.nowrap:
        tr = {m: wrap(v, metrics) for m, v in tr.items()}
    path = os.path.join(args.script, f"{args.scene}.txt")
    out, msg, jp = [], None, {}
    for ln in open(path, encoding="utf-8").read().split("\n"):
        if ln.startswith("@ "):
            msg = int(ln[2:])
        if ln.startswith("EN "):
            continue
        out.append(ln)
        if ln.startswith("JP "):
            jp.setdefault(msg, []).append(ln)
    # EN lines go after the last JP line of each message
    final, cur = [], None
    for k, ln in enumerate(out):
        final.append(ln)
        if ln.startswith("@ "):
            cur = int(ln[2:])
        nxt = out[k + 1] if k + 1 < len(out) else ""
        if ln.startswith("JP ") and not nxt.startswith("JP ") and cur in tr:
            final += ["EN " + e for e in tr[cur]]
    open(path, "w", encoding="utf-8").write("\n".join(final))

    missing, extra = sorted(set(jp) - set(tr)), sorted(set(tr) - set(jp))
    for m, lines in sorted(tr.items()):
        body = lines[1:] if lines and lines[0].endswith(":") else lines
        if len(body) > 3:
            print(f"!! @{m:03d}: {len(body)} text lines (max 3 + speaker)")
        if m in jp and lines[0].endswith(":") != jp[m][0].rstrip().endswith(("：", ":")):
            print(f"!! @{m:03d}: speaker label mismatch")
        script.check_message(lines, metrics, f"@{m:03d}")
    print(f"scene {args.scene}: {len(tr)} translated, missing {missing}, extra {extra}")


if __name__ == "__main__":
    main()
