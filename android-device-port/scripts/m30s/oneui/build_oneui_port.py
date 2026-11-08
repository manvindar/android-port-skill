#!/usr/bin/env python3
"""One UI 9 (A266BXXUCDZJ6 donor) -> Galaxy M30s (SM-M307F) system image: apply the changes the Android 11 vendor and the 4.14 kernel need to the ext4 made by erofs2ext4.py.
usage: build_oneui_port.py --base system-oneui9.img --out system-oneui9-port.img --a14fs DIR --vndk-dir DIR [--tools TB_TOOLS] [--build-tools BT]
Everything is debugfs on an image copy (macOS or Linux, no mount). Each step is a fix for a failure seen on the Pixel A17 image of this repo or a gap listed in docs/oneui9/M2-GAPS.md; steps that need a
phone log to be proven are marked UNPROVEN. Same vendor as the Pixel image (vendor-a17.img from tools/img/build_vendor_a17.py).
  1  init: boot SELinux permissive (pattern patch, the kernel a17 supports permissive)
  2  build.prop: debuggable (adb), egl, timeouts
  3  /init = launcher of Android 14's first stage (the phone's boot.img has no ramdisk, A17 init is second-stage only), 03_zram.rc
  4  VNDK v30 apex + sepolicy mapping 30.0 + cgroups.json (from the Android 14 GSI; the donor only has vndk v33)
  5  bionic: libc/linkers (clone3 stub, MADV_WIPEONFORK) in /system and inside the runtime apex; libbinder, libmeminfo, libprocessgroup_setup, libui gralloc gate
  6  bpf: netbpfload with the kernel-version gates removed, bind-mounted over the apex copy (00_bpf_bind.rc); reboot_on_failure dropped
Tools of the tablet repo (A17_TOOLS, default ~/Aistuff/tb-x606v-android17/tools) are used for the pattern patches that already work on Samsung's binaries."""
import argparse, glob, json, os, re, shutil, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); IMGRC = os.path.join(HERE, '..', 'img', 'rc')
ap = argparse.ArgumentParser()
ap.add_argument('--base', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--a14fs', required=True); ap.add_argument('--vndk-dir', required=True)
ap.add_argument('--tools', default=os.environ.get('A17_TOOLS') or os.path.expanduser('~/Aistuff/tb-x606v-android17/tools'))
ap.add_argument('--port-repo', default=os.path.expanduser('~/Aistuff/tb-x606v-android16-port'), help='repo with debug/bootdiag.sh + zz_bootdiag.rc (boot logs into /data/local/tmp/bootdiag)')
ap.add_argument('--audio-closure', help='dir from tools/audio/a16_closure.py (Android 16 audioserver + libs, public LineageOS 23.2 GSI): audio for the vendor HIDL audio 5.0'); ap.add_argument('--capstone-python', default=os.path.expanduser('~/Aistuff/android-aosp/work/venv/bin/python'), help='python with capstone (audio AIDL patches)')
ap.add_argument('--google-stage', help='dir from tools/oneui/stage_google.py (WebView + Play services/Store/GSF, public sources): product/ goes under /product, system_ext/ under /system/system_ext'); ap.add_argument('--fphal', action='store_true', help='fingerprint AIDL shim over the vendor HIDL 2.1 (tools/fphal, builds the jar: needs a JDK 17 `javac` on PATH)'); ap.add_argument('--build-tools'); ap.add_argument('--e2fs', default='/opt/homebrew/opt/e2fsprogs/sbin')
a = ap.parse_args()
E2, TOOLS = a.e2fs, a.tools
def bt_dir():
    if a.build_tools: return a.build_tools
    for sdk in (os.environ.get('ANDROID_HOME'), os.path.expanduser('~/Library/Android/sdk'), os.path.expanduser('~/Android/Sdk')):
        c = sorted(glob.glob(os.path.join(sdk or '/nonexistent', 'build-tools', '*')), key=lambda p: [int(x) for x in re.findall(r'\d+', os.path.basename(p))])
        if c: return c[-1]
    sys.exit('Android SDK build-tools not found (zipalign, apksigner): --build-tools')
BT = bt_dir()
W = tempfile.mkdtemp(prefix='oneuiport')
def wp(n): return os.path.join(W, n)
def tmpf(name, data): open(wp(name), 'wb' if isinstance(data, bytes) else 'w').write(data); return wp(name)
def run(*c, ok=(0,), env=None):
    r = subprocess.run(c, capture_output=True, text=True, env=env)
    if r.returncode not in ok: sys.exit(f'{c[0]} failed ({r.returncode}): {" ".join(map(str, c))[:300]}\n{r.stdout[-1500:]}{r.stderr[-1500:]}')
    return r.stdout
def py(script, *args, env=None):
    p = script if os.path.isabs(script) else os.path.join(TOOLS, script)
    return run(sys.executable, '-I', p, *map(str, args), env=env)
def dbg(*c): return subprocess.run([os.path.join(E2, 'debugfs'), '-R', ' '.join(c), a.out], capture_output=True)
def cat(path):
    r = dbg('cat', path).stdout
    if not r: sys.exit(f'{path} not in the image')
    return r
def exists(path): return b'Inode:' in dbg('stat', path).stdout
def attrs(path):
    st = dbg('stat', path).stdout.decode('latin1')
    m = re.search(r'Mode:\s+0?(\d+)', st); u = re.search(r'User:\s+(\d+)\s+Group:\s+(\d+)', st)
    lbl = dbg('ea_get', '-V', path, 'security.selinux').stdout.decode('latin1').split('\n')[0].split('\0')[0].strip()
    assert m and u and lbl, f'cannot read attributes of {path}'
    return m.group(1)[-3:], int(u.group(1)), int(u.group(2)), lbl

cmds = []; lbl = {}
SYS = 'u:object_r:system_file:s0'; LIB = 'u:object_r:system_lib_file:s0'
def label_file(ctx):
    if ctx not in lbl: lbl[ctx] = tmpf('label%d' % len(lbl), ctx.encode() + b'\0')
    return lbl[ctx]
def put(src, dst, mode, uid=0, gid=0, ctx=SYS):
    cmds.extend([f'rm {dst}', f'write {src} {dst}', f'set_inode_field {dst} mode 0100{mode}', f'set_inode_field {dst} uid {uid}', f'set_inode_field {dst} gid {gid}', f'ea_set -f {label_file(ctx)} {dst} security.selinux'])
def replace(dst, src):
    m, u, g, c = attrs(dst); put(src, dst, m, u, g, c)
def mkdir(path, mode='755', ctx=SYS):
    cmds.extend([f'mkdir {path}', f'set_inode_field {path} mode 040{mode}', f'set_inode_field {path} uid 0', f'set_inode_field {path} gid 0', f'ea_set -f {label_file(ctx)} {path} security.selinux'])
def symlink(path, target, ctx=LIB): cmds.extend([f'rm {path}', f'symlink {path} {target}', f'ea_set -f {label_file(ctx)} {path} security.selinux'])
def apply():
    global cmds
    f = tmpf('cmds', '\n'.join(cmds) + '\n'); cmds = []
    out = subprocess.run([os.path.join(E2, 'debugfs'), '-w', '-f', f, a.out], capture_output=True, text=True)
    bad = [l for l in (out.stdout + out.stderr).split('\n') if re.search(r'(?i)(error|not found|no such|not enough|no space)', l) and not l.startswith('debugfs: rm ') and 'File not found by ext2_lookup' not in l]
    if bad: sys.exit('debugfs reported:\n' + '\n'.join(bad[:20]))
    run(os.path.join(E2, 'e2fsck'), '-fn', a.out)
def apex_member(apex, inner, dst):
    d = wp('apx'); os.makedirs(d, exist_ok=True)
    open(d + '/a.zip', 'wb').write(cat(apex)); import zipfile; z = zipfile.ZipFile(d + '/a.zip')
    if 'original_apex' in z.namelist(): open(d + '/o.zip', 'wb').write(z.read('original_apex')); z = zipfile.ZipFile(d + '/o.zip')
    open(d + '/payload.img', 'wb').write(z.read('apex_payload.img'))
    subprocess.run([os.path.join(E2, 'debugfs'), '-R', f'dump {inner} {dst}', d + '/payload.img'], capture_output=True)
    assert os.path.exists(dst) and os.path.getsize(dst) > 0, f'{inner} not in {apex}'
def patched(tool, path, name):
    src = tmpf(name + '.orig', cat(path)); out = wp(name + '.p'); py(tool, src, out); return out

print('0 image copy')
if os.path.exists(a.out): os.remove(a.out)
if subprocess.run(['cp', '-c', a.base, a.out], capture_output=True).returncode: shutil.copyfile(a.base, a.out)

print('1 init permissive')
init = cat('/system/bin/init'); d = bytearray(init)
hits = [x for x in range(0, len(d) - 16, 4) if struct.unpack_from('<I', d, x)[0] == 0x7100041f and (struct.unpack_from('<I', d, x + 4)[0] & 0xff00001f) == 0x54000000
        and struct.unpack_from('<I', d, x + 8)[0] == 0x52800020 and struct.unpack_from('<I', d, x + 12)[0] >> 26 == 0x25]
assert len(hits) == 1, ('init: enforce check not found or ambiguous', hits)
o = hits[0] + 4
struct.pack_into('<I', d, o, struct.unpack_from('<I', d, o)[0] | 1); struct.pack_into('<I', d, o + 4, 0x52800000)   # b.eq skip -> b.ne skip ; mov w0,#0 : setenforce(0) when the kernel is enforcing
m, u, g, c = attrs('/system/bin/init'); put(tmpf('init.orig', init), '/system/bin/init.enforcing', m, u, g, c); replace('/system/bin/init', tmpf('init.p', bytes(d)))

print('2 build.prop')
bp = cat('/system/build.prop').decode()
for x, y in (('ro.secure=1', 'ro.secure=0'), ('ro.debuggable=0', 'ro.debuggable=1'), ('ro.force.debuggable=0', 'ro.force.debuggable=1'), ('ro.adb.secure=1', 'ro.adb.secure=0')):
    assert x in bp, x; bp = bp.replace(x, y)
bp += '\npersist.sys.usb.config=adb\nro.hw_timeout_multiplier=5\nro.hardware.egl=mali\npm.dexopt.install=speed\npm.dexopt.install-bulk=speed\npersist.traced.enable=0\n'
replace('/system/build.prop', tmpf('build.prop', bp))

print('3 first stage launcher, zram')
mkdir('/system/a14fs'); mkdir('/system/a14fs/lib64')
for f in ('init', 'linker64', 'launcher'): put(os.path.join(a.a14fs, f), '/system/a14fs/' + f, '755')
for f in sorted(os.listdir(os.path.join(a.a14fs, 'lib64'))): put(os.path.join(a.a14fs, 'lib64', f), '/system/a14fs/lib64/' + f, '644')
symlink('/init', '/system/a14fs/launcher', 'u:object_r:rootfs:s0')
put(os.path.join(IMGRC, '03_zram.rc'), '/system/etc/init/03_zram.rc', '644')
put(os.path.join(a.port_repo, 'debug', 'bootdiag.sh'), '/system/bin/bootdiag.sh', '755')       # boot logs for the first boots; the 'su' domain is not in the policy
put(tmpf('zz_bootdiag.rc', open(os.path.join(a.port_repo, 'debug', 'zz_bootdiag.rc')).read().replace('u:r:su:s0', 'u:r:init:s0')), '/system/etc/init/zz_bootdiag.rc', '644')

print('4 vndk 30, selinux mapping 30.0, cgroups')
vndk = open(os.path.join(a.vndk_dir, 'com.android.vndk.v30.apex'), 'rb').read(); assert len(vndk) > 50_000_000
put(tmpf('vndk30.apex', vndk), '/system/system_ext/apex/com.android.vndk.v30.apex', '644')
symlink('/system/lib64/vndk-sp-30', '/apex/com.android.vndk.v30/lib64'); symlink('/system/lib/vndk-sp-30', '/apex/com.android.vndk.v30/lib')
defined = set()
for p in ('/system/etc/selinux/plat_sepolicy.cil', '/system/system_ext/etc/selinux/system_ext_sepolicy.cil', '/system/product/etc/selinux/product_sepolicy.cil'):
    if exists(p): defined |= set(re.findall(r'\((?:type|typeattribute|typealias) ([A-Za-z0-9_.]+)\)', cat(p).decode('latin1')))
assert len(defined) > 1000, 'sepolicy cil not found: ' + str(len(defined))
KW = {'and', 'or', 'not', 'xor', 'all'}
def prune(text):
    out, dropped, stripped = [], 0, 0
    for l in text.split('\n'):
        mm = re.match(r'^\(typeattributeset (\S+) \((.*)\)\)\s*$', l)
        if mm and not re.search(r'\((and|or|not|xor)\b', mm.group(2)):
            toks = mm.group(2).split(); keep = [t for t in toks if t in defined or t in KW]
            if not keep: dropped += 1; continue
            if len(keep) != len(toks): stripped += 1; l = '(typeattributeset %s (%s))' % (mm.group(1), ' '.join(keep))
        out.append(l)
    print(f'  mapping 30.0: {stripped} statements pruned, {dropped} dropped'); return '\n'.join(out)
put(tmpf('map30.cil', prune(open(os.path.join(a.vndk_dir, '30.0.cil'), encoding='latin1').read())), '/system/etc/selinux/mapping/30.0.cil', '644')
put(os.path.join(a.vndk_dir, '30.0.compat.cil'), '/system/etc/selinux/mapping/30.0.compat.cil', '644')
for p in ('/system/system_ext/etc/selinux/mapping/30.0.cil', '/system/system_ext/etc/selinux/mapping/30.0.compat.cil', '/system/product/etc/selinux/mapping/30.0.cil'):
    put(tmpf('empty', ''), p, '644')
cg = json.loads(cat('/system/etc/cgroups.json'))
cg['Cgroups'] = [x for x in cg['Cgroups'] if x['Controller'] != 'blkio']
for x in cg.get('Cgroups2', {}).get('Controllers', []):
    if x['Controller'] == 'freezer': x['Optional'] = True
replace('/system/etc/cgroups.json', tmpf('cgroups.json', json.dumps(cg, indent=2)))
# the donor's system_ext policy declares typealiases that the stock vendor policy declares too: secilc (init's compile) fails on the re-declaration (tools/oneui/sepol_check.py)
sx = cat('/system/system_ext/etc/selinux/system_ext_sepolicy.cil').decode('latin1')
for n in ('felicalock', 'felica', 'mfw', 'mfs', 'mfm', 'mfc'): sx, k = re.subn(r'(?m)^\(typealias %s\)\n\(typealiasactual %s \S+\)\n' % (n, n), '', sx); assert k == 1, n
replace('/system/system_ext/etc/selinux/system_ext_sepolicy.cil', tmpf('sext.cil', sx.encode('latin1')))
apply()      # directories and symlinks must exist before the apex edits below read them back

print('5 bionic and friends')
libc64 = patched('libc/patch_libc.py', '/system/lib64/bootstrap/libc.so', 'libc64'); libc32 = patched('libc/patch_libc.py', '/system/lib/bootstrap/libc.so', 'libc32')
ld64 = patched('libc/patch_libc.py', '/system/bin/bootstrap/linker64', 'linker64'); ld32 = patched('libc/patch_libc.py', '/system/bin/bootstrap/linker', 'linker32')
for path, f in (('/system/lib64/bootstrap/libc.so', libc64), ('/system/lib/bootstrap/libc.so', libc32), ('/system/bin/bootstrap/linker64', ld64), ('/system/bin/bootstrap/linker', ld32),
                ('/system/lib64/libui.so', patched(os.path.join(HERE, 'patch_libui_gate.py'), '/system/lib64/libui.so', 'ui64')), ('/system/lib/libui.so', patched(os.path.join(HERE, 'patch_libui_gate.py'), '/system/lib/libui.so', 'ui32')),
                ('/system/lib64/libprocessgroup_setup.so', patched('libc/patch_pgsetup.py', '/system/lib64/libprocessgroup_setup.so', 'pgsetup')),
                ('/system/lib64/libmeminfo.so', patched('libc/patch_libmeminfo.py', '/system/lib64/libmeminfo.so', 'meminfo')),
                ('/system/lib64/libbinder.so', patched('libc/patch_libbinder.py', '/system/lib64/libbinder.so', 'binder'))):
    replace(path, f)
print('5b services.jar (HintManagerService without an AIDL power HAL, isBuildConsistent); stale services.{odex,vdex,art} dropped so ART does not map a mismatching oat')
replace('/system/framework/services.jar', patched(os.path.join(HERE, 'patch_services_oneui.py'), '/system/framework/services.jar', 'services'))
cmds.extend(f'rm /system/framework/oat/arm64/services.{x}' for x in ('art', 'odex', 'vdex'))
cmds.append('rm /system/app/TEEgrisTuiService/TEEgrisTuiService.apk')     # Trusted UI service: its TUIThread epoll_ctl()s the TEEgris tui socket and the 4.14 kernel oopses in tz_uiwsock_poll (circ_buf_bytes_used) ~15 s after the launcher starts
if a.audio_closure:
    print('5c audio: Android 16 audioserver + closure, private under /system/lib64/a16audio (same recipe as the Pixel image, tools/audio/install_a16_audio.sh)')
    cl = a.audio_closure; CP = a.capstone_python; AU = lambda n: os.path.join(TOOLS, 'audio', n)
    mkdir('/system/lib64/a16audio', ctx=LIB)
    for n in sorted(os.listdir(cl + '/lib64')):
        f = cl + '/lib64/' + n
        if n == 'audiopolicy-aidl-cpp.so': run(CP, '-I', AU('patch_server_codes.py'), f, wp('a16.audiopolicy.p')); f = wp('a16.audiopolicy.p')      # transaction 115 -> getPermissionController
        if n == 'libaudiopermission.so': run(CP, '-I', AU('patch_audiopermission.py'), f, wp('a16.audiopermission.p')); f = wp('a16.audiopermission.p')
        put(f, '/system/lib64/a16audio/' + n, '644', 0, 0, LIB)
    # install BOTH patch sets or neither: the A17 clients must send A16's AIDL numbers
    for lib, classes in (('audioflinger-aidl-cpp.so', 'BpAudioTrack,BpMmapStream'), ('audiopolicy-aidl-cpp.so', 'BpAudioPolicyService')):
        src = tmpf(lib + '.a17', cat('/system/lib64/' + lib)); run(CP, '-I', AU('fix_aidl_codes.py'), src, cl + '/lib64/' + lib, wp(lib + '.p'), classes)
        replace('/system/lib64/' + lib, wp(lib + '.p'))
    replace('/system/bin/audioserver', cl + '/audioserver')
    rc = cat('/system/etc/init/audioserver.rc').decode(); first, rest = rc.split('\n', 1); assert first.startswith('service audioserver ')
    replace('/system/etc/init/audioserver.rc', tmpf('audioserver.rc', first + '\n    setenv LD_LIBRARY_PATH /system/lib64/a16audio\n' + rest))
if a.google_stage:
    print('5d Google layer (WebView, Play services, Play Store, Services Framework) from public sources, staged under /system/system_ext (the phone mounts its own product partition over /product, so nothing under /product of this image is visible)')
    gs = os.path.abspath(a.google_stage); made = set()
    def gdst(rel): return '/system/system_ext/' + rel[len('product/'):] if rel.startswith('product/') else '/system/' + rel
    for r, _, fs in sorted(os.walk(gs)):
        for f in sorted(fs):
            rel = os.path.relpath(os.path.join(r, f), gs); d = gdst(rel); chain = []; q = os.path.dirname(d)
            while q not in ('/', '/system', '/product', '/system/system_ext') and q not in made and not exists(q): chain.append(q); q = os.path.dirname(q)
            for q in reversed(chain): made.add(q); mkdir(q)
            put(os.path.join(gs, rel), d, '644', 0, 0, LIB if '/lib' in rel.split('/')[1] else SYS)
if a.fphal:
    print('5e fingerprint: AIDL IFingerprint/default shim over the vendor HIDL IBiometricsFingerprint@2.1 (Samsung services.jar also has the HIDL ISehBiometricsFingerprint@3.0 client for the Seh calls); face feature removed (no face HAL on the vendor)')
    fp = os.path.join(HERE, '..', 'fphal'); fpjar = wp('m30s-fphal.jar'); run(sys.executable, '-I', os.path.join(fp, 'make_fphal_jar.py'), fpjar, BT)
    put(fpjar, '/system/etc/m30s-fphal.jar', '644'); put(os.path.join(fp, 'fphal.sh'), '/system/bin/m30s-fphal.sh', '755'); put(os.path.join(fp, 'fphal.rc'), '/system/etc/init/05_fphal.rc', '644')
    put(os.path.join(fp, 'android.hardware.biometrics.fingerprint-m30s.xml'), '/system/etc/vintf/manifest/android.hardware.biometrics.fingerprint-m30s.xml', '644')
    cmds.append('rm /system/etc/permissions/android.hardware.biometrics.face.xml')
# signing material for the repacked runtime apex (apexd only needs the key inside the apex to match)
KEY, KS = wp('apex_key.pem'), wp('apex_sign.jks')
run('openssl', 'genrsa', '-out', KEY, '4096'); run('keytool', '-genkeypair', '-keystore', KS, '-storepass', 'android', '-keypass', 'android', '-alias', 'a17', '-keyalg', 'RSA', '-keysize', '2048', '-dname', 'CN=a17', '-validity', '10000')
APEX_ENV = dict(os.environ, E2FS=E2, ZIPALIGN=os.path.join(BT, 'zipalign'), APKSIGNER=os.path.join(BT, 'apksigner'), APEX_SIGN_KS=KS)
open(wp('rt.apex'), 'wb').write(cat('/system/apex/com.android.runtime.apex')); repl = []
for inner, name in (('/lib64/bionic/libc.so', 'rtlibc64'), ('/lib/bionic/libc.so', 'rtlibc32'), ('/bin/linker64', 'rtlinker64'), ('/bin/linker', 'rtlinker32')):
    apex_member('/system/apex/com.android.runtime.apex', inner, wp(name + '.orig')); py('libc/patch_libc.py', wp(name + '.orig'), wp(name + '.p')); repl.append(f'{inner}={wp(name + ".p")}')
py('apex/repack_apex.py', wp('rt.apex'), wp('rt.new.apex'), KEY, *repl, env=APEX_ENV)
replace('/system/apex/com.android.runtime.apex', wp('rt.new.apex'))

print('6 bpf: netbpfload gates')
mkdir('/system/etc/bpf.oneui')
nb = wp('netbpfload.orig'); apex_member('/system/apex/com.google.android.tethering_compressed.apex', '/bin/netbpfload', nb)
py(os.path.join(HERE, 'patch_netbpfload.py'), nb, wp('netbpfload.p'))
put(wp('netbpfload.p'), '/system/bin/netbpfload.oneui', '755', 0, 2000, 'u:object_r:bpfloader_exec:s0')
nu = wp('netd_updatable.orig'); apex_member('/system/apex/com.google.android.tethering_compressed.apex', '/lib64/libnetd_updatable.so', nu)     # netd aborts on the same V+/25Q2+ kernel gates
run(sys.executable, '-I', os.path.join(HERE, 'patch_netbpfload.py'), nu, wp('netd_updatable.p'), 'V+ platform with kernel version <', '25Q2+ platform with kernel version <', env=dict(os.environ, WINDOW='96', MIN='2'))
put(wp('netd_updatable.p'), '/system/lib64/libnetd_updatable.oneui.so', '644', 0, 0, LIB)
lsc = wp('lsc.orig'); apex_member('/system/apex/com.google.android.tethering_compressed.apex', '/lib64/libservice-connectivity.so', lsc)    # ConnectivityService aborts without the BPF ringbuf (kernel < 5.8)
py(os.path.join(HERE, 'patch_lsc_ringbuf.py'), lsc, wp('lsc.p'))
put(wp('lsc.p'), '/system/lib64/libservice-connectivity.oneui.so', '644', 0, 0, LIB)
rc = '''# One UI port: kernel 4.14 workarounds for the tethering apex (see tools/oneui/patch_netbpfload.py)
on load-bpf-programs
    mount none /system/bin/netbpfload.oneui /apex/com.android.tethering/bin/netbpfload bind
    mount none /system/lib64/libnetd_updatable.oneui.so /apex/com.android.tethering/lib64/libnetd_updatable.so bind
    mount none /system/lib64/libservice-connectivity.oneui.so /apex/com.android.tethering/lib64/libservice-connectivity.so bind
'''
put(tmpf('00_bpf_bind.rc', rc), '/system/etc/init/00_bpf_bind.rc', '644')
for rcp in ('/system/etc/init/netbpfload.rc',):
    if exists(rcp):
        txt = cat(rcp).decode()
        replace(rcp, tmpf('netbpfload.rc', ''.join(l for l in txt.splitlines(True) if 'reboot_on_failure reboot,netbpfload' not in l)))
print('5f health: hide the vendor\'s AIDL IHealth fragment (bind mount of an empty manifest, vendor untouched) so the donor framework uses the vendor\'s HIDL vendor.samsung.hardware.health@2.0::ISehHealth')
put(os.path.join(HERE, 'rc', 'oneui_empty_manifest.xml'), '/system/etc/vintf/oneui_empty_manifest.xml', '644'); put(os.path.join(HERE, 'rc', '00_health_hidl.rc'), '/system/etc/init/00_health_hidl.rc', '644')
print('7 overlay: services extension package (donor names android.ext.services, its extservices apex ships com.google.android.ext.services)')
ovd = os.path.join(HERE, 'overlay-extservices'); fres = wp('framework-res.apk'); open(fres, 'wb').write(cat('/system/framework/framework-res.apk'))
run(os.path.join(BT, 'aapt2'), 'compile', '--dir', os.path.join(ovd, 'res'), '-o', wp('ov.res.zip'))
run(os.path.join(BT, 'aapt2'), 'link', '-o', wp('ov.apk'), '-I', fres, '--manifest', os.path.join(ovd, 'AndroidManifest.xml'), '--min-sdk-version', '34', '--target-sdk-version', '34', wp('ov.res.zip'))
run(os.path.join(BT, 'zipalign'), '-p', '-f', '4', wp('ov.apk'), wp('ov.al.apk'))
run(os.path.join(BT, 'apksigner'), 'sign', '--ks', KS, '--ks-pass', 'pass:android', '--ks-key-alias', 'a17', '--out', wp('M30sExtServicesOverlay.apk'), wp('ov.al.apk'))
put(wp('M30sExtServicesOverlay.apk'), '/system/system_ext/overlay/M30sExtServicesOverlay.apk', '644')
print('7b module metadata: minimal com.android.modulemetadata (PackageManagerService.getInstalledModules throws without one; ActivityManager.systemReady calls it)')
mmd = os.path.join(HERE, 'modulemetadata'); aj = sorted(glob.glob(os.path.join(os.path.dirname(BT), '..', 'platforms', 'android-*', 'android.jar')))[-1]
run(os.path.join(BT, 'aapt2'), 'compile', '--dir', os.path.join(mmd, 'res'), '-o', wp('mm.res.zip'))
run(os.path.join(BT, 'aapt2'), 'link', '-o', wp('mm.apk'), '-I', aj, '--manifest', os.path.join(mmd, 'AndroidManifest.xml'), '--min-sdk-version', '34', '--target-sdk-version', '34', wp('mm.res.zip'))
run(os.path.join(BT, 'zipalign'), '-p', '-f', '4', wp('mm.apk'), wp('mm.al.apk'))
run(os.path.join(BT, 'apksigner'), 'sign', '--ks', KS, '--ks-pass', 'pass:android', '--ks-key-alias', 'a17', '--out', wp('ModuleMetadata.apk'), wp('mm.al.apk'))
if not exists('/system/system_ext/app/ModuleMetadata'): mkdir('/system/system_ext/app/ModuleMetadata')
put(wp('ModuleMetadata.apk'), '/system/system_ext/app/ModuleMetadata/ModuleMetadata.apk', '644')
apply()
shutil.rmtree(W)
print('done', a.out)
