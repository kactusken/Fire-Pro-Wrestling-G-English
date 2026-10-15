#!/usr/bin/env python3
"""Extract / insert NUL-terminated UI strings in code modules (overlays, EXE).

Strings are found in a module's string area (C rodata: NUL-terminated,
4-byte aligned) together with their references:
  - pointer words: aligned 32-bit words equal to the string's address
  - code: lui reg, hi / (addiu|ori|lw...) x, lo(reg) pairs building it

Text file format (text/<module>.txt):
    @ 8005a800 len=12 refs=p1,c1
    JP 対戦形式
    EN Match Type

Entries can be added by hand for strings the scanner missed (e.g. a string
that directly follows a pointer table); their slot runs to the NUL.

On insert, a translated string that fits in its original slot (string + NUL
padding up to the next string) is written in place. Otherwise it goes into
a string pool appended to the module, and every reference is repointed.
A code reference is only repointed when its lui serves that string alone;
otherwise the string must fit in place.

Encoding of EN text: ASCII letters, digits and most punctuation stay single
bytes (the menu renderer maps 0x28-0x7E to the font's full-width glyphs).
!"#$%&' are not drawn by the menu renderer as ASCII, so they are written as
full-width SJIS, except in control codes ("#x12," pen moves, "%d" formats).
"\\n" in the text file is a line break (0x0A).
"""
import re
import struct

import codepatch

FULLWIDTH = {"!": "！", '"': "”", "#": "＃", "$": "＄", "%": "％", "&": "＆", "'": "’"}


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def is_japanese(raw):
    try:
        t = raw.decode("cp932")
    except UnicodeDecodeError:
        return False
    return any(ord(c) > 0x7F for c in t)


def find_strings(img, base, start, end):
    """Yield (addr, raw bytes, slot length) for strings in [start, end)."""
    i = start - base
    stop = end - base
    while i < stop:
        if img[i] == 0:
            i += 1
            continue
        if (base + i) % 4:
            # strings start 4-aligned; skip stray bytes
            i += 1
            continue
        j = img.index(b"\0", i)
        k = j + 1
        while k < stop and img[k] == 0 and (base + k) % 4:
            k += 1
        yield base + i, bytes(img[i:j]), k - i
        i = k


def scan_refs(img, base, targets):
    """Return {addr: [("p", word_addr) | ("c", lui_addr, lo_addr, exclusive)]}."""
    refs = {a: [] for a in targets}
    n = len(img) // 4
    words = struct.unpack_from(f"<{n}I", img, 0)
    for i, w in enumerate(words):
        if w in refs:
            refs[w].append(("p", base + 4 * i))
    for i, w in enumerate(words):
        if w >> 26 != 15:
            continue
        reg = (w >> 16) & 31
        hi = (w & 0xFFFF) << 16
        uses = []
        jump_at = None
        for j in range(i + 1, min(i + 24, n)):
            w2 = words[j]
            op = w2 >> 26
            rs, rt, rd = (w2 >> 21) & 31, (w2 >> 16) & 31, (w2 >> 11) & 31
            if rs == reg and op in (9, 13, 32, 33, 35, 36, 37, 40, 41, 43):
                lo = (w2 & 0xFFFF) if op == 13 else s16(w2 & 0xFFFF)
                uses.append((j, (hi + lo) & 0xFFFFFFFF))
            writes = (op in range(8, 16) or op in range(32, 38)) and rt == reg
            writes |= op == 0 and rd == reg and (w2 & 63) not in (8, 9)
            if writes:
                break
            if jump_at is not None and j > jump_at:
                break  # past the delay slot of a jump
            if op == 2 or (op == 0 and (w2 & 63) == 8):
                jump_at = j
        for j, a in uses:
            if a in refs:
                refs[a].append(("c", base + 4 * i, base + 4 * j, len(uses) == 1))
    return refs


CONTROL = re.compile(r"#x-?\d+,|%[-0-9.]*[a-z]")  # pen moves and printf formats stay as-is


def encode_en(text):
    text = text.replace("\\n", "\n")
    out = bytearray()
    i = 0
    while i < len(text):
        m = CONTROL.match(text, i)
        if m:
            out += m.group().encode("ascii")
            i = m.end()
            continue
        ch = text[i]
        i += 1
        if ch in FULLWIDTH:
            out += FULLWIDTH[ch].encode("cp932")
        elif ch == "\n":
            out.append(0x0A)
        else:
            out += ch.encode("cp932")
    return bytes(out)


