#!/usr/bin/env python3
"""Minimal read-only EROFS reader for the uncompressed images Samsung ships (plain, inline and chunk layouts; no compression).
Why: the Mac has no erofs mount and `fsck.erofs --extract` as a normal user loses uid/gid. This reads mode, uid, gid, xattrs (security.selinux, security.capability) and data straight from the image.
usage: erofs.py IMAGE            prints counts per type (compare with `dump.erofs -S IMAGE`) and checks every regular file reads back to its size
as a module: E = Erofs(path); for path, ino in E.walk(): ino.mode / .uid / .gid / .size / .xattrs / E.read(ino) / E.readlink(ino)"""
import struct, sys, os, stat

class Inode:
    __slots__ = ('nid', 'mode', 'uid', 'gid', 'size', 'layout', 'raw', 'isize', 'xcount', 'off', 'xattrs')

class Erofs:
    def __init__(self, path):
        self.f = open(path, 'rb')
        sb = self._at(1024, 128)
        magic, = struct.unpack_from('<I', sb, 0); assert magic == 0xE0F5E1E2, 'not erofs'
        self.bs = 1 << sb[12]; self.root, = struct.unpack_from('<H', sb, 14)
        self.meta, self.xblk = struct.unpack_from('<II', sb, 40)
        incompat, = struct.unpack_from('<I', sb, 80)
        assert incompat & ~0x4 == 0, f'unsupported incompat features {incompat:#x} (compression, device table...)'   # 0x4 = chunked_file
    def _at(self, off, n): self.f.seek(off); return self.f.read(n)
    def inode(self, nid):
        i = Inode(); i.nid = nid; i.off = self.meta * self.bs + nid * 32
        h = self._at(i.off, 64); fmt, i.xcount, i.mode = struct.unpack_from('<HHH', h, 0)
        i.layout = (fmt >> 1) & 7
        if fmt & 1: i.size, i.raw, _, i.uid, i.gid = struct.unpack_from('<QI4sII', h, 8); i.isize = 64
        else: i.size, _, i.raw, _, i.uid, i.gid = struct.unpack_from('<IIIIHH', h, 8); i.isize = 32
        i.xattrs = self._xattrs(i); return i
    def _xattr_entries(self, buf, pos, end, out):
        while pos + 4 <= end:
            nl, idx, vs = struct.unpack_from('<BBH', buf, pos); pos += 4
            name = buf[pos:pos + nl]; pos += nl; val = buf[pos:pos + vs]; pos += vs; pos = (pos + 3) & ~3
            assert not idx & 0x80, 'long xattr prefix'
            prefix = {1: b'user.', 2: b'system.posix_acl_access', 3: b'system.posix_acl_default', 4: b'trusted.', 6: b'security.'}.get(idx, b'')
            out[(prefix + name).decode('latin1')] = val
    def _xattrs(self, i):
        out = {}
        if not i.xcount: return out
        n = 12 + (i.xcount - 1) * 4; buf = self._at(i.off + i.isize, n); shared = buf[4]
        for k in range(shared):
            sid, = struct.unpack_from('<I', buf, 12 + 4 * k); blk = self._at(self.xblk * self.bs + sid * 4, 4 + 255 + 65535)
            nl, _, vs = struct.unpack_from('<BBH', blk, 0); self._xattr_entries(blk, 0, 4 + nl + vs, out)
        self._xattr_entries(buf, 12 + 4 * shared, n, out); return out
    def read(self, i):
        sz = i.size
        if i.layout == 0: return self._at(i.raw * self.bs, sz)
        if i.layout == 2:
            full = sz // self.bs * self.bs; tail = sz - full
            xs = 12 + (i.xcount - 1) * 4 if i.xcount else 0
            return (self._at(i.raw * self.bs, full) if full else b'') + (self._at(i.off + i.isize + xs, tail) if tail else b'')
        if i.layout == 4:
            xs = 12 + (i.xcount - 1) * 4 if i.xcount else 0
            fmt = i.raw & 0xFFFF
            cbits = self.bs.bit_length() - 1 + (fmt & 0x1f); csz = 1 << cbits; n = (sz + csz - 1) >> cbits
            esz = 8 if fmt & 0x20 else 4; idx = self._at(i.off + i.isize + xs, n * esz); out = bytearray()
            for k in range(n):
                blk = struct.unpack_from('<I', idx, k * esz + (4 if esz == 8 else 0))[0]
                want = min(csz, sz - k * csz)
                out += bytes(want) if blk == 0xFFFFFFFF else self._at(blk * self.bs, want)
            return bytes(out)
        raise NotImplementedError(f'layout {i.layout}')
    def readlink(self, i): return self.read(i).decode('utf-8', 'surrogateescape')
    def listdir(self, i):
        data = self.read(i); out = []
        for b in range(0, len(data), self.bs):
            blk = data[b:b + self.bs]; first, = struct.unpack_from('<H', blk, 8); cnt = first // 12
            ents = [struct.unpack_from('<QHBx', blk, 12 * k) for k in range(cnt)]
            for k, (nid, noff, _t) in enumerate(ents):
                end = ents[k + 1][1] if k + 1 < cnt else len(blk)
                name = blk[noff:end].split(b'\0')[0] if k + 1 == cnt else blk[noff:end]
                name = name.decode('utf-8', 'surrogateescape')
                if name not in ('.', '..'): out.append((name, nid))
        return out
    def walk(self, skip=lambda p: False, root='/'):
        """yield (path, inode) parents first; skip(path) -> True prunes that path and everything below it"""
        stack = [(root, self.inode(self.root))]
        while stack:
            p, i = stack.pop(); yield p, i
            if stat.S_ISDIR(i.mode):
                for name, nid in sorted(self.listdir(i), reverse=True):
                    c = p.rstrip('/') + '/' + name
                    if not skip(c): stack.append((c, self.inode(nid)))

if __name__ == '__main__':
    E = Erofs(sys.argv[1]); cnt = {}; total = 0
    for p, i in E.walk():
        k = stat.S_IFMT(i.mode); cnt[k] = cnt.get(k, 0) + 1
        if stat.S_ISREG(i.mode):
            assert len(E.read(i)) == i.size, p; total += i.size
        elif stat.S_ISLNK(i.mode): assert len(E.readlink(i)) == i.size, p
    print({stat.filemode(k): v for k, v in cnt.items()}, 'bytes', total)
