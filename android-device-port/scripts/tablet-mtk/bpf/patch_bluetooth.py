#!/usr/bin/env python3
"""com.android.bt libbluetooth_jni.so (Android 17): the vendor controller answers READ_DEFAULT_ERRONEOUS_DATA_REPORTING (0x0c5a) with
UNKNOWN_HCI_COMMAND as a Command Status; HciLayer::impl::on_hci_event then log::fatal()s "was not expecting status event" (two template instances).
Retarget the two `tbz w20,#0,<fatal block>` to the normal exit: an event that does not match the queued command is ignored, a matching one is handled as before (an unconditional `b` skipped the handling of every event). Bind-mount the result over the apex lib64 copy.
usage: patch_bluetooth.py IN OUT"""
import hashlib, struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
# per build: ((tbz site, its fatal-block target, normal exit) x2, (SSP tbz site, its fatal target)); found by matching instruction windows between the builds (docs/PORTING.md)
SITES = {
    'old': (((0xc24528, 0xc25738, 0xc24554), (0xc248f0, 0xc25770, 0xc249ac)), (0xabaf10, 0xabafec)),                  # DP11.261002.005
    'new': (((0xc49bbc, 0xc4adb4, 0xc49be8), (0xc49f7c, 0xc4adec, 0xc4a034)), (0xae047c, 0xae0558)),                  # DP11.261016.003
}
sha = hashlib.sha256(d).hexdigest()[:16]
which = {'cc8d7346173bfc73': 'old', 'e0ae3969c6dc2d60': 'new'}.get(sha)
if not which: sys.exit(f'libbluetooth_jni.so: unknown build {sha}; the patch sites have to be ported (docs/PORTING.md)')
pairs, (ssp, ssp_t) = SITES[which]
for a, t, x in pairs:
    o = struct.unpack_from('<I', d, a)[0]
    assert (o & 0xfff80000) == 0x36000000 and (o & 0x1f) == 20 and a + ((o >> 5) & 0x3fff) * 4 == t, hex(o)
    struct.pack_into('<I', d, a, (o & ~(0x3fff << 5)) | ((((x - a) >> 2) & 0x3fff) << 5))   # same tbz, new target
# btm_sec_dev_reset: `tbz w0,#0,<fatal "only controllers with SSP is supported">` after Controller::SupportsSimplePairing(); the check fails
# with the features read through the ignored status, so accept it (the chip is BT 5.0 and does support SSP).
assert struct.unpack_from('<I', d, ssp)[0] == 0x36000000 | (((ssp_t - ssp) >> 2) << 5) | 0
struct.pack_into('<I', d, ssp, 0xd503201f)
open(sys.argv[2], 'wb').write(d); print('patched ->', sys.argv[2])
