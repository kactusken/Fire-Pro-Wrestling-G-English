#!/usr/bin/env python3
"""Decode the Fighting Road battle table (overlay 002) into docs/story_battles.tsv.

ov2 0x800662a0: 520 s16, the battle number of each scene's match (-1 = none).
ov2 0x80064f28: 356 battle records of 14 bytes, read by the match setup 0x800600f0:
  +0   rules preset: index into the 6-byte presets at 0x80064dcc
       {venue -> +0x981, ring -> +0x982, u16 rule flags -> +0x97a, rules -> +0x97c, referee -> +0x984}
  +1   COM level 1-6 (minus 1 -> setting +0x983)
  +2   wrestlers in the match: 2 = singles, 4 = tag
  +4   u16 opponent            (match slot 2, +0x708)
  +6   u16 opponent's partner  (slot 3, +0x966; tag only)
  +8   u16 hero's partner      (slot 1, +0x4aa; tag only)
  +10  copied to story state +0x49 (by 0x80060f4c)
  +13  match music (setting +0x985); 9 = random 0-3
  +3, +11, +12  not read by the setup
Wrestler ids: low 9 bits = roster index, bits 9-10 = variant (EXE 0x8001938c);
0xFFF0-0xFFF3 = FPG 127 records 8-11 (Sakagami's four versions, loaded as edit records).

Usage: storybattles.py [--ov002 PATH] [--out PATH] [--extracted PATH] [--text PATH]
  defaults: decompress FPG 002 from extracted/fpg, write docs/story_battles.tsv
"""
import collections
import csv
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lzss  # noqa: E402
import paths  # noqa: E402

EXTRACTED, TEXT = paths.repo(paths.EXTRACTED), paths.repo(paths.TEXT)
BASE = 0x8005A718
SCENE_BATTLE, SCENES = 0x800662A0, 520
BATTLES, BATTLE_SIZE, BATTLE_COUNT = 0x80064F28, 14, 356
PRESETS, PRESET_SIZE = 0x80064DCC, 6
# ov1 0x80088df8 (venue names, by setting +0x981) and 0x80088e44 (referees, by +0x984)
VENUES = ["Nippon Budokan", "HUMAN DOME", "Yurakuen Hall", "Murakawa Town Gym", "Yamamoto Dojo?",
          "Bayside Coliseum", "Kawashima Stadium"]
# venue 4 (no name in the game) and referee 4 are only used by battles 0-2, the
# prologue training matches at the dojo
REFEREES = ["T. Hattori", "J. Higuchi", "Soranaka", "T. Tanabe"]
# Match-setup option values (ov1 tables 0x80088d64-0x80088e7c, display code 0x800600f0+)
RULES = ["3-count", "2-count", "pinfall only", "submission only"]       # +0x97c
MUSIC = ["Ring-Side", "Biorhythm", "Fujiyama", "Blue-Thunder", "FR:GOOD", "FR:BAD",
         "Musashi's Theme", "Hikawa's Theme"]                            # +0x985, EXE 0x800492f0
MUSIC_RANDOM = 9            # story records only: random 0-3
# +0x97a bits shown as ON/OFF options (set = ON); 0x01 = 2 of 3 falls; 0x100+ are not options
RULE_FLAGS = [(0x02, "Rope Check"), (0x04, "Lumberjack"), (0x08, "Tornado"), (0x10, "Cut Play"),
              (0x20, "Foul Count"), (0x40, "COM Skip"), (0x80, "Ring-out Count")]


RING_NAMES = 0x800492B0   # EXE: 16 pointers to the ring names, by match-setup list position (0x8001a580)
RING_VALUES = 0x800103A0  # EXE: 16 bytes, list position -> ring value stored in +0x982 (0x8001a494)


def ring_names(extracted=EXTRACTED, text=TEXT):
    """Ring names by ring value (+0x982), as the patched game shows them: text/exe.txt where
    translated, else the EXE string. The names are listed by menu position; RING_VALUES maps
    each position to the value the match setting stores."""
    exe = open(os.path.join(extracted, "SLPS_020.65"), "rb").read()
    def off(a):
        return a - 0x80010000 + 0x800
    english, cur = {}, None
    for ln in open(os.path.join(text, "exe.txt"), encoding="utf-8"):
        if ln.startswith("@ "):
            cur = int(ln.split()[1], 16)
        elif ln.startswith("EN ") and cur is not None:
            english.setdefault(cur, ln[3:].rstrip("\n"))
    out = [None] * 16
    for pos in range(16):
        p = struct.unpack_from("<I", exe, off(RING_NAMES) + 4 * pos)[0]
        name = english.get(p) or exe[off(p):exe.index(b"\0", off(p))].decode("cp932")
        out[exe[off(RING_VALUES) + pos]] = name
    return out


