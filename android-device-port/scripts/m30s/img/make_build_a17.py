#!/usr/bin/env python3
"""Derive build_a17.py (Galaxy M30s, SM-M307F) from the tablet's build_image17.py by exact text substitutions.
The tablet repo (~/Aistuff/tb-x606v-android17, read-only) stays the source of the patch tools (its tools/ dir); only the builder is forked here.
usage: make_build_a17.py [TABLET_REPO] > build_a17.py      (every substitution asserts that its anchor exists, so a changed upstream fails loudly)"""
import os, sys
repo = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/Aistuff/tb-x606v-android17')
s = open(os.path.join(repo, 'build', 'build_image17.py')).read()
n = 0
def sub(old, new, count=1):
    global s, n
    assert s.count(old) >= 1, 'anchor not found: ' + old[:80]
    s = s.replace(old, new) if count == 0 else s.replace(old, new, count); n += 1

sub('"""Android 17 (Google aosp_arm64 GSI DP11.261002.005) -> TB-X606V system image: every change that was applied to the tested tablet, rebuilt offline.',
    '"""Android 17 (Google aosp_arm64 GSI DP11.261016.003) -> Galaxy M30s (SM-M307F) system image. FORKED from the tablet builder by tools/img/make_build_a17.py (do not edit by hand).\nDifferences from the tablet: 4800 MiB partition, VNDK v30 + SELinux mapping 30.0 (from the Android 14 GSI, --vndk-dir) for the Android 11 Samsung vendor, Samsung identity props,\nno ROM Tuner (MediaTek only), no lights/vibrator shims in this first image (health shim kept), Bluetooth class of device of a phone.\nOriginal doc follows.\n\n(tablet text) Android 17 -> TB-X606V system image: every change that was applied to the tested tablet, rebuilt offline.')
sub("HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.join(HERE, '..', 'tools')",
    "HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.environ.get('A17_TOOLS') or os.path.expanduser('~/Aistuff/tb-x606v-android17/tools')")
sub("ap.add_argument('--out', required=True);",
    "ap.add_argument('--vndk-dir', required=True, help='dir with com.android.vndk.v30.apex, 30.0.cil, 30.0.compat.cil (from the Android 14 GSI)')\nap.add_argument('--out', required=True);")
sub("ap.add_argument('--no-tuner', action='store_true');", "ap.add_argument('--no-tuner', action='store_true', default=True);")
sub('PART = 0xf3800000', 'PART = 5033164800                                              # 4800 MiB: the M30s system partition')
sub('1  grow to the 0xf3800000-byte partition', '1  grow to the 5033164800-byte partition')

sub("ap.add_argument('--out', required=True);",
    "ap.add_argument('--a14fs', required=True, help='dir made by tools/img/make_a14fs.py (A14 first-stage init + libs, /init launcher, bpf tracer, lmkd)')\nap.add_argument('--out', required=True);")

# step 2: properties
sub("bp += 'persist.vendor.sys.pq.shp.idx=0\\n'     # MediaTek sharpening off by default: it makes video look worse (ROM Tuner > Picture quality changes it)\n", '')
sub("bp += 'persist.sysui.disableBlur=1\\n'     # window blur (Pixel Launcher drawer, shade) drops the GE8320 to ~17 fps: 72% janky frames with blur, 5% without\n",
    "bp += 'persist.sysui.disableBlur=1\\n'     # kept from the tablet: blur is expensive on a mid-range GPU (Mali-G72 here is untested)\n")
i = s.index("# stock-looking fingerprint assembled"); j = s.index("# the GSI ships no bluetooth.mk properties")
s = s[:i] + ("# the phone's real stock identity (vendor props of M307FXXS4CWC2)\n"
             "bp += ('ro.build.fingerprint=samsung/m30sdd/m30s:11/RP1A.200720.012/M307FXXS4CWC2:user/release-keys\\n'\n"
             "       'ro.build.description=m30sdd-user 11 RP1A.200720.012 M307FXXS4CWC2 release-keys\\n')\n"
             "bp += 'ro.hardware.egl=mali\\n'     # the Mali EGL loader looks for /vendor/lib64/egl/libGLES_mali.so by ro.hardware.egl; surfaceflinger aborts without an GLES implementation\n") + s[j:]
sub("bluetooth.device.class_of_device=90,2,12", "bluetooth.device.class_of_device=5a,02,0c")
sub("Tablet without telephony or LE Audio.", "Phone (class of device 0x5a020c); LE Audio left off.")
sub("(('brand', 'Lenovo'), ('device', 'achilles6_row_call'), ('manufacturer', 'LENOVO'), ('model', 'Lenovo TB-X606V'), ('name', 'full_achilles6_row_call'))",
    "(('brand', 'samsung'), ('device', 'm30s'), ('manufacturer', 'samsung'), ('model', 'SM-M307F'), ('name', 'm30sdd'))")
sub("# the tablet reports its real identity", "# the phone reports its real identity")

