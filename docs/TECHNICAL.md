# Fire Pro Wrestling G — technical reference

How the PlayStation game Fire Pro Wrestling G (SLPS-02065, Human, 1999) is put together: the
disc, the data archive and its compression, what each file holds, and the formats worked out
so far. It is written from the translation project's reverse engineering. The tools named here
are in `tools/`. How the translation changes the game is in [PATCHES.md](PATCHES.md); hidden and
cut content is in [HIDDEN_CONTENT.md](HIDDEN_CONTENT.md); wrestler costumes, body parts and colours
are in [COSTUMES.md](COSTUMES.md); moves, move slots and the move data format are in
[MOVES.md](MOVES.md).

Conventions: numbers in `0x…` are hexadecimal. Addresses like 0x8005A718 are PlayStation RAM.
"u16"/"u32" are little-endian unsigned integers unless marked big-endian (BE). "FPG 251" is
entry 251 of FPG.BIN, and "ov4" is code overlay 004.

## Contents
1. [Disc layout](#disc-layout)
2. [The executable and memory map](#the-executable-and-memory-map)
3. [FPG.BIN: the data archive](#fpgbin-the-data-archive)
4. [Compression](#compression)
5. [FPG entry map](#fpg-entry-map)
6. [Code overlays](#code-overlays)
7. [Wrestler data](#wrestler-data)
8. [Wrestler graphics and Wrestler Make](#wrestler-graphics-and-wrestler-make)
9. [Moves](#moves)
10. [Story mode](#story-mode)
11. [Text and fonts](#text-and-fonts)
12. [Save data and progress](#save-data-and-progress)
13. [Audio](#audio)
14. [Images](#images)
15. [Debug code](#debug-code)
16. [Open questions](#open-questions)

---

## Disc layout

One MODE2/2352 data track with four files:

| File | Start sector (LBA) | Size (bytes) | Contents |
|---|---|---|---|
| SYSTEM.CNF | 23 | 68 | Boot configuration; runs `SLPS_020.65` |
| SLPS_020.65 | 24 | 274,432 | Main executable (PS-X EXE) |
| FPG.BIN | 158 | 42,397,696 | Data archive: code overlays, graphics, text, music, wrestler and move data |
| FPG.XA | 20860 | 221,128,704 | XA-ADPCM audio streams (Mode 2 Form 2 sectors) and the intro movie |

FPG.BIN ends exactly where FPG.XA starts, so it cannot grow. The translation's build therefore
rewrites it in place (`build.py`), and `tools/discpatch.py` regenerates the EDC/ECC error codes of
every changed sector (checked against the original sectors with `discpatch.py --verify`).

---

## The executable and memory map

SLPS_020.65 is a standard PS-X EXE: a 0x800-byte header, then code and data loaded at 0x80010000.

| Address | What is there |
|---|---|
| 0x80010000 | Start of the EXE. The first words are a table of each overlay's end address. |
| 0x800523d0 | FPG.BIN table of contents, read from disc at boot (EXE 0x80011e2c, 2 sectors) |
| 0x800541b0 | Pointer to the wrestler work area (+0x2fa0: pointer to the current wrestler record) |
| 0x800541b4 | Pointer to the save/system block (progress, unlocks; see [Save data](#save-data-and-progress)) |
| 0x800541c8 | Pointer to the current mode's work area (edit mode, Wrestler Make state) |
| 0x800541d0 | Pointer to the story state (0xFC8 bytes) |
| 0x8005410a / 0x80054134 / 0x80054120 | Pad 1: held / newly pressed / auto-repeat buttons (u16) |
| 0x8005A718 | Load address of every code overlay |
| 0x80092000 | Heap start while overlay 002 is loaded (free space for patches below it) |
| 0x1F800000 | Scratchpad; the decompressor's 1 KB ring buffer |

Useful EXE routines:

| Address | Routine |
|---|---|
| 0x8001c6b0 | Main loop (title, mode flow, hidden-combo check) |
| 0x80012c14 | Load FPG entry *n* into a buffer |
| 0x80012c90 | Load part of an FPG entry (offset, size) |
| 0x80012fe4 | Size of FPG entry *n* (from the TOC) |
| 0x80012028, 0x80012acc | Other FPG loaders |
| 0x80012620 | Load queue for { pointer, id, type } records (no callers) |
| 0x80012cdc | LZSS decompressor |
| 0x80012e0c | Small-ring LZ unpacker used for font glyphs |
| 0x80014900 / 0x80014824 | Memory allocation (size, name tag) |
| 0x80015f5c | Menu text renderer |
| 0x80016bc8 | Create a menu text window (cell budget, context) |
| 0x80016cf8 | Draw a string centred in a field (width at ctx+0x2e) |
| 0x800167d0 | Count the cells a string needs (sizes windows automatically, via 0x80017424) |
| 0x80017490 | Draw a string into a menu window |
| 0x80018430 | Build a wrestler's full name from short name, second part and flags |
| 0x800193ac / 0x800193dc / 0x8001940c | Wrestler short name / second part / nickname |
| 0x80018670 | A wrestler's text for the database screen |
| 0x800186f4 | Move name for a wrestler's slot (returns the custom finisher name, edit record +0x1C8, when set) |
| 0x80019e2c | Copy a roster wrestler's costume and colours (Wrestler Make); the other costume and colour routines are listed in [COSTUMES.md](COSTUMES.md#routines) |
| 0x80019cf4 / 0x80019c8c | Promotion short / full name |
| 0x80019504 | Move name by move id |
| 0x8001a614 | "Story cleared": unlock all wrestlers, set the cleared flag |
| 0x8001a65c / 0x8001a678 | Read the story-cleared flag / Edit Ranking reward level |
| 0x8001a694 | Set the Edit Ranking reward level |
| 0x8001de90 / 0x8001e9bc | Wrestler-figure object system: init / update and draw |
| 0x80017974 | Developer mode-select menu (unused in retail) |
| 0x800146e8, 0x80015270 | Developer printf and number input (empty stubs in retail) |

---

## FPG.BIN: the data archive

`tools/fpgbin.py` unpacks and repacks it; a round trip is byte-identical.

```
0x0000  TOC: 291 entries of { u32 offset, u32 size }, then a terminator { archive end, 0 }
0x1000  first entry; every entry starts on a 0x800-byte (sector) boundary
```

- Sizes are the stored size: compressed entries store their compressed length. Whether an entry
  is compressed is not marked in the archive; the code that loads it knows.
- Because the EXE reads the TOC from disc at boot, entries can move and grow as long as the whole
  archive keeps its size. The build packs entries back to back. About 50 KB of slack remains in
  the patched build.

---

## Compression

Most entries are LZSS-compressed (`tools/lzss.py`; decoder at EXE 0x80012cdc):

- 1 KB (0x400-byte) ring buffer, zero-filled, write position starting at 0x3BE.
- A flag byte precedes each group of 8 items, read least significant bit first: 0 = literal byte,
  1 = back-reference.
- A back-reference is two bytes `b0 b1`: ring position `b0 | (b1 & 0xC0) << 2`, length
  `(b1 & 0x3F) + 3`. The position is absolute in the ring, not relative.
- No header: the caller passes the compressed size from the TOC.

The project's compressor uses lazy matching and produces slightly smaller output than the
original tool.

A second, tiny LZ (EXE 0x80012e0c) packs font glyphs and several match data sets (the basic
motions in FPG 259, the referee sprites in FPG 260–266): a 32-byte ring, zero-filled, write
position starting at 0x17; flag bytes as above; a reference is one byte with ring position
`b >> 3` and length `(b & 7) + 2`. The caller passes the packed size. Each item in those files is
packed separately and found through the file's own offset table.

---

## FPG entry map

C = LZSS-compressed, R = stored raw. Sizes are as stored; "→" gives the unpacked size.

| Entry | C/R | Contents |
|---|---|---|
| 000–005 | C | Code overlays (see [Code overlays](#code-overlays)) |
| 006 | R | XA index: 8 { start sector, size } pairs into FPG.XA |
| 007 | R | VAB header of a small sound bank (5 programs, 6 samples), loaded at boot (EXE 0x80015510 → SsVabOpenHead / SsVabTransBody through 0x800139dc) |
| 008 | R | That bank's sample data (raw ADPCM, 25,408 bytes = the header's sample sizes) |
| 009 | C | Menu font (proportional widths patched by the translation) |
| 010 | C | Roster: 194 wrestler records × 426 bytes |
| 011 | C | Container: menu font copy (+0x18), roster copy (+0x1046C), roster colour table (+0x24740, [COSTUMES.md](COSTUMES.md#the-colour-table-fpg-011)), move name table (+0x30A38) |
| 012 | R | Title screen: a compressed 320×240 8-bpp TIM at +0x14 |
| 013 | R | Fresh save data: 30 bonus edit wrestlers (+0x4E28) and their profiles (+0x8A28) |
| 014 | C | PocketStation save template (title at +4) |
| 015 | C | Head presets for Wrestler Make: 109 × 78 bytes (stance, size, 8 part numbers, 34 colours) |
| 016 | R | Edit records: a sample wrestler and Coach Yamamoto |
| 017 | R | Dojo tutorial text |
| 018 | C | Outline-effect wrestler figure (240×208, 17 palettes); use unknown |
| 019–090 | C | 72 arena texture sheets (ring aprons, banners, crowd) |
| 091–095, 097 | C/R | Small UI images (TIM; 092 raw, the others compressed) |
| 093 | C | Small title logo (160×131) |
| 096 | R | Six screen test patterns (compressed TIMs inside; hidden viewer) |
| 098 | R | VAB header of the menu/system sound-effect bank (21 programs, 48 samples); loaded by the title screen and the game-flow code (EXE 0x8001b6dc) |
| 099 | R | That bank's sample data (raw ADPCM, 350,080 bytes) |
| 100–124 | R | Music sequences (SEQ) |
| 125 | C | A music sequence plus the VAB header of its own instrument bank (5 programs, 13 samples); loaded by overlay 004 (0x80071900) |
| 122 | R | SEQ only reachable from the sound test |
| 126 | R | Sample data for the bank in 125 (raw ADPCM, 127,968 bytes) |
| 127 | C | Story hero templates: Sakagami's four versions (edit records) |
| 128 | R | Story font (Shift-JIS, 20×32 glyphs) |
| 129 | R | Story mode music: u32 offset table, 20 LZSS-compressed SEQ songs and an empty slot; loaded by overlay 002 (0x8005f590) with the story font and script index |
| 130 | R | Story script index: start sector of each scene in 131 |
| 131 | R | Story script: 522 scene blocks |
| 132–142 | R | Story backgrounds, 512×320 BS (MDEC) pictures |
| 143–247 | C | Story character portraits (32×32 tiles) |
| 248–249 | R | TIM images |
| 250 | R | Hit-effect sprites (128×128, 4-bit TIM); loaded only by the overlay 003 programs |
| 251 | R | Wrestler graphics archive: heads and body parts ([COSTUMES.md](COSTUMES.md#body-parts)) |
| 252–258 | C | Move data: 1,600 u32 offsets by move id, then the blocks ([MOVES.md](MOVES.md#the-move-block)) |
| 259 | R | Basic motions for matches: 640 u16 offsets, then each motion packed with the small LZ (475 used). Unpacked, identical to FPG 273. Loaded with the move data (ov0 0x80080208); ov0 0x8008055c unpacks motions from match state +0x48 |
| 260–267 | R | Referee sprites, one pair per referee (Referee setting 0–3: T. Hattori, J. Higuchi, Soranaka, T. Tanabe, per the ov1 name table 0x80088e44): the even entry holds 1,040 16×16 4-bit tiles (u32 offsets, each packed with the small LZ to 128 bytes; unpacked by ov0 0x8007fb7c from +8), the odd one a big-endian table (from +0xc) that assembles them into frames. Loaded by ov0 0x8007f6c8 (FPG 260 + 2 × referee, 261 + 2 × referee), which also uploads one of four palettes, (referee × 4 + 0–3) from 0x80085430 to the rectangle at 0x80085428 (Left/Right/Down held at match load) |
| 268, 269 | R | VAB sound banks (2.2 MB and 10.3 MB) |
| 270 | R | Global forms (poses): 4,032 (0xFC0) × 96 bytes, the forms move frames 0–0xFBF point at ([MOVES.md](MOVES.md#forms)). Loaded raw by matches (ov0 0x8007ded4, to match state +0x4c, a buffer the sound-bank loader 0x8007df48 also uses) and edit mode |
| 271 | R | 5,820-entry offset table and data: animation data for the wrestler-figure system (loaded by EXE 0x8001de90; format not decoded) |
| 272 | C? | Loaded with 271 by the wrestler-figure system (format not decoded) |
| 273 | R | Basic motions, uncompressed (640 u32 offsets; 475 used), loaded by edit mode (ov4 0x800735e8). Same layout as a move block ([MOVES.md](MOVES.md#the-move-block)) with an empty status block and no local forms: walking, reactions and similar, indexed by action number |
| 274 | R | Uncompressed copy of all move data (identical to 252–258): 1,792 { u32 offset, u32 size }, one sector-aligned block per move id |
| 275 | R | Unused illustrations: u32 offset table, 13 LZSS-compressed 8-bit TIMs (entries 3–7 640×480, the rest 320×240) and an empty 14th slot. Never loaded |
| 276 | R | 8×8 debug font: 4-bit TIM, 16×16 grid of ASCII glyphs (used by overlay 003) |
| 277 | C | Big texture sheet: mode-select names, select-screen labels, tags, arena thumbnails |
| 278, 287–289 | C | Full-screen and UI images (TIM) |
| 279–285 | C | Victory / title screens (photo plus caption strip) |
| 286 | C | Character list for the name-entry grid |
| 290 | R | Promotion logos: 35 u32 offsets, 34 LZSS-compressed images (16-colour palette + 96×96 4-bit), shown by overlay 005 (0x80061a0c uploads one to VRAM (608, 256)). Four contain Japanese text (梶原組, 春樹軍, 真誠倒幕, いきぐにプロレス) |

---

## Code overlays

Entries 000–005 are compressed code modules. All load at 0x8005A718, and the first word of each
is its id (4–9). The EXE's table at 0x80010000 gives each overlay's end address. The space after
an overlay's end, up to its work area, is free for patches; the translation puts its text hooks
and string pools there.

| Entry | Unpacked | Used for |
|---|---|---|
| 000 | 179 KB | Matches (the match engine, hit effects, ring view) and the Dojo tutorial |
| 001 | 193 KB | Mode select, match setup, wrestler select screen |
| 002 | 120 KB | Title screen and Fighting Road (story mode) |
| 003 | 145 KB | Developer move/animation editor ("anime tool"); unused in retail |
| 004 | 133 KB | Edit mode (Wrestler Make, Skill Edit, Move Edit, CPU logic), Edit Ranking, options, memory card |
| 005 | 152 KB | Database and sound test (debug), test patterns, name entry, image prompts |

### Overlay 003 (developer tools)

Entry points, from the dead "yone process select" (EXE 0x8001ef00, jump table 0x80010a58):
0x800747b0 the editor shell ("GED"), 0x8007610c and 0x800758c0 two sprite tests,
0x800769d0 an SE test (printf). Each runs its own loop and returns when the auto-repeat pad
word (0x80054120) equals 0x00C0 (Square + Cross).

- Shell: allocates the editor state (`*0x8007db68`, 0xE4E0 bytes) and two draw buffers
  (GEDDB0/1, 0x1778 bytes each: a GsOT header at +0x1360 with its order table at +0x1374).
  It loads FPG 276 to VRAM (960, 384) and then FPG 250 to (961, 380), on top of it. Per frame
  it calls two empty stubs (0x80074b10, 0x80074b18) where the editor was called.
- Editor: init 0x8005f0a0, per frame 0x8005f154, exit 0x8005f134; nothing calls them.
- Text (0x80074ff0): codes `{` + x, y bytes (cursor, in 8-pixel cells), `@n` (colour = CLUT row
  448 + 16n), newline. Glyph slots come from counter 0x8007db74 (1,000 per buffer, 40-byte
  POLY_FT4 each, in a 0x14000 buffer at `*0x8007db64`); they are linked into the order table
  at 0x8007db6c. Only the uncalled 0x80074f0c resets these. The retail glyph code uses
  `char & 0x50` and u = 0, so it cannot draw the font correctly.
- Pads: each frame the editor copies every controller slot's held, pressed and repeat words,
  mouse dx/dy and device type. It reads the mouse from slot `+0x28 - 1` and sets +0x28 to 5
  (slot 4, port 2 behind a multitap). Clicks are slot button masks 0x44 / 0x28 (mouse button
  bits or Cross / Circle). The cursor is +0x48 / +0x4c (0–639, 0–447).
- No file or device I/O is left; the only disc reads are FPG 251 (body parts, 0x800755a4,
  requested through +0x628). Poses are drawn with the game's sprite renderer 0x8001cd24.
- TEST 12 (0x800758c0): 640×480 (GsInitGraph 640, 480), a 0x4B120-byte buffer (`*0x8007db8c`
  +8) for an 8-bit 640×480 TIM. Circle: CLUT to (0, 511) via 0x80014f18, pixels +0x220 and
  +0x25A20 to (640, 0) and (640, 256), then 20 8-bit POLY_FT4 tiles. No code fills the buffer
  (0x80075a0c allocates 0x20000 and frees it). The buffer is 256 bytes short of a full TIM
  (0x4B220), so the second upload reads past it.
- SE TEST (0x800769d0): reads the pressed word at pad +0xc. Select, or Left/Right on row 0,
  toggles the page (+0x28); Up/Down change the row (+0x2c); Circle or L2 (0x21) plays, and on
  row 0 sets +0x24 (exit); Square (0x80) plays a key-on test note; Triangle (0x10) calls
  0x800366bc (all keys off).
- TEST 11 (0x8007610c): runs the wrestler-figure object system (see
  [Wrestler-figure objects](#wrestler-figure-objects-exe)) plus one FPG 250 frame drawn by
  0x80075e2c at (160, 120). Its backdrop is five 15-bit POLY_FT4 panels sampling VRAM (320+, 256).
  It prints `%03d/%03d` of 0x80054150 / 0x80054154 each frame.
- The debug build's repairs to these programs are described in [PATCHES.md](PATCHES.md#debug-menu-and-route-5).

---

## Wrestler data

### Roster record (426 bytes; FPG 010, copies in FPG 011 and overlay 005)

| Offset | Size | Field |
|---|---|---|
| +0 | 1 | Division: 0 X, 1 Heavyweight, 2 Junior Heavy, 3 Freelance |
| +1 | 1 | Name flags: 0x80 = second part first; low nibble = separator (0 space, 1 "・", 2 "＝", 3+ none). The translation adds 0x20 = "second part only". |
| +2 | 14 | Short name (shown alone in lists) |
| +16 | 20 | Second name part |
| +36 | 26 | Nickname |
| +62 | 1 | Height |
| +63 | 1 | Weight |
| +64 | 1 | Birthplace |
| +65..+67 | 3 | Birth year − 1900, month, day |
| +68 | 1 | Promotion |
| +69 | 1 | Fighting style |
| +70.. | | Skills, ratings, reversal style, special skills, theme music, voices… (Skill Edit fields) |
| +0x5C | 1 | Stance (0–8, Strong … Kobudo) |
| +0x5D | 1 | Size (0–2: S, M, L) |
| +0x74..+0xE5 | 57 × u16 | Move slots: move id = value & 0x7FF; 0x1000 signature, 0x2000 finisher, bits 14–15 shout ([MOVES.md](MOVES.md#move-slots)) |
| +0x182..+0x1A9 | 4 × 10 | Costumes 1–4: u16 head id, then 8 body part numbers ([COSTUMES.md](COSTUMES.md#roster-record-fields)) |

A roster wrestler's colours are not in the record. They come from the colour table in FPG 011,
one set of 34 colours per wrestler and costume ([COSTUMES.md](COSTUMES.md#the-colour-table-fpg-011)).

### Edit record (512 bytes; save data, FPG 013/016/127)
The same layout up to the moves, plus:

| Offset | Field |
|---|---|
| +0x5C, +0x5D | Stance, size |
| +0x184..+0x1C7 | 34 colours (15-bit; groups and palettes in [COSTUMES.md](COSTUMES.md#colours)) |
| +0x1C8 | Custom finisher name (EXE 0x800186f4 returns it instead of the move name; overlay 001 copies 28 bytes; the field runs to +0x1F2) |
| +0x1F2 | u16 head id |
| +0x1F4..+0x1FB | 8 body part numbers |

### Edit Mode tables (overlay 004)
*From the code* (read for the player's guide, 2026-10-29; `tools/guidedata.py` reads the
tables marked with it).

- **Skill Edit rows** (0x80076954, 20 bytes each; `tools/skilledit.py`): +0 flags (byte 0 value
  box cells; byte 1 low nibble row type, high nibble cost table; byte 2 minimum; byte 3
  maximum), +4 option list, +8 suffix, +12 label, +16 record offset. Rows 33–38 are a second,
  short form (Div, birth date, Origin: Amateur, Judo, Karate, Gymnastics, Sumo, Weightlifting,
  Thug, None), apparently the Fighting Road hero's setup. *guidedata.py*
- **Critical order:** Skill Edit lists the types in another order than the record stores them;
  0x8007668C maps stored value → option (0, 4, 1, 5, 2, 3), 0x80076694 the reverse. *guidedata.py*
- **Edit points:** one budget for Skill Edit and Param. Edit; the limit is a u16 at edit
  record +0x182. Points used = the cost of each Skill Edit choice (8 cost lists at 0x80076C94,
  by option: Critical 0/20/20/25/30/30; Special 0 then 15; Recovery, Breathing, Spirit
  0/10/20 and their bleeding rows 0/5/10; Neck/Arms/Back/Legs 0/2/5; Speed 0/2/6/14/24; Climb
  0/2/4/6/8; Post 0/4/12) plus, for each of the 20 ratings, its shown value − 1. Every one of
  the 30 Edit Ranking wrestlers fits its limit under this rule. Param. Edit shows a rating as
  the stored byte − 2 (1–10).
- **CPU Logic** (record +0xE6, 156 bytes): situations at 0x80074DFC (8 bytes: label, first
  condition, count), conditions at 0x80074E8C (label, first action, count, data index),
  actions at 0x80074FBC (label, u16 code: < 0x200 the Move Edit slot × 2, 0x200 no move,
  0x201–0x203 actions without a slot). A condition's bytes are **cumulative thresholds** for
  all its actions but the last: an action's chance is its threshold minus the one before, and
  the last action takes what is left of 100 (checked on the roster: each row rises to 100 at
  most). *guidedata.py*
- **Edit Ranking rewards by wins** (0x8005C160, 30 bytes by the win count after a win; the
  save's reward level is raised when the table's value is higher; 0x8005C180 flags the
  reward message): level 1 at 4 wins, 2 at 7, 3 at 8, 4 at 13, 5 at 15, 6 at 16, 7 at 19, 8 at
  23, 9 at 24, 10 at 28, 11 at 29. Each win also adds an edit point. Not checked in game, nor
  whether the count is per wrestler.

### Specials and ratings in a match (overlay 000)
*From the code.* The match start (0x80074040) turns Skill Edit's Special into one bit of
fighter +0x124 (table 0x8005B028). HP and spirit run 0–0xFFFF.

| Special | Effect | Where |
|---|---|---|
| Star Power | moves × 4506/4096 (+10%) when HP < 0xA00 and bit 0x10000 of +0x124 is set (what sets it is not traced) | 0x800649E8 |
| Quick Up | down time / 8 when knocked down with HP 0xC01–0x32FF and spirit > 0x9900 | 0x80065B18 |
| Comeback | critical chance × 2 when HP < 0x1900 and spirit > 0x4C00 | 0x80064BAC |
| Fast Start | signature moves +2 (not +1) to both attack ratings while HP > 0xB333 | 0x8006476C |
| Guts | spirit damage halved when HP < 0x200 | 0x800650B4 |
| Fightback | +1 to both attack ratings when HP < 0x500 | 0x800647A8 |
| One-Hit KO | the finisher × 2.5 for its first two uses (counter +0x196) | 0x80064A34 |
| Bleeding | moves × 4301/4096 (+5%) while bleeding (+0x120 bit 8) | 0x800649AC |

A move's strength factor (0x80064700) is 3 × the attacker's main rating + his second rating −
3 × the defender's main defence − his second defence + 64, then scaled by tables not yet
decoded; the finisher adds 2 to both attack ratings, a signature move 1.

### Promotions
Full names (15 × 26 bytes at EXE 0x80049054) and short names (15 × 14 bytes at 0x800491DC).
Ids of 15 and up are player-made promotions in the save data.

---

## Wrestler graphics and Wrestler Make

### FPG 251: graphics archive
```
0x0000  871 entries of { u32 offset, u32 size }  (data starts at 0x2000)
```
| Entries | Contents |
|---|---|
| Entries | Contents (Wrestler Make label) |
|---|---|
| 0–319 | Heads (Face; index = head id) |
| 320–395 | Part byte 0: chest (Chest) |
| 396–517 | Part byte 1: trunks (Waist) |
| 518–588 | Part byte 2: upper arms (Bicep) |
| 589–655 | Part byte 3: forearms (Arm) |
| 656–713 | Part byte 4: shins and knees (Shin) |
| 714–810 | Part byte 5: thighs (Thigh) |
| 811–832 | Part byte 6: hands (Wrist) |
| 833–870 | Part byte 7: feet (Ankle) |

A head is entry *head id* (edit record +0x1F2). Part byte *s* (record +0x1F4 + *s*) is entry
`base[s + 1] + part number`; the bases are a table in ov4 at 0x80079F60. The loader is ov4
0x80073820 (FPG 0xFB through EXE 0x80012c90). Part entries are LZSS-compressed 4-bit tiles
(24 × 24, or 16 × 16 for hands and feet). Heads use a format that is not decoded yet. Which
palette draws each part, and the colour groups, are in [COSTUMES.md](COSTUMES.md#body-parts).

### Wrestler Make tables (overlay 004)

- **Category rows** (0x80076478, 20 bytes each; Wrestler Make itself is 0x80061254): list
  pointer, slot, type, then the number of list items available at each Edit Ranking level 0–11
  (+6..+17), then the total (+18). Rows 3–10 are the body-part categories; row 2 counts the head
  list (count + 255).
- **Part lists**: 12-byte entries { name pointer, variant count, 4 part numbers (one per variant),
  padding }. Variants are the build-dependent versions of a part.
- **Head list** (0x80076220): u16 head ids, 299 entries: 0–276, then 290, 292–298, 282, 283,
  289, 303, 300, 301, 284, 288, 285, 286, 306, 307, 304, 302. A head id under 194 copies that
  roster wrestler's costume 1, colours, stance and size (EXE 0x80019e2c). Positions 194 and up
  load preset (position − 194) from FPG 015 instead.
- **FPG 015 presets** (109 × 78 bytes): stance, size, 8 part numbers, 34 colours (the layout of
  edit record +0x5C/+0x5D, +0x1F4 and +0x184). Presets 105–108 lie past the end of the head list
  (105 is a copy of 104).
- When the screen opens, the game finds each list position by searching for the record's current
  value (0x800628ac). Inserting new items therefore doesn't disturb saved wrestlers.

---

## Moves

Moves are documented in [MOVES.md](MOVES.md): the 57 move slots and their flags, the Move Edit
lists, variants, and the move block (status block, animations, frames and forms). In short:

| Data | Where | Format |
|---|---|---|
| Names | FPG 011 at 0x30A38 | 1,592 u16 offsets (relative to the table) to NUL-terminated Shift-JIS names |
| Move data | FPG 252–258 | Each: 1,600 u32 offsets at the start (indexed by move id), then the move blocks |
| Uncompressed copy | FPG 274 | 1,792 { u32 offset, u32 size } pairs; one sector-aligned block per move id |
| Global forms | FPG 270 | 4,032 × 96-byte poses |
| Move Edit lists | ov4 0x80078C60 (normal), 0x800791B8 (Edit Ranking level 9), 0x80078FF0 / 0x80078E28 (Fighting Road hero, early stages) | 57 { list pointer, count } per set |

- The match loader (ov0 0x80080208) reads all seven of FPG 252–258. The byte table at ov0
  0x80081EBC maps a wrestler's facing to a move variant; it does not choose files.
- Moves come as runs of 1–3 consecutive ids with the same name: variants for different facings.
  A slot stores the first id.
- The four list sets together offer 962 first ids, 1,264 ids with their variants. Roster
  records use 892 first ids, all of them offered. 113 named ids are offered by no set and used by
  no wrestler ([HIDDEN_CONTENT.md](HIDDEN_CONTENT.md#named-moves-that-were-cut)).

---

## Story mode

### Script files
- **FPG 130**: u16 start sector of each scene within FPG 131. 522 scenes plus an end marker.
- **FPG 131**: scene blocks, each starting on a sector boundary (BE u16 fields):

```
+0  0x0004
+2  T = offset of the text table
+4  label table: u16 offsets relative to +4 (its first entry also gives its length)
    bytecode, up to T
T   message offsets relative to T (count = first offset / 2)
    NUL-terminated Shift-JIS messages, lines separated by CR LF
```

The Japanese script has 9,428 messages, about 538 KB of text; the scenes use 633 KB of the
1.25 MB file. Original lines are at most about 22 full-width characters, and the story box shows
3 lines of about 21.

Overlay 002 holds one more scene block of its own (0x80064B98; header 0x0004, text table at
+0x64): the save prompt and the pre-match "Ready for the match?" choice. It is reached through
two `lui`/`addiu` pairs (0x8005DB74/78, 0x8005DBC0/C4).

### Scene bytecode
The interpreter is ov2 0x8005DD94, with 57 opcodes (jump table 0x8005A818). Operand sizes are in
`tools/storyflow.py`. Main opcodes:

| Op | Meaning |
|---|---|
| 00 | End scene |
| 02 | Show message *n* |
| 04 / 05 | 2- / 3-way choice (message, labels) |
| 17 | Jump to label |
| 1C | Go to scene (low + 100 × high) |
| 1E | If the last match was lost, jump |
| 21 | Graduation offer: pick a promotion, jump to label base + result (scene 3 only) |
| 22 | Jump by the stored offer result |
| 23 / 24 / 2B | Add to a promotion affinity / a stat / Star Points |
| 25 | Developer prompt "VIEW JAPAN BRANCH" (unused) |
| 26 | Set the next scene |
| 27 / 28 | Set / test Champion |
| 29 / 2A | Star Points / stat at least a value |
| 2C | End Fighting Road (ending) |
| 2D–33 | Flags |
| 37 | If the given style is the player's top style |

All 522 scenes parse exactly up to their text tables. A scene returning 3 ends Fighting Road
(ov2 0x8005ffd4), which runs the "clear all" routine 0x8001a614.

**Graduation offer** (opcode 0x21, ov2 0x8005e848, scene 3 only): a hero who is not a
heavyweight (player record byte 0 ≠ 1, inferred) gets route 6, Michinoku Pro. Otherwise the top
style adds +3 / +1 to promotion affinities and the highest of NJPW, AJPW, FMW, UWF and America
wins (ties go to NJPW, AJPW, FMW, America, then UWF), giving routes 0–4. The route is stored at
state +0x3f and the opcode jumps to label 3 + route; opcode 0x22 jumps by it later. Route 5 is
never produced (see HIDDEN_CONTENT.md). Affinities 5 and 6 are raised by some scenes but never
read.

### Wrestler-figure objects (EXE)
The animated wrestler figures shown outside matches (and in overlay 003 TEST 11) use a small object
system. 0x8001de90 allocates its state (`*0x800541d8`), loads FPG 271 and 272, and resets five
objects (0x8001ead0); 0x8001e9bc updates and draws them. Objects are 0x734 bytes from state +0x24
(0x8001ea98(i) returns object *i*):

| Offset | Meaning |
|---|---|
| +0x00 | Flags: 0x01 shown, 0x04 mirrored, 0x08 animation frozen, 0x10 extra sprite; 0x02 is not read |
| +0x02 | Wrestler id (-2 = the edit wrestler in the state's +0x18 record) |
| +0x04, +0x06 | Screen position |
| +0x0A | Draw value, 128 after reset (probably brightness or size) |
| +0x12, +0x14, +0x30 | Animation frame, its timer and the time it started |

### Story battles (overlay 002)
- 0x800662a0: 520 s16, the battle number of each scene's match (-1 = no match). 364 scenes have a
  match, using battle numbers 0–355; a few battles are shared by several scenes.
- 0x80064f28: one 14-byte record per battle, read by the match setup 0x800600f0:

| Offset | Meaning |
|---|---|
| +0 | Rules preset: index into 6-byte presets at 0x80064dcc {venue → +0x981, ring → +0x982, u16 rule flags → +0x97a, rules → +0x97c, referee → +0x984} |
| +1 | COM level 1–6 (minus 1 → +0x983) |
| +2 | Wrestlers: 2 = singles, 4 = tag |
| +4 / +6 / +8 | u16 opponent (match slot 2), opponent's partner (slot 3), hero's partner (slot 1); the hero is slot 0 |
| +10 | Copied to story state +0x49 |
| +13 | Match music (+0x985); 9 = random 0–3 |
| +3, +11, +12 | Not read by the setup |

  Wrestler ids: low 9 bits = roster index, bits 9–10 = a variant 0–3 (EXE 0x8001938c);
  0xFFF0–0xFFF3 = FPG 127 records 8–11 (Sakagami's four versions). Venue names come from ov1
  0x80088df8 by setting +0x981 (0 Nippon Budokan, 1 HUMAN DOME, 2 Yurakuen Hall, 3 Murakawa Town
  Gym, 4 unnamed, 5 Bayside Coliseum, 6 Kawashima Stadium). `tools/storybattles.py` writes every
  battle to `docs/story_battles.csv`; the route map shows opponents and venues, and the scene panel
  the full match settings.

Match settings (`*(state+0x968)`, set by the match-setup screen in overlay 001 and by the story
battles), named from overlay 001's option labels (0x80088cf8, indexed by option id) and value
tables:

| Setting | Option | Values |
|---|---|---|
| +0x978 | Game Speed | u16, 0x100 = 100% |
| +0x97a | Rule flags | bit 0x01 = 2 of 3 falls (else 1 fall); ON when set: 0x02 Rope Check, 0x04 Lumberjack, 0x08 Tornado, 0x10 Cut Play, 0x20 Foul Count, 0x40 COM Skip, 0x80 Ring-out Count; 0x100 and up are not options (0x2000 = Dojo tutorial) |
| +0x97c | Rules | 0 3-count, 1 2-count, 2 pinfall only, 3 submission only |
| +0x97d / +0x97e | Blue / Red corner | controllers |
| +0x97f | Time Limit | 0 in story matches |
| +0x981 | Venue | names at ov1 0x80088df8; 4 is unnamed (the dojo) |
| +0x982 | Ring | ring value 0–15 (EXE 0x800103a0 maps menu positions to values; names at EXE 0x800492b0 by position): 0 New Japan, 1 nWo, 2 All Japan, 3 FMW, 4 WAR, 5 Michinoku Pro, 6 WCW, 7 RINGS, 8 S-1, 9 Pancrase, 10 AAA, 11 HWA, 12 WWF, 13 BattlArts, 14 UWF, 15 Tobaku-gun; 0x20 special death match ring, 0x40 octagon, 0x7f random |
| +0x983 | COM Level | 0–9, shown as 1–10 |
| +0x984 | Referee | 0 T. Hattori, 1 J. Higuchi, 2 Soranaka, 3 T. Tanabe (4 in the dojo) |
| +0x985 | Match BGM | 0 Ring-Side, 1 Biorhythm, 2 Fujiyama, 3 Blue-Thunder, 4 FR:GOOD, 5 FR:BAD, 6 Musashi's Theme, 7 Hikawa's Theme (titles at EXE 0x800492f0) |
| +0x986 | Bomb Timer | |
- Venue 4 and referee 4 appear only in battles 0–2, the prologue training matches (EXE
  0x8001cbf8 sets up the Dojo tutorial the same way: venue 4, referee 4, flags 0x2704). Across
  the story, 283 matches use 3-count rules and 73 submission only (the shoot rings: RINGS, UWF,
  Pancrase, HWA); all are one fall; music is FR:GOOD in 20, FR:BAD in 12, Fujiyama in 3 and
  random in the rest.
- The match-setup screen's option handler is a jump table at ov1 0x8005aae8 (option id →
  setting); values are displayed by ov1 0x800600f0 / 0x80060290 from value tables (a set ON/OFF
  bit shows "ON", 0x80060350). Ring names are looked up by menu position (EXE 0x8001a580), music
  titles by EXE 0x8001a800.
- 0x80060edc(n) plays battle *n* directly: it finds the first scene with that battle number,
  stores the scene at story state +0x16 and runs its match. Debug mode 5 (BATTLE SELECT) calls it
  through EXE 0x8001ca9c with a fresh story state.

### Story state (`*(0x800541d0)`, 0xFC8 bytes)

| Offset | Field |
|---|---|
| +0x16 / +0x18 | Current scene / next scene (−1 = current + 1) |
| +0x1A | Star Points |
| +0x1C / +0x1E / +0x20 | Ambition / Babyface / Passion |
| +0x22 | 7 promotion affinities (NJPW, AJPW, FMW, UWF, America, two unused) |
| +0x2A | 10 style counters (striking, submissions, throws, power, technique, flying, rough, performance, shoot, chokes) |
| +0x3E / +0x3F / +0x40 | Last match result / graduation route / Champion |
| +0x54 | The hero's wrestler record (512 bytes) |
| +0x704 | Buffer for the current message after name codes are expanded (about 2.2 KB) |

The field names come from the developers' debug dump in ov2 (`YASIN`, `BABY FACE`, `NEKKETU`…).
After a scene ends, the main loop (0x8005FF34) plays the scene's match from a table at 0x800662A0
(14-byte records at 0x80064F28: match type, opponents, partner), then moves on to the next scene.

### Text codes in messages
The preprocessor (ov2 0x80061c90) expands codes into state +0x704 before a message is shown and
copies other bytes unchanged:

| Code | Expands to | Routine |
|---|---|---|
| `#MS` / `#MF` | The hero's short / full name (id 0x8000) | EXE 0x800193ac / 0x80018430 |
| `#WSnnn` | Wrestler *nnn*'s short name (record +2) | EXE 0x800193ac |
| `#WLnnn` | Second name part (+0x10) | EXE 0x800193dc |
| `#WNnnn` | Nickname (+0x24) | EXE 0x8001940c |
| `#WFnnn` | Full name | EXE 0x80018430 |
| `#PSnn` / `#PLnn` | Promotion short / full name (ids 15 and up are player-made) | EXE 0x80019cf4 / 0x80019c8c |
| `#Snn` | A save-slot line | |

Any other code goes to a printf stub and copies nothing. The expansion buffer is about 2.2 KB,
so there is no practical length limit. Scene 401 message 2 uses `#MF00`, which prints the full
name followed by "00".

---

## Text and fonts

### Story text
- **Font** (FPG 128): header { u32 map offset (0x18), u32 data offset (0x3818), u32 end × 4 }; a
  u16 map from linear Shift-JIS index to glyph number (1,981 glyphs); then u32 offsets to glyphs
  packed with the small LZ. Each glyph unpacks to 20×32 pixels at 4 bpp (16-level anti-aliasing).
  The full-width Latin glyphs are drawn proportionally within their cells
  ([ascii_fullwidth_glyphs.png](ascii_fullwidth_glyphs.png)).
- **Typewriter** (ov2 0x80063344): one step per character, drawing it with 0x80062e54
  (Shift-JIS high, low byte, text window); the pen advances 20 + spacing (window +0x2a). Its
  single-byte branch (0x8006368c) handles only 0x0A and skips every other single byte, so ASCII
  is never drawn. Fast-forward runs up to 8 steps per frame (loops at 0x8005ec48 / 0x8005ed18 /
  0x8005ee04).
- **Text window fields**: +0x18 pen x, +0x1a pen y, +0x24 left margin, +0x26 auto-wrap limit
  (0 = off), +0x28 line height, +0x2a spacing.
- **Slots**: each character is drawn into a 20×32 4-bpp "slot". The text pool (config at
  0x80064d04) has 48 staging images per frame, 16 windows and 96 slots. Slot *n* is at VRAM
  x = 960 + (*n* / 8) × 5 halfwords, y = (*n* % 8) × 32, with sprite u = (*n* / 8) × 20,
  v = (*n* % 8) × 32, so 96 is a hard limit. The story window owns 80 slots used as a ring:
  past 80 glyphs the oldest are overwritten. Glyph sprites are 19 pixels wide (slot init
  0x80062964). Per-frame staging list: pool +0x14 = halfword count, pool +0x18 = (slot, count)
  pairs, 32 halfwords at most.
- The translation's variable-width text is described in [PATCHES.md](PATCHES.md#story-text-variable-width-font).

### Menu text
- **Font**: FPG 009 (copy in FPG 011 at +0x18): 12×13 1-bpp glyphs in 12-pixel cells (header:
  map 0x18, glyphs 0x3818 at 26 bytes each, widths 0x10164 indexed by linear Shift-JIS index
  below 0x2f0). The glyph draw 0x80015C90 advances the pen by width + spacing unless the window
  forces a fixed pitch.
- **ASCII**: the EXE text routines (0x80015F80, around 0x80016800, 0x8001718C and 0x8001777C) and
  one in overlay 004 (around 0x80067A00, the edit-mode text box) all convert ASCII 0x28–0x7E to
  full-width glyphs through the table at 0x80048CDC, so unpatched English is drawn at about 12
  pixels per letter.
- **Renderer**: EXE 0x80015F5C. Windows (created by 0x80016bc8 with a cell budget) take their
  cells from the context's pool in order (ctx+0x16), with no bounds check: going over corrupts
  the display. Overlay 001 creates 174 windows and overlay 004 60 (budgets 1–88; lists share one
  window). Single bytes 0x28–0x7E are drawn as the matching full-width glyphs (table at EXE
  0x80048cdc), one cell each.
- **Control codes**: `#xN,` moves the pen N pixels (`#x-N,` moves left); the codes `#c` to `#y`
  have a jump table at 0x80010138.
- **Centring**: ctx+0x2e is the field width; the wrapper 0x80016cf8 offsets a string by
  (field − width) / 2.
- The translation's tiling hook is described in [PATCHES.md](PATCHES.md#menu-text-tiling-hook-and-string-pools).

### Other text locations
Menu strings are standard C rodata: NUL-terminated, padded to 4 bytes, at the start of each
module, reached through 32-bit pointer words or `lui`/`addiu` pairs. Many use half-width katakana
(single bytes 0xA1–0xDF). The project's copies are `text/ov00N.txt` and `text/exe.txt`.

| Module | Range | Contents |
|---|---|---|
| Overlay 001 | 0x8005A7E8–0x8005C5A8 | Main menus, match setup, results, titles, mode descriptions, save prompts (about 160 strings; most through pointer tables). The overlay ends at 0x80089744 |
| Overlay 002 | 0x8005A71C–0x8005AD40 | Story-mode extras: speaker names, `No.%03d`, copyright line |
| Overlay 004 | 0x8005A71C–0x8005D270 | Edit mode: parameters, CPU logic, costume parts, memory card and PocketStation messages, Edit Ranking (about 430 strings). Jump tables sit right before some strings |
| Overlay 005 | 0x8005A71C–0x8005AC10 | Logo / CG paint editor, name-entry labels |
| EXE | 0x800103B0–0x80010B34 | Finish types, countries, finisher list, team names, music titles; pointer tables at 0x80048F5C and 0x800493F4 / 0x80049418 |

Overlays 000 and 003 have no referenced strings. Move names have a single copy on the disc (FPG
011); in the 1,592-entry table, 840 strings are distinct, and entry 0 is 使わない ("not used").
FPG 286 (5,984 bytes unpacked) is the name-entry character grid.

- **Dojo tutorial**: FPG 017, raw: BE u16 offsets, then NUL-terminated messages with CR LF lines.
  Overlay 000 loads it at 0x8007850c with the menu font (FPG 009), fetches message *n* through
  0x800793ec and draws it with EXE 0x80017490 into a 56-cell window (created at 0x800785ac). Text
  starts at x 6, y 177; lines are 16 pixels apart and 3 fit. Each lesson's messages are listed in
  8-byte rows at 0x8008432c (0xFF ends a row). Button icons are sprites from a 22-entry table at
  0x80084290 { message, line, icon, x }, drawn at y = 0xB2 + 16 × line with u = 16 × icon (0 weak,
  1 medium, 2 strong, 3 run/whip); in the Japanese each sits on a full-width space, at that
  space's pen x + 5.
- **Bonus wrestler profiles**: FPG 013 +0x8A28, shown in Edit Ranking's Fight list
  (ﾗﾝｷﾝグ戦) in a fixed 54-cell window at x 108, y 168 that wraps when the pen passes x 308
  (EXE 0x80017928; ctx+0x26 = 320, set by ov4 0x80063c58) and shows 3 lines. The player's own
  wrestler shows ov4 0x8005c20c there instead.
- **Edit Ranking**: the intro lines (table 0x80079DCC, 15 strings, 181 cells) and the ending
  (0x80079E08, 10 strings, 67 cells) take their windows' cells from one pool with no bounds check;
  going over corrupts the GPU packet list and the whole screen is painted flat. The ranking list
  uses 10-, 16- and 4-cell windows.
- **Move Edit button icons** are sprites from a table at ov4 0x80079B80 (69 × 5 bytes: texture,
  slot row, x, unused, palette), drawn at x..x+15 on their row (0x80068DF8); labels are centred
  between x 52 and 140 (0x80067CB0).
- **Overlay 002** strings: the speaker names for the story character list (0x8005fb2c), the
  `No.%03d` format and the copyright line.
- **Staff credits** (story ending, ov2 0x8005AD5C–0x8005C3A0): fixed 48-byte lines, the role
  padded with full-width spaces and then the name, stored last line first. They credit Studio
  D-VOLT for the character visuals and Human's F.P.S team for the game.
- **Memory card titles**: see [Save data](#save-data-and-progress).

---

## Save data and progress

Save/system block `S = *(0x800541b4)`, created from FPG 013:

| Offset | Field |
|---|---|
| +0x4E28 (in FPG 013) | 30 bonus edit wrestlers (512-byte records) |
| +0x8A28 (in FPG 013) | Their profiles: 29 BE u16 offsets, then NUL-terminated text |
| S+0x13c7d / +0x13cc5 | Scenes reached / characters met |
| S+0x13cd3 | 194-bit set of locked wrestlers (initialised from the EXE list at 0x800494E4: ids 12 13 14 21 22 24 25 26 59 60 61 62 67 84 85 86 110 133 149 163 164 175 176 177 178) |
| S+0x13cec | Story cleared |
| S+0x13ced | Edit Ranking reward level 0–11 |
| S+0x13cf8 / +0x13cfc | Checksums over the block (EXE 0x8001a240) |

FPG 013 is loaded raw into the save block by EXE 0x8001b5cc. The "clear all" routine 0x8001a614
zeroes the lock set and sets the cleared flag; the setup after loading data (0x8001a908, called
from 0x80018358 on every pass through the title and mode flow) and after a memory-card load
(0x8001a2cc) re-run it only when the flag is set.

The memory card title is a full-width Shift-JIS string at EXE 0x80010364 (44 bytes; 0x80017f94
copies it into the save header). The PocketStation save's title is FPG 014 +4 (64 bytes).

### Progress gates

What the story-cleared flag and the Edit Ranking level open (the player-facing list is in
HIDDEN_CONTENT.md):

- **Story cleared**: Title Match (ov1 0x80073204 buzzer, 0x80073974 grey label), the FR:GOOD and
  FR:BAD music, team presets 33–42, Options > Staff Credits (ov4 0x80072014–0x80072244) and the
  story hero's starting edit points (minimum 160/200/240/280; the top tier also needs 30% of the
  scenes seen: 0x8001bbfc, 0x8001bca8, 0x8001be78, 0x8001c0a8). In the Skill Edit table record
  33 (Division, 0x80076be8; X/Heavy/Junior/Free) has a maximum of 2, lowered to 1 (Heavyweight
  only) unless cleared (0x8006709c), and 0x80066dec draws the extra item only when cleared.
  Records 33–35 (Division, birth year, month) look like the Fighting Road hero setup (not
  verified).
- **Skill Edit fields**: 20-byte records at ov4 0x80076954. Fight Style (field 0x45, 16 styles
  including Giant and Demonic, maximum 15) and the reversal style (0x46, 13) have fixed maxima:
  no gate.
- **Voices** (V1/V2 Type, fields 0x58 / 0x5a, type 5): 10 id groups with ranges at ov4
  0x80076cb4 (category bytes at 0x80076cdc); R1/L1 jumps between groups (0x800668c8). The last
  reachable group is 6 at level 0, 7 at level 1 (beast), 9 at level 4 (women's: ids 1100–1146,
  1150–1196).
- **Wrestler Make**: per-level counts in the category rows. Faces (row 2) go from 29 to 43: +2 at
  level 1, +1 at 3 (sumo), +3 at 4, +1 at 5, +1 at 6, +2 at 7, +4 at 10. Body parts: level 1 bear,
  2 scarred, 4 women's set, 5 panda, 6 tanuki (upper body), 7 kappa (upper body), 8 Mitts,
  10 Paw Gloves and Paw Boots.
- **Moves**: from level 9 the Move Edit list set 0x80078c60 is swapped for 0x800791b8 (ov4
  0x80067680).

---

## Audio

- **Music**: SEQ sequences in FPG 100–125 with VAB sound banks (FPG 007, 098, 125, 268, 269).
- **XA streams** (FPG.XA): FPG 006 lists 8 files as { start sector, size }. A play table at EXE
  0x80049A60 (41 entries of { file, channel, length }) maps tracks to file and channel. Story
  voice clips use file 0 channel 7 (ov2 table 0x800666CC). File 6 is the intro movie (STR); it has
  no Japanese text that needs translating.
- **Sound test** (debug mode 3, ov5 0x8005bad8): internal music *n* plays FPG 100 + *n*
  (0x8005be44), so FPG 122 is music 22; XA music *n* is entry *n* of the play table.

---

## Images

- **TIM** images (the standard PlayStation format) appear raw, compressed, or embedded part-way
  into entries; `tools/tim.py` reads them.
- **BS (MDEC)** pictures, versions 2 and 3, are used for the story backgrounds; `tools/bs.py`
  decodes them.
- The game stores palette indices, and palette index 0 (colour 0x0000) is transparent.
- `tools/contact.py` renders every image found on the disc (raw and compressed TIMs, TIMs embedded
  part-way into entries or packed behind offset tables, BS pictures) to contact sheets;
  `images/graphics.csv` catalogues the ones the translation edits.

| Entry | Image | Text |
|---|---|---|
| 012 | Title screen: compressed 8-bpp 320×240 TIM at +9518 (+0x252E), sharing the entry with the two boot logos (HUMAN, S-NEO team Presents) | Large ファイヤープロレスリングG logo; the menu and "© HUMAN 1999" are English |
| 018 | Outline-effect wrestler figure, 8-bpp 240×208, 17 palettes (palette-cycling); use unknown | A kanji on its chest |
| 019–090 | Arena sheets: 8-bpp TIMs holding 4-bpp texture data, 13 palettes | Banners, mostly Latin with some katakana (e.g. "HUMANプロレス") |
| 093 | Small title logo, 4-bpp 160×131 | The flaming logo |
| 096 | Six screen test patterns | None |
| 132–142 | Story backgrounds, BS v3 512×320: arena, crowd, locker room, hallway, office, gym, weight room, two street scenes, sepia gym | A few small shop signs |
| 143–247 | Story portraits, 8-bpp in 32×32 tiles | None |
| 277 | 16-bpp TIM of 576×256 halfwords at VRAM (320, 256) that holds 4-bpp textures and their CLUTs | See below |
| 278, 288 | Font sheets | |
| 279–285 | Victory / title screens: a 16-bpp VRAM block holding an 8-bpp 320×240 photo and, at halfword x 192, a 4-bpp 128×240 caption strip (CLUT at row 241, x 192) | Captions 勝利, 優勝, 制覇, タイトル奪取, タイトル防衛 (128×48 each), identical in all seven; the photos' English banners are part of the photo |
| 287 | Edit-mode icons | English labels |
| 289 | FIRE PROWRESTLING background | |
| 091, 095, 248, 250, 276 | Effect textures and the debug font | |

FPG 277 holds:
- the 14 mode-select names (x 0–255, y 0–127; 128×16 each in two columns; CLUT at sheet row 251).
  The game recolours them with other CLUTs (purple, grey when locked), so each index keeps its
  meaning: a dark-to-light ramp with 2 = white highlight;
- the 7 select-screen labels 名前 ニックネーム 出身地 必殺技 身長 生年月日 体重 (x 1408–1447,
  y 0–111; 40×16 each; CLUT at sheet row 195, x 320): colour 0 is opaque yellow text, 14 the
  dark shadow, 15 transparent; the gradient box behind them is drawn separately;
- the 欠場 (absent) and AUTO VS marks, bracket digits, 1P/2P/CP tags, arena thumbnails,
  NowLoading and RANDOM.

---

## Debug code

The retail game keeps most of its developer code. What each mode does for a player is in
HIDDEN_CONTENT.md; this is where the code is.

- **Hidden combo**: the main loop (0x8001c6b0) runs the title (ov2 0x8005d348; its "press start"
  screen 0x8005d0d8 accepts Circle or Start). If the held pad is then exactly 0x4816
  (L1+R2+Triangle+Down+Start), it loads overlay 005 and runs 0x8005c618, the test-pattern viewer
  (FPG 096). The check runs after the title's fade-out and music stop.
- **Mode select** (0x80017974, " < SELECT >" at 0x800101fc), never called. Its number input
  0x80015270, printf 0x800146e8 and 0x80015278 / 0x80015280 are retail stubs (on the dev kit
  they went to a PC console). Modes:

| Mode | Code | Notes |
|---|---|---|
| 0 DATABASE | ov5 0x8005afc8 | R1/L1 fetch move names (0x80019504 → 0x80017490 into the window at +8, line +0x60), but the per-frame draw 0x8005b5c4 rewrites that line with 0x80018670(wrestler). Triangle calls 0x80013fe0 (stop music) |
| 2 RING | ov0 0x80074824 | Arena viewer; the stub input picks arena 0 |
| 3 SOUND TEST | ov5 0x8005bad8 | The row cursor used a console locate() stub, so it is not shown |
| 4 FR DEBUG | 0x80017d4c | Scene jumper (`ST%04d`), runs scenes with 0x8001c9d0 |
| 5 BATTLE SELECT | 0x80017ee8 | Input stub 0x80015278 returns 0; then 0x8001ca9c(n) with a fresh zeroed story state, overlay 002 and 0x80060edc(n) |
| 6 HIT EFFECT | ov0 0x800761bc | Arena 6 (0x80074b70(6)), FPG 091; Triangle spawns 6 bursts in each of two effect systems (`*0x80086178`, `*0x8008617c`) at positions 0x80084244 / 0x8008425c, three around each corner post (±1360, ±730 / 1990), 400 above the mat; prints `%03d/%03d` of 0x80054150 / 0x80054154 |
| 7 WRS SAVE | | PC only |
| 8 TITLE, 10 EDIT | | EDIT skips the mode-select screens that load the window art |
| 11 MC EDIT LOAD | 0x80017ad0 | Reads memory card file "BISLPSPxxxxx GAME" (EXE 0x800102b4, a placeholder product code) from +0x180, 0xA000 bytes, and copies 0x9A4D bytes to S+0x180 (edit wrestlers and profiles; the progress fields at +0x13C7D lie past it). Never found on a retail card: prints "ERROR!" |
| 12 | ov5 0x8005b9b0 | Prints constant structure sizes: EQUIPMENT 114, LOGIC 156, STDWRS 386, HUMAN 426, EDITHUMAN 512, MEMCARD 0x13D00 |
| 13 | ov5 0x8005c618 | Test patterns |
| 20 / 21, 70 / 80 | | PC file load / save |
| 40 | ov2 0x80063bd8 | Staff roll with music |
| 200 | 0x8001a614 | Clear all, then 0x8001a694(11) |

- **Yone process select** (EXE 0x8001ef00, jump table 0x80010a58): a second unused selector for
  the overlay 003 programs; see [Overlay 003](#overlay-003-developer-tools).
- **Overlay 002 debug printer** (0x8005ef6c) prints only when 0x80077bd8 is 1–3; the story-state
  dump strings (0x8005ab58, 0x8005abd0) belong to it. Script opcode 0x25 is the unused prompt
  "VIEW JAPAN BRANCH 0:SEIKIGUN 1:FWO".
- **Button codes in matches** (overlay 000): music override at 0x8007112c, HUD mask at
  0x8007cd88, referee palette at 0x8007f6c8 (see HIDDEN_CONTENT.md).
- **FPG 275 is never loaded.** Every call of the FPG loaders (0x80012028, 0x80012c14, 0x80012c90,
  0x80012acc, 0x80012fe4) in the EXE and overlays 000–005 resolves to constants or base + index
  ranges (arena sheets 19 + 17n + k, portraits 143 + s8, backgrounds 132 + s8, move data
  252 / 257 + n, 260–267, music 100 + n, the overlay table 0x80010034, ov1's table 120/123/124);
  none reaches 275. The values 0x111 / 0x113 at ov0 0x8005dad4 are action ids (wrestler +0x16c),
  not files. The load queue 0x80012620 has no callers and no { pointer, id, type } records exist
  in any module.

---

## Open questions
- The head sprite format in FPG 251 (entries 0–319; body parts are plain LZSS tiles).
- The format of FPG 271 / 272 (wrestler-figure animation data) and the referee frame tables (odd entries of FPG 261–267).
- What FPG 018 (an outline-effect wrestler figure) is used for.
- Whether records 33–35 of the Skill Edit table are the Fighting Road hero setup.
- The open move fields ([MOVES.md](MOVES.md#open-questions)).
- The full Skill Edit field layout from +0x46 onwards and the CPU logic data. Debug mode 12 gives the
  developers' block sizes: equipment 114 bytes, CPU logic 156, standard wrestler 386 (with the
  426-byte roster and 512-byte edit records, and the 81,152-byte save block).
