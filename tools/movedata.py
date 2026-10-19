#!/usr/bin/env python3
"""Export the move data and the roster's move sets to CSV (docs/MOVES.md).

    python3 tools/movedata.py [--extracted PATH] [--text PATH] [--out-dir DIR]

Writes two tables:
  moves.csv           one row per move id with data (1,270): name, where Move Edit
                      offers it, who uses it, and every field of its status block
                      and attacker animation header
  wrestler_moves.csv  one row per roster wrestler (194): the move in each of the
                      57 slots, the finisher, the signature moves and the shouts

Reads the unpacked disc (tools/extract.py): FPG 274 (move data), FPG 010
(roster), FPG 011 (move names) and overlay 004 (Move Edit lists), and the
English names in text/.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lzss  # noqa: E402
import paths  # noqa: E402
import roster  # noqa: E402
import table  # noqa: E402

RECORD, WRESTLERS = 426, 194
SLOTS_AT, SLOT_COUNT = 0x74, 57        # roster record: 57 u16 move slots
NAMES, NAME_COUNT = 0x30A38, 1592      # FPG 011, unpacked
OVERLAY_BASE = 0x8005A718
# Move Edit list sets in overlay 004: 57 {u32 list pointer, u32 count} each
LIST_SETS = {"normal": 0x80078C60, "level9": 0x800791B8,
             "story0": 0x80078FF0, "story1": 0x80078E28}

# (column name, Move Edit label, buttons, variants loaded per slot)
SLOTS = [
    ("stand_a", "Stand", "A", 3), ("stand_b", "Stand", "B", 3),
    ("stand_c", "Stand", "C", 3), ("stand_ab", "Stand", "A+B", 3),
    ("run_a", "Run", "A", 2), ("run_b", "Run", "B", 2),
    ("counter_a", "Counter", "A", 2), ("counter_b", "Counter", "B", 2),
    ("diagonal_c", "Diagonal", "C", 1), ("dive_c", "Dive", "C", 2),
    ("plancha_c", "Plancha", "C", 2), ("apron_c", "Apron", "C", 2),
    ("post_a", "Post", "A", 2), ("post_b", "Post", "B", 2),
    ("post_c", "Post", "C", 2), ("post_ab", "Post", "A+B", 2),
] + [
    (f"grab_{b.lower()}{d}", "Grab", (D + " " if D else "") + b, 1)
    for b in "ABC" for d, D in (("", ""), ("_up", "Up"), ("_toward", "Toward"), ("_down", "Down"))
] + [
    ("grab_ab", "Grab", "A+B", 1),
    ("back_a", "Back", "A", 1), ("back_b", "Back", "B", 1), ("back_c", "Back", "C", 1),
    ("back_away_c", "Back", "Away C", 1), ("back_toward_c", "Back", "Toward C", 1),
    ("back_ab", "Back", "A+B", 1),
    ("back_rev_a", "B.Rev", "A", 1), ("back_rev_b", "B.Rev", "B", 1),
] + [
    (f"{k}_{b.lower()}", label, b, 1)
    for b in "BC"
    for k, label in (("up_head", "UpHead"), ("up_legs", "UpLegs"),
                     ("down_head", "DnHead"), ("down_legs", "DnLegs"))
] + [
    ("run_down_c", "Run Dn", "C", 2),
    ("corner_up_c", "Corner", "Up C", 1), ("corner_toward_c", "Corner", "Toward C", 1),
    ("corner_down_c", "Corner", "Down C", 1),
    ("taunt_l", "Taunt", "L", 1), ("taunt_r", "Taunt", "R", 1),
    ("front_duo", "Front Duo", "", 1), ("front_trio", "Front Trio", "", 1),
    ("back_duo", "Back Duo", "", 1), ("back_trio", "Back Trio", "", 1),
    ("corner_duo", "Corner Duo", "", 1), ("corner_trio", "Corner Trio", "", 1),
]
assert len(SLOTS) == SLOT_COUNT

# status byte 30 ("waza type2"): names from overlay 003's table at 0x8007AB08
COMMANDS = {
    0: "standing a b", 2: "standing c a+b", 4: "running a b", 6: "counter a b",
    8: "diagonal running c", 9: "running for outside c", 10: "outside from apron c",
    11: "inside from apron c", 12: "on corner a b c a+b", 16: "grapple a",
    20: "grapple b", 24: "grapple c a+b", 29: "back a", 30: "back b", 31: "back c a+b",
    35: "reverse back a", 36: "reverse back b", 37: "upside head b c",
    38: "upside leg b c", 39: "downside head b c", 40: "downside leg b c",
    45: "corner grapple c", 48: "performance l r", 50: "front two platoon",
    51: "front three platoon", 52: "back two platoon", 53: "back three platoon",
    54: "corner two platoon", 55: "corner three platoon",
}
# status byte 0 ("waza type1"). The editor has no names for it; these are named
# after the moves that use each value
CLASSES = [
    "strike", "grapple", "big strike", "lunging strike", "diagonal run",
    "dive outside (strike)", "dive outside (body)", "top rope on downed (strike)",
    "top rope on downed (body)", "top rope on standing (strike)",
    "top rope on standing (body)", "double team", "triple team", "run at downed",
    "combination (follow-up)", "combination (opener)",
]
# record +0x5F+n (offence) and +0x69+n (defence), Skill Edit order
OFFENCE = ["Strikes", "Kicks", "Throws", "Submission", "Chokes", "Power", "Agility",
           "Strength", "Off. Skill", "Brawling"]
DEFENCE = ["Strike Def.", "Kick Def.", "Throw Def.", "Sub. Def.", "Choke Def.",
           "Aerial Def.", "Slam Def.", "vs Lariat", "Def. Skill", "vs Brawling"]
# status byte 19, bit n: critical on a wrestler whose Critical (record +0x54) is n
CRITICALS = ["Finisher", "Strikes", "Suplex", "Submission", "Power", "Technique",
             "Give up", "Foul"]
BODY = [(8, "neck"), (4, "arm"), (2, "waist"), (1, "leg")]
# sound effects, overlay 003's table at 0x8007ABE8
SE = (["none", "(system) move", "(system) select", "(system) entry", "(system) cancel",
       "(system) error", "catch(sho)", "catch(chu)", "catch(dai)"]
      + [f"{k} lv{n}" for k in ("tackle", "head attack", "elbow.knee", "choppe", "punch",
                                "body attack", "high kick", "low kick", "jump kick",
                                "run attack", "down attack") for n in range(1, 5)]
      + [f"wind cutter {n}" for n in range(1, 8)]
      + [f"guard lv{n}" for n in range(1, 5)]
      + [f"mat(step) {n}" for n in range(1, 6)]
      + [f"{k} lv{n}" for k in ("mat(normal)", "mat(highspeed)", "mat(bom)", "mat(dai)",
                                "stretch", "sub misson") for n in range(1, 5)]
      + ["critical!", "poison fog", "big fire", "kakimushiri", "fang", "weapon(sho)",
         "weapon(dai)", "weekpoint(sho)", "weekpoint(dai)", "kama", "corner crush",
         "shoes noise(sho)", "shoes noise(chu)", "shoes noise(dai)", "rope bound(sho)",
         "rope bound(chu)", "rope bound(dai)", "touch", "gong(fight)", "gong(emergency)",
         "gong(match end)", "gong(match draw)", "grapple", "down mat(sho)",
         "down mat(chu)", "down mat(dai)"]
      + [f"drop down mat lv{n}" for n in range(1, 5)]
      + [f"self bom mat lv{n}" for n in range(1, 5)]
      + ["wrestler voice"]
      + [f"mat(out of ring) lv{n}" for n in range(1, 5)]
      + ["fall out ring(sho)", "fall out ring(chu)", "fall out ring(dai)",
         "fly drop out(sho)", "fly drop out(chu)", "fly drop out(dai)"])
assert len(SE) == 138


def blocks(fpg274):
    """-> {move id: block bytes} from FPG 274 (1,792 {u32 offset, u32 size})."""
    out = {}
    for i in range(1792):
        o, s = struct.unpack_from("<II", fpg274, 8 * i)
        if s:
            out[i] = fpg274[o:o + s]
    return out


def animations(block):
    """-> [(slot, header bytes, [frame bytes])] for the block's non-empty animations."""
    ends = block[0x20:0x30]
    out, prev = [], 0
    for k, end in enumerate(ends):
        if end > prev:
            at = 0x30 + 12 * prev
            n = block[at]
            out.append((k, block[at:at + 12],
                        [block[at + 12 * (f + 1):at + 12 * (f + 2)] for f in range(n)]))
        prev = max(prev, end)
    return out


