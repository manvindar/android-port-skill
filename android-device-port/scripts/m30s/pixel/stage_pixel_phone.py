#!/usr/bin/env python3
"""Pixel phone (Pixel 9a "tegu") system_ext and product pieces for the GSI of the same build (DP11.261016.003), for the Galaxy M30s: SystemUI (SystemUIGoogle), Settings (SettingsGoogle), Pixel Launcher,
wallpaper picker and live wallpapers, themes and fonts, Setup Wizard, Google apps (Dialer, Messages, Contacts, Clock, Calendar, Calculator, Files, Photos, Gboard, Google app, Wellbeing, At a Glance), Chrome with its
WebView and the Pixel config overlays and boot animation. Adapted from the tablet's stage_pixel_tablet.py (same output layout, so build_a17.py can take it with --pixel-phone). Nothing is redistributable: run it on your own download.
usage: stage_pixel_phone.py FACTORY.zip OUT_DIR [--keys DIR] [--build-tools DIR] [--e2fs DIR] [--images DIR]   (--only TEXT: partial run (repeatable); --images: directory that already holds the unpacked product.img and system_ext.img)
The apps that need the platform certificate (SystemUI, Settings, launcher) are re-signed with the public AOSP platform test key (the GSI's platform certificate, zipalign first); every other app keeps Google's signature.
oat/, *.prof and fsverity metadata are left out (compiled for another boot image)."""
import argparse, glob, os, shutil, subprocess, sys, tempfile, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('factory'); ap.add_argument('out'); ap.add_argument('--keys', default=HERE); ap.add_argument('--build-tools'); ap.add_argument('--e2fs'); ap.add_argument('--images'); ap.add_argument('--only', action='append', help='partial run, repeatable: stage just the PKGS/FILES whose destination contains this text (no DIRS, no re-signing), to add apps to an existing stage dir')
a = ap.parse_args()
E2 = a.e2fs or next((d for d in ('/opt/homebrew/opt/e2fsprogs/sbin', '/usr/local/opt/e2fsprogs/sbin', '/sbin', '/usr/sbin') if os.path.exists(d + '/debugfs')), '')
BT = a.build_tools or sorted(glob.glob(os.path.expanduser('~/Library/Android/sdk/build-tools/*')) + glob.glob(os.environ.get('ANDROID_HOME', '/x') + '/build-tools/*'))[-1]
# (partition, dir in the Pixel image, destination dir under /system/<partition>/); the dir is copied whole, apk files listed in RESIGN are re-signed
PKGS = [
    ('system_ext', '/priv-app/SystemUIGoogle', 'priv-app/SystemUI'),                      # replaces the GSI's SystemUI (same package)
    ('system_ext', '/priv-app/SettingsGoogle', 'priv-app/Settings'),                      # replaces the GSI's Settings
    ('system_ext', '/priv-app/NexusLauncherRelease', 'priv-app/NexusLauncherRelease'),
    ('system_ext', '/priv-app/WallpaperPickerGoogleRelease', 'priv-app/WallpaperPickerGoogleRelease'),
    ('system_ext', '/priv-app/SetupWizardPixelPrebuilt_versioned', 'priv-app/SetupWizardPixelPrebuilt'),
    ('system_ext', '/priv-app/QuickAccessWallet', 'priv-app/QuickAccessWallet'),
    ('system_ext', '/priv-app/AvatarPickerGoogle', 'priv-app/AvatarPickerGoogle'),
    ('system_ext', '/priv-app/SystemUI-ScreenRecordingMarkup', 'priv-app/SystemUI-ScreenRecordingMarkup'),
    *[('system_ext', f'/priv-app/SystemUIClocks-{c}', f'priv-app/SystemUIClocks-{c}') for c in ('BigNum', 'Calligraphy', 'Growth', 'Inflate', 'Metro', 'NumOverlap', 'Weather')],
    ('product', '/priv-app/SetupWizardPrebuilt_versioned', 'priv-app/SetupWizardPrebuilt'),                 # config_defaultModuleMetadataProvider of the Pixel overlay (system_server aborts without it)
    ('product', '/priv-app/PrebuiltBugle', 'priv-app/PrebuiltBugle'),                     # Messages
    ('product', '/priv-app/GoogleDialer', 'priv-app/GoogleDialer'),
    ('product', '/priv-app/PrebuiltDeskClockGoogle_76112331', 'priv-app/PrebuiltDeskClockGoogle'),
    ('product', '/priv-app/FilesPrebuilt', 'priv-app/FilesPrebuilt'),
    ('product', '/priv-app/SettingsIntelligenceGooglePrebuilt', 'priv-app/SettingsIntelligenceGooglePrebuilt'),
    ('product', '/priv-app/PixelLiveWallpaperPrebuilt-27000055', 'priv-app/PixelLiveWallpaperPrebuilt'),
    ('product', '/priv-app/CustomizationBundlePrebuiltFullVersionStable', 'priv-app/CustomizationBundlePrebuilt'),    # Wallpaper & style bundles (colours, icon shapes, clock faces)
    ('product', '/priv-app/Velvet', 'priv-app/Velvet'),                                   # Google app (search bar, assistant)
    ('product', '/priv-app/DevicePersonalizationAiAiPrebuiltPixel2024', 'priv-app/DevicePersonalizationAiAiPrebuilt'),    # At a Glance
    ('product', '/priv-app/WeatherPixelPrebuilt_10008663', 'priv-app/WeatherPixelPrebuilt'),
    ('product', '/priv-app/WellbeingPrebuilt', 'priv-app/WellbeingPrebuilt'),
    ('product', '/priv-app/SearchSelectorPrebuilt', 'priv-app/SearchSelectorPrebuilt'),
    ('product', '/app/GoogleContacts', 'app/GoogleContacts'),
    ('product', '/app/CalendarGooglePrebuilt', 'app/CalendarGooglePrebuilt'),
    ('product', '/app/CalculatorGooglePrebuilt_85022643', 'app/CalculatorGooglePrebuilt'),
    ('product', '/app/Photos', 'app/Photos'),
    ('product', '/app/LatinIMEGooglePrebuilt', 'app/LatinIMEGooglePrebuilt'),             # Gboard
    ('product', '/app/PixelWallpapers2024a', 'app/PixelWallpapers2024a'),
    ('product', '/app/SoundPickerPrebuilt_3.4', 'app/SoundPickerPrebuilt'),
    ('product', '/app/PixelThemesStub2022_and_newer', 'app/PixelThemesStub'),
    ('product', '/app/ModuleMetadataGoogle', 'app/ModuleMetadataGoogle'),
    ('product', '/app/WallpaperEmojiPrebuilt-p26-foldable-wallpaper', 'app/WallpaperEmojiPrebuilt'),
    ('product', '/app/GoogleTTS', 'app/GoogleTTS'),
    ('product', '/app/MarkupGoogle_v2', 'app/MarkupGoogle'),
    # Chrome and its WebView (Trichrome: the library APK holds the native code for both)
    ('product', '/app/TrichromeLibrary', 'app/TrichromeLibrary'),
    ('product', '/app/Chrome', 'app/Chrome'),
    ('product', '/app/WebViewGoogle', 'app/WebViewGoogle'),
    # Play services, Play Store and the Services Framework come from MindTheGapps (build with --gapps): on the Pixel com.google.android.gms is a system APEX
]
# static overlays copied as they are (dest relative to /system/<partition>/); the tegu_beta__auto_generated ones are left out (they size apps for the 9a)
OVL = ['PixelConfigOverlayCommon', 'PixelConfigOverlay2018', 'PixelConfigOverlay2019', 'PixelConfigOverlay2019Midyear', 'PixelConfigOverlay2021', 'GoogleWebViewOverlay', 'GoogleConfigOverlay',
       'PixelSetupWizardOverlay2024', 'PixelSetupWizardOverlay2025Midyear', 'PixelSetupWizardOverlayExpressive', 'GooglePermissionControllerOverlay', 'GooglePermissionControllerSafetyCenterOverlay',
       'GoogleDeviceLockControllerOverlay', 'GoogleHealthConnectOverlay', 'IdentityCheckSettingsOverlay', 'ManagedProvisioningPixelOverlay', 'MessagingReadRestrictionAllowlistOverlay',
       'NetworkStackOverlay', 'VerifierResOverlay', 'TelecomOverlayDeprecatedGoogle', 'PixelTetheringOverlay2021', 'PixelConnectivityOverlay2024', 'AvatarPickerPixelOverlay',
       'WildlifeSettingsVpnOverlay2022', 'WildlifeSysuiVpnOverlay2022', 'SystemUIGXOverlay']
