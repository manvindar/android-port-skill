#!/usr/bin/env python3
"""Google layer for the One UI image from PUBLIC sources only: WebView (Trichrome library + WebViewGoogle + GoogleWebViewOverlay, taken from Google's Pixel factory image) and
Play services, Play Store, Services Framework (MindTheGapps). No donor material. Same selection as the Pixel image (tools/img/build_a17.py add_gapps, tools/pixel/stage_pixel_phone.py).
usage: stage_google.py PRODUCT.img GAPPS.zip OUT_DIR --keys DIR --build-tools DIR [--e2fs DIR] [--unset-multiarch FILE]
  PRODUCT.img  the Pixel factory image's product.img (ext4; `getprod.py` streams just that file out of the factory zip)
  OUT_DIR      gets product/{app,priv-app,overlay,etc,framework} and system_ext/{priv-app,etc}; build_oneui_port.py --google-stage puts product/ under /product and system_ext/ under /system/system_ext
  --keys       dir with platform.pk8/.x509.pem (the public AOSP test key) for unset_multiarch.py"""
import argparse, glob, gzip, os, shutil, subprocess, sys, tempfile, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('product'); ap.add_argument('gapps'); ap.add_argument('out'); ap.add_argument('--keys', required=True); ap.add_argument('--build-tools', required=True)
ap.add_argument('--e2fs', default='/opt/homebrew/opt/e2fsprogs/sbin'); ap.add_argument('--unset-multiarch', default=os.path.expanduser('~/Aistuff/m30s-port-main/tools/pixel/unset_multiarch.py'))
a = ap.parse_args(); out = os.path.abspath(a.out); shutil.rmtree(out, ignore_errors=True); tmp = tempfile.mkdtemp()
def rdump(src, dst):
    os.makedirs(dst, exist_ok=True)
    subprocess.run([os.path.join(a.e2fs, 'debugfs'), '-R', f'rdump {src} {dst}', a.product], capture_output=True)
    inner = os.path.join(dst, os.path.basename(src)); assert os.path.isdir(inner), f'{src} not in {a.product}'
    shutil.rmtree(os.path.join(inner, 'oat'), ignore_errors=True)
    for r, _, fs in os.walk(inner):
        for f in fs:
            if f.endswith(('.prof', '.fsv_meta')) or os.path.islink(os.path.join(r, f)): os.remove(os.path.join(r, f))
    return inner
try:
    # WebView: Trichrome (the library holds the native code for both Chrome and WebView) + WebViewGoogle, shipped as <App>.apk.gz
    for n in ('TrichromeLibrary', 'WebViewGoogle'):
        d = rdump('/app/' + n, os.path.join(tmp, 'x')); t = os.path.join(out, 'product/app', n); os.makedirs(os.path.dirname(t), exist_ok=True); shutil.copytree(d, t)
        for f in os.listdir(t):
            if f.endswith('.apk.gz'):
                with gzip.open(os.path.join(t, f)) as zi, open(os.path.join(t, f[:-3]), 'wb') as zo: shutil.copyfileobj(zi, zo)
                os.remove(os.path.join(t, f))
    wv = os.path.join(out, 'product/app/WebViewGoogle/WebViewGoogle.apk')     # arm64-only apk that declares multiArch: PackageManager refuses it on a phone that also supports armeabi-v7a
    subprocess.run([sys.executable, '-I', a.unset_multiarch, wv, wv + '.new', a.keys, a.build_tools], check=True, capture_output=True); os.replace(wv + '.new', wv)
    os.makedirs(os.path.join(out, 'product/overlay'), exist_ok=True)
    subprocess.run([os.path.join(a.e2fs, 'debugfs'), '-R', f'dump /overlay/GoogleWebViewOverlay.apk {out}/product/overlay/GoogleWebViewOverlay.apk', a.product], capture_output=True)
    assert os.path.getsize(os.path.join(out, 'product/overlay/GoogleWebViewOverlay.apk')) > 0
    # MindTheGapps: same selection as build_a17.py add_gapps (no Setup Wizard, Velvet, Speech services, Wellbeing); the Settings overlay targets AOSP Settings, One UI has its own
    keep = ('GmsCore', 'Phonesky', 'GoogleServicesFramework', 'GooglePartnerSetup', 'GoogleCalendarSyncAdapter', 'GoogleContactsSyncAdapter', 'PrebuiltExchange3Google')
    skip_ovl = ('GmsSetupWizardOverlay.apk', 'GmsSettingsOverlay.apk')
    zf = zipfile.ZipFile(a.gapps); n = 0
    for i in zf.infolist():
        p = i.filename
        if i.is_dir() or not p.startswith(('system/product/', 'system/system_ext/')): continue
        parts = p.split('/')
        if len(parts) >= 5 and parts[2] in ('priv-app', 'app') and parts[3] not in keep: continue
        if parts[2] == 'overlay' and parts[-1] in skip_ovl: continue
        if parts[2] == 'lib64': continue
        dst = os.path.join(out, *parts[1:]); os.makedirs(os.path.dirname(dst), exist_ok=True); open(dst, 'wb').write(zf.read(i)); n += 1
    tot = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(out) for f in fs)
    print(f'staged {sum(len(fs) for _, _, fs in os.walk(out))} files, {tot >> 20} MiB in {out} (gapps files {n})')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
