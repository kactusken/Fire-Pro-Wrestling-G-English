"""Tests against the game's own files. Skipped unless the disc is unpacked
(python3 tools/extract.py). The full-build test also needs the original image
and FPWG_SLOW=1, since it builds twice (about a minute)."""
import filecmp
import glob
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest

from tests import EXTRACTED, ROM, TestCase, needs_extracted, needs_rom, repo

import costumes
import fpgbin
import lzss
import movedata
import movefix
import script
import storycheck
import storylint
import strtab
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
class MovesTest(TestCase):
    """docs/MOVES.md: move blocks, slots, variants and the Move Edit lists."""

    @classmethod
    def setUpClass(cls):
        cls.data = movedata.blocks(entry("274"))
        cls.roster = lzss.decompress(entry("010"))
        cls.sets = movedata.lists(open(os.path.join(EXTRACTED, "ovl", "004.bin"), "rb").read())
        cls.names = movedata.move_names(lzss.decompress(entry("011")), {})

    def records(self):
        for w in range(movedata.WRESTLERS):
            yield w, movedata.slot_values(self.roster[w * movedata.RECORD:(w + 1) * movedata.RECORD])

    def test_every_block_is_animations_then_forms(self):
        self.assertEqual(len(self.data), 1270)
        for i, b in self.data.items():
            with self.subTest(move=i):
                anims = movedata.animations(b)
                self.assertEqual(anims[0][0], 0)
                used = sum(1 + len(frames) for _, _, frames in anims)
                self.assertEqual(used, b[0x2F])
                self.assertEqual((len(b) - 0x30 - 12 * used) % 96, 0)

    def test_slots_have_one_finisher_and_at_most_four_signatures(self):
        for w, values in self.records():
            with self.subTest(wrestler=w):
                self.assertEqual(sum(1 for v in values if v & 0x2000), 1)
                self.assertLessEqual(sum(1 for v in values if v & 0x1000), 4)
                self.assertFalse(any(v & 0x800 for v in values))
                self.assertTrue(values[56] & 0x7FF)     # the 57th slot is in use

    def test_roster_moves_are_offered_with_all_variants(self):
        for w, values in self.records():
            for s, v in enumerate(values):
                first = v & 0x7FF
                if not first:
                    continue
                with self.subTest(wrestler=w, slot=s):
                    self.assertIn(first, self.sets["level9"][s])
                    for k in range(movedata.SLOTS[s][3]):
                        self.assertIn(first + k, self.data)
                        self.assertEqual(self.names[first + k], self.names[first])

    def test_punch(self):
        b = self.data[1]
        (_, head, frames), = movedata.animations(b)
        self.assertEqual((b[0], b[2], b[12], b[22], b[23], b[30]), (0, 4, 6, 11, 10, 0))
        self.assertEqual(struct.unpack_from("b", b, 20)[0], -37)
        self.assertEqual(movedata.SE[head[5]], "punch lv1")
        self.assertEqual([f[6] for f in frames], [6, 6, 8])
        self.assertEqual([f[8] & 0x80 for f in frames], [0, 0x80, 0])     # hits on frame 2
        self.assertEqual([struct.unpack_from(">H", f, 2)[0] for f in frames], [0x5A4, 0x5A5, 0x5A6])

    def test_critical_types(self):
        # record +0x54: Misawa (40) is a striker; Original Backdrop can be a suplex critical
        self.assertEqual(self.roster[40 * movedata.RECORD + 0x54], 1)
        self.assertEqual(self.data[948][19] & 0b100, 0b100)

    def test_global_forms(self):
        self.assertEqual(len(entry("270")), 0xFC0 * 96)


@needs_extracted
class MoveFixTest(TestCase):
    """docs/PATCHES.md, "Move fixes"."""

    def test_fixes_change_only_the_flags_and_fit(self):
        fpg = bytearray(open(os.path.join(EXTRACTED, "FPG.BIN"), "rb").read())
        copy = bytearray(entry(movefix.COPY))
        packed = {e: entry(e) for e in movefix.MOVE_FILES}
        new = movefix.apply_packed(copy, packed)
        self.assertEqual(sorted(new), ["255", "256", "257"])
        fixed = movedata.blocks(copy)
        for move, (_, value, _) in movefix.FIXES.items():
            self.assertEqual(fixed[move][movefix.FLAGS], value)
        for e, data in new.items():
            old, now = lzss.decompress(packed[e]), lzss.decompress(data)
            self.assertEqual(sum(a != b for a, b in zip(old, now)), 1, e)
            fpgbin.replace(fpg, int(e), data)       # fits without moving other entries


@needs_extracted
class CostumesTest(TestCase):
    """docs/COSTUMES.md: roster looks, the colour table and the part lists."""

    @classmethod
    def setUpClass(cls):
        cls.rows = list(costumes.rows(
            lzss.decompress(entry("010")), lzss.decompress(entry("011")),
            open(os.path.join(EXTRACTED, "ovl", "004.bin"), "rb").read(),
            strtab.parse(repo("text/ov004.txt")), {}))
        cls.header = costumes.header()

    def test_one_row_per_wrestler_and_costume(self):
        self.assertEqual(len(self.rows), costumes.WRESTLERS * costumes.COSTUMES)
        for row in self.rows:
            self.assertEqual(len(row), len(self.header))

    def test_every_part_is_in_a_wrestler_make_list(self):
        for row in self.rows:
            for slot in costumes.SLOTS:
                self.assertTrue(row[self.header.index(slot + "_name")], (row[0], row[3], slot))

    def test_misawa_first_costume(self):
        # roster 40 as seen in the game: green trunks (group 3) and knee pads (group 4),
        # white thigh stripes (group 1) and boots (group 6), black hair (group 9)
        row = dict(zip(self.header, self.rows[40 * 4]))
        self.assertEqual((row["stance"], row["size"], row["head"]), ("Technic", "M", 40))
        self.assertEqual([row[f"group3_{i}"] for i in (1, 2, 3)], ["#003100", "#007321", "#00C65A"])
        self.assertEqual(row["group4_3"], "#00C65A")
        self.assertEqual((row["group1_3"], row["group6_3"]), ("#E7E7E7", "#E7E7E7"))
        self.assertEqual(row["group9_1"], "#101010")

    def test_body_parts_unpack_to_whole_tiles(self):
        data = entry("251")
        for first, last, tile in ((320, 810, 288), (811, 870, 128)):
            for e in range(first, last + 1):
                off, size = struct.unpack_from("<II", data, 8 * e)
                with self.subTest(entry=e):
                    self.assertEqual(len(lzss.decompress(data[off:off + size])) % tile, 0)


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
