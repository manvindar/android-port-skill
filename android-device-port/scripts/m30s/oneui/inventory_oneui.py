#!/usr/bin/env python3
"""Inventory of an extracted One UI donor (tools/oneui/unpack_donor.py output): every APK of every partition with package, versionCode, sharedUserId, minSdk, required <uses-library>
(checked against the shared libraries the donor declares in etc/permissions/*.xml and the jars that exist), native ABIs, signer SHA-256 and size. Writes OUT/inventory.json and prints a summary
of what cannot work on the AOSP GSI framework (required Samsung libraries missing there = PackageManager refuses to install the app).
usage: inventory_oneui.py TREE_DIR OUT_JSON [--gsi-libs FILE] [--build-tools DIR] [--jobs N]
  --gsi-libs: text file, one shared-library name per line, taken from the GSI's /system/etc/permissions + /system_ext/etc/permissions (default: only the AOSP names the script knows)"""
import argparse, glob, json, os, re, subprocess, sys, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
ap = argparse.ArgumentParser(); ap.add_argument('tree'); ap.add_argument('out'); ap.add_argument('--gsi-libs'); ap.add_argument('--build-tools'); ap.add_argument('--jobs', type=int, default=8)
a = ap.parse_args()
BT = a.build_tools or sorted(glob.glob(os.path.expanduser('~/Library/Android/sdk/build-tools/*')))[-1]
AOSP_LIBS = {'android.test.base', 'android.test.mock', 'android.test.runner', 'org.apache.http.legacy', 'android.hidl.base-V1.0-java', 'android.hidl.manager-V1.0-java', 'com.android.location.provider',
             'com.android.media.remotedisplay', 'com.android.mediadrm.signer', 'com.android.nfc_extras', 'android.ext.shared', 'androidx.window.extensions', 'androidx.window.sidecar', 'javax.obex',
             'org.apache.http.legacy', 'android.net.ipsec.ike', 'com.android.future.usb.accessory', 'com.android.cts.ctsshim', 'android.car-system-stubs', 'com.google.android.maps', 'com.google.android.media.effects'}
gsi_libs = set(AOSP_LIBS)
if a.gsi_libs: gsi_libs |= {l.strip() for l in open(a.gsi_libs) if l.strip()}
parts = sorted(d for d in os.listdir(a.tree) if os.path.isdir(os.path.join(a.tree, d)))
donor_libs = {}                                            # library name -> jar path, from <library name= file=> in the donor's permission xmls
for p in parts:
    for x in glob.glob(os.path.join(a.tree, p, 'etc/permissions/*.xml')) + glob.glob(os.path.join(a.tree, p, 'etc/sysconfig/*.xml')):
        try: root = ET.parse(x).getroot()
        except ET.ParseError: continue
        for l in root.iter('library'): donor_libs[l.get('name')] = l.get('file')
def aapt(apk):
    r = subprocess.run([os.path.join(BT, 'aapt2'), 'dump', 'badging', apk], capture_output=True, text=True); t = r.stdout; g = lambda rx: (re.search(rx, t) or [None, None])[1]
    return dict(package=g(r"package: name='([^']+)'"), versionCode=g(r"versionCode='(\d+)'"), sharedUserId=g(r"sharedUserId='([^']+)'"), minSdk=g(r"sdkVersion:'(\d+)'"), targetSdk=g(r"targetSdkVersion:'(\d+)'"),
                libs=re.findall(r"^uses-library:'([^']+)'", t, re.M), libs_optional=re.findall(r"^uses-library-not-required:'([^']+)'", t, re.M),
                abis=sorted(set(re.findall(r"'(arm64-v8a|armeabi-v7a|x86_64|x86)'", g(r'native-code: (.*)') or ''))), ok=r.returncode == 0)
def signer(apk):
    r = subprocess.run(['java', '-jar', os.path.join(BT, 'lib/apksigner.jar'), 'verify', '--print-certs', apk], capture_output=True, text=True)
    return (re.search(r'certificate SHA-256 digest: (\w+)', r.stdout) or [None, None])[1]
def one(item):
    part, path = item; d = aapt(path); d.update(part=part, path=os.path.relpath(path, os.path.join(a.tree, part)), size=os.path.getsize(path), signer=signer(path)); return d
items = [(p, f) for p in parts for f in glob.glob(os.path.join(a.tree, p, '**', '*.apk'), recursive=True) if not os.path.islink(f)]
print(len(items), 'apks in', parts)
with ThreadPoolExecutor(a.jobs) as ex: rows = list(ex.map(one, items))
for r in rows:
    r['missing_libs'] = sorted(l for l in r['libs'] if l not in gsi_libs)
json.dump(dict(partitions=parts, donor_libs=donor_libs, apks=rows), open(a.out, 'w'), indent=1)
by = {}
for r in rows: by.setdefault(r['part'], []).append(r)
for p, rs in sorted(by.items()):
    bad = [r for r in rs if r['missing_libs']]; su = [r for r in rs if r['sharedUserId'] == 'android.uid.system']
    print(f'{p:12} {len(rs):4} apks {sum(r["size"] for r in rs) >> 20:5} MiB | {len(bad)} need a library the GSI lacks | {len(su)} are android.uid.system | signers {len({r["signer"] for r in rs})}')
