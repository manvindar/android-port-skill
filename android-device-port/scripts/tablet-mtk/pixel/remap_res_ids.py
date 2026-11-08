#!/usr/bin/env python3
"""Re-point framework resource references (@*android:...) in an APK to this device's numbering.

Unreleased ('staging') framework resources are numbered alphabetically, so an app built against another A17 build can
reference a neighbouring resource. IN_OUT pairs are old=new IDs, found by comparing resource names (see docs/PIXEL.md).
Patches TYPE_REFERENCE values in resources.arsc and in compiled XML: full Res_value (size=8, res0=0, dataType=1, data=id) and compact
table entries (flags 0x0108 = FLAG_COMPACT + reference, data=id).

usage: remap_res_ids.py IN.apk OUT.apk 0x01050148=0x01050149 ...      (unsigned output, keep entry compression: zipalign + sign afterwards)"""
import re, struct, sys, zipfile
src, dst = sys.argv[1:3]
pairs = {int(a, 16): int(b, 16) for a, b in (p.split('=') for p in sys.argv[3:])}
sigs = lambda i: (b'\x08\x00\x00\x01' + struct.pack('<I', i), b'\x08\x01' + struct.pack('<I', i))
zin = zipfile.ZipFile(src); n = 0
with zipfile.ZipFile(dst, 'w') as z:
    for info in zin.infolist():
        data = zin.read(info)
        if info.filename == 'resources.arsc' or info.filename.endswith('.xml'):
            for old, new in pairs.items():
                for so, sn in zip(sigs(old), sigs(new)):
                    c = data.count(so)
                    if c: data = data.replace(so, sn); n += c; print(f'{info.filename}: {hex(old)} -> {hex(new)} x{c}')
        zi = zipfile.ZipInfo(info.filename, info.date_time); zi.compress_type = info.compress_type; zi.external_attr = info.external_attr
        z.writestr(zi, data)
print(n, 'references remapped')