def ring_name(n, rings):
    """+0x982: ring value 0-15, 0x20 special death match ring, 0x40 octagon, 0x7f random."""
    if n == 0x20:
        return "Death Match ring"
    if n == 0x40:
        return "Octagon ring"
    if n == 0x7F:
        return "random ring"
    return f"{rings[n]} ring" if n < len(rings) else f"ring {n}"


def decode(rec, preset, rings):
    """Match settings of one battle record and its rules preset."""
    flags = preset[2] | preset[3] << 8
    music = rec[13]
    return {
        "venue": VENUES[preset[0]] if preset[0] < len(VENUES) else f"venue {preset[0]}",
        "referee": REFEREES[preset[5]] if preset[5] < len(REFEREES) else None,
        "ring": ring_name(preset[1], rings),
        "rules": RULES[preset[4]] if preset[4] < len(RULES) else f"rules {preset[4]}",
        "falls": "2 of 3 falls" if flags & 1 else "1 fall",
        "com_level": rec[1],
        "music": ("random (" + "/".join(MUSIC[:4]) + ")" if music == MUSIC_RANDOM
                  else MUSIC[music] if music < len(MUSIC) else f"music {music}"),
        "on": [name for bit, name in RULE_FLAGS if flags & bit],
        "flags": flags,
    }


def load_names(text=TEXT):
    names = {}
    with open(os.path.join(text, "wrestlers.tsv"), encoding="utf-8") as f:
        rows = [r for r in csv.reader(f, delimiter="\t") if r and not r[0].startswith("#")]
    head = rows[0]
    for r in rows[1:]:
        names[int(r[head.index("idx")])] = r[head.index("en_full")]
    templates = {}
    with open(os.path.join(text, "edit_wrestlers.tsv"), encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r and r[0].startswith("127:"):
                templates[int(r[0][4:])] = f"{r[3]} ({r[4]})"
    return names, templates


def wrestler(wid, names, templates):
    if wid >= 0xFFF0:
        return templates.get(wid - 0xFFE8, f"FPG 127 #{wid - 0xFFE8}")
    name = names.get(wid & 0x1FF, f"roster {wid & 0x1FF}")
    variant = (wid >> 9) & 3
    return name + (f" [variant {variant}]" if variant else "")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Decode the Fighting Road battle table into a TSV.")
    ap.add_argument("--ov002", metavar="PATH",
                    help="decompressed overlay 002 (default: decompress <extracted>/fpg/002.bin)")
    paths.add(ap, "--out", os.path.join(paths.DOCS, "story_battles.tsv"), "output TSV")
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output")
    paths.add(ap, "--text", paths.TEXT, "text folder (exe.txt, wrestlers.tsv, edit_wrestlers.tsv)")
    args = ap.parse_args(argv)
    out = args.out
    if args.ov002:
        ov = open(args.ov002, "rb").read()
    else:
        ov = lzss.decompress(open(os.path.join(args.extracted, "fpg", "002.bin"), "rb").read())
    names, templates = load_names(args.text)
    rings = ring_names(args.extracted, args.text)
    scene_battle = struct.unpack_from(f"<{SCENES}h", ov, SCENE_BATTLE - BASE)
    scenes = collections.defaultdict(list)
    for s, b in enumerate(scene_battle):
        if b >= 0:
            scenes[b].append(s)
    rows = []
    for n in range(BATTLE_COUNT):
        r = ov[BATTLES - BASE + BATTLE_SIZE * n:BATTLES - BASE + BATTLE_SIZE * (n + 1)]
        p = ov[PRESETS - BASE + PRESET_SIZE * r[0]:PRESETS - BASE + PRESET_SIZE * (r[0] + 1)]
        opp, opp2, partner = struct.unpack_from("<3H", r, 4)
        tag = r[2] == 4
        m = decode(r, p, rings)
        rows.append([
            n, " ".join(f"{s:03d}" for s in scenes[n]), "tag" if tag else "single",
            wrestler(opp, names, templates),
            wrestler(opp2, names, templates) if tag else "",
            wrestler(partner, names, templates) if tag else "",
            m["venue"], m["referee"] or f"referee {p[5]}", m["ring"], m["rules"], m["falls"],
            m["com_level"], m["music"], ", ".join(m["on"]), f"{m['flags']:04x}", r[0], r.hex(" ")])
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Fighting Road battles, decoded by tools/storybattles.py (see its docstring).\n"
                "# Values are named from the match-setup option tables in overlay 001. flags: setting +0x97a.\n")
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["battle", "scenes", "type", "opponent", "opponent_partner", "hero_partner",
                    "venue", "referee", "ring", "rules", "falls", "com_level", "music", "rules_on",
                    "flags", "preset", "raw"])
        w.writerows(rows)
    print(f"{len(rows)} battles -> {out}")


if __name__ == "__main__":
    main()
