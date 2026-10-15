#!/usr/bin/env python3
"""Story-mode flow analysis: scene bytecode -> branches, choices and stat changes.

Scene VM (overlay 002, dispatcher 0x8005dd94, jump table 0x8005a818, 57 opcodes).
Block header: 0x0004, text table T, then a label table (u16 offsets relative to
block+4; its first entry also gives its own length), then bytecode up to T.
Story state S = *(0x800541d0); field names come from the debug dump strings at
0x8005ab58/0x8005abd0:
    +0x16 scene   +0x18 next scene (-1 = scene + 1)   +0x1a STAR POINT
    +0x1c YASIN (ambition)  +0x1e BABY FACE  +0x20 NEKKETU (passion)
    +0x22 u8[7] promotion affinity (0 NJPW, 1 AJPW, 2 FMW, 3 UWF, 4 America; 5, 6 unused)
    +0x2a u16[10] style counters (DAGEKI KANSETSU NAGE POWER TEC FLY RAHU PAFORM SYUTO SHIME)
    +0x3e MATCH RESULT (non-zero = lost)  +0x3f route  +0x40 CHAMPION  +0x41 u8[8] flags
    +0x54 player's wrestler record (byte 0: 1 = heavyweight)
After a scene ends, the main loop (0x8005ff34) plays the scene's match from the
table at 0x800662a0 (14-byte records at 0x80064f28; -1 = none), then goes to
+0x18 or scene + 1. Opcode 0x2c ends Fighting Road (ending).

Usage: storyflow.py <out.json> [--extracted PATH] [--script PATH] [--text PATH]
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import script  # noqa: E402
import storybattles  # noqa: E402

EXTRACTED, SCRIPT, TEXT = paths.repo(paths.EXTRACTED), paths.repo(paths.SCRIPT), paths.repo(paths.TEXT)


def configure(extracted=None, script_dir=None, text=None):
    """Set the input folders (None keeps the current one)."""
    global EXTRACTED, SCRIPT, TEXT
    EXTRACTED, SCRIPT, TEXT = extracted or EXTRACTED, script_dir or SCRIPT, text or TEXT


def add_options(parser):
    paths.add(parser, "--extracted", paths.EXTRACTED, "tools/extract.py output")
    paths.add(parser, "--script", paths.SCRIPT, "story script folder")
    paths.add(parser, "--text", paths.TEXT, "text folder (wrestlers.tsv, exe.txt, exe_promotions.py)")

OV2_BASE = 0x8005A718
MATCH_TABLE, MATCH_RECS, REC = 0x800662A0, 0x80064F28, 14

SIZE = {0x00: 0, 0x01: 1, 0x02: 1, 0x03: 0, 0x04: 3, 0x05: 4, 0x06: 2, 0x07: 1, 0x08: 1,
        0x09: 1, 0x0a: 0, 0x0b: 0, 0x0c: 2, 0x0d: 2, 0x0e: 1, 0x0f: 1, 0x10: 1, 0x11: 1,
        0x12: 1, 0x13: 1, 0x14: 0, 0x15: 1, 0x16: 1, 0x17: 1, 0x18: 1, 0x19: 1, 0x1a: 0,
        0x1b: 0, 0x1c: 2, 0x1d: 2, 0x1e: 1, 0x1f: 0, 0x20: 0, 0x21: 1, 0x22: 1, 0x23: 2,
        0x24: 2, 0x25: 2, 0x26: 2, 0x27: 1, 0x28: 2, 0x29: 2, 0x2a: 3, 0x2b: 1, 0x2c: 0,
        0x2d: 2, 0x2e: 2, 0x2f: 2, 0x30: 3, 0x31: 3, 0x32: 3, 0x33: 3, 0x34: 3, 0x35: 1,
        0x36: 0, 0x37: 2, 0x38: 1}
STATS = ["Ambition", "Babyface", "Passion"]
PROMOS = ["NJPW", "AJPW", "FMW", "UWF", "America", "aff5 (unused)", "aff6 (unused)"]
STYLES = ["Striking", "Submissions", "Throws", "Power", "Technique", "Flying", "Rough",
          "Performance", "Shoot", "Chokes"]
# opcode 0x21 (route): the player's top style adds +3 / +1 to these affinities
ROUTE_P3 = [4, 3, 1, 0, 1, 2, 2, 4, 3, 0]
ROUTE_P1 = [2, 0, 3, 1, 4, 1, 4, 2, 0, 3]
ROUTE_RESULTS = ["NJPW offer", "AJPW offer", "FMW offer", "UWF offer", "America offer",
                 "NJPW offer (with Liger; unreachable)", "Michinoku Pro offer"]
# FPG 127 records 8-11: Sakagami's four versions
SPECIAL = {0xFFF0: "Koichi Sakagami (Classmate)", 0xFFF1: "Koichi Sakagami (Heavyweight)",
           0xFFF2: "Koichi Sakagami (U-Style)", 0xFFF3: "Koichi Sakagami (Junior)"}
# rules presets (6 bytes; [0] venue, [5] referee), see tools/storybattles.py
PRESETS, PRESET_SIZE = 0x80064DCC, 6


def s8(x):
    return x - 256 if x > 127 else x


def disasm(blk):
    tab = script.be16(blk, 2)
    first = script.be16(blk, 4)
    labels = [4 + script.be16(blk, 4 + 2 * i) for i in range(first // 2)]
    pc, ins = 4 + first, {}
    order = []
    while pc < tab:
        op = blk[pc]
        n = SIZE[op]
        ins[pc] = (op, list(blk[pc + 1:pc + 1 + n]), pc + 1 + n)
        order.append(pc)
        pc += 1 + n
    return labels, ins, order


def load_messages(s):
    out, cur = {}, None
    path = os.path.join(SCRIPT, f"{s:03d}.txt")
    jp = {}
    for ln in open(path, encoding="utf-8"):
        if ln.startswith("@ "):
            cur = int(ln[2:])
            out[cur], jp[cur] = [], []
        elif ln.startswith("EN "):
            out[cur].append(ln[3:].rstrip())
        elif ln.startswith("JP "):
            jp[cur].append(ln[3:].rstrip())
    return out, jp


def wrestler_names():
    names = {}
    for ln in open(os.path.join(TEXT, "wrestlers.tsv"), encoding="utf-8"):
        if ln.startswith(("#", "idx")):
            continue
        f = ln.rstrip("\n").split("\t")
        names[int(f[0])] = f[7]
    return names


def matches():
    ov = open(os.path.join(EXTRACTED, "ovl", "002.bin"), "rb").read()
    names = wrestler_names()
    rings = storybattles.ring_names(EXTRACTED, TEXT)

    def name(x):
        return SPECIAL.get(x) or names.get(x & 0xFF, f"wrestler {x & 0xFF}")

    out = {}
    for s in range(522):
        m = struct.unpack_from("<h", ov, MATCH_TABLE - OV2_BASE + 2 * s)[0]
        if m < 0:
            continue
        r = ov[MATCH_RECS - OV2_BASE + REC * m:][:REC]
        opp1, opp2, partner = struct.unpack_from("<HHH", r, 4)
        p = ov[PRESETS - OV2_BASE + PRESET_SIZE * r[0]:][:PRESET_SIZE]
        place = storybattles.decode(r, p, rings)
        place.pop("flags")
        if r[2] == 2:
            out[s] = {"id": m, "opponents": [name(opp1)], "partner": None, **place}
        else:
            out[s] = {"id": m, "opponents": [name(opp1), name(opp2)], "partner": name(partner),
                      **place}
    return out


def fmt_effect(op, a):
    if op == 0x24:
        return {"kind": "stat", "stat": STATS[a[0]], "delta": s8(a[1])}
    if op == 0x23:
        return {"kind": "affinity", "stat": PROMOS[a[0]], "delta": s8(a[1])}
    if op == 0x2b:
        return {"kind": "stat", "stat": "Star Points", "delta": s8(a[0])}
    if op == 0x27:
        return {"kind": "set", "stat": "Champion", "value": a[0]}
    if op == 0x2d:
        return {"kind": "set", "stat": f"Flag {'ABCDEFGH'[a[0] & 7]}", "value": a[1]}
    if op == 0x2e:
        return {"kind": "stat", "stat": f"Flag {'ABCDEFGH'[a[0] & 7]}", "delta": a[1]}
    if op == 0x2f:
        return {"kind": "stat", "stat": f"Flag {'ABCDEFGH'[a[0] & 7]}", "delta": -a[1]}
    return None


EFFECT_OPS = {0x23, 0x24, 0x27, 0x2b, 0x2d, 0x2e, 0x2f}


def flag(i):
    return f"Flag {'ABCDEFGH'[i & 7]}"


def branches(op, a, nxt, labels, route):
    """Successors of one instruction: list of (pc or exit, condition or None)."""
    L = labels
    if op == 0x17:
        return [(L[a[0]], None)]
    if op == 0x1e:
        return [(L[a[0]], "Lost the last match"), (nxt, "Won the last match")]
    if op == 0x28:
        return [(L[a[1]], f"Champion = {a[0]}"), (nxt, f"Champion ≠ {a[0]}")]
    if op == 0x29:
        return [(L[a[1]], f"Star Points ≥ {s8(a[0])}"), (nxt, f"Star Points < {s8(a[0])}")]
    if op == 0x2a:
        st = STATS[a[0]]
        return [(L[a[2]], f"{st} ≥ {s8(a[1])}"), (nxt, f"{st} < {s8(a[1])}")]
    if op in (0x30, 0x31, 0x32, 0x33):
        rel, neg = {0x30: ("=", "≠"), 0x31: ("≠", "="), 0x32: ("≥", "<"), 0x33: ("<", "≥")}[op]
        f = flag(a[0])
        return [(L[a[2]], f"{f} {rel} {s8(a[1])}"), (nxt, f"{f} {neg} {s8(a[1])}")]
    if op == 0x37:
        st = STYLES[a[0]]
        return [(L[a[1]], f"Most-used style: {st}"), (nxt, f"Most-used style is not {st}")]
    if op == 0x25:  # unused debug prompt
        return [(L[a[0]], "Debug: 0"), (L[a[1]], "Debug: 1")]
    if op == 0x21:
        return [(L[a[0] + k], ("route", k)) for k in range(7) if k != 5]
    if op == 0x22:
        return [(L[a[0] + route], None)]
    return [(nxt, None)]


def analyse(s, blk, msgs, match_of):
    labels, ins, order = disasm(blk)
    en, jp = msgs

    def text(i):
        return " ".join(en.get(i) or jp.get(i) or ["?"])

    def options(i):
        lines = en.get(i) or jp.get(i) or []
        opts = [ln.lstrip("・").strip() for ln in lines if ln.startswith("・")]
        return opts

    # Choices: option effects up to the point where the options merge again.
    choices = []
    choice_effect_pcs = set()
    for pc in order:
        op, a, nxt = ins[pc]
        if op not in (4, 5):
            continue
        targets = [labels[x] for x in a[1:]]
        walks = []
        for t in targets:
            seen, p = [], t
            while p in ins and p not in seen:
                seen.append(p)
                o, aa, n = ins[p]
                if o == 0x17:
                    p = labels[aa[0]]
                    continue
                if o in (0, 0x1c, 0x2c) or len(branches(o, aa, n, labels, 0)) > 1 or o in (4, 5):
                    break
                p = n
            walks.append(seen)
        merge = set()
        for i, w in enumerate(walks):
            for j, w2 in enumerate(walks):
                if i != j:
                    merge |= set(w) & set(w2)
        opts = options(a[0])
        out = []
        for i, w in enumerate(walks):
            eff = []
            for p in w:
                if p in merge:
                    break
                o, aa, _ = ins[p]
                if o in EFFECT_OPS:
                    eff.append(fmt_effect(o, aa))
                    choice_effect_pcs.add(p)
            out.append({"text": opts[i] if i < len(opts) else f"Option {i + 1}", "effects": eff})
        prompt = [ln for ln in (en.get(a[0]) or []) if not ln.startswith("・")]
        choices.append({"pc": pc, "prompt": " ".join(prompt), "options": out,
                        "context": context_before(order, ins, pc, text)})

    # Paths: decisive conditions only, plus route value and pending next scene.
    def reach_exits(start):
        memo = {}

        def go(p, stack):
            if p in memo:
                return memo[p]
            if p in stack or p not in ins:
                return frozenset()
            stack.add(p)
            o, aa, n = ins[p]
            if o == 0:
                r = frozenset([("end",)])
            elif o == 0x1c:
                r = frozenset([("scene", aa[0] + 100 * aa[1])])
            elif o == 0x2c:
                r = frozenset([("ending",)])
            elif o == 0x22:
                r = frozenset().union(*[go(labels[aa[0] + k], stack) for k in range(7)])
            else:
                r = frozenset().union(*[go(t, stack) for t, _ in branches(o, aa, n, labels, 0)])
                if o == 0x26:
                    r = frozenset(("end", aa[0] + 100 * aa[1]) if x == ("end",) else x for x in r)
            stack.discard(p)
            memo[p] = r
            return r
        return go(start, set())

    exits = {}
    effects = []

    def walk(p, conds, full, route, nxt_scene, depth, seen):
        if depth > 4000 or (p, route) in seen:
            return
        seen = seen | {(p, route)}
        if p not in ins:
            return
        o, aa, n = ins[p]
        if o == 0:
            to = nxt_scene if nxt_scene is not None else s + 1
            add_exit(("next", to), conds)
            return
        if o == 0x1c:
            add_exit(("jump", aa[0] + 100 * aa[1]), conds)
            return
        if o == 0x2c:
            add_exit(("ending", None), conds)
            return
        if o == 0x26:
            nxt_scene = aa[0] + 100 * aa[1]
        if o in EFFECT_OPS and p not in choice_effect_pcs:
            effects.append((p, tuple(full), fmt_effect(o, aa)))
        if o in (4, 5):
            succ = [(labels[x], ("choice", p, i)) for i, x in enumerate(aa[1:])]
        else:
            succ = branches(o, aa, n, labels, route)
        if len(succ) > 1:
            sets = [reach_exits_cached(t) for t, _ in succ]
            decisive = len(set(sets)) > 1 or o == 0x21
        else:
            decisive = False
        for t, c in succ:
            r = route
            if isinstance(c, tuple) and c[0] == "route":
                r = c[1]
            nc = conds + [c] if (decisive and c is not None) else conds
            nf = full + [c] if (len(succ) > 1 and c is not None) else full
            walk(t, nc, nf, r, nxt_scene, depth + 1, seen)

    cache = {}

    def reach_exits_cached(t):
        if t not in cache:
            cache[t] = reach_exits(t)
        return cache[t]

    def add_exit(key, conds):
        exits.setdefault(key, set()).add(tuple(conds))

    walk(4 + script.be16(blk, 4), [], [], 0, None, 0, frozenset())

    choice_by_pc = {c["pc"]: c for c in choices}

    def cond_text(c):
        if isinstance(c, str):
            return c
        if c[0] == "choice":
            ch = choice_by_pc[c[1]]
            opt = ch["options"][c[2]]["text"] if c[2] < len(ch["options"]) else f"option {c[2] + 1}"
            return f"Choose “{opt}”"
        if c[0] == "route":
            return ROUTE_RESULTS[c[1]]
        return str(c)

    exit_list = []
    for (kind, to), condsets in sorted(exits.items(), key=lambda kv: (str(kv[0][1]), kv[0][0])):
        alts = sorted({tuple(simplify([cond_text(c) for c in cs])) for cs in condsets})
        if any(len(a) == 0 for a in alts):
            alts = [()]
        exit_list.append({"kind": kind, "to": to, "when": [list(a) for a in alts]})

    eff_out = []
    seen_eff = {}
    for p, conds, e in effects:
        key = p
        seen_eff.setdefault(key, (e, []))[1].append(conds)
    for p, (e, condsets) in sorted(seen_eff.items()):
        common = set(condsets[0])
        for cs in condsets[1:]:
            common &= set(cs)
        guard = simplify([cond_text(c) for c in condsets[0] if c in common])
        e = dict(e)
        e["when"] = guard
        e["context"] = context_before(order, ins, p, text)
        eff_out.append(e)

    has_route = any(ins[p][0] == 0x21 for p in order)
    ending = any(ins[p][0] == 0x2c for p in order)
    first = next((text(ins[p][1][0]) for p in order if ins[p][0] in (2, 0x35)), "")
    nmsg = sum(1 for p in order if ins[p][0] in (2, 0x35))
    for c in choices:
        del c["pc"]
    return {"id": s, "first": first, "messages": nmsg, "match": match_of.get(s),
            "choices": choices, "effects": eff_out, "exits": exit_list,
            "route_decision": has_route, "ending": ending,
            "flow": flow(s, labels, ins, en, jp)}


def promo_names():
    ns = {}
    exec(open(os.path.join(TEXT, "exe_promotions.py"), encoding="utf-8").read(), ns)
    return ns["NAMES"]


PROMO_NAMES = None


def readable(line):
    """Story text for display: player and promotion codes spelled out."""
    global PROMO_NAMES
    if PROMO_NAMES is None:
        PROMO_NAMES = promo_names()
    line = line.replace("#MS", "[Player]").replace("#MF", "[Player]")
    line = re.sub(r"#PL(\d\d)", lambda m: PROMO_NAMES[int(m.group(1))][0], line)
    return re.sub(r"#PS(\d\d)", lambda m: PROMO_NAMES[int(m.group(1))][1], line)


def flow(s, labels, ins, en, jp):
    """Basic-block graph of one scene: dialogue, effects, choices and exits.

    Blocks: {"lines": [[line, ...] per message], "effects": [...], "out": [edge]};
    edge: {"to": block} or {"exit": "next"|"jump"|"ending", "scene": n}, plus
    "label" (option text or condition) and "kind" ("choice", "cond" or None).
    """
    def lines(i):
        return [readable(x) for x in (en.get(i) or jp.get(i) or [])]

    def succ(pc):
        op, a, n = ins[pc]
        if op in (4, 5):
            opts = [x.lstrip("・").strip() for x in lines(a[0]) if x.startswith("・")]
            return [(labels[x], opts[i] if i < len(opts) else f"Option {i + 1}", "choice")
                    for i, x in enumerate(a[1:])]
        if op == 0:
            return [(("next",), None, None)]
        if op == 0x1c:
            return [(("jump", a[0] + 100 * a[1]), None, None)]
        if op == 0x2c:
            return [(("ending",), None, None)]
        if op in (0x21, 0x22):
            return [(labels[a[0] + k], ROUTE_RESULTS[k], "cond") for k in range(7) if k != 5]
        out = []
        for t, c in branches(op, a, n, labels, 0):
            out.append((t, c, "cond" if c else None))
        return out

    entry = min(ins)
    # reachable instructions and predecessor counts
    preds, seen, todo = {}, set(), [entry]
    while todo:
        p = todo.pop()
        if p in seen or p not in ins:
            continue
        seen.add(p)
        for t, _, _ in succ(p):
            if isinstance(t, int):
                preds.setdefault(t, []).append(p)
                todo.append(t)
    leaders = {entry}
    for p in seen:
        ss = succ(p)
        if len(ss) > 1 or ins[p][0] in (4, 5, 0x21, 0x22):
            leaders |= {t for t, _, _ in ss if isinstance(t, int)}
    leaders |= {p for p in seen if len(preds.get(p, [])) > 1}
    order = sorted(leaders)
    bid = {p: i for i, p in enumerate(order)}
    blocks = []
    for lead in order:
        b = {"lines": [], "effects": [], "out": [], "setnext": None, "end": False}
        p = lead
        while True:
            op, a, n = ins[p]
            if op in (2, 0x35):
                b["lines"].append(lines(a[0]))
            elif op in (4, 5):
                prompt = [x for x in lines(a[0]) if not x.startswith("・")]
                if prompt:
                    b["lines"].append(prompt)
            elif op in EFFECT_OPS:
                e = fmt_effect(op, a)
                if "unused" not in e["stat"]:
                    b["effects"].append(e)
            elif op == 0x26:
                b["setnext"] = a[0] + 100 * a[1]
            ss = succ(p)
            if len(ss) == 1 and isinstance(ss[0][0], int) and ss[0][0] not in leaders \
                    and op not in (4, 5, 0x21, 0x22):
                p = ss[0][0]
                continue
            for t, label, kind in ss:
                e = {"label": label, "kind": kind}
                if isinstance(t, int):
                    e["to"] = bid[t]
                elif t[0] == "next":
                    b["end"] = True
                    e["exit"] = "next"
                elif t[0] == "jump":
                    e["exit"], e["scene"] = "jump", t[1]
                else:
                    e["exit"] = "ending"
                b["out"].append(e)
            break
        blocks.append(b)
    # pending "next scene" values reaching each block
    pend = [set() for _ in blocks]
    pend[0] = {None}
    changed = True
    while changed:
        changed = False
        for i, b in enumerate(blocks):
            outv = {b["setnext"]} if b["setnext"] is not None else pend[i]
            for e in b["out"]:
                if "to" in e and not outv <= pend[e["to"]]:
                    pend[e["to"]] |= outv
                    changed = True
    for i, b in enumerate(blocks):
        vals = {b["setnext"]} if b["setnext"] is not None else pend[i]
        new_out = []
        for e in b["out"]:
            if e.get("exit") == "next":
                for v in sorted(vals, key=lambda x: -1 if x is None else x):
                    new_out.append(dict(e, scene=s + 1 if v is None else v,
                                        ambiguous=len(vals) > 1))
            else:
                new_out.append(e)
        b["out"] = new_out
    # bypass empty pass-through blocks
    def target(i, depth=0):
        b = blocks[i]
        if depth < 50 and i != 0 and not b["lines"] and not b["effects"] and len(b["out"]) == 1 \
                and "to" in b["out"][0] and not b["out"][0]["label"]:
            return target(b["out"][0]["to"], depth + 1)
        return i
    for b in blocks:
        for e in b["out"]:
            if "to" in e:
                e["to"] = target(e["to"])
    keep, todo = set(), [0]
    while todo:
        i = todo.pop()
        if i in keep:
            continue
        keep.add(i)
        todo += [e["to"] for e in blocks[i]["out"] if "to" in e]
    remap = {i: k for k, i in enumerate(sorted(keep))}
    out = []
    for i in sorted(keep):
        b = blocks[i]
        for e in b["out"]:
            if "to" in e:
                e["to"] = remap[e["to"]]
            if e["label"] is None:
                del e["label"]
            if e["kind"] is None:
                del e["kind"]
        out.append({"lines": b["lines"], "effects": b["effects"], "out": b["out"]})
    return out


def simplify(conds):
    """Drop negative style tests implied by a later positive one; merge the rest."""
    neg = "Most-used style is not "
    if any(c.startswith("Most-used style: ") for c in conds):
        return [c for c in conds if not c.startswith(neg)]
    nots = [c[len(neg):] for c in conds if c.startswith(neg)]
    out = [c for c in conds if not c.startswith(neg)]
    if nots:
        out.insert(0, neg + " or ".join(nots))
    return out


def context_before(order, ins, pc, text):
    i = order.index(pc)
    for p in reversed(order[:i]):
        if ins[p][0] in (2, 0x35):
            return text(ins[p][1][0])
    return ""


def build():
    idx = open(os.path.join(EXTRACTED, "fpg", "130.bin"), "rb").read()
    data = open(os.path.join(EXTRACTED, "fpg", "131.bin"), "rb").read()
    match_of = matches()
    scenes = [analyse(s, blk, load_messages(s), match_of) for s, blk in script.scenes(idx, data)]
    meta = {"stats": STATS, "promotions": PROMOS[:5], "styles": STYLES,
            "route_style_bonus": [{"style": STYLES[i], "plus3": PROMOS[ROUTE_P3[i]],
                                   "plus1": PROMOS[ROUTE_P1[i]]} for i in range(10)]}
    return {"meta": meta, "scenes": scenes}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Story-mode flow analysis to JSON.")
    ap.add_argument("out", help="output .json")
    add_options(ap)
    args = ap.parse_args(argv)
    configure(args.extracted, args.script, args.text)
    out_path = args.out
    d = build()
    json.dump(d, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(d['scenes'])} scenes -> {out_path}")


if __name__ == "__main__":
    main()
