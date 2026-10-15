#!/usr/bin/env python3
"""Find every image in FPG.BIN and lay them out on labelled contact sheets.

    python3 tools/contact.py [--extracted PATH] [--review PATH]      (needs Pillow)
        -> review/all-images/<id>.png + index.csv, review/contact-sheets/sheet_NNN.png

Ids are <entry>_<n>: the n-th image found in that FPG entry (or <entry>_<n>p<k> for
the k-th 256-px texture page of a VRAM sheet). They are stable as long as the
original disc is the same, so they can be used to point at an image later;
index.csv says where each one lives.

What is found:
  * TIMs stored plainly anywhere in an entry, in the decompressed entry, or as
    LZSS-compressed TIMs starting part-way into an entry
  * BS (MDEC) pictures (story backgrounds)
  * story portraits (143-247): a 16x10 map of 32x32 8bpp tiles + palette
  * VRAM sheets (16bpp TIMs holding 4bpp textures): 277 split into texture pages
    (grey palette), victory screens 279-285 split into photo and caption strip
Images drawn with a palette from somewhere else are shown in grey. Not shown:
sound (VAB/SEQ), text, tables, and data in formats not decoded here (the big
blocks 099/126, 252-267, 270-274, 290 - probably wrestler sprites and animation). Exact
duplicates are shown once (index.csv lists them).
"""
import csv
import hashlib
import os
import struct
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("needs Pillow: python3 -m pip install -r requirements.txt") from None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bs  # noqa: E402
import paths  # noqa: E402
from lzss import decompress  # noqa: E402
from tim import Tim, find_tims  # noqa: E402

FPG = paths.repo(os.path.join(paths.EXTRACTED, "fpg"))
OUT = paths.repo(os.path.join(paths.REVIEW, "all-images"))
SHEETS = paths.repo(os.path.join(paths.REVIEW, "contact-sheets"))
SKIP = {"268", "269"}            # VAB sound banks
NO_LZ_SCAN = 1_500_000           # bigger entries: only plain TIMs are looked for
GREY = [(k * 17, k * 17, k * 17, 255 if k else 0) for k in range(16)]


