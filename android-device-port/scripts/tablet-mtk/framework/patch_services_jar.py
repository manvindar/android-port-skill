#!/usr/bin/env python3
"""services.jar (Android 17 DP11.261002.005): HintManagerService assumes an AIDL IPower HAL exists.
`mPowerHal = injector.createIPower()` is null on this device (vendor has only the HIDL power HAL), `mSupportInfo` stays null and
the constructor dies on `mSupportInfo.headroom` (NPE) -> system_server restart loop.
Patch (bytecode, in the dex that holds HintManagerService; classes.dex is 3 dex files back to back):
  1. constructor: NOP the `if-eqz v7, :skip` so getSupportInfo() is always called
  2. getSupportInfo(): catch NullPointerException (was RemoteException) and, in the handler, `goto` the code that builds a default SupportInfo
     (all features off) instead of returning null
then fix the dex checksum + SHA-1 signature and rewrite the jar. Offsets are asserted.
usage: patch_services_jar.py IN.jar OUT.jar"""
import hashlib, re, struct, sys, zipfile, zlib
src, dst = sys.argv[1:3]
zin = zipfile.ZipFile(src); raw = bytearray(zin.read('classes.dex'))
heads = [m.start() for m in re.finditer(rb'dex\n041\x00', raw)]
# find the HintManagerService.<init>/getSupportInfo bytecode by its instruction pattern (so no hard-coded offsets)
# The method/field/string/type indices change with every GSI build, so the patterns wildcard them (re.DOTALL, '..' = one 16-bit index) and the patches reuse the matched indices.
def find1(pattern, what):
    ms = list(re.finditer(pattern, raw, re.DOTALL))
    assert len(ms) == 1, (what, len(ms))
    return ms[0]
# method names from the dex tables (offsets in a v041 container header are absolute), to tell look-alike call sites apart
def _uleb(o):
    v = sh = 0
    while True:
        x = raw[o]; o += 1; v |= (x & 0x7f) << sh; sh += 7
        if not x & 0x80: return v, o
def _str(base, i):
    o = struct.unpack_from('<I', raw, struct.unpack_from('<I', raw, base + 0x3c)[0] + 4 * i)[0]; _, o = _uleb(o); return raw[o:raw.index(b'\0', o)].decode('latin1')
def method_name(pos, idx):
    base = max(x for x in heads if x <= pos)
    c, _, n = struct.unpack_from('<HHI', raw, struct.unpack_from('<I', raw, base + 0x5c)[0] + 8 * idx)
    ty = struct.unpack_from('<I', raw, struct.unpack_from('<I', raw, base + 0x44)[0] + 4 * c)[0]
    return _str(base, ty) + '.' + _str(base, n)
def find_call(pattern, what, idx_at, wanted):
    ms = [m for m in re.finditer(pattern, raw, re.DOTALL) if method_name(m.start(), struct.unpack_from('<H', raw, m.start() + idx_at)[0]) == wanted]
    assert len(ms) == 1, (what, len(ms))
    return ms[0]
def pat(*parts):
    out = b''
    for part in parts:
        out += b'.{2}' if part is None else re.escape(bytes.fromhex(part))
    return out
# if-eqz v7,+0x10 ; invoke-virtual {v6} getSupportInfo ; move-result-object v7 ; iput-object v7,v6,mSupportInfo
mc = find1(pat('38071000', '6e10', None, '0600', '0c07', '5b67', None), 'ctor pattern'); c = mc.start()
# move-exception v6 ; const-string v0,"Could not contact PowerHAL!" ; invoke-static ; const/4 v6,0 ; return-object v6
mh = find1(pat('0d06', '1a00', None, '7120', None, '6000', '1206', '1106'), 'handler pattern'); h = mh.start(); HANDLER = mh.group(0)
base = max(x for x in heads if x <= h)
# the try/catch item right after the insns of getSupportInfo (4-byte aligned: 2 bytes of padding when the unit count is odd)
# the insns start is found through the code item's insns_size field, so a method that grew or shrank between GSI builds still works
tot = None
for k in range(20, 400):
    if struct.unpack_from('<I', raw, h - 2 * k - 4)[0] == k + len(HANDLER) // 2: tot = k + len(HANDLER) // 2; ins0 = h - 2 * k; hunit = k; break
assert tot, 'getSupportInfo code item'
insn_end = h + len(HANDLER)
tries = insn_end + (2 if tot % 2 else 0)
assert raw[tries:tries + 4] == b'\0\0\0\0' and raw[tries + 4:tries + 6] == b'\x11\x00', raw[tries:tries + 12].hex()
lst = tries + 8; assert raw[lst] == 1 and raw[lst + 1] == 1, raw[lst:lst + 6].hex()
tidx_off = lst + 2
# decode the current type_idx (uleb128) and look up RemoteException / NullPointerException in this dex's type table
def uleb(b, o):
    v = s = 0
    while True:
        x = b[o]; o += 1; v |= (x & 0x7f) << s; s += 7
        if not x & 0x80: return v, o
