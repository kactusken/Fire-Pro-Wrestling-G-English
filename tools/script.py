#!/usr/bin/env python3
"""Story script tool for Fire Pro Wrestling G (FPG.BIN entries 130/131).

131.bin holds 522 scene blocks, each starting on a 2048-byte sector.
130.bin is the scene index: u16 LE start sector per scene, then the end sector.

Scene block layout (all big-endian u16):
    0x00  0x0004
    0x02  text table offset (T)
    ...   script bytecode
    T     table of message offsets, relative to T (count = first entry / 2)
    ...   NUL-terminated Shift-JIS messages, lines separated by CR LF

Inline codes (kept verbatim): #MS #MF #WSnnn #WFnnn #WLnnn #WNnnn #PSnn #PLnn

Text file format (one per scene, script/NNN.txt):
    @ 012
    JP 「俺は・・・勝ったのか・・・
    JP 　手に入れたのか・・・・
    EN I... won...?
    EN Did I really get it...?

Each message has JP lines (reference, ignored on insert) and EN lines.
A message with no EN lines is inserted unchanged.

Usage:
  script.py extract <130.bin> <131.bin> <outdir>
  script.py insert  <130.bin> <131.bin> <indir> <new130.bin> <new131.bin>
"""
import os
import re
import struct

import codepatch

SECTOR = 0x800
ENC = "cp932"


def be16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def load_index(idx_data):
    vals = [struct.unpack_from("<H", idx_data, i)[0] for i in range(0, len(idx_data), 2)]
    end = len(vals) - 1
    while vals[end] == 0:
        end -= 1
    return vals[:end + 1]


def split_scene(blk):
    """Return (code bytes before text table, list of message bytes)."""
    assert be16(blk, 0) == 4
    tab = be16(blk, 2)
    count = be16(blk, tab) // 2
    msgs = []
    for i in range(count):
        o = tab + be16(blk, tab + 2 * i)
        msgs.append(blk[o:blk.index(b"\0", o)])
    return blk[:tab], msgs


def build_scene(code, msgs):
    table = bytearray()
    body = bytearray()
    base = 2 * len(msgs)
    for m in msgs:
        table += struct.pack(">H", base + len(body))
        body += m + b"\0"
    blk = bytes(code) + bytes(table) + bytes(body)
    assert len(blk) < 0x10000, "scene exceeds 16-bit offsets"
    return blk


def scenes(idx_data, script_data):
    idx = load_index(idx_data)
    for s in range(len(idx) - 1):
        yield s, script_data[idx[s] * SECTOR:idx[s + 1] * SECTOR]


