#!/usr/bin/env python3
"""Android 17 (Google aosp_arm64 GSI DP11.261002.005) -> TB-X606V system image: every change that was applied to the tested tablet, rebuilt offline.

usage: build_image17.py --gsi system.img --donor LineageOS-23.2-GSI.img --out system-a17.img [--gapps MindTheGapps.zip [--out-gapps system-a17-gapps.img]]
                        [--port-repo DIR] [--with-bootdiag] [--no-tuner] [--dolby DIR] [--pixel NikGapps-full-arm64-16.zip --pixel-launcher-apk PATCHED.apk]

Inputs: the raw ext4 `system.img` from Google's GSI zip, and a LineageOS 23.2 (Android 16) GSI as donor (VNDK 29, SELinux 29.0 mapping, audioserver and its libraries).
Everything is done offline with debugfs (no mount, runs on macOS and Linux). Steps, each one fixes a failure seen on the tablet:
   1  grow to the 0xf3800000-byte partition, drop ext4 shared_blocks
   2  init: boot SELinux permissive (the GSI is a *user* build); build.prop (debuggable, Bluetooth workaround and profiles, timeouts for a slow device)
   3  libc/linkers (MADV_WIPEONFORK), libprocessgroup_setup (cgroup mount options), libui (HIDL gralloc fallback, gralloc usage bits), libmeminfo, libbinder,
      libandroid_runtime: patched copies in /system; libc and the linkers also inside the runtime APEX (repacked and re-signed with a generated key)
   4  VNDK v29 APEX, SELinux mapping 29.0 for the Android 10 vendor, cgroups.json without blkio, vndk-sp-29 links
   5  com.android.virt.apex: EROFS payload converted to ext4 (kernel 4.9 has no EROFS)
   6  services.jar (HintManagerService with no AIDL power HAL), service-connectivity.jar, and the tethering/bluetooth/swcodec APEX files that must be patched but are signed:
      patched copies in /system/etc/bpf.a17 and /system/bin/netbpfload.{a17,tracer}, bind-mounted by 00_bpf_bind.rc
   7  audio: Android 16's audioserver and library closure run privately from /system/lib64/a16audio; the A17 clients get A16's AIDL numbers
   8  lmkd replacement for the in-kernel low memory killer, lights shim (brightness), vibrator shim (haptics), health shim (battery), RT cgroup budgets, aee off, init.rc console only on request
   9  ROM Tuner app + daemon and the Gemini boot animation (from the Android 16 port repo)
  10  optional MindTheGapps (the same file selection as tools/scripts/install_gapps.sh)
  --dolby DIR   Dolby Atmos from your own copy of the Lenovo firmware: DaxUI.apk, daxService.patched.apk (or daxService.apk), com.dolby.daxservice.xml (not redistributable)
  --pixel ZIP   Pixel layer (docs/PIXEL.md): Pixel Launcher (built by tools/pixel/build_pixel_launcher.sh from the APKMirror Android 17 APK, passed as --pixel-launcher-apk),
                Wallpaper & style, sounds, Google Contacts, Calculator, Files, Calendar, Clock, plus a one-shot that makes the Pixel Launcher the home app.
                The staged priv-apps are checked against the allowlists first: a missing entry would hang the tablet on the boot animation.
Compiled app code (oat/odex) cannot be produced offline: see tools/scripts/dexopt_on_tablet.sh. The vendor partition needs tools/scripts/apply_vendor_a17.sh."""
import argparse, contextlib, glob, hashlib, io, json, os, re, shutil, struct, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.join(HERE, '..', 'tools')
ap = argparse.ArgumentParser()
ap.add_argument('--gsi', required=True, help='raw ext4 system.img from the Google GSI zip (DP11.261002.005)')
ap.add_argument('--donor', '--a16', dest='donor', required=True, help='LineageOS 23.2 GSI, raw ext4')
ap.add_argument('--out', required=True); ap.add_argument('--gapps', help='MindTheGapps-16.0.0-arm64 zip'); ap.add_argument('--out-gapps', help='write a second image with the Google apps (the --out image stays without)')
ap.add_argument('--port-repo', default=os.path.join(HERE, '..', '..', 'tb-x606v-android16-port'), help='Android 16 port repo (ROM Tuner, boot animations)')
ap.add_argument('--dev-tools', action='store_true', help='development safety net (tools/debug): boot_watchdog reboots into recovery when a boot does not finish, bootdiag writes the boot logcat to /data/local/tmp/bootdiag')
ap.add_argument('--no-tuner', action='store_true'); ap.add_argument('--with-bootdiag', action='store_true', help='boot diagnostics service (logcat/kmsg into /data/local/tmp/bootdiag, costs performance)')
ap.add_argument('--dolby', help='directory with DaxUI.apk, daxService.patched.apk (or daxService.apk) and com.dolby.daxservice.xml from the stock Lenovo firmware')
ap.add_argument('--pixel', help='NikGapps-full-arm64-16-*.zip: source of the Pixel apps (Android 16 build; the launcher itself comes from --pixel-launcher-apk)')
ap.add_argument('--pixel-tablet', help='directory made by tools/pixel/stage_pixel_tablet.py: Pixel Tablet SystemUI, Settings and launcher + config overlays of the matching Android 17 build (replaces the GSI SystemUI and Settings)')
ap.add_argument('--pixel-launcher-apk', help='Pixel Launcher built by tools/pixel/build_pixel_launcher.sh')
ap.add_argument('--platform-keys', help='directory with platform.pk8 and platform.x509.pem (the public AOSP platform test key): with it framework-res.apk also accepts Chrome WebView Beta as a WebView provider (tools/framework/allow_webview_beta.py)')
ap.add_argument('--e2fs', help='directory with debugfs, e2fsck, resize2fs, mke2fs (default: found on PATH, /sbin, Homebrew)')
ap.add_argument('--build-tools', help='Android SDK build-tools directory (zipalign, apksigner, d8); default $ANDROID_HOME/build-tools/<newest>')
ap.add_argument('--workdir'); ap.add_argument('--keep-work', action='store_true')
a = ap.parse_args()
if bool(a.pixel) != bool(a.pixel_launcher_apk): sys.exit('--pixel and --pixel-launcher-apk go together')

def find_dir(tool, extra):
    for d in extra + os.environ.get('PATH', '').split(os.pathsep) + ['/sbin', '/usr/sbin', '/opt/homebrew/opt/e2fsprogs/sbin', '/usr/local/opt/e2fsprogs/sbin']:
        if d and os.path.exists(os.path.join(d, tool)): return d
    sys.exit(f'{tool} not found (install e2fsprogs; --e2fs DIR)')
E2 = a.e2fs or find_dir('debugfs', [])
def bt_dir():
    if a.build_tools: return a.build_tools
    for sdk in (os.environ.get('ANDROID_HOME'), os.environ.get('ANDROID_SDK_ROOT'), os.path.expanduser('~/Library/Android/sdk'), os.path.expanduser('~/Android/Sdk')):
        c = sorted(glob.glob(os.path.join(sdk or '/nonexistent', 'build-tools', '*')), key=lambda p: [int(x) for x in re.findall(r'\d+', os.path.basename(p))])
        if c: return c[-1]
    sys.exit('Android SDK build-tools not found (zipalign, apksigner): set ANDROID_HOME or --build-tools')
