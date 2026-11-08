#!/usr/bin/env python3
"""libandroid_runtime.so (Android 17, arm64): MemoryBudgetManager.nativeRegisterPackageBudgetWatcher / nativeRegisterProcessBudgetWatcher return 0 when the kernel
cannot deliver memory budget events (no memcg/BPF support on 4.9), and Java then throws IllegalStateException("Failed to register package budget listener"):
Google Maps (and any app that registers an over-budget listener) crashes at start. Make both natives return a dummy non-zero handle; no event is ever delivered,
which is what these apps tolerate. The unregister native looks the handle up in a hash map and ignores unknown ones.
The two trampolines `mov x1,x2; mov w2,#1|2; b register` are found by pattern (newer builds put a `bti c` in front of each).
usage: patch_libandroid_runtime.py IN OUT"""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
W = struct.unpack_from('<%dI' % (len(d) // 4), d, 0)
def tramp(kind): return [i for i in range(len(W) - 3) if W[i] == 0xaa0203e1 and W[i + 1] == 0x52800002 | (kind << 5) and W[i + 2] >> 26 == 5]
t1, t2 = tramp(1), tramp(2)
pairs = [(a, b) for a in t1 for b in t2 if 0 < b - a <= 6 and W[a + 2] != 0 and ((W[a + 2] & 0x3ffffff) - (W[b + 2] & 0x3ffffff)) == (b - a)]   # both branch to the same register function
assert len(pairs) == 1, ('budget watcher trampolines not found or ambiguous', t1, t2)
for i in pairs[0]:
    struct.pack_into('<III', d, i * 4, 0xd2800020, 0xd65f03c0, 0xd503201f)                           # mov x0,#1 ; ret ; nop
open(sys.argv[2], 'wb').write(d); print('patched', [hex(i * 4) for i in pairs[0]])
