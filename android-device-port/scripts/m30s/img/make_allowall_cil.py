#!/usr/bin/env python3
"""Emit CIL that allows everything: the Samsung stock kernel is built with CONFIG_ALWAYS_ENFORCE (security/selinux/Makefile), so setenforce(0)
and (typepermissive T) have no effect (AVD_FLAGS_PERMISSIVE is 0); an allow-all policy is the permissive substitute.
usage: make_allowall_cil.py PLAT_SEPOLICY.cil > allowall.cil     (append to /system/etc/selinux/plat_sepolicy.cil; init's secilc runs with -N, no neverallow check)"""
import re, sys
t = open(sys.argv[1], encoding='latin1').read()
commons = {m.group(1): m.group(2).split() for m in re.finditer(r'^\(common (\S+) \(([^)]*)\)\)', t, re.M)}
cc = {m.group(1): m.group(2) for m in re.finditer(r'^\(classcommon (\S+) (\S+)\)', t, re.M)}
classes = {m.group(1): m.group(2).split() for m in re.finditer(r'^\(class (\S+) \(([^)]*)\)\)', t, re.M)}
out = ['', '; M30s: allow everything (stock kernel cannot be made permissive, see make_allowall_cil.py)', '(typeattribute m30s_allall)', '(typeattributeset m30s_allall (all))']
for c, p in sorted(classes.items()):
    perms = sorted(set(p) | set(commons.get(cc.get(c), [])))
    if not perms: continue
    out.append(f'(allow m30s_allall m30s_allall ({c} ({" ".join(perms)})))')
    if 'ioctl' in perms: out.append(f'(allowx m30s_allall m30s_allall (ioctl {c} (range 0x0000 0xffff)))')
print('\n'.join(out))
print(f'; {len(classes)} classes', file=sys.stderr)