FILES = [('product', f'/overlay/{o}.apk', f'overlay/{o}.apk') for o in OVL] + [
         ('product', '/etc/fonts_customization.xml', 'etc/fonts_customization.xml'),
         ('product', '/media/bootanimation.zip', 'media/bootanimation-pixel.zip'),
         ('product', '/media/bootanimation-dark.zip', 'media/bootanimation-pixel-dark.zip')]
DIRS = [('product', '/fonts', 'fonts'), ('product', '/media/audio', 'media/audio'), ('product', '/media/vibration', 'media/vibration'), ('product', '/wallpaper', 'wallpaper'),
        ('product', '/etc/permissions', 'etc/permissions'), ('product', '/etc/sysconfig', 'etc/sysconfig'), ('product', '/etc/default-permissions', 'etc/default-permissions'),
        ('system_ext', '/etc/permissions', 'etc/permissions'), ('system_ext', '/etc/sysconfig', 'etc/sysconfig')]   # the Pixel's privileged-permission allowlists of the system_ext apps live here
# not re-signed: the wallpaper picker (its Theme packs tile asks a Google backend that rejects the AOSP test key copy) and everything else of Google's
RESIGN = ('system_ext/priv-app/SystemUI/SystemUIGoogle.apk', 'system_ext/priv-app/Settings/SettingsGoogle.apk', 'system_ext/priv-app/NexusLauncherRelease/NexusLauncherRelease.apk')
RENAME = {'system_ext/priv-app/SystemUI/SystemUIGoogle.apk': 'SystemUI.apk', 'system_ext/priv-app/Settings/SettingsGoogle.apk': 'Settings.apk'}
def sh(*c, **k): return subprocess.run(c, capture_output=True, text=True, **k)
def dump(img, src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    sh(os.path.join(E2, 'debugfs'), '-R', f'dump {src} {dst}', img)
    assert os.path.exists(dst) and os.path.getsize(dst) > 0, f'{src} not found in {img}'
def rdump(img, src, dst):
    os.makedirs(dst, exist_ok=True)
    r = sh(os.path.join(E2, 'debugfs'), '-R', f'rdump {src} {dst}', img)
    inner = os.path.join(dst, os.path.basename(src))                      # rdump creates DST/<basename>
    assert os.path.isdir(inner), f'{src} not found in {img}: {r.stderr[-200:]}'
    for r_, ds, fs in os.walk(inner, topdown=True):
        ds[:] = [d for d in ds if d != 'oat']
        for f in fs:
            if f.endswith(('.prof', '.fsv_meta')) or os.path.islink(os.path.join(r_, f)): os.remove(os.path.join(r_, f))     # symlinks point into the Pixel's partitions (TurboAdapter lib): the builder makes them
    shutil.rmtree(os.path.join(inner, 'oat'), ignore_errors=True)
    return inner
tmp = tempfile.mkdtemp(); out = os.path.abspath(a.out); shutil.rmtree(out, ignore_errors=True)
try:
    img = {}
    if a.images: img = {p: os.path.join(a.images, p + '.img') for p in ('system_ext', 'product')}
    else:
        z = zipfile.ZipFile(a.factory); inner = next(n for n in z.namelist() if '/image-' in n and n.endswith('.zip') or n.startswith('image-') and n.endswith('.zip'))
        z.extract(inner, tmp); iz = zipfile.ZipFile(os.path.join(tmp, inner))
        for p in ('system_ext', 'product'): iz.extract(p + '.img', tmp); img[p] = os.path.join(tmp, p + '.img')
        os.remove(os.path.join(tmp, inner))
    sel = lambda l: [x for x in l if not a.only or any(o in x[2] for o in a.only)]
    for part, src, dst in sel(PKGS):
        d = rdump(img[part], src, os.path.join(tmp, 'x'))
        target = os.path.join(out, part, dst); os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(d, target); shutil.rmtree(d)
    for part, src, dst in sel(FILES): dump(img[part], src, os.path.join(out, part, dst))
    for part, src, dst in ([] if a.only else DIRS):
        d = rdump(img[part], src, os.path.join(tmp, 'x')); target = os.path.join(out, part, dst); os.makedirs(target, exist_ok=True)
        for n in os.listdir(d): shutil.move(os.path.join(d, n), os.path.join(target, n)) if not os.path.exists(os.path.join(target, n)) else None
        shutil.rmtree(d)
    # Chrome, TrichromeLibrary and WebViewGoogle ship as <App>.apk.gz (compressed system apps, normally unpacked from a stub package): unpack them in place
    if not a.only:
        import gzip
        for r_, _, fs in os.walk(out):
            for f in fs:
                if f.endswith('.apk.gz'):
                    with gzip.open(os.path.join(r_, f)) as zi_, open(os.path.join(r_, f[:-3]), 'wb') as zo_: shutil.copyfileobj(zi_, zo_)
                    os.remove(os.path.join(r_, f))
    # WebViewGoogle is arm64-only but declares multiArch: PackageManager refuses it on this phone (armeabi-v7a is supported too): "native libs don't support all the natively supported ABIs"
    if not a.only:
        wv = os.path.join(out, 'product/app/WebViewGoogle/WebViewGoogle.apk')
        subprocess.run([sys.executable, os.path.join(HERE, 'unset_multiarch.py'), wv, wv + '.new', a.keys, BT], check=True, capture_output=True); os.replace(wv + '.new', wv)
    # GoogleConfigOverlay names com.google.android.ext.services (a Google mainline APEX of the Pixel's system image, not in the GSI) as the required services extension package: PackageManagerService
    # then aborts system_server at boot. The GSI has the AOSP one, android.ext.services (inside APEX com.android.extservices): rewrite the string in place (shorter, so the string pool stays valid) and re-sign
    if not a.only:
        ov = os.path.join(out, 'product/overlay/GoogleConfigOverlay.apk'); old = b'\x1f\x1fcom.google.android.ext.services\x00'; new = b'\x14\x14android.ext.services\x00'.ljust(len(old), b'\x00')
        zi = zipfile.ZipFile(ov); arsc = zi.read('resources.arsc'); assert arsc.count(old) == 1, 'ext.services string not found once in GoogleConfigOverlay'
        tmpz = ov + '.new'
        with zipfile.ZipFile(tmpz, 'w') as zo:
            for i in zi.infolist():
                if i.filename.startswith('META-INF/'): continue                                       # the old signature is void
                zo.writestr(zipfile.ZipInfo(i.filename, i.date_time), arsc.replace(old, new) if i.filename == 'resources.arsc' else zi.read(i), compress_type=zipfile.ZIP_STORED if i.filename == 'resources.arsc' else i.compress_type)
        zi.close(); subprocess.run([os.path.join(BT, 'zipalign'), '-p', '-f', '4', tmpz, ov + '.al'], check=True); os.remove(tmpz)
        subprocess.run([os.path.join(BT, 'apksigner'), 'sign', '--key', os.path.join(a.keys, 'platform.pk8'), '--cert', os.path.join(a.keys, 'platform.x509.pem'), '--out', ov, ov + '.al'], check=True, capture_output=True)
        os.remove(ov + '.al'); os.path.exists(ov + '.idsig') and os.remove(ov + '.idsig')
    # the M30s panel has rounded corners and the Pixel 9a's auto-generated overlay (its corner/padding values) is not staged: a static framework overlay gives the status bar content a corner padding
    if not a.only:
        subprocess.run([sys.executable, os.path.join(HERE, 'make_m30s_overlay.py'), os.path.join(out, 'product/overlay/M30sDisplayOverlay.apk'), a.keys, BT], check=True, capture_output=True)
        subprocess.run([sys.executable, os.path.join(HERE, 'make_m30s_overlay.py'), os.path.join(out, 'product/overlay/M30sWifiOverlay.apk'), a.keys, BT], check=True, capture_output=True, env=dict(os.environ, OVERLAY='overlay-m30s-wifi'))     # config_wifi5ghzSupport=true: 5 GHz hotspot
        os.makedirs(os.path.join(out, 'product/app/Precompile'), exist_ok=True)    # launcher icon + Quick Settings tile that start the on-device compile job (rc/04_precompile.rc)
        subprocess.run([sys.executable, os.path.join(HERE, 'make_precompile_app.py'), os.path.join(out, 'product/app/Precompile/Precompile.apk'), a.keys, BT], check=True, capture_output=True)
        os.makedirs(os.path.join(out, 'product/app/DisplayExtras'), exist_ok=True)    # launcher icon: screen mode (mdnie) and HDR format switches
        subprocess.run([sys.executable, os.path.join(HERE, 'make_precompile_app.py'), os.path.join(out, 'product/app/DisplayExtras/DisplayExtras.apk'), a.keys, BT], check=True, capture_output=True, env=dict(os.environ, APP='display-app'))
    for rel in ([] if a.only else RESIGN):
        f = os.path.join(out, rel)
        subprocess.run([os.path.join(BT, 'zipalign'), '-p', '-f', '4', f, f + '.al'], check=True)
        subprocess.run([os.path.join(BT, 'apksigner'), 'sign', '--key', os.path.join(a.keys, 'platform.pk8'), '--cert', os.path.join(a.keys, 'platform.x509.pem'), '--out', f, f + '.al'], check=True, capture_output=True)
        os.remove(f + '.al'); idsig = f + '.idsig'; os.path.exists(idsig) and os.remove(idsig)
        if rel in RENAME: os.rename(f, os.path.join(os.path.dirname(f), RENAME[rel]))
    tot = sum(os.path.getsize(os.path.join(r_, f)) for r_, _, fs in os.walk(out) for f in fs)
    print(f'staged {sum(len(fs) for _, _, fs in os.walk(out))} files, {tot >> 20} MB in {out}')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
