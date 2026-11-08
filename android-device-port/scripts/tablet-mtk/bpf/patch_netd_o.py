#!/usr/bin/env python3
"""Make the tethering apex's netd.o loadable on kernel 4.9: LRU_HASH(9)/LRU_PERCPU_HASH(10) maps become HASH(1)/PERCPU_HASH(5).
Also relaxes the loader-version range of the 4.9 program variants.
The type lives in two places: the BTF map definition (shared int[9] array) and the loader's .android_maps entries (180 bytes each, type first).
Newer builds (DP11.261016.003) also compile the traffic counters with atomic fetch-add (BPF_STX | BPF_ATOMIC, imm = BPF_ADD | BPF_FETCH = 1); kernel 4.9 only has
plain XADD (imm = 0) and rejects the program with "BPF_STX uses reserved fields". Where the fetched old value is dead (the pattern is `neg r ; atomic r ; neg r ; atomic r ; mov r0,0 ; ja`), imm becomes 0.
usage: patch_netd_o.py IN OUT"""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
shoff = struct.unpack_from('<Q', d, 0x28)[0]; shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x3A)
sh = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * shentsize) for i in range(shnum)]
st = sh[shstrndx]; names = d[st[4]:st[4] + st[5]]
S = {names[s[0]:names.index(b'\0', s[0])].decode(): s for s in sh}
NEW = {9: 1, 10: 5}
am = S['.android_maps']
for k in range(0, am[5], 180):
    t = struct.unpack_from('<I', d, am[4] + k)[0]
    if t in NEW: struct.pack_into('<I', d, am[4] + k, NEW[t]); print('android_maps entry', k // 180, t, '->', NEW[t])
# The kernel-4.9 program variants ("..$4_9_t") are only valid for bpfloader versions < 0xdac (pre-U); allow them on this loader.
pg = S['.android_progs']
for k in range(0, pg[5], 180):
    mn, mx, lmin, lmax = struct.unpack_from('<IIxxxxIII', d, pg[4] + k + 0x10 - 0) if False else (struct.unpack_from('<I', d, pg[4] + k + 0x10)[0], struct.unpack_from('<I', d, pg[4] + k + 0x14)[0], struct.unpack_from('<I', d, pg[4] + k + 0x1c)[0], struct.unpack_from('<I', d, pg[4] + k + 0x20)[0])
    if mn == 0x04090000 and lmax < 0x10000:
        struct.pack_into('<I', d, pg[4] + k + 0x20, 0x10000); print('android_progs entry', k // 180, 'loader max', hex(lmax), '-> 0x10000')
# atomic fetch-add -> xadd
fixed = 0
for name, sec in S.items():
    if sec[1] != 1 or not sec[2] & 4 or sec[5] % 8: continue            # SHT_PROGBITS + SHF_EXECINSTR
    ins = lambda i: struct.unpack_from('<BBhi', d, sec[4] + i * 8)
    for i in range(sec[5] // 8):
        op, regs, off, imm = ins(i)
        if op in (0xc3, 0xdb) and imm == 1:
            # the old value lands in the src register: it must be dead. Accepted shape: this is the 2nd atomic of the pair and `mov r0,0 ; ja` follows, or the 1st with `neg ; atomic ; mov r0,0 ; ja` after it
            tail = [ins(i + k) for k in (1, 2, 3, 4)]
            ok = (tail[0][0] == 0xb7 and tail[0][1] & 15 == 0 and tail[0][3] == 0 and tail[1][0] == 0x05) or \
                 (tail[0][0] == 0x87 and tail[1][0] in (0xc3, 0xdb) and tail[2][0] == 0xb7 and tail[2][1] & 15 == 0 and tail[3][0] == 0x05)
            assert ok, f'{name}: atomic fetch at insn {i} whose result may be used'
            struct.pack_into('<i', d, sec[4] + i * 8 + 4, 0); fixed += 1
print('atomic fetch-add -> xadd:', fixed)
open(sys.argv[2], 'wb').write(d)
