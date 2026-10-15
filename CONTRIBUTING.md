# Contributing

Thanks for helping with the Fire Pro Wrestling G translation. You don't need to know
Japanese or be a programmer to help: right now, playing the game and reporting what you
see is the most useful thing anyone can do.

## Ways to help

- **Play and report.** Most story routes and endings haven't been played through yet.
  [docs/TESTING.md](docs/TESTING.md) lists what has been checked and what hasn't. Open an
  [issue](../../issues) for anything that looks wrong, and for an untested route even when
  everything looked fine. Include a screenshot, the patch you used and where you were
  ([details](README.md#reporting-problems)).
- **Improve the translation.** Fix a typo, a line that reads oddly, a name, or text that
  doesn't fit. You can do this from GitHub's web editor without building anything,
  although building lets you check your change in the game.
- **Redraw images** with English text ([docs/EDITING.md](docs/EDITING.md)).
- **Code and research.** Improve the tools, or work out more of the game's formats
  ([docs/TECHNICAL.md](docs/TECHNICAL.md) ends with open questions).

For anything large, such as renaming a wrestler or promotion across the whole game or
changing how a patch works, open an issue first so it can be discussed before you put in
the work.

## Never share game data

The project only shares patches, never the game itself. Don't commit, attach or link:

- disc images (`.bin`, `.cue`, `.iso`, `.chd` and so on),
- files from the disc or made from it: `extracted/`, `build/`, `release/` and the review
  sheets in `review/` all stay on your machine.

`.gitignore` already keeps these out of git. Screenshots are fine, and so are the Japanese
lines in the text files, which the project includes for translators.

## Setting up

See [docs/BUILDING.md](docs/BUILDING.md). In short: Python 3.8 or newer, your own copy of the
original disc in `rom/`, then:

```sh
python3 build.py              # build the patched game into build/
python3 tools/extract.py      # unpack the disc for the checking tools (once)
```

## Changing the translation

[docs/TRANSLATION.md](docs/TRANSLATION.md) says which file holds which text, how the files
are laid out, and the style guide and glossary to follow. In short:

- Edit only the `EN` lines (and the English columns of the `.tsv` tables). The `JP` lines
  and the `@` lines are what the build uses to find the text.
- Use the names and terms in the glossary. If you think one is wrong, raise it in an
  issue, because the same name usually appears in many places.
- Read the comments at the top of a file before editing it: they give its limits.

Then check your change:

```sh
python3 tools/storylint.py               # story text: should report 0 problems
python3 tools/storycheck.py              # story text: line widths as the game draws them
python3 tools/uilint.py text/ov004.txt   # menu text: strings that may be too wide
python3 build.py                         # stops if something doesn't fit
```

If you can, look at the changed text in an emulator and add a screenshot to your pull
request. For story scenes, a build with `--debug-menu` jumps straight to any scene
([docs/TESTING.md](docs/TESTING.md#testing-with-a-debug-build)).

## Changing images

Follow [docs/EDITING.md](docs/EDITING.md). Your work in progress lives in
`images/handmade/`, which git ignores. When an image is finished, approve it with
`tools/edit.py`: that copies it to `images/approved/` and marks it `done` in
`images/graphics.csv`, and those two are what you commit. `make_patches.py` refuses to make
a release while unapproved images are still in `images/handmade/`.

## Changing code

- `build.py` and everything it imports use only the Python standard library, and must
  keep working on Python 3.8. Only the image tools (Pillow) and the disassembler
  (capstone) may use other packages, listed in `requirements.txt`.
- Tools take their input and output paths as command-line options, with defaults relative
  to the repository from [tools/paths.py](tools/paths.py). Give every tool a `--help`.
- A patch to game code should check the original bytes before it changes them, so it
  fails loudly on the wrong disc. `codepatch.patch_words` and `codepatch.set_pair(...,
  expect=...)` do this.
- Builds are reproducible. If your change shouldn't change the game (a refactor, a new
  tool), build before and after and compare the images' checksums (`sha1sum` on Linux,
  `certutil -hashfile FILE SHA1` on Windows): they must match.
- Document what you find. Patches are described in [docs/PATCHES.md](docs/PATCHES.md),
  formats in [docs/TECHNICAL.md](docs/TECHNICAL.md), and tools in
  [tools/README.md](tools/README.md).

Before you open a pull request, run the tests and the linter:

```sh
python3 -m unittest discover -s tests -t .
ruff check .
```

Most tests need no game data. The ones that do are skipped until `extracted/` exists.
GitHub runs both on every push and pull request.

## Pull requests

- Keep each pull request to one topic: a route's scenes, one screen, one tool.
- Say what you changed and how you checked it, especially what you looked at in the game.
- Commit messages start with the area they touch, as in the existing history:
  `Story: scene 214 typo`, `Edit Ranking: profile text fits its box`,
  `Docs: overlay 003 notes`.
- Add a line to the unreleased section of [CHANGELOG.md](CHANGELOG.md) for anything a
  player would notice.

## License

The code is released under the [MIT License](LICENSE). By contributing code, you agree that
your contribution is released under the same license.
