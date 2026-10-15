import struct
import unittest

from tests import TestCase

import codepatch
from mips_asm import assemble

BASE = 0x8005A718


def image(source):
    code, _ = assemble(source, BASE)
    return bytearray(code)


class PairTest(TestCase):
    def test_addiu_pair_with_negative_low_half(self):
        # 0x8007C000: the low half 0xC000 is negative, so lui holds 0x8008.
        img = image("lui a0, 0x8008\naddiu a0, a0, -0x4000")
        self.assertEqual(codepatch.pair_target(img, BASE, BASE, BASE + 4), 0x8007C000)

    def test_set_pair_rounds_high_half(self):
        img = image("lui a0, 0x8006\naddiu a0, a0, 0x10")
        codepatch.set_pair(img, BASE, BASE, BASE + 4, 0x8007C000, expect=0x80060010)
        self.assertEqual(codepatch.word(img, BASE, BASE) & 0xFFFF, 0x8008)
        self.assertEqual(codepatch.pair_target(img, BASE, BASE, BASE + 4), 0x8007C000)

    def test_set_pair_keeps_registers_and_opcodes(self):
        img = image("lui t3, 0x8006\nlw v1, 0x10(t3)")
        before = [codepatch.word(img, BASE, BASE + i) & 0xFFFF0000 for i in (0, 4)]
        codepatch.set_pair(img, BASE, BASE, BASE + 4, 0x80071234)
        after = [codepatch.word(img, BASE, BASE + i) & 0xFFFF0000 for i in (0, 4)]
        self.assertEqual(before, after)
        self.assertEqual(codepatch.pair_target(img, BASE, BASE, BASE + 4), 0x80071234)

    def test_ori_pair_uses_unsigned_low_half(self):
        img = image("lui a0, 0x8006\nori a0, a0, 0x10")
        codepatch.set_pair(img, BASE, BASE, BASE + 4, 0x8007C000)
        self.assertEqual(codepatch.word(img, BASE, BASE) & 0xFFFF, 0x8007)
        self.assertEqual(codepatch.word(img, BASE, BASE + 4) & 0xFFFF, 0xC000)
        self.assertEqual(codepatch.pair_target(img, BASE, BASE, BASE + 4), 0x8007C000)

    def test_set_pair_checks_expected_target(self):
        img = image("lui a0, 0x8006\naddiu a0, a0, 0x10")
        with self.assertRaises(SystemExit):
            codepatch.set_pair(img, BASE, BASE, BASE + 4, 0x80070000, expect=0x80060020)


class RepointTest(TestCase):
    def test_pointer_and_code_references(self):
        img = image("lui a0, 0x8006\naddiu a0, a0, 0x10\nnop") + struct.pack("<I", 0x80060010)
        refs = [("c", BASE, BASE + 4, True), ("p", BASE + 12)]
        codepatch.repoint(img, BASE, refs, 0x80079ABC)
        self.assertEqual(codepatch.pair_target(img, BASE, BASE, BASE + 4), 0x80079ABC)
        self.assertEqual(codepatch.word(img, BASE, BASE + 12), 0x80079ABC)


class PatchWordsTest(TestCase):
    def test_applies_checked_patches(self):
        img = image("addiu v0, zero, 108")
        codepatch.patch_words(img, BASE, [(BASE, 0x2402006C, 0x24020078)])
        self.assertEqual(codepatch.word(img, BASE, BASE), 0x24020078)

    def test_refuses_unexpected_code(self):
        img = image("addiu v0, zero, 108")
        with self.assertRaises(SystemExit):
            codepatch.patch_words(img, BASE, [(BASE, 0x12345678, 0)])


if __name__ == "__main__":
    unittest.main()
