#!/usr/bin/env python3
"""libui (Android 17): GraphicBufferMapper only falls back to the HIDL gralloc mappers 3.0/2.x when android_get_device_api_level() <= 35.
On this device the API level seen by libui is higher (GSI), so SurfaceFlinger aborts with "gralloc-mapper is missing" although the vendor has mapper 2.1.
NOP the 'b.gt' after `cmp w0,#0x23` (arm64) / `cmp r0,#0x23; bgt` (thumb), in the constructor and in preloadHal.
usage: patch_libui.py IN OUT"""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read()); hits = []
if d[4] == 2:
    for i in range(0, len(d) - 8, 4):
        if struct.unpack_from('<I', d, i)[0] == 0x71008c1f and (struct.unpack_from('<I', d, i + 4)[0] & 0xff00001f) == 0x5400000c:  # cmp w0,#0x23 ; b.gt
            hits.append(i + 4)
    for a in hits: struct.pack_into('<I', d, a, 0xd503201f)
else:
    for i in range(0, len(d) - 4, 2):
        if d[i:i + 2] == b'\x23\x28' and d[i + 3] == 0xdc:   # cmp r0,#0x23 ; bgt <imm8>
            hits.append(i + 2)
    for a in hits: d[a:a + 2] = b'\x00\xbf'
assert len(hits) == 2, hits
# Gralloc2 (HIDL mapper 2.x) rejects descriptors whose usage has bit 13 (0x2000, the legacy GRALLOC_USAGE_EXTERNAL_DISP) with "buffer descriptor contains invalid usage bits 0x2000".
# The MediaTek OMX decoder asks for it, so ACodec's YV12 output buffers could not be allocated and YouTube showed a green screen / "problem while playing".
# arm64 only (the 32-bit library is not used by the apps that decode video): in the two validate functions the invalid-bits mask is built with
# `mov xN,#0x2400 ; ... movk xN,#0x28(8),lsl #16 ; movk xN,#0xffff,lsl #32`; drop bit 13 from it (0x2400 -> 0x0400).
if d[4] == 2:
    words = struct.unpack_from('<%dI' % (len(d) // 4), d, 0); fixed = []
    for i, w in enumerate(words):
        if w in (0xd2848009, 0xd284800a):                         # movz x9/x10,#0x2400
            rd = w & 31
            nxt = [words[j] for j in range(i + 1, min(i + 6, len(words)))]
            if any((n & 0xffe0001f) == (0xf2a00000 | rd) and ((n >> 5) & 0xffff) in (0x28, 0x828, 0xe28) for n in nxt):   # movk xRd,#0x28|0x828|0xe28,lsl #16
                struct.pack_into('<I', d, i * 4, 0xd2808000 | rd); fixed.append(i * 4)
    assert len(fixed) == 3, [hex(f) for f in fixed]
    print('usage mask fixed at', [hex(f) for f in fixed])
open(sys.argv[2], 'wb').write(d); print('patched', [hex(h) for h in hits])
