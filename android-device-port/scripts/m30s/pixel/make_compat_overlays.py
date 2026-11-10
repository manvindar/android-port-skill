#!/usr/bin/env python3
"""Build the two narrow M30s Pixel resource overlays with distinct public test identities."""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile

PLATFORM_CERT = 'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8'
SAFETY_CERT = '366f75e331af7cd858d44815dfc1e4f403b68093b7592ed71fd682b9f3af4cf7'
HERE = Path(__file__).resolve().parent


def certificate(path):
    data = subprocess.check_output(['openssl', 'x509', '-in', str(path), '-outform', 'DER'])
    return hashlib.sha256(data).hexdigest()


def build(out, platform_keys, safety_keys, bt, jar):
    configs = [
        ('M30sGestureOverlay.apk', 'overlay-m30s-gesture', platform_keys, 'platform', PLATFORM_CERT, 'platform'),
        ('M30sSafetyOverlay.apk', 'overlay-m30s-safety', safety_keys,
         'com.android.safetycenter.resources', SAFETY_CERT, 'safety'),
    ]
    # Check every signer before compiling either APK. No fallback to a different identity.
    for _, _, keys, stem, expected, label in configs:
        if certificate(Path(keys) / (stem + '.x509.pem')) != expected:
            raise ValueError(label + ' certificate mismatch')
        if not (Path(keys) / (stem + '.pk8')).is_file():
            raise ValueError(label + ' signing key missing')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, source, keys, stem, _, _ in configs:
        source = HERE / source
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            subprocess.run([str(Path(bt) / 'aapt2'), 'compile', '--dir', str(source / 'res'),
                            '-o', str(tmp / 'res.zip')], check=True)
            subprocess.run([str(Path(bt) / 'aapt2'), 'link', '-o', str(tmp / 'raw.apk'),
                            '-I', str(jar), '--manifest', str(source / 'AndroidManifest.xml'),
                            '--min-sdk-version', '37', '--target-sdk-version', '37',
                            str(tmp / 'res.zip')], check=True)
            subprocess.run([str(Path(bt) / 'zipalign'), '-p', '-f', '4',
                            str(tmp / 'raw.apk'), str(tmp / 'aligned.apk')], check=True)
            subprocess.run([str(Path(bt) / 'apksigner'), 'sign', '--key', str(Path(keys) / (stem + '.pk8')),
                            '--cert', str(Path(keys) / (stem + '.x509.pem')), '--v4-signing-enabled', 'false',
                            '--out', str(out / name), str(tmp / 'aligned.apk')], check=True)
    subprocess.run([sys.executable, str(HERE / 'verify_compat_overlays.py'), str(out), str(bt)], check=True)


if __name__ == '__main__':
    build(*sys.argv[1:])