BT = bt_dir()
PART = 0xf3800000
SYS = 'u:object_r:system_file:s0'; LIB = 'u:object_r:system_lib_file:s0'
W = a.workdir or tempfile.mkdtemp(prefix='a17build'); os.makedirs(W, exist_ok=True)

def run(*c, ok=(0,), env=None, cwd=None):
    r = subprocess.run(c, capture_output=True, text=True, env=env, cwd=cwd)
    if r.returncode not in ok: sys.exit(f'{c[0]} failed ({r.returncode}): {" ".join(map(str, c))[:300]}\n{r.stdout[-2000:]}{r.stderr[-2000:]}')
    return r.stdout
def py(script, *args, env=None): return run(sys.executable, '-I', os.path.join(TOOLS, script), *map(str, args), env=env)
def dbg(img, *c): return subprocess.run([os.path.join(E2, 'debugfs'), '-R', ' '.join(c), img], capture_output=True)
def cat(img, path):
    r = dbg(img, 'cat', path).stdout
    if not r: sys.exit(f'{path} not found in {img}')
    return r
def tmpf(name, data):
    p = os.path.join(W, name); open(p, 'wb' if isinstance(data, bytes) else 'w').write(data); return p
def wp(name): return os.path.join(W, name)

def attrs(img, path):
    """(octal permission digits, uid, gid, SELinux label) of an existing file in the image"""
    st = dbg(img, 'stat', path).stdout.decode('latin1')
    m = re.search(r'Mode:\s+0?(\d+)', st); u = re.search(r'User:\s+(\d+)\s+Group:\s+(\d+)', st)
    lbl = dbg(img, 'ea_get', '-V', path, 'security.selinux').stdout.decode('latin1').split('\n')[0].split('\0')[0].strip()
    assert m and u and lbl, f'cannot read attributes of {path}'
    return m.group(1)[-3:], int(u.group(1)), int(u.group(2)), lbl
def exists(img, path): return b'Inode:' in dbg(img, 'stat', path).stdout

# --- ext4 edit list (debugfs -w -f) ---------------------------------------------------------------------------------------
cmds = []; lbl = {}
def label_file(ctx):
    if ctx not in lbl: lbl[ctx] = tmpf('label%d' % len(lbl), ctx.encode() + b'\0')
    return lbl[ctx]
def put(src, dst, mode, uid=0, gid=0, ctx=SYS):
    cmds.extend([f'rm {dst}', f'write {src} {dst}', f'set_inode_field {dst} mode 0100{mode}', f'set_inode_field {dst} uid {uid}',
                 f'set_inode_field {dst} gid {gid}', f'ea_set -f {label_file(ctx)} {dst} security.selinux'])
def replace(img, dst, src):
    """new content, original owner, mode and SELinux label"""
    m, u, g, c = attrs(img, dst); put(src, dst, m, u, g, c)
def mkdir(path, mode='755', ctx=SYS):
    cmds.extend([f'mkdir {path}', f'set_inode_field {path} mode 040{mode}', f'set_inode_field {path} uid 0', f'set_inode_field {path} gid 0',
                 f'ea_set -f {label_file(ctx)} {path} security.selinux'])
def symlink(path, target, ctx=LIB):
    cmds.extend([f'rm {path}', f'symlink {path} {target}', f'ea_set -f {label_file(ctx)} {path} security.selinux'])
def apply(img):
    global cmds
    f = tmpf('cmds', '\n'.join(cmds) + '\n'); cmds = []
    out = subprocess.run([os.path.join(E2, 'debugfs'), '-w', '-f', f, img], capture_output=True, text=True)
    bad = [l for l in (out.stdout + out.stderr).split('\n') if re.search(r'(?i)(error|not found|no such|not enough|no space)', l) and not l.startswith('debugfs: rm ')]
    # `rm` of a path that does not exist yet prints "File not found by ext2_lookup": expected
    bad = [l for l in bad if 'File not found by ext2_lookup' not in l]
    if bad: sys.exit('debugfs reported:\n' + '\n'.join(bad[:20]))
    run(os.path.join(E2, 'e2fsck'), '-fn', img)

def apex_member(img, apex, inner, dst):
    """copy one file out of the payload of an apex or capex stored in the image"""
    d = wp('apx'); os.makedirs(d, exist_ok=True)
    open(d + '/a.zip', 'wb').write(cat(img, apex)); z = zipfile.ZipFile(d + '/a.zip')
    if 'original_apex' in z.namelist(): open(d + '/o.zip', 'wb').write(z.read('original_apex')); z = zipfile.ZipFile(d + '/o.zip')
    open(d + '/payload.img', 'wb').write(z.read('apex_payload.img'))
    r = dbg(d + '/payload.img', 'dump', inner, dst)
    assert os.path.exists(dst) and os.path.getsize(dst) > 0, f'{inner} not in {apex}'

# 1 ------------------------------------------------------------------------------------------------------------------
print('1 image'); GSI = a.gsi
if open(GSI, 'rb').read(4) == bytes.fromhex('3aff26ed'): sys.exit('sparse image: convert to raw first (simg2img)')
shutil.copyfile(GSI, a.out)
with open(a.out, 'r+b') as f: f.truncate(PART)
run(os.path.join(E2, 'e2fsck'), '-fy', a.out, ok=(0, 1)); run(os.path.join(E2, 'resize2fs'), a.out)
run(os.path.join(E2, 'e2fsck'), '-fy', '-E', 'unshare_blocks', a.out, ok=(0, 1)); run(os.path.join(E2, 'e2fsck'), '-fn', a.out)
S = a.out                                                          # original files are read from the output image before they are replaced

# signing material for the repacked APEX files: AVB key + a JKS for apksigner. Generated per build; apexd only needs the key inside the apex to match.
KEY, KS = wp('apex_key.pem'), wp('apex_sign.jks')
for f in (KEY, KS):
    if os.path.exists(f): os.remove(f)
run('openssl', 'genrsa', '-out', KEY, '4096'); run('keytool', '-genkeypair', '-keystore', KS, '-storepass', 'android', '-keypass', 'android', '-alias', 'a17',
                                                   '-keyalg', 'RSA', '-keysize', '2048', '-dname', 'CN=a17', '-validity', '10000')
APEX_ENV = dict(os.environ, E2FS=E2, ZIPALIGN=os.path.join(BT, 'zipalign'), APKSIGNER=os.path.join(BT, 'apksigner'), APEX_SIGN_KS=KS)

