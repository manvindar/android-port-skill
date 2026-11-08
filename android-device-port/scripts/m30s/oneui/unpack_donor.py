#!/usr/bin/env python3
"""Samsung full-firmware zip -> extracted partition trees, using as little disk as possible. Nothing but AP's super.img.lz4 is read; BL, CP and CSC are never touched.
usage: unpack_donor.py FIRMWARE.zip OUT_DIR [--parts system_ext,product,system,odm,optics,prism] [--keep-images]
  1. finds AP_*.tar.md5 inside the zip (stored, read in place), copies super.img.lz4 out through `lz4 -d` into OUT_DIR/super.img (Android sparse)
  2. tools/oneui/lpunpack.py cuts the wanted partitions out of it, one EROFS image at a time
  3. fsck.erofs --extract=OUT_DIR/tree/<part> (Homebrew erofs-utils) unpacks each, the image is deleted straight away
Needs: lz4 and fsck.erofs on PATH (brew install lz4 erofs-utils). macOS is case-insensitive and hdiutil is blocked in the agent sandbox: the script compares the extracted entry count with the inode count of the EROFS superblock (dump.erofs -s) and says so when they differ (case collisions or failures)."""
import argparse, os, shutil, subprocess, sys, tarfile, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('zip'); ap.add_argument('out'); ap.add_argument('--parts', default='system_ext,product,system,odm,optics,prism'); ap.add_argument('--keep-images', action='store_true')
a = ap.parse_args(); out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
sup = os.path.join(out, 'super.img')
if not os.path.exists(sup):
    z = zipfile.ZipFile(a.zip); ap_name = next(n for n in z.namelist() if n.startswith('AP_') and '.tar' in n); print('AP:', ap_name)
    with z.open(ap_name) as zf, tarfile.open(fileobj=zf, mode='r:') as t:
        m = next(m for m in t if m.name.startswith('super.img'))
        print('member', m.name, m.size >> 20, 'MiB')
        src = t.extractfile(m)
        with open(sup, 'wb') as o:
            if m.name.endswith('.lz4'):
                p = subprocess.Popen(['lz4', '-dc'], stdin=subprocess.PIPE, stdout=o)
                shutil.copyfileobj(src, p.stdin, 1 << 24); p.stdin.close(); assert p.wait() == 0, 'lz4 failed'
            else: shutil.copyfileobj(src, o, 1 << 24)
print('super.img', os.path.getsize(sup) >> 20, 'MiB'); subprocess.run([sys.executable, '-I', os.path.join(HERE, 'lpunpack.py'), sup, '--list'], check=True)
import re
for part in a.parts.split(','):
    img = os.path.join(out, 'img', part + '.img'); tree = os.path.join(out, 'tree', part)
    r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'lpunpack.py'), sup, '--out', os.path.join(out, 'img'), part], capture_output=True, text=True)
    if not os.path.exists(img): print('skip', part, '(not in super or empty)'); continue
    shutil.rmtree(tree, ignore_errors=True); os.makedirs(tree)
    r = subprocess.run(['fsck.erofs', '--extract=' + tree, '--no-xattrs', '--overwrite', '--force', img], capture_output=True, text=True)
    print(part, 'extract rc', r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:] or '')
    sb = subprocess.run(['dump.erofs', '-s', img], capture_output=True, text=True).stdout; m = re.search(r'inode count:\s*(\d+)', sb)
    got = sum(len(ds) + len(fs) for _, ds, fs in os.walk(tree)) + 1
    if m and got != int(m.group(1)): print(f'  WARNING {part}: {got} entries extracted, superblock says {m.group(1)} inodes (case collisions on APFS, or extraction errors)')
    n_files = sum(len(fs) for _, _, fs in os.walk(tree)); print(part, n_files, 'files', sum(os.path.getsize(os.path.join(r_, f)) for r_, _, fs in os.walk(tree) for f in fs if not os.path.islink(os.path.join(r_, f))) >> 20, 'MiB')
    if not a.keep_images: os.remove(img)
os.path.exists(sup) and print('super.img kept (delete it when the trees are good):', sup)
