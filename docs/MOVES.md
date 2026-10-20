# Moves

How Fire Pro Wrestling G stores its moves and gives them to wrestlers. It covers the 57 move
slots in a wrestler's record, how Move Edit lists the choices, and the move data itself: the
damage and hit box in the 32-byte status block, and the animations frame by frame. Conventions
are those of [TECHNICAL.md](TECHNICAL.md): RAM addresses, "FPG *n*" for entries of FPG.BIN, and
"ov4" for code overlay 004.

Two tables list all of it, both made from the disc by `tools/movedata.py`
([Exporting](#exporting)):
- [moves.csv](moves.csv) has one row per move.
- [wrestler_moves.csv](wrestler_moves.csv) has one row per roster wrestler.

## Contents
1. [Overview](#overview)
2. [Where the data is](#where-the-data-is)
3. [Move ids and variants](#move-ids-and-variants)
4. [Move slots](#move-slots)
5. [Move Edit lists](#move-edit-lists)
6. [The move block](#the-move-block)
7. [Status block](#status-block)
8. [Animations](#animations)
9. [Forms](#forms)
10. [Value tables](#value-tables)
11. [Example: Punch](#example-punch)
12. [Routines and tables](#routines-and-tables)
13. [Exporting](#exporting)
14. [How this was worked out](#how-this-was-worked-out)
15. [Open questions](#open-questions)

## Overview

- A move is a **move id** (1–1591). The id indexes three things: the move name table
  (FPG 011), the move data (FPG 252–258, with a copy in FPG 274), and the Move Edit lists.
- Every wrestler record has **57 move slots**, one per command: Stand A, Grab C toward, Taunt L,
  and so on. Each slot holds a move id plus flags. The flags mark the finisher, up to four
  signature moves, and which of the wrestler's two shouts (if any) goes with the move.
- Most moves come in **variants**: 2 or 3 consecutive ids with the same name, drawn for
  different facings. A slot stores the first id; the match picks the variant from the
  direction the wrestler faces.
- A **move block** has two kinds of data:
  - A 32-byte **status block**, the game rules: command type, damage to each body part, the
    ratings it is rolled against, critical types, hit box and flight.
  - Up to 16 **animations**, frame by frame: pose, offsets, timing, hit flags and sounds.
    Slot 0 is the attacker; a grapple's slot 1 is the defender.
- The developers' editor in overlay 003 (the "anime tool", [HIDDEN_CONTENT.md](HIDDEN_CONTENT.md#developer-moveanimation-editor-overlay-003))
  edits exactly this data. Its screen labels name most of the fields below, and are quoted as
  `label`.

## Where the data is

| Data | Where | Format |
|---|---|---|
| Names | FPG 011 (LZSS) at +0x30A38 | 1,592 u16 offsets, relative to the table, to NUL-terminated Shift-JIS names. English in `text/moves.csv` |
| Move data | FPG 252–258 (raw) | Each file: 1,600 u32 offsets indexed by move id, then the blocks. Each file holds part of the ids; the rest of its table points at an empty entry |
| Move data copy | FPG 274 (raw) | 1,792 { u32 offset, u32 size } pairs, then one sector-aligned block per id. Byte for byte the same 1,270 blocks as 252–258; the exporter reads this one |
| Global forms | FPG 270 (raw) | 4,032 forms of 96 bytes (0xFC0, see [Forms](#forms)) |
| Basic motions | FPG 273 (raw), FPG 259 (packed) | Walking, reactions and so on: the same layout as a move block, with an empty status block and no local forms |
| Move slots | Roster record (FPG 010) +0x74..+0xE5; edit record, same offsets | 57 × u16 |
| Move Edit lists | ov4 0x80078C60 and three more sets | 57 × { u32 list pointer, u32 count } per set |
| Critical type | Record +0x54 | 0–5 ([Criticals](#criticals)) |
| Shouts | Record +0x58 (Voice 1), +0x5A (Voice 2) | Voice numbers |
| Custom finisher name | Edit record +0x1C8 | Replaces the finisher's name for edit wrestlers |

The match loader (ov0 0x80080208) reads all seven of FPG 252–258 and keeps every block it finds.
For each fighter it then picks out the blocks its slots need ([Variants](#variants)).

## Move ids and variants

- 1,592 ids have names. **1,270 have data.** The other ids are padding ("(予約)", reserved) or
  moves that were named and never made ([HIDDEN_CONTENT.md](HIDDEN_CONTENT.md#moves)).
- Id 0 is "Unused", what an empty slot shows.
- Id ranges follow the Move Edit commands: 1–199 standing, 217–309 running, 331–485 counters,
  507–689 diagonal, dives and top rope, 697–1017 grapples, 1018–1159 from behind, 1166–1362 on
  the ground, 1368–1424 corner, 1430–1457 and 1553–1557 double and triple teams, 1464–1549
  taunts, 1558–1591 running at a downed opponent.

### Variants
Each slot loads a fixed number of consecutive ids, starting at the id it stores. All ids of a
run have data and the same name (checked for every offered move).

| Slot kind | Ids loaded | How the match picks one |
|---|---|---|
| Stand (slots 0–3) | 3 | By facing (fighter +0x1A0, 0–5) through the table at ov0 0x80081EBC = [0, 1, 2, 0, 2, 1]: facings 0 and 3 (left/right) use the first id, the two diagonal pairs the second and third |
| Run, Counter, Dive, Plancha, Apron, Post, Run Dn (slots 4–7, 9–15, 45) | 2 | By the table at 0x80081EC4 = [0, 0, 1, 0, 1, 0]. Facing straight left or right, the index is 1 or 2 (5 or 4) depending on whether the opponent is above; other facings use the facing itself (ov0 0x8006997c) |
| All others | 1 | Always the stored id |

The loader keeps 77 blocks per fighter, one per slot and variant (slot table ov0 0x80085640,
variant table 0x80085690, reverse map 0x800856e0 with 127 = none). They are stored at
`*0x800861c8 + 0x1E4 + 4 × (80 × fighter + entry)`. Which diagonal is "up" is not checked.

## Move slots

Slot *n* is the u16 at record +0x74 + 2*n*. The labels are Move Edit's (ov4 table 0x80079380,
entry *n* + 1). The buttons are its icons (ov4 0x80079B80). Ids 0–2 are A, B and C, 9 and 11 are
L and R. Ids 4/6/5 and 7 are directions, read here as up, toward, down and away (not checked in
the game). The list range is the level-9 set, the fullest.

| Slot | Offset | Move Edit | Buttons | Ids loaded | List: ids (entries) |
|---|---|---|---|---|---|
| 0 | +0x74 | Stand | A | 3 | 1–55 (17) |
| 1 | +0x76 | Stand | B | 3 | 1–55 (17) |
| 2 | +0x78 | Stand | C | 3 | 1–199 (56) |
| 3 | +0x7A | Stand | A+B | 3 | 1–199 (56) |
| 4 | +0x7C | Run | A | 2 | 217–309 (44) |
| 5 | +0x7E | Run | B | 2 | 217–309 (44) |
| 6 | +0x80 | Counter | A | 2 | 331–485 (67) |
| 7 | +0x82 | Counter | B | 2 | 331–485 (67) |
| 8 | +0x84 | Diagonal (run) | C | 1 | 0, 507–530 (25) |
| 9 | +0x86 | Dive (run out of the ring) | C | 2 | 0, 537–557 (12) |
| 10 | +0x88 | Plancha (over the ropes) | C | 2 | 0, 565–573 (6) |
| 11 | +0x8A | Apron (back into the ring) | C | 2 | 0, 581–591 (7) |
| 12–15 | +0x8C..+0x92 | Post | A, B, C, A+B | 2 | 0, 601–689 (42) |
| 16–19 | +0x94..+0x9A | Grab | A, up A, toward A, down A | 1 | 697–746 (48) |
| 20–23 | +0x9C..+0xA2 | Grab | B, up B, toward B, down B | 1 | 697–835 (128) |
| 24–27 | +0xA4..+0xAA | Grab | C, up C, toward C, down C | 1 | 697–1017 (279) |
| 28 | +0xAC | Grab | A+B | 1 | 697–1017 (279) |
| 29 | +0xAE | Back | A | 1 | 1018–1029 (12) |
| 30 | +0xB0 | Back | B | 1 | 1018–1056 (33) |
| 31–33 | +0xB2..+0xB6 | Back | C, away C, toward C | 1 | 1018–1129 (91) |
| 34 | +0xB8 | Back | A+B | 1 | 1018–1129 (91) |
| 35 | +0xBA | B.Rev (reversal from behind) | A | 1 | 1139 (1) |
| 36 | +0xBC | B.Rev | B | 1 | 1140–1159 (15) |
| 37 / 41 | +0xBE / +0xC6 | UpHead (face up, at the head) | B / C | 1 | 1166–1229 (57) |
| 38 / 42 | +0xC0 / +0xC8 | UpLegs (face up, at the legs) | B / C | 1 | 1234–1272 (35) |
| 39 / 43 | +0xC2 / +0xCA | DnHead (face down, at the head) | B / C | 1 | 1277–1323 (42) |
| 40 / 44 | +0xC4 / +0xCC | DnLegs (face down, at the legs) | B / C | 1 | 1327–1362 (33) |
| 45 | +0xCE | Run Dn (run at a downed opponent) | C | 2 | 0, 1558–1590 (18) |
| 46–48 | +0xD0..+0xD4 | Corner (grapple in the corner) | up C, toward C, down C | 1 | 1368–1424 (41) |
| 49 / 50 | +0xD6 / +0xD8 | Taunt | L / R | 1 | 1464–1549 (81) |
| 51 | +0xDA | Front Duo | | 1 | 1430–1435 (3) |
| 52 | +0xDC | Front Trio | | 1 | 1553 (1) |
| 53 | +0xDE | Back Duo | | 1 | 1442–1443 (2) |
| 54 | +0xE0 | Back Trio | | 1 | 1554 (1) |
| 55 | +0xE2 | Corner Duo | | 1 | 1451–1454 (4) |
| 56 | +0xE4 | Corner Trio | | 1 | 1555–1557 (3) |

- Lists that start with id 0 ("Unused") allow an empty slot: slots 8–15 and 45. Every roster
  wrestler fills all the other slots.
- The grapple lists grow with the button: A's list is the start of B's, which is the start of
  C's. The move's own command type ([status byte 30](#status-block)) is the weakest button it
  is listed under. Roster wrestlers often put a B move on C (e.g. 25 wrestlers on Grab C).
- Avalanche moves (top-rope throws) are in the Corner list. Double and triple team moves are
  slots 51–56. Nothing outside the 57 slots gives a wrestler a move.
- +0xE6 onwards is the CPU logic (ov0 0x80068e6c).
- EXE 0x80018670 looks for the finisher in only the first 56 slots. That does no harm:
  slot 56 is never the finisher.

### Slot value
| Bits | Meaning |
|---|---|
| 0–10 (& 0x7FF) | Move id, 0 = empty. Name lookups mask with 0xFFF |
| 11 | Never set |
| 12 (0x1000) | **Signature move.** Move Edit allows at most four, and not on the finisher (Circle on page 1, ov4 0x800683b4). Every roster wrestler has four, except two with three. In a match it sets fighter flag 0x100000; the match counts how often they are used (ov0 0x80071560) |
| 13 (0x2000) | **Finisher.** Exactly one (Square on page 1, ov4 0x800682dc). The select screen and the database show its name (EXE 0x80018670); for an edit wrestler they show the custom name at +0x1C8 instead. In a match it sets fighter flag 0x80000 and +0x1C2 = 3 |
| 14–15 (>> 14) | **Shout**: 0 none, 1 Voice 1 (+0x58), 2 Voice 2 (+0x5A). It plays when an animation frame plays the "wrestler voice" sound (SE 127): ov0 0x8007e6e0 reads the slot being performed (fighter +0x16C), takes the shout and plays that voice. Set on Move Edit page 0 with Square or Circle (ov4 0x800681e4) |

Move Edit has three columns per row, chosen with L/R (work area +0x344): the shout icon, the
finisher/signature icon and the move name. Circle on the name opens the list.

## Move Edit lists

Each set has 57 { u32 pointer, u32 count } entries, one per slot. Each list is a run of u16 first
ids. The set is chosen at ov4 0x80067680 from the edit work area (`*0x800541c8`):

| Set | When | Size |
|---|---|---|
| 0x80078FF0 | Fighting Road hero, story stage 0 (work area +0x340 = 2, +0x16 = 0) | Smallest |
| 0x80078E28 | Fighting Road hero, stage 1 | Larger |
| 0x80078C60 | Everything else (and the hero from stage 2) | Normal |
| 0x800791B8 | The normal set once the Edit Ranking level (EXE 0x8001a678) is 9 or more | Normal + Phoenix Kick (530, one list) and Muscle Buster (947, five lists) |

The story stage is byte 10 of the story battle record. ov2 0x80060054 passes it to EXE
0x8001c150, which copies the hero into the work area and sets +0x340 = 2. Of the story battles,
23 use stage 0, 92 stage 1 and 241 stage 2, so the hero's move choices grow as the story goes
on.

The level-9 set offers 962 first ids. With their variants that is 1,264 of the 1,270 ids with
data; the other six are 211–216, "(Reserved)" ([HIDDEN_CONTENT.md](HIDDEN_CONTENT.md#unnamed-moves-with-data)).

## The move block

The layout holds for all 1,270 blocks, and for the 475 basic motions in FPG 273.

```
+0x00  32 bytes   status block (the rules: see below)
+0x20  16 bytes   end table: end[k] = end of animation k, counted in 12-byte records from +0x30
+0x30             animations 0..15, each a 12-byte header and then its frames, 12 bytes each
+0x30 + 12 × end[15]
                  local forms, 96 bytes each, to the end of the block
```

- Animation *k* starts at +0x30 + 12 × end[*k*−1] (end[−1] = 0) and holds 1 + *frames* records,
  so end[*k*] − end[*k*−1] = 1 + its frame count. An empty slot has end[*k*] = end[*k*−1];
  unused slots at the end repeat the last value. Only move 1389 has an empty slot in the middle.
- **Slot 0 is the attacker.** Only it carries the hit sound and reversal fields (the editor
  shows them only for slot 0). In a grapple, slot 1 is the defender (its poses are mirrored,
  0x41xx). The engine finds slot 1 at +0x30 + 12 × end[0] (ov0 0x80072c4c). Other moves use more
  slots for their phases or extra wrestlers. The roles of those slots are not decoded:

  | Class ([status byte 0](#status-block)) | Animations |
  |---|---|
  | strike | 1 |
  | grapple, big strike, diagonal run, combination follow-up | 2 |
  | lunging strike, double team, combination opener | 3 |
  | triple team, dives (strike) | 4 |
  | dive outside (body) | 5 |
  | top rope on standing (strike) | 6 |
  | top rope on standing (body) | 7 |
  | top rope on downed (body), run at downed | 8 |
- In a match, fighter +0x15C points at the block being performed.
- The editor holds a move as 0x4820 bytes: the status block, 24 animations of 0x300 bytes, and
  64 local forms (ov3 0x80060b7c packs it, 0x80060bac unpacks it).

## Status block

32 bytes at the start of the block. The editor shows them on four screens: "waza status",
"waza parameter", "waza attack range" and "waza extend data". The overlay 003 code that unpacks
them is at 0x80060bac, and the code that shows them is at 0x800635e8–0x80063eb4.

| Byte | Editor label | Meaning | moves.csv |
|---|---|---|---|
| 0 | `waza type1` | Class, 0–15 ([Classes](#classes)). Decides how many animations the move has and how it is performed | class |
| 1 | `waza side` | 0, 1 or 2. 0 for standing strikes, 1 for lunging and running moves, 2 for grapples; meaning not worked out | side |
| 2 | `hp-atk` | Damage to HP | hp |
| 3 | `sp-atk` | Damage to spirit | spirit |
| 4 | `nk-atk` | Damage to the neck | neck |
| 5 | `am-atk` | Damage to the arms | arm |
| 6 | `ws-atk` | Damage to the waist | waist |
| 7 | `lg-atk` | Damage to the legs | leg |
| 8 | `br-atk` | Damage to breathing (`br-los` and `br-bom` are shown as 0 and not stored) | breathing |
| 9 | `blood rate` | Chance of opening a cut | blood |
| 10 | `am` / `as` | High nibble: the attacker's main rating, low nibble: the sub rating. An index into the 10 offence ratings at record +0x5F (ov0 0x80064700) | attack_rating, attack_sub_rating |
| 11 | `dm` / `ds` | The defender's main and sub rating: an index into the 10 defence ratings at record +0x69 | defence_rating, defence_sub_rating |
| 12 | `nek` `arm` `wst` `leg` | Bits 8, 4, 2, 1: the body parts the attacker uses (a punch uses arm + waist, a kick waist + leg) | uses |
| 13–18 | `hp-bom` … `lg-bom` | Damage the attacker takes, same order as 2–7. Mostly on dives | self_hp … self_leg |
| 19 | `cri normal` … `hansoku` | Bit flags: 0–5 the critical types the move can trigger, 6 can make the opponent give up, 7 foul ([Criticals](#criticals)) | flags (the byte), critical, give_up, foul |
| 20, 21 | `offset x`, `y` | Signed hit box offset from the attacker. x is negated when facing the other way (ov0 0x8005be34) | offset_x, offset_y |
| 22, 23 | `range x`, `y` | Hit box half-width and half-height: the box is position + offset ± range | range_x, range_y |
| 24 | `atk dist` | Attack distance. Non-zero only on diagonal runs, dives and combinations | attack_dist |
| 25 | `fly dist` | Flight distance (dives: 100–140) | fly_dist |
| 26 | `fly time` | Flight time (32–48) | fly_time |
| 27 | `flypower` | Flight power (2–5) | fly_power |
| 28 | `s height` | Start height | start_height |
| 29 | `e height` | End height | end_height |
| 30 | `waza type2` | Command type: the Move Edit command the move belongs to ([Command types](#command-types)) | command |
| 31 | `single hit`, `combo hit` | Low nibble: single hits; high nibble: combo hits (ov0 0x8005c150, 0x8005c1e8) | single_hits, combo_hits |

The command type is the command the move was made for. Roster wrestlers keep to it, with two
kinds of exception:
- The lists for stronger buttons include the weaker buttons' moves (Stand, Grab, Back), so a C
  slot may hold a move with an A or B command type.
- A few lists mix in other commands. For example, Run Dn offers top-rope moves (command 12)
  next to its own (37).

## Animations

### Animation header (12 bytes)
Shown on the "anime status data" screen (ov3 0x80063ec0; unpacked at 0x800615d4).

| Byte | Editor label | Meaning | moves.csv (slot 0) |
|---|---|---|---|
| 0 | | Number of frames | frames |
| 1 | `loop point` | Frame to loop from | loop_point |
| 2 | `loop back` | Frame to loop back to | loop_back |
| 3 | `fall frame` | Frame where the wrestler falls | fall_frame |
| 4 | `limit mode` | 0, 2 or 3 | limit_mode |
| 5 | `dageki hit se` | Sound when a strike lands ([Sounds](#sounds)); Punch has 25 "punch lv1", High Kick 33 "high kick lv1" | hit_se |
| 6 | `waza se level` | 0–6 | se_level |
| 7 | (not shown) | 0–10, slot 0 only. Meaning not known | byte7 |
| 8 | `rev waza type` | Reversal type (the engine reads it signed, from block +0x38). 0–121 | reversal_type |
| 9 | `rev rate type` | Reversal rate type, 0–96 | reversal_rate |
| 10 | `start mode` | | start_mode |
| 11 | `end mode` | | end_mode |

Bytes 5–9 are non-zero only in slot 0.

### Frame (12 bytes)
The editor shows frames in three column sets (ov3 0x800641a8, 0x80064620–0x800649b8; unpacked
at 0x800618e0): "af wt fx fy form sx sy shd fpr rpr y", "af wt ad dmg bom tai sep z u/d l/r
i/o" and "af wt r x kan se# name".

| Byte | Editor label | Meaning |
|---|---|---|
| 0, 1 | `sx`, `sy` | Signed step: how far the wrestler moves this frame |
| 2–3 | `form` | **Big-endian** u16 pose. Bits 0–13: form number; bit 14: flip horizontally; bit 15: flip vertically. Below 0xFC0 it is a global form (FPG 270); 0xFC0 + *k* is local form *k* of this block |
| 4, 5 | `fx`, `fy` | Signed sprite offset |
| 6 | `wt` | Frames to hold the pose (1–71); the sum over slot 0 is moves.csv's duration |
| 7 | `fpr` `rpr` `shd` | Bits 7–6 fpr, bits 5–3 rpr, bits 2–0 shadow |
| 8 | `a` `d` `dmg` `bom` `tai` `sep` `kan` | Flags 0x80 a (attack: the frame that can hit; set on Punch's middle frame), 0x40 d (defence: can be hit), 0x20 dmg, 0x10 bom, 0x08 tai, 0x04 sep, 0x02 kan. Bit 0 is never set |
| 9 | `u/d` `z` `l/r` `i/o` | Bit 7 u/d (0 u, 1 d); bits 6–4 z; bit 3 l/r (0 l, 1 r); bits 1–0 i/o (0 –, 1 in, 2 out). Bit 2 is never set |
| 10 | `x` `y` `r` | Bits 7–5 x (0 none, else value − 1), bits 4–3 y, bits 2–0 r |
| 11 | `se#` | Sound to play on this frame, 0 = none ([Sounds](#sounds)). Common: 127 "wrestler voice" (the slot's shout), 64–66 "mat(step)", 116 "down mat(chu)" |

The editor reads the pose with a little-endian load, but the data on the disc is big-endian:
- local forms are numbered 0x0FC0, 0x0FC1 … in frame order;
- the largest global form in use is 0xFB6, below 0xFC0;
- defenders' frames carry 0x41xx (flipped).

## Forms

A form is one pose: a list of body-part sprites with their positions. **FPG 270 is 387,072
bytes, exactly 0xFC0 × 96**: the 4,032 global forms that frames 0–0xFBF point at. A block's
local forms follow its animations; 139 blocks carry local forms that none of their frames use.

96 bytes: a 6-byte header, then 15 part entries of three big-endian u16, in draw order:

| Word | Bits |
|---|---|
| 0 | Bits 15–14 vertical/horizontal flip, bits 13–9 group/attribute (usually 0, 8, 16 or 24), bits 8–0 the sprite (`CHR`, 0–511) |
| 1 | High byte `MX` (signed x); low byte two signed nibbles |
| 2 | High byte `MY` (signed y); low byte two signed nibbles |

The editor ("# MX MY CHR ATTR ZR", ov3 0x800607e8) names the part types P0-FACE, P1-CHEST,
P2-BODY, P3-U_ARM, P4-F_ARM, P5-SHIN, P6-THIGH, P7-HAND and P8-FOOT, the same parts as the
costume system ([COSTUMES.md](COSTUMES.md#body-parts)). The header and how `CHR` picks a
sprite from the wrestler's parts are not decoded.

## Value tables

### Command types
Status byte 30. The names are the editor's (ov3 table 0x8007AB08, 57 entries; values not listed
are "( no support )" or blank).

| Value | Name | Move Edit slots |
|---|---|---|
| 0 | standing a b | Stand A, B (and C, A+B) |
| 2 | standing c a+b | Stand C, A+B |
| 4 | running a b | Run A, B |
| 6 | counter a b | Counter A, B |
| 8 | diagonal running c | Diagonal |
| 9 | running for outside c | Dive |
| 10 | outside from apron c | Plancha |
| 11 | inside from apron c | Apron |
| 12 | on corner a b c a+b | Post (and Run Dn) |
| 16 / 20 / 24 | grapple a / b / c a+b | Grab A / B / C, A+B |
| 29 / 30 / 31 | back a / b / c a+b | Back A / B / C, A+B |
| 35 / 36 | reverse back a / b | B.Rev A / B |
| 37 / 38 / 39 / 40 | upside head / upside leg / downside head / downside leg (b c) | UpHead, UpLegs, DnHead, DnLegs |
| 45 | corner grapple c | Corner |
| 48 | performance l r | Taunt |
| 50 / 51 | front two / three platoon | Front Duo / Trio |
| 52 / 53 | back two / three platoon | Back Duo / Trio |
| 54 / 55 | corner two / three platoon | Corner Duo / Trio |

### Classes
Status byte 0. The editor shows only the number; these names come from the moves that use
each value.

| Value | Name in moves.csv | Moves |
|---|---|---|
| 0 | strike | Standing, running and counter strikes; taunts |
| 1 | grapple | Every grapple, back, ground and corner move, and three diagonal moves |
| 2 | big strike | High Kick and other heavy standing strikes |
| 3 | lunging strike | Lariat Attack, Double-Leg Tackle: strikes that travel |
| 4 | diagonal run | Diagonal C |
| 5 / 6 | dive outside (strike / body) | Elbow Suicida / Tope, Plancha |
| 7 / 8 | top rope on downed (strike / body) | Diving Elbow Drop / Moonsault Press |
| 9 / 10 | top rope on standing (strike / body) | Diving Lariat / Diving Body Attack |
| 11 / 12 | double team / triple team | Duo and Trio slots |
| 13 | run at downed | Run Dn |
| 14 / 15 | combination (follow-up / opener) | Combination 1–3 (193–201) |

### Ratings
Status bytes 10 and 11. The index is the order of the ratings in the record and in Skill Edit.

| Index | Offence (record +0x5F + *n*) | Defence (record +0x69 + *n*) |
|---|---|---|
| 0 | Strikes | Strike Def. |
| 1 | Kicks | Kick Def. |
| 2 | Throws | Throw Def. |
| 3 | Submission | Sub. Def. |
| 4 | Chokes | Choke Def. |
| 5 | Power | Aerial Def. |
| 6 | Agility | Slam Def. |
| 7 | Strength | vs Lariat |
| 8 | Off. Skill | Def. Skill |
| 9 | Brawling | vs Brawling |

### Criticals
Status byte 19. Bits 0–5 say which critical types the move can trigger. Bit 6 lets the move make
the opponent give up, and bit 7 marks it as a foul. The match engine reads the byte when a move
lands, in the damage routine around ov0 0x80064e18.

| Bit | Editor label | Meaning | Moves with it (first ids) |
|---|---|---|---|
| 0 (0x01) | `cri normal` | Critical for type 0 (Finisher), only when the move is performed as the wrestler's finisher | 381 |
| 1 (0x02) | `cri dageki` | Critical for type 1 (Striking) | 27 |
| 2 (0x04) | `cri suplex` | Critical for type 2 (Suplex) | 13 |
| 3 (0x08) | `cri submis` | Critical for type 3 (Submission) | 44 |
| 4 (0x10) | `cri power` | Critical for type 4 (Power) | 27 |
| 5 (0x20) | `cri techni` | Critical for type 5 (Technical) | 30 |
| 6 (0x40) | `give up` | The move can make the opponent submit | 115 |
| 7 (0x80) | `hansoku` | The move is a foul (Bite, Low Blow, weapon attacks…) | 15 |

**Critical check** (ov0 0x80064a7c, per hit):
1. There is no critical if the attacker has state flag 0x40 (fighter +0x176).
2. The attacker's Critical type *n* comes from record +0x54.
   - Type 0 (Finisher): the move must be the finisher (fighter flag 0x80000) and have bit 0.
   - Types 1–5: the move must have bit *n* (mask table 0x80081848 = 1, 2, 4, 8, 0x10, 0x20).
3. If the move qualifies, the game rolls a chance from the table at 0x80081E0C, indexed by
   type × 13 + the defender's record +0x46. The chance doubles when the attacker has flag
   0x400 (+0x124) with HP (+0x128) below 0x1900 and spirit (+0x12A) above 0x4C00. A second
   roll, from 0x80081E5C, indexed by type × 16 + the defender's HP / 4096, must also succeed.

**When a critical lands** (0x8006515c):
- Every stat the move damages (status bytes 2–8 that are not 0) drops to 0 at once: HP,
  spirit, neck, arm, waist, legs, breathing.
- Without bit 3 or bit 5 (a striking, suplex, power or finisher critical), the defender is
  also knocked out: fighter flag 0x200000, and +0x156 = 0x140.
- A submission or technical critical leaves the defender conscious.
- A submission critical calls 0x80071084 with 0x5D (93, the "critical!" sound's number); the
  others call 0x8007103c. What those calls do is not traced.
- With bit 6, the defender gives up (flag 0x1000000).

**Give up, bit 6.** Without a critical, the move does its normal damage. The defender gives
up (flag 0x1000000) when either of these happens with a bit-6 move:
- the move takes their spirit (+0x12A) below 0;
- the move takes their HP below 0 under the match rule that makes that a KO (match flag
  0x93C & 4, flag 0x200000).

When the hold ends, the attacker's code checks the flag (ov0 0x8006dc7c). The defender then
plays the give-up motion and 0x8006f490 counts them as beaten. A hold without bit 6 can drain
a wrestler to nothing but **cannot win by submission**.

**Foul, bit 7.** It sets attacker flag 0x2000000 (0x8006530c). The referee code checks that
flag with the match rules (0x97A & 0x20) at 0x8006d934, 0x8006df88 and 0x8006e07c, presumably
for warnings or disqualification. Not traced further.

**Odd values on the disc.** Most same-named moves agree, but a few do not:
- **Arching Boston Crab**: face down (1345) is 0x41, Finisher + give up; face up (1248) is
  0x01, so it can't make anyone submit.
- **Haruki Special**: Grab C (891) is 0x49; Back C (1073) is 0x40.
- **Low Blow**: Grab B (782) is 0x81, a foul; Back A (1029) is 0x01, not a foul.
- Four moves can cause a submission critical but have no give-up bit: Joint Kick, Leg Sweep,
  Back Joint Kick and Knee Crusher. They are kicks and sweeps, so this may be intended.

The Critical types of the roster wrestlers:

| Value | Skill Edit | Wrestlers |
|---|---|---|
| 0 | Finisher | 142 (most) |
| 1 | Striking | 20: Misawa, Kawada, Maeda, the kickboxers |
| 2 | Suplex | 5: Steiner, Albright, Karelin |
| 3 | Submission | 16: Inoki, Shamrock, Fujiwara, Tamura |
| 4 | Power | 3: Vader, Andre, Norton |
| 5 | Technical | 8: Fujinami, Rey, Sasuke |

The stored values do not follow the order of the Skill Edit options (Finisher, Suplex, Power,
Technical, Striking, Submission). The screen converts between them with two tables in ov4:
0x80076694 maps option to value ([0, 2, 4, 5, 1, 3]) and 0x8007668C maps value to option
([0, 4, 1, 5, 2, 3]).

### Sounds
Hit sounds (header byte 5) and frame sounds (frame byte 11) index the editor's sound list (ov3
0x8007ABE8, 138 names). moves.csv writes the name.

| Index | Names |
|---|---|
| 0 | none |
| 1–5 | (system) move, select, entry, cancel, error |
| 6–8 | catch (sho / chu / dai: small, medium, large) |
| 9–52 | lv1–4 each of: tackle, head attack, elbow.knee, choppe, punch, body attack, high kick, low kick, jump kick, run attack, down attack |
| 53–59 | wind cutter 1–7 |
| 60–63 | guard lv1–4 |
| 64–68 | mat(step) 1–5 |
| 69–92 | lv1–4 each of: mat(normal), mat(highspeed), mat(bom), mat(dai), stretch, sub misson |
| 93–103 | critical!, poison fog, big fire, kakimushiri, fang, weapon sho / dai, weekpoint sho / dai, kama, corner crush |
| 104–110 | shoes noise sho / chu / dai, rope bound sho / chu / dai, touch |
| 111–114 | gong: fight, emergency, match end, match draw |
| 115–118 | grapple, down mat sho / chu / dai |
| 119–126 | drop down mat lv1–4, self bom mat lv1–4 |
| 127 | wrestler voice (plays the slot's shout) |
| 128–137 | mat(out of ring) lv1–4, fall out ring sho / chu / dai, fly drop out sho / chu / dai |

## Example: Punch

Move 1, from FPG 274 (96 bytes):

```
+00  00 00 04 00 00 00 00 00 00 00 00 00 06 00 00 00   class 0 strike, side 0, hp 4,
+10  00 00 00 00 db 00 0b 0a 00 00 00 00 00 00 00 00   ratings 0/0 (Strikes vs Strike Def.),
                                                       uses arm + waist, offset (-37, 0),
                                                       range 11 × 10, command 0 "standing a b"
+20  04 04 04 04 04 04 04 04 04 04 04 04 04 04 04 04   one animation: 1 header + 3 frames
+30  03 00 00 00 00 19 00 00 01 01 00 00               3 frames, hit sound 25 "punch lv1",
                                                       reversal type 1, rate 1
+3C  00 00 05 a4 09 f5 06 00 48 00 00 7f               form 0x5A4 for 6, d+tai, "wrestler voice"
+48  00 00 05 a5 09 f5 06 00 c8 00 00 40               form 0x5A5 for 6, a+d+tai (the hit), "mat(step) 1"
+54  00 00 05 a6 09 f5 08 00 48 00 00 00               form 0x5A6 for 8
```

Ids 2 and 3 are the same punch for the two diagonals: forms 0x5AA–0x5AC and 0x5A7–0x5A9, offsets
(−19, 19) and (−21, −21).

## Routines and tables

| Address | What |
|---|---|
| EXE 0x80018670 | Finisher name for a wrestler (first slot with 0x2000; edit wrestlers: record +0x1C8) |
| EXE 0x800186f4, 0x80019504 | Move name for a slot / by move id |
| EXE 0x8001c150 | Copy the story hero into the edit work area (+0x340 = 2, +0x16 = stage) |
| ov0 0x80080208 | Load FPG 252–258 for a match |
| ov0 0x80085640, 0x80085690, 0x800856e0 | Per-fighter block table: slot, variant, reverse map |
| ov0 0x80081EBC, 0x80081EC4 | Facing → variant (3-id and 2-id slots) |
| ov0 0x80064700 | Rating lookup (status bytes 10, 11) |
| ov0 0x80064a7c, 0x80081848, 0x80081E0C | Critical check, mask table, chance table |
| ov0 0x8006515c | Critical result: drain, knockout, give up |
| ov0 0x8006dc7c | Give-up check when a hold ends |
| ov0 0x8005be34 | Hit box from status bytes 20–23 |
| ov0 0x8007e6e0 | Shout on "wrestler voice" |
| ov4 0x80067680 | Choose the Move Edit list set |
| ov4 0x800681d0–0x80068418 | Move Edit buttons (shout, finisher, signature) |
| ov4 0x80079380, 0x80079B80 | Move Edit slot labels and button icons |
| ov4 0x80076694, 0x8007668C | Critical type option → value, value → option |
| ov3 0x80060bac, 0x800615d4, 0x800618e0, 0x800607e8 | Editor: unpack status, animation header, frame, form |
| ov3 0x8007AB08, 0x8007ABE8 | Editor: command type names, sound names |

## Exporting

```
python3 tools/movedata.py [--extracted PATH] [--text PATH] [--out-dir DIR]
```

It reads the unpacked disc (`tools/extract.py`): FPG 274, 010, 011 and overlay 004. It also reads
the English names from `text/`. It writes two files.

**moves.csv** has one row per move id with data (1,270):
- **id, name**: the move id and its English name.
- **variant**: 1–3, the move's position in its run of ids.
- **move_edit**: the Move Edit slots that offer the move.
- **level9_only**: "yes" for the two hidden moves.
- **story_from**: when the Fighting Road hero can first pick the move: start, middle or end.
- **roster_uses**: how many roster wrestlers have the move.
- **The status block**: one column per field, with the command type, ratings, critical types and
  body parts as names.
- **The attacker's animation**:
  - animations: the number of animations;
  - frames: the attacker's frame count;
  - duration: the sum of the attacker's frame times, in game frames;
  - local_forms: the number of local forms;
  - the header fields.

**wrestler_moves.csv** has one row per roster wrestler (194):
- **id, name, short**: the wrestler.
- **One column per slot** (stand_a … corner_trio), holding the move's name.
- **finisher, signature**: the slot and name of the finisher and of each signature move.
- **voice1_moves, voice2_moves**: the slot and name of each move that has a shout.

## How this was worked out

- The developers' editor in overlay 003 still has its screens: the field labels, the
  command-type and sound name tables, and the code that unpacks a move into its own structure.
  Following each label to the byte it prints gave the status block, the animation header and the
  frame fields. The block layout then checked out against all 1,270 blocks and the 567 basic
  motions with no exceptions.
- The match engine (ov0) confirmed the fields it reads: the hit box, the ratings, the hit counts,
  the critical mask, and the step from slot 0 to slot 1.
- Move Edit (ov4) gave the slots: its row labels, button icons, list sets and the code behind
  the finisher, signature and shout buttons.
- The data agrees:
  - every roster wrestler puts each move in a slot of its command type;
  - every offered id has data for all its variants, with the same name;
  - the critical types match the wrestlers' styles;
  - Punch hits on the frame flagged `a`.

## Open questions

- **Status byte 1** (`waza side`), **header byte 7**, and the limit, start and end modes.
- **Reversals**: the meaning of the reversal type and reversal rate values.
- **The frame fields** shd/fpr/rpr, the flags (dmg, bom, tai, sep, kan) and x/y/r. The names
  are the editor's; what each one does in a match is not traced.
- **Animations 2 and up**: the roles of the extra slots in dives, top-rope moves and team moves.
- **Forms**: the 6-byte header, and how `CHR` and the group select a sprite from FPG 251.
- **Directions**: the direction icons on the Grab, Back and Corner rows were read as up, toward,
  down and away from their order, not seen in the game.
