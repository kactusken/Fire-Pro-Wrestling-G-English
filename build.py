#!/usr/bin/env python3
"""Build a patched disc image from the original Japanese one.

    python3 build.py                 English, everything unlocked, extra Wrestler Make parts
    python3 build.py --no-unlock     English, the original unlock progression
    python3 build.py --no-unlock --no-extra-parts
                                     English, otherwise the game as released
    python3 build.py --japanese      Japanese text, everything unlocked

Output: build/<name>.bin and .cue; the name says which options were used
(--name sets it). make_patches.py builds the release variants and their xdelta patches.

Developer options:
    --debug-menu       developer menu on the title screen (hold Select, press Start)
    --route5           debug menu, and the graduation offer always gives the cut
                       Choshu/Liger scene (debug mode 4, scene 3)
    --no-text 004      leave that overlay's strings in Japanese (comma-separated list)
    --only 004:8005b690-8005bbe0
                       translate only the strings in that range of that overlay
                       ("004:!lo-hi" translates all but that range)

Steps: unpack FPG.BIN from the original image, insert the translated story script,
patch the story overlay for variable-width text, translate the menus, roster,
moves and images, repack FPG.BIN (it must not grow), and patch it and the
executable back into a copy of the image in place.
"""
import argparse
import os
import runpy
import shutil
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import codepatch  # noqa: E402
import debugmenu  # noqa: E402
import hiddenparts  # noqa: E402
import editdata  # noqa: E402
import discfs  # noqa: E402
import discpatch  # noqa: E402
import fpgbin  # noqa: E402
import gfx  # noqa: E402
import lzss  # noqa: E402
import menu_vwf_patch  # noqa: E402
import menufont  # noqa: E402
import moves  # noqa: E402
import roster  # noqa: E402
import script  # noqa: E402
import skilledit  # noqa: E402
import moveedit  # noqa: E402
import paths  # noqa: E402
import storycheck  # noqa: E402
import strtab  # noqa: E402
import tutorial  # noqa: E402
import unlock  # noqa: E402
import vwf_patch  # noqa: E402

OUT_NAME = "Fire Pro Wrestling G (English)"
OUT_NAME_JP = "Fire Pro Wrestling G (Japan)"

OVERLAY_BASE = 0x8005A718
OVERLAY_LIMIT = 0x80092000  # heap start
# UI strings in code overlays: FPG entry -> (file in text/, rodata start, end)
OVERLAY_TEXT = {
    "001": ("ov001.txt", 0x8005A7E8, 0x8005C5B0),
    "002": ("ov002.txt", 0x8005A71C, 0x8005AD40),
    "004": ("ov004.txt", 0x8005A71C, 0x8005D270),
    "005": ("ov005.txt", 0x8005A71C, 0x8005AC10),
}
# EXE strings: (file in text/, area start, end)
EXE_TEXT = ("exe.txt", 0x800103B0, 0x80010B34)  # after a byte table; ends before a jump table
# Memory card save title: (address, Japanese, English, slot bytes); full-width SJIS
SAVE_TITLE = (0x80010364, "ファイヤープロレスリングＧ　セーブデータ".encode("cp932"),
              "ＦＩＲＥ　ＰＲＯ　ＷＲＥＳＴＬＩＮＧ　Ｇ", 44)
# PocketStation save (FPG 014, written by overlay 004): its SJIS title, 64 bytes at +4
POCKET_TITLE = ("ファイヤープロレスリングＧ　ファイプロポケット" + "　" * 9,
                "ＦＩＲＥ　ＰＲＯ　ＷＲＥＳＴＬＩＮＧ　Ｇ　ＰＯＣＫＥＴ" + "　" * 5)
