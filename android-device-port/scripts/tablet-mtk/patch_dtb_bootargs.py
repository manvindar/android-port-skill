#!/usr/bin/env python3
"""Swap the debug-only bootargs `slub_debug=OFZPU page_owner=on` and `console=tty0` in a boot.img DTB section for
`cpuidle.off=1 printk.devkmsg=on`, byte for byte (same length, so the DTB layout is untouched).

Why: this bootloader ignores the boot.img cmdline and uses /chosen/bootargs from the DTB. cpuidle.off=1 avoids a NULL deref in
MediaTek's MCDI deep-idle code on the 4.9.117 source; printk.devkmsg=on stops the kernel dropping init's messages after ten.
usage: patch_dtb_bootargs.py stock_dtb.bin out_dtb.bin   (the dtb section extracted from the stock boot.img)"""
import sys
d = bytearray(open(sys.argv[1], 'rb').read())
i = d.index(b'console=tty0'); j = d.index(b'\0', i); old = bytes(d[i:j])
new = old.replace(b'console=tty0 ', b'').replace(b'slub_debug=OFZPU page_owner=on', b'cpuidle.off=1 printk.devkmsg=on')
assert len(new) <= len(old) and b'cpuidle.off=1' in new, old
d[i:j] = new.ljust(len(old), b' ')
open(sys.argv[2], 'wb').write(d); print(bytes(d[i:j]).decode().rstrip())
