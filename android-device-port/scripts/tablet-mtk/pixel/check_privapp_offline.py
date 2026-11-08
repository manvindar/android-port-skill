#!/usr/bin/env python3
"""Offline version of the boot-time privileged-permission allowlist check (see check_privapp.py, which asks a tablet instead).

usage: check_privapp_offline.py --perm-apk framework-res.apk [--perm-apk SystemUI.apk ...] --allow privapp.xml [--allow ...] --apk priv-app.apk [--apk ...]
A priv-app that requests a `privileged` permission which no allowlist grants it makes system_server abort at boot (ro.control_privapp_permissions=enforce in the
Android 10 vendor): the tablet hangs on the boot animation. Platform-signed apps are NOT exempt (the framework checks them too: the Pixel Tablet launcher re-signed with the AOSP test key still stopped system_server).
An allowlist is read from the partition of the app (a system_ext priv-app needs its entries in system_ext/etc/permissions): `--allow FILE[:PART]` and `--apk FILE[:PART]` take an optional partition
(system, system_ext, product, vendor); an apk with a partition only accepts allowlists of the same partition (untagged allowlists count for every partition).
Exit status 1 and a list of violations if any; with --write-extra out.xml the missing entries are written as an allowlist (all candidate package names).
Needs aapt2 and apksigner from the Android build-tools (BUILD_TOOLS)."""
import argparse, glob, os, re, subprocess, sys, xml.etree.ElementTree as ET
BT = os.environ.get('BUILD_TOOLS') or sorted(glob.glob(os.path.expanduser('~/Library/Android/sdk/build-tools/*')) + glob.glob(os.path.expanduser('~/Android/Sdk/build-tools/*')) + glob.glob(os.path.join(os.environ.get('ANDROID_HOME', '/nonexistent'), 'build-tools', '*')))[-1]
PLATFORM_CERT = 'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8'
ap = argparse.ArgumentParser()
ap.add_argument('--perm-apk', action='append', default=[]); ap.add_argument('--allow', action='append', default=[]); ap.add_argument('--apk', action='append', default=[]); ap.add_argument('--write-extra')
a = ap.parse_args()
aapt2 = lambda *c: subprocess.run([os.path.join(BT, 'aapt2'), *c], capture_output=True, text=True).stdout

priv = set()
for apk in a.perm_apk:
    for blk in re.split(r'\n\s*E: ', aapt2('dump', 'xmltree', '--file', 'AndroidManifest.xml', apk)):
        if not blk.startswith('permission '): continue
        n = re.search(r'android:name\(0x[0-9a-f]+\)="([^"]+)"', blk); lv = re.search(r'protectionLevel\(0x[0-9a-f]+\)=(?:\(type 0x\w+\))?0x([0-9a-f]+)', blk)
        if n and lv and int(lv.group(1), 16) & 0x10: priv.add(n.group(1))      # PROTECTION_FLAG_PRIVILEGED
allowed = {}      # (partition or None, package) -> permissions
def split(arg):
    f, _, part = arg.rpartition(':') if arg.rpartition(':')[2] in ('system', 'system_ext', 'product', 'vendor') else (arg, '', '')
    return f, (part or None)
for arg in a.allow:
    f, part = split(arg)
    try: root = ET.parse(f).getroot()
    except ET.ParseError: continue
    for pp in root.iter('privapp-permissions'):
        d = allowed.setdefault((part, pp.get('package')), set())
        for p in pp:
            if p.tag == 'permission': d.add(p.get('name'))
            if p.tag == 'deny-permission': d.discard(p.get('name'))
bad = {}
for arg in a.apk:
    apk, apart = split(arg)
    out = aapt2('dump', 'badging', apk); pkg = re.search(r"package: name='([^']+)'", out).group(1)
    tree = aapt2('dump', 'xmltree', '--file', 'AndroidManifest.xml', apk)
    names = [pkg] + re.findall(r'E: original-package[^\n]*\n\s+A: [^\n]*name\(0x[0-9a-f]+\)="([^"]+)"', tree)   # an app registers under its original-package name (Google Clock: com.android.deskclock)
    req = set(re.findall(r"uses-permission(?:-sdk-\d+)?: name='([^']+)'", out))
    # observed on the tablet: a system_ext priv-app is also granted by the system partition's lists (SystemUI's CUSTOMIZE_SYSTEM_UI), but not by product's (the launcher's 24 entries had to move to system_ext)
    PARTS = {'system_ext': ('system_ext', 'system'), 'product': ('product', 'system'), 'vendor': ('vendor',), 'system': ('system',)}
    got = lambda n: allowed.get((None, n), set()).union(*[allowed.get((pt, n), set()) for pt in PARTS.get(apart, ())]) if apart else set().union(*[v for (pt, nn), v in allowed.items() if nn == n])
    miss = sorted(p for p in req if p in priv and not all(p in got(n) for n in names))
    print(f'{pkg}: {len(req)} permissions requested, {len(miss)} privileged not allowed' + (': ' + ', '.join(miss) if miss else ''))
    if miss:
        for n in names: bad[n] = miss
if bad and a.write_extra:
    with open(a.write_extra, 'w') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<permissions>\n')
        for pkg, ps in bad.items(): f.write(f'    <privapp-permissions package="{pkg}">\n' + ''.join(f'        <permission name="{p}"/>\n' for p in ps) + '    </privapp-permissions>\n')
        f.write('</permissions>\n')
sys.exit(1 if bad else 0)
