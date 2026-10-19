# Building the patch

This explains how to build the patched game and the release patches from the
original disc, and how the repository is laid out.

## What you need

- **Python 3.8 or newer.** `build.py` and `make_patches.py` use only the standard library.
- **The original disc image**, `Fire Pro Wrestling G (Japan).bin` (SLPS-02065, CRC32
  `d9b6b206`), with its `.cue`. It isn't included. Put it in `rom/` or pass `--rom`.
- **xdelta3**, only for making patches (`apt install xdelta3`, or a build from
  [the xdelta releases](https://github.com/jmacd/xdelta-gpl/releases)).
- **Optional:** Pillow for the image-editing tools, and capstone for the disassembler:

  ```sh
  python3 -m pip install -r requirements.txt
  ```

  To keep them out of your system Python, use a virtual environment: `python3 -m venv .venv`,
  then activate it (`source .venv/bin/activate`; on Windows `.venv\Scripts\activate`) before
  installing and before running the tools. `.venv/` is already ignored by git.

All the tools work on Linux, macOS and Windows. The examples use `python3`; on Windows
use `py` or `python`.

## Building

```sh
python3 build.py
```

This reads `rom/Fire Pro Wrestling G (Japan).bin` and writes
`build/Fire Pro Wrestling G (English).bin` and `.cue`. It takes about half a minute.
The original image is never modified.

| Option | Effect |
|---|---|
| *(none)* | English, everything unlocked, extra Wrestler Make parts |
| `--no-unlock` | Keep the original unlock progression |
| `--no-extra-parts` | Leave out the unused heads and body parts |
| `--fake-names` | Use the game's own stand-in names instead of the real ones (see [TRANSLATION.md](TRANSLATION.md#fake-names)) |
| `--japanese` | Keep the Japanese text; apply only the unlock patch |
| `--rom PATH` | The original image (default `rom/Fire Pro Wrestling G (Japan).bin`) |
| `--out-dir PATH` | Output folder (default `build/`; work files go in its `work/`) |
| `--script PATH`, `--text PATH`, `--images PATH` | Use other translation folders (default `script/`, `text/`, `images/`) |
| `--name NAME` | Output file name (default: derived from the options) |

Developer options, not for release builds:

| Option | Effect |
|---|---|
| `--debug-menu` | Restores the developer mode-select menu: hold **Select** and press **Start** on the title screen. Its text goes to the emulator's TTY log. See [HIDDEN_CONTENT.md](HIDDEN_CONTENT.md#developer-menu-and-debug-leftovers). |
| `--route5` | Debug menu, plus the graduation offer always gives the cut New Japan/Liger scene (debug mode 4, scene 3) |
| `--no-text 001,004` | Leave those overlays' menu strings in Japanese, to narrow down a text bug |
| `--only 004:8005b690-8005bbe0` | Translate only the strings in that address range of an overlay (`004:!lo-hi` translates everything else) |

As defaults, paths are relative to the repository, so you can run the tools from any
folder. Paths you give on the command line are relative to your current folder. All the
tools in `tools/` follow the same rule.

The build is reproducible: the same inputs always give a byte-identical image.

## Making the release patches

```sh
python3 make_patches.py --version v0.2
```

This builds the five release variants into `build/release/`, makes an xdelta patch for
each against the original image, applies every patch again to check that it gives
exactly the built image, and writes everything to `release/`:

- `<variant>.xdelta` and `<variant>.cue` for each variant,
- `README.txt` with instructions and checksums,
- `Fire Pro Wrestling G English Patch v0.2.zip` containing all of the above, ready to
  attach to a GitHub release.

The variants are listed in `VARIANTS` at the top of `make_patches.py`. It first checks that
`--rom` is the expected disc and stops if it isn't (`--any-rom` skips the check). Patches
are made without xdelta's secondary compression so that browser patchers can read them.

## Extracting the disc for the other tools

`build.py` reads the disc image directly. The checking and research tools work on
unpacked files instead:

```sh
python3 tools/extract.py      # -> extracted/
```

This writes the executable `SLPS_020.65`, `SYSTEM.CNF`, `FPG.BIN`, every archive entry as
stored (`extracted/fpg/NNN.bin`), and the decompressed code overlays
(`extracted/ovl/000.bin` … `005.bin`).

## Checking your changes

Run these after editing text. `build.py` repeats the most important checks and stops on
errors, but these explain problems in more detail.

```sh
python3 tools/storylint.py               # story: missing English, leftover codes, speaker labels, line counts and widths
python3 tools/storycheck.py              # story: lays out every message exactly as the patched game draws it
python3 tools/uilint.py text/ov001.txt   # menus: strings whose English needs more room than the Japanese
```

`storylint.py` should report 0 problems (it exits with status 1 otherwise). `storycheck.py` flags lines between 440 and 455 px
(still visible, but tight) and errors past 455 px. `uilint.py` is a guide, not a pass/fail
test: a longer string is fine wherever its window has room, so check the ones it lists in
the game.

## Running the tests

```sh
python3 -m unittest discover -s tests -t .
```

The tests use only the standard library and take a few seconds. Most need nothing but this
repository:

- **Unit tests** cover compression, code patching, the assembler and CPU simulator, the
  text file formats, the archive, PNG and disc-sector code, and the build options.
- **Data checks** cover the translation files themselves. Every scene is present and passes
  the lint, menu strings encode, names fit their fields, tutorial icons match, approved
  images match the catalogue, and documentation links resolve.

More tests run once `extracted/` exists (`python3 tools/extract.py`). They check that the
compressor and archive packer reproduce the game's files, that the Japanese in `script/`
matches the disc, the story text widths, and that the layout model agrees with the real text
hook running in the simulator. `FPWG_SLOW=1` also builds the game twice to check that builds
are reproducible (about a minute).

The code is linted with [ruff](https://docs.astral.sh/ruff/) (`pip install ruff`, then
`ruff check .`; the settings are in `ruff.toml`). GitHub runs the lint and the tests that need
no game data on every push (`.github/workflows/tests.yml`).

See [tools/README.md](../tools/README.md) for every tool and its options, and
[TRANSLATION.md](TRANSLATION.md) for the text formats.

## Repository layout

| Path | Contents |
|---|---|
| `build.py` | Builds a patched disc image |
| `make_patches.py` | Builds the release variants and their xdelta patches |
| `script/NNN.txt` | The story script, one file per scene (522), Japanese and English side by side |
| `text/` | Everything else: menu and system strings per code module, the roster, move names, edit wrestlers and profiles, the tutorial, promotion names |
| `images/graphics.csv` | Catalogue of in-game images that contain text |
| `images/approved/` | Finished English images, used by the build |
| `images/handmade/` | Work in progress (not tracked by git; also used by the build) |
| `tools/` | The patching code, checks, and research tools ([tools/README.md](../tools/README.md)) |
| `tests/` | Unit tests and data checks (`python3 -m unittest discover -s tests -t .`) |
| `docs/` | Documentation, plus reference data: the story name table, scene titles, the battle table, and the route map |
| `rom/` | Your original disc image (not tracked) |
| `extracted/`, `build/`, `release/`, `review/` | Generated output (not tracked) |
