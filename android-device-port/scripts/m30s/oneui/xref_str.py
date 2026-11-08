#!/usr/bin/env python3
"""xref_str.py ELF 'string' [context=14]: where does an aarch64 binary load a string (adrp+add), with the disassembly around each reference. Needs capstone (the tablet repo's work/venv has it).
Used to find the kernel-version gates in netbpfload and similar checks so a patch can be located by the string instead of by a per-build offset."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
f, needle = sys.argv[1], sys.argv[2].encode(); ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 14
d = open(f, 'rb').read()
phoff, = struct.unpack_from('<Q', d, 0x20); phentsize, phnum = struct.unpack_from('<HH', d, 0x36)
loads = [struct.unpack_from('<IIQQQQQQ', d, phoff + i * phentsize) for i in range(phnum)]
loads = [(p[2], p[3], p[5], p[1]) for p in loads if p[0] == 1]    # (offset, vaddr, filesz, flags)
def off2va(o): return next(v + (o - fo) for fo, v, sz, fl in loads if fo <= o < fo + sz)
def va2off(v): return next(fo + (v - va) for fo, va, sz, fl in loads if va <= v < va + sz)
text = [(fo, va, sz) for fo, va, sz, fl in loads if fl & 1]
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
pos = 0
while (i := d.find(needle, pos)) >= 0:
    pos = i + 1
    try: sva = off2va(i)
    except StopIteration: continue
    print(f'string at file {i:#x} va {sva:#x}: {d[i:i + 80].split(chr(0).encode())[0].decode(errors="replace")}')
    for fo, va, sz in text:
        ins = list(md.disasm(d[fo:fo + sz], va))
        for k in range(len(ins) - 1):
            a, b = ins[k], ins[k + 1]
            if a.mnemonic == 'adrp' and b.mnemonic == 'add':
                ra, imm = a.op_str.split(', ')
                if b.op_str.startswith(ra + ', ' + ra + ', #') or b.op_str.split(', ')[1] == ra:
                    tgt = int(imm.lstrip('#'), 0) + int(b.op_str.split('#')[-1], 0)
                    if tgt == sva:
                        print(f'  xref at {a.address:#x}')
                        for x in ins[max(0, k - ctx):k + 6]: print(f'    {x.address:#x}: {x.mnemonic} {x.op_str}' + ('   <==' if x.address == a.address else ''))
