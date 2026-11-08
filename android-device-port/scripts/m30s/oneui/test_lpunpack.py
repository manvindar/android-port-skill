#!/usr/bin/env python3
"""Self-check for lpunpack.py: builds a tiny LP super (raw and as an Android sparse image) with two partitions and extracts them. Run: python3 -I tools/oneui/test_lpunpack.py"""
import os, struct, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); tmp = tempfile.mkdtemp()
def part(name, first, num): return name.encode().ljust(36, b'\0') + struct.pack('<IIII', 0, first, num, 0)
exts = [(8, 0, 2048, 0), (8, 0, 2056, 0)]                     # two linear extents of 4 KiB each at sectors 2048, 2056
parts = [part('system', 0, 1), part('product', 1, 1), part('empty', 2, 0)]
tables = b''.join(parts) + b''.join(struct.pack('<QIQI', *e) for e in exts)
hdr = struct.pack('<IHHI', 0x414c5030, 10, 2, 256).ljust(44, b'\0') + struct.pack('<I', len(tables)) + bytes(32)
hdr += struct.pack('<12I', 0, 3, 52, 3 * 52, 2, 24, 0, 0, 0, 0, 0, 0); hdr = hdr.ljust(256, b'\0')
geo = (struct.pack('<II', 0x616c4467, 52) + bytes(32) + struct.pack('<III', 4096, 1, 4096)).ljust(4096, b'\0')
img = bytearray(4096 + 4096 + 4096 + 4096 + 4096)               # reserved, geometry, backup geometry, metadata slot (max 4096), backup
img[4096:8192] = geo; img[12288:12288 + len(hdr + tables)] = hdr + tables
img += bytes(2048 * 512 - len(img)); img += b'S' * 4096 + b'P' * 4096
raw = os.path.join(tmp, 'super.raw'); open(raw, 'wb').write(img)
# sparse form: one RAW chunk per 4 KiB block run, a DONT_CARE hole in the middle
bsz = 4096; nb = len(img) // bsz; hole = (4, nb - 2)
sp = bytearray(struct.pack('<IHHHHIIII', 0xED26FF3A, 1, 0, 28, 12, bsz, nb, 3, 0))
sp += struct.pack('<HHII', 0xCAC1, 0, hole[0], 12 + hole[0] * bsz) + img[:hole[0] * bsz]
sp += struct.pack('<HHII', 0xCAC3, 0, hole[1] - hole[0], 12) + struct.pack('<HHII', 0xCAC1, 0, 2, 12 + 2 * bsz) + img[-2 * bsz:]
sparse = os.path.join(tmp, 'super.sparse'); open(sparse, 'wb').write(sp)
for src in (raw, sparse):
    out = os.path.join(tmp, 'o_' + os.path.basename(src))
    r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'lpunpack.py'), src, '--out', out], capture_output=True, text=True); assert r.returncode == 0, r.stderr
    assert open(os.path.join(out, 'system.img'), 'rb').read() == b'S' * 4096 and open(os.path.join(out, 'product.img'), 'rb').read() == b'P' * 4096, src
    assert not os.path.exists(os.path.join(out, 'empty.img'))
print('lpunpack ok (raw and sparse)')
