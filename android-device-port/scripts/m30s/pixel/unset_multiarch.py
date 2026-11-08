#!/usr/bin/env python3
"""Set android:multiArch="false" in the binary AndroidManifest.xml of an arm64-only APK and re-sign it (platform test key).
WebViewGoogle (Pixel 9a, 64-bit only) declares multiArch, which PackageManager refuses on a device that also supports armeabi-v7a ("native libs don't support all the natively supported ABIs").
usage: unset_multiarch.py IN.apk OUT.apk KEYDIR [BUILD_TOOLS]"""
import os, struct, subprocess, sys, zipfile
src, dst, keys = sys.argv[1:4]; bt = sys.argv[4] if len(sys.argv) > 4 else os.path.expanduser('~/Library/Android/sdk/build-tools/36.1.0')
RID = 0x0101048e
zi = zipfile.ZipFile(src); m = bytearray(zi.read('AndroidManifest.xml'))
pos = 8; ids = None; n = 0
while pos < len(m):
    t, hs, sz = struct.unpack_from('<HHI', m, pos)
    if t == 0x0180: ids = struct.unpack_from('<%dI' % ((sz - hs) // 4), m, pos + hs)
    elif t == 0x0102:            # start element: header 16, ext: ns, name, attrStart(2), attrSize(2), attrCount(2), ...
        attr_start, attr_size, cnt = struct.unpack_from('<HHH', m, pos + 16 + 8)
        for i in range(cnt):
            a = pos + 16 + attr_start + i * attr_size; name = struct.unpack_from('<I', m, a + 4)[0]
            if name < len(ids) and ids[name] == RID:
                assert m[a + 15] == 0x12, 'not a boolean'; struct.pack_into('<I', m, a + 16, 0); n += 1
    pos += sz
assert n == 1, n
tmp = dst + '.tmp'
with zipfile.ZipFile(tmp, 'w') as zo:
    for i in zi.infolist():
        if i.filename.startswith('META-INF/'): continue
        zo.writestr(zipfile.ZipInfo(i.filename, i.date_time), bytes(m) if i.filename == 'AndroidManifest.xml' else zi.read(i), compress_type=i.compress_type)
subprocess.run([bt + '/zipalign', '-p', '-f', '4', tmp, dst + '.al'], check=True); os.remove(tmp)
subprocess.run([bt + '/apksigner', 'sign', '--key', keys + '/platform.pk8', '--cert', keys + '/platform.x509.pem', '--out', dst, dst + '.al'], check=True, capture_output=True)
os.remove(dst + '.al'); os.path.exists(dst + '.idsig') and os.remove(dst + '.idsig'); print('written', dst)
