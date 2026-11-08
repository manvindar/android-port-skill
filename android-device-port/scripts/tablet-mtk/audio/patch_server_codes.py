#!/usr/bin/env python3
"""Android 16 audioserver, library audiopolicy-aidl-cpp.so: BnAudioPolicyService::onTransact is a jump table indexed by transaction code - 1.
system_server's Java proxy (framework.jar, boot classpath, so not patched) still sends A17's code 115 for getPermissionController(); in A16 that number is
getMmapPolicyForDevice, so the native audio permission controller was never handed to AudioFlinger and every app AudioTrack failed with
"NPC::validatedUidPackagePair: controller never populated by system_server" (no sound). Point table entry 115 at the getPermissionController handler (entry 113).
(The native clients no longer use 115 for getMmapPolicyForDevice: fix_aidl_codes.py sends it as unsupported, code 200.)
usage: patch_server_codes.py IN OUT"""
import struct, sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
d = bytearray(open(sys.argv[1], 'rb').read())

def find_ontransact():
    shoff, = struct.unpack_from('<Q', d, 0x28); sz, n, si = struct.unpack_from('<HHH', d, 0x3a)
    secs = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * sz) for i in range(n)]
    for s in secs:
        if s[1] == 11:
            strs = secs[s[6]]
            for k in range(s[5] // 24):
                nm, info, oth, shn, val, size = struct.unpack_from('<IBBHQQ', d, s[4] + k * 24)
                e = d.index(b'\0', strs[4] + nm); name = d[strs[4] + nm:e].decode()
                if name.startswith('_ZN7android5media20BnAudioPolicyService10onTransact'): return val, size

fn, size = find_ontransact()            # vaddr == file offset in the first segments of these libraries
ins = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(bytes(d[fn:fn + 200]), fn)); table = None
for k, x in enumerate(ins):
    if x.mnemonic == 'ldrh' and 'x8, lsl #1' in x.op_str:
        reg = x.op_str.split('[')[1].split(',')[0]
        a = next(y for y in reversed(ins[:k]) if y.mnemonic == 'adr' and y.op_str.startswith(reg + ','))
        table = int(a.op_str.split('#')[1], 16); break      # capstone prints the absolute target of adr
assert table, 'jump table not found'
e113 = struct.unpack_from('<H', d, table + 2 * 112)[0]; e115 = struct.unpack_from('<H', d, table + 2 * 114)[0]
print('table', hex(table), 'entry113', hex(e113), 'entry115', hex(e115))
struct.pack_into('<H', d, table + 2 * 114, e113)
open(sys.argv[2], 'wb').write(d)
