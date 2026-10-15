# Translation guide

Where the game's text lives in this repository, the formats of those files, and the
style and names the translation uses. For building and checking, see
[BUILDING.md](BUILDING.md). For the in-game graphics, see [EDITING.md](EDITING.md).

## Where the text is

| File | What it holds | Limits checked by |
|---|---|---|
| `script/000.txt` … `script/521.txt` | The Fighting Road story, one file per scene | `build.py`, `tools/storylint.py`, `tools/storycheck.py` |
| `text/ov002_scene.txt` | Story-mode prompts built into the story module (save, "Ready for the match?") | same as the story |
| `text/ov001.txt` | Main menus, match setup, results, mode descriptions | `build.py`, `tools/uilint.py` |
| `text/ov002.txt` | Story-mode names and labels outside the script | same |
| `text/ov004.txt` | Edit Mode, CPU logic, memory card, options, Edit Ranking | same, plus Skill Edit box checks |
| `text/ov005.txt` | Logo/paint editor, name entry | same |
| `text/exe.txt` | Strings in the main program: results, countries, team names, music titles | `build.py` (no free space: strings are repacked into the original area) |
| `text/exe_promotions.py` | Promotion full and short names (fixed-size fields) | `build.py` |
| `text/wrestlers.tsv` | The 194-wrestler roster: short name, full name, nickname | `build.py` |
| `text/moves.tsv` | Move names | `build.py` |
| `text/edit_wrestlers.tsv` | Wrestler records outside the roster: the 30 bonus edit wrestlers, samples, the story hero's default | `build.py` |
| `text/edit_profiles.txt` | Profiles of the 30 bonus edit wrestlers (Edit Ranking) | `build.py` |
| `text/tutorial.txt` | The Dojo tutorial | `build.py` |
| `text/wrestler_list.txt` | Reference only: the stand-in names and the real wrestlers they stand for | — |

Every file starts with comment lines (`#`) explaining its limits. Read them before editing.

### Message files (`script/`, `text/ov*.txt`, `text/exe.txt`, `tutorial.txt`, `edit_profiles.txt`)

One block per message. `@` starts a block, `JP` lines are the original (leave them
alone), and `EN` lines are the translation:

```
@ 001
JP 「大観衆の声が聞こえる・・・こんなに
JP 　たくさんの観客が俺を祝福してくれている。
EN "I can hear the roar of the crowd... So
EN  many people, all of them cheering for
EN  me."
```

In the story files each `EN` line is one line on screen. A message with no `EN` lines
keeps its Japanese. In the menu files (`text/ov*.txt`, `text/exe.txt`) the `@` line also
gives the string's address, its original size in bytes, and how the code refers to it.
That's information for the build, not something to edit. In `tutorial.txt` and
`edit_profiles.txt`, `\n` starts a new line.

The `*_en.py` files next to some menu text files (`exe_en.py`, `ov004_en.py`,
`ov005_en.py`) are Japanese → English tables that were used to fill in those text files
in bulk with `tools/fill_text.py`. Edit the `.txt` file itself: it is what the build
reads. `fill_text.py` only fills strings that have no English yet, unless you pass
`--overwrite`.

### Tables (`.tsv`)

Tab-separated, one row per record, with a header row naming the columns. Edit only the
English columns (`en_*`, or `short` / `full` / `nickname` / `finisher`).

## Story style

- **Speaker label** on its own line, ending in `:`, for example `Sakagami:`,
  `#MS & Sakagami:` or `???:`.
- **Dialogue** goes in double quotes, opened and closed in every box. Continuation
  lines start with one space. Both 「」 and 『』 become "…". Narration is unquoted.
- **Choices** keep the `・` bullet, with one option per line. Spoken options are quoted.
- **Fit:** at most 3 text lines per box, plus the speaker line. Lines can be up to
  440 px wide, about 35 letters. `tools/storylint.py` and the build check this.