# step 4: VNDK 30 from --vndk-dir
sub("vndk = cat(a.donor, '/system/system_ext/apex/com.android.vndk.v29.apex'); assert len(vndk) > 50_000_000",
    "vndk = open(os.path.join(a.vndk_dir, 'com.android.vndk.v30.apex'), 'rb').read(); assert len(vndk) > 50_000_000")
sub("put(tmpf('vndk29.apex', vndk), '/system/system_ext/apex/com.android.vndk.v29.apex', '644')", "put(tmpf('vndk30.apex', vndk), '/system/system_ext/apex/com.android.vndk.v30.apex', '644')")
sub("looks for passthrough HALs in /system/lib64/vndk-sp-29/hw", "looks for passthrough HALs in /system/lib64/vndk-sp-30/hw")
sub("symlink('/system/lib64/vndk-sp-29', '/apex/com.android.vndk.v29/lib64'); symlink('/system/lib/vndk-sp-29', '/apex/com.android.vndk.v29/lib')",
    "symlink('/system/lib64/vndk-sp-30', '/apex/com.android.vndk.v30/lib64'); symlink('/system/lib/vndk-sp-30', '/apex/com.android.vndk.v30/lib')")
sub("print(f'  mapping 29.0:", "print(f'  mapping 30.0:")
sub("put(tmpf('map29.cil', prune(cat(a.donor, '/system/etc/selinux/mapping/29.0.cil').decode('latin1'))), '/system/etc/selinux/mapping/29.0.cil', '644')",
    "put(tmpf('map30.cil', prune(open(os.path.join(a.vndk_dir, '30.0.cil'), encoding='latin1').read())), '/system/etc/selinux/mapping/30.0.cil', '644')")
sub("put(tmpf('map29c.cil', cat(a.donor, '/system/etc/selinux/mapping/29.0.compat.cil')), '/system/etc/selinux/mapping/29.0.compat.cil', '644')",
    "put(os.path.join(a.vndk_dir, '30.0.compat.cil'), '/system/etc/selinux/mapping/30.0.compat.cil', '644')")
sub("('/system/system_ext/etc/selinux/mapping/29.0.cil', '/system/system_ext/etc/selinux/mapping/29.0.compat.cil', '/system/product/etc/selinux/mapping/29.0.cil')",
    "('/system/system_ext/etc/selinux/mapping/30.0.cil', '/system/system_ext/etc/selinux/mapping/30.0.compat.cil', '/system/product/etc/selinux/mapping/30.0.cil')")
sub("print('4 vndk 29, selinux mapping, cgroups')", "print('4 vndk 30, selinux mapping, cgroups')")

# first-stage init bundle, NDK tracer/lmkd (SELinux permissive and BPF JIT come from the m30s-kernel release, no policy or netbpfload patch)
i = s.index("# 5 virt apex ---")
s = s[:i] + """# A17's init is second-stage only and the phone's boot.img has no ramdisk: /init is a launcher that runs Android 14's first-stage init (tools/img/make_a14fs.py)
print('A14 first stage bundle')
mkdir('/system/a14fs'); mkdir('/system/a14fs/lib64')
for f in ('init', 'linker64', 'launcher'): put(os.path.join(a.a14fs, f), '/system/a14fs/' + f, '755')
for f in sorted(os.listdir(os.path.join(a.a14fs, 'lib64'))): put(os.path.join(a.a14fs, 'lib64', f), '/system/a14fs/lib64/' + f, '644')
symlink('/init', '/system/a14fs/launcher', 'u:object_r:rootfs:s0')
if not a.pixel_phone: put(os.path.join(HERE, 'rc', '02_webview.rc'), '/system/etc/init/02_webview.rc', '644')    # picks the system WebView (the vendor GMS overlay leaves no default); the Pixel layer brings Chrome's WebView, which is the default
put(os.path.join(HERE, 'rc', '03_zram.rc'), '/system/etc/init/03_zram.rc', '644')    # swap: the stock vendor fstab has no zram
put(os.path.join(HERE, 'rc', '04_precompile.rc'), '/system/etc/init/04_precompile.rc', '644')    # the Precompile apps icon/tile starts it
put(os.path.join(HERE, 'rc', '05_gesture.rc'), '/system/etc/init/05_gesture.rc', '644')    # no ML back gesture: its TFLite lib is SIGILL on the Exynos 9611, SystemUI would crash-loop in gesture navigation
put(os.path.join(HERE, 'rc', '06_nosensorhog.rc'), '/system/etc/init/06_nosensorhog.rc', '644')    # GMS Personal Safety streamed the accelerometer at 100 Hz: system_server 26-55% CPU idle (docs/PERF.md)
if exists(S, '/system/product/etc/permissions/android.hardware.biometrics.face.xml'): cmds.append('rm /system/product/etc/permissions/android.hardware.biometrics.face.xml')    # face feature without a HAL: BiometricService spun on IVirtualHal (4 log lines/s)
""" + s[i:]

