#!/usr/bin/env python3
"""erofs2ext4.py SRC.erofs OUT.img [--size-mib 4800] [--exclude LIST ...] [--dry-run]
Repack a Samsung EROFS partition into a raw ext4 image the M30s kernel (4.14, no erofs) can mount, minus a debloat list.
Keeps mode, uid, gid, symlinks, security.selinux and security.capability of every file; works as a normal user on macOS (debugfs, no mount).
--exclude LIST: text file, one fnmatch pattern per line (`#` comments); a match prunes that path and everything below it. Patterns match the full path in the image, e.g. /system/priv-app/OneDrive_Samsung_v3 or /system/app/SamsungTTSVoice_*.
--dry-run: print what would be kept and the size, write nothing.
Disk use while running: the output image (sparse, grows to the kept size) + one batch of source files (<= 300 MiB)."""
import argparse, fnmatch, os, re, shutil, stat, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erofs import Erofs

ap = argparse.ArgumentParser()
ap.add_argument('src'); ap.add_argument('out'); ap.add_argument('--size-mib', type=int, default=4800)
ap.add_argument('--exclude', action='append', default=[]); ap.add_argument('--dry-run', action='store_true')
ap.add_argument('--e2fs', default='/opt/homebrew/opt/e2fsprogs/sbin'); ap.add_argument('--inodes', type=int, default=24000)
a = ap.parse_args()

pats = [x for f in a.exclude for l in open(f) for x in [l.split('#')[0].strip()] if x]
E = Erofs(a.src)
skipped = []
def skip(p):
    if any(fnmatch.fnmatchcase(p, x) for x in pats): skipped.append(p); return True
    return False
entries = list(E.walk(skip))
files = [(p, i) for p, i in entries if stat.S_ISREG(i.mode)]
kept = sum(i.size for _, i in files)
print(f'{len(entries)} entries, {len(files)} files, {kept / 2**20:.0f} MiB kept; {len(skipped)} paths excluded')
if len(skipped) != len({s for s in skipped}): sys.exit('duplicate matches?')
unmatched = [x for x in pats if not any(fnmatch.fnmatchcase(s, x) for s in skipped)]
if unmatched: print('patterns that matched nothing:', *unmatched, sep='\n  ')
if a.dry_run: sys.exit(0)

tmp = tempfile.mkdtemp(prefix='erofs2ext4'); lbl = {}
def val_file(b):
    if b not in lbl: lbl[b] = os.path.join(tmp, 'v%d' % len(lbl)); open(lbl[b], 'wb').write(b)
    return lbl[b]
q = lambda s: f'"{s}"' if re.search(r'\s', s) else s
def attr_cmds(p, i):
    t = {stat.S_IFDIR: 0o040000, stat.S_IFREG: 0o100000, stat.S_IFLNK: 0o120000}[stat.S_IFMT(i.mode)]
    c = [f'set_inode_field {q(p)} mode 0{t | (i.mode & 0o7777):o}', f'set_inode_field {q(p)} uid {i.uid}', f'set_inode_field {q(p)} gid {i.gid}']
    for k in ('security.selinux', 'security.capability'):
        if k in i.xattrs: c.append(f'ea_set -f {val_file(i.xattrs[k] + (b"\0" if k == "security.selinux" else b""))} {q(p)} {k}')
    return c
bad_re = re.compile(r'(?i)(error|not found|no such|not enough|no space|bad|invalid)')
def debugfs(cmds):
    f = os.path.join(tmp, 'cmds'); open(f, 'w').write('\n'.join(cmds) + '\n')
    r = subprocess.run([os.path.join(a.e2fs, 'debugfs'), '-w', '-f', f, a.out], capture_output=True, text=True)
    bad = [l for l in (r.stdout + r.stderr).split('\n') if bad_re.search(l) and not l.startswith('debugfs:')]
    if bad: sys.exit('debugfs reported:\n' + '\n'.join(bad[:20]))

if os.path.exists(a.out): os.remove(a.out)
subprocess.run([os.path.join(a.e2fs, 'mke2fs'), '-q', '-t', 'ext4', '-b', '4096', '-m', '0', '-L', 'system', '-I', '256', '-N', str(a.inodes),
                '-O', '^has_journal,^orphan_file', '-E', 'root_owner=0:0', a.out, f'{a.size_mib}M'], check=True)
cmds = []
for p, i in entries:                                    # directories first (walk yields parents before children), then symlinks
    if stat.S_ISDIR(i.mode):
        if p != '/': cmds.append(f'mkdir {q(p)}')
        cmds += attr_cmds(p, i)
for p, i in entries:
    if stat.S_ISLNK(i.mode): cmds += [f'symlink {q(p)} {E.readlink(i)}'] + attr_cmds(p, i)
debugfs(cmds); print('dirs and symlinks done')
batch, bsize, done = [], 0, 0
def flush():
    global batch, bsize
    c = []
    for p, i, src in batch: c += [f'write {src} {q(p)}'] + attr_cmds(p, i)
    debugfs(c)
    for _, _, src in batch: os.remove(src)
    batch, bsize = [], 0
for p, i in files:
    src = os.path.join(tmp, 'f%d' % len(batch)); open(src, 'wb').write(E.read(i))
    batch.append((p, i, src)); bsize += i.size; done += i.size
    if bsize > 300 * 2**20: flush(); print(f'  {done / 2**20:.0f} / {kept / 2**20:.0f} MiB', flush=True)
flush()
shutil.rmtree(tmp)
r = subprocess.run([os.path.join(a.e2fs, 'e2fsck'), '-fn', a.out], capture_output=True, text=True); print(r.stdout[-400:], r.stderr[-200:])
sys.exit(r.returncode)
