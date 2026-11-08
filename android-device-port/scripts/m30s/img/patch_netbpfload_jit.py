#!/usr/bin/env python3
"""M30s: the stock Samsung kernel has CONFIG_BPF_JIT off, and netbpfload (DP11.261016.003, sha256 ca1b12368362d4f1...) fails every program load with
"Kernel eBPF JIT failure for ..." when bpf_prog_info.jited_prog_len is 0. NOP the `b.ge` to that error path (0xc714: cbnz jited_len ok ; ldr w8 ; cmp w8,#0xe10 ; b.ge fail).
Programs then run in the eBPF interpreter. usage: patch_netbpfload_jit.py IN(netbpfload.a17) OUT"""
import hashlib, struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
A = 0xc714
o = struct.unpack_from('<I', d, A)[0]
assert o & 0xff00001f == 0x5400000a, hex(o)          # b.ge
assert struct.unpack_from('<I', d, A - 4)[0] == 0x7138411f, hex(struct.unpack_from('<I', d, A - 4)[0])    # cmp w8,#0xe10 precedes it
struct.pack_into('<I', d, A, 0xd503201f)
open(sys.argv[2], 'wb').write(d); print('patched', sys.argv[2])
