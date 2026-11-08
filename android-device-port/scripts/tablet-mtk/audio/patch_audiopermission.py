#!/usr/bin/env python3
"""Android 16 audioserver, library libaudiopermission.so: NativePermissionController::populatePermissionState(PermissionEnum, vector<int>) returns
EX_ILLEGAL_ARGUMENT (-3) for any enum value >= 16. Android 17's system_server sends enum values up to the A17 count and treats the exception as fatal:
the AudioService permission listener runs on the "audioserver_lifecycle" thread, an uncaught exception there kills system_server (boot loop with the boot animation
on screen). Return success instead (`mov w0,#-3` -> `mov w0,wzr`) for the out-of-range values. offset 0x180fc is specific to the Android 16 build used here.
usage: patch_audiopermission.py IN OUT"""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
a = 0x180fc
assert struct.unpack_from('<I', d, a)[0] == 0x12800040, 'expected mov w0,#-3 at 0x180fc'
struct.pack_into('<I', d, a, 0x2a1f03e0)
open(sys.argv[2], 'wb').write(d); print('patched', hex(a))
