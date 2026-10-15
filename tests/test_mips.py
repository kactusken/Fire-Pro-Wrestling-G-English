"""The hook assembler and the CPU simulator used to test hooks offline."""
import struct
import unittest

from tests import TestCase

from mips_asm import assemble
from mipsim import CPU

BASE = 0x80100000


def run(source, regs=None, data=None, max_steps=10000):
    """Assemble source at BASE, run it until the `done` label, return the CPU."""
    code, symbols = assemble(source + "\ndone: nop", BASE)
    cpu = CPU()
    cpu.load(BASE, code)
    for addr, blob in (data or {}).items():
        cpu.load(addr, blob)
    for r, v in (regs or {}).items():
        cpu.r[r] = v
    cpu.stops = {symbols["done"]}
    cpu.run(BASE, max_steps)
    return cpu


V0, V1, A0, A1, T0 = 2, 3, 4, 5, 8


class AssemblerTest(TestCase):
    def test_known_encodings(self):
        # Words that build.py's code tweaks write into overlay 001.
        self.assertEqual(assemble("addiu v0, zero, 120", BASE)[0], struct.pack("<I", 0x24020078))
        self.assertEqual(assemble("addiu v1, zero, 120", BASE)[0], struct.pack("<I", 0x24030078))
        self.assertEqual(assemble("nop", BASE)[0], bytes(4))

    def test_labels_and_symbols(self):
        code, symbols = assemble("start: nop\nloop: j loop\nnop", BASE, {"X": 5})
        self.assertEqual(symbols["start"], BASE)
        self.assertEqual(symbols["loop"], BASE + 4)
        self.assertEqual(len(code), 12)


class SimulatorTest(TestCase):
    def test_arithmetic(self):
        cpu = run("addiu v0, zero, 40\naddiu v1, zero, 2\naddu v0, v0, v1")
        self.assertEqual(cpu.r[V0], 42)

    def test_loop_with_branch_delay_slot(self):
        # Sum 1..10. The addiu in the delay slot runs on every pass.
        cpu = run("""
                addiu t0, zero, 10
                addu  v0, zero, zero
        loop:   addu  v0, v0, t0
                bne   t0, zero, loop
                addiu t0, t0, -1
                j     done
                nop
        """)
        self.assertEqual(cpu.r[V0], 55)

    def test_load_delay_slot(self):
        # The instruction after a load still sees the register's old value.
        cpu = run("""
                lui   a0, 0x8010
                lw    v0, 0x100(a0)
                addu  v1, v0, zero
                addu  a1, v0, zero
        """, regs={V0: 7}, data={BASE + 0x100: struct.pack("<I", 99)})
        self.assertEqual(cpu.r[V1], 7)
        self.assertEqual(cpu.r[A1], 99)

    def test_memory_store(self):
        cpu = run("lui a0, 0x8010\naddiu v0, zero, 0x55\nsb v0, 0x200(a0)")
        self.assertEqual(cpu.mem[BASE + 0x200 - 0x80000000], 0x55)

    def test_zero_register_stays_zero(self):
        cpu = run("addiu zero, zero, 5")
        self.assertEqual(cpu.r[0], 0)


if __name__ == "__main__":
    unittest.main()
