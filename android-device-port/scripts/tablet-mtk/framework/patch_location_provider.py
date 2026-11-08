#!/usr/bin/env python3
"""services.jar: let the Google network location provider (Play services) bind on this GSI.

Play services' manifest does not request android.permission.INSTALL_LOCATION_PROVIDER, but ProxyLocationProvider hands that permission to
CurrentUserServiceSupplier.createFromConfig() as `servicePermission`, which disqualifies every service whose uid does not hold it
("NetworkLocationService disqualified due to not holding android.permission.INSTALL_LOCATION_PROVIDER", dumpsys location: network provider
enabled=false, target service=null). The call sites (the two ProxyLocationProvider constructors) are patched to pass null instead:
  const/4 v7, 0 ; const-string/jumbo v8, "android.permission.INSTALL_LOCATION_PROVIDER"   ->   ... ; const/4 v8, 0 ; nop ; nop
Effect: any app that declares a network/fused location provider service named in the system config can serve as provider (the config still
names the allowed package; on this GSI that is whichever package declares the service). Acceptable on a personal device, not on a hardened one.
The jar holds a dex container (three dex files sharing one string table), so offsets are container-relative.
usage: patch_location_provider.py IN.jar OUT.jar"""
import hashlib, re, struct, sys, zipfile, zlib
src, dst = sys.argv[1:3]
zin = zipfile.ZipFile(src); raw = bytearray(zin.read('classes.dex'))
heads = [m.start() for m in re.finditer(rb'dex\n0\d\d\x00', raw)]
def uleb(b, o):
    v = s = 0
    while True:
        x = b[o]; o += 1; v |= (x & 0x7f) << s; s += 7
        if not x & 0x80: return v, o
n, off = struct.unpack_from('<II', raw, 56)
want = b'android.permission.INSTALL_LOCATION_PROVIDER'
idx = None
for i in range(n):
    so = struct.unpack_from('<I', raw, off + 4 * i)[0]; ln, p = uleb(raw, so)
    if raw[p:p + ln] == want: idx = i; break
assert idx is not None, 'string not found'
pat = b'\x12\x07\x1b\x08' + struct.pack('<I', idx)
sites = [m.start() for m in re.finditer(re.escape(pat), bytes(raw))]
if not sites:
    done = b'\x12\x07\x12\x08\x00\x00\x00\x00'
    assert raw.find(done) > 0, 'neither original nor patched pattern found'
    print('already patched'); sites = []
assert len(sites) in (0, 2), f'expected the two ProxyLocationProvider constructors, found {len(sites)}'
touched = set()
for k in sites:
    raw[k + 2:k + 8] = bytes.fromhex('1208' + '00000000')       # const/4 v8,#0 ; nop ; nop  (6 bytes -> 6 bytes)
    touched.add(max(h for h in heads if h <= k))
for b0 in touched:
    fs = struct.unpack_from('<I', raw, b0 + 0x20)[0]
    raw[b0 + 12:b0 + 32] = hashlib.sha1(bytes(raw[b0 + 32:b0 + fs])).digest()
    struct.pack_into('<I', raw, b0 + 8, zlib.adler32(bytes(raw[b0 + 12:b0 + fs])) & 0xffffffff)
zout = zipfile.ZipFile(dst, 'w')
for i in zin.infolist():
    data = bytes(raw) if i.filename == 'classes.dex' else zin.read(i.filename)
    zi = zipfile.ZipInfo(i.filename, i.date_time); zi.compress_type = i.compress_type; zi.external_attr = i.external_attr
    zout.writestr(zi, data)
zout.close(); print('patched', len(sites), 'sites; wrote', dst)
