# Testing status

What has been checked in the game, and what still needs a playthrough. If you play any
part marked untested, please report what you saw, good or bad, in an
[issue](../../../issues). Include the patch you used and, for the story, the route and
roughly where you were.

| Mark | Meaning |
|---|---|
| ✅ | Verified in the game: the text is correct, fits, and reads well |
| 🟡 | Partly checked: seen once, or only some screens |
| ⬜ | Not tested yet |
| ❌ | Known problem (see the notes) |

What to look for:
- text that runs past its box or window, overlaps, or is cut off;
- Japanese that still shows;
- wrong names, typos, or lines that read oddly;
- anything that crashes, freezes or looks corrupted.

## Patches

| Patch | Status | Notes |
|---|---|---|
| English | 🟡 | Every build before the unlock patch was this variant, so most of the checks below also cover it |
| English (All Unlocked) | ✅ | The main test build |
| Japanese (All Unlocked) | ⬜ | Only the unlock patch, applied to the original game |
| Applying with Rom Patcher JS | ⬜ | The patches are made in a format it should read |
| Applying with Delta Patcher / xdelta3 | 🟡 | xdelta3 is checked automatically when the patches are made |

## Menus and modes

| Screen | Status | Notes |
|---|---|---|
| Title screen, mode select | ✅ | Mode names are translated graphics; the logo stays Japanese |
| Wrestler select | ✅ | Names, nicknames, labels, birth dates |
| Match setup (rules, ring, venue, referee) | ✅ | |
| Team battle setup | 🟡 | |
| Victory and title screens | ✅ | Translated captions |
| One Night Match | ✅ | |
| One Night Tournament | ✅ | Bracket and champion screen |
| Open League | ⬜ | |
| Elimination Match | ⬜ | |
| Battle Royal | ⬜ | |
| Death Match | ⬜ | Including the special death-match ring name |
| Gruesome Fighting | 🟡 | Bracket title seen |
| Title Match | ⬜ | Locked until Fighting Road is cleared, unless you use an All Unlocked patch |
| Dojo (tutorial) | ✅ | Lesson text and button icons |
| Options | ⬜ | Staff Credits is locked until Fighting Road is cleared |
| Memory Card (save, load, PocketStation) | ⬜ | |

## Edit Mode

| Screen | Status | Notes |
|---|---|---|
| Edit menu, Group Edit | 🟡 | |
| Wrestler Make (appearance) | 🟡 | The extra heads and body parts were checked in the All Unlocked build |
| Name entry | ⬜ | The kana grids stay Japanese on purpose |
| Skill Edit | ✅ | Letter-grade ratings |
| Parameter Edit | 🟡 | |
| Move Edit | ✅ | Labels and button icons |
| CPU Logic | ⬜ | |
| Save menu | ⬜ | |
| Logo / paint editor | ⬜ | |
| Edit Ranking | 🟡 | Ranking list and profiles seen. The intro and ending text share a fixed space budget, so check they display fully |

## Fighting Road (story mode)

The route is decided at graduation (scene 3). A hero who isn't a heavyweight goes to
Michinoku Pro. Otherwise the style you used most in the prologue tips the offer, together
with your earlier choices. For example, Power or Chokes lean toward New Japan, Throws or
Technique toward All Japan, Flying or Rough toward FMW, Submissions or Shoot toward the UWF,
and Striking or Performance toward America. The
[route map](route-map/index.html) shows every scene, choice and branch.

| Route | Scenes | Story matches | Endings | Status | Notes |
|---|---|---|---|---|---|
| Prologue | 0–3 | 3 | — | 🟡 | Parts seen during development |
| New Japan | 4–94 | 56 | 10 | ⬜ | |
| All Japan | 95–157, 518–519 | 44 | 6 | ⬜ | |
| FMW | 158–248 | 62 | 13 | ⬜ | |
| UWF | 249–396 | 97 | 10 | ⬜ | No choices; the longest route |
| America | 397–457 | 55 | 6 | ⬜ | |
| Michinoku Pro | 458–517 | 47 | 4 | ⬜ | |
| Story save prompts and the "Ready for the match?" choice | — | — | — | ⬜ | |
| Staff credits after an ending | — | — | — | ❌ | Still in Japanese (not translated yet) |

### Endings

Scene numbers are in parentheses. Tick one off by reporting it.

**New Japan:** Wrestler of the Year (58) · Best Bout, then retirement (59) · Onita defeated
(60) · Onita match lost (61) · slump and retirement (62). The same five also come in a
"regulars" version (90–94).

**All Japan:** Champion Carnival, ace of All Japan (143) · knee injury (144) · Best Bout and
Wrestler of the Year (147) · Best Bout, then retirement (148) · back injury (156) · joining
the Heisei Ishingun (157).

**FMW:** third golden age (209) · neck injury (210) · fighting back against Sakagami (211) ·
fired by Sakagami (212) · No Respect fades (214) · third golden age, regulars (230) · left in
the undercard (231) · beat Fuyuki (232) · FMW declines (233) · New Outlaw Legend (245) ·
outlaw heir fades (246) · outlaw heir after the Tenryu match (247) · fading alone (248).

**UWF:** years as ace (294) · knee gives out (295, 334, 396) · years of vale tudo (333, 395) ·
pre-match with Sakagami (335) · Kikuchi asks you to coach (336) · beat Sakagami at the Dome
(361) · beat Satake (362).

**America:** Sakagami reunion (425, 456) · Hashimoto loss (426) · Goldberg's streak ended
(444) · Mr. Socko sister angle (445, 457).

**Michinoku Pro:** ring ceremony (514) · Liger rematch promise (515) · Sakagami and Coach
Yamamoto (516) · overseas tour with Sakagami (517).

## Testing with a debug build

If you build the patch yourself ([BUILDING.md](BUILDING.md)), `python3 build.py --debug-menu`
adds the developer menu: hold **Select** and press **Start** on the title screen. Mode 4
(FR DEBUG) jumps straight to any story scene, which is handy for checking one scene or
ending without replaying a route. See
[HIDDEN_CONTENT.md](HIDDEN_CONTENT.md#developer-menu-and-debug-leftovers).
