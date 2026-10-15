#!/usr/bin/env python3
"""Edit the game's text images (needs Pillow: pip install -r requirements.txt).

  edit.py overview [text]       every image as Japanese | English on review/overview/overview_NNN.png
  edit.py list [text]           find images in images/graphics.csv (name, Japanese or English)
  edit.py start <images>        copy the current English (or the example) to images/handmade/<image>.png
                                (edit this) next to <image>_japanese.png (the original, for reference)
  edit.py check <images>        validate images/handmade/<image>.png; writes <image>_check.png
  edit.py approve <images> [--force]
                                final: snap to the game palette, move to images/approved/, mark done
                                (an image with no hand edit gets its example approved)
  edit.py reset <images>        drop the hand edit and approval of an image (back to Japanese)
  edit.py sheet ...             edit several images as one sheet (see `edit.py sheet`)

<images>: names separated by spaces or commas; wildcards work (mode_*, victory_*).

Folder options: --images, --extracted, --review, --font-dir;
defaults are the repository's images/, extracted/ and review/ (see `edit.py --help`).

The English side of an image is, in order: images/handmade/ (HAND), images/approved/ (DONE),
the example render in review/english/ (EXAMPLE). The build uses only HAND and DONE images,
so a hand-made image is in the game as soon as you build - approve it once it looks right.
"""
import fnmatch
import json
import os
import shutil
import sys
import types

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("needs Pillow: python3 -m pip install -r requirements.txt") from None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx  # noqa: E402
import render  # noqa: E402

KEY = (255, 0, 255, 255)            # transparency on sheets
BG = (40, 40, 48, 255)
TAGS = {"HAND": (120, 255, 120), "DONE": (255, 255, 255), "EXAMPLE": (150, 200, 255), "KEEP": (150, 150, 150),
        "NONE": (255, 120, 120)}
REFS = ("_japanese", "_check")


# ---------------------------------------------------------------- helpers

def show(p):
    return os.path.relpath(p)


def sheets_dir():
    return os.path.join(gfx.HANDMADE, "sheets")


def names_from(args):
    every = [r["image"] for r in gfx.rows()]
    out = []
    for tok in (t for a in args for t in a.replace(",", " ").split()):
        hits = fnmatch.filter(every, tok)
        if not hits:
            sys.exit(f"no image matches {tok!r} (try: edit.py list)")
        out += [h for h in hits if h not in out]
    return out


def japanese(name):
    p = os.path.join(gfx.JAPANESE, f"{name}.png")
    if not os.path.exists(p):
        gfx.export()
    return Image.open(p)


def example(r):
    p = os.path.join(render.english_dir(), f"{r['image']}.png")
    if r["status"] != "keep" and r["english"] and not os.path.exists(p):
        render.render(r)
    return p if os.path.exists(p) else None


def english(r):
    """(tag, path) of the image's current English side."""
    for tag, d in (("HAND", gfx.HANDMADE), ("DONE", gfx.APPROVED)):
        p = os.path.join(d, f"{r['image']}.png")
        if os.path.exists(p):
            return tag, p
    if r["status"] == "keep":
        return "KEEP", os.path.join(gfx.JAPANESE, f"{r['image']}.png")
    p = example(r)
    return ("EXAMPLE", p) if p else ("NONE", os.path.join(gfx.JAPANESE, f"{r['image']}.png"))


def rgba(img):
    return img.convert("RGBA")


def snap(r, img):
    """An RGBA image as indices of the image's game palette -> (indices, palette)."""
    w, h, _, pal = gfx.piece(r)
    png = types.SimpleNamespace(width=img.width, height=img.height, indexed=False,
                                rows=[[img.getpixel((x, y)) for x in range(img.width)] for y in range(img.height)])
    return gfx.to_indices(r["image"], png, w, h, pal), pal


def indexed(idx, pal, w, h):
    im = Image.new("P", (w, h))
    im.putpalette([c for v in pal for c in gfx.c15(v)])
    im.putdata(idx)
    im.info["transparency"] = bytes(0 if v == 0 else 255 for v in pal)
    return im


def on_key(img):
    """The image over magenta, so transparency shows."""
    base = Image.new("RGBA", img.size, KEY)
    base.alpha_composite(rgba(img))
    return base


def set_status(name, status):
    table = gfx.rows()
    for r in table:
        if r["image"] == name:
            r["status"] = status
    gfx.write_rows(table)


# ---------------------------------------------------------------- overview / list

