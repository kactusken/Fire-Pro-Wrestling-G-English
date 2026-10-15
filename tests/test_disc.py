"""Tests against the game's own files. Skipped unless the disc is unpacked
(python3 tools/extract.py). The full-build test also needs the original image
and FPWG_SLOW=1, since it builds twice (about a minute)."""
import filecmp
import glob
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

from tests import EXTRACTED, ROM, TestCase, needs_extracted, needs_rom, repo

import fpgbin
import lzss
import script
import storycheck
import storylint
import vwf_patch

OVERLAYS = ["000", "001", "002", "003", "004", "005"]


def entry(name):
    return open(os.path.join(EXTRACTED, "fpg", f"{name}.bin"), "rb").read()


@needs_extracted
class ArchiveTest(TestCase):
    def test_overlays_recompress(self):
        # Our compressor must round-trip the game's code and not come out larger.
        for name in OVERLAYS:
            with self.subTest(overlay=name):
                original = entry(name)
                data = lzss.decompress(original)
                packed = lzss.compress(data)
                self.assertEqual(lzss.decompress(packed), data)
                self.assertLessEqual(len(packed), len(original))

    def test_fpg_repacks_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            fpgbin.unpack(os.path.join(EXTRACTED, "FPG.BIN"), os.path.join(d, "fpg"))
            fpgbin.pack(os.path.join(d, "fpg"), os.path.join(d, "FPG.BIN"))
            self.assertTrue(filecmp.cmp(os.path.join(d, "FPG.BIN"), os.path.join(EXTRACTED, "FPG.BIN"),
                                        shallow=False))


@needs_extracted
class StoryTest(TestCase):
    def test_japanese_in_script_files_matches_the_disc(self):
        # The JP lines in script/ are the reference translators work from; they must
        # be exactly what the game holds.
        with tempfile.TemporaryDirectory() as d:
            script.extract(os.path.join(EXTRACTED, "fpg", "130.bin"),
                           os.path.join(EXTRACTED, "fpg", "131.bin"), d)
            for path in sorted(glob.glob(os.path.join(d, "*.txt"))):
                ours = [ln for ln in open(repo("script", os.path.basename(path)), encoding="utf-8")
                        .read().split("\n") if ln.startswith("JP ")]
                disc = [ln for ln in open(path, encoding="utf-8").read().split("\n") if ln.startswith("JP ")]
                self.assertEqual(ours, disc, os.path.basename(path))

    def test_story_lint_with_widths(self):
        self.assertEqual(storylint.main(["--extracted", EXTRACTED]), 0)

    def test_text_layout_model_matches_the_real_hook(self):
        # storycheck's Python model of the VWF hook against the hook itself, run in
        # the simulator: same glyph slots, same pixels.
        self.assertEqual(storycheck.main(["0", "1", "2", "--verify", "6", "--extracted", EXTRACTED]), 0)

    def test_vwf_hook_assembles_into_overlay_002(self):
        ov = lzss.decompress(entry("002"))
        patched, symbols = vwf_patch.patch_overlay(ov, entry("128"))
        self.assertGreater(len(patched), len(ov))
        self.assertTrue(symbols)


@needs_rom
@unittest.skipUnless(os.environ.get("FPWG_SLOW"), "slow: set FPWG_SLOW=1")
class ReproducibleBuildTest(TestCase):
    def test_build_does_not_depend_on_hash_seed(self):
        digests = []
        with tempfile.TemporaryDirectory() as d:
            for seed in ("1", "2"):
                out = os.path.join(d, seed)
                env = dict(os.environ, PYTHONHASHSEED=seed)
                subprocess.run([sys.executable, repo("build.py"), "--rom", ROM, "--out-dir", out],
                               check=True, env=env, capture_output=True)
                with open(os.path.join(out, "Fire Pro Wrestling G (English).bin"), "rb") as f:
                    digests.append(hashlib.sha1(f.read()).hexdigest())
        self.assertEqual(digests[0], digests[1])


if __name__ == "__main__":
    unittest.main()
