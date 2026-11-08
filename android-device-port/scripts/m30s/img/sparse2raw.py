#!/usr/bin/env python3
"""Android sparse image -> raw image (no simg2img on the Mac). Usage: sparse2raw.py in.img out.raw"""
import struct, sys

def main(src, dst):
    with open(src, 'rb') as f, open(dst, 'wb') as o:
        magic, major, minor, hsz, chsz, bsz, tblk, nchunk, _ = struct.unpack('<IHHHHIIII', f.read(28))
        assert magic == 0xED26FF3A and major == 1, 'not an Android sparse image'
        f.seek(hsz)
        for _ in range(nchunk):
            ctype, _, csz, tsz = struct.unpack('<HHII', f.read(12))
            n = csz * bsz
            if ctype == 0xCAC1:
                left = n
                while left:
                    b = f.read(min(left, 1 << 24)); o.write(b); left -= len(b)
            elif ctype == 0xCAC2:
                o.write(f.read(4) * (n // 4))
            elif ctype == 0xCAC3:
                o.seek(n, 1)
            elif ctype == 0xCAC4:
                f.read(4)
            else:
                raise SystemExit('bad chunk %#x' % ctype)
        o.truncate(tblk * bsz)
    print(src, '->', dst, tblk * bsz, 'bytes')

main(*sys.argv[1:3])