# 2 init, build.prop ---------------------------------------------------------------------------------------------------
print('2 init, build.prop')
init = cat(S, '/system/bin/init')
d = bytearray(init)
# the SELinux enforce decision: bl is_enforcing-ish ; cmp w0,#1 ; b.eq skip ; mov w0,#1 ; bl setenforce ; cbz w0,... (found by pattern, the offset moves with every GSI build)
hits = [a for a in range(0, len(d) - 16, 4)
        if struct.unpack_from('<I', d, a)[0] == 0x7100041f and (struct.unpack_from('<I', d, a + 4)[0] & 0xff00001f) == 0x54000000
        and struct.unpack_from('<I', d, a + 8)[0] == 0x52800020 and struct.unpack_from('<I', d, a + 12)[0] >> 26 == 0x25]
assert len(hits) == 1, ('init: enforce check not found or ambiguous', hits)
o = hits[0] + 4
struct.pack_into('<I', d, o, struct.unpack_from('<I', d, o)[0] | 1)      # b.eq skip -> b.ne skip
struct.pack_into('<I', d, o + 4, 0x52800000)                             # mov w0,#0   -> setenforce(0) when the kernel is enforcing
put(tmpf('init.orig', init), '/system/bin/init.enforcing', '755')
replace(S, '/system/bin/init', tmpf('init.p', bytes(d)))

bp = cat(S, '/system/build.prop').decode()
for x, y in (('ro.secure=1', 'ro.secure=0'), ('ro.debuggable=0', 'ro.debuggable=1'), ('ro.force.debuggable=0', 'ro.force.debuggable=1'), ('ro.adb.secure=1', 'ro.adb.secure=0')):
    assert x in bp, x; bp = bp.replace(x, y)
bp += '\npersist.sys.bt.unsupported.commands=182\npersist.sys.usb.config=adb\nro.hw_timeout_multiplier=5\n'   # slow device: scales AMS/Watchdog/ANR timeouts
bp += 'dalvik.vm.usap_pool_enabled=true\ndalvik.vm.usap_pool_size_max=4\ndalvik.vm.usap_pool_refill_threshold=2\n'    # pre-forked app processes: faster app start, GSIs ship it off
bp += 'persist.vendor.sys.pq.shp.idx=0\n'     # MediaTek sharpening off by default: it makes video look worse (ROM Tuner > Picture quality changes it)
bp += 'persist.sysui.disableBlur=1\n'     # window blur (Pixel Launcher drawer, shade) drops the GE8320 to ~17 fps: 72% janky frames with blur, 5% without
bp += 'pm.dexopt.install=speed\npm.dexopt.install-bulk=speed\n'     # compile apps fully when the Play Store installs or updates them (default speed-profile has no profile yet, so the app ran uncompiled until the nightly job)
bp += 'persist.traced.enable=0\n'    # perfetto traced crash-loops on kernel 4.9 (no vsock) and flags_health_check retries every 5 s
# stock-looking fingerprint assembled from the Lenovo vendor props (build id and incremental of V9.56). Made up: Lenovo's real one is not on the tablet, so Play does not know it
bp += ('ro.build.fingerprint=Lenovo/full_achilles6_row_call/achilles6_row_call:10/QP1A.190711.020/TB-X606V_USR_S300665_2206300345_V9.56_BMP_ROW:user/release-keys\n'
       'ro.build.description=full_achilles6_row_call-user 10 QP1A.190711.020 TB-X606V_USR_S300665_2206300345_V9.56_BMP_ROW release-keys\n')
# the GSI ships no bluetooth.mk properties, so no profile (A2DP, HFP, HID...) is started and nothing can connect
bp += ("\n# Bluetooth profiles (what AOSP's bluetooth.mk sets; a GSI without it starts no profile except hearing aid). Tablet without telephony or LE Audio.\n"
       'bluetooth.device.class_of_device=90,2,12\nbluetooth.profile.a2dp.source.enabled=true\nbluetooth.profile.avrcp.target.enabled=true\n'
       'bluetooth.profile.hfp.ag.enabled=true\nbluetooth.profile.hid.host.enabled=true\nbluetooth.profile.hid.device.enabled=true\nbluetooth.profile.gatt.enabled=true\n'
       'bluetooth.profile.bas.client.enabled=true\nbluetooth.profile.opp.enabled=true\nbluetooth.profile.pan.nap.enabled=true\nbluetooth.profile.pan.panu.enabled=true\n'
       'bluetooth.profile.asha.central.enabled=true\n')
if a.pixel_tablet:
    # Pixel Settings (SettingsGoogle) shows its two-pane layout only if this property is true: ActivityEmbeddingUtils reads it once in a static initializer and logs
    # "isSettingsSplitSupported = false" without it. The Pixel sets it in its own build.prop, which this GSI does not have (docs/PIXEL.md, "Settings two-pane / tablet UI")
    bp += 'persist.settings.large_screen_opt.enabled=true\n'
replace(S, '/system/build.prop', tmpf('build.prop', bp))
# the tablet reports its real identity (the GSI says "AOSP on ARM64"): streaming apps pick their quality tier by model, and Netflix only offered SD to the generic one
pb = cat(S, '/system/product/etc/build.prop').decode()
for k, v in (('brand', 'Lenovo'), ('device', 'achilles6_row_call'), ('manufacturer', 'LENOVO'), ('model', 'Lenovo TB-X606V'), ('name', 'full_achilles6_row_call')):
    pb, n = re.subn(r'(?m)^ro\.product\.product\.%s=.*$' % k, 'ro.product.product.%s=%s' % (k, v), pb); assert n == 1, k
if a.pixel_tablet:
    # the GSI says "default"; the stock Lenovo firmware said "tablet". Read by Settings (media output and illustration icons), Play services, Gboard (only "desktop"), setup wizard, Wellbeing, Google app. Read only at boot
    pb, n = re.subn(r'(?m)^ro\.build\.characteristics=.*$', 'ro.build.characteristics=tablet', pb); assert n == 1, 'ro.build.characteristics'
replace(S, '/system/product/etc/build.prop', tmpf('product.build.prop', pb))

# 3 patched libraries --------------------------------------------------------------------------------------------------
print('3 libc, linkers, libui, ...')
def patched(tool, path, name):
    """stock file -> patch tool -> work file"""
    src = tmpf(name + '.orig', cat(S, path)); out = wp(name + '.p'); py(tool, src, out); return out
