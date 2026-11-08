#!/usr/bin/env python3
"""libmeminfo (Android 17, arm64): BpfMapRO<unsigned long,unsigned long>::abortOnMismatch() abort()s when a pinned bpf map is missing.
system_server calls it via Debug.getGpuTotalUsageKb -> ReadProcessGpuUsageKb (the gpuMem bpf program cannot load on kernel 4.9), killing system_server
every ~75 s. Make the function return at its entry (located by its bpf() call, so it works on every GSI build).  usage: patch_libmeminfo.py IN OUT"""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
# found by its bpf(2) call: mov w0,#280 (__NR_bpf) ; mov w1,#15 (BPF_OBJ_GET_INFO_BY_FD) ; ... mov w3,#168 ; the function start is the `sub sp,sp,#imm` before it
W = struct.unpack_from('<%dI' % (len(d) // 4), d, 0)
hits = [i * 4 for i in range(len(W) - 12) if W[i] == 0x52802300 and W[i + 1] == 0x528001e1 and 0x52801503 in W[i:i + 4]]
assert len(hits) == 1, ('abortOnMismatch not found or ambiguous', hits)
j = hits[0]
while j > hits[0] - 0x200 and (W[j // 4] & 0xffc003ff) != 0xd10003ff: j -= 4
assert (W[j // 4] & 0xffc003ff) == 0xd10003ff, 'function start'
while W[j // 4 - 1] in (0xd503233f, 0xd503245f, 0xd503249f, 0xd50324df): j -= 4      # paciasp / bti c|j|jc: patch before them
struct.pack_into('<I', d, j, 0xd65f03c0)
open(sys.argv[2], 'wb').write(d); print('patched', hex(j), '->', sys.argv[2])
