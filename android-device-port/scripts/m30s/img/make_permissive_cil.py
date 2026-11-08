#!/usr/bin/env python3
"""Emit (typepermissive T) for every type declared in the CIL files that init compiles into the policy.
usage: make_permissive_cil.py SYSTEM.img VENDOR.img > permissive.cil     (append the output to /system/etc/selinux/plat_sepolicy.cil)
Why: the Samsung kernel boots SELinux enforcing and the A17 init patch that calls setenforce(0) has no effect there; permissive types keep an enforcing kernel from denying anything."""
import os, re, subprocess, sys
E = next(d for d in ('/opt/homebrew/opt/e2fsprogs/sbin', '/usr/local/opt/e2fsprogs/sbin', '/sbin') if os.path.exists(d + '/debugfs'))
system, vendor = sys.argv[1:3]
FILES = [(system, p) for p in ('/system/etc/selinux/plat_sepolicy.cil', '/system/system_ext/etc/selinux/system_ext_sepolicy.cil', '/system/product/etc/selinux/product_sepolicy.cil')] + \
        [(vendor, p) for p in ('/etc/selinux/vendor_sepolicy.cil', '/etc/selinux/plat_pub_versioned.cil', '/etc/selinux/odm_sepolicy.cil')]
types, seen = [], set()
for img, path in FILES:
    t = subprocess.run([E + '/debugfs', '-R', 'cat ' + path, img], capture_output=True).stdout.decode('latin1')
    n = 0
    for m in re.finditer(r'^\(type ([A-Za-z0-9_]+)\)', t, re.M):
        if m.group(1) not in seen: seen.add(m.group(1)); types.append(m.group(1)); n += 1
    print(f'; {path}: {n} types', file=sys.stderr)
print('\n; M30s: every type permissive (Samsung kernel stays enforcing)')
print('\n'.join(f'(typepermissive {x})' for x in types))
print(f'; total {len(types)}', file=sys.stderr)
