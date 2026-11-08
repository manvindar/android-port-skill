#!/usr/bin/env python3
"""libbinder (Android 17, arm64): IBinder::addFrozenStateChangeCallback needs the binder-freeze-notification ioctl of a 6.x kernel and returns -38
(INVALID_OPERATION) on kernel 4.9. CameraService::addListener, SensorService, AudioFlinger::registerClient ... all treat that as fatal
("Failed to register a camera service listener", "linkToDeath returned -38"), which crashed system_server. Make it succeed without doing anything
(`mov w0,wzr ; ret` at the function entry, found through the exported symbol). usage: patch_libbinder.py IN OUT"""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
def dynsym(d):
    shoff = struct.unpack_from('<Q', d, 0x28)[0]; ent, num = struct.unpack_from('<HH', d, 0x3a)
    secs = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * ent) for i in range(num)]
    for s in secs:
        if s[1] == 11:
            st = secs[s[6]]
            for k in range(s[5] // 24):
                nm, info, oth, shn, val, sz = struct.unpack_from('<IBBHQQ', d, s[4] + k * 24)
                if val and (info & 15) == 2: yield val, d[st[4] + nm:d.index(b'\0', st[4] + nm)].decode('latin1')
hits = [v for v, n in dynsym(d) if n.startswith('_ZN7android7IBinder28addFrozenStateChangeCallback')]
assert len(hits) == 1, ('addFrozenStateChangeCallback not found or ambiguous', hits)
a = hits[0]
first = struct.unpack_from('<I', d, a)[0]
assert first == 0xa9be7bfd or first == 0xd503233f, 'unexpected libbinder entry %#x' % first      # stp x29,x30,[sp,#-0x20]! | paciasp
struct.pack_into('<II', d, a, 0x2a1f03e0, 0xd65f03c0)
open(sys.argv[2], 'wb').write(d); print('patched', hex(a), '->', sys.argv[2])
