# Fire Pro Wrestling G — how the translation patches the game

This document describes what `build.py` changes in the game and why, one section per patch,
with the tool that makes each change and the limits a contributor has to respect. The formats
these patches work on (disc, FPG.BIN, compression, records, renderers) are described in
[TECHNICAL.md](TECHNICAL.md). Hidden content that the unlock and debug patches expose is in
[HIDDEN_CONTENT.md](HIDDEN_CONTENT.md). For a gentler overview, start with
[HOW_IT_WORKS.md](HOW_IT_WORKS.md).

Conventions are the same as in TECHNICAL.md: addresses are PlayStation RAM, "ov2" is code
overlay 002, "FPG 131" is entry 131 of FPG.BIN.

## Contents
1. [Build overview](#build-overview)
2. [Story text: variable-width font](#story-text-variable-width-font)
3. [Story script](#story-script)
4. [Overlay 002's built-in scene](#overlay-002s-built-in-scene)
5. [Menu text: tiling hook and string pools](#menu-text-tiling-hook-and-string-pools)
6. [Menu font](#menu-font)
7. [Overlay code tweaks](#overlay-code-tweaks)
8. [EXE strings](#exe-strings)
9. [Wrestler names, moves, edit records and profiles](#wrestler-names-moves-edit-records-and-profiles)
10. [Skill Edit and Move Edit](#skill-edit-and-move-edit)
11. [Dojo tutorial](#dojo-tutorial)
12. [Memory card titles](#memory-card-titles)
13. [Images](#images)
14. [Unlock everything](#unlock-everything)
15. [Extra Wrestler Make parts](#extra-wrestler-make-parts)
16. [Move fixes](#move-fixes)
17. [Debug menu and route 5](#debug-menu-and-route-5)
18. [What stays Japanese](#what-stays-japanese)
19. [Limits to respect](#limits-to-respect)
20. [Checking tools](#checking-tools)

---

## Build overview

`build.py` starts from a copy of the original image and:

1. reads FPG.BIN and the EXE from the disc (`tools/discfs.py`) and unpacks FPG.BIN
   (`tools/fpgbin.py`);
2. changes the unpacked entries and the EXE as described below, recompressing entries with
   `tools/lzss.py`. Each change is one step function in `build.py`, run in the order of its
   `STEPS` list: story, menu font, tutorial, roster, moves, edit records, PocketStation title,
   images, the code overlays (`patch_overlay`, one call per overlay), then the EXE;
3. repacks FPG.BIN and writes it and the EXE back into the image in place
   (`tools/discpatch.py`, which regenerates EDC/ECC and updates the directory sizes).

**FPG.BIN must not grow.** It ends exactly where FPG.XA starts. Individual entries may grow,
though: the EXE reads the table of contents from disc at boot, so `fpgbin.pack` lays the entries
out back to back and later entries simply move. The build stops if the whole archive is larger
than the original, and pads it to the original size otherwise. The compressor uses lazy matching
and comes out slightly smaller than the original tool, which leaves room for growth.

The EXE has no free space and cannot grow: translated EXE strings are repacked into the space
the Japanese used (see [EXE strings](#exe-strings)), and new EXE code goes into dead code.

Options:

| Option | Effect |
|---|---|
| (none) | English, everything unlocked, extra Wrestler Make parts |
| `--no-unlock` | Leave out [Unlock everything](#unlock-everything) |
| `--no-extra-parts` | Leave out [Extra Wrestler Make parts](#extra-wrestler-make-parts) |
| `--fake-names` | The game's own stand-in names instead of the real ones: `tools/fakenames.py` writes a copy of the text with the names swapped (in `work/fake-names/`) and the build reads that |
| `--japanese` | Japanese text; only the unlock patch (combine with `--no-unlock` for an unchanged copy) |
| `--debug-menu`, `--route5` | [Debug menu and route 5](#debug-menu-and-route-5); not for release |
| `--no-text 004`, `--only 004:lo-hi` | Diagnostic builds: leave an overlay's strings (or all but a range) in Japanese, to find a string that breaks a screen |

`make_patches.py` builds the release variants and makes the xdelta patches.

---

## Story text: variable-width font

Tool: `tools/vwf_patch.py`; always applied. Tested offline by `tools/test_vwf.py`, which runs the
patched code in `tools/mipsim.py` (a small R3000 simulator) and renders the result.

The story renderer only draws two-byte Shift-JIS and line breaks. On the original game, a line
of ASCII came out blank and ASCII after full-width text was dropped; full-width Latin letters do
render, but on a 20 px fixed pitch that fits only about 21 letters per line.

The patch hooks the single-byte branch at 0x8006368C. For bytes 0x21–0x7E it unpacks the font's
matching full-width glyph and blends its ink columns into a 20-pixel tile at the exact pen
position, starting a new slot only when a tile is full. A space only advances the pen. A line of
English therefore uses about as many slots as a line of Japanese. Finished tiles are uploaded
through the game's own per-frame staging list.

- The hook, a metrics table and its buffers are appended after the end of overlay 002
  (0x80077BE0). The space up to the heap (0x80092000) is free while overlay 002 is loaded, and
  the loader decompresses from a sector buffer on the stack, so the larger overlay loads safely.
- Glyph sprites are widened from 19 to 20 pixels (slot init 0x80062964) so tile edges are not
  clipped.
- Fast-forward runs up to 8 typewriter steps per frame (loops at 0x8005EC48 / 0x8005ED18 /
  0x8005EE04); the patch lowers that to 4, so the 32-entry staging list cannot overflow (one
  letter can stage up to 6 entries).
- Verified in game: English renders cleanly, long messages no longer erase themselves,
  fast-forward works, and Japanese text still renders.

## Story script

Tool: `tools/script.py` (`insert`); text in `script/NNN.txt`, one file per scene.

Each message has `JP` lines (reference only) and `EN` lines; a message without `EN` lines is
inserted unchanged. The tool rebuilds every scene block of FPG 131 with the English messages and
rewrites the scene index in FPG 130. Scenes keep starting on sector boundaries. Only 633 KB of
FPG 131's 1.25 MB is used by the Japanese, so there is plenty of room for longer English.

- Inline codes (`#MS`, `#MF`, `#PSnn`, `#PLnn`; see TECHNICAL.md) are kept as they are. `#W..nnn`
  codes are replaced by the plain English names in the script; `tools/storylint.py` reports any
  left over.
- The visible line width is about 455 pixels; the build warns over 440 (`script.LINE_LIMIT`,
  `script.check_message`). A message holds a speaker line plus 3 text lines.
- Lines containing name codes are measured after expanding the codes the way the game does
  (`tools/storycheck.py`'s model). Lines holding `#MF` need to leave about 150 pixels for it.
- Messages that are never shown (see HIDDEN_CONTENT.md) are translated anyway.

## Overlay 002's built-in scene

Tool: `script.patch_ov002_scene`; text in `text/ov002_scene.txt`.

Overlay 002 holds one scene block of its own at 0x80064B98 (header 0x0004, text table at +0x64):
the save prompt and the pre-match "Ready for the match?" choice. It is loaded through two
`lui`/`addiu` pairs (0x8005DB74/78 and 0x8005DBC0/C4). The build rebuilds the block from the text
file, appends it to the overlay and repoints both pairs. The old copy stays in place, unused.

## Menu text: tiling hook and string pools

Tools: `tools/menu_vwf_patch.py` (hook), `tools/strtab.py` (strings); text in `text/ov001.txt`,
`ov002.txt`, `ov004.txt`, `ov005.txt`.

**Hook.** The menu renderer (EXE 0x80015F5C) draws a whole string at once, one 12-pixel cell
("slot") per glyph, and each window has a fixed cell budget sized for Japanese, so English was
cut off after a few letters. The renderer's ASCII path calls the glyph draw 0x80015C90 at
0x80016094; that call now goes to a hook. At the first letter of an ASCII run the hook reads
ahead through the string, lets the game draw each letter into a private scratch cell (so shadow
and outline effects still apply), blends the letters into 12-pixel tiles at their pen positions,
and copies each finished tile into the staging buffer exactly once. Only finished tiles are
written, because the GPU can read the staging buffer while the next frame is drawn. Tiles past
the window's budget are dropped, so text that is too long is cut off instead of overwriting the
next window's cells (or running past the cell pool, which crashes the game). Spaces narrow from
8 to 4 pixels (0x80016108).

- The hook is assembled at the original end of each overlay that uses the menu text API (000,
  001, 004, 005). The renderer's ASCII branch (0x80016058) looks up the resident overlay's end
  in the EXE table at 0x80010000 (indexed by the overlay id word at 0x8005A718) and calls it.
- The cell counter 0x800167D0 (used to size windows automatically, EXE 0x80017424) counted one
  cell per ASCII letter, which doubled windows on English screens and overran the cell pool. Its
  non-SJIS case (0x80016830) now calls a measuring routine in the same hook block.

**Strings.** `strtab.py` finds each module's NUL-terminated strings and their references
(aligned pointer words, and `lui`/`addiu`-style pairs). A translated string that fits its
original slot (string plus NUL padding up to the next string) is written in place; otherwise it
goes into a string pool appended after the hook, and every reference is repointed. A code
reference is only repointed when its `lui` serves that string alone; otherwise the English must
fit in place.

- Text file format: `@ address len=N refs=...`, then `JP` and `EN` lines. Entries can be added
  by hand for strings the scanner missed. Check a hand-added address against a real reference
  first: 0x8005D008 in overlay 004 looks like a string start but is the last entry of the jump
  table at 0x8005CFF8; the string is 0x8005D00C.
- Overlay 004's rodata has jump tables right before some strings, and the scanner merges those
  into junk "strings". Leave those without `EN`.
- Encoding: ASCII letters, digits and most punctuation stay single bytes (the renderer maps
  0x28–0x7E to full-width glyphs). `!"#$%&'` are written as full-width Shift-JIS except inside
  control codes (`#x12,` pen moves, `%d` formats). `\n` is a line break.
- Overlay 002's strings (speaker names for the story character list at 0x8005FB2C, the
  `No.%03d` format, the copyright line) use the same mechanism; their pool goes after the story
  VWF code.
- An overlay's pool must stay below the first BSS address it uses past its end
  (`build.OVERLAY_BSS`: ov1 0x80090000, ov4 and ov5 0x80080000; found with
  `tools/bss_scan.py`). The build checks this.

## Menu font

Tool: `tools/menufont.py`; always applied to FPG 009 and its copy in FPG 011 (+0x18).

The font's width table gave Latin letters a full 12-pixel cell. The patch sets each to its ink
width plus a gap and redraws a few glyphs to remove blank columns.

## Overlay code tweaks

Defined in `build.py` (`OVERLAY_CODE`, `OVERLAY_TABLES`); each checks the original word first.

- Match setup (ov1): labels are centred in a 108-pixel field (ctx+0x2E, used by the EXE wrapper
  0x80016CF8); 120 moves them 6 pixels right so the longer labels clear the window border
  (0x8005FE28, 0x8005FFA4). The Referee value field grows from 256 to 268 (0x8006053C); names up
  to about 75 pixels fit, so referees show as "T. Hattori", "J. Higuchi", "Soranaka", "T. Tanabe".
- Team battle positions (Lead … Captain): boxes grow from 2 to 5 cells (0x80068340, 0x80068384)
  and the team screen's cell pool grows to match (0x800682AC, 58 → 73; these pools were sized
  exactly). The VS team screen has 2-cell tiles, so it gets its own table of short labels
  `#1`–`#5` (repointed at 0x8006A0C4/CC and 0x8006A144/48).
- Select-screen birth date: 0x80087920 appends 年/月/日 to the numbers; they become `／`, `／` and
  end of string (1971／ 9／23).
- Option boxes (ov1 menu table 0x80089688): line windows grow from 12 to 16 cells (0x80088040)
  and the box pool from 72 to 88 (0x80087F5C), so "One Night Tournament" fits.
- `roster.patch_ov001` makes overlay 001's own name builder honour the "second part only" flag
  (see below).

## EXE strings

Tool: `strtab.insert(..., repack=True)`; text in `text/exe.txt` (area 0x800103B0–0x80010B34).

The EXE has no room for a pool. In repack mode, every translated string whose references can all
be repointed gives up its slot; neighbouring slots merge, and the strings are packed back into
them (largest first, 4-byte aligned). Untranslated ASCII strings reached only by pointers move
too. The area starts at 0x800103B0 (DQ Loss/Win) and ends before a jump table.

Promotion names (15 full names of 26 bytes at EXE 0x80049054 and 15 short names of 14 bytes at
0x800491DC) are written from `text/exe_promotions.py`.

## Wrestler names, moves, edit records and profiles

- **Roster** (`tools/roster.py`, `text/wrestlers.csv`): written to all three copies (FPG 010,
  FPG 011 +0x1046C, overlay 005 0x8006B3B8; overlay 005's extra 195th record is left alone).
  Field sizes are fixed (short name 14 bytes, second part 20, nickname 26); writing a longer
  nickname overwrites height, weight and birth data. A patch to the EXE name builder 0x80018430
  adds flag bit 0x20, "second part only": the list shows the short name and the full name is the
  second part alone (at most 18 bytes). The game never sets that bit, so player-made names are
  unaffected. Overlay 001's builder (0x800771BC) copies fields in 2-byte steps, so fields are
  padded to an even length with 0x01, which the menu renderer skips.
- **Moves** (`tools/moves.py`, `text/moves.csv`): the 1,592-entry name table in FPG 011 is
  rewritten freely because the EXE always goes through it: identical names share one copy and a
  name that ends a longer one points into it. Strings are laid out longest first, ties in byte
  order, so builds are reproducible.
- **Edit-format records outside the roster** (`tools/editdata.py`, `text/edit_wrestlers.csv`):
  the 30 bonus edit wrestlers in FPG 013 (0x4E28), the sample wrestler and Coach Yamamoto in
  FPG 016, Sakagami's four story templates in FPG 127, the new-wrestler default in overlay 004
  (0x800755E8) and the story hero's default in the EXE (0x8004980C). Custom finisher names
  (+0x1C8) stay under 28 bytes, because overlay 001 copies only that much.
- **Profiles** of the bonus wrestlers (`text/edit_profiles.txt`, FPG 013 +0x8A28), shown in
  Edit Ranking's Fight list: a fixed 54-cell window that wraps at x 308 and shows 3 lines;
  `editdata.py` checks the cell count and keeps each line within 195 pixels.

## Skill Edit and Move Edit

- **Skill Edit** (`tools/skilledit.py`): the screen's 378-cell pool has no bounds check and
  opens on top of the Edit menu, so there is almost no headroom; the first English labels crashed
  it. The patch shrinks value boxes whose English options are shorter (letter grades C–A need one
  cell) and spends those cells on clearer labels. The build checks that every option fits its box
  and that any 7 consecutive rows (6 visible plus one scrolling in) need no more cells than the
  Japanese did.
- **Move Edit** (`tools/moveedit.py`): the button icons beside the move-slot labels are sprites
  from the table at 0x80079B80. The patch moves every row's icons to a common right edge (x 140)
  and pads the labels (`#xN,` gaps) to end just before them. `text/ov004_en.py` holds the labels
  for slots with one icon.
- Any change to the Move Edit lists must patch both the normal set (0x80078C60) and the level-9
  set (0x800791B8): the unlocked build always uses the level-9 set, which points some slots at its
  own copies of the lists.

## Dojo tutorial

Tool: `tools/tutorial.py`; text in `text/tutorial.txt`; FPG 017 rebuilt, icon table in overlay
000 rewritten.

The tutorial text goes through the menu renderer, so the tiling hook handles it. Lines are CR LF,
16 pixels apart, and 3 fit; something slides in from the right to x 204, so lines stay within
about 210 pixels. The button icons are sprites placed by a 22-entry table at 0x80084290
(message, line, icon, x); in the Japanese each sits on a full-width space. The English marks icon
positions with `{}`: `tutorial.py` leaves a 16-pixel gap there and rewrites each entry's line and
x from the English pen positions. Verified in game.

## Memory card titles

The save title (full-width Shift-JIS at EXE 0x80010364, 44 bytes, shown by the BIOS) becomes
ＦＩＲＥ　ＰＲＯ　ＷＲＥＳＴＬＩＮＧ　Ｇ. The PocketStation save title (FPG 014 +4, 64 bytes) gets
the same with ＰＯＣＫＥＴ. Both must stay full-width.

## Images

Tool: `tools/gfx.py` (`apply`); catalogue `images/graphics.csv`; PNGs in `images/approved/`
(and work in progress in `images/handmade/`, which takes precedence). Editing workflow:
[EDITING.md](EDITING.md); which entries hold which images: [TECHNICAL.md](TECHNICAL.md#images).

Each catalogue row names a rectangle of a source texture and its palette. At build time each
approved PNG is mapped to that palette and written into every entry of its source (the victory
captions appear in seven entries, FPG 279–285). 4-bpp images must start and end on an even x.

## Unlock everything

Tool: `tools/unlock.py`; applied unless `--no-unlock`. EXE only, so it also makes the Japanese
"All Unlocked" patch (`--japanese`).

The "clear all" routine 0x8001A614 (run when Fighting Road is finished) clears the locked-
wrestler set and sets the story-cleared flag. The patch rewrites it to also set the Edit Ranking
reward level to 11, and makes the two places that re-run it only when the flag is set
(after loading data, 0x8001A934; after a memory-card load, 0x8001A3B8) run it every time. New and
loaded saves alike then have everything. The four "30% of scenes seen" checks for the story
edit-point floor (0x8001BBFC, 0x8001BCA8, 0x8001BE78, 0x8001C0A8) are dropped, so the floor is
280. Verified in game.

## Extra Wrestler Make parts

Tool: `tools/hiddenparts.py`; applied unless `--no-extra-parts`.

The unused heads and body parts in FPG 251 (listed in HIDDEN_CONTENT.md) become regular choices.

- Body parts: each list is copied to the end of overlay 004 with the extras ("Extra 1",
  "Extra 2") inserted after the items available from the start, and every per-level count and
  the total of its Wrestler Make row grow by the same number, so the extras exist at every unlock
  level. The game finds a record's list position by value (0x800628AC), so saved wrestlers are
  unaffected.
- Heads: the head list is copied with the 13 heads appended (positions 300–312), its three
  references are repointed, and the last level's count and the total grow by 13. Positions from
  194 on normally also copy a preset from FPG 015, which has none for the new positions, so a
  trampoline on 0x80062738 skips the preset copy for positions past the original list; an extra
  head keeps the current body and colours. The extra heads come with the last Edit Ranking
  reward, which the unlocked build always has.
- Overlay 004 grows by about 2 KB; FPG.BIN still fits.

## Move fixes

Tool: `tools/movefix.py`; applied unless `--no-move-fixes`, and also to the Japanese "All
Unlocked" patch.

Three moves have a status flags byte (byte 19 of the move block, [MOVES.md](MOVES.md#criticals))
that disagrees with the same move from another position. Each gets the other version's value:

| Move | Id | Before | After | Effect |
|---|---|---|---|---|
| Arching Boston Crab (face up) | 1248 | 0x01 | 0x41 | Can make the opponent give up, like the face-down version (1345) |
| Low Blow (from behind) | 1029 | 0x01 | 0x81 | Counts as a foul, like the front version (782) |
| Haruki Special (from behind) | 1073 | 0x40 | 0x49 | Can be a Finisher or Submission critical, like the front version (891) |

- The match reads the moves from FPG 252–258 (LZSS); FPG 274 holds an uncompressed copy.
  Both are patched. Each move's block in 252–258 is found by comparing it with 274's copy.
- The packed files are not recompressed. `lzss.patch` rewrites only a few flag groups around
  each change as plain literals and keeps the rest of the stream. Each file grows by 77–95
  bytes, inside the free space at the end of its last sector. The Japanese build replaces the
  three entries in place (`fpgbin.replace`), so the rest of FPG.BIN keeps its layout.

## Debug menu and route 5

Tool: `tools/debugmenu.py`; only with `--debug-menu` or `--route5`. Not for release.

- **Trigger.** The main loop's hidden combo check (0x8001C6E4: held pad == 0x4816 =
  L1+R2+Triangle+Down+Start opens the test-pattern viewer) tests for Select instead and opens the
  developer mode select (0x80017974). The check runs only after the title has faded out and its
  music stopped, by which time players have let go, so the title (ov2 0x8005D238) now records the
  held buttons at the Start press and the check reads that record. Hold Select and press Start on
  the title screen.
- **Selector.** The menu's number input (a retail stub) is replaced by Up/Down + Circle/Start.
  The printf stubs 0x800146E8 and 0x80015280 forward to the BIOS printf (A0h:3Fh) between
  entering the menu and choosing EXIT, so the modes' text appears in the emulator's TTY log and
  normal play stays quiet.
- **Space.** The code lives in dead EXE code: the unused "yone process select" and the uncalled
  function after it (0x8001EF00–0x8001F0C8). Mode names go where that select's banner and jump
  table were (0x80010A10). The menu branches past the PC-only cases 20/21, and their code
  (0x80017C1C) holds the selector's tables. Modes 7, 20, 21, 70 and 80 (PC file access) are left
  off the menu.
- **Overlay 003.** The menu lists the four yone-select programs as ids 0x300–0x303; the selector
  loads overlay 003, calls the entry and shows the menu again. `patch_ov003` repairs the anime
  tool: the editor's init (0x8005F0A0) and per-frame routine (0x8005F154) are called from the
  shell's empty stubs; the uncalled text reset 0x80074F0C is rewritten to fetch this frame's
  order table (`*(*0x8007DB68) + 0x1364`) and runs before the editor (without it the glyph counter
  overran the stack); the glyph u/v code uses the whole character code; the FPG 250 upload that
  covered the font is skipped; and the mouse slot is changed from 5 to 2, with an EXE routine
  (MOUSE) feeding a pad's D-pad in port 2 into the mouse dx/dy when no mouse is there. Verified in
  game.
- **Route 5** (`--route5`, `patch_route5`): the graduation offer (opcode 0x21) always takes the
  never-produced route 5, so the cut New Japan / Liger scene can be watched: debug menu mode 4
  (FR DEBUG), scene 3.

## What stays Japanese

Leftover Japanese is found by scanning a build with `tools/sjisscan.py` (every FPG entry, raw
and decompressed, and the EXE; keep only runs of common kana and kanji that end in NUL or CR).
What it still reports is either binary data that happens to decode as Shift-JIS or left alone
on purpose:

- Graphics with Japanese text that are kept as art: the arena banners, the title logo and the
  four promotion logos with text in FPG 290.
- The story ending's staff credits (ov2 0x8005AD5C–0x8005C3A0). Not translated yet.
- The name-entry kana grids and FPG 286 (the name-entry character list).
- The old copy of overlay 002's built-in scene (it is repointed).
- "Ｎｏ Ｄａｔａ" in overlay 001 (already English).
- The intro movie (FPG.XA file 6) has no Japanese text that needs translating.

Strings the overlay scanner misses (merged into pointer tables, or with the `lui` far from its
`addiu`) are added to the text files by hand; examples are ov005 0x8005AB28 (the overwrite-image
prompt), ov001 0x8005C134 (不明, a 5-byte slot, "N/A") and EXE 0x800103B0/BC (DQ Loss/Win).

## Limits to respect

| What | Limit | Checked by |
|---|---|---|
| Story lines | about 455 px visible; warning above 440 px; speaker + 3 lines per message | `script.check_message` (build), `storylint.py`, `storycheck.py` |
| Story lines with `#MF` | leave about 150 px for the name (up to ~307 px with the longest names) | `storycheck.py --long-names` |
| Menu windows | each window's cell budget (12-px cells); overflow is cut off by the hook | `uilint.py` |
| Skill Edit | no more cells than the Japanese in any 7 consecutive rows | `skilledit.check` (build) |
| Edit Ranking intro / ending | 15 strings in 181 cells (table 0x80079DCC) and 10 strings in 67 cells (0x80079E08), the Japanese totals: the screens share one pool with no bounds check, and going over corrupts the GPU packet list (the whole screen turns flat) | by hand |
| Edit Ranking profiles | 54 cells, 3 lines of at most 195 px (the player's own wrestler shows ov004 0x8005C20C in the same window) | `editdata.py` (build) |
| Edit Ranking list | 10-, 16- and 4-cell windows | by hand |
| Dojo tutorial | 3 lines of about 210 px | by hand |
| Referee names (match setup) | about 75 px | by hand |
| Roster fields | short name 14 bytes, second part 20, nickname 26 | `roster.py` (build) |
| Custom finisher names | under 28 bytes | by hand |
| Overlay string pools | below the overlay's BSS (`OVERLAY_BSS`) | build |
| FPG.BIN | no larger than the original | build |

## Checking tools

- `tools/storylint.py`: every scene: missing English, leftover `#W` codes or Japanese, too many
  lines, speaker-label mismatches, widths.
- `tools/storycheck.py`: lays out every message the way the patched game draws it, expanding
  name codes like the preprocessor; `--long-names` uses the longest names a player can enter,
  `--png DIR` renders flagged messages, `--verify N` checks the Python model against the real
  hook in mipsim (pixel-identical). It does not model the story window's auto-wrap (assumed off)
  or Shift-JIS spacing (assumed 0).
- `tools/uilint.py`: menu strings whose English needs more cells or pixels than the Japanese.
- `tools/test_vwf.py`, `tools/test_menu_vwf.py`: run the story and menu hooks in mipsim and
  render the result to PNG.
- `tools/storyflow.py`, `tools/storymap.py`: the story branch analysis and the route map's
  data; `tools/guidedata.py` writes it, with the roster and moves, into the guide at
  `docs/guide/index.html` (rerun after script or name edits); `tools/storybattles.py` writes
  `docs/story_battles.csv`.