def forms(block):
    """Number of 96-byte local forms after the animations."""
    return (len(block) - 0x30 - 12 * block[0x2F]) // 96


def move_names(fpg011, en):
    """-> [English name per move id]; en maps Japanese name -> English."""
    offs = struct.unpack_from(f"<{NAME_COUNT}H", fpg011, NAMES)
    out = []
    for o in offs:
        jp = fpg011[NAMES + o:fpg011.index(b"\0", NAMES + o)].decode("cp932")
        out.append(en.get(jp, jp))
    return out


def lists(ov004):
    """-> {set name: [[move ids] per slot]} from overlay 004."""
    def word(a):
        return struct.unpack_from("<I", ov004, a - OVERLAY_BASE)[0]
    out = {}
    for name, at in LIST_SETS.items():
        out[name] = []
        for s in range(SLOT_COUNT):
            ptr, n = word(at + 8 * s), word(at + 8 * s + 4)
            out[name].append(list(struct.unpack_from(f"<{n}H", ov004, ptr - OVERLAY_BASE)))
    return out


def slot_label(s):
    _, label, buttons, _ = SLOTS[s]
    return f"{label} {buttons}".strip()


def slot_values(rec):
    return struct.unpack_from(f"<{SLOT_COUNT}H", rec, SLOTS_AT)


