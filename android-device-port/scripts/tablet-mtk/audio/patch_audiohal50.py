#!/usr/bin/env python3
"""Android 16's libaudiohal@5.0.so inside Android 17: DeviceHalHidl::openOutputStream crashes (length_error building the HIDL source metadata
vector: the framework-side DeviceHalInterface/track-metadata ABI changed between 16 and 17). Make it fail with -EINVAL instead:
`mov w0,#-22 ; ret` at the function entry (0x14024 in the A16 build, asserted). AudioFlinger then simply has no output.
usage: patch_audiohal50.py IN OUT"""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
assert struct.unpack_from('<I', d, 0x14024)[0] == 0xd106c3ff, 'unexpected libaudiohal@5.0 build'
struct.pack_into('<II', d, 0x14024, 0x128002a0, 0xd65f03c0)
open(sys.argv[2], 'wb').write(d); print('patched ->', sys.argv[2])
