#!/usr/bin/env python3
"""Dry-run of the boot-time privapp allowlist check, so a missing entry cannot hang the tablet on the boot animation.

usage: check_privapp.py STAGE_DIR [out.xml]     (adb root device attached; STAGE_DIR laid out like /system/product)
For every priv-app APK in STAGE_DIR: privileged permissions it requests (per `pm list permissions -f` on the device) minus what the device's
privapp-permissions*.xml files and the staged etc/permissions/*.xml allow. Prints violations; with out.xml writes a supplemental allowlist for them."""
import glob, os, re, subprocess, sys, xml.etree.ElementTree as ET
BT = os.environ.get('BUILD_TOOLS', os.path.expanduser('~/Library/Android/sdk/build-tools/35.0.0'))
ADB = os.environ.get('ADB', os.path.expanduser('~/Library/Android/sdk/platform-tools/adb'))
adb = lambda *c: subprocess.run([ADB, 'shell', *c], capture_output=True, text=True).stdout
stage = sys.argv[1]
priv = set(); cur = None
for l in adb('pm list permissions -f').splitlines():
    m = re.match(r'\+ permission:(\S+)', l)
    if m: cur = m.group(1)
    m = re.search(r'protectionLevel:(\S+)', l)
    if m and cur and 'privileged' in m.group(1) or (m and cur and 'preinstalled' in m.group(1)): priv.add(cur)
print(len(priv), 'privileged permissions on the device')
allowed = {}
def read_xml(text):
    try: root = ET.fromstring(text)
    except ET.ParseError: return
    for pp in root.iter('privapp-permissions'):
        d = allowed.setdefault(pp.get('package'), set())
        for p in pp:
            if p.tag == 'permission': d.add(p.get('name'))
            if p.tag == 'deny-permission': d.discard(p.get('name'))
for d in ('/system/etc/permissions', '/system/product/etc/permissions', '/system/system_ext/etc/permissions', '/vendor/etc/permissions'):
    for f in adb(f'ls {d}/privapp-permissions*.xml 2>/dev/null').split():
        read_xml(adb('cat', f))
for f in glob.glob(stage + '/etc/permissions/*.xml'): read_xml(open(f).read())
bad = {}
for apk in glob.glob(stage + '/priv-app/*/*.apk'):
    out = subprocess.run([os.path.join(BT, 'aapt2'), 'dump', 'badging', apk], capture_output=True, text=True).stdout
    pkg = re.search(r"package: name='([^']+)'", out).group(1)
    tree = subprocess.run([os.path.join(BT, 'aapt2'), 'dump', 'xmltree', '--file', 'AndroidManifest.xml', apk], capture_output=True, text=True).stdout
    names = [pkg] + re.findall(r'E: original-package[^\n]*\n\s+A: [^\n]*name\(0x[0-9a-f]+\)="([^"]+)"', tree)   # an app can register under an original-package name (Google Clock: com.android.deskclock)
    req = set(re.findall(r"uses-permission(?:-sdk-\d+)?: name='([^']+)'", out))
    miss = sorted(p for p in req if p in priv and not all(p in allowed.get(n, ()) for n in names))
    print(f'{pkg}: {len(req)} permissions requested, {len(miss)} privileged not allowed' + (': ' + ', '.join(miss) if miss else ''))
    if miss:
        for n in names: bad[n] = miss
if len(sys.argv) > 2 and bad:
    with open(sys.argv[2], 'w') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<permissions>\n')
        for pkg, ps in bad.items():
            f.write(f'    <privapp-permissions package="{pkg}">\n' + ''.join(f'        <permission name="{p}"/>\n' for p in ps) + '    </privapp-permissions>\n')
        f.write('</permissions>\n')
    print('wrote', sys.argv[2])