def extract(idx_path, script_path, outdir):
    idx_data = open(idx_path, "rb").read()
    script_data = open(script_path, "rb").read()
    os.makedirs(outdir, exist_ok=True)
    total = 0
    for s, blk in scenes(idx_data, script_data):
        _, msgs = split_scene(blk)
        lines = []
        for i, m in enumerate(msgs):
            lines.append(f"@ {i:03d}")
            for ln in m.decode(ENC).split("\r\n"):
                lines.append(f"JP {ln}")
            lines.append("")
        with open(os.path.join(outdir, f"{s:03d}.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
        total += len(msgs)
    print(f"extracted {total} messages")


def parse_text(path):
    """Return {msg_index: [EN lines]} for messages that have EN lines."""
    out = {}
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("@ "):
                cur = int(line[2:])
            elif line.startswith("EN") and cur is not None:
                out.setdefault(cur, []).append(line[3:])
    return out


def encode_message(lines):
    text = "\r\n".join(lines)
    return text.encode(ENC)


LINE_LIMIT = 440       # px; the story box shows ~455 px
SLOT_LIMIT = 80        # glyph slots in the story window
CODE_WIDTH = 110       # px allowance for an expanded #MS/#WSnnn/... name
CODE_RE = re.compile(r"#(?:MS|MF|W[SFLN]\d{3}|P[SL]\d{2})")


def check_message(lines, metrics, where):
    """Warn about lines wider than the box or messages needing too many slots."""
    import vwf_patch
    slots = 0
    for ln in lines:
        codes = len(CODE_RE.findall(ln))
        plain = CODE_RE.sub("", ln)
        wide = sum(1 for ch in plain if ord(ch) > 0x7F)
        width = vwf_patch.line_width(plain, metrics) + codes * CODE_WIDTH + wide * 20
        if width > LINE_LIMIT:
            print(f"warning: {where}: line is {width}px (limit {LINE_LIMIT}): {ln}")
        slots += -(-width // 20) + 1
    if slots > SLOT_LIMIT - 2:
        print(f"warning: {where}: needs about {slots} glyph slots (limit {SLOT_LIMIT})")
    # Lines with name codes: lay them out with the real expansions, both the default
    # hero name and the longest a player can enter (tools/storycheck.py).
    if any(CODE_RE.search(ln) for ln in lines):
        import storycheck
        for names in (storycheck.DEFAULT_NAMES, storycheck.LONG_NAMES):
            for problem in storycheck.check(lines, metrics, names)[0]:
                if "past the box" in problem or "slots" in problem:
                    print(f"warning: {where}: {problem}")


MAX_SCENE = 4 * SECTOR     # largest original scene block


def insert(idx_path, script_path, indir, out_idx, out_script, metrics=None):
    idx_data = open(idx_path, "rb").read()
    script_data = open(script_path, "rb").read()
    new_script = bytearray()
    new_idx = []
    changed = 0
    for s, blk in scenes(idx_data, script_data):
        code, msgs = split_scene(blk)
        path = os.path.join(indir, f"{s:03d}.txt")
        if os.path.exists(path):
            for i, lines in parse_text(path).items():
                if i >= len(msgs):
                    raise SystemExit(f"{path}: message {i} out of range")
                msgs[i] = encode_message(lines)
                if metrics:
                    check_message(lines, metrics, f"script/{s:03d}.txt @ {i:03d}")
                changed += 1
        new_idx.append(len(new_script) // SECTOR)
        data = build_scene(code, msgs)
        # Scenes are packed to whole sectors. The game reads a scene as the
        # sectors between its index entry and the next; no scene may need more
        # sectors than the largest original one (4), the size of its buffer.
        size = len(data) + (-len(data)) % SECTOR
        if size > MAX_SCENE:
            raise SystemExit(f"scene {s:03d} needs {size} bytes (max {MAX_SCENE})")
        new_script += data + b"\0" * (size - len(data))
    new_idx.append(len(new_script) // SECTOR)

    if len(new_script) > len(script_data):
        raise SystemExit(f"script grew to {len(new_script)} bytes (limit {len(script_data)})")
    new_script += b"\0" * (len(script_data) - len(new_script))

    idx_out = bytearray(len(idx_data))
    for i, v in enumerate(new_idx):
        struct.pack_into("<H", idx_out, i * 2, v)
    open(out_idx, "wb").write(idx_out)
    open(out_script, "wb").write(new_script)
    print(f"inserted {changed} messages, script uses {new_idx[-1]} sectors")


# Overlay 002 also carries one scene block of its own (save prompt, pre-match
# choice). It is rebuilt from text/ov002_scene.txt, appended to the overlay
# and the two lui/addiu pairs that load its address are repointed.
OV002_SCENE = 0x80064B98
OV002_SCENE_REFS = [(0x8005DB74, 0x8005DB78), (0x8005DBC0, 0x8005DBC4)]


def patch_ov002_scene(ov, base, text_path, metrics=None):
    """Append the translated built-in scene to overlay 002 (bytearray) and repoint it."""
    at = OV002_SCENE - base
    tab = be16(ov, at + 2)
    count = be16(ov, at + tab) // 2
    end = at + tab + be16(ov, at + tab + 2 * (count - 1))
    end = ov.index(b"\0", end) + 1
    code, msgs = split_scene(bytes(ov[at:end]))
    for i, lines in parse_text(text_path).items():
        msgs[i] = encode_message(lines)
        if metrics:
            check_message(lines, metrics, f"{os.path.basename(text_path)} @ {i:03d}")
    data = build_scene(code, msgs)
    ov += bytes((-len(ov)) % 4)
    new = base + len(ov)
    ov += data
    for lui, lo in OV002_SCENE_REFS:
        codepatch.set_pair(ov, base, lui, lo, new, expect=OV002_SCENE)
    return new


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Extract or insert the story script (FPG 130/131).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="scene blocks -> one NNN.txt per scene")
    p.add_argument("idx", metavar="130.bin")
    p.add_argument("data", metavar="131.bin")
    p.add_argument("outdir")
    p = sub.add_parser("insert", help="NNN.txt files -> new 130/131 (build.py does this itself)")
    p.add_argument("idx", metavar="130.bin")
    p.add_argument("data", metavar="131.bin")
    p.add_argument("indir")
    p.add_argument("out_idx", metavar="new130.bin")
    p.add_argument("out_data", metavar="new131.bin")
    args = ap.parse_args()
    if args.cmd == "extract":
        extract(args.idx, args.data, args.outdir)
    else:
        insert(args.idx, args.data, args.indir, args.out_idx, args.out_data)
