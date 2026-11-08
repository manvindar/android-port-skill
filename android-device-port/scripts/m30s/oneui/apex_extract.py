#!/usr/bin/env python3
"""apex_extract.py SYSTEM.erofs APEX_PATH OUT_DIR [INNER_PREFIX ...]: copy files out of the payload of an apex/capex stored in the donor image.
The payload (apex_payload.img) is EROFS or ext4 depending on the apex; both are handled (ext4 through debugfs rdump). Without INNER_PREFIX the whole payload is extracted."""
import io, os, shutil, stat, subprocess, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erofs import Erofs
E2 = '/opt/homebrew/opt/e2fsprogs/sbin'
img, apex, out = sys.argv[1:4]; prefixes = sys.argv[4:]
E = Erofs(img)
node = next(i for p, i in E.walk(skip=lambda p: not apex.startswith(p.rstrip('/') + '/') and p != apex) if p == apex)
z = zipfile.ZipFile(io.BytesIO(E.read(node)))
if 'original_apex' in z.namelist(): z = zipfile.ZipFile(io.BytesIO(z.read('original_apex')))
tmp = tempfile.mkdtemp(); pl = os.path.join(tmp, 'payload.img'); open(pl, 'wb').write(z.read('apex_payload.img'))
os.makedirs(out, exist_ok=True)
if open(pl, 'rb').read(2048)[1024:1028] == bytes.fromhex('e2e1f5e0'):          # EROFS magic at 1024
    P = Erofs(pl)
    for p, i in P.walk():
        if prefixes and not any(p.startswith(x) for x in prefixes): continue
        d = os.path.join(out, p.lstrip('/'))
        if stat.S_ISDIR(i.mode): os.makedirs(d, exist_ok=True)
        elif stat.S_ISREG(i.mode): os.makedirs(os.path.dirname(d), exist_ok=True); open(d, 'wb').write(P.read(i))
    print('erofs payload')
else:
    for x in prefixes or ['/']:
        subprocess.run([f'{E2}/debugfs', '-R', f'rdump {x} {out}', pl], capture_output=True)
    print('ext4 payload')
shutil.rmtree(tmp)
