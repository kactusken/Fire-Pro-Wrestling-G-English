"""Small helpers for patching a loaded MIPS image (the EXE or a code overlay).

Addresses are RAM addresses; `base` is the image's load address. An address
"pair" is the usual way MIPS code loads a 32-bit address: `lui reg, hi`
followed by `addiu`/`lw`/`sw`... (signed low half) or `ori` (unsigned low half).
"""
import struct

ORI = 13   # opcode whose immediate is unsigned


def word(img, base, addr):
    return struct.unpack_from("<I", img, addr - base)[0]


def put_word(img, base, addr, value):
    struct.pack_into("<I", img, addr - base, value)


def patch_words(img, base, patches, what="code"):
    """Apply (address, expected old word, new word) patches, checking each old word."""
    for addr, old, new in patches:
        if word(img, base, addr) != old:
            raise SystemExit(f"{what}: unexpected code at {addr:#x}")
        put_word(img, base, addr, new)


def _halves(target, unsigned_lo):
    if unsigned_lo:
        return target >> 16, target & 0xFFFF
    return ((target + 0x8000) >> 16) & 0xFFFF, target & 0xFFFF


def pair_target(img, base, lui, lo):
    """The address that the lui at `lui` and the instruction at `lo` load."""
    hi_w, lo_w = word(img, base, lui), word(img, base, lo)
    low = lo_w & 0xFFFF
    if lo_w >> 26 != ORI:
        low = (low ^ 0x8000) - 0x8000
    return ((hi_w & 0xFFFF) << 16) + low


def set_pair(img, base, lui, lo, target, expect=None):
    """Make a lui/lo pair load `target`. With `expect`, first check that it loads that."""
    if expect is not None and pair_target(img, base, lui, lo) != expect:
        raise SystemExit(f"unexpected address loaded at {lui:#x}: "
                         f"{pair_target(img, base, lui, lo):#x}, expected {expect:#x}")
    hi_w, lo_w = word(img, base, lui), word(img, base, lo)
    hi, low = _halves(target, lo_w >> 26 == ORI)
    put_word(img, base, lui, (hi_w & 0xFFFF0000) | hi)
    put_word(img, base, lo, (lo_w & 0xFFFF0000) | low)


def repoint(img, base, refs, target):
    """Point every reference at `target`. refs: ("p", pointer address) for a
    32-bit pointer in data, or ("c", lui, lo, ...) for an address pair in code."""
    for ref in refs:
        if ref[0] == "p":
            put_word(img, base, ref[1], target)
        else:
            set_pair(img, base, ref[1], ref[2], target)
