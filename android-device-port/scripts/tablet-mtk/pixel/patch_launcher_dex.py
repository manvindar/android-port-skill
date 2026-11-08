#!/usr/bin/env python3
"""Make an app APK survive framework flag enum constants that the device's framework no longer has (NoSuchFieldError).

Every `sget-object vX, Cls.MISSING` is re-pointed at another constant of the same enum that the app already references (flag values only gate
desktop-mode features, which this tablet does not use). Methods are not touched. Output is unsigned: run zipalign + apksigner afterwards.

usage: patch_launcher_dex.py IN.apk OUT.apk missing.txt     (missing.txt = output of check_dex_refs.py)
env: BUILD_TOOLS (default ~/Library/Android/sdk/build-tools/35.0.0)"""
import hashlib, os, re, struct, subprocess, sys, tempfile, zipfile, zlib

BT = os.environ.get('BUILD_TOOLS', os.path.expanduser('~/Library/Android/sdk/build-tools/35.0.0'))
src, dst, miss_file = sys.argv[1:4]
missing = set()
for l in open(miss_file):
    f = l.rstrip('\n').split('\t')
    if f[0] == 'field':
        m = re.match(r'(.+)\.([A-Za-z0-9_$]+):(L[^;]+;)$', f[1])
        if m and m.group(3).replace('/', '.')[1:-1] == m.group(1): missing.add((m.group(1), m.group(2)))     # enum constant: field type == owner class
print(len(missing), 'missing enum constants')

def fix_checksums(raw):
    fs = struct.unpack_from('<I', raw, 32)[0]
    raw[12:32] = hashlib.sha1(bytes(raw[32:fs])).digest()
    struct.pack_into('<I', raw, 8, zlib.adler32(bytes(raw[12:fs])) & 0xffffffff)

zin = zipfile.ZipFile(src); out = {}; patched = 0
for name in zin.namelist():
    data = zin.read(name)
    if re.fullmatch(r'classes\d*\.dex', name):
        with tempfile.NamedTemporaryFile(suffix='.dex') as t:
            t.write(data); t.flush()
            dump = subprocess.run([os.path.join(BT, 'dexdump'), '-d', t.name], capture_output=True, text=True, errors='replace', env=dict(os.environ, LC_ALL='C')).stdout
        refs = []        # (file offset, cls, name, idx)
        for l in dump.splitlines():
            m = re.match(r'([0-9a-f]+): ([0-9a-f]{4}) ([0-9a-f]{4}).*?\|[0-9a-f]+: sget-object v\d+, (L[^;]+;)\.([A-Za-z0-9_$]+):\4 // field@([0-9a-f]+)', l)
            if m: refs.append((int(m.group(1), 16), m.group(4)[1:-1].replace('/', '.'), m.group(5), int(m.group(6), 16)))
        good = {}
        for off, c, n, idx in refs:
            if (c, n) not in missing: good.setdefault(c, (n, idx))
        raw = bytearray(data)
        for off, c, n, idx in refs:
            if (c, n) in missing:
                if c not in good: sys.exit(f'{name}: no existing constant of {c} to point {n} at')
                struct.pack_into('<H', raw, off + 2, good[c][1]); patched += 1
                print(f'{name} @{off:#x}: {c}.{n} -> {good[c][0]}')
        fix_checksums(raw); data = bytes(raw)
    out[name] = (zin.getinfo(name), data)
with zipfile.ZipFile(dst, 'w') as z:
    for name, (info, data) in out.items():
        zi = zipfile.ZipInfo(name, info.date_time); zi.compress_type = info.compress_type; zi.external_attr = info.external_attr
        z.writestr(zi, data)
print(patched, 'sites patched ->', dst)
