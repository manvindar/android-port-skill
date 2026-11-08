#!/usr/bin/env python3
"""Build the fingerprint HAL shim (tools/fphal/shim) into a dex jar for app_process.
usage: make_fphal_jar.py OUT.jar BUILD_TOOLS [PLATFORM_JAR]     (PLATFORM_JAR defaults to $ANDROID_HOME/platforms/android-*/android.jar, newest)
The AIDL stubs are generated from tools/fphal/aidl-src (frozen AOSP snapshot). android.os.Hw* are compile-only stubs (shim/stubs), left out of the dex: the framework has the real ones."""
import glob, os, re, subprocess, sys, tempfile
out, bt = sys.argv[1:3]
here = os.path.dirname(os.path.abspath(__file__))
jar = sys.argv[3] if len(sys.argv) > 3 else sorted(glob.glob(os.path.join(os.environ.get('ANDROID_HOME') or os.path.expanduser('~/Library/Android/sdk'), 'platforms/android-*/android.jar')))[-1]
t = tempfile.mkdtemp()
def run(*c):
    r = subprocess.run(c, capture_output=True, text=True)
    if r.returncode: sys.exit(f'{c[0]} failed:\n{r.stdout}{r.stderr}')
src = os.path.join(here, 'aidl-src')
run(os.path.join(bt, 'aidl'), '--lang=java', '--structured', '--stability', 'vintf', '--min_sdk_version', '34', '-I', src, '-o', t + '/gen', *glob.glob(src + '/**/*.aidl', recursive=True))
for f in glob.glob(t + '/gen/**/*.java', recursive=True):   # Binder.markVintfStability is hidden: call it by reflection
    s = open(f).read()
    n = s.replace('this.markVintfStability();', 'try { android.os.Binder.class.getMethod("markVintfStability").invoke(this); } catch (ReflectiveOperationException e) { throw new RuntimeException(e); }')
    n = re.sub(r'@Override\s+public final int getStability\(\) \{[^}]*\}', '', n)   # Parcelable.PARCELABLE_STABILITY_VINTF is hidden; the default (local) is accepted everywhere
    n = n.replace('android.os.Parcelable.PARCELABLE_STABILITY_VINTF', '1')   # hidden constant
    if n != s: open(f, 'w').write(n)
os.makedirs(t + '/stubcls'); os.makedirs(t + '/cls')
run('javac', '--release', '17', '-classpath', jar, '-d', t + '/stubcls', *glob.glob(here + '/shim/stubs/**/*.java', recursive=True))
run('javac', '--release', '17', '-classpath', jar + os.pathsep + t + '/stubcls', '-d', t + '/cls', *glob.glob(t + '/gen/**/*.java', recursive=True), *glob.glob(here + '/shim/src/**/*.java', recursive=True))
run(os.path.join(bt, 'd8'), '--min-api', '34', '--lib', jar, '--output', t, *glob.glob(t + '/cls/**/*.class', recursive=True))
run('zip', '-j', '-q', t + '/o.jar', t + '/classes.dex')
os.replace(t + '/o.jar', out)
print('jar', out, os.path.getsize(out))
