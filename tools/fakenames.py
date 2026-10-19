#!/usr/bin/env python3
"""Fake-names variant: the game's own stand-in names instead of the real ones.

The translation uses real names (New Japan, Riki Choshu, Tiger Hattori). For
`build.py --fake-names`, make_tree() writes a copy of the text and script folders
with the game's stand-ins (VIEW JAPAN, Hurricane Rikimaru, Panther Tottori), and the
build reads that copy instead:

- text/fake_roster.tsv replaces the roster names in wrestlers.tsv;
- text/fake_names.tsv rules swap names in the English of every JP/EN text file
  (story scenes, menu strings, profiles) and of edit_wrestlers.tsv;
- FAKE_NAMES in text/exe_promotions.py replaces NAMES;
- text/fake_script.txt holds hand-written English for story messages that the
  swap leaves too long or awkward (`@ <scene> <message>` and EN lines).

Rules (text/fake_names.tsv) are `real<TAB>fake[<TAB>when]`. Matches are whole words,
case-sensitive, longest first. A rule with `when` (a regular expression) applies only
if it matches the Japanese of the message, else of the whole file (story scene);
the rules for one name are tried in order and the first that applies wins, so put
the default (no `when`) last.

Story messages with a line that no longer fits the box are re-wrapped
(storyfill.wrap); the build warns about any still too long.

Run on its own to review the result:
    python3 tools/fakenames.py            # summary: changes, re-wraps, unused rules
    python3 tools/fakenames.py --diff     # every changed English line
"""
import argparse
import glob
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import script  # noqa: E402
import storyfill  # noqa: E402

ROSTER, RULES, OVERRIDES = "fake_roster.tsv", "fake_names.tsv", "fake_script.txt"
SEP = r"(?: |\n ?)"            # between the words of a name
SKIP = {"wrestler_list.txt", OVERRIDES}   # not JP/EN text read by the build


def load_rules(path):
    """-> [(real, fake, when regex or None)] in file order."""
    rules = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        cols = [c for c in line.split("\t") if not c.startswith("#")]
        if len(cols) < 2 or not cols[0]:
            raise SystemExit(f"{path}:{n}: expected real<TAB>fake[<TAB>when]")
        when = re.compile(cols[2]) if len(cols) > 2 and cols[2] else None
        rules.append((cols[0], cols[1], when))
    return rules


class Swapper:
    def __init__(self, rules):
        self.rules = {}
        for real, fake, when in rules:
            self.rules.setdefault(real, []).append((fake, when))
        names = sorted(self.rules, key=len, reverse=True)
        # Spaces in a name also match a line break (with its indent) between
        # the lines of a message; a word boundary also holds after a literal
        # "\n" (profiles, tutorial).
        alts = "|".join(SEP.join(re.escape(w) for w in n.split(" ")) for n in names)
        self.rx = re.compile(r"(?:(?<=\\n)|(?<![A-Za-z0-9]))(" + alts + r")(?![A-Za-z0-9])")
        self.used = {}

    def pick(self, real, jp, file_jp):
        for context in (jp, file_jp):
            for fake, when in self.rules[real]:
                if when and when.search(context):
                    return fake
        for fake, when in self.rules[real]:
            if not when:
                return fake
        return None

    def swap(self, lines, jp, file_jp):
        """lines: the English lines of one entry -> the lines with names swapped."""
        def sub(m):
            parts = re.split("(" + SEP + ")", m.group(1))
            real = " ".join(parts[::2])
            fake = self.pick(real, jp, file_jp)
            if fake is None:
                return m.group(0)
            self.used[real, fake] = self.used.get((real, fake), 0) + 1
            # keep a line break inside the name: after the same word, or
            # before the whole name if the fake has fewer words
            words, seps = fake.split(" "), parts[1::2]
            brk = next((i for i, s in enumerate(seps) if "\n" in s), None)
            if brk is None:
                return fake
            if brk < len(words) - 1:
                return " ".join(words[:brk + 1]) + seps[brk] + " ".join(words[brk + 1:])
            return seps[brk] + fake
        out = self.rx.sub(sub, "\n".join(lines)).split("\n")
        return [new.rstrip(" ") if new != old else new for new, old in zip(out, lines)]


def blocks(lines):
    """Split a JP/EN text file into [header lines], [[block lines]] at each '@ '."""
    head, out = [], []
    for ln in lines:
        if ln.startswith("@ "):
            out.append([ln])
        elif out:
            out[-1].append(ln)
        else:
            head.append(ln)
    return head, out


def load_overrides(path):
    """-> {(scene file, message header): [EN lines]}"""
    out, key = {}, None
    for line in open(path, encoding="utf-8").read().split("\n"):
        if line.startswith("@ "):
            scene, msg = line[2:].split()
            key = (scene + ".txt", "@ " + msg)
            out[key] = []
        elif line.startswith("EN ") and key:
            out[key].append(line[3:])
    return out


def swap_text_file(src, dst, swapper, metrics, story, log, overrides=None):
    lines = open(src, encoding="utf-8").read().split("\n")
    head, blks = blocks(lines)
    file_jp = "\n".join(ln[3:] for ln in lines if ln.startswith("JP "))
    out = list(head)
    name = os.path.basename(src)
    for blk in blks:
        jp = "\n".join(ln[3:] for ln in blk if ln.startswith("JP "))
        en = [ln[3:] for ln in blk if ln.startswith("EN ")]
        new = swapper.swap(en, jp, file_jp)
        if overrides and (name, blk[0]) in overrides:
            new = overrides.pop((name, blk[0]))
            log.append(("hand", name, blk[0], en, new))
        elif new != en:
            if story and metrics and any(storyfill.width(ln, metrics) > script.LINE_LIMIT for ln in new):
                new = storyfill.wrap(new, metrics)
                log.append(("wrap", name, blk[0], en, new))
            else:
                log.append(("swap", name, blk[0], en, new))
        if new == en:
            out += blk
            continue
        first = next(i for i, ln in enumerate(blk) if ln.startswith("EN "))
        rest = [ln for ln in blk[first:] if not ln.startswith("EN ")]
        out += blk[:first] + ["EN " + ln for ln in new] + rest
    open(dst, "w", encoding="utf-8").write("\n".join(out))


