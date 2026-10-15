"""Tests: python3 -m unittest discover -s tests -t .   (from the repository root)

Most tests need nothing but this repository. Those that read the game's files
are skipped unless the disc has been unpacked with tools/extract.py (or
FPWG_EXTRACTED points at the unpacked folder) and, for a few, unless the
original image is in rom/ (or FPWG_ROM points at it).
"""
import contextlib
import io
import os
import sys
import unittest
import warnings

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
for p in (TOOLS, REPO):
    if p not in sys.path:
        sys.path.insert(0, p)

EXTRACTED = os.environ.get("FPWG_EXTRACTED", os.path.join(REPO, "extracted"))
ROM = os.environ.get("FPWG_ROM", os.path.join(REPO, "rom", "Fire Pro Wrestling G (Japan).bin"))

needs_extracted = unittest.skipUnless(os.path.isfile(os.path.join(EXTRACTED, "SLPS_020.65")),
                                      "needs the unpacked disc (python3 tools/extract.py)")
needs_rom = unittest.skipUnless(os.path.isfile(ROM), "needs the original disc image in rom/")


def repo(*parts):
    return os.path.join(REPO, *parts)


class TestCase(unittest.TestCase):
    """unittest.TestCase that keeps the tools' progress messages out of the test
    output and ignores ResourceWarnings (the tools read files with
    open(...).read(), which CPython closes at once)."""

    def setUp(self):
        super().setUp()
        warnings.simplefilter("ignore", ResourceWarning)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
