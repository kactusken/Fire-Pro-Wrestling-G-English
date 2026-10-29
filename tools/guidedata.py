#!/usr/bin/env python3
"""The player's guide's data block (docs/guide/index.html).

    python3 tools/guidedata.py [--check] [--json FILE]

Reads the ORIGINAL game's tables from the unpacked disc (tools/extract.py) and the English
from text/, so the guide always shows the patch's names, in both name versions (the real
names and the game's own stand-ins of the Fake Names patches). --check exits 1 if the page
is out of date; --json also dumps the data, indented, for inspection.

What goes in (docs/TECHNICAL.md and docs/MOVES.md have the layouts):
- names: {token: [real, fake]} for every <span class="nm" data-k="token">Real name</span> in
  the page's prose; the fake name comes from the Fake Names build's own rules
  (text/fake_names.csv, tools/fakenames.py).
- promos: the 15 promotions, [[real full, fake full], [real short, fake short]]
  (text/exe_promotions.py NAMES / FAKE_NAMES).
- skill: the Skill Edit rows (overlay 004 0x80076954, tools/skilledit.py): label, record
  offset and choice list, in the screen's order.
- w: the 194 roster wrestlers (FPG 010, 426-byte records): names in both versions
  (text/wrestlers.csv, text/fake_roster.csv), promotion +0x44, division +0, height, weight,
  birthplace (EXE list 0x80048fd4), birthday, the Skill Edit values, the ten offence
  (+0x5F) and ten defence (+0x69) values, the 57 move slots (+0x74) and whether the wrestler
  starts locked (EXE 0x800494e4, one byte per wrestler).
- ew: the 30 fighters of Edit Ranking (FPG 013 0x4E28, 512-byte edit records; names, finisher
  name and profiles from text/edit_wrestlers.csv and text/edit_profiles.txt), with the same
  fields as w plus their custom finisher name (f) and profile (pf).
- entries: the guide search's index of wrestlers.
- logic: CPU Logic's layout (overlay 004: situations 0x80074DFC, conditions 0x80074E8C,
  actions 0x80074FBC). Each wrestler's 156 bytes at +0xE6 hold, per condition, the
  cumulative thresholds of its actions but the last (an action's chance is its threshold minus
  the one before; the last action takes what is left of 100).
- crit: the critical type names by stored value (a move's critical bits, record +0x54); Skill
  Edit lists them in another order (overlay 004 0x8007668C maps value -> option). The Skill
  Edit values in sk are option indexes, so they index the row's choices.
- ratings: the ten attack and ten defence rating names (tools/movedata.py).
- slots / cats: Move Edit's 57 slots and the 30 lists they offer (overlay 004 0x80078C60; the
  level 9 set 0x800791B8 adds the hidden moves); slots offering the same list share a category.
- mv: every move a wrestler or a list uses: name and its status block values (FPG 274).
- story: Fighting Road's scenes and branches for the route map (tools/storymap.py), with the
  script's name codes resolved (#MS / #MF the player as "Hero", #PSnn / #PLnn a promotion).
"""
import argparse
import json
import os
import re
import runpy
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import editdata  # noqa: E402
import fakenames  # noqa: E402
import lzss  # noqa: E402
import movedata  # noqa: E402
import pagedata  # noqa: E402
import paths  # noqa: E402
import roster  # noqa: E402
import skilledit  # noqa: E402
import storymap  # noqa: E402
import strtab  # noqa: E402
import table  # noqa: E402

EXE_BASE = 0x80010000 - 0x800          # file offset = address - EXE_BASE
BIRTHPLACES, BIRTHPLACE_COUNT = 0x80048FD4, 32
LOCKED = 0x800494E4                    # 194 bytes: 1 = starts locked
OFFENCE_AT, DEFENCE_AT = 0x5F, 0x69
SKIP_ROWS = {0x00, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44}   # shown in the profile header
VOICE_ROWS = {0x58, 0x5A}

