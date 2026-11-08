#!/usr/bin/env python3
"""Copy a boot image (header v0/v1) with a new kernel cmdline (<= 511 bytes). No other byte changes,
so the AVB footer no longer matches: use only with verification off. Usage: boot_cmdline.py in.img out.img 'cmdline'"""
import sys
src, dst, cmd = sys.argv[1:4]
d = bytearray(open(src, 'rb').read())
assert d[:8] == b'ANDROID!', 'not a boot image'
c = cmd.encode()
assert len(c) <= 511
d[64:576] = c.ljust(512, b'\0')
open(dst, 'wb').write(d)
print(dst, 'cmdline =', repr(d[64:576].split(b'\0')[0].decode()))
