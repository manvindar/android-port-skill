#!/usr/bin/env python3
"""vintf_gap.py DONOR_SYSTEM.erofs PHONE_VENDOR_DIR: which HAL interfaces the donor system needs/links against, and which of them the M30s Android 11 vendor serves.
PHONE_VENDOR_DIR holds etc/vintf/{manifest.xml,manifest/*.xml} (rdump of the stock vendor image). Prints markdown."""
import glob, os, re, stat, sys, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erofs import Erofs
E = Erofs(sys.argv[1]); VD = sys.argv[2]

def manifest_hals(paths):
    got = {}   # package -> {fmt, interfaces:{iface: set(versions)}}
    for p in paths:
        for h in ET.parse(p).getroot().findall('hal'):
            n = h.findtext('name'); vers = [v.text for v in h.findall('version')] + [x for v in h.findall('versions') for x in [v.text]]
            for ver in h.findall('fqname'): vers.append(ver.text)
            ifs = [i.findtext('name') for i in h.findall('interface')]
            d = got.setdefault(n, {'fmt': h.get('format', 'hidl'), 'vers': set(), 'ifs': set()}); d['vers'] |= {v.split('::')[0].lstrip('@') for v in vers if v}; d['ifs'] |= set(ifs)
    return got
phone = manifest_hals(glob.glob(f'{VD}/etc/vintf/manifest.xml') + glob.glob(f'{VD}/etc/vintf/manifest/*.xml'))

def ver_tuple(v): return tuple(int(x) for x in re.findall(r'\d+', v))
# client libraries in the donor: /system/**/lib64/<pkg>@<maj>.<min>.so (HIDL) and <pkg>-V<n>-ndk.so (AIDL)
hidl, aidl = {}, {}
for p, i in E.walk():
    if not stat.S_ISREG(i.mode) or '/lib64/' not in p: continue
    b = os.path.basename(p)
    m = re.match(r'(.+)@(\d+\.\d+)\.so$', b)
    if m and not m.group(1).startswith('android.hidl') and not m.group(1).startswith('android.hardware.'): hidl.setdefault(m.group(1), set()).add(m.group(2))
    elif m and m.group(1).startswith('android.hardware.'): hidl.setdefault(m.group(1), set()).add(m.group(2))
    m = re.match(r'(.+)-V(\d+)-ndk\.so$', b)
    if m and (m.group(1).startswith('vendor.samsung') or m.group(1).startswith('android.hardware.')): aidl.setdefault(m.group(1), set()).add(int(m.group(2)))

print('## Samsung HIDL client libs in the donor vs the M30s vendor\n\n| package | donor client versions | M30s vendor serves | verdict |\n|---|---|---|---|')
for n in sorted(k for k in hidl if k.startswith('vendor.')):
    have = phone.get(n, {}).get('vers', set()); cl = sorted(hidl[n], key=ver_tuple)
    ok = [v for v in cl if v in have or any(ver_tuple(h)[0] == ver_tuple(v)[0] and ver_tuple(h) >= ver_tuple(v) for h in have)]
    print(f'| {n} | {", ".join(cl)} | {", ".join(sorted(have, key=ver_tuple)) or "-"} | ' + ('ok' if ok else ('MISSING (no such HAL in vendor)' if not have else 'VERSION GAP')) + ' |')
print('\n## Samsung AIDL client libs in the donor (the A11 vendor has no AIDL HALs at all)\n')
print(', '.join(f'{k} V{max(v)}' for k, v in sorted(aidl.items()) if k.startswith('vendor.samsung')) or 'none')
print('\n## AOSP HIDL packages: donor client libs vs vendor\n\n| package | donor | vendor | note |\n|---|---|---|---|')
for n in sorted(k for k in hidl if k.startswith('android.hardware.') and k in phone):
    cl = sorted(hidl[n], key=ver_tuple); have = sorted((v for v in phone[n]['vers'] if re.match(r'\d+\.\d+$', v)), key=ver_tuple)
    if not have: print(f'| {n} | {", ".join(cl)} | unversioned (AIDL or fqname only) | check by hand |'); continue
    print(f'| {n} | {", ".join(cl)} | {", ".join(have)} | ' + ('ok' if set(cl) & set(have) or (cl and have and ver_tuple(have[-1]) >= ver_tuple(cl[-1])) else 'donor client is older than vendor' if ver_tuple(cl[-1]) < ver_tuple(have[0]) else 'donor wants newer') + ' |')
print('\n## Vendor HALs with no donor client\n')
print(', '.join(sorted(n for n in phone if n not in hidl)))