# Move Edit's lists, in screen order, with the guide's names (the slots that offer each)
CATEGORY_TITLES = [
    "Standing strikes", "Standing big moves", "Running attacks", "Counters to a running opponent",
    "Diagonal run", "Dives to the outside", "Planchas", "From the apron", "Off the top rope",
    "Grapples: weak", "Grapples: medium", "Grapples: strong", "From behind: weak",
    "From behind: medium", "From behind: strong", "Reversal from behind: weak",
    "Reversal from behind: medium", "Downed opponent: face up, at the head",
    "Downed opponent: face up, at the legs", "Downed opponent: face down, at the head",
    "Downed opponent: face down, at the legs", "Running attacks on a downed opponent",
    "Opponent in the corner", "Taunts", "Double-team: in front", "Triple-team: in front",
    "Double-team: from behind", "Triple-team: from behind", "Double-team: in the corner",
    "Triple-team: in the corner",
]
VERSIONS = ("real", "fake")
EDIT_AT, EDIT_REC, EDIT_COUNT = 0x4E28, 512, 30
CRIT_OPTION = 0x8007668C               # overlay 004: critical value -> Skill Edit option (6 bytes)
NAME_SPAN = re.compile(r'<span class="nm" data-k="([^"]+)">([^<]*)</span>')
LOGIC_SITUATIONS, LOGIC_CONDITIONS, LOGIC_ACTIONS = 0x80074DFC, 0x80074E8C, 0x80074FBC
LOGIC_AT, LOGIC_SIZE = 0xE6, 156


def exe_string(exe, addr):
    o = addr - EXE_BASE
    return exe[o:exe.index(b"\0", o)].decode("cp932")


def both(real, fake):
    return real if real == fake else [real, fake]


def promotions(text):
    ns = runpy.run_path(os.path.join(text, "exe_promotions.py"))
    real, fake = ns["NAMES"], ns["FAKE_NAMES"]
    return [[both(r[0], f[0]), both(r[1], f[1])] for r, f in zip(real, fake)]


def skill_rows(ov004, en):
    """[{l: label, o: record offset, c: [choices] or None, x: suffix, lo: first index}]"""
    base = skilledit.OVERLAY_BASE

    def s(a):
        return en.get(a) or skilledit._string(ov004, a).decode("cp932")
    rows = []
    for _addr, (flags, opts, suffix, label, off) in skilledit._rows(ov004):
        if off in SKIP_ROWS or off in VOICE_ROWS or s(label).endswith("Exit"):
            continue
        choices = None
        if opts and base <= opts < base + len(ov004):
            choices = []
            for k in range((flags >> 24) + 1):
                p = struct.unpack_from("<I", ov004, opts + 4 * k - base)[0]
                choices.append(s(p) if p else "")
        label = s(label).replace("#x8,- ", "")
        if label == "Bleeding":
            label = rows[-1]["l"] + " (bleeding)"
        rows.append({"l": label, "o": off, "c": choices,
                     "x": s(suffix) if suffix and base <= suffix < base + len(ov004) else ""})
    return rows