def nibble_names(byte, names):
    return names[byte >> 4], names[byte & 15]


def move_header():
    return ["id", "name", "variant", "move_edit", "level9_only", "story_from",
            "roster_uses", "class", "command", "side",
            "hp", "spirit", "neck", "arm", "waist", "leg", "breathing", "blood",
            "attack_rating", "attack_sub_rating", "defence_rating", "defence_sub_rating",
            "uses", "self_hp", "self_spirit", "self_neck", "self_arm", "self_waist",
            "self_leg", "critical", "offset_x", "offset_y", "range_x", "range_y",
            "attack_dist", "fly_dist", "fly_time", "fly_power", "start_height",
            "end_height", "single_hits", "combo_hits",
            "animations", "frames", "duration", "local_forms", "hit_se", "se_level",
            "byte7", "reversal_type", "reversal_rate", "loop_point", "loop_back",
            "fall_frame", "limit_mode", "start_mode", "end_mode"]


def move_rows(data, names, sets, fpg010):
    # where Move Edit offers each id: first id of a run, plus its variants
    offered = {}
    for name, per_slot in sets.items():
        for s, ids in enumerate(per_slot):
            for first in (i for i in ids if i):     # 0 = "Unused"
                for v in range(SLOTS[s][3]):
                    offered.setdefault(first + v, {}).setdefault(name, set()).add(s)
    uses = {}
    for w in range(WRESTLERS):
        for s, value in enumerate(slot_values(fpg010[w * RECORD:(w + 1) * RECORD])):
            first = value & 0x7FF
            if first:
                for v in range(SLOTS[s][3]):
                    uses.setdefault(first + v, set()).add(w)
    for i, b in sorted(data.items()):
        where = offered.get(i, {})
        normal, lv9 = where.get("normal", set()), where.get("level9", set())
        story = ("start" if "story0" in where else "middle" if "story1" in where
                 else "end" if normal else "")
        variant = 1
        while i - variant in data and names[i - variant] == names[i] and variant < 3:
            variant += 1
        anims = animations(b)
        head, frames = anims[0][1], anims[0][2]
        yield ([i, names[i], variant,
                "; ".join(slot_label(s) for s in sorted(normal | lv9)),
                "yes" if lv9 and not normal else "",
                story,
                len(uses.get(i, ())),
                CLASSES[b[0]], COMMANDS.get(b[30], b[30]), b[1]]
               + list(b[2:10])
               + list(nibble_names(b[10], OFFENCE)) + list(nibble_names(b[11], DEFENCE))
               + ["+".join(n for bit, n in BODY if b[12] & bit)]
               + list(b[13:19])
               + ["+".join(n for k, n in enumerate(CRITICALS) if b[19] >> k & 1)]
               + list(struct.unpack_from("<bb", b, 20)) + list(b[22:30])
               + [b[31] & 15, b[31] >> 4,
                  len(anims), head[0], sum(f[6] for f in frames), forms(b),
                  SE[head[5]], head[6], head[7], head[8], head[9],
                  head[1], head[2], head[3], head[4], head[10], head[11]])


