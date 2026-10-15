"""Parsing and encoding of the translation files."""
import os
import tempfile
import textwrap
import unittest

from tests import TestCase

import fill_text
import script
import strtab


def write(dirname, name, text):
    path = os.path.join(dirname, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(textwrap.dedent(text).lstrip("\n"))
    return path


class EncodeTest(TestCase):
    def test_ascii_stays_single_byte(self):
        self.assertEqual(strtab.encode_en("Grab"), b"Grab")

    def test_line_breaks(self):
        self.assertEqual(strtab.encode_en(r"One\nTwo"), b"One\nTwo")

    def test_pen_codes_pass_through(self):
        self.assertEqual(strtab.encode_en("Ankle:#x12,"), b"Ankle:#x12,")

    def test_full_width_text_is_shift_jis(self):
        self.assertEqual(strtab.encode_en("・Save."), "・".encode("cp932") + b"Save.")


class StrtabFileTest(TestCase):
    def test_parse_reads_english_by_address(self):
        with tempfile.TemporaryDirectory() as d:
            path = write(d, "ov.txt", """
                # overlay 001: strings
                @ 8005a7e8 len=12 refs=p1,c0
                JP － 次へ －
                EN - Next -

                @ 8005a7f4 len=12 refs=p1,c0
                JP 爆破時間
            """)
            self.assertEqual(strtab.parse(path), {0x8005A7E8: "- Next -"})


class StoryScriptTest(TestCase):
    def test_parse_text_groups_lines_per_message(self):
        with tempfile.TemporaryDirectory() as d:
            path = write(d, "000.txt", """
                @ 000
                JP 「俺は・・・勝ったのか・・・
                EN "I... I won...?
                EN  The belt...?"

                @ 001
                JP 削除
            """)
            self.assertEqual(script.parse_text(path), {0: ['"I... I won...?', ' The belt...?"']})

    def test_messages_use_crlf(self):
        self.assertEqual(script.encode_message(["Line one", "Line two"]), b"Line one\r\nLine two")

    def test_scene_block_round_trip(self):
        code = b"\x00\x04\x00\x0c" + bytes(8)   # header (0x0004, table at 12) + bytecode
        msgs = [b"Hello", "・はい".encode("cp932"), b""]
        block = script.build_scene(code, msgs)
        self.assertEqual(script.split_scene(block), (code, msgs))

    def test_index_drops_trailing_zeroes(self):
        idx = bytes([0, 0, 5, 0, 9, 0, 0, 0, 0, 0])
        self.assertEqual(script.load_index(idx), [0, 5, 9])


class FillTextTest(TestCase):
    SOURCE = """
        @ 8005b000 len=8 refs=p1,c0
        JP 左右反転

        @ 8005b008 len=8 refs=p1,c0
        JP 消去
        EN Erase

        @ 8005b010 len=8 refs=p1,c0
        JP 未訳
    """

    def run_fill(self, *extra):
        with tempfile.TemporaryDirectory() as d:
            path = write(d, "ov.txt", self.SOURCE)
            table = write(d, "table.py", 'EN = {"左右反転": "Flip H", "消去": "Clear"}\n')
            fill_text.main([path, table, *extra])
            return strtab.parse(path)

    def test_fills_only_missing_english(self):
        self.assertEqual(self.run_fill(), {0x8005B000: "Flip H", 0x8005B008: "Erase"})

    def test_overwrite_replaces_existing_english(self):
        self.assertEqual(self.run_fill("--overwrite"), {0x8005B000: "Flip H", 0x8005B008: "Clear"})


if __name__ == "__main__":
    unittest.main()
