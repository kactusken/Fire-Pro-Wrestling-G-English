# Changelog

What changed in each release of the patch. Newest first.

## v0.3 — 2026-10-19

### Added
- **Move fixes** in the All Unlocked patches, including the Japanese one: the face-up
  Arching Boston Crab can make the opponent give up, Low Blow from behind is a foul, and
  the Haruki Special from behind can cause criticals, as their other versions do. The
  English and Fake Names patches are unchanged.
- docs/MOVES.md and docs/COSTUMES.md: how moves and costumes are stored, with CSV exports.

## v0.2 — 2026-10-19

### Added
- **Fake Names patches**, at a player's request: the translation with the game's own
  stand-in names for wrestlers, promotions, venues and referees (Hurricane Rikimaru,
  View Japan, Nippon Butokan, Panther Tottori) instead of the real ones. There are two,
  one with the original unlocks and one with everything unlocked, so a release now has
  five patches. The other three patches are unchanged from v0.1.

## v0.1 — 2026-10-15 (first public beta)

The first public release. Everything is translated, but most of the story hasn't been
played through yet. See [docs/TESTING.md](docs/TESTING.md) for what has and hasn't been
checked in the game.

### Translated
- **Story mode (Fighting Road):** all 522 scenes, about 9,400 messages, across the
  prologue and the six promotion routes.
- **Menus and system text:** about 1,000 strings in the main menus, match setup, results,
  Edit Mode, CPU logic, Edit Ranking, memory card and PocketStation screens, the
  paint editor, and the main program.
- **Roster:** all 194 wrestlers' names and nicknames, plus the bonus edit wrestlers and
  their Edit Ranking profiles.
- **Moves:** 840 move names.
- **Dojo tutorial:** all 43 lessons, with their button icons repositioned.
- **Graphics:** 26 images, namely the mode-select names, the wrestler-select labels and the
  victory captions.
- **Memory card:** the save titles for the game and the PocketStation.

### Added
- A variable-width font for story text and menus, so English fits the original windows.
- Real names for the wrestlers, promotions and referees that the original game disguises.
- Three patches: English; English with everything unlocked; Japanese with everything
  unlocked.
- In the All Unlocked English patch: unused heads and body parts found on the disc are
  added to Wrestler Make.

### Known issues
- Most story routes and endings haven't been played through yet
  ([TESTING.md](docs/TESTING.md)).
- The staff credits after the story ending are still in Japanese.
- The Japanese (All Unlocked) patch hasn't been tested in the game.
- Only the original release (SLPS-02065) is supported, not the Spike Library reissue
  (SLPS-02817).
- About 36 story lines are close to the edge of the text box. They're still readable, but
  worth a look while testing.
