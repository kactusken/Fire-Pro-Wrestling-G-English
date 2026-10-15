# Fire Pro Wrestling G — English Translation

An English translation patch for **Fire Pro Wrestling G** (ファイヤープロレスリングG), the 1999
PlayStation game by Human Entertainment, released only in Japan.

It covers the whole game: all 522 scenes of the Fighting Road story mode, the menus,
the roster, move names, the Dojo tutorial, Edit Mode, and the menu graphics. Story
text uses a new variable-width font, so English lines fit in the dialogue box.

**[See screenshots](docs/SCREENSHOTS.md)** of the patched game.

> **Status: first public beta.** Everything is translated. Not every story route has been
> played through yet, so you may find text that runs out of its box, a name that
> doesn't fit, or a line that reads oddly. Please report anything like that
> ([how to report](#reporting-problems)). [docs/TESTING.md](docs/TESTING.md) shows what
> has been checked so far, and [CHANGELOG.md](CHANGELOG.md) lists what's in each release.

## Downloads

Get the latest zip from the [Releases](../../releases) page. It contains three patches.
Pick one:

| Patch | What you get |
|---|---|
| **Fire Pro Wrestling G (English)** | The translation, with the game otherwise unchanged. Wrestlers, Edit Mode rewards and other extras unlock as you play, as in the original. |
| **Fire Pro Wrestling G (English) (All Unlocked)** | The translation with everything unlocked from the start: every wrestler, every Edit Ranking reward (parts, voices, hidden moves), and the story-clear extras. It also adds some unused heads and body parts found on the disc to Wrestler Make. |
| **Fire Pro Wrestling G (Japan) (All Unlocked)** | The original Japanese game with everything unlocked from the start. |

## How to patch

You need your own copy of the original Japanese disc as a `.bin`/`.cue` image. Disc
images are not provided here.

- Game: *Fire Pro Wrestling G* (Japan), serial **SLPS-02065**. The later Spike Library
  reissue (SLPS-02817) is a different disc and won't patch.
- The `.bin` must match: 303,368,016 bytes, CRC32 `d9b6b206`,
  SHA-1 `8dbba0ddad40f4b669a88b688417d67c21eb792d`.

Then:

1. Apply the `.xdelta` patch to the `.bin` with any xdelta tool:
   - [Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) runs in your web browser,
     with nothing to install.
   - Delta Patcher is a desktop app for Windows, macOS and Linux.
   - On the command line:
     `xdelta3 -d -s "Fire Pro Wrestling G (Japan).bin" "patch.xdelta" "patched.bin"`
2. Rename the patched `.bin` to match the `.cue` that comes with the patch (for example
   `Fire Pro Wrestling G (English).bin`), and keep both in the same folder.
3. Open the `.cue` in your emulator. The patch has been tested in
   [DuckStation](https://www.duckstation.org/).

## Notes for players

- **Names.** The original game uses made-up stand-in names for real wrestlers, promotions
  and referees. This translation uses the real names where they're known (for
  example "New Japan" rather than "View Japan").
- **What's still in Japanese.** The arena banners, the title logo and the promotion logos
  stay as they are, because they're artwork. So do the kana grids on the name-entry
  screen and the staff credits after the story ending.
- **Saves.** The patch doesn't change the save format, so memory cards from the Japanese
  game should work. The save's title on the memory card is now in English. With an
  "All Unlocked" patch, loading an old save also unlocks everything.
- **Hidden content.** The game holds a developer menu, cut story scenes, unused art and
  more. See [docs/HIDDEN_CONTENT.md](docs/HIDDEN_CONTENT.md).

## Reporting problems

Open an [issue](../../issues) with:

- a screenshot,
- which patch you used,
- where you were: the mode or menu, or in story mode, roughly what had just happened.

Text that is cut off, overlaps, or still shows Japanese is especially helpful.
Reports on the untested story routes and endings in [docs/TESTING.md](docs/TESTING.md)
are the most useful of all, even if everything looked fine.

## For ROM hackers and contributors

Everything needed to rebuild the patches from the original disc is in this repository:
the translated text, the patching code (Python 3, no dependencies for the build) and
documentation of the game's formats.

| Document | What's in it |
|---|---|
| [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) | Start here: a plain-English tour of what the patch changes and why |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to help: reporting, translation fixes, images, code, and pull requests |
| [docs/BUILDING.md](docs/BUILDING.md) | Setting up, building, making patches, the repository layout, and the checking tools |
| [docs/TRANSLATION.md](docs/TRANSLATION.md) | Text file formats, style guide, glossary, and naming decisions |
| [docs/EDITING.md](docs/EDITING.md) | Editing the in-game text graphics |
| [docs/PATCHES.md](docs/PATCHES.md) | How each patch works: variable-width font hooks, string relocation, unlocks, debug menu |
| [docs/TECHNICAL.md](docs/TECHNICAL.md) | The game's disc layout, archive, compression, data formats, and memory map |
| [docs/TESTING.md](docs/TESTING.md) | What has been tested in the game, and what still needs a playthrough |
| [docs/HIDDEN_CONTENT.md](docs/HIDDEN_CONTENT.md) | Unlockables, debug features, and unused and cut content |
| [tools/README.md](tools/README.md) | Every tool, what it's for and how to run it |
| [Story Route Map](https://kactusken.github.io/Fire-Pro-Wrestling-G-English/route-map/) | An interactive map of Fighting Road's branches |

Quick start:

```sh
python3 build.py                      # -> build/Fire Pro Wrestling G (English).bin/.cue
python3 make_patches.py --version v0.1   # -> release/*.xdelta and a zip (needs xdelta3)
```

## Legal

This is a non-commercial fan translation.
It contains no copyrighted game data that would let anyone play without owning the game.
The patches only work on your own copy of the disc. Fire Pro Wrestling G is © 1999 Human
Entertainment and its successors in interest. The Japanese script text in this
repository is included for translation and reference.

The code in this repository is released under the [MIT License](LICENSE).