def extract(img, base, start, end, path, module):
    targets = {a: (raw, ln) for a, raw, ln in find_strings(img, base, start, end) if is_japanese(raw)}
    refs = scan_refs(img, base, targets)
    lines = [f"# {module}: strings in {start:#x}..{end:#x}", ""]
    count = 0
    for a, (raw, ln) in sorted(targets.items()):
        r = refs[a]
        p = sum(1 for x in r if x[0] == "p")
        c = sum(1 for x in r if x[0] == "c")
        if not r:
            continue  # unreferenced: probably not a whole string
        jp = raw.decode("cp932").replace("\n", "\\n")
        lines += [f"@ {a:08x} len={ln} refs=p{p},c{c}", f"JP {jp}", ""]
        count += 1
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"{module}: {count} strings -> {path}")


def parse(path):
    entries = {}
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("@ "):
                cur = int(line.split()[1], 16)
            elif line.startswith("EN ") or line == "EN":
                if cur is not None:
                    entries[cur] = line[3:]
    return entries


def insert(img, base, start, end, path, pool_base=None, select=None, repack=False):
    """Patch img (bytearray) in place; returns pool bytes to append at pool_base.
    select: optional predicate on the string address (diagnostic builds).
    repack: no pool (EXE): every translated string whose references can all be
    repointed gives up its slot; neighbouring slots merge, and the strings are
    packed back into them (largest first, 4-byte aligned like the originals)."""
    entries = parse(path)
    if select:
        entries = {a: t for a, t in entries.items() if select(a)}
    slots = {a: ln for a, raw, ln in find_strings(img, base, start, end)}
    for a in entries:
        if a not in slots and start <= a < end and a % 4 == 0 and img[a - base]:
            # added by hand: a string the scanner merged into preceding data
            j = img.index(b"\0", a - base)
            k = j + 1
            while k < end - base and img[k] == 0 and (base + k) % 4:
                k += 1
            slots[a] = k - (a - base)
    keep = {}  # repack: untranslated ASCII strings reached only by pointers move too
    if repack:
        for a, raw, _ln in find_strings(img, base, start, end):
            if a not in entries and len(raw) > 1 and all(0x20 <= c < 0x7F for c in raw):
                keep[a] = raw
    refs = scan_refs(img, base, set(entries) | set(keep))
    for a in list(keep):
        if not refs[a] or any(x[0] != "p" for x in refs[a]):
            del keep[a]
    pool = bytearray()
    moved = inplace = 0
    problems = []
    spans = []          # free (addr, size) inside the area, used without a pool
    to_move = []
    for a, text in sorted(entries.items()):
        if a not in slots:
            problems.append(f"{a:08x}: not a string start")
            continue
        data = encode_en(text)
        r = refs[a]
        movable = r and not any(x[0] == "c" and not x[3] for x in r)
        if repack and movable:
            to_move.append((a, data, r))
            spans.append((a, slots[a]))
            continue
        if len(data) + 1 <= slots[a]:
            off = a - base
            img[off:off + slots[a]] = data + b"\0" * (slots[a] - len(data))
            spans.append((a + len(data) + 1, slots[a] - len(data) - 1))
            inplace += 1
            continue
        if not movable:
            problems.append(f"{a:08x}: needs {len(data) + 1} bytes, slot {slots[a]}, cannot relocate: {text}")
            continue
        to_move.append((a, data, r))
        spans.append((a, slots[a]))   # its old slot is free once repointed
    for a, raw in keep.items():
        to_move.append((a, raw, refs[a]))
        spans.append((a, slots[a]))
    # Without a pool, strings that don't fit go into the space other strings
    # left free in the same area (largest first, smallest span that fits).
    spans = _merge(spans)
    for a, *_ in to_move:              # clear the freed slots
        img[a - base:a - base + slots[a]] = bytes(slots[a])
    align = 4 if repack else 1
    for a, data, r in sorted(to_move, key=lambda m: -len(m[1])):
        if pool_base is not None:
            new = pool_base + len(pool)
            pool += data + b"\0"
            pool += b"\0" * ((-len(pool)) % 4)
        else:
            need = len(data) + 1
            fit = [i for i, (sa, sz) in enumerate(spans)
                   if sz - ((-sa) % align) >= need]
            if not fit:
                # its old slot may already hold another string: unrecoverable
                raise SystemExit(f"{a:08x}: needs {need} bytes, no free space left "
                                 f"in {start:#x}..{end:#x}: {data!r}; shorten some strings")
            i = min(fit, key=lambda i: spans[i][1])
            sa, size = spans[i]
            new = sa + (-sa) % align
            spans[i] = (new + need, sa + size - new - need)
            off = new - base
            img[off:off + len(data) + 1] = data + b"\0"
        codepatch.repoint(img, base, r, new)
        moved += 1
    return bytes(pool), inplace, moved, problems


def _merge(spans):
    out = []
    for a, n in sorted(spans):
        if out and out[-1][0] + out[-1][1] == a:
            out[-1] = (out[-1][0], out[-1][1] + n)
        elif n > 0:
            out.append((a, n))
    return out



if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                            epilog="A library used by build.py; it has no commands of its own.").parse_args()
    print(__doc__)
