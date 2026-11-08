#!/usr/bin/env python3
"""Pixel Tablet (tangorpro) system_ext and product pieces for the GSI of the same build: SystemUI (SystemUITitan), Settings (SettingsGoogle), Pixel Launcher, wallpapers and their picker,
Google Messages, Clock, Contacts, Calendar, Calculator, Files, Photos, Gboard, sounds, fonts, the Pixel config overlays and the Pixel boot animation. Taken from Google's factory image of the matching
Android 17 build (DP11.261016.003 for the GSI DP11.261016.003); nothing is redistributable, run it on your own download.
usage: stage_pixel_tablet.py FACTORY.zip OUT_DIR [--keys DIR] [--build-tools DIR] [--e2fs DIR] [--images DIR]   (--only TEXT: partial run (repeatable); --images: directory that already holds the unpacked product.img and system_ext.img)
OUT_DIR gets system_ext/... and product/... (paths under /system/system_ext and /system/product). The apps that need the platform certificate (SystemUI, Settings, launcher, wallpaper picker) are
re-signed with the public AOSP platform test key (the GSI's platform certificate, zipalign first); every other app keeps Google's signature. oat/, *.prof and fsverity metadata are left out
(compiled for another boot image)."""
import argparse, glob, os, shutil, subprocess, sys, tempfile, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('factory'); ap.add_argument('out'); ap.add_argument('--keys', default=HERE); ap.add_argument('--build-tools'); ap.add_argument('--e2fs'); ap.add_argument('--images'); ap.add_argument('--only', action='append', help='partial run, repeatable: stage just the PKGS/FILES whose destination contains this text (no DIRS, no re-signing), to add apps to an existing stage dir')
a = ap.parse_args()
E2 = a.e2fs or next((d for d in ('/opt/homebrew/opt/e2fsprogs/sbin', '/usr/local/opt/e2fsprogs/sbin', '/sbin', '/usr/sbin') if os.path.exists(d + '/debugfs')), '')
BT = a.build_tools or sorted(glob.glob(os.path.expanduser('~/Library/Android/sdk/build-tools/*')) + glob.glob(os.environ.get('ANDROID_HOME', '/x') + '/build-tools/*'))[-1]
# (partition, dir in the Pixel image, destination dir under /system/<partition>/); the dir is copied whole, apk files listed in RESIGN are re-signed
PKGS = [
    ('system_ext', '/priv-app/SystemUITitan', 'priv-app/SystemUI'),                       # replaces the GSI's SystemUI (same package)
    ('system_ext', '/priv-app/SettingsGoogle', 'priv-app/Settings'),                      # replaces the GSI's Settings
    ('system_ext', '/priv-app/NexusLauncherRelease', 'priv-app/NexusLauncherRelease'),
    ('system_ext', '/priv-app/WallpaperPickerGoogleRelease', 'priv-app/WallpaperPickerGoogleRelease'),
    ('product', '/priv-app/PrebuiltBugle', 'priv-app/PrebuiltBugle'),                     # Messages
    ('product', '/priv-app/PrebuiltDeskClockGoogle_76112331', 'priv-app/PrebuiltDeskClockGoogle'),
    ('product', '/priv-app/FilesPrebuilt', 'priv-app/FilesPrebuilt'),
    ('product', '/priv-app/SettingsIntelligenceGooglePrebuilt', 'priv-app/SettingsIntelligenceGooglePrebuilt'),
    ('product', '/priv-app/PixelLiveWallpaperPrebuilt-27000055', 'priv-app/PixelLiveWallpaperPrebuilt'),
    ('product', '/app/GoogleContacts', 'app/GoogleContacts'),
    ('product', '/app/CalendarGooglePrebuilt', 'app/CalendarGooglePrebuilt'),
    ('product', '/app/CalculatorGooglePrebuilt_85022643', 'app/CalculatorGooglePrebuilt'),
    ('product', '/app/Photos', 'app/Photos'),
    ('product', '/app/LatinIMEGooglePrebuilt', 'app/LatinIMEGooglePrebuilt'),             # Gboard
    ('product', '/app/PixelWallpapers2023Tablet', 'app/PixelWallpapers2023Tablet'),
    ('product', '/app/SoundPickerPrebuilt_3.4', 'app/SoundPickerPrebuilt'),
    ('product', '/app/PixelThemesStub2022_and_newer', 'app/PixelThemesStub'),
    ('product', '/app/ModuleMetadataGoogle', 'app/ModuleMetadataGoogle'),
    # The Pixel image has no Play services base APK to take (com.google.android.gms is a system APEX there; PrebuiltGmsCore holds only its modules), so Play services, Play Store and the Services Framework
    # come from MindTheGapps (build with --gapps). On top of them: the Google app (search bar, assistant), At a Glance and weather, Digital Wellbeing
    ('product', '/priv-app/Velvet', 'priv-app/Velvet'),
    ('product', '/priv-app/DevicePersonalizationAiAiPrebuiltPixelTablet2023', 'priv-app/DevicePersonalizationAiAiPrebuilt'),
    ('product', '/priv-app/WeatherPixelPrebuilt_10008663', 'priv-app/WeatherPixelPrebuilt'),
    ('product', '/priv-app/WellbeingPrebuilt', 'priv-app/WellbeingPrebuilt'),
    # the Pixel setup wizard (shown after a data wipe) with its tablet overlays
    ('system_ext', '/priv-app/SetupWizardPixelPrebuilt_versioned', 'priv-app/SetupWizardPixelPrebuilt'),
    ('product', '/priv-app/SetupWizardPrebuilt_versioned', 'priv-app/SetupWizardPrebuilt'),                 # config_defaultModuleMetadataProvider of the Pixel overlay (system_server aborts without it)
    # Hub mode (com.google.assistant.hubui, the glanceable hub and its dream; the Pixel's own allowlist com.google.assistant.hubui.xml comes with DIRS), its overlays are in FILES
    ('product', '/priv-app/SmartDisplayPrebuilt', 'priv-app/SmartDisplayPrebuilt'),
    # lock screen clocks (SystemUI plugins) and Device Health Services (battery data; TurboAdapter reads the power stats HAL)
    *[('system_ext', f'/priv-app/SystemUIClocks-{c}', f'priv-app/SystemUIClocks-{c}') for c in ('BigNum', 'Calligraphy', 'Growth', 'Inflate', 'Metro', 'NumOverlap', 'Weather')],
    ('product', '/priv-app/TurboPrebuilt', 'priv-app/TurboPrebuilt'),
    ('system_ext', '/priv-app/TurboAdapter', 'priv-app/TurboAdapter'),
    # theme packs: Wallpaper & style bundles (colours, icon shapes, clock faces) and the emoji wallpaper
    ('product', '/priv-app/CustomizationBundlePrebuiltFullVersionStable', 'priv-app/CustomizationBundlePrebuilt'),
    ('product', '/app/WallpaperEmojiPrebuilt-p26-foldable-wallpaper', 'app/WallpaperEmojiPrebuilt'),
]
# files and directories copied as they are (dest relative to /system/<partition>/)
FILES = [('product', '/overlay/PixelConfigOverlayCommon.apk', 'overlay/PixelConfigOverlayCommon.apk'),
         ('product', '/overlay/LargeScreenConfigOverlay.apk', 'overlay/LargeScreenConfigOverlay.apk'),
         ('product', '/overlay/PixelSetupWizardOverlayTangorpro.apk', 'overlay/PixelSetupWizardOverlayTangorpro.apk'),
         ('product', '/overlay/PixelSetupWizardOverlayExpressive.apk', 'overlay/PixelSetupWizardOverlayExpressive.apk'),
         # Hub mode overlays (static, no property gate). TitanConfigOverlay is not taken (gesture navigation, pinner files, user types): tools/pixel/TitanHubOverlay.apk replaces it, see docs/PIXEL.md
         ('product', '/overlay/GlanceableHubConfigOverlay.apk', 'overlay/GlanceableHubConfigOverlay.apk'),
         ('product', '/overlay/GlanceableHubSettingsConfigOverlay.apk', 'overlay/GlanceableHubSettingsConfigOverlay.apk'),
         ('product', '/overlay/GlanceableHubSysuiConfigOverlay.apk', 'overlay/GlanceableHubSysuiConfigOverlay.apk'),
         ('product', '/overlay/TitanSettingsOverlay.apk', 'overlay/TitanSettingsOverlay.apk'),
         ('product', '/overlay/TitanSysuiConfigOverlay.apk', 'overlay/TitanSysuiConfigOverlay.apk'),
         ('system_ext', '/lib64/libpowerstatshaldataprovider.so', 'lib64/libpowerstatshaldataprovider.so'),      # TurboAdapter's JNI lib (the Pixel links it from the app's lib/arm64)
         ('product', '/etc/fonts_customization.xml', 'etc/fonts_customization.xml'),
         ('product', '/media/bootanimation.zip', 'media/bootanimation-pixel.zip'),
         ('product', '/media/bootanimation-dark.zip', 'media/bootanimation-pixel-dark.zip')]
DIRS = [('product', '/fonts', 'fonts'), ('product', '/media/audio', 'media/audio'), ('product', '/wallpaper', 'wallpaper'),
        ('product', '/etc/permissions', 'etc/permissions'), ('product', '/etc/sysconfig', 'etc/sysconfig'), ('product', '/etc/default-permissions', 'etc/default-permissions')]
# The wallpaper picker is NOT re-signed: its Theme packs tile asks a Google backend, which answers PERMISSION_DENIED "Rejected by (1st-party only Allowlist) security policy.
# Not google-signed." for the AOSP-test-key copy, and the tile stays greyed. Its signature-level permissions are `preinstalled` or its own, so Google's signature is enough.
RESIGN = ('system_ext/priv-app/SystemUI/SystemUITitan.apk', 'system_ext/priv-app/Settings/SettingsGoogle.apk', 'system_ext/priv-app/NexusLauncherRelease/NexusLauncherRelease.apk')
RENAME = {'system_ext/priv-app/SystemUI/SystemUITitan.apk': 'SystemUI.apk', 'system_ext/priv-app/Settings/SettingsGoogle.apk': 'Settings.apk'}
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
