#!/usr/bin/env python3
"""Stream ONE file out of Google's Pixel factory zip (4.2 GB, nested: outer zip -> stored image-*.zip -> deflated product.img) with HTTP range requests, writing it sparsely.
usage: fetch_factory_product.py FACTORY_URL OUT.img [member=product.img]
Peak disk = the member only (product.img is 4.6 GiB raw, a 2.7 GB download); tools/oneui/stage_google.py takes the result. Public Google download, nothing donor-derived."""
import io, struct, sys, urllib.request, zipfile
class R(io.RawIOBase):
    def __init__(s, url):
        s.url=url; s.pos=0
        r=urllib.request.Request(url, method='HEAD'); s.size=int(urllib.request.urlopen(r).headers['Content-Length'])
    def seekable(s): return True
    def readable(s): return True
    def tell(s): return s.pos
    def seek(s, o, w=0):
        s.pos = o if w==0 else s.pos+o if w==1 else s.size+o; return s.pos
    def readinto(s, b):
        n=len(b)
        if n==0 or s.pos>=s.size: return 0
        e=min(s.pos+n, s.size)-1
        r=urllib.request.Request(s.url, headers={'Range':f'bytes={s.pos}-{e}'})
        d=urllib.request.urlopen(r).read(); b[:len(d)]=d; s.pos+=len(d); return len(d)
class Sub(io.RawIOBase):
    def __init__(s, base, off, size): s.b=base; s.off=off; s.size=size; s.pos=0
    def seekable(s): return True
    def readable(s): return True
    def tell(s): return s.pos
    def seek(s, o, w=0):
        s.pos = o if w==0 else s.pos+o if w==1 else s.size+o; return s.pos
    def readinto(s, b):
        n=min(len(b), s.size-s.pos)
        if n<=0: return 0
        s.b.seek(s.off+s.pos); m=s.b.readinto(memoryview(b)[:n]); s.pos+=m; return m

def open_inner(url):
    r = R(url); z = zipfile.ZipFile(io.BufferedReader(r, 1 << 20))
    i = next(x for x in z.infolist() if '/image-' in x.filename and x.filename.endswith('.zip'))
    assert i.compress_type == 0, 'inner image zip is expected to be stored'
    r.seek(i.header_offset); h = r.read(30); n, e = struct.unpack('<HH', h[26:30]); off = i.header_offset + 30 + n + e
    return zipfile.ZipFile(io.BufferedReader(Sub(r, off, i.file_size), 1 << 20))
if __name__ == '__main__':
    url, out = sys.argv[1:3]; member = sys.argv[3] if len(sys.argv) > 3 else 'product.img'
    with open_inner(url).open(member) as s, open(out, 'wb') as o:
        n = 0
        while True:
            b = s.read(1 << 22)
            if not b: break
            if b.count(0) == len(b): o.seek(len(b), 1)
            else: o.write(b)
            n += len(b)
        o.truncate(n)
    print('wrote', n)
