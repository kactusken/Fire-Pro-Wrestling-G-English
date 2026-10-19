"""build.py's and make_patches.py's command lines (no building)."""
import contextlib
import io
import os
import unittest

from tests import TestCase

import build
import make_patches
import paths


def parse(*argv):
    with contextlib.redirect_stderr(io.StringIO()):
        return build.parse_args(list(argv))


class OptionsTest(TestCase):
    def test_output_names(self):
        cases = {
            (): "Fire Pro Wrestling G (English)",
            ("--no-unlock",): "Fire Pro Wrestling G (English) (locked)",
            ("--no-unlock", "--no-extra-parts"): "Fire Pro Wrestling G (English) (locked) (no extra parts)",
            ("--debug-menu",): "Fire Pro Wrestling G (English) (debug)",
            ("--route5",): "Fire Pro Wrestling G (English) (debug) (route 5)",
            ("--fake-names", "--no-unlock"): "Fire Pro Wrestling G (English) (Fake Names) (locked)",
            ("--japanese",): "Fire Pro Wrestling G (Japan) (unlocked)",
            ("--name", "Custom"): "Custom",
        }
        for argv, name in cases.items():
            self.assertEqual(build.output_name(parse(*argv)), name, argv)

    def test_defaults_are_inside_the_repository(self):
        args = parse()
        self.assertEqual(args.rom, paths.repo(paths.ROM))
        self.assertEqual(args.text, paths.repo("text"))
        self.assertEqual(os.path.dirname(args.out_dir), paths.ROOT)

    def test_given_paths_are_kept_as_given(self):
        self.assertEqual(parse("--rom", "game.bin").rom, "game.bin")

    def test_japanese_rejects_translation_options(self):
        for extra in ("--debug-menu", "--route5", "--fake-names"):
            with self.assertRaises(SystemExit):
                parse("--japanese", extra)

    def test_build_steps_cover_every_stage(self):
        names = [s.__name__ for s in build.STEPS]
        self.assertEqual(names[0], "unpack_fpg")
        self.assertEqual(names[-2:], ["repack_fpg", "patch_exe"])


class ReleaseVariantsTest(TestCase):
    def test_five_variants_with_valid_options(self):
        self.assertEqual(len(make_patches.VARIANTS), 5)
        for name, options, description in make_patches.VARIANTS:
            parse(*options)   # must be accepted by build.py
            self.assertTrue(name.startswith("Fire Pro Wrestling G"))
            self.assertTrue(description)

    def test_names_are_unique(self):
        names = [v[0] for v in make_patches.VARIANTS]
        self.assertEqual(len(set(names)), len(names))


if __name__ == "__main__":
    unittest.main()
