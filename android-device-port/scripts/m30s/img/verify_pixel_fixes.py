#!/usr/bin/env python3
"""Read-only final ext4 image audit of Pixel compatibility overlays and startup helpers."""
from pathlib import Path
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/pixel'))
from verify_compat_overlays import verify
from make_compat_overlays import PLATFORM_CERT, SAFETY_CERT


def dump(image, remote, local):
    subprocess.run(['debugfs', '-R', f'dump {remote} {local}', str(image)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert local.is_file() and local.stat().st_size, ('Missing image member', remote)


def signer(apk, bt):
    text = subprocess.check_output([str(Path(bt) / 'apksigner'), 'verify', '--print-certs', str(apk)], text=True)
    hashes = re.findall(r'Signer #\d+ certificate SHA-256 digest: ([0-9a-f]+)', text)
    assert len(hashes) == 1
    return hashes[0]


def audit(image, bt, output):
    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary)
        for name in ('M30sGestureOverlay.apk', 'M30sSafetyOverlay.apk'):
            dump(image, '/system/product/overlay/' + name, tmp / name)
        receipt = verify(tmp, bt)
        dump(image, '/system/system_ext/priv-app/SystemUI/SystemUI.apk', tmp / 'SystemUI.apk')
        assert signer(tmp / 'SystemUI.apk', bt) == PLATFORM_CERT, 'SystemUI target signer mismatch'
        target_resources = subprocess.check_output([str(Path(bt) / 'aapt2'), 'dump', 'resources',
                                                    str(tmp / 'SystemUI.apk')], text=True)
        assert 'bool/config_useBackGestureML' in target_resources, 'Missing gesture target resource'
        listing = subprocess.check_output(['debugfs', '-R', 'ls -p /system/apex', str(image)], text=True,
                                          stderr=subprocess.DEVNULL)
        names = [line.split('/')[5] for line in listing.splitlines() if line.count('/') >= 6]
        module = [n for n in names if n in ('com.android.permission.capex', 'com.android.permission.apex')]
        assert len(module) == 1, ('Expected one AOSP permission module', module)
        dump(image, '/system/apex/' + module[0], tmp / 'permission.zip')
        with zipfile.ZipFile(tmp / 'permission.zip') as z:
            if 'original_apex' in z.namelist():
                with zipfile.ZipFile(io.BytesIO(z.read('original_apex'))) as inner:
                    payload = inner.read('apex_payload.img')
            else:
                payload = z.read('apex_payload.img')
        (tmp / 'payload.img').write_bytes(payload)
        app = tmp / 'apps'; app.mkdir()
        if payload[1024:1028] == bytes.fromhex('e2e1f5e0'):
            subprocess.run(['fsck.erofs', '--extract=' + str(app), str(tmp / 'payload.img')], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            for location in ('/app', '/priv-app'):
                subprocess.run(['debugfs', '-R', f'rdump {location} {app}', str(tmp / 'payload.img')], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        resources = list(app.rglob('SafetyCenterResources.apk'))
        assert len(resources) == 1, 'AOSP SafetyCenter target absent/ambiguous'
        assert signer(resources[0], bt) == SAFETY_CERT, 'SafetyCenter target signer mismatch'
        # Pin the actual API37 target whose parser/resource route was reviewed.
        assert hashlib.sha256(resources[0].read_bytes()).hexdigest() == '29e77b57cbc0214ab293dea69ca029edcbd87e4974ca56895d5d79a6be21b58e'
        scripts = {}
        for local, remote in [('scripts/nosensorhog.sh', '/system/bin/nosensorhog.sh'),
                              ('scripts/dexopt_all.sh', '/system/bin/dexopt_all.sh'),
                              ('rc/04_precompile.rc', '/system/etc/init/04_precompile.rc'),
                              ('rc/06_nosensorhog.rc', '/system/etc/init/06_nosensorhog.rc')]:
            dest = tmp / Path(remote).name
            dump(image, remote, dest)
            assert dest.read_bytes() == (ROOT / 'tools/img' / local).read_bytes(), remote
            stat = subprocess.check_output(['debugfs', '-R', 'stat ' + remote, str(image)], text=True,
                                            stderr=subprocess.DEVNULL)
            assert 'User:     0' in stat and 'Group:     0' in stat, remote
            expected_mode = '0755' if remote.endswith('.sh') else '0644'
            assert re.search(r'Mode:\s+' + expected_mode, stat), remote
            scripts[remote] = hashlib.sha256(dest.read_bytes()).hexdigest()
        receipt.update({'image': Path(image).name, 'target_signers': {'SystemUI': PLATFORM_CERT, 'SafetyCenterResources': SAFETY_CERT},
                        'startup_sha256': scripts, 'runtime_verified': False})
        Path(output).write_text(json.dumps(receipt, indent=2) + '\n')
        print('Final image compatibility components verified; Android runtime acceptance remains pending.')


if __name__ == '__main__':
    audit(*sys.argv[1:])
