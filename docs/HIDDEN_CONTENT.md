# Fire Pro Wrestling G — hidden, locked and cut content

Everything here was found while translating Fire Pro Wrestling G (PlayStation, SLPS-02065,
Human, 1999). It covers what the game locks behind progress, what it hides, and what was
left on the disc but cut. Each item says how it was confirmed: **verified in game** means it
was seen running in an emulator; **from the code** means it was read from the program or data
and not yet seen running.

Addresses are PlayStation RAM addresses. Overlays are code modules loaded at 0x8005A718;
"ov2" means overlay 002 (the story mode), and so on. File numbers ("FPG 251") are entries in
the game's data archive, FPG.BIN. [TECHNICAL.md](TECHNICAL.md) explains both.

## Contents
1. [How to see it yourself](#how-to-see-it-yourself)
2. [Unlockables and progress gates](#unlockables-and-progress-gates)
3. [Developer menu and debug leftovers](#developer-menu-and-debug-leftovers)
4. [Button codes](#button-codes)
5. [Unused wrestler graphics](#unused-wrestler-graphics)
6. [Moves](#moves)
7. [Story mode (Fighting Road)](#story-mode-fighting-road)
8. [Unused files and other leftovers](#unused-files-and-other-leftovers)
9. [Not explored yet](#not-explored-yet)

---

## How to see it yourself

The **All Unlocked** release patches (English or Japanese) unlock everything described
under [Unlockables](#unlockables-and-progress-gates) from the start. The English one
also adds the unused heads and body parts to Wrestler Make.

The rest needs a build from source ([BUILDING.md](BUILDING.md)):

| Command | What it gives you |
|---|---|
| `python3 build.py` | Same as the English All Unlocked patch |
| `python3 build.py --no-unlock` | Original progression: locked wrestlers, Edit Ranking rewards and story-clear rewards behave as in the Japanese release |
| `python3 build.py --no-extra-parts` | Leaves the unused heads and body parts out of Wrestler Make |
| `python3 build.py --japanese` | Japanese text, everything unlocked |
| `python3 build.py --debug-menu` | Restores the developer mode-select menu (hold **Select** and press **Start** on the title screen). Its text output goes to the emulator's TTY log |
| `python3 build.py --route5` | Debug build in which the graduation offer always gives the cut New Japan / Liger scene (see [Story mode](#story-mode-fighting-road)) |

---

## Unlockables and progress gates

The game keeps its progress in a save block at `*(0x800541b4)`:

| Offset | Meaning |
|---|---|
| +0x13cd3 … +0x13ceb | 194-bit set of locked wrestlers |
| +0x13cec | Fighting Road (story mode) cleared |
| +0x13ced | Edit Ranking reward level, 0–11 |
| +0x13c7d / +0x13cc5 | Scenes reached / characters met (the percentages in Options) |

Clearing the story runs one routine (EXE 0x8001a614) that unlocks all wrestlers and sets the
"cleared" flag. The patch makes that routine run on every boot and also set the Edit Ranking
level to 11 (`tools/unlock.py`). **Verified in game.**

### Locked wrestlers
25 wrestlers start locked (list in the EXE at 0x800494e4) and are freed by clearing the story:

Antonio Inoki, Riki Choshu, Animal Hamaguchi, Tiger Mask, Dynamite Kid, Black Tiger,
Norio Honaga, Kotetsu Yamamoto (New Japan); Giant Baba, Jumbo Tsuruta, Dory Funk Jr.,
Bruiser Brody, Tiger Mask II (All Japan); Tiger Jeet Singh, The Great Kabuki, Koji Kitao
(FMW); Ric Flair (WCW); Andre the Giant (WWF); Akira Maeda (RINGS); Dos Caras, Mil Mascaras
(AAA); Roland Bock (Shoot Fighters); Rikidozan, Karl Gotch, Lou Thesz (Legends).

### Clearing Fighting Road also unlocks
- **Title Match** mode (greyed out and buzzes until then; ov1 0x80073204 / 0x80073974).
- The **FR:GOOD** and **FR:BAD** tracks in the match music list.
- Ten **team presets** (ids 33–42).
- **Options > Staff Credits**.
- **More starting edit points** for the story hero. The minimum is 160/200/240/280, and the
  top tier also needs 30% of the story scenes seen (the patch drops that check, so it is 280).
- **Junior Heavyweight** for the hero (from the code): a short form with Division, birth year
  and birth month (records 33–35 of the Skill Edit table, apparently the Fighting Road hero
  setup) offers only Heavyweight until the story is cleared (ov4 0x8006709c).

### Edit Ranking rewards
Climbing the Edit Ranking raises the reward level. Each level adds Wrestler Make parts, voices
or moves (from the code; the reward messages are in overlay 004):

| Level | Reward message | What it actually adds |
|---|---|---|
| 1 | Got bear parts & beast voice! | Bear version of every body part, 2 bear faces, the beast voice group |
| 2 | Got scar parts! | Scarred parts for body, arms, wrists, legs, shoes |
| 3 | Got the sumo face! | 1 face |
| 4 | Got women's parts & voice! | About 50 women's clothing parts, 3 faces, the two women's voice groups |
| 5 | Got panda parts! | Panda version of most parts, 1 face |
| 6 | Got tanuki parts! | Tanuki upper body and lower body, 1 face |
| 7 | Got kappa parts! | Kappa upper body and lower body, 2 faces |
| 8 | Got mitt parts! | Mitts (hands) |
| 9 | Got hidden moves! | Muscle Buster (5 move lists) and Phoenix Kick (1 list) |
| 10 | Got the girl's face! | 4 girl's faces, plus **Paw Gloves** and **Paw Boots**, which the message doesn't mention |
| 11 | (themes) | Musashi's and Hikawa's themes in the match music list |

How the gates work:
- **Parts:** a table at ov4 0x80076478 gives, for each Wrestler Make category, how many list
  items are available at each level. The lists are ordered so that each level's items come
  after the previous level's.
- **Voices:** voice ids come in 10 groups (ranges at ov4 0x80076cb4). R1/L1 jumps between
  groups; the last reachable group is 6 at level 0, 7 at level 1 (beast), 9 at level 4 (women's).
- **Hidden moves:** from level 9 the game swaps the whole Move Edit list set (0x80078c60) for a
  copy (0x800791b8) that adds the two moves.

The **Giant** and **Demonic** fighting styles are *not* gated: the Fight Style list (16 styles)
and the reversal-style list (13) have fixed maximums in the Skill Edit table.

---

## Developer menu and debug leftovers

### Test pattern viewer (in the retail game)
After the title screen, holding **L1 + R2 + Triangle + Down + Start** (exactly those buttons)
opens a viewer for six screen-calibration patterns (FPG 096). Circle shows the next one, Cross
toggles 320/640 width, the D-pad scrolls, Start exits. From the code; the five-button combo did
not register in DuckStation; the viewer is also mode 13 of the restored menu.

### Developer mode-select menu
The EXE still contains the developers' mode menu (0x80017974, titled " < SELECT >"), but
nothing calls it. Its number entry and text output went to a PC console on the development kit
and are empty stubs in the retail game. `--debug-menu` reconnects it: hold Select and press
Start on the title screen, pick a mode with Up/Down and Circle. Text output goes to the TTY log.
The menu and every mode it offers have been run in game (the PC-only modes 7, 20/21 and 70/80 are left off the restored menu); the details of what each does come from the code.

| Mode | Name | What it does / controls |
|---|---|---|
| 0 | DATABASE | **Verified in game.** Shows each wrestler's text with music playing. Left/Right promotion group, Up/Down wrestler, Triangle stops the music, Cross exits. R1/L1 step through the 1,592 move names, but the name goes into the bottom text line, which the screen redraws with the wrestler's own text every frame, so it never shows. Each frame it also prints the promotion and wrestler counts and the wrestler's height, weight and birth date to the TTY log. |
| 2 | RING | **Verified in game.** Arena viewer; the ring and arena are real 3D models. Hold Circle + D-pad/L1/L2 to rotate the camera; hold Square + Up/Down (height), Left/Right (distance), L1/L2 (zoom). Start exits. |
| 3 | SOUND TEST | **Verified in game.** Nothing on screen; the values print to the TTY log (INTERNAL MUSIC, INTERNAL VOLUME, XA MUSIC). Up/Down row (music, volume, XA track, stop, exit), Left/Right value, Circle plays, Cross stops, Start exits. Internal music *n* plays FPG 100 + *n* (0–25); XA music *n* is entry *n* of the XA play table (00–40). The tracks only reachable here are internal music 22 and XA music 00 and 06. |
| 4 | FR DEBUG | Fighting Road scene jumper. Right/Left ±1, Up/Down ±10, R1/L1 ±100, Circle runs the scene. It first shows a **story-state editor** (match result, Ambition, Babyface, Passion, Star Points, Champion and the ten style counters): Up/Down picks, Right/Left changes, Circle starts. |
| 5 | BATTLE SELECT | Plays a Fighting Road match directly, without its story scene, from a blank story state. It asks for a battle number (0–355), but the input is a stub, so it always plays battle 0, the match of scene 0 (**verified in game**: it goes straight to a match). |
| 6 | HIT EFFECT | Loads arena 6 with the RING viewer's camera controls. Triangle fires 12 effect bursts of two kinds, three around each of the four corner posts. A two-number counter (probably a performance meter) prints to the TTY log every frame. Start exits. |
| 7 | WRS SAVE | Saved wrestler data to the PC (dev kit only). |
| 8 / 10 / 11 | TITLE / EDIT / MC EDIT LOAD | Jump straight to those screens. **8 and 10 verified in game.** EDIT skips the mode-select screens that normally load the menu window art, so its frames show leftover video memory (text and menus work). 11 reads the memory card save "BISLPSPxxxxx GAME", a placeholder name from before the game had its product code, so on a retail disc it always prints "ERROR!" to the TTY log (tried in game). Had it found the file, it would have copied the edit half of that save (edit wrestlers, their profiles; save block +0x180 to +0x9BCD) into the running game and left progress (unlocks, story, Edit Ranking) alone. |
| 12 | (sizes) | **Verified in game.** Prints the developers' data structure sizes to the TTY log (constants, not counts): EQUIPMENT 114, LOGIC 156, STDWRS 386, HUMAN 426 (the roster record), EDITHUMAN 512 (the edit record), MEMCARD 81,152 bytes = 80 KB (the save block). |
| 13 | (patterns) | The test pattern viewer above. |
| 20 / 21, 70 / 80 | DOS LOAD / SAVE, file loaders | Read and write files on the PC (dev kit only). |
| 40 | (staff roll) | **Verified in game.** Scrolling staff credits with music; Cross skips. |
| 200 | (clear) | **Verified in game** (no visible output). Runs the "story cleared" routine (unlocks everything, sets the cleared flag) and sets the Edit Ranking level to 11. The patch already unlocks everything, so it changes nothing visible there. |

Other debug leftovers:
- A second debug selector, "yone process select" (EXE 0x8001ef00, dated 1999/04/15), for the
  overlay 003 programs below. It is dead code, and the restored menu lives in its space.
- Overlay 002 has a debug printer (0x8005ef6c) that prints only when a debug variable
  (0x80077bd8) is 1–3. The story-state dump strings (`MATCH RESULT %3d`, `YASIN`, `BABY FACE`,
  `NEKKETU`…) belong to it. They also give the story variables their names.
- Story script opcode 0x25 shows a developer prompt, "VIEW JAPAN BRANCH 0:SEIKIGUN 1:FWO", for
  choosing between the New Japan regulars and nWo routes. No scene uses it.
- Strings: "- PROLOG NOW MAKING PUSH X TO NEXT -" (unreferenced) and development paths
  `../AIKOH/MC_SAVE.BIN`, `../AIKOH2/WRSDATA.ROM`, `C:/USE/EDIT00.WRS`.

### Developer move/animation editor (overlay 003)
Overlay 003 is never loaded by the retail game. The dead "yone process select" ran four
programs from it, and the restored menu lists them as **OV3 ANIME TOOL**, **OV3 TEST 11**,
**OV3 TEST 12** and **OV3 SE TEST**. All four exit with **Square + Cross** held on controller 1.

The anime tool ("GED") is the developers' editor for building moves. It is **verified in
game** (screens, pointer and tab switching), after four repairs that only `--debug-menu`
builds make:
- In retail, its per-frame hooks are empty stubs. The patch calls the editor's init
  (0x8005f0a0) and per-frame routine (0x8005f154) from them.
- Its 8×8 text never reset its glyph counter or set its draw list, so it was invisible and
  soon overran memory. The uncalled reset routine (0x80074f0c) now runs each frame.
- The retail glyph code picks only four glyphs (`char & 0x50`, no horizontal offset). It now
  uses the full character code against the 16×16 font grid (FPG 276).
- Its shell uploads FPG 250 (hit-effect sprites) over the font, so that upload is skipped.

It is driven by a PlayStation Mouse. It read the mouse from controller slot 4, which is
port 2 behind a multitap in port 1, probably the developers' setup. The patch reads port 2
directly. A normal pad in port 2 also works: its D-pad moves the pointer, and Cross and
Circle click.

What the screens are for (from their labels):

| Tab | Contents |
|---|---|
| FILE | Load and save move banks `waza-a`…`h` (`.gsf`), poses (`.f96`), `blkform.bfd`, `c:gfd.f96`, `c:gsd.blk`, to SRAM, "pmem", CD-ROM or floppy (FDD1/FDD2). |
| FORM | Build a pose from body-part sprites ("PARTS DIRECT SELECT MODE"; part position MX/MY, GROUP/REVERSE/ROLL). |
| ANIM | Build an animation as a frame list. Per frame: wait time, offset, pose and shadow; attack data (damage, impact, height, direction); a sound effect from a named list ("head attack lv1", "mat(normal)", "gong(match end)"…). |
| CONF | Loop count, repeat wait, view mode, select check; wrestlers 0–5 with CPY/SWP/UND; ring post type and colour; screen colour. |

Other screens set each move's game data: type, single and combo hits, damage to head, neck,
arm, waist and leg, attack range and flight, critical rates (strike, suplex, submission,
power, technique), foul, give-up and blood rates, and the reversal type. Those screens, and
the move data they edit, are decoded in [MOVES.md](MOVES.md).

It cannot load anything. Its load/save code was compiled out (no file or device access is
left), and the only data it reads from the disc is the wrestler body-part archive (FPG 251).
It draws poses with the game's own sprite renderer (EXE 0x8001cd24). Showing a real move
would mean converting a move block into the editor's memory layout (both are described in
[MOVES.md](MOVES.md#the-move-block)) and copying it in; not attempted.

**OV3 TEST 11** (**verified in game**) is a sprite test bench. It shows one frame of the
hit-effect sheet (FPG 250) in the middle of the screen, and five objects of the game's animated
wrestler-figure system (the large animated wrestler drawings used outside matches), placed 64
pixels apart. Controls:

| Button | Effect |
|---|---|
| Left/Right | Step through the 57 effect frames, and at the same time pick the object (0–4) the buttons below change |
| R1 | Flip the effect frame (R2 also flips it, as well as mirroring the object) |
| Circle | Show or hide the object's figure |
| R2 | Mirror the figure |
| Square | Freeze or resume its animation |
| Start | Toggle an extra small sprite drawn with it |
| Triangle | Sets a flag the figure code never reads (no visible effect) |
| L1/L2 | Change a value that starts at 128 (probably brightness or size) |
| Select | Reset all five objects |

Every object shows wrestler 0: the reset sets that, and no button changes it (the developers
probably set it from their PC console). A small cursor is meant to be moved by a mouse in the
developers' multitap slot, so it stays put. The background is a view of part of video memory,
so it can show leftover screens.

**OV3 TEST 12** (**verified in game**: it runs, but shows only raw video memory) is a 640×480
picture viewer whose picture never arrives. It switches to 640×480 and sets aside a buffer sized
for a 640×480 256-colour TIM, but nothing ever loads into it: the loading step is gone (a leftover
routine reserves 128 KB and frees it at once), so the picture probably came from the developers'
PC. Until then the screen shows video memory as it is, which is mostly the game's texture sheets.
**Circle** uploads the buffer's palette and two halves and shows it full-screen as 20 tiles, which
with an empty buffer is garbage. A counter steps 0–4 every three frames and nothing reads it.
The likely pictures are in FPG 275: five of its 13 images are exactly 640×480 at 256 colours, the
layout TEST 12 expects. Nothing in the code names FPG 275, so this is a match of formats only.

**OV3 SE TEST** (**verified in game**) prints a sound tester to the TTY log. Page 1 has rows exit, def se, ref se and kan se (probably general effects, referee voice and crowd); page 2 drives a sound-chip voice directly (voice, ssid, prog, tone, note, fine, voll, volr, with an ok/ng status). Select switches pages (so do Left/Right on the exit row), Up/Down pick a row (no cursor is printed; it starts on exit), Left/Right change the value, Circle or L2 plays (or exits on the exit row), Square plays a test note with the page-2 settings, Triangle stops all sounds.

---

## Button codes

From the match code (overlay 000), pad 1, exact button combination:

| Code | Effect | Status |
|---|---|---|
| Hold L1 + L2 + R1 + R2 while a match loads | Match music = Musashi's Theme (BGM 13) | From the code (ov0 0x8007112c) |
| Hold L1 + L2 + R2 while a match loads | Match music = Hikawa's Theme (BGM 14) | Same |
| Hold L1 + R1 and press Select during a match | Cycles a HUD mask (hides the clock and one other element) | From the code (ov0 0x8007cd88) |
| Hold Left, Right or Down while a match loads | Alternate referee colours: each of the four referees has four palettes, and these pick palette 1, 2 or 3 | From the code (ov0 0x8007f6c8 loads the referee sprites and uploads the palette) |

---

## Unused wrestler graphics

Wrestler heads and body parts are stored in FPG 251 and picked by number. Comparing it with
every list, roster wrestler, bonus edit wrestler and preset turned up graphics nothing uses.
All are unique art (no copies), and all were **verified in game** through a test build.

| Kind (Wrestler Make label) | Unused graphics |
|---|---|
| Heads (Face) | 305 (among the girl's faces 302–307; probably a fifth one), 308–319 |
| Chest | 74, 75 |
| Trunks (Waist) | 120, 121 |
| Upper arms (Bicep) | 69, 70 |
| Forearms (Arm) | 64, 65 (66 is a copy of another part) |
| Shins (Shin) | 56, 57 |
| Thighs (Thigh) | 95, 96 |
| Feet (Ankle) | 36 (19 is a copy) |

Part numbers are per category; [COSTUMES.md](COSTUMES.md#body-parts) has the FPG 251 entries.

In each category the unused parts are the last ones, which suggests parts made late or dropped.
Head slots 277–281, 287, 291 and 299 are empty.

**The patch adds them to Wrestler Make** (`tools/hiddenparts.py`). Body parts appear as
"Extra 1" / "Extra 2" right after each list's starting items. The 13 heads come at the end of the
head list (positions 300–312). Heads from position 194 on normally also load a matching body and
colours from a preset file (FPG 015). That file has no presets for the new positions, so a patch
skips that step and the extra heads keep the current body.

FPG 015 also holds 4 presets past the end of the head list (one is a copy), with no head of their
own. They are unreachable but contain nothing visible.

---

## Moves

### Hidden moves (Edit Ranking level 9)
Muscle Buster and Phoenix Kick, as above.

### Named moves that were cut
The move name table has 1,592 entries. Move Edit offers 962 moves, and roster wrestlers use 892,
all of which Move Edit also offers. 113 named moves are never offered and never used. 85 of them
fall within a Move Edit category, among them:

> Gory Special, Miracle Ecstasy, Smith Special, Nelson Nagata Lock, Spine Buster, Swan Dive DDT,
> Mexican Ace Crusher, Diving Brain Chop, Body Drop Lariat, Butchikamashi, Gut Headbutt,
> Indian Deathlock, Super Tiger Suplex, Super Dragon Suplex, Hashimoto Pose, Beer Chug…

**None of them has any animation data.** Move data lives in FPG 252–258 (one entry per move
number). Every offered move has an entry there, and none of these does. A test build that put
them in Move Edit confirmed it: picking Gut Headbutt replays whatever animation played last.
**Verified in game.** These moves were named and then never made. One is even labelled in the
Japanese as unused: 裏投げ(未使用), "Ura-nage (unused)".

### Unnamed moves with data
Move numbers 211–216, named "(Reserved)", do have move data: two moves with three variants each,
right after the three "Combination" strikes and almost identical to them. In game they play like
Combination 1 and Combination 3, so nothing new. **Verified in game.**

### Second copy of the move data
FPG 274 (3.8 MB, uncompressed) holds a copy of all the move data. It has the same 1,270 entries
as FPG 252–258, byte for byte, so it contains no extra moves. A search of every other file found
no other move data.

---

## Story mode (Fighting Road)

### Cut recruitment: New Japan with Liger
At graduation (scene 3) the game picks which promotion recruits you: New Japan, All Japan, FMW,
UWF or America by your best style, or Michinoku Pro if your hero isn't a heavyweight. The script
has room for a seventh result that the code never produces (route 5). Its scene is a copy of the
normal Choshu recruitment with one line changed:

> **Choshu:** "Liger would be on board with you, too."

(normally: "Would I joke about this?"). After it, route 5 reuses the New Japan lines for Sakagami
and then continues into **the Michinoku Pro debut** (scene 458), just like the junior route. It
looks as if juniors were first meant to join New Japan's junior division alongside Jushin Liger,
and that was replaced by Michinoku Pro. No New Japan junior scenes exist. **Verified in game**
with `build.py --route5` (debug menu mode 4, scene 3).

### Lines that are never shown
These messages sit in the scene text tables, but no instruction in their scene ever displays
them. They are leftovers from script edits:

| Scene, message | Text |
|---|---|
| 002 @24 | 削除 ("deleted") |
| 066 @2 | Reporter: "But it was a fantastic match." |
| 070 @7 | It worked. Goto had the look of a man who meant business. Now this match will be fun! |
| 266 @14–15 | Anjoh: "Yo, long time no see." / Hero: "It's been a while." |
| 520 @26 | "Come on!" |

### Other story findings
- All 522 scenes can be reached. Scenes 520–521 only play in the title-screen demo.
- Two of the seven promotion-affinity counters (5 and 6) are raised by some scenes but never
  read: traces of routes that were planned and dropped.
- Scene 401 message 2 prints the hero's full name followed by a stray "00" in the Japanese. The
  translation drops it.

---

## Unused files and other leftovers

| What | Where | Notes |
|---|---|---|
| Anime / dating-sim illustrations | FPG 275 | `tools/unused_art.py` exports them to PNG (`extracted/images/fpg275/`). 13 images, including a "PALETTE パレット" title card: art from *PALETTE*, a 1998 Windows visual novel by Fairytale / F&C ([VNDB v11654](https://vndb.org/v11654)). No name in the game's staff credits matches PALETTE's credited staff, and no PlayStation version of PALETTE was found, so how it got here is unknown; possibly sample pictures for the 640×480 viewer (TEST 12). Five are 640×480 and eight 320×240, all 256 colours. No code in the game loads FPG 275 (every archive load in the EXE and overlays checked). Overlay 003 TEST 12 is a 640×480 viewer for exactly this kind of picture. |
| Developer move/animation editor | Overlay 003 | Runs from the restored debug menu; see [above](#developer-moveanimation-editor-overlay-003). |
| 8×8 debug font | FPG 276 | The editor's font: 16×16 grid of ASCII glyphs, white and red/yellow sets. |
| Hit-effect sprites | FPG 250 | Loaded only by the overlay 003 programs (shown by TEST 11). |
| Music sequence | FPG 122 | Only playable from the sound test. |
| Two XA audio tracks | FPG.XA index 0 (file 0 channel 0, ~58 s) and 6 (file 0 channel 6, ~28 s) | Only playable from the sound test. |

---

## Not explored yet
- Loading a real move into the overlay 003 editor (the formats are in [MOVES.md](MOVES.md)).
- Dumping the sound-test-only audio to WAV.
