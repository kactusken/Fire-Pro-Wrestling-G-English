# Editing images

Every image with Japanese text is listed in `images/graphics.csv`: its name, where it lives,
the Japanese, the English to draw and its status (`todo`, `done` = approved, `keep` = stays
Japanese). The image tools need Pillow: `python3 -m pip install -r requirements.txt` (see
[BUILDING.md](BUILDING.md#what-you-need); if you install it into a virtual environment, activate
that first, and the commands below work as written).
`build.py` itself still runs with plain `python3`. Run `python3 tools/extract.py` once first:
the tools read the original images from `extracted/`.

The example renders use the Ubuntu font family (`fonts-ubuntu` on Debian/Ubuntu, or from
[design.ubuntu.com/font](https://design.ubuntu.com/font)). If it is somewhere other than
`/usr/share/fonts/truetype/ubuntu/`, pass `--font-dir PATH` to `render.py` and `edit.py`.
All three tools also take `--images`, `--extracted` and `--review` to use other folders.

## 0. Browse every image in the game

```sh
python3 tools/contact.py     # review/contact-sheets/sheet_NNN.png, review/all-images/
```

All 249 images on the disc (TIMs, the story backgrounds and portraits, the VRAM sheets split
into texture pages) are drawn on contact sheets, each labelled with an id like `277_00p5` or
`143_00` (`entry_number`, plus `p<k>` for a texture page or `c` for the victory captions).
Magenta is transparent; `x7` means the same image appears 7 times. `review/all-images/index.csv`
says where each id lives. To add an image to the workflow below, give its id and the part
you want; it then gets a row in `graphics.csv`.

## 1. See the catalogued images

```sh
python3 tools/gfx.py export                 # review/japanese/<image>.png (the originals)
python3 tools/render.py            # review/english/<image>.png (English examples)
python3 tools/edit.py overview     # review/overview/overview_000.png
```

The overview shows each image as **Japanese | English** with its name and English text. The
English side is the first that exists of:

| Tag | What it is | In the build? |
|---|---|---|
| HAND | your work in progress, `images/handmade/<image>.png` | yes |
| DONE | approved, `images/approved/<image>.png` | yes |
| EXAMPLE | the automatic example, `review/english/<image>.png` | no |
| KEEP | stays Japanese | no |

The examples are drawn in the original's own palette and style: the same background, the
same colour for each text row (so gradients carry over) and the same outline colour. Fonts are
Ubuntu (Condensed). Change the wording in the `english` column of `graphics.csv` (`" / "`
forces a line break) and run `render.py <image>` again. `edit.py overview mode` only shows
images whose name, Japanese or English contains "mode".

## 2. Put the ones you want on a sheet

```sh
python3 tools/edit.py sheet start modes "mode_*"
```

This writes `images/handmade/sheets/modes.png`, with each image as **Japanese | English** at
its original size. Edit the **right-hand** image of each pair. Names can be listed with
spaces or commas, and wildcards work (`"mode_*"`, `"victory_*"`, `"label_*"`).

- Keep within each rectangle. The Japanese side, labels and gaps are not read back, so you
  can scribble notes there.
- **Magenta** (255,0,255) is transparent. Paint magenta to clear pixels.
- Any colours work: they are snapped to the image's game palette (16 colours). The palette
  entries are listed in each `review/japanese/<image>.png`. Drawing with exactly those colours
  gives the most predictable result.

## 3. Check

```sh
python3 tools/edit.py sheet check modes
```

This lists which images you changed and writes `modes_check.png`: the sheet as the game will
show it, after palette snapping.

## 4. Try it in the game (optional)

```sh
python3 tools/edit.py sheet split modes      # changed images -> images/handmade/
python3 build.py
```

Hand-made images are in the build straight away, so you can look at them in DuckStation before
approving.

## 5. Approve

```sh
python3 tools/edit.py sheet approve modes          # changed images only
python3 tools/edit.py sheet approve modes --all    # also the ones left as the example
```

Approving snaps each image to the game palette, saves it to `images/approved/`, marks it `done`
in `graphics.csv` and removes the sheet. `--all` approves untouched examples too, for when the
example is already good enough.

## Single images

```sh
python3 tools/edit.py start label_name    # images/handmade/label_name.png (+ _japanese.png)
python3 tools/edit.py check label_name    # label_name_check.png: original above, yours below
python3 tools/edit.py approve label_name
python3 tools/edit.py reset label_name    # undo: back to Japanese (removes hand edit and approval)
python3 tools/edit.py list victory        # find images
```

`start` begins from the current English (approved, else the example). Keep the same size.

## Notes on the images

- **Mode select** (`mode_*`, 128x16): the game also draws these with a purple palette and a grey
  one (locked modes). Keep the original's idea of light-to-dark shading so those still look right.
- **Victory captions** (`victory_*`, 128x48): one edit is written into all seven victory screens
  (FPG 279-285).
- **Select labels** (`label_*`, 40x16): yellow text (colour 0, lighter yellows for highlights)
  with a dark shadow (14) on a transparent background (15, magenta on sheets). The game draws a
  blue gradient box behind them. Their palette is in the 277 sheet at row 195, x 320.
- `absent`, `voice_1`, `voice_2`, `finisher_tag`: their palettes aren't known yet (grey stand-in),
  and so far no one has seen where they appear in game.
- `title_screen` cannot be imported yet (it is a TIM inside entry 012). It and `logo_small`
  are marked `keep` for now.
- `images/approved/` is part of the repository. `images/handmade/` and `review/` are not: they
  hold work in progress and generated previews. `make_patches.py` refuses to run while
  `images/handmade/` has images in it, so unfinished work can't slip into a release.

## Image format rules

- Keep the same pixel size and **indexed colour with the same palette**. The game stores
  palette indices, not RGB. The sheet workflow above snaps colours for you. If you edit
  outside it, use indexed mode (GIMP: Image > Mode > Indexed with a custom palette; Aseprite
  and GraphicsGale keep indexed mode).
- Palette index 0 (colour 0x0000) is transparent, except in the select labels (see above).
- The victory captions are 4bpp with their own 16-colour palette, the same in all seven
  victory screens. The photo's 256-colour palette isn't involved.
- Where every image lives in the archive, and which images have no text, is in
  [TECHNICAL.md](TECHNICAL.md#images).
