#!/usr/bin/env python3
"""Layer a staged One UI tree onto a FINISHED system image (the v0.2-img Pixel image) with debugfs: no GSI, no donor inputs, no rebuild of the base.
usage: apply_layer.py BASE.img STAGE_DIR OUT.img [--e2fs DIR] [--remove PATH ...]
STAGE_DIR holds <partition>/... trees (system, system_ext, product, optics, prism) that land under /system/<partition>/ (the M30s has ONE system partition: /system/system_ext and /system/product are plain
directories); `system/<x>` lands in /system/<x>. oneui-stage.json (optional): {"remove": [GSI/Pixel files to delete first], "exec": [stage-relative paths that get mode 755], "symlinks": {"/system/a": "target"}}.
Files under lib/ or lib64/ get u:object_r:system_lib_file:s0, the rest system_file (the kernel boots permissive; labels are cosmetic). Existing files are replaced (rm + write). OUT.img is a copy of BASE.img
(dd bs=4m: cp is slow on multi-GB files here); the free-space check refuses a layer that does not fit; e2fsck -fn must be clean at the end."""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('stage'); ap.add_argument('out'); ap.add_argument('--e2fs'); ap.add_argument('--remove', action='append', default=[])
a = ap.parse_args()
E2 = a.e2fs or next(d for d in ('/opt/homebrew/opt/e2fsprogs/sbin', '/usr/local/opt/e2fsprogs/sbin', '/sbin', '/usr/sbin') if os.path.exists(d + '/debugfs'))
st = os.path.abspath(a.stage); man = json.load(open(os.path.join(st, 'oneui-stage.json'))) if os.path.exists(os.path.join(st, 'oneui-stage.json')) else {}
staged = sorted(os.path.relpath(os.path.join(r, f), st) for r, _, fs in os.walk(st) for f in fs if f != 'oneui-stage.json')
dst_of = lambda f: '/' + f if f.startswith('system/') else '/system/' + f
tmp = tempfile.mkdtemp()
def dbg(*c, img=None): return subprocess.run([os.path.join(E2, 'debugfs'), *c, img or a.out], capture_output=True, text=True)
if os.path.abspath(a.base) != os.path.abspath(a.out): subprocess.run(['dd', 'if=' + a.base, 'of=' + a.out, 'bs=4m'], check=True, capture_output=True)
# free space
info = subprocess.run([os.path.join(E2, 'dumpe2fs'), '-h', a.out], capture_output=True, text=True).stdout
bs = int(re.search(r'Block size:\s+(\d+)', info).group(1)); free = int(re.search(r'Free blocks:\s+(\d+)', info).group(1)) * bs
need = sum((os.path.getsize(os.path.join(st, f)) + bs - 1) // bs * bs for f in staged)
print(f'{len(staged)} files, layer {need >> 20} MiB, free in image {free >> 20} MiB')
if need > free + 0: sys.exit(f'layer does not fit: need {need >> 20} MiB, free {free >> 20} MiB (before the removals)')
lbl = {}
def label(ctx):
    if ctx not in lbl: lbl[ctx] = os.path.join(tmp, 'l%d' % len(lbl)); open(lbl[ctx], 'wb').write(ctx.encode() + b'\0')
    return lbl[ctx]
SYS, LIB = 'u:object_r:system_file:s0', 'u:object_r:system_lib_file:s0'
cmds = []; made = set()
def exists(p): return 'Inode:' in dbg('-R', 'stat ' + p).stdout
for r in man.get('remove', []) + a.remove:
    if exists(r): cmds.append('rm ' + r)
    else: print('  (not in image, skipped removal)', r)
for f in staged:
    d = os.path.dirname(dst_of(f)); chain = []
    while d not in ('/system', '/') and d not in made:
        chain.append(d); d = os.path.dirname(d)
    for d in reversed(chain):
        made.add(d)
        if not exists(d): cmds += [f'mkdir {d}', f'set_inode_field {d} mode 040755', f'set_inode_field {d} uid 0', f'set_inode_field {d} gid 0', f'ea_set -f {label(SYS)} {d} security.selinux']
for f in staged:
    d = dst_of(f); mode = '755' if f in man.get('exec', []) else '644'; ctx = LIB if '/lib64/' in f or '/lib/' in f else SYS
    if os.path.islink(os.path.join(st, f)): cmds += [f'rm {d}', f'symlink {d} {os.readlink(os.path.join(st, f))}', f'ea_set -f {label(ctx)} {d} security.selinux']; continue
    cmds += [f'rm {d}', f'write {os.path.join(st, f)} {d}', f'set_inode_field {d} mode 0100{mode}', f'set_inode_field {d} uid 0', f'set_inode_field {d} gid 0', f'ea_set -f {label(ctx)} {d} security.selinux']
for p, t in man.get('symlinks', {}).items(): cmds += [f'rm {p}', f'symlink {p} {t}', f'ea_set -f {label(LIB)} {p} security.selinux']
cf = os.path.join(tmp, 'cmds'); open(cf, 'w').write('\n'.join(cmds) + '\n')
r = subprocess.run([os.path.join(E2, 'debugfs'), '-w', '-f', cf, a.out], capture_output=True, text=True)
bad = [l for l in (r.stdout + r.stderr).split('\n') if re.search(r'(?i)(error|not found|no such|not enough|no space)', l) and not l.startswith('debugfs: rm ') and 'File not found by ext2_lookup' not in l]
if bad: sys.exit('debugfs reported:\n' + '\n'.join(bad[:20]))
e = subprocess.run([os.path.join(E2, 'e2fsck'), '-fn', a.out], capture_output=True, text=True); print(e.stdout.strip().splitlines()[-1])
if e.returncode: sys.exit('e2fsck is not clean:\n' + e.stdout[-1500:])
shutil.rmtree(tmp, ignore_errors=True); print('ok:', a.out)