# services.jar: HintManager/camera/build-consistent fixes, then the network location provider bind (Play services does not hold INSTALL_LOCATION_PROVIDER)
services_loc = wp('services.loc.p'); py('framework/patch_location_provider.py', patched('framework/patch_services_jar.py', '/system/framework/services.jar', 'services'), services_loc)
libc64 = patched('libc/patch_libc.py', '/system/lib64/bootstrap/libc.so', 'libc64'); libc32 = patched('libc/patch_libc.py', '/system/lib/bootstrap/libc.so', 'libc32')
ld64 = patched('libc/patch_libc.py', '/system/bin/bootstrap/linker64', 'linker64'); ld32 = patched('libc/patch_libc.py', '/system/bin/bootstrap/linker', 'linker32')
for path, f in (('/system/lib64/bootstrap/libc.so', libc64), ('/system/lib/bootstrap/libc.so', libc32), ('/system/bin/bootstrap/linker64', ld64), ('/system/bin/bootstrap/linker', ld32),
                ('/system/lib64/libui.so', patched('libc/patch_libui.py', '/system/lib64/libui.so', 'ui64')), ('/system/lib/libui.so', patched('libc/patch_libui.py', '/system/lib/libui.so', 'ui32')),
                ('/system/lib64/libprocessgroup_setup.so', patched('libc/patch_pgsetup.py', '/system/lib64/libprocessgroup_setup.so', 'pgsetup')),
                ('/system/lib64/libmeminfo.so', patched('libc/patch_libmeminfo.py', '/system/lib64/libmeminfo.so', 'meminfo')),
                ('/system/lib64/libbinder.so', patched('libc/patch_libbinder.py', '/system/lib64/libbinder.so', 'binder')),
                ('/system/bin/netd', patched('libc/patch_netd_spawn.py', '/system/bin/netd', 'netd_spawn')),
                ('/system/lib64/libandroid_runtime.so', patched('libc/patch_libandroid_runtime.py', '/system/lib64/libandroid_runtime.so', 'androidrt')),
                ('/system/framework/services.jar', services_loc)):
    replace(S, path, f)
if a.platform_keys:
    print('3b framework-res.apk: Chrome WebView Beta accepted as a WebView provider')
    jar = os.path.join(os.path.dirname(os.path.dirname(BT)), 'platforms', 'android-34', 'android.jar')
    py('framework/allow_webview_beta.py', tmpf('framework-res.orig', cat(S, '/system/framework/framework-res.apk')), os.path.join(TOOLS, 'framework', 'chrome_webview_cert.b64'),
       os.path.join(a.platform_keys, 'platform.pk8'), os.path.join(a.platform_keys, 'platform.x509.pem'), wp('framework-res.wv.apk'), env=dict(os.environ, BUILD_TOOLS=BT, ANDROID_JAR=jar))
    replace(S, '/system/framework/framework-res.apk', wp('framework-res.wv.apk'))
# the runtime APEX carries its own copies of libc and the linkers (apps and the bionic namespace use them)
open(wp('rt.apex'), 'wb').write(cat(S, '/system/apex/com.android.runtime.apex'))
repl = []
for inner, name in (('/lib64/bionic/libc.so', 'rtlibc64'), ('/lib/bionic/libc.so', 'rtlibc32'), ('/bin/linker64', 'rtlinker64'), ('/bin/linker', 'rtlinker32')):
    apex_member(S, '/system/apex/com.android.runtime.apex', inner, wp(name + '.orig')); py('libc/patch_libc.py', wp(name + '.orig'), wp(name + '.p')); repl.append(f'{inner}={wp(name + ".p")}')
py('apex/repack_apex.py', wp('rt.apex'), wp('rt.new.apex'), KEY, *repl, env=APEX_ENV)
replace(S, '/system/apex/com.android.runtime.apex', wp('rt.new.apex'))

# 4 VNDK 29, SELinux mapping, cgroups -------------------------------------------------------------------------------------
print('4 vndk 29, selinux mapping, cgroups')
vndk = cat(a.donor, '/system/system_ext/apex/com.android.vndk.v29.apex'); assert len(vndk) > 50_000_000
put(tmpf('vndk29.apex', vndk), '/system/system_ext/apex/com.android.vndk.v29.apex', '644')
# the Android 10 vendor's libhwbinder looks for passthrough HALs in /system/lib64/vndk-sp-29/hw
symlink('/system/lib64/vndk-sp-29', '/apex/com.android.vndk.v29/lib64'); symlink('/system/lib/vndk-sp-29', '/apex/com.android.vndk.v29/lib')
defined = set()
for p in ('/system/etc/selinux/plat_sepolicy.cil', '/system/system_ext/etc/selinux/system_ext_sepolicy.cil', '/system/product/etc/selinux/product_sepolicy.cil'):
    defined |= set(re.findall(r'\((?:type|typeattribute|typealias) ([A-Za-z0-9_.]+)\)', cat(S, p).decode('latin1')))
KW = {'and', 'or', 'not', 'xor', 'all'}
def prune(text):
    out, dropped, stripped = [], 0, 0
    for l in text.split('\n'):
        m = re.match(r'^\(typeattributeset (\S+) \((.*)\)\)\s*$', l)
        if m and not re.search(r'\((and|or|not|xor)\b', m.group(2)):    # single-line plain lists only; nested expressions are left alone
            toks = m.group(2).split(); keep = [t for t in toks if t in defined or t in KW]
            if not keep: dropped += 1; continue                          # an empty list is a secilc syntax error
            if len(keep) != len(toks): stripped += 1; l = '(typeattributeset %s (%s))' % (m.group(1), ' '.join(keep))
        out.append(l)
    print(f'  mapping 29.0: {stripped} statements pruned, {dropped} dropped'); return '\n'.join(out)
put(tmpf('map29.cil', prune(cat(a.donor, '/system/etc/selinux/mapping/29.0.cil').decode('latin1'))), '/system/etc/selinux/mapping/29.0.cil', '644')
put(tmpf('map29c.cil', cat(a.donor, '/system/etc/selinux/mapping/29.0.compat.cil')), '/system/etc/selinux/mapping/29.0.compat.cil', '644')   # defines its own "vendordomain"
for p in ('/system/system_ext/etc/selinux/mapping/29.0.cil', '/system/system_ext/etc/selinux/mapping/29.0.compat.cil', '/system/product/etc/selinux/mapping/29.0.cil'):
    put(tmpf('empty', ''), p, '644')
cg = json.loads(cat(S, '/system/etc/cgroups.json'))
cg['Cgroups'] = [c for c in cg['Cgroups'] if c['Controller'] != 'blkio']           # kernel 4.9 has no blkio controller here
for c in cg['Cgroups2']['Controllers']:
    if c['Controller'] == 'freezer': c['Optional'] = True
replace(S, '/system/etc/cgroups.json', tmpf('cgroups.json', json.dumps(cg, indent=2)))

# 5 virt apex ------------------------------------------------------------------------------------------------------------
print('5 virt apex (EROFS -> ext4)')
if shutil.which('fsck.erofs'):
    open(wp('virt.apex'), 'wb').write(cat(S, '/system/apex/com.android.virt.apex'))
    py('apex/virt_to_ext4.py', wp('virt.apex'), wp('virt.new.apex'), KEY, env=APEX_ENV)
    replace(S, '/system/apex/com.android.virt.apex', wp('virt.new.apex'))
else:
    print('  fsck.erofs (erofs-utils) not found: removing the APEX instead (the framework then lacks the virtualization jar; boot is untested that way)')
    cmds.append('rm /system/apex/com.android.virt.apex')

