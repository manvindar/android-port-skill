#!/usr/bin/env python3
"""Collect Android 16's audioserver and the closure of the shared libraries it needs (plus the audio policy plugins and the HAL factory) from an Android 16 GSI.
usage: a16_closure.py DONOR_IMG OUTDIR [E2FSPROGS_DIR]   -> OUTDIR/audioserver, OUTDIR/lib64/*.so  (raw ext4 image, read with debugfs, nothing is mounted)"""
import os, shutil, struct, subprocess, sys
IMG, OUT = sys.argv[1:3]
DEBUGFS = os.path.join(sys.argv[3], 'debugfs') if len(sys.argv) > 3 else shutil.which('debugfs') or '/opt/homebrew/opt/e2fsprogs/sbin/debugfs'
def dump(path, dst):
    subprocess.run([DEBUGFS, '-R', 'dump %s %s' % (path, dst), IMG], capture_output=True)
    ok = os.path.exists(dst) and os.path.getsize(dst) > 0
    if not ok and os.path.exists(dst): os.remove(dst)       # debugfs leaves an empty file behind for a missing path
    return ok
def needed(fn):
    d = open(fn, 'rb').read()
    shoff, = struct.unpack_from('<Q', d, 0x28); sz, cnt, si = struct.unpack_from('<HHH', d, 0x3a)
    secs = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * sz) for i in range(cnt)]
    out = []
    for s in secs:
        if s[1] == 6:  # DYNAMIC
            strs = secs[s[6]]
            for k in range(s[5] // 16):
                tag, val = struct.unpack_from('<qQ', d, s[4] + k * 16)
                if tag == 1:
                    e = d.index(b'\0', strs[4] + val); out.append(d[strs[4] + val:e].decode())
    return out
os.makedirs(OUT + '/lib64', exist_ok=True)
assert dump('/system/bin/audioserver', OUT + '/audioserver'), 'no audioserver in the donor image'
todo = needed(OUT + '/audioserver') + ['libaudiohal@5.0.so', 'libaudiopolicymanagerdefault.so', 'libaudiopolicyenginedefault.so', 'libaudiopolicyengineconfigurable.so',
                                      'libaudiohal.so', 'libaudiohal_deathhandler.so']
seen = {}
while todo:
    n = todo.pop()
    if n in seen: continue
    dst = OUT + '/lib64/' + n
    ok = dump('/system/lib64/' + n, dst)       # libs that are not in /system/lib64 (apex or vendor ones) are skipped
    seen[n] = ok
    if ok: todo += needed(dst)
print(sum(seen.values()), 'libraries copied,', [n for n, ok in sorted(seen.items()) if not ok], 'not in /system/lib64')