# First BSS address each overlay uses past its end (tools/bss_scan.py):
# a string pool must stay below it.
OVERLAY_BSS = {"001": 0x80090000, "004": 0x80080000, "005": 0x80080000}  # 000: none
# Code tweaks (address, original word, new word) applied with the text.
OVERLAY_CODE = {
    # Match setup: labels are centred in a 108 px field (ctx+0x2e, see the
    # EXE wrapper 0x80016cf8). 120 px moves them 6 px right so the longer
    # English labels clear the window border.
    "001": [(0x8005FE28, 0x2402006C, 0x24020078),   # addiu v0, zero, 108 -> 120
            (0x8005FFA4, 0x2403006C, 0x24030078),   # addiu v1, zero, 108 -> 120
            # Referee value: field 256 -> 268 moves the name 6 px right,
            # clear of the "Referee" label (names up to ~75 px fit).
            (0x8006053C, 0x24020100, 0x2402010C),
            # Team battle positions (Lead ... Captain): boxes 2 -> 5 cells,
            # and the team screen's cell pool grows by the same amount
            # (0x80081ad8 a2 = cells; these pools were sized exactly).
            (0x800682AC, 0x2406003A, 0x24060049),   # one team: 58 -> 73 cells
            (0x80068340, 0x24040002, 0x24040005),
            (0x80068384, 0x24040002, 0x24040005),   # (loop's delay slot)
            # Select screen birth date (0x80087920 appends a kanji to each
            # number): 1971年 9月23日 -> 1971／ 9／23.
            (0x80087990, 0x24020094, 0x24020081),   # 年 -> ／ (0x815E)
            (0x800879A0, 0x2402004E, 0x2402005E),
            (0x800879E0, 0x2402008C, 0x24020081),   # 月 -> ／
            (0x800879F0, 0x2402008E, 0x2402005E),
            (0x80087A28, 0x24020093, 0x24020000),   # 日 -> (end of string)
            # Option boxes (menu table 0x80089688, e.g. One Night Match /
            # One Night Tournament): 12 cells per line cut "One Night
            # Tournament" (15). Lines get 16 cells; the box pool grows from
            # 72 to 88 so the 5-line boxes still fit.
            (0x80087F5C, 0x24C60048, 0x24C60058),   # pool: a2 += 72 -> 88
            (0x80088040, 0x2404000C, 0x24040010),   # line window: 12 -> 16 cells
            ],
}
# Extra string tables appended to an overlay: (strings, [(lui, addiu)] code
# references to repoint at the new table). The VS team screen has 2-cell tiles
# for the positions, so it gets its own short labels; the team screen keeps
# the full words.
OVERLAY_TABLES = {
    "001": [(["#1", "#2", "#3", "#4", "#5"],   # Lead .. Captain (table 0x8008902c)
             [(0x8006A0C4, 0x8006A0CC), (0x8006A144, 0x8006A148)])],
}


def read_disc_file(img, name):
    with open(img, "rb") as f:
        for path, lba, size, _is_dir in discfs.walk(f):
            if path == name:
                return discfs.read_extent(f, lba, size)
    raise SystemExit(f"{name} not on disc")


