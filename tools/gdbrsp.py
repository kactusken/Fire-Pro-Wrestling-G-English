#!/usr/bin/env python3
"""Minimal GDB remote-protocol client for DuckStation's GDB server.

DuckStation listens on 127.0.0.1 only, so from WSL run it with the Windows
Python (python.exe tools\\gdbrsp.py ...). No dependencies.

  gdbrsp.py peek <addr> [len]          hex dump of RAM
  gdbrsp.py regs                       general registers + pc
  gdbrsp.py break <addr> [timeout]     run until pc == addr, print regs, keep paused
  gdbrsp.py cont                       resume (detach)

The emulator is paused while a command talks to it; every command except
"break" detaches at the end so the game keeps running.
"""
import socket
import struct
import sys

REGS = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
        "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
        "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
        "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
        "sr", "lo", "hi", "bad", "cause", "pc"]


class Gdb:
    def __init__(self, host="127.0.0.1", port=2345, timeout=5):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.buf = b""
        self.cmd("?")  # the server may send a stop notification first; sync on it

    def _read_packet(self, timeout=5):
        self.s.settimeout(timeout)
        while True:
            i = self.buf.find(b"$")
            j = self.buf.find(b"#", i)
            if i >= 0 and j >= 0 and len(self.buf) >= j + 3:
                data = self.buf[i + 1:j]
                self.buf = self.buf[j + 3:]
                self.s.sendall(b"+")
                return data.decode("latin-1")
            chunk = self.s.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed")
            self.buf += chunk

    def cmd(self, body, timeout=5, reply=True):
        pkt = body.encode("latin-1")
        csum = sum(pkt) & 0xFF
        self.s.sendall(b"$" + pkt + b"#%02x" % csum)
        return self._read_packet(timeout) if reply else None

    def read(self, addr, n):
        out = b""
        while n:
            k = min(n, 0x400)
            r = self.cmd(f"m{addr:x},{k:x}")
            if r.startswith("E"):
                raise OSError(f"read {addr:#x}: {r}")
            out += bytes.fromhex(r)
            addr += k
            n -= k
        return out

    def write(self, addr, data):
        r = self.cmd(f"M{addr:x},{len(data):x}:{data.hex()}")
        if r != "OK":
            raise OSError(f"write {addr:#x}: {r}")

    def regs(self):
        r = self.cmd("g")
        if len(r) < 8 * 32:
            raise OSError(f"g: {r[:40]!r}")
        # unavailable registers come back as "xxxxxxxx"
        vals = [struct.unpack("<I", bytes.fromhex(r[i:i + 8].replace("x", "0")))[0]
                for i in range(0, len(r), 8)]
        return dict(zip(REGS, vals))

    def run_to(self, addr, timeout=60):
        r = self.cmd(f"Z0,{addr:x},4")
        if r != "OK":
            raise OSError(f"breakpoint {addr:#x}: {r!r}")
        try:
            return self.cont(timeout)
        finally:
            self.cmd(f"z0,{addr:x},4")

    def cont(self, timeout=60):
        """Resume and wait for the stop reply (S../T..); skip anything else."""
        r = self.cmd("c", timeout=timeout)
        while r[:1] not in ("S", "T"):
            r = self._read_packet(timeout)
        return r

    def detach(self):
        """Resume the emulator and disconnect (DuckStation stays paused on "D" alone)."""
        try:
            self.cmd("c", reply=False)
            self.cmd("D", timeout=2)
        except Exception:
            pass
        self.s.close()


def show_regs(r):
    names = list(r)
    for i in range(0, len(names), 6):
        print("  ".join(f"{n:>5}={r[n]:08x}" for n in names[i:i + 6]))


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    g = Gdb()
    op = argv[0]
    try:
        if op == "peek":
            addr = int(argv[1], 16)
            n = int(argv[2], 0) if len(argv) > 2 else 0x40
            data = g.read(addr, n)
            for i in range(0, len(data), 16):
                print(f"{addr + i:08x}: {data[i:i + 16].hex(' ')}")
        elif op == "regs":
            show_regs(g.regs())
        elif op == "break":
            addr = int(argv[1], 16)
            t = float(argv[2]) if len(argv) > 2 else 60
            print("stop:", g.run_to(addr, t))
            show_regs(g.regs())
            return  # stay paused: the next command inspects this state
        elif op == "cont":
            pass
        else:
            print(__doc__)
    finally:
        if op != "break":
            g.detach()


if __name__ == "__main__":
    main(sys.argv[1:])
