#!/usr/bin/env python3
"""Fill the JSON data block of a reference page in docs/ (the guide).

    python3 tools/pagedata.py docs/guide/index.html DATA.json [--check]

A page keeps its data on one line between
    <script type="application/json" id="page-data">  and  </script>
and renders it with its own script, so the page stays one file with no build step. This
replaces what's between the markers with DATA.json, compacted. --check only reports whether
the page is up to date (exit 1 if not).

A data tool (tools/guidedata.py) reads the original's tables and the English names from text/,
then calls write(), so the page always uses the patch's names.
"""
import argparse
import json
import os
import sys

START, END = '<script type="application/json" id="page-data">', "</script>"


def write(page, data, check=False):
    """Put data (JSON-serialisable) into page's data block; with check, only compare.
    Returns True when the page was already up to date."""
    html = open(page, encoding="utf-8").read()
    a = html.find(START)
    b = html.find(END, a + len(START)) if a >= 0 else -1
    if a < 0 or b < 0:
        sys.exit(f"{page}: no {START}...{END} block")
    # "</" inside a script would end it early: escape the slash, as JSON allows
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    new = html[:a + len(START)] + blob + html[b:]
    if new == html:
        return True
    if check:
        sys.exit(f"{os.path.relpath(page)}: data out of date - run tools/guidedata.py")
    with open(page, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print(f"{os.path.relpath(page)}: data block updated ({len(blob):,} bytes)")
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("page", help="the page, e.g. docs/guide/index.html")
    ap.add_argument("data", help="a JSON file")
    ap.add_argument("--check", action="store_true", help="only check that the page is up to date")
    args = ap.parse_args(argv)
    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    if write(args.page, data, args.check) and args.check:
        print(f"{args.page}: up to date")


if __name__ == "__main__":
    main()
