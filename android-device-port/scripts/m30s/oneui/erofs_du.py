#!/usr/bin/env python3
"""erofs_du.py IMAGE [PATH] [DEPTH]: per-directory size (MiB) of an EROFS image without extracting it (dump.erofs). Prints a TSV of `path<TAB>MiB<TAB>files` to depth DEPTH below PATH (default / and 3)."""
import subprocess, sys, re, functools
img = sys.argv[1]; root = sys.argv[2] if len(sys.argv) > 2 else '/'; depth = int(sys.argv[3]) if len(sys.argv) > 3 else 3
def dump(args): return subprocess.run(['dump.erofs', *args, img], capture_output=True, text=True).stdout
@functools.lru_cache(None)
def entries(p):
    out = []
    for l in dump(['--ls', f'--path={p}']).splitlines():
        m = re.match(r'\s+(\d+)\s+(\d)\s+(.+)$', l)
        if m and m.group(3) not in ('.', '..'): out.append((int(m.group(2)), m.group(3)))
    return out
def fsize(p):
    m = re.search(r'Size: (\d+)', dump([f'--path={p}'])); return int(m.group(1)) if m else 0
sizes = {}
def walk(p, d):
    tot = n = 0
    for t, name in entries(p):
        c = p.rstrip('/') + '/' + name
        if t == 2:  # directory
            s, k = walk(c, d + 1); tot += s; n += k
        elif t == 1: tot += fsize(c); n += 1
        else: n += 1   # symlink etc: no data
    if d <= depth: sizes[p] = (tot, n)
    return tot, n
walk(root, 0)
for p, (s, n) in sorted(sizes.items()): print(f'{p}\t{s/2**20:.1f}\t{n}')