- `・・・` becomes `...`. Long runs of dots keep roughly their length.
- **Codes:** keep `#MS` / `#MF` (the player's short/full name) and `#PSnn` / `#PLnn`
  (a promotion's short/full name) as codes. Write **wrestlers as plain names**, not
  `#WSnnn`: that code gives the abbreviated select-list name ("Nishimr").
  [story_names.tsv](story_names.tsv) lists every wrestler code with its English name.
- A message whose text is only `削除` ("deleted") is never shown. Leave it untranslated.
- **Honorifics:** drop さん/君 in narration ("Choshu"). When someone is addressed
  politely, "Mr. Choshu" is fine. 先生 is "Coach". 先輩 is just the name (or "sir"). Don't
  use Japanese terms like senpai or sensei in the English.
- **Voice:** natural, punchy wrestling-promo English. Keep each character's register:
  heels are rude, veterans gruff, reporters polite. Keep shouts and emphasis (!!, ...).

## Menu style

- Keep English about as wide as the Japanese it replaces. Menus are drawn in windows
  with a fixed number of cells, and a Japanese character is 12 px. `tools/uilint.py`
  reports strings that are too wide.
- `#xN,` moves the pen N pixels (`#x-N,` moves it left). It lines up columns, so keep it
  where the Japanese has it.
- Terminology follows the established English Fire Pro guides: **Recovery**,
  **Breathing**, **Spirit**, **Submission**, and so on. Sub-items read as an indented
  `- X`. Skill Edit ratings use letter grades **C / C+ / B / B+ / A**.
- Edit Ranking's ﾗﾝｷﾝグ戦 menu item is **Fight**.

## Names

The game uses made-up stand-ins for real wrestlers, promotions and referees. The
translation uses the **real names** where they're known.

- **Wrestlers:** see `text/wrestlers.tsv` and the reference `text/wrestler_list.txt`.
  Story dialogue usually uses the surname.
- **Promotions:** `text/exe_promotions.py` maps each in-game promotion to the real one
  ("View Japan" → New Japan, "Olive Japan" → All Japan, …). The same names are used in
  team names and the story.
- **Referees:** パンサー鳥取 = Tiger Hattori, ジョー弘 = Joe Higuchi, Mr.水中 = Mr. Soranaka,
  バット若部 = Ted Tanabe. Match setup has room for about 75 px, so it shows "T. Hattori",
  "J. Higuchi", "Soranaka" and "T. Tanabe". Tanabe also speaks in the story (scenes 458,
  492, 493).

### Story glossary

| Japanese | English | Notes |
|---|---|---|
| 若元一徹 (#WL026, 先生) | Kotetsu Yamamoto, "Coach Yamamoto", label `Yamamoto:` | The dojo coach |
| #WS141 | label `Y. Yamamoto:` | To tell him apart from Coach Yamamoto |
| ホンダブラザーズ | the Yamaha Brothers | Yamamoto's old US tag team |
| 坂上浩一 | Koichi Sakagami (`Sakagami:`) | Fellow trainee and rival |
| 増田信行 | Nobuyuki Masuda | |
| ゾンビ・マサ / マサ | Masa Saito (`Masa:`) | New Japan's overseas man. The Saitos go by first name: `Masa:`, `Hiro:`, `Akitoshi:` |
| ディンク・カクラコンJr. / ディンク | Vince McMahon Jr. (`McMahon:`) | |
| 正井 / マサイ | Asai (Ultimo Dragon; label `Ultimo:`) | |
| バット若部 | Ted Tanabe | Referee |
| 坂内（社長） | (President) Sakaguchi | |
| 中岡（記者） | Nakaoka | Reporter |
| 記者 | Reporter | |
| マイク・ベアー | Mark Kerr | |
| ＪＥＮ / ＺＥＲＵ | ZEN / Team Zero | |
| 長州 (#WS013) etc. | Surnames: Choshu, Hashimoto, Chono, Tenzan, Mutoh… | Chono says "Huh!?" for エー, Tenzan "oeh!". Austin is "Stone Cold" |
| 道場 / 先生 | dojo / Coach | |
| ハンマースルー | Irish whip | |
| ヤングタイガー | Young Lions | New Japan rookies |
| 王道 | the King's Road | All Japan's style |
| 正規軍 | the regular army / the regulars | New Japan's main roster |
| ＦＷＯ・ＪＡＰＡＮ / ＦＷＯ | nWo JAPAN / nWo | Chono's faction |
| レッドＦＷＯ / ブラックＦＷＯ | nWo Wolfpac / nWo Hollywood | |
| 倒幕軍 | the Heisei Ishingun / the Ishingun | Koshinaka's faction |
| Ｖ１－ＴＲＹＭＡＸ | G1 CLIMAX | New Japan's tournament |
| 『チャンプ・オブ・ザ・ハイパージュニア』 | Super J-Cup | Best guess |
| 四天王 / 第三世代 | the Four Pillars / Third Generation | All Japan |
| ワールド三冠 / 三冠 | Triple Crown | |
| 東洋タッグ / ワールドタッグ | All Asia Tag / World Tag | |
| ワールドワンタッグ（決定）リーグ戦 | Real World Tag League | |
| チャンピオンフェスティバル | Champion Carnival | |
| すばる杯 | Asunaro Cup | |
| ライトニング | Burning | Kobashi & Akiyama |
| 悪者協会 / フレンドリー軍団 | Akuyaku Shokai / Family Gundan | |
| ＵＷＨ | UWF | The original UWF (Maeda, Takada, Fujiwara) |
| ＵＷＨインテグラル / Ｕインテグラル | UWF International / UWF-i | Takada's |
| キャッスル | Kingdom | Anjoh's promotion |
| #WS150組 | Fujiwara Gumi | |
| ギガバトルトーナメント | Mega Battle Tournament | RINGS |
| ハイブリッド・レスリング | Hybrid Wrestling | Pancrase. キングオブ#PS10 = King of #PS10 |
| バーリトゥード | vale tudo | |
| グルーサム（ファイティング） | Gruesome Fighting | The event Don Frye won, i.e. the UFC |
| 邪道 | outlaw / the outlaw way | Onita's banner |
| ＵＬＯ | UFO | Inoki's group |
| ＥＸＷ | ECW | |
| 西連隊ＥＸ / 西連隊 | Kaientai DX / Kaientai ("Kai-En-Tai" from McMahon) | |
| ノーリストリクト | Team No Respect | FMW faction |
| ＷＩＮＮＩＮＧ | W*ING | |
| フトットルース | Footloose | Fuyuki & Kanemura |
| #WS071軍 | Fuyuki-gun | |
| フォー・ナイツ | the Four Horsemen | |
| チーム・カンパニー / 魔界同盟 | the Corporation / the Ministry of Darkness | |
| ロード・#WL119ズ / ロードブラスターズ | the Road Warriors | |

## Reference data

- [story_names.tsv](story_names.tsv): every wrestler code used in the story, with the
  name to write.
- [story_titles.tsv](story_titles.tsv): a title and one-line summary for each scene, used
  by the route map.
- [story_battles.tsv](story_battles.tsv): every story match, with opponents, partner,
  rules, venue, referee and music (from `tools/storybattles.py`).
- [route-map/index.html](route-map/index.html): the interactive route map. Rebuild it with
  `tools/storymap.py` after changing scene titles.