# 6 tethering / bluetooth / swcodec ------------------------------------------------------------------------------------
print('6 bpf and friends')
mkdir('/system/etc/bpf.a17')
T = 'com.android.tethering.capex'; A = '/system/apex/'
nb = wp('netbpfload.orig'); apex_member(S, A + T, '/bin/netbpfload', nb); py('bpf/patch_binaries.py', 'netbpfload', nb, wp('netbpfload.a17'))
put(wp('netbpfload.a17'), '/system/bin/netbpfload.a17', '755', 0, 2000, 'u:object_r:bpfloader_exec:s0')
# the tracer starts netbpfload.a17 under ptrace (children are resumed, bpf.progs_loaded is set when it ends) and is what the bind mount puts in the apex
def zigcc(src, out):
    zig = shutil.which('zig'); cmd = [zig] if zig else [sys.executable, '-m', 'ziglang']
    run(*cmd, 'cc', '-target', 'aarch64-linux-musl', '-static', '-O2', '-D_GNU_SOURCE', '-o', out, src)
zigcc(os.path.join(TOOLS, 'bpf', 'netbpfload_tracer.c'), wp('tracer')); zigcc(os.path.join(TOOLS, 'lmkd', 'lmkd_inkernel.c'), wp('lmkd'))
put(wp('tracer'), '/system/bin/netbpfload.tracer', '755', 0, 2000, 'u:object_r:bpfloader_exec:s0')
def bpf_file(name, apex, inner, tool, mode, ctx):
    src = wp(name + '.orig'); apex_member(S, A + apex, inner, src); out = wp(name + '.p'); tool(src, out); put(out, '/system/etc/bpf.a17/' + name, mode, 0, 0, ctx)
bpf_file('libnetd_updatable.so', T, '/lib64/libnetd_updatable.so', lambda i, o: py('bpf/patch_binaries.py', 'netd_updatable', i, o), '644', LIB)
bpf_file('libservice-connectivity.so', T, '/lib64/libservice-connectivity.so', lambda i, o: py('bpf/patch_binaries.py', 'service_connectivity', i, o), '644', LIB)
bpf_file('service-connectivity.jar', T, '/javalib/service-connectivity.jar', lambda i, o: py('framework/patch_service_connectivity_jar.py', i, o), '644', SYS)
bpf_file('libbluetooth_jni.so', 'com.android.bt.capex', '/lib64/libbluetooth_jni.so', lambda i, o: py('bpf/patch_bluetooth.py', i, o), '644', LIB)
bpf_file('libui_swcodec64.so', 'com.android.media.swcodec.capex', '/lib64/libui.so', lambda i, o: py('libc/patch_libui.py', i, o), '644', SYS)
bpf_file('libui_swcodec32.so', 'com.android.media.swcodec.capex', '/lib/libui.so', lambda i, o: py('libc/patch_libui.py', i, o), '644', SYS)
def netd(i, o): py('bpf/btfmaps.py', i, '--patch', wp('netd.btf.o')); py('bpf/patch_netd_o.py', wp('netd.btf.o'), o)       # LRU_HASH -> HASH in the BTF, then in .android_maps
bpf_file('netd.o', T, '/etc/bpf/mainline/netd.o', netd, '644', SYS)
for rc in ('bpf/00_bpf_bind.rc', 'bpf/00_aee_off.rc', 'zz_a17_rt.rc'): put(os.path.join(TOOLS, rc), '/system/etc/init/' + os.path.basename(rc), '644')
# compiles the apps in speed mode by itself after a data wipe (CI images carry no compiled code); skips what is already compiled
put(os.path.join(TOOLS, 'firstboot', 'firstboot_dexopt.sh'), '/system/bin/firstboot_dexopt.sh', '755'); put(os.path.join(TOOLS, 'scripts', 'dexopt_all.sh'), '/system/bin/dexopt_all.sh', '755')
put(os.path.join(TOOLS, 'firstboot', 'zz_firstboot_dexopt.rc'), '/system/etc/init/zz_firstboot_dexopt.rc', '644')
put(os.path.join(TOOLS, 'firstboot', 'odex_bind.sh'), '/system/bin/odex_bind.sh', '755'); put(os.path.join(TOOLS, 'firstboot', 'zz_odex_bind.rc'), '/system/etc/init/zz_odex_bind.rc', '644')
rc = cat(S, '/system/etc/init/netbpfload.rc').decode(); assert 'reboot_on_failure reboot,netbpfload-missing' in rc
replace(S, '/system/etc/init/netbpfload.rc', tmpf('netbpfload.rc', ''.join(l for l in rc.splitlines(True) if 'reboot_on_failure reboot,netbpfload-missing' not in l)))

# 7 audio ----------------------------------------------------------------------------------------------------------------
print('7 audio')
cl = wp('closure'); py('audio/a16_closure.py', a.donor, cl, E2)
mkdir('/system/lib64/a16audio', ctx=LIB)
for n in sorted(os.listdir(cl + '/lib64')):
    f = cl + '/lib64/' + n
    if n == 'audiopolicy-aidl-cpp.so': py('audio/patch_server_codes.py', f, wp('a16.audiopolicy.p')); f = wp('a16.audiopolicy.p')     # transaction 115 -> getPermissionController
    if n == 'libaudiopermission.so': py('audio/patch_audiopermission.py', f, wp('a16.audiopermission.p')); f = wp('a16.audiopermission.p')
    put(f, '/system/lib64/a16audio/' + n, '644', 0, 0, LIB)
# Install BOTH of those patches or neither (see tools/audio/install_a16_audio.sh). A17 clients send A16's AIDL numbers:
for lib, classes in (('audioflinger-aidl-cpp.so', 'BpAudioTrack,BpMmapStream'), ('audiopolicy-aidl-cpp.so', 'BpAudioPolicyService')):
    src = tmpf(lib + '.a17', cat(S, '/system/lib64/' + lib)); py('audio/fix_aidl_codes.py', src, cl + '/lib64/' + lib, wp(lib + '.p'), classes)
    replace(S, '/system/lib64/' + lib, wp(lib + '.p'))
replace(S, '/system/bin/audioserver', cl + '/audioserver')
rc = cat(S, '/system/etc/init/audioserver.rc').decode(); first, rest = rc.split('\n', 1); assert first.startswith('service audioserver ')
replace(S, '/system/etc/init/audioserver.rc', tmpf('audioserver.rc', first + '\n    setenv LD_LIBRARY_PATH /system/lib64/a16audio\n' + rest))

# 8 lmkd, lights, vibrator, health, init.rc -------------------------------------------------------------------------------------------------
print('8 lmkd, lights, vibrator, health, console')
replace(S, '/system/bin/lmkd', wp('lmkd'))
rc = cat(S, '/system/etc/init/lmkd.rc').decode(); assert '    critical\n' in rc    # lmkd is critical: if it dies the tablet reboots
replace(S, '/system/etc/init/lmkd.rc', tmpf('lmkd.rc', rc.replace('    critical\n', '', 1)))
# cpustatsd asks init for the ambient capabilities BPF (39) and PERFMON (38); kernel 4.9 knows capabilities up to 37, init's prctl(PR_CAP_AMBIENT_RAISE) fails and the service
# aborts and restarts every 5 s (a tombstone each time). SYS_NICE is the only one it needs here.
if exists(S, '/system/etc/init/cpustatsd.rc'):
    rc = cat(S, '/system/etc/init/cpustatsd.rc').decode()
    if 'capabilities BPF SYS_NICE PERFMON' in rc: replace(S, '/system/etc/init/cpustatsd.rc', tmpf('cpustatsd.rc', rc.replace('capabilities BPF SYS_NICE PERFMON', 'capabilities SYS_NICE')))
