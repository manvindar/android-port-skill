"""Actual Android SDK packaging checks; requires public test keys, never a phone."""
import os
from pathlib import Path
import subprocess
import shutil
import re
import xml.etree.ElementTree as ET
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class PackagingTests(unittest.TestCase):
    def test_original_safety_config_and_six_certificate_constraints_preserved(self):
        raw = (HERE / 'overlay-m30s-safety/res/raw-v37/safety_center_config.xml').read_text()
        old = (HERE / 'testdata/aosp-safety-config-v37.xml').read_text()
        dynamic = re.search(r'            <dynamic-safety-source\s+id="AdvancedProtection".*?/>\n', raw, re.S)
        group = re.search(r'        <safety-sources-group\s+id="AdvancedProtectionIssuesSources".*?</safety-sources-group>\n', raw, re.S)
        self.assertIsNotNone(dynamic); self.assertIsNotNone(group)
        self.assertEqual(raw.replace(dynamic.group(), '').replace(group.group(), ''), old)
        allowed = {'f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83',
                   '5f2391277b1dbd489000467e4c2fa6af802430080457dce2f618992e9dfb5402'}
        for node in ET.fromstring(raw).iter():
            if node.attrib.get('id') in ('AdvancedProtection', 'AdvancedProtectionIssueSource'):
                certs = set(node.attrib['packageCertificateHashes'].split(','))
                self.assertEqual(len(certs), 6)
                self.assertTrue(allowed <= certs)

    def test_compile_sign_and_resource_closure(self):
        if not (HERE / 'make_compat_overlays.py').is_file():
            self.fail('Compatibility overlay packaging has not been integrated')
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(HERE / 'make_compat_overlays.py'),
                            tmp, os.environ['PLATFORM_KEYS'], os.environ['SAFETY_KEYS'],
                            os.environ['BT'], os.environ['PLATFORM_JAR']], check=True)
            subprocess.run([sys.executable, str(HERE / 'verify_compat_overlays.py'),
                            tmp, os.environ['BT']], check=True)

    def test_wrong_safety_signer_is_rejected_without_output(self):
        if not (HERE / 'make_compat_overlays.py').is_file():
            self.fail('Compatibility overlay packaging has not been integrated')
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / 'wrong'; wrong.mkdir()
            for ext in ('pk8', 'x509.pem'):
                shutil.copyfile(Path(os.environ['PLATFORM_KEYS']) / ('platform.' + ext),
                                wrong / ('com.android.safetycenter.resources.' + ext))
            result = subprocess.run([sys.executable, str(HERE / 'make_compat_overlays.py'),
                                     tmp, os.environ['PLATFORM_KEYS'], str(wrong),
                                     os.environ['BT'], os.environ['PLATFORM_JAR']], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'safety certificate mismatch', result.stderr)
            self.assertFalse(list(Path(tmp).glob('*.apk')))


if __name__ == '__main__':
    unittest.main()
