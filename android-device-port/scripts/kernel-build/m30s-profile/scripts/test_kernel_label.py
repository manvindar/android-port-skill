"""The label must not weaken module validation or alter any functional setting."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/label_baseline_config.py'
BASELINE = ROOT / 'config/baseline-a17.config'


class KernelLabelTests(unittest.TestCase):
    def run_script(self, mode, config, date='20261110'):
        self.assertTrue(SCRIPT.is_file(), 'Reviewed-baseline labeling is not implemented')
        return subprocess.run([sys.executable, str(SCRIPT), mode, str(BASELINE), str(config), date],
                              capture_output=True, text=True)

    def test_actual_baseline_label_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config'
            result = self.run_script('apply', config)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('CONFIG_LOCALVERSION="-perf-20261110"', config.read_text())
            self.assertIn('# CONFIG_LOCALVERSION_AUTO is not set', config.read_text())
            result = self.run_script('verify', config)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_disabling_module_version_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config'
            self.assertEqual(self.run_script('apply', config).returncode, 0)
            config.write_text(config.read_text().replace('CONFIG_MODVERSIONS=y', '# CONFIG_MODVERSIONS is not set'))
            result = self.run_script('verify', config)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('CONFIG_MODVERSIONS', result.stderr)

    def test_invalid_calendar_date_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config'
            result = self.run_script('apply', config, '20261310')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(config.exists())


if __name__ == '__main__':
    unittest.main()
