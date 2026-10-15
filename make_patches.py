#!/usr/bin/env python3
"""Build the release variants and make an xdelta patch for each.

    python3 make_patches.py [--version v1.0] [--rom PATH] [--out-dir PATH]

For each variant in VARIANTS this runs build.py, makes an xdelta3 patch from the
original image to the result, applies it again to check that it reproduces the
build exactly, and writes a .cue to go with it. Everything goes in a zip for the
release, with checksums and short instructions.

Needs the xdelta3 program (Debian/Ubuntu: apt install xdelta3; Windows/macOS:
https://github.com/jmacd/xdelta-gpl/releases), or give its path with --xdelta.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import textwrap
import zipfile
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import paths  # noqa: E402

# The disc the patches apply to: Fire Pro Wrestling G (Japan), SLPS-02065, one .bin.
SOURCE = {"size": 303368016, "crc32": "d9b6b206", "md5": "82a63356577f475b53e04067e9f75bbf",
          "sha1": "8dbba0ddad40f4b669a88b688417d67c21eb792d"}

# (output name, build.py options, description)
VARIANTS = [
    ("Fire Pro Wrestling G (English)", ["--no-unlock", "--no-extra-parts"],
     "English translation. Everything else as in the original game: wrestlers and "
     "extras unlock as you play."),
    ("Fire Pro Wrestling G (English) (All Unlocked)", [],
     "English translation with everything unlocked from the start (all wrestlers, "
     "Edit Ranking rewards, story-clear extras) and the unused heads and body "
     "parts added to Wrestler Make."),
    ("Fire Pro Wrestling G (Japan) (All Unlocked)", ["--japanese"],
     "The original Japanese game with everything unlocked from the start."),
]

APPLY_HELP = """\
How to apply
------------
You need your own copy of the original Japanese disc as a .bin/.cue image:
  Fire Pro Wrestling G (Japan), SLPS-02065 (not the Spike Library reissue)
  {size} bytes, CRC32 {crc32}, MD5 {md5}
  SHA-1 {sha1}

1. Pick one of the .xdelta patches below.
2. Apply it to the original .bin with any xdelta tool:
     - Rom Patcher JS (in a web browser): https://www.marcrobledo.com/RomPatcher.js/
     - Delta Patcher (Windows, macOS, Linux)
     - command line: xdelta3 -d -s "original.bin" "patch.xdelta" "patched.bin"
3. Name the patched .bin as the patch's .cue file expects (the patch name with
   .bin), keep the two together, and load the .cue in your emulator.

Patches
-------
"""


def checksums(path):
    sha1, md5, crc = hashlib.sha1(), hashlib.md5(), 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            sha1.update(chunk)
            md5.update(chunk)
            crc = zlib.crc32(chunk, crc)
    return {"size": os.path.getsize(path), "crc32": f"{crc:08x}", "md5": md5.hexdigest(),
            "sha1": sha1.hexdigest()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 2)[2])
    paths.add(ap, "--rom", paths.ROM, "original Japanese disc image (.bin)")
    paths.add(ap, "--out-dir", paths.RELEASE, "where the patches and zip go")
    paths.add(ap, "--build-dir", os.path.join(paths.BUILD, "release"), "where the patched images are built")
    ap.add_argument("--version", default="dev", help="release name used in the zip name (default: dev)")
    ap.add_argument("--xdelta", default="xdelta3", metavar="PROGRAM", help="xdelta3 program (default: xdelta3)")
    paths.add(ap, "--images", paths.IMAGES, "image catalogue folder")
    ap.add_argument("--any-rom", action="store_true",
                    help="skip the check that --rom is the expected original image")
    ap.add_argument("--allow-handmade", action="store_true",
                    help="build even if <images>/handmade/ holds unapproved images")
    args = ap.parse_args(argv)

    handmade = os.path.join(args.images, "handmade")
    wip = sorted(f for f in os.listdir(handmade) if f.endswith(".png")) if os.path.isdir(handmade) else []
    if wip and not args.allow_handmade:
        raise SystemExit(f"{handmade} has unapproved images, which the build would include:\n  "
                         + ", ".join(wip) + "\napprove or remove them (docs/EDITING.md), or pass --allow-handmade")

    if not shutil.which(args.xdelta):
        raise SystemExit(f"{args.xdelta} not found; install xdelta3 or pass --xdelta PATH")
    print(f"checking {args.rom}")
    source = checksums(args.rom)
    if source != SOURCE and not args.any_rom:
        raise SystemExit(f"{args.rom} is not the expected original image:\n  got      {source}\n"
                         f"  expected {SOURCE}\n(--any-rom makes patches for it anyway)")

    os.makedirs(args.out_dir, exist_ok=True)
    notes = APPLY_HELP.format(**source)
    files = []
    for name, options, description in VARIANTS:
        print(f"\n=== {name}")
        subprocess.run([sys.executable, os.path.join(ROOT, "build.py"), "--rom", args.rom,
                        "--out-dir", args.build_dir, "--images", args.images, "--name", name, *options], check=True)
        built = os.path.join(args.build_dir, name + ".bin")
        patch = os.path.join(args.out_dir, name + ".xdelta")
        # -S none: no secondary compression, which some patchers (Rom Patcher JS) can't read
        subprocess.run([args.xdelta, "-e", "-9", "-S", "none", "-f", "-s", args.rom, built, patch],
                       check=True)
        check = built + ".check"
        subprocess.run([args.xdelta, "-d", "-f", "-s", args.rom, patch, check], check=True)
        target = checksums(built)
        if checksums(check) != target:
            raise SystemExit(f"{patch} does not reproduce {built}")
        os.remove(check)
        shutil.copyfile(os.path.join(args.build_dir, name + ".cue"),
                        os.path.join(args.out_dir, name + ".cue"))
        files += [name + ".xdelta", name + ".cue"]
        print(f"{patch}: {os.path.getsize(patch)} bytes, verified")
        notes += (f"\n{name}.xdelta\n{textwrap.fill(description, 78, initial_indent='  ', subsequent_indent='  ')}\n"
                  f"  Result: {target['size']} bytes, CRC32 {target['crc32']}, SHA-1 {target['sha1']}\n")

    notes_path = os.path.join(args.out_dir, "README.txt")
    with open(notes_path, "w", newline="\r\n") as f:
        f.write(f"Fire Pro Wrestling G English translation - {args.version}\n\n{notes}")
    zip_path = os.path.join(args.out_dir, f"Fire Pro Wrestling G English Patch {args.version}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(notes_path, "README.txt")
        for f in files:
            z.write(os.path.join(args.out_dir, f), f)
    print(f"\n{zip_path}: {os.path.getsize(zip_path)} bytes")


if __name__ == "__main__":
    main()