def overview(text=""):
    table = [r for r in gfx.rows() if text.lower() in " ".join((r["image"], r["japanese"], r["english"])).lower()]
    out = os.path.join(gfx.REVIEW, "overview")
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.startswith("overview_"):
            os.remove(os.path.join(out, f))
    tiles = []
    for r in table:
        jp = japanese(r["image"])
        tag, p = english(r)
        en = Image.open(p)
        s = 3 if jp.width <= 128 and jp.height <= 64 else 1
        w, h = jp.width * s, jp.height * s
        t = Image.new("RGBA", (max(2 * w + 8, 300), h + 28), (60, 60, 90, 255))
        t.paste(on_key(jp).resize((w, h), Image.NEAREST), (0, 26))
        t.paste(on_key(en).resize((w, h), Image.NEAREST), (w + 8, 26))
        d = ImageDraw.Draw(t)
        d.line([(w + 3, 26), (w + 3, 26 + h)], fill=(255, 255, 0, 255), width=2)
        d.text((2, 1), f"{r['image']}  {tag}", fill=TAGS[tag] + (255,))
        d.text((2, 13), r["english"] or "-", fill=(220, 220, 220, 255))
        tiles.append(t)
    W, H = 1600, 1800
    pages, cur, x, y, rowh = [], [], 0, 0, 0
    for t in tiles:
        if x + t.width > W:
            x, y, rowh = 0, y + rowh + 10, 0
        if y + t.height > H and cur:
            pages.append(cur)
            cur, x, y, rowh = [], 0, 0, 0
        cur.append((t, x, y))
        x += t.width + 12
        rowh = max(rowh, t.height)
    if cur:
        pages.append(cur)
    for k, page in enumerate(pages):
        c = Image.new("RGBA", (W, max(y + t.height for t, x, y in page) + 4), (30, 30, 40, 255))
        for t, x, y in page:
            c.alpha_composite(t, (x, y))
        c.save(os.path.join(out, f"overview_{k:03d}.png"))
    print(f"{len(tiles)} images on {len(pages)} page(s) -> {show(out)}/overview_NNN.png")
    print("  tags: HAND = hand-made (in the build), DONE = approved, EXAMPLE = automatic example "
          "(not in the build), KEEP = stays Japanese")


def find(text=""):
    for r in gfx.rows():
        if text.lower() in " ".join((r["image"], r["japanese"], r["english"])).lower():
            tag, _ = english(r)
            print(f"{r['image']:<24} {r['w']}x{r['h']:<4} {tag:<8} {r['japanese']} | {r['english']}")


# ---------------------------------------------------------------- single images

def start(name):
    r = gfx.row(name)
    os.makedirs(gfx.HANDMADE, exist_ok=True)
    target = os.path.join(gfx.HANDMADE, f"{name}.png")
    if os.path.exists(target):
        print(f"{show(target)} already exists - not overwriting")
    else:
        tag, src = english(r)
        shutil.copyfile(src, target)
        print(f"{name}: started from the {tag.lower()} version")
    japanese(name).save(os.path.join(gfx.HANDMADE, f"{name}_japanese.png"))
    print(f"  {r['w']}x{r['h']}, {1 << gfx.bpp(r)} colours | {r['japanese']} -> {r['english']}")
    print(f"  edit {show(target)}  (reference: {name}_japanese.png)")


def check(name):
    r = gfx.row(name)
    p = os.path.join(gfx.HANDMADE, f"{name}.png")
    print(f"{name}:")
    if not os.path.exists(p):
        print(f"  ! {show(p)} not found (run: edit.py start {name})")
        return ["missing"]
    new = Image.open(p)
    w, h, _, pal = gfx.piece(r)
    if new.size != (w, h):
        print(f"  ! size {new.size[0]}x{new.size[1]}, must be {w}x{h}")
        return ["size"]
    idx, pal = snap(r, rgba(new))
    snapped = indexed(idx, pal, w, h)
    s = 4 if w <= 128 else 2
    a = on_key(japanese(name)).resize((w * s, h * s), Image.NEAREST)
    b = on_key(snapped).resize((w * s, h * s), Image.NEAREST)
    prev = Image.new("RGBA", (w * s, 2 * h * s + 6), (255, 255, 0, 255))
    prev.paste(a, (0, 0))
    prev.paste(b, (0, h * s + 6))
    prev.save(os.path.join(gfx.HANDMADE, f"{name}_check.png"))
    print(f"  OK - preview (original above, yours below, as the game will show it): {name}_check.png")
    return []


