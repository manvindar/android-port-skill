#!/usr/bin/env python3
"""Verify signed compiled resource scope, not Android idmap or runtime admission."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from make_compat_overlays import PLATFORM_CERT, SAFETY_CERT

HERE = Path(__file__).resolve().parent
CERTS = {
    'M30sGestureOverlay.apk': ('org.m30s.overlay.systemui.gesture', 'com.android.systemui', PLATFORM_CERT),
    'M30sSafetyOverlay.apk': ('com.m30s.safetycenter.compat', 'com.android.safetycenter.resources', SAFETY_CERT),
}


def verify(directory, bt):
    records = {}
    for name, (package, target, cert) in CERTS.items():
        apk = Path(directory) / name
        result = subprocess.check_output([str(Path(bt) / 'apksigner'), 'verify', '--verbose',
                                          '--print-certs', str(apk)], text=True)
        got = re.findall(r'Signer #\d+ certificate SHA-256 digest: ([0-9a-f]+)', result)
        assert got == [cert], (name, 'APK signer mismatch')
        manifest = subprocess.check_output([str(Path(bt) / 'aapt2'), 'dump', 'xmltree',
                                             '--file', 'AndroidManifest.xml', str(apk)], text=True)
        assert f'="{package}"' in manifest and f'="{target}"' in manifest, name
        assert re.search(r':hasCode\([^)]*\)=false', manifest), name
        assert re.search(r':isStatic\([^)]*\)=true', manifest), name
        assert re.search(r':minSdkVersion\([^)]*\)=37\b', manifest), name
        assert re.search(r':targetSdkVersion\([^)]*\)=37\b', manifest), name
        assert not any('E: ' + tag in manifest for tag in
                       ('uses-permission', 'activity', 'service', 'receiver', 'provider')), name
        resources = subprocess.check_output([str(Path(bt) / 'aapt2'), 'dump', 'resources', str(apk)], text=True)
        types = re.findall(r'^\s*resource \S+ (\S+)', resources, re.M)
        resource_ids = {name: ident for ident, name in
                        re.findall(r'^\s*resource (0x[0-9a-f]+) (\S+)', resources, re.M)}
        with zipfile.ZipFile(apk) as z:
            entries = z.namelist()
            assert not any(n.endswith('.dex') or n.startswith('lib/') or n.endswith('.json') for n in entries), name
            assert all(n in ('AndroidManifest.xml', 'resources.arsc') or n.startswith(('res/', 'META-INF/')) for n in entries), name
            if name == 'M30sGestureOverlay.apk':
                assert types == ['bool/config_useBackGestureML'], types
                assert 'false' in resources and 'true' not in resources, name
            else:
                assert set(types) == {'raw/safety_center_config', 'xml/overlays',
                                      'string/google_advanced_protection_title',
                                      'string/google_advanced_protection_summary'}, types
                raw = z.read('res/raw-v37/safety_center_config.xml')
                assert raw == (HERE / 'overlay-m30s-safety/res/raw-v37/safety_center_config.xml').read_bytes()
                config = ET.fromstring(raw)
                for ident in ('AdvancedProtection', 'AdvancedProtectionIssueSource'):
                    node = next(n for n in config.iter() if n.attrib.get('id') == ident)
                    assert node.attrib['packageName'] == 'com.google.android.gms'
                    assert len(node.attrib['packageCertificateHashes'].split(',')) == 6
                assert '@com.m30s.safetycenter.compat:string/google_advanced_protection_title' in raw.decode()
                assert 'Advanced Protection' in resources
                expected_strings = Counter(
                    n.text[1:-1].replace('\\"', '"').replace('\\\\', '\\')
                    for p in (HERE / 'overlay-m30s-safety/res').glob('values*/strings.xml')
                    for n in ET.parse(p).getroot())
                compiled_strings = Counter(re.findall(r'^\s+\([^)]*\) "(.*)"$', resources, re.M))
                assert compiled_strings == expected_strings, 'Compiled localized strings differ from reviewed source'
                mapping = subprocess.check_output([str(Path(bt) / 'aapt2'), 'dump', 'xmltree',
                                                    '--file', 'res/xml/overlays.xml', str(apk)], text=True)
                assert '="raw/safety_center_config"' in mapping, mapping
                assert mapping.count('E: item') == 1 and 'value' in mapping, mapping
                assert re.search(r':resourcesMap\([^)]*\)=@' + resource_ids['xml/overlays'] + r'\b', manifest)
                assert re.search(r'A: value=@' + resource_ids['raw/safety_center_config'] + r'\b', mapping)
                qualified_expected = {}
                for p in (HERE / 'overlay-m30s-safety/res').glob('values*/strings.xml'):
                    qualifier = p.parent.name[7:]
                    api = re.search(r'(?:^|-)v(\d+)$', qualifier)
                    assert api and int(api[1]) <= 37
                    qualifier = re.sub(r'-?v\d+$', '', qualifier)
                    for node in ET.parse(p).getroot():
                        qualified_expected[('string/' + node.attrib['name'], qualifier)] = node.text[1:-1].replace('\\"', '"').replace('\\\\', '\\')
                qualified_actual = {}; current = None
                for line in resources.splitlines():
                    entry = re.match(r'\s*resource \S+ (\S+)', line)
                    if entry: current = entry[1]
                    value = re.match(r'\s+\(([^)]*)\) "(.*)"$', line)
                    if value: qualified_actual[(current, value[1])] = value[2]
                assert qualified_actual == qualified_expected, 'Compiled locale qualifier/value binding differs'
        records[name] = {'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
                         'bytes': apk.stat().st_size, 'package': package, 'target': target,
                         'signer_sha256': cert, 'resource_names': types}
    receipt = {'scope': 'Compiled APK signer/manifest/resource-map checks only; no Android idmap/runtime proof',
               'overlays': records}
    (Path(directory) / 'compat-overlays-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == '__main__':
    verify(*sys.argv[1:])
