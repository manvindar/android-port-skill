#!/usr/bin/env python3
"""lpunpack for the Mac (no AOSP lpunpack/simg2img here): list or extract the partitions of an Android `super` image, read straight from the sparse file (no 10 GB raw copy).
usage: lpunpack.py SUPER.img [--list] [--out DIR] [NAME ...]      (SUPER.img: Android sparse or raw; NAME: partitions to extract, default all non-empty)
Samsung's AP tar holds super.img.lz4: `lz4 -d super.img.lz4 super.img` first. Reads LP metadata v10 (geometry at 4096, primary slot 0 at 12288), linear and zero extents of one block device."""
import os, struct, sys, argparse

class Sparse:
    """random access over an Android sparse image (or a plain file)"""
    def __init__(self, path):
        self.f = open(path, 'rb'); h = self.f.read(28); self.chunks = []; self.sparse = False
        if len(h) == 28 and struct.unpack('<I', h[:4])[0] == 0xED26FF3A:
            self.sparse = True
            _, major, minor, hsz, chsz, self.bsz, self.tblk, n, _ = struct.unpack('<IHHHHIIII', h)
            self.f.seek(hsz); pos = 0
            for _ in range(n):
                ctype, _, csz, tsz = struct.unpack('<HHII', self.f.read(12)); body = tsz - 12; dpos = self.f.tell(); length = csz * self.bsz
                fill = self.f.read(4) if ctype == 0xCAC2 else None
                self.f.seek(dpos + body)
                self.chunks.append((pos, length, ctype, dpos, fill)); pos += length
            self.size = self.tblk * self.bsz
        else: self.size = os.path.getsize(path)
    def read(self, off, n):
        if not self.sparse: self.f.seek(off); return self.f.read(n)
        out = bytearray()
        for pos, length, ctype, dpos, fill in self.chunks:
            if pos + length <= off or pos >= off + n: continue
            a = max(off, pos); b = min(off + n, pos + length)
            if ctype == 0xCAC1: self.f.seek(dpos + a - pos); out += self.f.read(b - a)
            elif ctype == 0xCAC2: out += (fill * ((b - a) // 4 + 1))[:b - a]       # fill chunks are 4-byte aligned in practice
            else: out += bytes(b - a)                                              # don't-care / CRC
        return bytes(out)

def parse(sp):
    g = sp.read(4096, 52); magic, ssz = struct.unpack('<II', g[:8]); assert magic == 0x616c4467, 'no LP geometry at 4096: not a super image'
    max_size, slots, lbs = struct.unpack('<III', g[40:52])
    m = sp.read(4096 + 8192, max_size); (magic, major, minor, hsz) = struct.unpack('<IHHI', m[:12]); assert magic == 0x414c5030, 'bad LP metadata magic'
    tables_size = struct.unpack('<I', m[44:48])[0]
    d = struct.unpack('<12I', m[80:128]); (po, pn, ps, eo, en, es, go, gn, gs, bo, bn, bs) = d
    t = m[hsz:hsz + tables_size]
    ext = [struct.unpack('<QIQI', t[eo + i * es: eo + i * es + 24]) for i in range(en)]
    parts = []
    for i in range(pn):
        e = t[po + i * ps: po + (i + 1) * ps]; name = e[:36].split(b'\0')[0].decode(); attr, first, num, grp = struct.unpack('<IIII', e[36:52])
        parts.append((name, attr, ext[first:first + num]))
    return parts

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('super'); ap.add_argument('--list', action='store_true'); ap.add_argument('--out', default='.'); ap.add_argument('names', nargs='*')
    a = ap.parse_args(); sp = Sparse(a.super); parts = parse(sp)
    for name, attr, ext in parts:
        size = sum(x[0] for x in ext) * 512
        if a.list or not size: print(f'{name:24} {size >> 20:6} MiB  extents={len(ext)} attr={attr:#x}'); continue
        if a.names and name not in a.names: continue
        os.makedirs(a.out, exist_ok=True); dst = os.path.join(a.out, name + '.img')
        with open(dst, 'wb') as o:
            for sectors, ttype, tdata, tsrc in ext:
                n = sectors * 512
                if ttype == 1: o.write(bytes(n)); continue
                off = tdata * 512; left = n
                while left: b = sp.read(off, min(left, 1 << 24)); o.write(b); off += len(b); left -= len(b)
        print('extracted', dst, size >> 20, 'MiB')
main()