run('sh', os.path.join(TOOLS, 'lights', 'build.sh'), env=dict(os.environ, ANDROID_HOME=os.path.abspath(os.path.join(BT, '..', '..')), BUILD_TOOLS=BT))
put(os.path.join(TOOLS, 'lights', 'out', 'lightsshim.jar'), '/system/etc/lightsshim.jar', '644')
put(os.path.join(TOOLS, 'lights', 'lightsshim.sh'), '/system/bin/lightsshim.sh', '755'); put(os.path.join(TOOLS, 'lights', 'lightsshim.rc'), '/system/etc/init/lightsshim.rc', '644')
# vibrator: same pattern, the AIDL IVibrator/default shim (its vintf fragment goes on /vendor with the lights one, see tools/scripts/apply_vendor_a17.sh)
run('sh', os.path.join(TOOLS, 'vibrator', 'build.sh'), env=dict(os.environ, ANDROID_HOME=os.path.abspath(os.path.join(BT, '..', '..')), BUILD_TOOLS=BT))
put(os.path.join(TOOLS, 'vibrator', 'out', 'vibratorshim.jar'), '/system/etc/vibratorshim.jar', '644')
put(os.path.join(TOOLS, 'vibrator', 'vibratorshim.sh'), '/system/bin/vibratorshim.sh', '755'); put(os.path.join(TOOLS, 'vibrator', 'vibratorshim.rc'), '/system/etc/init/vibratorshim.rc', '644')
# health: same pattern, the AIDL IHealth/default shim that gives BatteryService the real level, voltage and temperature (its vintf fragment goes on /vendor, see tools/scripts/apply_vendor_a17.sh).
# Install order matters on a live system: with the fragment declared and no service registered, BatteryService waits for the HAL forever.
run('sh', os.path.join(TOOLS, 'health', 'build.sh'), env=dict(os.environ, ANDROID_HOME=os.path.abspath(os.path.join(BT, '..', '..')), BUILD_TOOLS=BT))
put(os.path.join(TOOLS, 'health', 'out', 'healthshim.jar'), '/system/etc/healthshim.jar', '644')
put(os.path.join(TOOLS, 'health', 'healthshim.sh'), '/system/bin/healthshim.sh', '755'); put(os.path.join(TOOLS, 'health', 'healthshim.rc'), '/system/etc/init/healthshim.rc', '644')
# init.rc starts the UART console on debuggable builds and ActivityManager then warns "Serial console enabled, performance is impacted" every boot
rc = cat(S, '/system/etc/init/hw/init.rc').decode(); old = 'on init && property:ro.debuggable=1\n    start console\n'; assert old in rc
replace(S, '/system/etc/init/hw/init.rc', tmpf('init.rc', rc.replace(old, '# console shell on the UART only when asked (ROM Tuner: Serial console). ActivityManager shows a performance warning whenever init.svc.console is running.\n'
                                                             'on property:persist.sys.console=1\n    start console\n')))

# 8c telephony sub-features the Android 10 vendor does not declare (RIL.mIsCellularSupported needs radio.access, else every radio service is 'not available')
put(os.path.join(TOOLS, 'telephony', 'android.hardware.telephony.a17.xml'), '/system/etc/permissions/android.hardware.telephony.a17.xml', '644')

# 9 ROM Tuner, boot animations, optional boot diagnostics ---------------------------------------------------------------------
R = os.path.join(a.port_repo, 'rom-tuner'); media = '/system/product/media'
def rc_fix(path): return open(path).read().replace('u:r:su:s0', 'u:r:init:s0')      # the 'su' domain is not in this policy
if not a.no_tuner:
    print('9 ROM Tuner, boot animation')
    assert os.path.exists(os.path.join(R, 'RomTuner.apk')), f'{R} is not the Android 16 port repo (--port-repo)'
    mkdir('/system/app/RomTuner'); put(os.path.join(R, 'RomTuner.apk'), '/system/app/RomTuner/RomTuner.apk', '644')
    put(os.path.join(R, 'device', 'tablet_tunerd.sh'), '/system/bin/tablet_tunerd.sh', '755')
    put(tmpf('tablet_tunerd.rc', rc_fix(os.path.join(R, 'device', 'tablet_tunerd.rc'))), '/system/etc/init/tablet_tunerd.rc', '644')
    gem = os.path.join(R, 'boot-animation', 'bootanimation-gemini.zip')
    put(os.path.join(R, 'boot-animation', 'bootanimation-arrow.zip'), media + '/bootanimation-arrow.zip', '644'); put(gem, media + '/bootanimation-gemini.zip', '644')
    put(gem, media + '/bootanimation.zip', '644')                    # Gemini is the default, the Tuner copies the chosen one over this file
    ov = os.path.join(R, 'overlays')                                 # font overlays and the pure black overlay (signed with the AOSP platform test key, like the rest)
    for f in sorted(os.listdir(ov)) if os.path.isdir(ov) else []:
        if f.endswith('.apk'): mkdir('/system/product/overlay/' + f[:-4]); put(os.path.join(ov, f), '/system/product/overlay/%s/%s' % (f[:-4], f), '644')
if a.dev_tools:
    for f, mode in (('boot_watchdog.sh', '755'), ('bootdiag.sh', '755')): put(os.path.join(TOOLS, 'debug', f), '/system/bin/' + f, mode)
    for f in ('zz_boot_watchdog.rc', 'zz_bootdiag.rc'): put(os.path.join(TOOLS, 'debug', f), '/system/etc/init/' + f, '644')
if a.with_bootdiag:
    put(os.path.join(a.port_repo, 'debug', 'bootdiag.sh'), '/system/bin/bootdiag.sh', '755')
    put(tmpf('zz_bootdiag.rc', rc_fix(os.path.join(a.port_repo, 'debug', 'zz_bootdiag.rc'))), '/system/etc/init/zz_bootdiag.rc', '644')

# 9b optional Dolby Atmos and Pixel layer ------------------------------------------------------------------------------------
made_dirs = set(); priv_apks = []; allow_xmls = []
def ensure_dirs(paths):
    for f in sorted(paths):
        d = os.path.dirname(f); chain = []
        while d not in ('/system', '/') and d not in made_dirs:
            chain.append(d); d = os.path.dirname(d)
        for d in reversed(chain):
            made_dirs.add(d)
            if not exists(S, d): mkdir(d)
