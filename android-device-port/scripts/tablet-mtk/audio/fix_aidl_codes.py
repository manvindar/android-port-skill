#!/usr/bin/env python3
"""A17 clients talking to the Android 16 audioserver: the AIDL transaction numbers of a few interfaces differ between the two releases
(IAudioPolicyService: volume-group methods reordered and methods inserted; IAudioTrack and IMmapStream: methods inserted).
Rewrite the `mov w1,#code` that every generated BpXxx::method uses before transact() in the A17 lib so it sends the A16 number.
Methods that only exist in A17 get code 200 (the A16 server answers UNKNOWN_TRANSACTION).
usage: fix_aidl_codes.py LIB17 LIB16 OUT CLASS[,CLASS...]   (e.g. audiopolicy-aidl-cpp.so, BpAudioPolicyService)"""
import re, struct, sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

def elf_syms(d):
    shoff, = struct.unpack_from('<Q', d, 0x28); sz, n, si = struct.unpack_from('<HHH', d, 0x3a)
    secs = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * sz) for i in range(n)]
    out = {}
    for s in secs:
        if s[1] == 11:
            strs = secs[s[6]]
            for k in range(s[5] // 24):
                nm, info, oth, shn, val, size = struct.unpack_from('<IBBHQQ', d, s[4] + k * 24)
                e = d.index(b'\0', strs[4] + nm); out[d[strs[4] + nm:e].decode()] = (val, size)
    return out

def va2off(d, va):
    phoff, = struct.unpack_from('<Q', d, 0x20); phsz, phn = struct.unpack_from('<HH', d, 0x36)
    for i in range(phn):
        t, fl, off, v, p, fs, ms, al = struct.unpack_from('<IIQQQQQQ', d, phoff + i * phsz)
        if t == 1 and v <= va < v + fs: return va - v + off

def transact_movs(d, cls):
    """{method: (file offset of the mov w1,#code, code)}"""
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM); res = {}
    for name, (val, size) in elf_syms(d).items():
        m = re.match(r'_ZN7android5media\d+' + cls + r'(\d+)([A-Za-z0-9]+)E', name)
        if not m or not size or not val: continue
        meth = m.group(2)[:int(m.group(1))] if False else None
        m2 = re.match(r'_ZN7android5media\d+' + cls + r'(\d+)(.+)', name)
        ln = int(m2.group(1)); meth = m2.group(2)[:ln]
        o = va2off(d, val); last = None
        for x in md.disasm(d[o:o + size], val):
            if x.mnemonic == 'mov' and x.op_str.startswith('w1, #'):
                last = (va2off(d, x.address), int(x.op_str.split('#')[1], 0))
            if x.mnemonic == 'blr' and last: res[meth] = last; break
    return res

# getMmapPolicyForDevice's A16 number (115) is taken over by patch_server_codes.py for getPermissionController: report it as unsupported (200)
OVERRIDE = {'getMmapPolicyForDevice'}
lib17, lib16, out, classes = sys.argv[1:5]
d17 = bytearray(open(lib17, 'rb').read()); d16 = open(lib16, 'rb').read()
for cls in classes.split(','):
    a = transact_movs(bytes(d17), cls); b = transact_movs(d16, cls); n = 0
    for meth, (off, code17) in a.items():
        code16 = 200 if meth in OVERRIDE else (b[meth][1] if meth in b else 200)
        if code16 != code17:
            struct.pack_into('<I', d17, off, 0x52800001 | (code16 << 5)); n += 1
    print(cls, len(a), 'methods,', n, 'renumbered,', [m for m in a if m not in b], 'only in A17')
open(out, 'wb').write(d17)
