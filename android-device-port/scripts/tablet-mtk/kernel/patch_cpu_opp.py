#!/usr/bin/env python3
"""CPU overclock kernel for the TB-X606V (MT8768, Lenovo kernel 4.9.190): give the fast cluster (cpu0-3) the 2.50 GHz OPP table that the same kernel already
carries for the faster bins, in place of its own 2.30 GHz table.

usage: patch_cpu_opp.py KERNEL_IMAGE_IN KERNEL_IMAGE_OUT      (the decompressed arm64 Image, e.g. `kernel` from `magiskboot unpack boot.img`)

The OPP tables are arrays of 16 pairs (frequency in kHz, voltage in 10 uV) in the kernel data. This tablet's table starts 2301000/111875, 2215000/106875 ... 900000/60000.
The bins above it start 2501000/111875 (two variants: 2383000/106875 or 2397000/107500 as second step). The script copies the variant with 2383000/106875 as second step (milder voltage on the middle steps; it is the one flashed on 2026-11-04) over the stock table,
so the hybrid DVFS firmware gets a LUT with 2.50 GHz as the top step (the kernel builds it from this table at boot). It changes 24 bytes. Only the fast cluster is touched.
"""
import struct, sys

STOCK = [2301000, 2215000, 2139000, 2074000, 2009000, 1944000, 1879000, 1814000, 1750000, 1617000, 1484000, 1351000, 1218000, 1085000, 979000, 900000]

def tables(k):
    """offsets of every 16 entry (kHz, 10 uV) table with descending frequencies"""
    out, o = [], 0
    while o + 128 <= len(k):
        f = struct.unpack_from('<32I', k, o)
        fr, v = f[0::2], f[1::2]
        if 300000 <= fr[0] <= 3000000 and all(fr[i] > fr[i + 1] for i in range(15)) and all(40000 <= x <= 150000 for x in v):
            out.append(o); o += 128
        else:
            o += 4
    return out

def main(src, dst):
    k = bytearray(open(src, 'rb').read())
    ts = tables(k)
    stock = [o for o in ts if list(struct.unpack_from('<32I', k, o)[0::2]) == STOCK]
    fast = [o for o in ts if struct.unpack_from('<I', k, o)[0] == 2501000]
    fast.sort(key=lambda o: struct.unpack_from('<I', k, o + 8)[0] != 2383000)   # the 2383000 variant first
    assert len(stock) == 1, f'expected one stock table, found {len(stock)}'
    assert fast, 'no 2.50 GHz table in this kernel'
    k[stock[0]:stock[0] + 128] = k[fast[0]:fast[0] + 128]
    open(dst, 'wb').write(k)
    print(f'stock table at {stock[0]:#x} replaced by the 2.50 GHz table at {fast[0]:#x}; tables seen: {len(ts)}')

if __name__ == '__main__':
    main(*sys.argv[1:3])
