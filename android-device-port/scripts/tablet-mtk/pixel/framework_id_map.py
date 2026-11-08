#!/usr/bin/env python3
"""Map framework resource ids between two builds of framework-res.apk by resource name.

usage: framework_id_map.py DEVICE_FRAMEWORK_RES.apk APP_BUILD_FRAMEWORK_RES.apk OUT.json
OUT.json: {"map": {"0xNEW": "0xOLD", ...}  (ids the app was built with -> ids of the device, only where they differ),
           "missing": {"0xNEW": "type/name", ...}  (exist only in the app's framework: no device id),
           "public_moved": n}
Non-public (private and staging) resources are numbered alphabetically inside each type, so one added resource shifts every id after it.
Needs aapt2 (env BUILD_TOOLS or ANDROID_HOME)."""
import glob, json, os, re, subprocess, sys

def aapt2():
    bt = os.environ.get('BUILD_TOOLS') or sorted(glob.glob(os.path.expanduser('~/Library/Android/sdk/build-tools/*')))[-1]
    return os.path.join(bt, 'aapt2')

def table(apk):
    out = subprocess.run([aapt2(), 'dump', 'resources', apk], capture_output=True, text=True, errors='replace', check=True).stdout
    return {(m.group(2), m.group(3)): (int(m.group(1), 16), bool(m.group(4)))
            for m in re.finditer(r'^\s+resource (0x[0-9a-f]{8}) (\w+)/(\S+)( PUBLIC)?', out, re.M)}

def build_map(dev_apk, app_apk):
    dev, app = table(dev_apk), table(app_apk)
    mp, missing, pub = {}, {}, 0
    for k, (i, public) in app.items():
        if k not in dev: missing[i] = '%s/%s' % k
        elif dev[k][0] != i:
            mp[i] = dev[k][0]; pub += public
    return mp, missing, pub, len(dev), len(app)

if __name__ == '__main__':
    mp, missing, pub, nd, na = build_map(sys.argv[1], sys.argv[2])
    json.dump({'map': {hex(k): hex(v) for k, v in mp.items()}, 'missing': {hex(k): v for k, v in missing.items()}, 'public_moved': pub}, open(sys.argv[3], 'w'))
    print(f'device {nd} resources, app framework {na}: {len(mp)} ids differ ({pub} public), {len(missing)} only in the app framework')
