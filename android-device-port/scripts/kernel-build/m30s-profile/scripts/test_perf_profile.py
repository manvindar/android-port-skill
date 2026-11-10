from pathlib import Path
import subprocess, sys, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
class ProfileTests(unittest.TestCase):
 def run_profile(self,mode,path):
  return subprocess.run([sys.executable,str(ROOT/'scripts/perf_baseline_config.py'),mode,str(ROOT/'config/baseline-a17.config'),str(path),'20261110'],capture_output=True,text=True)
 def test_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config';r=self.run_profile('apply',p);self.assertEqual(r.returncode,0,r.stderr)
   r=self.run_profile('verify',p);self.assertEqual(r.returncode,0,r.stderr)
 def test_unrelated_changes_rejected(self):
  for old,new in [('CONFIG_MODVERSIONS=y','# CONFIG_MODVERSIONS is not set'),('# CONFIG_SCSI_MQ_DEFAULT is not set','CONFIG_SCSI_MQ_DEFAULT=y'),('CONFIG_DEFAULT_TCP_CONG="bbr"','CONFIG_DEFAULT_TCP_CONG="cubic"'),('# CONFIG_PM_SLEEP_DEBUG is not set','CONFIG_PM_SLEEP_DEBUG=y')]:
   with self.subTest(old=old), tempfile.TemporaryDirectory() as d:
    p=Path(d)/'config';r=self.run_profile('apply',p);self.assertEqual(r.returncode,0,r.stderr)
    self.assertIn(old,p.read_text());p.write_text(p.read_text().replace(old,new));self.assertNotEqual(self.run_profile('verify',p).returncode,0)
 def test_unknown_active_symbol_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config';r=self.run_profile('apply',p);self.assertEqual(r.returncode,0,r.stderr)
   p.write_text(p.read_text()+'\nCONFIG_UNREVIEWED_HDR=y\n');self.assertNotEqual(self.run_profile('verify',p).returncode,0)
if __name__=='__main__':unittest.main()
