"""The CSV tables in text/ and docs/.

Comma-separated, UTF-8, quoted where a cell holds a comma or a quote (any
spreadsheet program writes them this way). Lines starting with "#" are notes for
the reader, and are skipped along with blank lines.
"""
import csv
import io


def is_note(line):
    return line.startswith("#") or not line.strip()


def read(path):
    """-> the data rows of a table, as lists of cells (notes skipped)."""
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(ln for ln in f if not is_note(ln)))


def split(line):
    """One data line -> its cells."""
    return next(csv.reader([line]))


def join(cells):
    """Cells -> one data line (no line end)."""
    out = io.StringIO()
    csv.writer(out, lineterminator="").writerow(cells)
    return out.getvalue()


def write(path, rows, notes=()):
    """Write notes (lines without the "#"), then the rows."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        for note in notes:
            f.write(f"# {note}\n")
        csv.writer(f, lineterminator="\n").writerows(rows)
