#!/usr/bin/env python3
"""Remove exactly what install_gapps.sh installed (the list in /system/etc/gapps-installed.txt of the image) from a raw ext4 system image, offline with debugfs.
usage: strip_gapps_image.py IMAGE [--e2fs DIR] [--keep-gapps] [--also PATH ...]   (edits in place; run on a copy; --also removes extra files/dirs, e.g. a Dolby port)"""
import os, subprocess, sys
img = sys.argv[1]; e2 = sys.argv[sys.argv.index('--e2fs') + 1] if '--e2fs' in sys.argv else '/opt/homebrew/opt/e2fsprogs/sbin'
dbg = lambda *c: subprocess.run([os.path.join(e2, 'debugfs'), *c], capture_output=True, text=True).stdout
lst = dbg('-R', 'cat /system/etc/gapps-installed.txt', img).split()
extra = sys.argv[sys.argv.index('--also') + 1:] if '--also' in sys.argv else []
lst = ([] if '--keep-gapps' in sys.argv else [x for x in lst if x not in extra]) + extra
assert lst, 'no manifest in the image'
keep = '--keep-gapps' in sys.argv
cmds = []
def walk(path):
    """('ls -p' lists `/inode/mode/uid/gid/name/size/`) -> rm files, recurse into directories, rmdir last"""
    out = dbg('-R', f'ls -p {path}', img); subs = []
    for line in out.split('\n'):
        f = line.split('/')
        if len(f) < 6 or f[5] in ('.', '..', ''): continue
        name = f[5]; isdir = f[2].startswith('04')
        (subs.append(name) if isdir else cmds.append(f'rm {path}/{name}'))
    for n in subs: walk(f'{path}/{n}')
    cmds.append(f'rmdir {path}')
for p in lst:
    st = dbg('-R', f'stat {p}', img)
    if 'Type: directory' in st: walk(p)
    elif 'Type: regular' in st: cmds.append(f'rm {p}')
if not keep and '/system/etc/gapps-installed.txt' not in extra: cmds.append('rm /system/etc/gapps-installed.txt')
open('/tmp/strip_cmds.txt', 'w').write('\n'.join(cmds) + '\n')
subprocess.run([os.path.join(e2, 'debugfs'), '-w', '-f', '/tmp/strip_cmds.txt', img], capture_output=True)
print(len(cmds), 'removals; run e2fsck -fn to verify')
