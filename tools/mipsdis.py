#!/usr/bin/env python3
"""MIPS R3000A (PS1) disassembly helpers for PS-X EXE files (needs capstone: pip install -r requirements.txt).

Usage:
  <exe> is a PS-X EXE path, or raw-binary@hexbase for overlays.
  mipsdis.py <exe> <start_addr> [count]     disassemble count instructions
  mipsdis.py <exe> --refs <addr>            find lui/addiu|ori|lw pairs that build addr
  mipsdis.py <exe> --calls <addr>           find jal <addr>
"""
import struct

try:
    import capstone
except ImportError:
    raise SystemExit("needs capstone: python3 -m pip install -r requirements.txt") from None

MD = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)

REGS = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
        "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
        "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
        "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


class Exe:
    """A PS-X EXE, or a raw binary given as 'path@base' (e.g. an overlay)."""

    def __init__(self, path):
        if "@" in path:
            path, base = path.rsplit("@", 1)
            self.text = open(path, "rb").read()
            self.base = int(base, 16)
            self.pc0 = None
            self.header = 0
            return
        data = open(path, "rb").read()
        assert data[:8] == b"PS-X EXE"
        self.pc0 = struct.unpack_from("<I", data, 0x10)[0]
        self.base = struct.unpack_from("<I", data, 0x18)[0]
        self.text = data[0x800:]
        self.header = 0x800

    def word(self, addr):
        return struct.unpack_from("<I", self.text, addr - self.base)[0]

    def contains(self, addr):
        return self.base <= addr < self.base + len(self.text) - 3

    def file_offset(self, addr):
        return addr - self.base + self.header


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def disasm(w, pc):
    for ins in MD.disasm(struct.pack("<I", w), pc):
        return f"{ins.mnemonic} {ins.op_str}".strip()
    return f".word 0x{w:08x}"


def listing(exe, start, count):
    for i in range(count):
        pc = start + 4 * i
        w = exe.word(pc)
        print(f"{pc:08x}: {w:08x}  {disasm(w, pc)}")


def find_refs(exe, target):
    """Find code that materialises target via lui + (addiu|ori|load|store)."""
    hi_lui = ((target + 0x8000) >> 16) & 0xFFFF
    hi_ori = (target >> 16) & 0xFFFF
    n = len(exe.text) // 4
    for i in range(n):
        pc = exe.base + 4 * i
        w = exe.word(pc)
        if w >> 26 != 15:
            continue
        reg = (w >> 16) & 31
        imm = w & 0xFFFF
        for j in range(1, 12):
            if i + j >= n:
                break
            pc2 = pc + 4 * j
            w2 = exe.word(pc2)
            op2 = w2 >> 26
            if (w2 >> 21) & 31 != reg:
                continue
            lo = w2 & 0xFFFF
            if op2 in (9, 32, 33, 35, 36, 37, 40, 41, 43) and imm == hi_lui:
                if (imm << 16) + s16(lo) & 0xFFFFFFFF == target:
                    print(f"{pc:08x} .. {pc2:08x}: {disasm(w2, pc2)}")
            elif op2 == 13 and imm == hi_ori and lo == target & 0xFFFF:
                print(f"{pc:08x} .. {pc2:08x}: {disasm(w2, pc2)}")


def find_calls(exe, target):
    enc = (3 << 26) | ((target >> 2) & 0x3FFFFFF)
    for i in range(len(exe.text) // 4):
        pc = exe.base + 4 * i
        if exe.word(pc) == enc:
            print(f"{pc:08x}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Disassemble PS1 code, or find references and calls.")
    ap.add_argument("exe", help="PS-X EXE path, or raw-binary@hexbase for an overlay")
    ap.add_argument("start", nargs="?", help="hex address to disassemble from")
    ap.add_argument("count", nargs="?", type=int, default=64, help="instructions to list (default: 64)")
    ap.add_argument("--refs", metavar="ADDR", help="find lui/addiu|ori|lw pairs that build ADDR (hex)")
    ap.add_argument("--calls", metavar="ADDR", help="find jal ADDR (hex)")
    args = ap.parse_args()
    exe = Exe(args.exe)
    if args.refs:
        find_refs(exe, int(args.refs, 16))
    elif args.calls:
        find_calls(exe, int(args.calls, 16))
    elif args.start:
        listing(exe, int(args.start, 16), args.count)
    else:
        ap.error("give a start address, --refs or --calls")