def wrestler_header():
    return (["id", "name", "short"] + [s[0] for s in SLOTS]
            + ["finisher", "signature", "voice1_moves", "voice2_moves"])


def picked(values, moves, test):
    """'Slot: Move; ...' for the filled slots whose value passes test."""
    return "; ".join(f"{slot_label(s)}: {moves[s]}"
                     for s, v in enumerate(values) if v & 0x7FF and test(v))


def wrestler_rows(fpg010, names, names_en):
    for w in range(WRESTLERS):
        values = slot_values(fpg010[w * RECORD:(w + 1) * RECORD])
        short, full = names_en.get(w, ("", ""))[:2]
        moves = [names[v & 0x7FF] if v & 0x7FF else "" for v in values]
        yield ([w, full, short] + moves
               + [picked(values, moves, lambda v: v & 0x2000),
                  picked(values, moves, lambda v: v & 0x1000),
                  picked(values, moves, lambda v: v >> 14 == 1),
                  picked(values, moves, lambda v: v >> 14 == 2)])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 2)[2])
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output")
    paths.add(ap, "--text", paths.TEXT, "translated text folder (English names)")
    paths.add(ap, "--out-dir", paths.DOCS, "folder for the two CSV files")
    args = ap.parse_args(argv)

    def read(*parts):
        return open(os.path.join(args.extracted, *parts), "rb").read()
    data = blocks(read("fpg", "274.bin"))
    fpg010 = lzss.decompress(read("fpg", "010.bin"))
    fpg011 = lzss.decompress(read("fpg", "011.bin"))
    en = {jp: e for _, jp, e in table.read(os.path.join(args.text, "moves.csv"))}
    names = move_names(fpg011, en)
    sets = lists(read("ovl", "004.bin"))
    names_en = roster.load(os.path.join(args.text, "wrestlers.csv"))
    os.makedirs(args.out_dir, exist_ok=True)
    for name, head, rows in (
            ("moves.csv", move_header(), move_rows(data, names, sets, fpg010)),
            ("wrestler_moves.csv", wrestler_header(), wrestler_rows(fpg010, names, names_en))):
        rows = [head] + list(rows)
        path = os.path.join(args.out_dir, name)
        table.write(path, rows)
        print(f"{path}: {len(rows) - 1} rows")


if __name__ == "__main__":
    main()