# netbpfload: the stock kernel has no BPF JIT, patch the "Kernel eBPF JIT failure" check out; tracer and lmkd come from make_a14fs.py (NDK builds)
sub("py('bpf/patch_binaries.py', 'netbpfload', nb, wp('netbpfload.a17'))",
    "py('bpf/patch_binaries.py', 'netbpfload', nb, wp('netbpfload.pre')); shutil.copyfile(wp('netbpfload.pre'), wp('netbpfload.a17'))")
sub("zigcc(os.path.join(TOOLS, 'bpf', 'netbpfload_tracer.c'), wp('tracer')); zigcc(os.path.join(TOOLS, 'lmkd', 'lmkd_inkernel.c'), wp('lmkd'))",
    "shutil.copy(os.path.join(a.a14fs, 'tracer'), wp('tracer')); shutil.copy(os.path.join(a.a14fs, 'lmkd'), wp('lmkd'))")

# Pixel phone layer (tools/pixel/stage_pixel_phone.py) -----------------------------------------------------------------------------
sub("ap.add_argument('--pixel-launcher-apk',", "ap.add_argument('--pixel-phone', help='directory made by tools/pixel/stage_pixel_phone.py (Pixel 9a SystemUI, Settings, launcher, Google apps, Chrome + WebView, overlays of the matching Android 17 build)')\nap.add_argument('--pixel-launcher-apk',")
sub("if priv_apks:\n    # a priv-app with a privileged permission", """if a.pixel_phone:
    print('9d Pixel phone layer')
    st = a.pixel_phone; SU = 'system_ext/priv-app/SystemUI/SystemUI.apk'; SE = 'system_ext/priv-app/Settings/Settings.apk'
    for dst, src in (('/system/' + SU, SU), ('/system/' + SE, SE)): replace(S, dst, os.path.join(st, src))         # same package, owner and label as the GSI's own apps
    staged = sorted(os.path.relpath(os.path.join(r, f), st) for r, _, fs in os.walk(st) for f in fs)
    new = [f for f in staged if f not in (SU, SE)]
    ensure_dirs('/system/' + f for f in new)
    for f in new: put(os.path.join(st, f), '/system/' + f, '644', 0, 0, LIB if '/lib64/' in f else SYS)
    # privileged permission allowlists: the Pixel's own xml files (both partitions) plus what the apps ask for beyond them
    for part in ('system_ext', 'product'):
        allow_xmls += [os.path.join(st, f) + ':' + part for f in staged if f.startswith(part + '/etc/permissions/') and f.endswith('.xml')]
    extra = os.path.join(HERE, '..', 'pixel', 'privapp-permissions-pixelphone-a17.xml')
    if os.path.exists(extra):
        for part in ('system_ext', 'product'): put(extra, f'/system/{part}/etc/permissions/privapp-permissions-pixelphone-a17.xml', '644'); allow_xmls.append(extra + ':' + part)
    priv_apks += [os.path.join(st, f) + (':system_ext' if f.startswith('system_ext/') else ':product') for f in staged if '/priv-app/' in f and f.endswith('.apk')]
    # Pixel boot animation (made for 1080x2424), fitted to the M30s panel (1080x2340)
    for pz, dsts in (('product/media/bootanimation-pixel.zip', ('bootanimation.zip',)), ('product/media/bootanimation-pixel-dark.zip', ('bootanimation-dark.zip',))):
        fitted = wp(os.path.basename(pz)); py(os.path.join('pixel', 'fit_bootanimation.py'), os.path.join(st, pz), fitted, 1080, 2340)
        for d in dsts: put(fitted, '/system/product/media/' + d, '644')
    # AOSP Provision is a second SETUP_WIZARD activity: with two, the Google wizard never gets the `setup` permissions
    cmds.append('rm /system/system_ext/priv-app/Provision/Provision.apk')
    put(os.path.join(TOOLS, 'pixel', 'pixel_home.sh'), '/system/bin/pixel_home.sh', '755')
    put(tmpf('zz_pixel_home.rc', open(os.path.join(TOOLS, 'pixel', 'zz_pixel_home.rc')).read()), '/system/etc/init/zz_pixel_home.rc', '644')
    put(os.path.join(TOOLS, 'pixel', 'wizard_lock_skip.sh'), '/system/bin/wizard_lock_skip.sh', '755')
    put(os.path.join(TOOLS, 'pixel', 'zz_wizard_lock_skip.rc'), '/system/etc/init/zz_wizard_lock_skip.rc', '644')
if priv_apks:
    # a priv-app with a privileged permission""")

# step 8: no lights / vibrator shims in the first image
i = s.index("run('sh', os.path.join(TOOLS, 'lights', 'build.sh')"); j = s.index("# health: same pattern")
s = s[:i] + "# lights and vibrator shims: not in the first M30s image (see docs/phase3prep/A17-BUILD.md); health shim below is kept\n" + s[j:]
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_a17.py'), 'w').write(s)
print(f'build_a17.py written, {n} substitutions', file=sys.stderr)
