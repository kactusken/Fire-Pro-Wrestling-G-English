# Tools

Everything is Python 3 and runs from the repository root or anywhere else. Every tool
with a command line has `--help`. Input and output paths are options. Their defaults
are relative to the repository (`extracted/`, `script/`, `text/`, `images/`, `review/`,
`docs/`); paths you pass are relative to your current folder. The defaults live in
[paths.py](paths.py).

Most tools that read game data expect the unpacked disc in `extracted/`, so run
`python3 tools/extract.py` once first. Only `edit.py`, `render.py` and `contact.py` (Pillow) and `mipsdis.py`
(capstone) need extra packages (`pip install -r requirements.txt`).

## Used by the build

`build.py` imports these. Most are libraries, and some also have a small command line
of their own.

| Tool | What it does |
|---|---|
| [discfs.py](discfs.py) | Reads files from a raw MODE2/2352 disc image (ISO 9660) |
| [discpatch.py](discpatch.py) | Writes files back into the image in place and regenerates EDC/ECC |
| [fpgbin.py](fpgbin.py) | Unpacks and repacks the FPG.BIN archive |
| [lzss.py](lzss.py) | The game's LZSS compression, both ways |
| [script.py](script.py) | Story script: extracts and inserts entries 130/131, the line-width checks, the story module's own scene block |
| [vwf_patch.py](vwf_patch.py) | Story text: the variable-width tiled font hook in overlay 002 |
| [font.py](font.py) | The story font (entry 128): unpacks glyphs, measures their ink, writes PNGs |
| [menu_vwf_patch.py](menu_vwf_patch.py) | Menu text: the tiling hook for the EXE's menu renderer |
| [menufont.py](menufont.py) | The menu font: proportional widths and extra Latin glyphs |
| [strtab.py](strtab.py) | Menu strings in code modules: finds, relocates and repoints them |
| [roster.py](roster.py) | Wrestler names into the three copies of the roster |
| [moves.py](moves.py) | Move names |
| [editdata.py](editdata.py) | Wrestler records outside the roster, and the edit-wrestler profiles |
| [skilledit.py](skilledit.py) | Skill Edit screen: layout fixes and fit checks |
| [moveedit.py](moveedit.py) | Move Edit screen: button icon positions and labels |
| [tutorial.py](tutorial.py) | Dojo tutorial text and its button icons |
| [gfx.py](gfx.py) | Images with text: the catalogue, export of the originals, import of the English |
| [pngread.py](pngread.py), [tim.py](tim.py) | PNG reading and PS1 TIM images |
| [unlock.py](unlock.py) | Everything unlocked from the start |
| [hiddenparts.py](hiddenparts.py) | Unused heads and body parts added to Wrestler Make |
| [debugmenu.py](debugmenu.py) | Restores the developer menu (debug builds only) |
| [mips_asm.py](mips_asm.py) | A small MIPS assembler for the hooks |
| [codepatch.py](codepatch.py) | Shared helpers for patching code: checked word patches, and reading and rewriting the address a `lui`/`addiu` pair loads |
| [paths.py](paths.py) | Default folder locations |

## Checking translations

| Tool | What it does |
|---|---|
| [storylint.py](storylint.py) | Checks the story script: missing English, leftover codes, Japanese in the English, speaker labels, line count and width |
| [storycheck.py](storycheck.py) | Lays out every story message exactly as the patched game draws it, with name codes expanded (`--long-names` for the worst case, `--png DIR` to see the problems) |
| [uilint.py](uilint.py) | Reports menu strings that are too wide for their windows |
| [test_vwf.py](test_vwf.py) | Runs the real story text hook in an emulated CPU and saves what it draws as a PNG |
| [test_menu_vwf.py](test_menu_vwf.py) | The same for the menu renderer and its hook |
| [mipsim.py](mipsim.py) | The small MIPS interpreter those two tests use |

## Translating

| Tool | What it does |
|---|---|
| [fakenames.py](fakenames.py) | The Fake Names variant: swaps the real names for the game's stand-ins (`build.py --fake-names`); run alone with `--diff` to review every change |
| [storyfill.py](storyfill.py) | Puts a draft translation into a scene, wrapping lines to the text box |
| [fill_text.py](fill_text.py) | Fills a menu text file's English from a Japanese → English table (`text/*_en.py`) |
| [edit.py](edit.py) | Image editing workflow: overview, sheets, check, approve ([docs/EDITING.md](../docs/EDITING.md)) |
| [render.py](render.py) | Draws English example versions of the text images |
| [contact.py](contact.py) | Puts every image in the game on labelled contact sheets |

## Research

| Tool | What it does |
|---|---|
| [extract.py](extract.py) | Unpacks the disc into `extracted/` |
| [storyflow.py](storyflow.py) | Decodes the story bytecode into branches, choices, stat changes and matches (JSON) |
| [storymap.py](storymap.py) | Builds the interactive route map, `docs/route-map/index.html`, from storyflow's data and `docs/story_titles.tsv` |
| [storybattles.py](storybattles.py) | Decodes the story battle table into `docs/story_battles.tsv` |
| [mipsdis.py](mipsdis.py) | Disassembler with reference and call search (needs capstone) |
| [sjisscan.py](sjisscan.py) | Finds Shift-JIS text in binary files |
| [bss_scan.py](bss_scan.py) | Estimates how far past its end a code module's memory use reaches |
| [bs.py](bs.py) | Decodes the BS (MDEC) still images used for story backgrounds |
| [unused_art.py](unused_art.py) | Exports the unused illustrations in FPG 275 |
| [gdbrsp.py](gdbrsp.py) | A minimal GDB remote client for DuckStation's GDB server: dump RAM, show registers, run to an address |