def ls_names(path): return [l.split('/')[5] for l in dbg(S, 'ls', '-p', path).stdout.decode('latin1').splitlines() if l.count('/') >= 6 and l.split('/')[5] not in ('.', '..')]
if a.dolby:
    print('9b Dolby Atmos')
    svc = next((os.path.join(a.dolby, n) for n in ('daxService.patched.apk', 'daxService.apk') if os.path.exists(os.path.join(a.dolby, n))), None)
    for need in (os.path.join(a.dolby, 'DaxUI.apk'), os.path.join(a.dolby, 'com.dolby.daxservice.xml'), svc):
        if not need or not os.path.exists(need): sys.exit(f'--dolby: {need} missing')
    files = {'/system/app/DaxUI/DaxUI.apk': os.path.join(a.dolby, 'DaxUI.apk'), '/system/product/priv-app/daxService/daxService.apk': svc,
             '/system/product/etc/permissions/com.dolby.daxservice.xml': os.path.join(a.dolby, 'com.dolby.daxservice.xml')}
    ensure_dirs(files)
    for dst, src in files.items(): put(src, dst, '644')
    priv_apks.append(svc + ':product'); allow_xmls.append(os.path.join(a.dolby, 'com.dolby.daxservice.xml') + ':product')
if a.pixel:
    print('9b Pixel layer')
    sys.path.insert(0, os.path.join(TOOLS, 'pixel')); import stage_pixel
    px = wp('pixel'); shutil.rmtree(px, ignore_errors=True)
    # Gboard is left out on purpose (draws no keyboard: its modules come from Play). The Pixel Launcher recents overlay is left out too (crashes SystemUI's shell).
    # Static overlays are only taken for the wallpaper picker and the sounds; the other packs' overlays are skipped like on the tested tablet.
    for n in ('PixelLauncher', 'GoogleWallpaper', 'PixelThemes', 'GoogleSounds', 'GoogleContacts', 'GoogleCalculator', 'GoogleFiles', 'GoogleCalendar', 'GoogleClock', 'EmojiWallpaper'):
        skip = tuple(k for k in stage_pixel.SKIP if k != '/overlay/') if n in ('GoogleWallpaper', 'GoogleSounds') else stage_pixel.SKIP
        with contextlib.redirect_stdout(io.StringIO()): stage_pixel.stage(a.pixel, px, [n], skip)
    shutil.copyfile(a.pixel_launcher_apk, px + '/priv-app/NexusLauncherRelease/NexusLauncherRelease.apk')     # replaces the Android 16 build that NikGapps ships
    for x in ('privapp-permissions-nexuslauncher-a17.xml', 'privapp-permissions-clock-a17.xml'): shutil.copyfile(os.path.join(TOOLS, 'pixel', x), px + '/etc/permissions/' + x)
    staged = sorted(os.path.relpath(os.path.join(r, f), px) for r, _, fs in os.walk(px) for f in fs)
    ensure_dirs('/system/product/' + f for f in staged)
    for f in staged: put(os.path.join(px, f), '/system/product/' + f, '644', 0, 0, LIB if f.startswith(('lib/', 'lib64/')) else SYS)
    priv_apks += [os.path.join(px, f) + ':product' for f in staged if f.startswith('priv-app/') and f.endswith('.apk')]
    allow_xmls += [os.path.join(px, f) + ':product' for f in staged if f.startswith('etc/permissions/') and f.endswith('.xml')]
    # AOSP Provision is a second SETUP_WIZARD activity: with two, PackageManager names no setup wizard package and the Google wizard never gets the `setup` permissions (NETWORK_SETUP_WIZARD: wifi page crashes)
    cmds.append('rm /system/system_ext/priv-app/Provision/Provision.apk')
    put(os.path.join(TOOLS, 'pixel', 'pixel_home.sh'), '/system/bin/pixel_home.sh', '755')
    put(tmpf('zz_pixel_home.rc', open(os.path.join(TOOLS, 'pixel', 'zz_pixel_home.rc')).read()), '/system/etc/init/zz_pixel_home.rc', '644')
if a.pixel_tablet:
    print('9c Pixel Tablet layer')
    st = a.pixel_tablet
    for dst, src in (('/system/system_ext/priv-app/SystemUI/SystemUI.apk', 'system_ext/priv-app/SystemUI/SystemUI.apk'),
                     ('/system/system_ext/priv-app/Settings/Settings.apk', 'system_ext/priv-app/Settings/Settings.apk')):
        replace(S, dst, os.path.join(st, src))            # same package, owner and label as the GSI's own apps
    staged = sorted(os.path.relpath(os.path.join(r, f), st) for r, _, fs in os.walk(st) for f in fs)
    new = [f for f in staged if f not in ('system_ext/priv-app/SystemUI/SystemUI.apk', 'system_ext/priv-app/Settings/Settings.apk')]
    ensure_dirs('/system/' + f for f in new)
    for f in new: put(os.path.join(st, f), '/system/' + f, '644', 0, 0, LIB if '/lib64/' in f else SYS)
    # Device Health Services: TurboAdapter's JNI lib lives in system_ext/lib64, the app links it from its own lib/arm64 as on the Pixel
    if 'system_ext/lib64/libpowerstatshaldataprovider.so' in staged:
        mkdir('/system/system_ext/priv-app/TurboAdapter/lib'); mkdir('/system/system_ext/priv-app/TurboAdapter/lib/arm64')
        symlink('/system/system_ext/priv-app/TurboAdapter/lib/arm64/libpowerstatshaldataprovider.so', '/system_ext/lib64/libpowerstatshaldataprovider.so')
    # allowlists the Pixel's own xml does not cover for the partition of the app: Hub mode (product, the Pixel xml has it too) and TurboAdapter (system_ext: the Pixel keeps it in system_ext/etc/permissions, which is not staged)
    for x, part in (('privapp-permissions-hub-a17.xml', 'product'), ('privapp-permissions-turbo-a17.xml', 'system_ext')):
        put(os.path.join(TOOLS, 'pixel', x), f'/system/{part}/etc/permissions/{x}', '644'); allow_xmls.append(os.path.join(TOOLS, 'pixel', x) + ':' + part)
    # the allowlist is read from the partition of the app: the launcher, SystemUI and Settings live in system_ext, so their extra entries go to /system/system_ext/etc/permissions
    put(os.path.join(TOOLS, 'pixel', 'privapp-permissions-pixeltablet-a17.xml'), '/system/system_ext/etc/permissions/privapp-permissions-pixeltablet-a17.xml', '644')
    allow_xmls.append(os.path.join(TOOLS, 'pixel', 'privapp-permissions-pixeltablet-a17.xml') + ':system_ext')
    allow_xmls += [os.path.join(st, f) + ':product' for f in staged if f.startswith('product/etc/permissions/') and f.endswith('.xml')]
    priv_apks += [os.path.join(st, f) + (':system_ext' if f.startswith('system_ext/') else ':product') for f in staged if '/priv-app/' in f and f.endswith('.apk')]
    # Pixel boot animation: the default slot of ROM Tuner ("gemini") and the plain file
    for pz, dsts in (('product/media/bootanimation-pixel.zip', ('bootanimation.zip', 'bootanimation-gemini.zip')), ('product/media/bootanimation-pixel-dark.zip', ('bootanimation-dark.zip',))):
        fitted = wp(os.path.basename(pz)); py(os.path.join('pixel', 'fit_bootanimation.py'), os.path.join(st, pz), fitted)    # canvas 2560x1600 -> this panel (1200x1920), see the script
        for d in dsts: put(fitted, '/system/product/media/' + d, '644')
    # AOSP Provision is a second SETUP_WIZARD activity: with two, PackageManager names no setup wizard package and the Google wizard never gets the `setup` permissions (NETWORK_SETUP_WIZARD: wifi page crashes)
    cmds.append('rm /system/system_ext/priv-app/Provision/Provision.apk')
    put(os.path.join(TOOLS, 'pixel', 'pixel_home.sh'), '/system/bin/pixel_home.sh', '755')
    put(os.path.join(TOOLS, 'pixel', 'wizard_lock_skip.sh'), '/system/bin/wizard_lock_skip.sh', '755')
    put(os.path.join(TOOLS, 'pixel', 'zz_wizard_lock_skip.rc'), '/system/etc/init/zz_wizard_lock_skip.rc', '644')
    put(tmpf('zz_pixel_home.rc', open(os.path.join(TOOLS, 'pixel', 'zz_pixel_home.rc')).read()), '/system/etc/init/zz_pixel_home.rc', '644')