def c15(v, transparent=True):
    if v == 0 and transparent:
        return (0, 0, 0, 0)
    return ((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31, 255)


def lz_prefix(src, n):
    """Decompress until n bytes are out; returns (data, compressed bytes used)."""
    ring, r, out, i = bytearray(0x400), 0x3BE, bytearray(), 0
    while i < len(src) and len(out) < n:
        f = src[i]
        i += 1
        for bit in range(8):
            if i >= len(src) or len(out) >= n:
                break
            if f >> bit & 1:
                if i + 1 >= len(src):
                    return bytes(out), len(src)
                b0, b1 = src[i], src[i + 1]
                i += 2
                pos = b0 | (b1 & 0xC0) << 2
                for _ in range(3 + (b1 & 0x3F)):
                    c = ring[pos]
                    pos = (pos + 1) & 0x3FF
                    out.append(c)
                    ring[r] = c
                    r = (r + 1) & 0x3FF
            else:
                c = src[i]
                i += 1
                out.append(c)
                ring[r] = c
                r = (r + 1) & 0x3FF
    return bytes(out), i


def tim_size(head):
    """Total size of the TIM whose first bytes are head, or None if it isn't one."""
    if len(head) < 20:
        return None
    magic, flags = struct.unpack_from("<II", head)
    if magic != 0x10 or flags not in (0, 1, 2, 8, 9):
        return None
    p = 8
    if flags & 8:
        ln, _, _, cw, ch = struct.unpack_from("<IHHHH", head, p)
        if not (cw and ch and ln == 12 + cw * ch * 2 and cw <= 256 and ch <= 256):
            return None
        p += ln
    return p


def lz_tims(raw):
    """(offset, TIM data) of LZSS-compressed TIMs starting inside raw."""
    o = 0
    while o < len(raw) - 24:
        if raw[o + 1] == 0x10 and not raw[o] & 1:
            head, _ = lz_prefix(raw[o:], 20)
            p = tim_size(head)
            if p is not None:
                head, _ = lz_prefix(raw[o:], p + 12)
                if len(head) >= p + 12:
                    ln, x, y, w, h = struct.unpack_from("<IHHHH", head, p)
                    if w and h and w <= 1024 and h <= 512 and ln == 12 + w * h * 2:
                        data, used = lz_prefix(raw[o:], p + ln)
                        try:
                            yield o, data, Tim(data, 0)
                            o += max(used, 1)
                            continue
                        except (ValueError, struct.error):
                            pass
        o += 1


def loose_tims(data):
    """TIMs whose image block length field is wrong but whose pixels are all there
    (e.g. FPG 249); find_tims skips these."""
    for i in range(0, len(data) - 20, 4):
        if data[i] != 0x10 or data[i + 1:i + 4] != b"\0\0\0" or data[i + 5:i + 8] != b"\0\0\0":
            continue
        p = tim_size(data[i:i + 64])
        if p is None or i + p + 12 > len(data):
            continue
        ln, x, y, w, h = struct.unpack_from("<IHHHH", data, i + p)
        need = 12 + w * h * 2
        if ln == need or not (w and h and x + w <= 1024 and y + h <= 512) or i + p + need > len(data):
            continue
        fixed = bytearray(data[i:i + p + need])
        struct.pack_into("<I", fixed, p, need)
        try:
            yield i, Tim(bytes(fixed), 0)
        except (ValueError, struct.error):
            pass


# ---------------------------------------------------------------- rendering

def tim_images(t):
    """[(suffix, RGBA image, note)] for a TIM."""
    stride = t.vram[2] * 2
    lines = [t.pixels_raw[y * stride:(y + 1) * stride] for y in range(t.height)]
    note = f"{t.bpp}bpp"
    if len(t.cluts) > 1 or (t.clut_pos and t.clut_pos[3] > 1):
        note += f", {t.clut_pos[3] if t.clut_pos else len(t.cluts)} palettes"
    if t.bpp == 16:
        img = Image.new("RGBA", (t.width, t.height))
        img.putdata([c15(v) for line in lines for v in struct.unpack(f"<{len(line) // 2}H", line)])
        return [("", img, note)]
    if t.bpp == 8 and t.clut_pos and t.clut_pos[2] % 256:
        # 8bpp container holding 4bpp textures with many 16-colour palettes (arena
        # sheets): shown with the palette giving the most distinct colours
        cols = [v for c in t.cluts for v in c]
        pals = [cols[k:k + 16] for k in range(0, len(cols), 16)]
        best = max(pals, key=lambda p: len(set(p)))
        pal = [c15(v) for v in best]
        idx = [[n for b in line for n in (b & 15, b >> 4)] for line in lines]
        note = f"4bpp textures in an 8bpp TIM, {len(pals)} palettes (one shown)"
    elif t.bpp == 4:
        pal = [c15(v) for v in t.cluts[0]] if t.cluts else GREY
        idx = [[n for b in line for n in (b & 15, b >> 4)] for line in lines]
    else:
        pal = [c15(v) for v in t.cluts[0]] if t.cluts else [(k, k, k, 255) for k in range(256)]
        idx = [list(line) for line in lines]
    if not t.cluts:
        note += ", no palette (grey)"
    img = Image.new("RGBA", (len(idx[0]), len(idx)))
    img.putdata([pal[i] if i < len(pal) else (255, 0, 255, 255) for line in idx for i in line])
    return [("", img, note)]


def sheet_images(entry, t):
    """16bpp VRAM sheets holding 4bpp textures."""
    stride = t.vram[2] * 2
    raw = t.pixels_raw
    if entry in ("279", "280", "281", "282", "283", "284", "285"):
        pal = [c15(v, False) for v in struct.unpack_from("<256H", raw, 240 * stride)]
        photo = Image.new("RGBA", (320, 240))
        photo.putdata([pal[raw[y * stride + x]] for y in range(240) for x in range(320)])
        cpal = [c15(v) for v in struct.unpack_from("<16H", raw, 241 * stride + 384)]
        cap = Image.new("RGBA", (128, 240))
        cap.putdata([cpal[n] for y in range(240) for b in raw[y * stride + 384:y * stride + 448]
                     for n in (b & 15, b >> 4)])
        return [("", photo, "8bpp photo (16bpp VRAM block)"), ("c", cap, "4bpp captions")]
    out = []
    w4 = t.vram[2] * 4
    idx = [[n for b in raw[y * stride:(y + 1) * stride] for n in (b & 15, b >> 4)] for y in range(t.height)]
    for k in range(0, w4, 256):
        img = Image.new("RGBA", (256, t.height))
        img.putdata([GREY[i] for line in idx for i in line[k:k + 256]])
        if img.getbbox():
            out.append((f"p{k // 256}", img, f"4bpp texture page, x {k}-{k + 255} (grey palette)"))
    return out


def portrait(data):
    tiles = data[:160]
    n = sum(1 for v in tiles if v)
    if len(data) != 672 + n * 1024 or set(tiles) - {0, 1}:
        return None
    pal = [c15(v) for v in struct.unpack_from("<256H", data, 160)]
    img = Image.new("RGBA", (512, 320), (0, 0, 0, 0))
    k = 0
    for i, v in enumerate(tiles):
        if not v:
            continue
        tile = data[672 + k * 1024:672 + (k + 1) * 1024]
        t = Image.new("RGBA", (32, 32))
        t.putdata([pal[b] for b in tile])
        img.paste(t, ((i % 16) * 32, (i // 16) * 32))
        k += 1
    return img.crop(img.getbbox() or (0, 0, 512, 320))


def bs_image(data):
    for w, h in ((512, 320), (320, 240), (640, 480), (256, 256)):
        mbs, _, _ = bs.decode(data, w, h)
        if len(mbs) == (w // 16) * (h // 16):
            rows = bs.to_rgb(mbs, h)
            img = Image.new("RGBA", (w, h))
            img.putdata([px for row in rows for px in row])
            return img
    return None


# ---------------------------------------------------------------- discovery

def discover():
    found = []           # (id, entry, where, note, image)
    for name in sorted(os.listdir(FPG)):
        entry = name[:3]
        if entry in SKIP or not name.endswith(".bin"):
            continue
        raw = open(os.path.join(FPG, name), "rb").read()
        items = []       # (where, Tim or image, note)
        dec = None
        if 143 <= int(entry) <= 247:
            img = portrait(decompress(raw))
            if img:
                items.append(("compressed entry", img, "story portrait, 32x32 tiles"))
        for o, t in find_tims(raw):
            items.append((f"raw +{o:#x}", t, ""))
        for o, t in loose_tims(raw):
            items.append((f"raw +{o:#x} (header length wrong)", t, ""))
        if len(raw) < NO_LZ_SCAN:
            try:
                dec = decompress(raw)
            except IndexError:
                dec = None
            if dec:
                for o, t in find_tims(dec):
                    items.append((f"decompressed +{o:#x}", t, ""))
        if len(raw) < NO_LZ_SCAN:
            for o, _data, t in lz_tims(raw):
                items.append((f"compressed TIM at raw +{o:#x}", t, ""))
        for blob, label in ((raw, "raw"), (dec, "decompressed")):
            if blob and len(blob) > 8 and struct.unpack_from("<H", blob, 2)[0] == 0x3800 \
                    and struct.unpack_from("<H", blob, 6)[0] in (2, 3):
                img = bs_image(blob)
                if img:
                    items.append((label, img, "BS (MDEC) picture"))
        n, here = 0, set()
        for where, obj, note in items:
            if isinstance(obj, Tim):
                parts = sheet_images(entry, obj) if obj.bpp == 16 and entry in (
                    "277", "279", "280", "281", "282", "283", "284", "285") else tim_images(obj)
                where += f", VRAM {obj.vram[0]},{obj.vram[1]}"
            else:
                parts = [("", obj, note)]
            key = b"".join(img.tobytes() for _, img, _ in parts)
            if key in here:          # the same TIM found twice (whole entry and LZ scan)
                continue
            here.add(key)
            for suffix, img, pnote in parts:
                found.append((f"{entry}_{n:02d}{suffix}", entry, where, pnote or note, img))
            n += 1
        print(f"{entry}: {n} image(s)", flush=True)
    return found


def main(argv=None):
    import argparse
    global FPG, OUT, SHEETS
    ap = argparse.ArgumentParser(description="Find every image in FPG.BIN and lay them out on contact sheets.")
    paths.add(ap, "--extracted", paths.EXTRACTED, "tools/extract.py output")
    paths.add(ap, "--review", paths.REVIEW, "output folder (all-images/, contact-sheets/)")
    args = ap.parse_args(argv)
    FPG = os.path.join(args.extracted, "fpg")
    OUT = os.path.join(args.review, "all-images")
    SHEETS = os.path.join(args.review, "contact-sheets")
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SHEETS, exist_ok=True)
    for d in (OUT, SHEETS):
        for f in os.listdir(d):
            if f.endswith(".png"):
                os.remove(os.path.join(d, f))
    found = discover()
    seen, rows, unique = {}, [], []
    for iid, entry, where, note, img in found:
        h = hashlib.sha1(img.tobytes() + bytes(str(img.size), "ascii")).hexdigest()
        dup = seen.get(h)
        if dup is None:
            seen[h] = iid
            img.save(os.path.join(OUT, f"{iid}.png"))
            unique.append((iid, img, note))
        rows.append({"id": iid, "entry": entry, "where": where, "width": img.width, "height": img.height,
                     "note": note, "duplicate_of": dup or ""})
    with open(os.path.join(OUT, "index.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    dups = {}
    for r in rows:
        if r["duplicate_of"]:
            dups.setdefault(r["duplicate_of"], []).append(r["id"])
    pages = layout(unique, dups)
    print(f"{len(rows)} images ({len(unique)} unique) on {pages} contact sheets -> "
          f"{SHEETS}/sheet_NNN.png; index: {OUT}/index.csv")


def layout(items, dups, width=1600, max_h=1800):
    pages, cur, x, y, rowh = 0, [], 0, 0, 0

    def flush():
        nonlocal pages
        if not cur:
            return
        h = max(py + t.height for t, px, py in cur) + 4
        c = Image.new("RGBA", (width, h), (30, 30, 40, 255))
        for t, px, py in cur:
            c.alpha_composite(t, (px, py))
        c.save(os.path.join(SHEETS, f"sheet_{pages:03d}.png"))
        pages += 1

    for iid, img, _note in items:
        s = 2 if img.width <= 160 and img.height <= 160 else 1
        im = img.resize((img.width * s, img.height * s), Image.NEAREST) if s > 1 else img
        if im.width > width:
            im = im.resize((width, im.height * width // im.width), Image.NEAREST)
        label = f"{iid}  {img.width}x{img.height}" + (f"  x{1 + len(dups[iid])}" if iid in dups else "")
        tw = max(im.width, 6 * len(label) + 4)
        tile = Image.new("RGBA", (min(width, tw), im.height + 14), (60, 60, 90, 255))
        checker = Image.new("RGBA", im.size, (255, 0, 255, 255))   # magenta = transparent
        checker.alpha_composite(im)
        tile.paste(checker, (0, 14))
        d = ImageDraw.Draw(tile)
        d.text((2, 1), label, fill=(255, 255, 0, 255))
        if x + tile.width > width:
            x, y, rowh = 0, y + rowh + 6, 0
        if y + tile.height > max_h and cur:
            flush()
            cur, x, y, rowh = [], 0, 0, 0
        cur.append((tile, x, y))
        x += tile.width + 6
        rowh = max(rowh, tile.height)
    flush()
    return pages


if __name__ == "__main__":
    main()
