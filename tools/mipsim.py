#!/usr/bin/env python3
"""Minimal MIPS R3000 interpreter for testing hooks offline.

Covers the integer instructions used by our patches and the game routines
they call. Branch delay slots and load delay slots are honoured: a loaded
value reaches its register only after the next instruction has run, as on
the R3000 (the instruction after a load still sees the old value).
"""

MEM_BASE = 0x80000000
MEM_SIZE = 0x200000
SCRATCH_BASE = 0x1F800000  # 1 KB scratchpad, mapped after main RAM
SCRATCH_SIZE = 0x400


class Halt(Exception):
    pass


class CPU:
    def __init__(self):
        self.mem = bytearray(MEM_SIZE + SCRATCH_SIZE)
        self.r = [0] * 32
        self.pc = 0
        self.stops = set()
        self.steps = 0
        self.pending = None  # (reg, value) of a load in its delay slot

    # memory -----------------------------------------------------------
    def _off(self, a, n):
        a &= 0xFFFFFFFF
        if SCRATCH_BASE <= a < SCRATCH_BASE + SCRATCH_SIZE:
            o = MEM_SIZE + a - SCRATCH_BASE
        else:
            o = a - MEM_BASE
        if not 0 <= o <= MEM_SIZE + SCRATCH_SIZE - n or (o >= MEM_SIZE and a < SCRATCH_BASE):
            raise Halt(f"bad address {a & 0xFFFFFFFF:#010x} at pc {self.pc:#010x}")
        if n > 1 and a % n:
            raise Halt(f"unaligned {n}-byte access {a:#010x} at pc {self.pc:#010x}")
        return o

    def load(self, addr, data):
        o = self._off(addr, 1)
        self.mem[o:o + len(data)] = data

    def rd(self, a, n, signed=False):
        o = self._off(a, n)
        v = int.from_bytes(self.mem[o:o + n], "little")
        if signed and v >> (8 * n - 1):
            v -= 1 << (8 * n)
        return v & 0xFFFFFFFF

    def wr(self, a, n, v):
        o = self._off(a, n)
        self.mem[o:o + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, "little")

    def w16(self, a, v):
        self.wr(a, 2, v)

    def r16(self, a, signed=False):
        return self.rd(a, 2, signed)

    def w32(self, a, v):
        self.wr(a, 4, v)

    def r32(self, a):
        return self.rd(a, 4)

    # execution ---------------------------------------------------------
    def step(self, w):
        """Execute one instruction, then retire the previous load."""
        pend, self.pending = self.pending, None
        before = self.r[pend[0]] if pend else None
        target = self.exec(w)
        if pend and pend[0] and self.r[pend[0]] == before:
            self.r[pend[0]] = pend[1]  # (unless this instruction wrote it)
        return target

    def run(self, pc, max_steps=2_000_000):
        self.steps = 0
        self.pending = None
        self.pc = pc
        npc = pc + 4
        while True:
            if self.pc in self.stops:
                return self.pc
            self.steps += 1
            if self.steps > max_steps:
                raise Halt("step limit")
            w = self.r32(self.pc)
            target = self.step(w)
            self.r[0] = 0
            if target is None:
                self.pc, npc = npc, npc + 4
            else:
                # execute delay slot
                slot_pc = npc
                self.pc = slot_pc
                ws = self.r32(slot_pc)
                if self.step(ws) is not None:
                    raise Halt(f"branch in delay slot at {slot_pc:#x}")
                self.r[0] = 0
                self.pc, npc = target, target + 4

    def exec(self, w):
        r = self.r
        op = w >> 26
        rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        sa, fn = (w >> 6) & 31, w & 63
        imm = w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        M = 0xFFFFFFFF
        pc = self.pc

        def s32(x):
            return x - (1 << 32) if x & 0x80000000 else x

        if op == 0:
            if fn == 0:
                r[rd] = (r[rt] << sa) & M
            elif fn == 2:
                r[rd] = r[rt] >> sa
            elif fn == 3:
                r[rd] = (s32(r[rt]) >> sa) & M
            elif fn == 4:
                r[rd] = (r[rt] << (r[rs] & 31)) & M
            elif fn == 6:
                r[rd] = r[rt] >> (r[rs] & 31)
            elif fn == 7:
                r[rd] = (s32(r[rt]) >> (r[rs] & 31)) & M
            elif fn == 8:
                return r[rs]
            elif fn == 9:
                t = r[rs]
                r[rd] = pc + 8
                return t
            elif fn in (32, 33):
                r[rd] = (r[rs] + r[rt]) & M
            elif fn in (34, 35):
                r[rd] = (r[rs] - r[rt]) & M
            elif fn == 36:
                r[rd] = r[rs] & r[rt]
            elif fn == 37:
                r[rd] = r[rs] | r[rt]
            elif fn == 38:
                r[rd] = r[rs] ^ r[rt]
            elif fn == 39:
                r[rd] = ~(r[rs] | r[rt]) & M
            elif fn == 42:
                r[rd] = int(s32(r[rs]) < s32(r[rt]))
            elif fn == 43:
                r[rd] = int(r[rs] < r[rt])
            elif fn == 24:
                p = s32(r[rs]) * s32(r[rt])
                self.lo, self.hi = p & M, (p >> 32) & M
            elif fn == 25:
                p = r[rs] * r[rt]
                self.lo, self.hi = p & M, (p >> 32) & M
            elif fn == 26:
                a, b = s32(r[rs]), s32(r[rt])
                if b:
                    q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
                    self.lo, self.hi = q & M, (a - q * b) & M
            elif fn == 27:
                if r[rt]:
                    self.lo, self.hi = r[rs] // r[rt], r[rs] % r[rt]
            elif fn == 16:
                r[rd] = self.hi
            elif fn == 18:
                r[rd] = self.lo
            else:
                raise Halt(f"unhandled special {fn} at {pc:#x}")
            return None
        if op == 1:
            cond = s32(r[rs]) < 0 if rt in (0, 16) else s32(r[rs]) >= 0
            if rt in (16, 17):
                r[31] = pc + 8
            return (pc + 4 + (simm << 2)) & M if cond else None
        if op in (2, 3):
            if op == 3:
                r[31] = pc + 8
            return ((pc + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
        if op in (4, 5, 6, 7):
            a, b = s32(r[rs]), s32(r[rt])
            cond = {4: a == b, 5: a != b, 6: a <= 0, 7: a > 0}[op]
            return (pc + 4 + (simm << 2)) & M if cond else None
        if op in (8, 9):
            r[rt] = (r[rs] + simm) & M
        elif op == 10:
            r[rt] = int(s32(r[rs]) < simm)
        elif op == 11:
            r[rt] = int(r[rs] < (simm & M))
        elif op == 12:
            r[rt] = r[rs] & imm
        elif op == 13:
            r[rt] = r[rs] | imm
        elif op == 14:
            r[rt] = r[rs] ^ imm
        elif op == 15:
            r[rt] = (imm << 16) & M
        elif op in (32, 33, 35, 36, 37):
            a = (r[rs] + simm) & M
            n = {32: 1, 33: 2, 35: 4, 36: 1, 37: 2}[op]
            self.pending = (rt, self.rd(a, n, signed=op in (32, 33)))
        elif op in (40, 41, 43):
            a = (r[rs] + simm) & M
            self.wr(a, {40: 1, 41: 2, 43: 4}[op], r[rt])
        else:
            raise Halt(f"unhandled opcode {op} at {pc:#x}")
        return None
