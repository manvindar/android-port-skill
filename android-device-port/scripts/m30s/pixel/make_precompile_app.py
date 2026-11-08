#!/usr/bin/env python3
"""Build a small platform-signed app from tools/pixel/<APP> (default precompile-app: launcher icon + Quick Settings tile that starts the on-device compile job; display-app: Settings > Display entry) into an APK.
usage: [APP=precompile-app] make_precompile_app.py OUT.apk KEYDIR BUILD_TOOLS [PLATFORM_JAR]     (PLATFORM_JAR defaults to $ANDROID_HOME/platforms/android-*/android.jar, newest)"""
import glob, os, subprocess, sys, tempfile
out, keys, bt = sys.argv[1:4]
here = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.environ.get('APP', 'precompile-app'))
jar = sys.argv[4] if len(sys.argv) > 4 else sorted(glob.glob(os.path.join(os.environ.get('ANDROID_HOME') or os.path.expanduser('~/Library/Android/sdk'), 'platforms/android-*/android.jar')))[-1]
t = tempfile.mkdtemp(); run = lambda *c, **k: subprocess.run(c, check=True, capture_output=True, **k)
run(os.path.join(bt, 'aapt2'), 'link', '-o', t + '/o.apk', '-I', jar, '--manifest', os.path.join(here, 'AndroidManifest.xml'), '--min-sdk-version', '34', '--target-sdk-version', '34')
os.makedirs(t + '/cls'); run('javac', '--release', '17', '-classpath', jar, '-d', t + '/cls', *glob.glob(here + '/src/**/*.java', recursive=True))
run(os.path.join(bt, 'd8'), '--min-api', '34', '--lib', jar, '--output', t, *glob.glob(t + '/cls/**/*.class', recursive=True))
run('zip', '-j', t + '/o.apk', t + '/classes.dex')
run(os.path.join(bt, 'zipalign'), '-p', '-f', '4', t + '/o.apk', t + '/a.apk')
run(os.path.join(bt, 'apksigner'), 'sign', '--key', os.path.join(keys, 'platform.pk8'), '--cert', os.path.join(keys, 'platform.x509.pem'), '--out', out, t + '/a.apk')
if os.path.exists(out + '.idsig'): os.remove(out + '.idsig')
print('app', out, os.path.getsize(out))