def cpu_logic(ov004, en):
    """[{s: situation, c: [{n: condition, d: data index, a: [[label, slot or -1], ...]}]}]"""
    base = skilledit.OVERLAY_BASE

    def s(a):
        return (en.get(a) or skilledit._string(ov004, a).decode("cp932")).split(",")[-1]
    out = []
    for k in range(1, 16):
        label, first, n = struct.unpack_from("<IBB", ov004, LOGIC_SITUATIONS - base + 8 * k)
        conds = []
        for c in range(first, first + n):
            cl, act, na, data = struct.unpack_from("<IBBB", ov004, LOGIC_CONDITIONS - base + 8 * c)
            acts = []
            for a in range(act, act + na):
                al, code = struct.unpack_from("<IH", ov004, LOGIC_ACTIONS - base + 8 * a)
                acts.append([s(al), code // 2 if code < 0x200 else -1])
            conds.append({"n": s(cl), "d": data, "a": acts})
        out.append({"s": s(label), "c": conds})
    return out


def roster_names(text):
    real = roster.load(os.path.join(text, "wrestlers.csv"))
    fake = {}
    for c in table.read(os.path.join(text, "fake_roster.csv")):
        if c and c[0].isdigit():
            fake[int(c[0])] = (c[2], c[3], c[4])
    return real, fake


def prose_names(page, swapper):
    """{token: [real, fake]} for the page's name spans."""
    with open(page, encoding="utf-8") as f:
        html = f.read()
    html = html[html.index("<main>"):html.index("</main>")]
    out = {}
    for token, real in NAME_SPAN.findall(html):
        fake = swapper.swap([real], "", "")[0]
        if out.get(token, [real])[0] != real:
            raise SystemExit(f"guide: name token {token!r} is used for {out[token][0]!r} and {real!r}")
        out[token] = [real, fake]
    return out


def wrestler(rec, skill, used, crit_option):
    """The fields every wrestler entry shares (roster and edit records)."""
    slots = []
    for v in movedata.slot_values(rec):
        i = v & 0x7FF
        if i:
            used.add(i)
        slots.append(i * 4 + (2 if v & 0x2000 else 0) + (1 if v & 0x1000 else 0) if i else 0)
    return {
        "p": rec[0x44], "dv": rec[0], "h": rec[0x3E], "wt": rec[0x3F], "bp": rec[0x40],
        "b": None if rec[0x41] == 0xFF else [1900 + rec[0x41], rec[0x42], rec[0x43]],
        "sk": [crit_option[rec[r["o"]]] if r["o"] == 0x54 else rec[r["o"]] for r in skill],
        "pa": list(rec[OFFENCE_AT:OFFENCE_AT + 10]) + list(rec[DEFENCE_AT:DEFENCE_AT + 10]),
        "mv": slots, "ai": list(rec[LOGIC_AT:LOGIC_AT + LOGIC_SIZE]),
    }


CODE = re.compile(r"#(MS|MF|PS|PL)(\d\d)?")


def resolve_codes(obj, promos):
    """The story script's name codes in readable form: #MS / #MF (the player's names) become
    "Hero", #PSnn / #PLnn the promotion's short / full real name."""
    def sub(m):
        if m.group(1) in ("MS", "MF"):
            return "Hero" + (m.group(2) or "")
        name = promos[int(m.group(2))][1 if m.group(1) == "PS" else 0]
        return name[0] if isinstance(name, list) else name
    if isinstance(obj, str):
        return CODE.sub(sub, obj)
    if isinstance(obj, list):
        return [resolve_codes(x, promos) for x in obj]
    if isinstance(obj, dict):
        return {k: resolve_codes(v, promos) for k, v in obj.items()}
    return obj


def build(extracted, text, titles, page):
    def read(*parts):
        with open(os.path.join(extracted, *parts), "rb") as f:
            return f.read()
    exe = read("SLPS_020.65")
    ov004 = read("ovl", "004.bin")
    fpg010 = lzss.decompress(read("fpg", "010.bin"))
    fpg011 = lzss.decompress(read("fpg", "011.bin"))
    blocks = movedata.blocks(read("fpg", "274.bin"))
    en_exe = strtab.parse(os.path.join(text, "exe.txt"))
    en_ov4 = strtab.parse(os.path.join(text, "ov004.txt"))
    en_moves = {jp: e for _, jp, e in table.read(os.path.join(text, "moves.csv"))}
    move_names = movedata.move_names(fpg011, en_moves)

    births = []
    for k in range(BIRTHPLACE_COUNT):
        p = struct.unpack_from("<I", exe, BIRTHPLACES + 4 * k - EXE_BASE)[0]
        births.append(en_exe.get(p) or exe_string(exe, p))
    locked = exe[LOCKED - EXE_BASE:LOCKED - EXE_BASE + movedata.WRESTLERS]
    skill = skill_rows(ov004, en_ov4)
    crit_option = ov004[CRIT_OPTION - skilledit.OVERLAY_BASE:CRIT_OPTION - skilledit.OVERLAY_BASE + 6]
    crit_names = next(r["c"] for r in skill if r["o"] == 0x54)
    real, fake = roster_names(text)

    used = set()
    wrestlers = []
    for w in range(movedata.WRESTLERS):
        rec = fpg010[w * movedata.RECORD:(w + 1) * movedata.RECORD]
        r_short, r_full, r_nick = real[w]
        f_short, f_full, f_nick = fake.get(w, (r_short, r_full, ""))
        e = {"n": both(r_full, f_full), "s": both(r_short, f_short), "k": both(r_nick, f_nick or r_nick)}
        e.update(wrestler(rec, skill, used, crit_option))
        e["lk"] = locked[w]
        wrestlers.append(e)

    swapper = fakenames.Swapper(fakenames.load_rules(os.path.join(text, fakenames.RULES)))
    fk = lambda t: swapper.swap([t], "", "")[0] if t else t   # noqa: E731
    fpg013 = read("fpg", "013.bin")
    profiles = editdata.load_profiles(os.path.join(text, "edit_profiles.txt"))
    rows = {r[0]: r for r in editdata.load(os.path.join(text, "edit_wrestlers.csv"))}
    edit = []
    for k in range(EDIT_COUNT):
        rec = fpg013[EDIT_AT + k * EDIT_REC:EDIT_AT + (k + 1) * EDIT_REC]
        _, _, short, full, nick, fin = rows[f"013:{k}"]
        pf = profiles[k].replace("\\n", " ") if k < len(profiles) else ""
        e = {"n": both(full, fk(full)), "s": both(short, fk(short)), "k": both(nick, fk(nick)),
             "f": both(fin, fk(fin)), "pf": both(pf, fk(pf))}
        e.update(wrestler(rec, skill, used, crit_option))
        edit.append(e)


    sets = movedata.lists(ov004)
    cats, slot_cat = [], []
    for s, ids in enumerate(sets["normal"]):
        key = tuple(ids)
        k = next((c for c, cat in enumerate(cats) if cat["key"] == key), None)
        if k is None:
            k = len(cats)
            lv9 = [i for i in sets["level9"][s] if i and i not in ids]
            cats.append({"key": key, "t": CATEGORY_TITLES[k], "m": [i for i in ids if i], "h": lv9})
        slot_cat.append(k)
    for c in cats:
        used.update(c["m"] + c["h"])
        del c["key"]
    slots = [{"l": movedata.SLOTS[s][1], "b": movedata.SLOTS[s][2], "c": slot_cat[s]}
             for s in range(movedata.SLOT_COUNT)]

    moves = {}
    for i in sorted(used):
        b = blocks.get(i)
        st = None
        if b:
            # hp, spirit, neck, arm, waist, leg, breathing, blood; attack / defence rating
            # (main << 4 | sub); critical bits (status byte 19)
            st = list(b[2:10]) + [b[10], b[11], b[19]]
        moves[i] = {"n": move_names[i], "st": st}

    promos = promotions(text)
    first = lambda v: v[0] if isinstance(v, list) else v   # noqa: E731
    entries = []
    for prefix, group, people in (("w", None, wrestlers), ("e", "Edit Ranking", edit)):
        for k, e in enumerate(people):
            n, fake_n = (e["n"] if isinstance(e["n"], list) else [e["n"], e["n"]])
            entries.append({"id": f"{prefix}{k}", "name": n,
                            "group": group or first(promos[e["p"]][0]) if e["p"] < len(promos) else group,
                            "text": " ".join(x for x in (fake_n if fake_n != n else "", first(e["k"])) if x)})
    return {
        "names": prose_names(page, swapper),
        "entries": entries,
        "promos": promos,
        "births": births,
        "skill": skill,
        "crit": [crit_names[crit_option[v]] for v in range(6)],
        "ratings": [movedata.OFFENCE, movedata.DEFENCE],
        "w": wrestlers,
        "ew": edit,
        "logic": cpu_logic(ov004, en_ov4),
        "slots": slots,
        "cats": cats,
        "mv": moves,
        "story": resolve_codes(storymap.page_data(titles), promos),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output")
    paths.add(ap, "--text", paths.TEXT, "translated text folder")
    paths.add(ap, "--titles", os.path.join(paths.DOCS, "story_titles.csv"), "scene titles and summaries")
    paths.add(ap, "--page", os.path.join(paths.DOCS, "guide", "index.html"), "the guide")
    ap.add_argument("--check", action="store_true", help="exit 1 if the page is out of date")
    ap.add_argument("--json", metavar="FILE", help="also write the data, indented, to FILE")
    args = ap.parse_args(argv)
    data = build(args.extracted, args.text, args.titles, args.page)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    if pagedata.write(args.page, data, args.check) and args.check:
        print(f"{os.path.relpath(args.page)}: up to date")


if __name__ == "__main__":
    main()