def approve(name, force=False):
    hand = os.path.join(gfx.HANDMADE, f"{name}.png")
    if not os.path.exists(hand):
        tag, src = english(gfx.row(name))
        if tag != "EXAMPLE":
            print(f"{name}:\n  ! nothing to approve ({tag.lower()})")
            return False
        os.makedirs(gfx.HANDMADE, exist_ok=True)
        shutil.copyfile(src, hand)
        print(f"{name}: no hand edit - approving the example")
    problems = check(name)
    if problems and not force:
        print("  not approved")
        return False
    r = gfx.row(name)
    w, h, _, pal = gfx.piece(r)
    idx, pal = snap(r, rgba(Image.open(os.path.join(gfx.HANDMADE, f"{name}.png"))))
    gfx.write_png(os.path.join(gfx.APPROVED, f"{name}.png"), w, h, bytes(idx), pal)
    for s in ("",) + REFS:
        f = os.path.join(gfx.HANDMADE, f"{name}{s}.png")
        if os.path.exists(f):
            os.remove(f)
    set_status(name, "done")
    print(f"  approved -> {show(os.path.join(gfx.APPROVED, name + '.png'))}")
    return True


def reset(name):
    gone = []
    for d, suffixes in ((gfx.HANDMADE, ("",) + REFS), (gfx.APPROVED, ("",))):
        for s in suffixes:
            f = os.path.join(d, f"{name}{s}.png")
            if os.path.exists(f):
                os.remove(f)
                gone.append(show(f))
    if gfx.row(name)["status"] == "done":
        set_status(name, "todo")
    print(f"{name}: reset" + (f" (removed {', '.join(gone)})" if gone else " (nothing to remove)"))


# ---------------------------------------------------------------- sheets

SHEET_HELP = """edit.py sheet start <sheet> <images>   images/handmade/sheets/<sheet>.png: each image as
                                         Japanese | English at original size - edit the right side
edit.py sheet check <sheet>              <sheet>_check.png: the sheet as the game will show it
edit.py sheet split <sheet> [--all]      changed images -> images/handmade/<image>.png (in the build)
edit.py sheet approve <sheet> [--all]    split + approve them + remove the sheet
edit.py sheet list                       existing sheets
--all also takes images you left unchanged (e.g. an example that is already fine).
Transparent pixels are magenta (255,0,255): paint magenta to make pixels transparent.
Only the English rectangles are read back; anything else on the sheet is ignored."""

GAP, LABEL, MID, MAX_W = 8, 12, 4, 640


def sheet_files(sheet):
    d = sheets_dir()
    return (os.path.join(d, f"{sheet}.png"), os.path.join(d, f"{sheet}.sheet.json"),
            os.path.join(d, f"{sheet}_check.png"))