# dex 041 container: every offset in the header is absolute within classes.dex
type_size, type_off = struct.unpack_from('<II', raw, base + 0x40); str_ids = struct.unpack_from('<I', raw, base + 0x3c)[0]
def tname(t):
    sidx = struct.unpack_from('<I', raw, type_off + 4 * t)[0]
    o = struct.unpack_from('<I', raw, str_ids + 4 * sidx)[0]; _, o = uleb(raw, o)
    return bytes(raw[o:raw.index(b'\0', o)]).decode('latin1')
cur, nxt = uleb(raw, tidx_off)
assert tname(cur) == 'Landroid/os/RemoteException;', tname(cur)
npe = next(t for t in range(type_size) if tname(t) == 'Ljava/lang/NullPointerException;')
enc = bytearray(); v = npe
while True:
    b7 = v & 0x7f; v >>= 7
    enc.append(b7 | (0x80 if v else 0))
    if not v: break
assert len(enc) == nxt - tidx_off, (len(enc), nxt - tidx_off)
raw[tidx_off:nxt] = enc
# the verifier merges register types over the whole try range: v6 (`this`) must not be clobbered inside it, or the handler's jump to the
# default-SupportInfo code sees v6 as Object ("'this' argument ... not instance of HintManagerService"). Rewrite units 0xb..0x11 to use v1/v0:
#   iget-object v1,v6,mPowerHal ; invoke-interface {v1},IPower.getSupportInfo ; move-result-object v0 ; return-object v0
t = ins0 + 0xb * 2            # insns start + unit 0xb
# DP11.261002.005: ... 0c06 ; 1106 (return-object v6)    DP11.261016.003: ... 0c06 ; 28xx (goto the shared return-object v6)
assert raw[t:t + 2] == bytes.fromhex('5466') and raw[t + 4:t + 6] == bytes.fromhex('7210') and raw[t + 8:t + 12] == bytes.fromhex('0600' + '0c06') and raw[t + 12:t + 14] in (bytes.fromhex('1106'), bytes.fromhex('2850')) or raw[t + 12] == 0x28, raw[t:t + 14].hex()
raw[t:t + 14] = bytes.fromhex('5461') + raw[t + 2:t + 4] + bytes.fromhex('7210') + raw[t + 6:t + 8] + bytes.fromhex('0100' + '0c00' + '1100')
raw[c:c + 4] = b'\0\0\0\0'                                  # 1. nop the null check on mPowerHal
assert raw[ins0 + 0x12 * 2:ins0 + 0x12 * 2 + 2] == bytes.fromhex('2200'), 'default SupportInfo code (new-instance) is not at unit 0x12'
raw[h:h + 6] = bytes.fromhex('2900') + struct.pack('<h', 0x12 - hunit) + bytes.fromhex('0000')   # 2. goto/16 to the default-SupportInfo code at unit 0x12 ; nop (kills the orphaned const-string operand)
# 3. BiometricCameraManagerImpl.subscribeToCameraEvents(): CameraManager.registerAvailabilityCallback throws on this device (the camera service cannot
#    initialise its listener, Function not implemented) and BiometricService's handler thread takes system_server down. Make it a no-op.
k = find_call(pat('5420', None, '5422', None, '1201', '6e30', None, '2001', '0e00'), 'camera pattern', 12, 'Landroid/hardware/camera2/CameraManager;.registerAvailabilityCallback').start()
raw[k:k + 4] = bytes.fromhex('0e000000')                      # return-void ; nop (keeps the rest of the method valid)
# 4. ActivityTaskManagerService.LocalService.showSystemReadyErrorDialogsIfNeeded(): `Build.isBuildConsistent()` (Treble => VintfObject.verifyBuildAtBoot) is false
#    for a GSI over this Android 10 vendor (sepolicy 29.0, VNDK 29, kernel 4.9), which shows "There's an internal problem with your device".
#    Treat the build as consistent: const/4 v2,#1 ; nop x3 replaces `invoke-static {} isBuildConsistent ; move-result v2`.
bk = find_call(pat('7100', None, '0000', '0a02'), 'isBuildConsistent pattern', 2, 'Landroid/os/Build;.isBuildConsistent').start()
raw[bk:bk + 8] = bytes.fromhex('1212' + '000000000000')
touched = {base, max(x for x in heads if x <= k), max(x for x in heads if x <= bk)}
# fix headers: signature then checksum, of every dex that was edited (each dex's file_size is in its own header)
for b0 in touched:
    fs = struct.unpack_from('<I', raw, b0 + 0x20)[0]
    raw[b0 + 12:b0 + 32] = hashlib.sha1(bytes(raw[b0 + 32:b0 + fs])).digest()
    struct.pack_into('<I', raw, b0 + 8, zlib.adler32(bytes(raw[b0 + 12:b0 + fs])) & 0xffffffff)
zout = zipfile.ZipFile(dst, 'w')
for i in zin.infolist():
    data = bytes(raw) if i.filename == 'classes.dex' else zin.read(i.filename)
    zi = zipfile.ZipInfo(i.filename, i.date_time); zi.compress_type = i.compress_type; zi.external_attr = i.external_attr
    zout.writestr(zi, data)
zout.close(); print('patched dex at', hex(base), 'catch type', cur, '->', npe, '; wrote', dst)
