"""Move fixes: three moves whose status flags disagree with their other versions.

Status byte 19 of a move block holds the critical types (bits 0-5), "give up"
(bit 6: the move can make the opponent submit) and "foul" (bit 7); see
docs/MOVES.md, "Criticals". Each move below has another version, the same move
from a different position, with the value given here. Applied by build.py
unless --no-move-fixes.

The match loads the moves from FPG 252-258 (LZSS; each file a table of 1,600 u32
offsets by move id, then blocks, and only some ids are its own). FPG 274 holds
an uncompressed copy (1,792 {u32 offset, u32 size}); both are patched. The block
in 252-258 is found by comparing it with 274's copy. The packed files are
changed with lzss.patch, which keeps the stream apart from a few bytes around
each change, so the rest of FPG.BIN (and the xdelta patch) stays small.
"""
import struct

import lzss

FLAGS = 19                      # status byte 19
MOVE_FILES = [f"{n:03d}" for n in range(252, 259)]
COPY = "274"

# move id -> (original, fixed, why)
FIXES = {
    1248: (0x01, 0x41, "Arching Boston Crab (face up) can't make the opponent give up; "
                       "face down (1345) can"),
    1029: (0x01, 0x81, "Low Blow from behind isn't a foul; from the front (782) it is"),
    1073: (0x40, 0x49, "Haruki Special from behind has no criticals; from the front (891) "
                       "it has Finisher and Submission"),
}


def apply(fpg274, files):
    """fpg274: bytearray of FPG 274; files: {entry: bytearray of 252-258, unpacked}.
    Patches them in place; -> the entries of `files` that changed."""
    changed = set()
    for move, (old, new, _) in FIXES.items():
        off, size = struct.unpack_from("<II", fpg274, 8 * move)
        block = bytes(fpg274[off:off + size])
        if not size or block[FLAGS] != old:
            raise SystemExit(f"move fixes: move {move} is not as expected")
        hits = []
        for entry, buf in files.items():
            at = struct.unpack_from("<I", buf, 4 * move)[0]
            if buf[at:at + size] == block:
                hits.append((entry, at))
        if len(hits) != 1:
            raise SystemExit(f"move fixes: move {move} found {len(hits)} times in 252-258")
        entry, at = hits[0]
        files[entry][at + FLAGS] = new
        fpg274[off + FLAGS] = new
        changed.add(entry)
    return changed


def apply_packed(fpg274, packed):
    """Like apply, but for the files as stored: packed is {entry: compressed bytes}.
    -> {entry: new compressed bytes} for the files that changed."""
    files = {entry: bytearray(lzss.decompress(data)) for entry, data in packed.items()}
    out = {}
    for entry in apply(fpg274, files):
        out[entry] = lzss.patch(packed[entry], files[entry]) or lzss.compress(bytes(files[entry]))
    return out
