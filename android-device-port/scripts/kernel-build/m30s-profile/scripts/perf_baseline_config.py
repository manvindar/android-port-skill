#!/usr/bin/env python3
"""Bounded performance profile on the authenticated Pixel baseline; no HDR/storage/security deltas."""
from pathlib import Path
import datetime, hashlib, json, re, sys
from label_baseline_config import BASELINE_SHA256, settings
PROFILE={
 'CONFIG_CC_OPTIMIZE_FOR_SIZE':'n','CONFIG_CC_OPTIMIZE_FOR_PERFORMANCE':'y',
 'CONFIG_CRYPTO_LZ4':'y','CONFIG_LZ4_COMPRESS':'y',
 'CONFIG_TCP_CONG_ADVANCED':'y','CONFIG_TCP_CONG_BBR':'y','CONFIG_DEFAULT_BBR':'y',
 'CONFIG_DEFAULT_CUBIC':'n','CONFIG_DEFAULT_TCP_CONG':'"bbr"',
 'CONFIG_NET_SCH_FQ':'y','CONFIG_NET_SCH_DEFAULT':'y','CONFIG_DEFAULT_FQ':'y',
 'CONFIG_DEFAULT_NET_SCH':'"fq"','CONFIG_DEFAULT_PFIFO_FAST':'n',
 'CONFIG_DEBUG_ATOMIC_SLEEP':'n','CONFIG_PM_DEBUG':'n','CONFIG_PM_SLEEP_DEBUG':'n','CONFIG_INPUT_BOOST_M30S':'y'}
# Enabling advanced TCP exposes other defaults: keep only the existing CUBIC fallback plus BBR.
for name in ['BIC','WESTWOOD','HTCP','HSTCP','HYBLA','VEGAS','NV','SCALABLE','LP','VENO','YEAH','ILLINOIS','DCTCP','CDG']:
 PROFILE['CONFIG_TCP_CONG_'+name]='n'
for name in ['BIC','HTCP','HYBLA','VEGAS','WESTWOOD','VENO','RENO','DCTCP','CDG']:
 PROFILE['CONFIG_DEFAULT_'+name]='n'
for name in ['CODEL','FQ_CODEL','SFQ']:
 PROFILE['CONFIG_DEFAULT_'+name]='n'
def profile(mode,baseline,config,date):
 datetime.datetime.strptime(date,'%Y%m%d');assert re.fullmatch(r'20\d{6}',date)
 original=Path(baseline).read_bytes();assert hashlib.sha256(original).hexdigest()==BASELINE_SHA256
 before=settings(original.decode());expected=dict(before);expected.update(PROFILE)
 expected.update(CONFIG_LOCALVERSION='"-perf-'+date+'"',CONFIG_LOCALVERSION_AUTO='n')
 if mode=='apply':
  lines=[];seen=set()
  for line in original.decode().splitlines():
   m=re.fullmatch(r'(CONFIG_\w+)=.*|# (CONFIG_\w+) is not set',line)
   if m:
    k=m[1] or m[2];seen.add(k);v=expected[k];line=('# '+k+' is not set') if v=='n' else k+'='+v
   lines.append(line)
  for k in sorted(expected.keys()-seen):
   v=expected[k];lines.append(('# '+k+' is not set') if v=='n' else k+'='+v)
  Path(config).write_text('\n'.join(lines)+'\n')
 else:assert mode=='verify'
 actual=settings(Path(config).read_text())
 diff={k:[expected.get(k,'n'),actual.get(k,'n')] for k in expected.keys()|actual.keys() if expected.get(k,'n')!=actual.get(k,'n')}
 assert not diff,'Unreviewed config delta: '+json.dumps(diff,sort_keys=True)
 deltas={k:[before.get(k,'n'),v] for k,v in expected.items() if before.get(k,'n')!=v}
 print(json.dumps({'profile':'pixel-perf-v1','kernel_release':'4.14.113-perf-'+date,'baseline_sha256':BASELINE_SHA256,'config_sha256':hashlib.sha256(Path(config).read_bytes()).hexdigest(),'config_deltas':deltas,'hdr':False,'runtime_validated':False},indent=2))
if __name__=='__main__':profile(*sys.argv[1:])