def write_compressed(path, data):
    """Recompress an FPG entry. Entries may grow: the game reads FPG.BIN's TOC at boot
    and fpgbin.pack lays them out again; only the whole archive must keep its size."""
    open(path, "wb").write(lzss.compress(data))


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 2)[2])
    paths.add(ap, "--rom", paths.ROM, "original Japanese disc image (.bin, MODE2/2352)")
    paths.add(ap, "--out-dir", paths.BUILD, "output folder (work files go in its work/)")
    paths.add(ap, "--script", paths.SCRIPT, "story script folder")
    paths.add(ap, "--text", paths.TEXT, "menu and data text folder")
    paths.add(ap, "--images", paths.IMAGES, "image catalogue folder (graphics.csv, approved/, handmade/)")
    ap.add_argument("--name", help="output file name without extension (default: from the options)")
    ap.add_argument("--japanese", action="store_true",
                    help="keep the Japanese text; only apply the unlock patch")
    ap.add_argument("--no-unlock", action="store_true",
                    help="keep the original unlock progression (tools/unlock.py)")
    ap.add_argument("--no-extra-parts", action="store_true",
                    help="leave out the unused heads and body parts otherwise added to "
                         "Wrestler Make (tools/hiddenparts.py)")
    ap.add_argument("--debug-menu", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--route5", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-text", metavar="ENTRIES", help=argparse.SUPPRESS)
    ap.add_argument("--only", metavar="ENTRY:RANGE", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.japanese and (args.debug_menu or args.route5 or args.no_text or args.only):
        ap.error("--japanese only combines with --no-unlock")
    if args.japanese and args.no_unlock:
        print("note: --japanese --no-unlock gives an unchanged copy of the original")
    return args


def output_name(args):
    if args.name:
        return args.name
    if args.japanese:
        return OUT_NAME_JP + ("" if args.no_unlock else " (unlocked)")
    name = OUT_NAME
    if args.no_text:
        name += f" (no-text {','.join(sorted(args.no_text.split(',')))})"
    if args.only:
        name += f" (only {args.only.replace(':', ' ')})"
    if args.no_unlock:
        name += " (locked)"
    if args.debug_menu or args.route5:
        name += " (debug)"
    if args.route5:
        name += " (route 5)"
    if args.no_extra_parts:
        name += " (no extra parts)"
    return name


def write_cue(out_dir, name):
    with open(os.path.join(out_dir, name + ".cue"), "w", newline="\r\n") as f:
        f.write(f'FILE "{name}.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')


def build_japanese(args, out_bin):
    """The original game with only the executable patches (unlocks)."""
    exe = bytearray(read_disc_file(args.rom, "/SLPS_020.65"))
    if not args.no_unlock:
        unlock.patch_exe(exe)
    shutil.copyfile(args.rom, out_bin)
    with open(out_bin, "r+b") as f:
        discpatch.patch_file(f, "/SLPS_020.65", bytes(exe))


class Build:
    """State shared by the build steps: options, the unpacked archive, and data
    that later steps reuse (fonts, roster rows, tutorial icon positions...)."""

    def __init__(self, args):
        self.args = args
        self.text_dir = args.text
        self.script_dir = args.script
        self.work = os.path.join(args.out_dir, "work")
        self.unpacked = os.path.join(self.work, "fpg")
        self.debug_menu = args.debug_menu or args.route5
        self.skip_text = set(args.no_text.split(",")) if args.no_text else set()
        self.select = {}
        if args.only:
            entry, rng = args.only.split(":")
            invert = rng.startswith("!")
            lo, hi = (int(x, 16) for x in rng.lstrip("!").split("-"))
            self.select[entry] = lambda a: (lo <= a <= hi) != invert

    def text(self, name):
        return os.path.join(self.text_dir, name)

    def entry_path(self, entry):
        return os.path.join(self.unpacked, f"{entry}.bin")

    def read_raw(self, entry):
        return bytearray(open(self.entry_path(entry), "rb").read())

    def write_raw(self, entry, data):
        open(self.entry_path(entry), "wb").write(bytes(data))

    def read(self, entry):
        """An LZSS-compressed entry, decompressed."""
        return bytearray(lzss.decompress(open(self.entry_path(entry), "rb").read()))

    def write(self, entry, data):
        write_compressed(self.entry_path(entry), bytes(data))


def unpack_fpg(b):
    """Copy FPG.BIN out of the original image and unpack it into work/fpg/."""
    os.makedirs(b.work, exist_ok=True)
    b.fpg = read_disc_file(b.args.rom, "/FPG.BIN")
    b.fpg_path = os.path.join(b.work, "FPG.BIN")
    open(b.fpg_path, "wb").write(b.fpg)
    if os.path.isdir(b.unpacked):
        shutil.rmtree(b.unpacked)
    fpgbin.unpack(b.fpg_path, b.unpacked)


def patch_story(b):
    """Story script (FPG 130/131) and the variable-width text hook in overlay 002."""
    e130, e131 = b.entry_path("130"), b.entry_path("131")
    font = bytes(b.read_raw("128"))
    b.metrics = vwf_patch.metrics(font)
    script.insert(e130, e131, b.script_dir, e130, e131, b.metrics)
    patched, _ = vwf_patch.patch_overlay(bytes(b.read("002")), font)
    b.write("002", patched)
    print("patched overlay 002 (tiled variable-width text)")


def patch_menu_font(b):
    """Menu font (two copies): proportional widths for Latin punctuation."""
    for entry, base in (("009", 0), ("011", 0x18)):
        f = b.read(entry)
        glyphs = menufont.patch_glyphs(f, base)
        if menufont.patch_widths(f, base) or glyphs:
            b.write(entry, f)
        if entry == "009":
            b.widths = menu_vwf_patch.ascii_widths(f)
            b.menu_font = bytes(f)
    print("patched menu font widths and glyphs")


def patch_tutorial(b):
    """Dojo tutorial text (FPG 017, raw); its button icons are moved in overlay 000 later."""
    data, b.tut_icons = tutorial.build(tutorial.load(b.text("tutorial.txt")), b.menu_font)
    b.write_raw("017", data)
    print(f"tutorial: {len(data)} bytes, {len(b.tut_icons)} button icons")


def patch_roster(b):
    """Wrestler names: FPG 010 and its copy in 011 (overlay 005's copy is patched with the overlays)."""
    b.roster_rows = roster.encode(roster.load(b.text("wrestlers.tsv")))
    b.roster_orig = bytes(b.read("010"))
    for entry, at in roster.COPIES.items():
        buf = b.read(entry)
        roster.apply(buf, at, b.roster_rows, b.roster_orig)
        b.write(entry, buf)
    print(f"roster: {len(b.roster_rows)} wrestlers")


def patch_moves(b):
    """Move names (in 011, after its roster copy)."""
    buf = b.read("011")
    used = moves.apply(buf, moves.load(b.text("moves.tsv")))
    b.write("011", buf)
    print(f"moves: {used} of {moves.AREA[1] - moves.AREA[0]} bytes")


def patch_edit_records(b):
    """Edit-format wrestler records outside the roster (bonus edits, samples, story
    templates) and the bonus edit wrestlers' profiles."""
    b.edit_rows = editdata.load(b.text("edit_wrestlers.tsv"))
    n = used = 0
    for entry in ("013", "016", "127"):
        packed = entry == "127"
        buf = b.read(entry) if packed else b.read_raw(entry)
        n += editdata.apply({entry: buf}, b.edit_rows)
        if entry == "013":
            used = editdata.apply_profiles(buf, editdata.load_profiles(b.text("edit_profiles.txt")),
                                           b.menu_font)
        (b.write if packed else b.write_raw)(entry, buf)
    print(f"edit records: {n} outside the roster, profiles {used} bytes")


def patch_pocketstation_title(b):
    """PocketStation save title (FPG 014, full-width SJIS)."""
    buf = b.read("014")
    old, new = (t.encode("cp932") for t in POCKET_TITLE)
    if buf[4:68] != old or len(new) != 64:
        raise SystemExit("FPG 014: unexpected PocketStation save title")
    buf[4:68] = new
    b.write("014", buf)


def patch_images(b):
    """Images: <images>/handmade/ (in progress) and <images>/approved/, see docs/EDITING.md.
    They may outgrow their sector slot: the TOC is read at boot and fpgbin.pack moves
    later entries."""
    gfx.configure(images=b.args.images)
    gfx.apply(b.unpacked)


def append_tables(ov, tables):
    """Extra string tables at the overlay end, with code references repointed to them."""
    for strings, refs in tables:
        ptrs = []
        for text in strings:
            ptrs.append(OVERLAY_BASE + len(ov))
            ov += strtab.encode_en(text) + b"\0"
            ov += bytes((-len(ov)) % 4)
        table = OVERLAY_BASE + len(ov)
        ov += struct.pack(f"<{len(ptrs)}I", *ptrs)
        codepatch.repoint(ov, OVERLAY_BASE, [("c", lui, lo) for lui, lo in refs], table)


def patch_overlay(b, entry):
    """One code overlay: the menu tiling hook at its original end, its own data
    patches, its translated strings (relocated ones in a pool after the hook),
    code tweaks, and anything appended after the pool."""
    ov = bytes(b.read(entry))
    if entry in menu_vwf_patch.MENU_OVERLAYS:
        ov = menu_vwf_patch.append_hook(ov, b.exe, b.widths)
    ov = bytearray(ov)
    translate = entry in OVERLAY_TEXT and entry not in b.skip_text

    if entry == "000":
        tutorial.apply_icons(ov, OVERLAY_BASE, b.tut_icons)
    elif entry == "001":
        roster.patch_ov001(ov)
    elif entry == "002":
        if b.debug_menu:
            debugmenu.patch_ov002(ov)
        if b.args.route5:
            debugmenu.patch_route5(ov)
    elif entry == "004":
        editdata.apply({"004": ov}, b.edit_rows)
    elif entry == "005":
        roster.apply(ov, roster.OV005_AT, b.roster_rows, b.roster_orig)

    pool = b""
    if translate:
        txt, start, end = OVERLAY_TEXT[entry]
        if entry == "004":
            problems = skilledit.check(ov, strtab.parse(b.text(txt)), b.menu_font)
            if problems:
                raise SystemExit("Skill Edit:\n  " + "\n  ".join(problems))
            skilledit.apply_boxes(ov)
            moveedit.apply(ov, OVERLAY_BASE)   # button icons to the right edge
        pool, inplace, moved, problems = strtab.insert(ov, OVERLAY_BASE, start, end, b.text(txt),
                                                       OVERLAY_BASE + len(ov), b.select.get(entry))
        for p in problems:
            print(f"warning: {txt}: {p}")
        print(f"overlay {entry}: {inplace} strings in place, {moved} relocated ({len(pool)} bytes)")
    codepatch.patch_words(ov, OVERLAY_BASE, OVERLAY_CODE.get(entry, ()), f"overlay {entry}")
    ov += pool

    if entry == "002" and translate:
        script.patch_ov002_scene(ov, OVERLAY_BASE, b.text("ov002_scene.txt"), b.metrics)
    if entry == "004" and translate:
        one_icon = runpy.run_path(b.text("ov004_en.py"), {"MENU_FONT": b.menu_font})["MOVE_ONE_ICON"]
        moveedit.add_labels(ov, OVERLAY_BASE, one_icon, strtab.encode_en)
    if entry == "004" and not b.args.no_extra_parts:
        for note in hiddenparts.apply(ov, OVERLAY_BASE, strtab.encode_en):
            print(f"extra parts: {note}")
    append_tables(ov, OVERLAY_TABLES.get(entry, ()))

    if OVERLAY_BASE + len(ov) > OVERLAY_BSS.get(entry, OVERLAY_LIMIT):
        raise SystemExit(f"overlay {entry} ends at {OVERLAY_BASE + len(ov):#x}, into its BSS")
    b.write(entry, ov)


def patch_overlays(b):
    b.exe = read_disc_file(b.args.rom, "/SLPS_020.65")
    for entry in sorted(set(menu_vwf_patch.MENU_OVERLAYS) | set(OVERLAY_TEXT)):
        patch_overlay(b, entry)
    print("appended menu tiling hook to overlays " + ", ".join(menu_vwf_patch.MENU_OVERLAYS))
    if b.debug_menu:   # overlay 003: wire the move/animation editor into its test shell
        ov = b.read("003")
        debugmenu.patch_ov003(ov)
        b.write("003", ov)


def repack_fpg(b):
    """Repack FPG.BIN; it must fit the original file's space on the disc."""
    b.new_fpg = os.path.join(b.work, "FPG.new.BIN")
    fpgbin.pack(b.unpacked, b.new_fpg)
    if os.path.getsize(b.new_fpg) > len(b.fpg):
        raise SystemExit("FPG.BIN grew; it must fit its original disc allocation")
    with open(b.new_fpg, "ab") as f:  # keep the original size on disc
        f.write(b"\0" * (len(b.fpg) - os.path.getsize(b.new_fpg)))


def patch_exe(b):
    """The executable: menu renderer hook, strings, promotion names, edit records,
    the memory card save title, and the unlock / debug menu patches."""
    exe = bytearray(menu_vwf_patch.patch_exe(b.exe))
    roster.patch_exe(exe)   # name builder: "second part only" flag
    # EXE strings: no free space, so translated strings are repacked into
    # the area their Japanese originals used (tools/strtab.py, repack mode).
    body = exe[0x800:]
    _, inplace, moved, problems = strtab.insert(body, 0x80010000, *EXE_TEXT[1:],
                                                b.text(EXE_TEXT[0]), repack=True)
    if problems:
        raise SystemExit("EXE text:\n  " + "\n  ".join(problems))
    exe[0x800:] = body
    promos = runpy.run_path(b.text("exe_promotions.py"))
    for i, names in enumerate(promos["NAMES"]):
        for name, at, size in zip(names, (promos["FULL_AT"], promos["SHORT_AT"]),
                                  (promos["FULL_SIZE"], promos["SHORT_SIZE"])):
            data = strtab.encode_en(name)
            if len(data) >= size:
                raise SystemExit(f"promotion name {name!r} is longer than {size - 1} bytes")
            off = at + i * size - 0x80010000 + 0x800
            exe[off:off + size] = data + bytes(size - len(data))
    editdata.apply({"exe": exe}, b.edit_rows)
    # Memory card save title (SJIS, shown by the BIOS; 0x80017f94 copies it into the header)
    title_at = SAVE_TITLE[0] - 0x80010000 + 0x800
    if exe[title_at:title_at + len(SAVE_TITLE[1])] != SAVE_TITLE[1]:
        raise SystemExit("EXE: unexpected save title")
    title = SAVE_TITLE[2].encode("cp932")
    exe[title_at:title_at + SAVE_TITLE[3]] = title + bytes(SAVE_TITLE[3] - len(title))
    if not b.args.no_unlock:
        unlock.patch_exe(exe)
    if b.debug_menu:
        debugmenu.patch_exe(exe)
    b.exe = bytes(exe)
    print(f"EXE: {inplace} strings in place, {moved} repacked")


def write_image(b, out_bin):
    """A copy of the original image with FPG.BIN and the EXE written back in place."""
    shutil.copyfile(b.args.rom, out_bin)
    with open(out_bin, "r+b") as f:
        discpatch.patch_file(f, "/FPG.BIN", open(b.new_fpg, "rb").read())
        discpatch.patch_file(f, "/SLPS_020.65", b.exe)


STEPS = [unpack_fpg, patch_story, patch_menu_font, patch_tutorial, patch_roster, patch_moves,
         patch_edit_records, patch_pocketstation_title, patch_images, patch_overlays,
         repack_fpg, patch_exe]


def main(argv=None):
    args = parse_args(argv)
    out_name = output_name(args)
    os.makedirs(args.out_dir, exist_ok=True)
    out_bin = os.path.join(args.out_dir, out_name + ".bin")
    if os.path.abspath(out_bin) == os.path.abspath(args.rom):
        raise SystemExit("the output would overwrite the original image")
    if args.japanese:
        build_japanese(args, out_bin)
    else:
        storycheck.load_promotions(args.text)   # promotion names for the story width checks
        b = Build(args)
        for step in STEPS:
            step(b)
        write_image(b, out_bin)
    write_cue(args.out_dir, out_name)
    print("built", out_bin)


if __name__ == "__main__":
    main()
