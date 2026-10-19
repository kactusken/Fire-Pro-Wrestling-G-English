# Wrestler costumes and colours

How Fire Pro Wrestling G stores and draws the look of its 194 built-in wrestlers: their four
costumes, the body parts each costume is built from, and the 34 colours that paint them. The same
system draws edit wrestlers, so the last sections cover Wrestler Make too. Conventions are those
of [TECHNICAL.md](TECHNICAL.md): RAM addresses, "FPG *n*" for entries of FPG.BIN, "ov4" for code
overlay 004.

[costumes.csv](costumes.csv) lists all of it, one row per wrestler and costume; `tools/costumes.py`
makes it from the disc ([Exporting](#exporting)).

## Contents
1. [Overview](#overview)
2. [Wrestler ids](#wrestler-ids)
3. [Roster record fields](#roster-record-fields)
4. [Body parts](#body-parts)
5. [Colours](#colours)
6. [The colour table (FPG 011)](#the-colour-table-fpg-011)
7. [From colours to palettes](#from-colours-to-palettes)
8. [What each colour group paints](#what-each-colour-group-paints)
9. [Edit wrestlers and Wrestler Make](#edit-wrestlers-and-wrestler-make)
10. [Routines](#routines)
11. [Exporting](#exporting)
12. [How this was worked out](#how-this-was-worked-out)
13. [Open questions](#open-questions)

## Overview

A wrestler's look is a **head**, **eight body parts** and **34 colours**:

- Every roster wrestler has **four costumes**. Each costume has its own head id and part
  numbers in the roster record (FPG 010), and its own colours in a shared colour table (FPG 011).
  After choosing a wrestler on the select screen, the player scrolls through the four and picks
  the one to wrestle in.
- The parts are sprite tiles in FPG 251, drawn with **three 16-colour palettes** (A, B and C)
  built from the 34 colours. Palette A draws the torso, arms and thighs, palette B the shins and
  feet, and palette C the head and hands.
- The 34 colours form **10 groups**. Group 0 is skin and appears in all three palettes. Groups
  1–3 go to palette A, groups 4–6 to palette B and groups 7–9 to palette C.
- Two more record bytes set the **stance** (idle animation) and the **size**.

## Wrestler ids

Wherever the game handles "a wrestler" it uses a 16-bit id, split by EXE 0x8001a84c:

| Bits | Mask | Meaning |
|---|---|---|
| 0–8 | 0x01FF | Number: roster wrestler 0–193, or edit slot |
| 9–11 | 0x0E00 | Costume, 0–3 (roster wrestlers only) |
| 13–15 | 0xE000 | Kind: 0 = roster wrestler (FPG 010 record), 0x2000 = edit wrestler in the save/system block (record at \*0x800541B4 + 0x1D0 + 512 × number), 0x8000 = working edit record (wrestler work area + 0x305C + 512 × number) |

The costume number is the one the player scrolls to on the wrestler select screen. Edit
wrestlers have one look, held in their own record, so the costume bits only matter for roster
wrestlers.

## Roster record fields

The roster record is 426 bytes; the full layout is in
[TECHNICAL.md](TECHNICAL.md#roster-record-426-bytes-fpg-010-copies-in-fpg-011-and-overlay-005).
The bytes that set the look:

| Offset | Size | Field |
|---|---|---|
| +0x5C | 1 | Stance, 0–8: Strong, Technic, Amateur, Power, Lucha, Shoot, Mystery, Koppo, Kobudo (the Wrestler Make "Stance" list, ov4 0x800757E8). The figure system uses it to pick the standing animation (table at EXE 0x8004A8B8) |
| +0x5D | 1 | Size, 0–2: S, M, L (Wrestler Make "Size"; the label table at ov4 0x8007580C also has a fourth, "D", that no list offers). The roster uses 0 87 times, 1 67 times and 2 40 times |
| +0x182 | 4 × 10 | Costumes 1–4, 10 bytes each: u16 head id, then 8 part numbers (part byte 0–7, below) |

Costume *c* (0–3) is at +0x182 + 10 × *c*. EXE 0x800199a0 returns a pointer to the costume's
head and parts (or to edit record +0x1F2 for an edit wrestler). EXE 0x80019e2c copies the
costume, stance and size into an edit record (Wrestler Make's "copy a roster wrestler").

## Body parts

FPG 251 holds every head and part. It starts with 871 { u32 offset, u32 size } entries (data at
0x2000). A head is entry *head id*. Part byte *s* with part number *p* is entry `base[s] + p`,
where the bases are the u16 table at ov4 0x80079F60 (after the head's 0).

| Part byte | Wrestler Make label | FPG 251 entries | What it draws | Tile size | Palette |
|---|---|---|---|---|---|
| (head id) | Face | 0–319 | Head, hair, face, mask | (own format) | C |
| 0 | Chest | 320–395 | Chest and shoulders | 24 × 24 | A |
| 1 | Waist | 396–517 | Trunks, tights top, belt | 24 × 24 | A |
| 2 | Bicep | 518–588 | Upper arm (elbow pads, arm bands) | 24 × 24 | A |
| 3 | Arm | 589–655 | Forearm (wristbands, tape) | 24 × 24 | A |
| 4 | Shin | 656–713 | Shin and knee (knee pads, boot tops, bare legs) | 24 × 24 | B |
| 5 | Thigh | 714–810 | Thigh (tights, knee supporters) | 24 × 24 | A |
| 6 | Wrist | 811–832 | Hand (bare, gloves, finger tape) | 16 × 16 | C |
| 7 | Ankle | 833–870 | Foot (bare, ankle tape, boots) | 16 × 16 | B |

The part bytes are not in the order of the Wrestler Make rows. The rows (ov4 0x80076478, 20 bytes
each: list pointer, part byte, type, item counts per Edit Ranking level, total) run Stance, Size,
Face, Chest, Waist, Bicep, Arm, Wrist, Thigh, Shin, Ankle, and name their part byte at +4.

**Part entries** (not heads) are plain LZSS ([TECHNICAL.md](TECHNICAL.md#compression)). They
unpack to 4-bit tiles, 24 × 24 (288 bytes) or 16 × 16 (128 bytes): a pose sheet of the part in
every angle the game needs. Wrestler Make's preview loader (ov4 0x80073820 / 0x800738d8) uploads
them to VRAM tile by tile from a per-slot list of { x, y, height, tile } records.

**Heads** use a different format, which is not decoded yet.

**Part lists and variants.** Each Wrestler Make row's list has 12-byte entries { u32 name
pointer, u8 variant count, 4 part numbers, padding }. A name can have up to four variants, which
are different builds of the same item. For example, "Normal" chest is parts 3, 2, 1 and 0. The
editor keeps the list position as entry × 4 + variant (ov4 0x800628ac), so the variant is chosen
per part and doesn't follow Size. The roster mixes them freely: a size-S wrestler can wear an
M-build chest. Entries with a variant count of 0 (hands, shins, feet) have one version.

## Colours

The 34 colours are 15-bit PlayStation colours (bits 0–4 red, 5–9 green, 10–14 blue, bit 15
semi-transparency). They are numbered 0–33 and form 10 groups (sizes from the byte table at EXE
0x80048F68; first colour per group at ov4 0x80076578):

| Group | Colours | Count | Palette | Palette indices |
|---|---|---|---|---|
| 0 (skin) | 0–3 | 4 | A, B and C | 1–4 |
| 1 | 4–6 | 3 | A | 5–7 |
| 2 | 7–9 | 3 | A | 8–10 |
| 3 | 10–12 | 3 | A | 11–13 |
| 4 | 13–15 | 3 | B | 5–7 |
| 5 | 16–18 | 3 | B | 8–10 |
| 6 | 19–23 | 5 | B | 11–15 |
| 7 | 24–26 | 3 | C | 5–7 |
| 8 | 27–29 | 3 | C | 8–10 |
| 9 | 30–33 | 4 | C | 11–14 |

A group's colours are the shades of one colour, in palette-index order. In every built-in set,
skin and group 8 run light to dark and the other groups dark to light. The two extra colours of group 6 (palette
B 14–15) and the extra one of group 9 (palette C 14) are details such as boot stripes and laces.

## The colour table (FPG 011)

Roster colours are not stored per wrestler. FPG 011 (LZSS) is a container: the menu font copy,
a roster copy at +0x1046C, the **colour table at +0x24740**, then the move names at +0x30A38.
The game keeps a pointer to the colour table at (\*0x800541B0) + 0xC.

Each group has a library of colour **sets**, and each wrestler-and-costume picks one set per
group. The table is u16 words, with offsets counted in u16s from the table start:

| Word | Contents |
|---|---|
| 0 | Offset of the set-count list (22) |
| 1–10 | Offset of each group's index table |
| 11–20 | Offset of each group's sets |
| 22–31 | Number of sets in each group: 36, 179, 207, 289, 223, 178, 190, 101, 101, 118 |

- **Index tables**: 776 entries (194 wrestlers × 4 costumes, entry 4 × wrestler + costume), one
  byte each, or a u16 each when the group has 256 sets or more (group 3 only).
- **Sets**: group *g*'s set *n* is its colours (3, 4 or 5 u16s) at sets[*g*] + *n* × count.

EXE 0x800188d4 looks up the 34 colours of the current roster wrestler and costume into a buffer.
The set libraries are also what Wrestler Make cycles through (below).

## From colours to palettes

EXE 0x80018ad0 turns 34 colours into six 16-colour palettes (96 u16s):

| Index | Palette A | Palette B | Palette C |
|---|---|---|---|
| 0 | transparent (0x0000) | transparent | transparent |
| 1–4 | skin 0–3 | skin 0–3 | skin 0–3 |
| 5–13 | colours 4–12 (groups 1–3) | colours 13–21 (groups 4, 5, first two of 6) | colours 24–32 (groups 7, 8, first two of 9) |
| 14 | black (0x8000) | colour 22 | colour 33 |
| 15 | colour 1 (skin, as index 2) | colour 23 | colour 1 (skin, as index 2) |

Palettes 3–5 are shaded copies of A, B and C. Each channel is multiplied by a per-index factor
/ 32 from the u16 table at EXE 0x80048F74, mostly 21–23 (about 70 %). Every entry except index
0 gets bit 15 set. The game draws the far-side arm and leg with the shaded palettes, so the two
sides of the body read apart.

The wrestler-figure system (EXE 0x8001de90, 0x8001e9bc; up to five figures on screen) asks for
the palettes through EXE 0x80019914. For roster wrestlers that is the colour table, and for edit
wrestlers the record's own colours. It uploads figure *k*'s palettes to VRAM at x = 1008,
y = 384 + 6*k* (one row per palette). Every sprite piece of the figure is drawn with one of
those six rows.

## What each colour group paints

The palette is fixed by the body part (table in [Body parts](#body-parts)). Which group a pixel
uses is down to the part's artwork: a part drawn with palette A can use any of groups 1–3, and
two parts can share a group. Across all the part art, the share of non-transparent pixels per
palette range is:

| Part byte | Palette | Skin (1–4) | 5–7 | 8–10 | 11–13 | 14–15 |
|---|---|---|---|---|---|---|
| 0 Chest | A | 42 % | 22 % (group 1) | 16 % (2) | 19 % (3) | 1 % (skin) |
| 1 Waist | A | 26 % | 13 % (1) | 16 % (2) | 44 % (3) | — |
| 2 Bicep | A | 54 % | 22 % (1) | 12 % (2) | 12 % (3) | — |
| 3 Arm | A | 49 % | 23 % (1) | 14 % (2) | 14 % (3) | — |
| 4 Shin | B | 27 % | 42 % (4) | 19 % (5) | 12 % (6) | 1 % (6) |
| 5 Thigh | A | 26 % | 19 % (1) | 33 % (2) | 22 % (3) | — |
| 6 Wrist (hand) | C | 36 % | 46 % (7) | 18 % (8) | — | — |
| 7 Ankle (foot) | B | 17 % | 17 % (4) | 33 % (5) | 31 % (6) | 2 % (6) |

So, as a rule of thumb: **groups 1–3** are the trunks, tights and upper-body gear (group 3 is
mostly the trunks), **groups 4–6** the knee pads, boot tops and boots, **groups 7–8** gloves and
head details such as masks, and **group 9** the hair.

The test that settled this gave each group of Mitsuharu Misawa (roster 40) its own colour (see
[How this was worked out](#how-this-was-worked-out)). In his costume 1:

| Group | Shows on | His own colour |
|---|---|---|
| 1 | Outer side of the thigh tights, wrist tape | white |
| 2 | Front of the thigh tights | green |
| 3 | Trunks | green |
| 4 | Knee pads | green |
| 5 | Band below the knee pads | green |
| 6 | Boots; its 4th–5th colours are the boot stripes | white |
| 7, 8 | Nothing: he has no gloves and his head uses neither | — |
| 9 | Hair | black |

## Edit wrestlers and Wrestler Make

An edit record (512 bytes) holds one look, in the same order as a roster costume:

| Offset | Contents |
|---|---|
| +0x5C, +0x5D | Stance, size |
| +0x184 | The 34 colours (68 bytes) |
| +0x1F2 | u16 head id |
| +0x1F4 | 8 part numbers |

Wrestler Make edits these directly:

- **Colours**: the cursor (work area +0x352) walks the 34 colours. Red, green and blue change one
  colour at a time (0–31 each), there is copy and paste, and one control steps the whole group
  through the set library of the colour table (ov4 0x800626a4 → EXE 0x800189d8). The table at ov4
  0x80076554 maps colour 0–33 to its group.
- **Heads**: the Face list is a list of head ids (ov4 0x80076220). A head id under 194 is a
  roster wrestler's own head, and choosing it copies that wrestler's costume 1, colours, stance
  and size (EXE 0x80019e2c). Choosing any other head loads a preset from FPG 015 (list position
  − 194).
- **FPG 015 presets** (109 × 78 bytes): stance, size, 8 part numbers, 34 colours. They have the
  same layout as record +0x5C/+0x5D, +0x1F4 and +0x184.

## Routines

| Address | Routine |
|---|---|
| EXE 0x8001a84c | Decode a wrestler id into the current-wrestler state (work +0x2FA0 record pointer, +0x2FA4 number, +0x2FA6 kind, +0x2FA8 costume) |
| EXE 0x800188d4 | Current roster wrestler's 34 colours from the colour table |
| EXE 0x800189d8 | Step one colour group to the next or previous set (Wrestler Make) |
| EXE 0x80018ad0 | 34 colours → palettes A, B, C and their shaded copies |
| EXE 0x80019914 | A wrestler's palettes, by id (roster or edit) |
| EXE 0x800199a0 | A wrestler's head and parts, by id |
| EXE 0x80019860 | Head/parts pointer, stance and size for the figure system |
| EXE 0x80019e2c | Copy a roster costume into an edit record |
| EXE 0x8001ec80 | Upload the five figures' palettes to VRAM (1008, 384 + 6*k*) |
| ov4 0x80073820 | Wrestler Make preview: load the head and parts from FPG 251 |
| ov4 0x800738d8 | Upload one part's tiles to VRAM |
| ov4 0x800628ac | Find each Wrestler Make list position from the record's values |

## Exporting

```sh
python3 tools/extract.py          # once: unpacks the disc into extracted/
python3 tools/costumes.py         # -> docs/costumes.csv
```

`--extracted`, `--text` and `--out` change the paths. The CSV has 776 rows (194 wrestlers × 4
costumes) with these columns:

| Columns | Contents |
|---|---|
| `id`, `name`, `short` | Roster number and English names (from `text/wrestlers.csv`) |
| `costume` | 1–4 |
| `stance`, `size` | As in the record, by name |
| `head` | Head id (FPG 251 entry) |
| `chest` … `ankle` | For each part byte, by its Wrestler Make label: part number, `_name` (the Wrestler Make list name, in English), `_variant` (1–4, blank for single-version parts) |
| `group0_set` … `group9_set` | The colour-table set each group uses |
| `group0_1` … `group9_4` | The 34 colours as `#RRGGBB`, by group (each 5-bit channel *v* becomes (*v* << 3) \| (*v* >> 2)) |

## How this was worked out

The routines above were traced in the EXE and overlay 004. The palette assignment needed a test
in the game. A throwaway build gave each of Misawa's colour groups 1–9 its own colour (red,
green, blue, yellow, magenta, cyan, orange, purple, pink), and the result was checked in two
DuckStation save states, on the wrestler select screen and in a match:

- The VRAM in the save state showed which body area each colour landed on.
- In the match state, the GPU command list in RAM showed every one of Misawa's 15 sprite pieces
  (head, chest, waist, two each of bicep, arm, thigh, shin, hand and foot) with its palette row.
- Each piece's texture in VRAM matched a tile of the expected FPG 251 part entry exactly, which
  ties each part byte to its palette.

## Open questions

- The head sprite format (FPG 251 entries 0–319). It is not plain LZSS like the parts.
- Where each sprite piece's palette row comes from. It is fixed per part in every pose seen, and
  is most likely in the pose data (FPG 270 / 271), whose format is not decoded.
- What Size changes in a match, and whether size "D" works.
