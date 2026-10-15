"""Checks on the translation files in this repository. They need no game data,
so they catch most editing mistakes before a build (and on GitHub)."""
import csv
import glob
import os
import re
import runpy
import subprocess
import sys
import unittest

import editdata
import moves
import roster
import storylint
import strtab
import tutorial
from tests import TestCase, repo

SCENES = 522


def text(name):
    return repo("text", name)


class StoryScriptTest(TestCase):
    def test_every_scene_is_present(self):
        files = sorted(os.path.basename(f) for f in glob.glob(repo("script", "*.txt")))
        self.assertEqual(files, [f"{i:03d}.txt" for i in range(SCENES)])

    def test_scenes_pass_lint(self):
        problems = []
        for path in sorted(glob.glob(repo("script", "[0-9][0-9][0-9].txt"))):
            problems += storylint.lint_file(path)
        problems += storylint.lint_file(text("ov002_scene.txt"))
        self.assertEqual(problems, [])

    def test_english_is_encodable(self):
        for path in sorted(glob.glob(repo("script", "*.txt"))):
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if line.startswith("EN "):
                        try:
                            line[3:].rstrip("\n").encode("cp932")
                        except UnicodeEncodeError as e:
                            self.fail(f"{path}:{n}: {e}")

    def test_scene_titles_cover_every_scene(self):
        with open(repo("docs", "story_titles.tsv"), encoding="utf-8") as f:
            ids = {int(ln.split("\t")[0]) for ln in f if ln.strip() and not ln.startswith("#")}
        self.assertEqual(ids, set(range(SCENES)))


class MenuTextTest(TestCase):
    FILES = ["ov001.txt", "ov002.txt", "ov004.txt", "ov005.txt", "exe.txt"]

    def test_files_parse_and_encode(self):
        for name in self.FILES:
            entries = strtab.parse(text(name))
            self.assertTrue(entries, name)
            for addr, en in entries.items():
                with self.subTest(file=name, address=f"{addr:08x}"):
                    strtab.encode_en(en)

    def test_pen_codes_are_well_formed(self):
        # "#x" must be followed by a number and a comma, or the menu renderer misreads it.
        for name in self.FILES:
            for addr, en in strtab.parse(text(name)).items():
                for m in re.finditer(r"#x", en):
                    self.assertRegex(en[m.start():], r"^#x-?\d+,", f"{name} {addr:08x}: {en!r}")

    def test_fill_tables_load(self):
        for name in ("exe_en.py", "ov005_en.py"):
            self.assertIsInstance(runpy.run_path(text(name))["EN"], dict)


class RosterAndDataTest(TestCase):
    def test_roster_fits_its_fields(self):
        rows = roster.load(text("wrestlers.tsv"))
        self.assertEqual(sorted(rows), list(range(194)))
        roster.encode(rows)   # raises on a name that doesn't fit

    def test_move_names_load(self):
        names = moves.load(text("moves.tsv"))
        self.assertEqual(len(names), 840)
        for jp, en in names.items():
            self.assertTrue(en, jp.decode("cp932"))
            strtab.encode_en(en)

    def test_edit_records_fit_their_fields(self):
        rows = editdata.load(text("edit_wrestlers.tsv"))
        self.assertTrue(rows)
        record = bytearray(512)
        for row in rows:
            with self.subTest(record=row[0]):
                editdata.patch_record(record, 0, row)   # raises on a field that doesn't fit

    def test_edit_profiles_complete(self):
        self.assertEqual(len(editdata.load_profiles(text("edit_profiles.txt"))), editdata.PROFILE_COUNT)

    def test_tutorial_icons_match(self):
        for n, (jp, en) in enumerate(tutorial.load(text("tutorial.txt"))):
            self.assertEqual(en.count("{}"), len(re.findall(r"\[\d\]", jp)),
                             f"message {n}: button icon count differs")

    def test_promotion_names_fit(self):
        p = runpy.run_path(text("exe_promotions.py"))
        for full, short in p["NAMES"]:
            self.assertLess(len(strtab.encode_en(full)), p["FULL_SIZE"], full)
            self.assertLess(len(strtab.encode_en(short)), p["SHORT_SIZE"], short)


class ImagesTest(TestCase):
    def setUp(self):
        with open(repo("images", "graphics.csv"), encoding="utf-8") as f:
            self.rows = list(csv.DictReader(f))

    def test_statuses(self):
        for r in self.rows:
            self.assertIn(r["status"], ("todo", "done", "keep"), r["image"])

    def test_done_images_are_approved(self):
        approved = {os.path.basename(p)[:-4] for p in glob.glob(repo("images", "approved", "*.png"))}
        done = {r["image"] for r in self.rows if r["status"] == "done"}
        self.assertEqual(done - approved, set(), "marked done but no approved image")
        self.assertEqual(approved - {r["image"] for r in self.rows}, set(), "approved image not in the catalogue")


class DocsTest(TestCase):
    def test_relative_links_resolve(self):
        files = [repo("README.md"), repo("CHANGELOG.md"), repo("CONTRIBUTING.md"), repo("tools", "README.md")] + \
            glob.glob(repo("docs", "*.md"))

        def slug(heading):
            return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")

        for path in files:
            body = open(path, encoding="utf-8").read()
            for link in re.findall(r"\]\(([^)\s]+)\)", body):
                if link.startswith(("http:", "https:", "mailto:")) or "/issues" in link or "/releases" in link:
                    continue
                target, _, anchor = link.partition("#")
                full = os.path.normpath(os.path.join(os.path.dirname(path), target)) if target else path
                with self.subTest(file=os.path.relpath(path, repo()), link=link):
                    self.assertTrue(os.path.exists(full), "missing file")
                    if anchor and full.endswith(".md"):
                        heads = re.findall(r"^#+ (.+)$", open(full, encoding="utf-8").read(), re.M)
                        self.assertIn(anchor, [slug(h) for h in heads], "missing heading")


class ToolsHelpTest(TestCase):
    """Every command-line tool answers --help (catches import and argument mistakes)."""
    SKIP = {"edit.py", "render.py", "contact.py",   # need Pillow
            "mipsdis.py"}                           # needs capstone

    def test_help(self):
        scripts = [repo("build.py"), repo("make_patches.py")] + sorted(glob.glob(repo("tools", "*.py")))
        for path in scripts:
            if os.path.basename(path) in self.SKIP or "__main__" not in open(path, encoding="utf-8").read():
                continue
            with self.subTest(tool=os.path.basename(path)):
                r = subprocess.run([sys.executable, path, "--help"], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr[-500:])
                if os.path.basename(path) != "gdbrsp.py":   # prints its own usage text
                    self.assertIn("usage", (r.stdout + r.stderr).lower())


if __name__ == "__main__":
    unittest.main()
