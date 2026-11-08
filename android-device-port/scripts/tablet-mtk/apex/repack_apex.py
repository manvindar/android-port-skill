#!/usr/bin/env python3
"""Replace files inside an APEX's ext4 payload and re-sign it with our own key (apexd accepts it: the public key only has to match the
one embedded in the apex, which we replace; /system apexes are trusted as-is). Same-size replacements are written in place (keeps inode + SELinux xattr).
needs also: apksigner + a keystore (APEX_SIGN_KS, password 'android').
usage: repack_apex.py IN.apex OUT.apex KEY.pem /path/in/payload=local_file [...]
needs: e2fsprogs debugfs (E2FS env or /opt/homebrew/opt/e2fsprogs/sbin), zip/unzip, zipalign (ZIPALIGN env), avbtool.py next to this script."""
import os, re, struct, subprocess, sys, tempfile, shutil
here = os.path.dirname(os.path.abspath(__file__))
E2 = os.environ.get('E2FS', '/opt/homebrew/opt/e2fsprogs/sbin')
ZA = os.environ.get('ZIPALIGN', os.path.expanduser('~/Library/Android/sdk/build-tools/35.0.0/zipalign'))
inp, outp, key = sys.argv[1:4]
repl = dict(a.split('=', 1) for a in sys.argv[4:])
tmp = tempfile.mkdtemp()
def run(*a, **k):
    r = subprocess.run(a, capture_output=True, text=True, **k)
    if r.returncode: sys.exit('failed: %s\n%s' % (' '.join(a), r.stderr))
    return r.stdout
run('unzip', '-o', '-q', inp, '-d', tmp + '/z')
pay = tmp + '/z/apex_payload.img'
info = run('python3', '-I', here + '/avbtool.py', 'info_image', '--image', pay)
orig = int(re.search(r'Original image size:\s+(\d+)', info).group(1)); total = None
block = int(re.search(r'Data Block Size:\s+(\d+)', info).group(1)); apexkey = re.search(r"Prop: apex.key -> '([^']+)'", info).group(1)
total = (orig + orig // 64 + (1 << 20)) // block * block   # room for hashtree (1/128 of the data) + vbmeta + footer
with open(pay, 'r+b') as f: f.truncate(orig)                       # drop hashtree + vbmeta + footer
for path, local in repl.items():
    new = open(local, 'rb').read()
    st = run(E2 + '/debugfs', '-R', 'stat ' + path, pay)
    size = int(re.search(r'Size: (\d+)', st).group(1)); assert size == len(new), (path, size, len(new))
    extents = []   # (logical start, physical start, length) from "debugfs ex" leaf lines (holes are simply not listed)
    for line in run(E2 + '/debugfs', '-R', 'ex ' + path, pay).split('\n'):
        m = re.match(r'\s*(\d+)/\s*(\d+)\s+\d+/\s*\d+\s+(\d+)\s*-\s*(\d+)\s+(\d+)\s*-\s*(\d+)\s+(\d+)', line)
        if m and m.group(1) == m.group(2): extents.append((int(m.group(3)), int(m.group(5)), int(m.group(7))))
    assert extents, path
    with open(pay, 'r+b') as f:
        for lbn, pbn, n in extents:
            f.seek(pbn * block); f.write(new[lbn * block:(lbn + n) * block].ljust(n * block, b'\0'))
    blocks = extents
    print('replaced', path, len(blocks), 'blocks')
run('python3', '-I', here + '/avbtool.py', 'add_hashtree_footer', '--image', pay, '--partition_size', str(total), '--partition_name', '',
    '--do_not_generate_fec', '--algorithm', 'SHA256_RSA4096', '--key', key, '--hash_algorithm', 'sha256', '--block_size', str(block),
    '--salt', os.urandom(32).hex(), '--prop', 'apex.key:' + apexkey)
run('python3', '-I', here + '/avbtool.py', 'extract_public_key', '--key', key, '--output', tmp + '/z/apex_pubkey')
names = [n for n in run('unzip', '-Z1', inp).split('\n') if n and not n.endswith('/')]
if os.path.exists(tmp + '/o.zip'): os.remove(tmp + '/o.zip')
run('zip', '-q', '-0', '-X', tmp + '/o.zip', *names, cwd=tmp + '/z')
if os.path.exists(outp): os.remove(outp)
run(ZA, '-f', '4096', tmp + '/o.zip', tmp + '/aligned.apex')   # every stored entry (incl. apex_payload.img) page aligned
# PackageManager also verifies the apex zip as an APK (v2 signing block); sign with any key, alignment is untouched
ks = os.environ.get('APEX_SIGN_KS', os.path.expanduser('~/Aistuff/android-aosp/work/a17/apex_sign.jks'))
SIGNER = os.environ.get('APKSIGNER', os.path.expanduser('~/Library/Android/sdk/build-tools/35.0.0/apksigner'))
run(SIGNER, 'sign', '--ks', ks, '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--v1-signing-enabled', 'false',
    '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'true', '--alignment-preserved', 'true', '--out', outp, tmp + '/aligned.apex')
shutil.rmtree(tmp); print('wrote', outp, os.path.getsize(outp))
