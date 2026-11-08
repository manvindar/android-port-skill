#!/usr/bin/env python3
"""patch_libui_gate.py IN OUT: libui (Android 17, arm64) falls back to the HIDL gralloc mappers 2.x/3.0 only when android_get_device_api_level() <= 35; with an Android 11 vendor (mapper 2.1) SurfaceFlinger aborts
("gralloc-mapper is missing"). NOP every `cmp w0,#0x23 ; b.gt` (the Samsung build has three sites, the AOSP build two). Same idea as tb-x606v-android17/tools/libc/patch_libui.py without its count assertion and without the MediaTek usage-bit fix."""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read()); hits = []
if d[4] == 2:
    for i in range(0, len(d) - 8, 4):
        if struct.unpack_from('<I', d, i)[0] == 0x71008c1f and (struct.unpack_from('<I', d, i + 4)[0] & 0xff00001f) == 0x5400000c: hits.append(i + 4)
    for a in hits: struct.pack_into('<I', d, a, 0xd503201f)
else:                                                                  # 32-bit (thumb): cmp r0,#0x23 ; bgt
    for i in range(0, len(d) - 4, 2):
        if d[i:i + 2] == b'\x23\x28' and d[i + 3] == 0xdc: hits.append(i + 2)
    for a in hits: d[a:a + 2] = b'\x00\xbf'
assert len(hits) >= 2 or (d[4] == 1 and hits), hits
open(sys.argv[2], 'wb').write(d); print('patched', [hex(h) for h in hits])
