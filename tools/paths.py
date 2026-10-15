"""Default file locations shared by the command-line tools.

Every tool takes its inputs and outputs as options. Defaults are paths relative
to the repository root, so the tools work from any directory; a path given on
the command line is relative to the current directory, as usual.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROM = "rom/Fire Pro Wrestling G (Japan).bin"   # the original disc image (not included)
EXTRACTED = "extracted"                       # tools/extract.py output
BUILD = "build"
RELEASE = "release"
SCRIPT = "script"
TEXT = "text"
IMAGES = "images"
REVIEW = "review"
DOCS = "docs"


def repo(rel):
    """A repository-relative path made absolute."""
    return os.path.join(ROOT, rel)


def add(parser, flag, default, help, **kw):
    """Add a path option whose default is relative to the repository root."""
    parser.add_argument(flag, default=repo(default), metavar=kw.pop("metavar", "PATH"),
                        help=f"{help} (default: {default})", **kw)
