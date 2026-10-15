"""Archive, image and disc-sector formats."""
import os
import struct
import tempfile
import unittest

import discpatch
import fpgbin
import gfx
import pngread
from tests import TestCase, ROM, needs_rom


class FpgArchiveTest(TestCase):
    def test_pack_then_unpack_round_trip(self):
        entries = [b"first", bytes(3000), b"x" * 0x801, b"\x01"]
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in")
            os.makedirs(src)
            for i, data in enumerate(entries):
                open(os.path.join(src, f"{i:03d}.bin"), "wb").write(data)
            archive = os.path.join(d, "FPG.BIN")
            fpgbin.pack(src, archive)
            toc = fpgbin.read_toc(open(archive, "rb").read())
            self.assertTrue(all(off % 0x800 == 0 for off, _ in toc[:-1]), "entries are sector aligned")
            out = os.path.join(d, "out")
            fpgbin.unpack(archive, out)
            for i, data in enumerate(entries):
                self.assertEqual(open(os.path.join(out, f"{i:03d}.bin"), "rb").read(), data)

    def test_empty_entry_is_refused(self):
        # A zero size marks the end of the table, so an empty entry would cut the archive short.
        with tempfile.TemporaryDirectory() as d:
            for i, data in enumerate((b"a", b"", b"c")):
                open(os.path.join(d, f"{i:03d}.bin"), "wb").write(data)
            with self.assertRaises(SystemExit):
                fpgbin.pack(d, os.path.join(d, "FPG.BIN"))


class PngTest(TestCase):
    def test_indexed_png_round_trip(self):
        width, height = 6, 3
        pixels = bytes((x + y) % 4 for y in range(height) for x in range(width))
        palette = [0x0000, 0x7FFF, 0x001F, 0x03E0] + [0] * 12   # PS1 15-bit colours
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "test.png")
            gfx.write_png(path, width, height, pixels, palette)
            png = pngread.read(path)
        self.assertEqual((png.width, png.height), (width, height))
        self.assertTrue(png.indexed)
        self.assertEqual(bytes(v for row in png.rows for v in row), pixels)


class SectorTest(TestCase):
    @needs_rom
    def test_edc_ecc_match_the_original_disc(self):
        # Recomputing EDC/ECC for untouched sectors must reproduce them exactly.
        with open(ROM, "rb") as f:
            for lba in (16, 17, 24, 25, 158):
                f.seek(lba * 2352)
                sector = f.read(2352)
                fixed = bytearray(sector)
                fixed[0x818:] = bytes(len(fixed) - 0x818)
                discpatch.fix_sector(fixed)
                self.assertEqual(bytes(fixed), sector, f"sector {lba}")

    def test_fix_sector_is_stable(self):
        sector = bytearray(2352)
        sector[0x10:0x818] = (bytes(range(256)) * 9)[:0x808]
        discpatch.fix_sector(sector)
        once = bytes(sector)
        discpatch.fix_sector(sector)
        self.assertEqual(bytes(sector), once)
        self.assertEqual(struct.unpack_from("<I", sector, 0x818)[0],
                         discpatch.edc(sector[0x10:0x818]))


if __name__ == "__main__":
    unittest.main()
