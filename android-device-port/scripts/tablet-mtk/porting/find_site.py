#!/usr/bin/env python3
"""Finds where a patch site of an OLD build lives in a NEW build of the same binary (arm64 ELF): instruction windows around the old address are
compared with the new binary, immediates and branch targets masked, `bti` / `paciasp` / `autiasp` skipped (newer builds add them).
usage: find_site.py OLD_BINARY NEW_BINARY 0xADDR [0xADDR ...]
Prints the new address and both instructions; check them against the disassembly before using the address in a patch table."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sigmatch import stream, locate
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
old, new = open(sys.argv[1], 'rb').read(), open(sys.argv[2], 'rb').read()
os_, ns = stream(old, len(old) // 4 * 4), stream(new, len(new) // 4 * 4)
def show(d, a):
    i = next(md.disasm(d[a:a + 4], a)); return f'{i.mnemonic} {i.op_str}'
for a in sys.argv[3:]:
    a = int(a, 16); r, w = locate(old, new, a, 8, os_, ns)
    print(hex(a), show(old, a), '->', (hex(r) + ' ' + show(new, r)) if r else 'not found (look at the disassembly side by side: capstone, or objdump -d)')