if priv_apks:
    # a priv-app with a privileged permission that no allowlist grants aborts system_server at boot (boot animation forever): refuse to build it
    print('  privileged permission allowlist check')
    for apk in ('/system/framework/framework-res.apk', '/system/system_ext/priv-app/SystemUI/SystemUI.apk'): open(wp(os.path.basename(apk)), 'wb').write(cat(S, apk))
    for d in ('/system/etc/permissions', '/system/product/etc/permissions', '/system/system_ext/etc/permissions'):
        for n in ls_names(d):
            if n.endswith('.xml'): allow_xmls.append(tmpf('allow_' + n, cat(S, d + '/' + n)) + ':' + ('product' if '/product/' in d else 'system_ext' if '/system_ext/' in d else 'system'))
    r = subprocess.run([sys.executable, '-I', os.path.join(TOOLS, 'pixel', 'check_privapp_offline.py'), '--perm-apk', wp('framework-res.apk'), '--perm-apk', wp('SystemUI.apk')]
                       + [x for f in allow_xmls for x in ('--allow', f)] + [x for f in priv_apks for x in ('--apk', f)], capture_output=True, text=True, env=dict(os.environ, BUILD_TOOLS=BT))
    print(r.stdout.rstrip())
    if r.returncode and a.dev_tools:
        # development builds: allowlist what the apps ask for (commit the generated file as tools/pixel/privapp-permissions-pixeltablet-extra-a17.xml for a release build)
        extra = wp('extra_allow.xml')
        subprocess.run([sys.executable, '-I', os.path.join(TOOLS, 'pixel', 'check_privapp_offline.py'), '--perm-apk', wp('framework-res.apk'), '--perm-apk', wp('SystemUI.apk')]
                       + [x for f in allow_xmls for x in ('--allow', f)] + [x for f in priv_apks for x in ('--apk', f)] + ['--write-extra', extra], capture_output=True, text=True, env=dict(os.environ, BUILD_TOOLS=BT))
        shutil.copyfile(extra, os.path.join(os.path.dirname(a.out) or '.', 'privapp-extra-allow.xml'))
        for part in ('system_ext', 'product'): put(extra, f'/system/{part}/etc/permissions/privapp-permissions-pixeltablet-extra-a17.xml', '644')
        print('  --dev-tools: the missing entries were allowlisted from the generated file (privapp-extra-allow.xml next to the image)')
    elif r.returncode: sys.exit('priv-app permissions are not allowlisted (see above): add them to an allowlist xml (check_privapp_offline.py --write-extra), or the tablet will not boot')

def add_oat_dirs(img):
    """odex_bind.sh bind mounts /data/odex/<app> over <app dir>/oat. / is read-only when it runs (post-fs-data), so the mount points have to be in the image."""
    for d in ('/system/system_ext/priv-app', '/system/system_ext/app', '/system/product/priv-app', '/system/product/app', '/system/priv-app', '/system/app'):
        out = dbg(img, 'ls', '-p', d).stdout.decode('latin1').splitlines()
        for l in out:
            f = l.split('/')
            if len(f) > 5 and f[5] not in ('.', '..') and f[2].lstrip('0')[:2] == '40' and not exists(img, f'{d}/{f[5]}/oat'): mkdir(f'{d}/{f[5]}/oat', '751')
    apply(img)

print('writing the image (debugfs)'); apply(a.out)
add_oat_dirs(a.out)

# 10 Google apps ----------------------------------------------------------------------------------------------------------------
def add_gapps(img):
    """Same selection as tools/scripts/install_gapps.sh (no Setup Wizard, Velvet, Speech services, Wellbeing); the list is kept in /system/etc/gapps-installed.txt"""
    keep_apps = ['GmsCore', 'Phonesky', 'GoogleServicesFramework', 'GooglePartnerSetup', 'GoogleCalendarSyncAdapter', 'GoogleContactsSyncAdapter', 'PrebuiltExchange3Google']
    root = wp('gapps'); shutil.rmtree(root, ignore_errors=True); zf = zipfile.ZipFile(a.gapps); files = []
    for i in zf.infolist():
        p = i.filename
        if i.is_dir() or not p.startswith(('system/product/', 'system/system_ext/')): continue
        parts = p.split('/')
        if len(parts) >= 5 and parts[2] in ('priv-app', 'app') and parts[3] not in keep_apps: continue
        if parts[2] == 'overlay' and parts[-1] == 'GmsSetupWizardOverlay.apk': continue
        if parts[2] == 'lib64': continue
        dst = os.path.join(root, *parts[1:]); os.makedirs(os.path.dirname(dst), exist_ok=True); open(dst, 'wb').write(zf.read(i)); files.append('/system/' + '/'.join(parts[1:]))
    made = set(); lst = []
    for f in sorted(files):
        d = os.path.dirname(f); chain = []
        while d not in ('/system', '/') and d not in made:
            chain.append(d); d = os.path.dirname(d)
        for d in reversed(chain):
            made.add(d)
            if not exists(img, d): mkdir(d)
        put(os.path.join(root, f[len('/system/'):]), f, '644')
        top = '/'.join(f.split('/')[:5]) if f.split('/')[3] in ('priv-app', 'app') else f     # apps as directories, everything else file by file (etc dirs are shared)
        if top not in lst: lst.append(top)
    put(tmpf('gapps-installed.txt', '\n'.join(lst) + '\n'), '/system/etc/gapps-installed.txt', '644')
    apply(img); print('  gapps:', len(files), 'files')
    add_oat_dirs(img)
if a.gapps:
    print('10 google apps')
    if a.out_gapps: shutil.copyfile(a.out, a.out_gapps)
    add_gapps(a.out_gapps or a.out)
if not a.keep_work and not a.workdir: shutil.rmtree(W, ignore_errors=True)
for p in filter(None, (a.out, a.out_gapps)): print('image:', p, os.path.getsize(p), 'bytes')
