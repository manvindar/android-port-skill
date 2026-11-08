#!/usr/bin/env python3
"""Build tools/pixel/overlay-m30s into a static framework overlay (M30sDisplayOverlay.apk) signed with the AOSP platform test key.
usage: make_m30s_overlay.py OUT.apk KEYDIR BUILD_TOOLS [PLATFORM_JAR]     (PLATFORM_JAR defaults to $ANDROID_HOME/platforms/android-34/android.jar)"""
import glob, os, subprocess, sys, tempfile
out, keys, bt = sys.argv[1:4]
here = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.environ.get('OVERLAY', 'overlay-m30s'))     # OVERLAY=overlay-m30s-wifi for the Wi-Fi resources overlay
jar = sys.argv[4] if len(sys.argv) > 4 else sorted(glob.glob(os.path.join(os.environ.get('ANDROID_HOME') or os.path.expanduser('~/Library/Android/sdk'), 'platforms/android-*/android.jar')))[-1]
t = tempfile.mkdtemp(); run = lambda *c: subprocess.run(c, check=True, capture_output=True)
run(os.path.join(bt, 'aapt2'), 'compile', '--dir', os.path.join(here, 'res'), '-o', t + '/res.zip')
run(os.path.join(bt, 'aapt2'), 'link', '-o', t + '/o.apk', '-I', jar, '--manifest', os.path.join(here, 'AndroidManifest.xml'), '--min-sdk-version', '34', '--target-sdk-version', '34', t + '/res.zip')
run(os.path.join(bt, 'zipalign'), '-p', '-f', '4', t + '/o.apk', t + '/a.apk')
run(os.path.join(bt, 'apksigner'), 'sign', '--key', os.path.join(keys, 'platform.pk8'), '--cert', os.path.join(keys, 'platform.x509.pem'), '--out', out, t + '/a.apk')
if os.path.exists(out + '.idsig'): os.remove(out + '.idsig')
print('overlay', out, os.path.getsize(out))
