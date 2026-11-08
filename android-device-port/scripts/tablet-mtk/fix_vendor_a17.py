#!/usr/bin/env python3
"""Make the tablet's Android 10 vendor fstabs readable by Android 17's libfstab. Run with the tablet in TWRP (adb recovery).

Android 17 treats the legacy flags `forcefdeorfbe=` and `resize` as a parse error, so init cannot read any default fstab and
/data never mounts. Android 16 ignored them, so removing them changes nothing there. /metadata is added because Android 17
expects it (aconfig, bootstat). The originals are saved as <file>.orig-a17. Nothing from the vendor image is stored in this repo.
usage: fix_vendor_a17.py [adb]"""
import re, subprocess, sys, tempfile, os
ADB = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/Library/Android/sdk/platform-tools/adb')
VENDOR = '/dev/block/by-name/vendor'
sh = lambda c: subprocess.run([ADB, 'shell', c], capture_output=True, text=True).stdout
assert 'recovery' in subprocess.run([ADB, 'devices'], capture_output=True, text=True).stdout, 'put the tablet in TWRP first'
sh('mkdir -p /mnt/v; umount /mnt/v 2>/dev/null; mount -t ext4 -o rw %s /mnt/v' % VENDOR)
for name in ('fstab.mt6765', 'fstab.mt8768'):
    cur = sh('cat /mnt/v/etc/' + name)
    if 'forcefdeorfbe' not in cur and 'metadata /metadata' in cur: print(name, 'already fixed'); continue
    out = []
    for l in cur.split('\n'):
        f = l.split()
        if len(f) >= 5 and l.startswith('/'):
            f[4] = re.sub(r',forcefdeorfbe=[^\s,]*', '', f[4]); f[4] = re.sub(r',resize\b', '', f[4]); f[4] = re.sub(r',+', ',', f[4]).strip(',')
            l = ' '.join(f)
        out.append(l)
        if l.startswith('/dev/block/platform/bootdevice/by-name/cache '):
            out.append('/dev/block/platform/bootdevice/by-name/metadata /metadata ext4 noatime,nosuid,nodev,discard wait,check,formattable')
    with tempfile.NamedTemporaryFile('w', delete=False) as t: t.write('\n'.join(out))
    subprocess.run([ADB, 'push', t.name, '/tmp/fstab.new'], capture_output=True)
    sh('[ -f /mnt/v/etc/%s.orig-a17 ] || cat /mnt/v/etc/%s > /mnt/v/etc/%s.orig-a17; cat /tmp/fstab.new > /mnt/v/etc/%s' % (name, name, name, name))  # cat keeps inode + SELinux label
    print(name, 'fixed; forcefde left:', sh('grep -c forcefde /mnt/v/etc/' + name).strip())
sh('sync; umount /mnt/v')