def compose(pos, size, pick):
    sheet = Image.new("RGBA", size, BG)
    d = ImageDraw.Draw(sheet)
    for n, (x, y, w, h) in pos.items():
        jx = x - w - MID
        d.text((jx, y - LABEL + 1), n, fill=(255, 255, 0, 255))
        sheet.paste(on_key(japanese(n)), (jx, y))
        sheet.paste(on_key(pick(n)), (x, y))
        d.line([(x - MID // 2 - 1, y), (x - MID // 2 - 1, y + h - 1)], fill=(255, 255, 0, 255))
    return sheet


def sheet_start(sheet, names):
    png, manifest, _ = sheet_files(sheet)
    if os.path.exists(manifest):
        sys.exit(f'sheet "{sheet}" already exists - pick another name or approve/remove it')
    pos, x, y, rowh = {}, GAP, GAP, 0
    for n in names:
        r = gfx.row(n)
        w, h = int(r["w"]), int(r["h"])
        tile = max(2 * w + MID, 80)
        if x + tile + GAP > MAX_W and x > GAP:
            x, y, rowh = GAP, y + rowh + LABEL + GAP, 0
        pos[n] = (x + w + MID, y + LABEL, w, h)
        x += tile + GAP
        rowh = max(rowh, h)
    size = (max(p[0] + p[2] for p in pos.values()) + GAP, max(p[1] + p[3] for p in pos.values()) + GAP)
    os.makedirs(sheets_dir(), exist_ok=True)
    start_from = {n: english(gfx.row(n)) for n in names}
    img = compose(pos, size, lambda n: Image.open(start_from[n][1]))
    img.save(png)
    started = {n: rgba_hash(on_key(Image.open(p))) for n, (_, p) in start_from.items()}
    json.dump({"images": pos, "started_from": started},
              open(manifest, "w"), indent=1)
    print(f'sheet "{sheet}": {len(names)} images, {size[0]}x{size[1]} -> {show(png)}')
    print("  edit the right-hand (English) image of each pair, then: "
          f"edit.py sheet check {sheet}  /  split {sheet}  /  approve {sheet}")


def rgba_hash(img):
    import hashlib
    return hashlib.sha1(img.tobytes()).hexdigest()


def pieces(sheet):
    png, manifest, _ = sheet_files(sheet)
    if not os.path.exists(manifest):
        sys.exit(f'no sheet "{sheet}" (see: edit.py sheet list)')
    m = json.load(open(manifest))
    img = rgba(Image.open(png))
    out = []
    for n, (x, y, w, h) in m["images"].items():
        crop = img.crop((x, y, x + w, y + h))
        changed = rgba_hash(crop) != m["started_from"][n]
        data = crop.get_flattened_data() if hasattr(crop, "get_flattened_data") else crop.getdata()
        crop.putdata([(0, 0, 0, 0) if p[:3] == KEY[:3] or p[3] == 0 else p[:3] + (255,) for p in data])
        out.append((n, crop, changed))
    return m, out


def sheet_check(sheet):
    m, ps = pieces(sheet)
    png, _, check_png = sheet_files(sheet)
    snapped = {n: indexed(*snap(gfx.row(n), p), p.width, p.height) for n, p, _ in ps}
    compose({n: tuple(v) for n, v in m["images"].items()}, Image.open(png).size, lambda n: snapped[n]).save(check_png)
    changed = [n for n, _, c in ps if c]
    print(f'sheet "{sheet}": {len(changed)} of {len(ps)} images changed'
          + (f": {', '.join(changed)}" if changed else ""))
    print(f"  as the game will show them: {show(check_png)}")


def sheet_split(sheet, take_all=False):
    _, ps = pieces(sheet)
    written = []
    for n, p, changed in ps:
        if not (changed or take_all):
            continue
        r = gfx.row(n)
        idx, pal = snap(r, p)
        gfx.write_png(os.path.join(gfx.HANDMADE, f"{n}.png"), p.width, p.height, bytes(idx), pal)
        written.append(n)
    print(f'sheet "{sheet}": {len(written)} image(s) -> {show(gfx.HANDMADE)}/'
          + (f": {', '.join(written)}" if written else " (nothing changed; --all takes them anyway)"))
    return written


def sheet_list():
    d = sheets_dir()
    found = sorted(f[:-11] for f in os.listdir(d) if f.endswith(".sheet.json")) if os.path.isdir(d) else []
    for s in found:
        m = json.load(open(sheet_files(s)[1]))
        print(f"{s}: {', '.join(m['images'])}")
    if not found:
        print("no sheets")


def main(a):
    import argparse
    ap = argparse.ArgumentParser(add_help=False)
    gfx.add_options(ap)
    render.add_options(ap)
    ap.add_argument("-h", "--help", action="store_true")
    opts, a = ap.parse_known_args(a)
    if opts.help:
        print(__doc__)
        ap.print_help()
        return
    gfx.configure(opts.images, opts.extracted, opts.review)
    render.FONT_DIR = opts.font_dir
    flags = {x for x in a if x.startswith("--")}
    a = [x for x in a if not x.startswith("--")]
    cmd = a[0] if a else ""
    if cmd == "overview":
        overview(" ".join(a[1:]))
    elif cmd == "list":
        find(" ".join(a[1:]))
    elif cmd in ("start", "check", "approve", "reset") and len(a) > 1:
        names = names_from(a[1:])
        results = []
        for i, n in enumerate(names):
            if i and cmd != "reset":
                print()
            if cmd == "start":
                start(n)
            elif cmd == "check":
                results.append(not check(n))
            elif cmd == "approve":
                results.append(approve(n, "--force" in flags))
            else:
                reset(n)
        if len(results) > 1:
            print(f"\n{sum(results)}/{len(results)} {'OK' if cmd == 'check' else 'approved'}")
    elif cmd == "sheet":
        sub = a[1] if len(a) > 1 else ""
        if sub == "start" and len(a) > 3:
            sheet_start(a[2], names_from(a[3:]))
        elif sub == "check" and len(a) == 3:
            sheet_check(a[2])
        elif sub == "split" and len(a) == 3:
            sheet_split(a[2], "--all" in flags)
        elif sub == "approve" and len(a) == 3:
            names = sheet_split(a[2], "--all" in flags)
            ok = [n for n in names if approve(n, "--force" in flags)]
            if len(ok) == len(names):
                for f in sheet_files(a[2]):
                    if os.path.exists(f):
                        os.remove(f)
                print(f'sheet "{a[2]}": {len(ok)} image(s) approved; sheet removed')
            else:
                print(f'sheet "{a[2]}": approved {len(ok)}/{len(names)} - sheet kept')
        elif sub == "list":
            sheet_list()
        else:
            print(SHEET_HELP)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