def swap_edit_wrestlers(src, dst, swapper, log):
    out = []
    for line in open(src, encoding="utf-8").read().split("\n"):
        c = line.split("\t")
        if line.startswith("#") or len(c) < 6 or c[0] == "id":
            out.append(line)
            continue
        new = c[:2] + [swapper.swap([t], c[1], "")[0] for t in c[2:]]
        if new != c:
            log.append(("swap", os.path.basename(src), c[0], c[2:], new[2:]))
        out.append("\t".join(new))
    open(dst, "w", encoding="utf-8").write("\n".join(out))


def swap_roster(src, fake_path, dst):
    fake = {}
    for line in open(fake_path, encoding="utf-8"):
        c = line.rstrip("\n").split("\t")
        if c and c[0].isdigit():
            fake[c[0]] = c
    out = []
    for line in open(src, encoding="utf-8").read().split("\n"):
        c = line.split("\t")
        if c and c[0].isdigit():
            f = fake[c[0]]
            if f[1] != c[7]:
                raise SystemExit(f"{fake_path}: {c[0]} is {f[1]!r} here but {c[7]!r} in wrestlers.tsv")
            c[6], c[7] = f[2], f[3]
            c[8] = f[4] or c[8]
            line = "\t".join(c)
        out.append(line)
    open(dst, "w", encoding="utf-8").write("\n".join(out))


def make_tree(text_dir, script_dir, out_dir, metrics=None):
    """Write <out_dir>/text and <out_dir>/script with the fake names.
    -> (text folder, script folder, log, rules that never matched); log entries are
    (kind, file, where, old EN, new EN)."""
    text_out, script_out = os.path.join(out_dir, "text"), os.path.join(out_dir, "script")
    for d in (text_out, script_out):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    swapper = Swapper(load_rules(os.path.join(text_dir, RULES)))
    overrides = load_overrides(os.path.join(text_dir, OVERRIDES))
    log = []
    for src in sorted(glob.glob(os.path.join(script_dir, "*.txt"))):
        swap_text_file(src, os.path.join(script_out, os.path.basename(src)), swapper, metrics,
                       True, log, overrides)
    if overrides:
        raise SystemExit(f"{OVERRIDES}: no such message: " +
                         ", ".join(f"{f[:-4]} {m[2:]}" for f, m in overrides))
    for name in sorted(os.listdir(text_dir)):
        src, dst = os.path.join(text_dir, name), os.path.join(text_out, name)
        if not os.path.isfile(src):
            continue
        if name.endswith(".txt") and name not in SKIP:
            swap_text_file(src, dst, swapper, metrics, name == "ov002_scene.txt", log)
        elif name == "edit_wrestlers.tsv":
            swap_edit_wrestlers(src, dst, swapper, log)
        elif name == "wrestlers.tsv":
            swap_roster(src, os.path.join(text_dir, ROSTER), dst)
        elif name == "exe_promotions.py":
            shutil.copyfile(src, dst)
            with open(dst, "a", encoding="utf-8") as f:
                f.write("\nNAMES = FAKE_NAMES   # added by tools/fakenames.py\n")
        else:
            shutil.copyfile(src, dst)
    unused = [real for real, opts in swapper.rules.items()
              if not any((real, fake) in swapper.used for fake, _ in opts)]
    return text_out, script_out, log, unused


def main(argv=None):
    ap = argparse.ArgumentParser(description="Preview the fake-names text (build.py --fake-names).")
    paths.add(ap, "--text", paths.TEXT, "translated text folder")
    paths.add(ap, "--script", paths.SCRIPT, "story script folder")
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output (for the story font)")
    paths.add(ap, "--out", os.path.join(paths.BUILD, "fake-names"), "where to write the copy")
    ap.add_argument("--diff", action="store_true", help="print every changed English line")
    ap.add_argument("--unused", action="store_true", help="list the rules that never matched")
    args = ap.parse_args(argv)

    import vwf_patch
    font = os.path.join(args.extracted, "fpg", "128.bin")
    metrics = vwf_patch.metrics(open(font, "rb").read()) if os.path.exists(font) else None
    _, _, log, unused = make_tree(args.text, args.script, args.out, metrics)
    if args.diff:
        for kind, name, where, old, new in log:
            note = {"wrap": "  (re-wrapped)", "hand": "  (fake_script.txt)"}.get(kind, "")
            print(f"{name} {where}{note}")
            for ln in old:
                print("  - " + ln)
            for ln in new:
                print("  + " + ln)
    wraps = [e for e in log if e[0] == "wrap"]
    print(f"{len(log)} entries changed, {len(wraps)} story messages re-wrapped; written to {args.out}")
    for _, name, where, _, new in wraps:
        body = new[1:] if new and new[0].endswith(":") else new
        if len(body) > 3:
            print(f"  too long after re-wrapping: {name} {where} ({len(body)} lines)")
    if unused:
        print(f"{len(unused)} rules never matched" +
              (": " + ", ".join(unused) if args.unused else " (--unused lists them)"))


if __name__ == "__main__":
    main()
