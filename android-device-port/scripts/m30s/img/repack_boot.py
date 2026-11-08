#!/usr/bin/env python3
"""Put a new kernel Image into the stock Samsung SM-M307F boot.img (header v1, no ramdisk, raw arm64 Image).
usage: repack_boot.py STOCK_boot.img NEW_Image OUT_boot.img
Everything else is kept byte for byte, including the AVB footer at the end (flash vbmeta disabled)."""
import struct, sys, hashlib
FMT = '<8s10I16s512s32s1024sIQI'
HLEN = struct.calcsize(FMT)
stock, kern, out = sys.argv[1:4]
d = bytearray(open(stock, 'rb').read())
f = list(struct.unpack(FMT, d[:HLEN]))
assert f[0] == b'ANDROID!' and f[9] == 1 and f[3] == 0 and f[5] == 0, 'expected a v1 header with no ramdisk'
page, ksz = f[8], f[1]
pad = lambda n: -n % page
old_end = page + ksz + pad(ksz)
new = open(kern, 'rb').read()
assert new[56:60] == b'ARMd', 'not a raw arm64 Image'
new_end = page + len(new) + pad(len(new))
# Samsung appends a trailer ('SEANDROIDENFORCE', 'SignerVer02', signature text) right after the padded kernel: move it behind the new kernel
t_end = old_end
if d[old_end:old_end + 9] == b'SEANDROID':
    t_end = old_end
    while d.find(bytes(4096), t_end) != t_end:
        t_end += 1
        while t_end < len(d) and d[t_end] == 0 and d.find(bytes(4096), t_end) != t_end: t_end += 1
trailer = bytes(d[old_end:t_end])
d[old_end:t_end] = bytes(len(trailer))
assert new_end + len(trailer) <= len(d) and not any(d[old_end:new_end + len(trailer)]), 'new kernel overruns the data after the old one'
f[1] = len(new)
f[13] = hashlib.sha1(new + struct.pack('<I', len(new)) + struct.pack('<I', 0) + struct.pack('<I', 0)).digest() + b'\0' * 12
d[:HLEN] = struct.pack(FMT, *f)
d[page:new_end] = new + b'\0' * pad(len(new))
d[new_end:new_end + len(trailer)] = trailer
open(out, 'wb').write(d)
print(f'{out}: kernel {len(new)} B (was {ksz}), total {len(d)} B (unchanged)')
