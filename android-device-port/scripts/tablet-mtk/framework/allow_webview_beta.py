#!/usr/bin/env python3
"""Adds WebView Beta (com.google.android.webview.beta) to the WebView providers this ROM accepts, so Developer options (or
`cmd webviewupdate set-webview-implementation`) can select it. The list is res/xml/config_webview_packages.xml inside /system/framework/framework-res.apk.
A provider that is not a system app needs the base64 of its signing certificate in <signature>. Use only the FIRST certificate apksigner prints:
a Chrome APK is signed with a lineage of two, and putting both into <signature> gives "bad base-64" in WebViewProviderInfo, which kills system_server at boot.
The result is signed with the platform test key (same certificate as the original) and has to be written from TWRP into /system/framework/framework-res.apk
with `cat new > file` (the partition is full, and a running system keeps the old file mapped).
The second argument is either the Beta APK (the certificate is read from it) or a file with that base64 certificate (`chrome_webview_cert.b64` next to this script holds the public Chrome signing certificate).
usage: allow_webview_beta.py framework-res.apk beta-base.apk|chrome_webview_cert.b64 platform.pk8 platform.x509.pem out.apk   (build-tools 35 on PATH or in ~/Library/Android/sdk)"""
import base64, os, re, subprocess, sys, tempfile, zipfile
fr, beta, key, crt, out = sys.argv[1:6]
BT = os.environ.get('BUILD_TOOLS') or os.path.expanduser('~/Library/Android/sdk/build-tools/35.0.0')
PL = os.environ.get('ANDROID_JAR') or os.path.expanduser('~/Library/Android/sdk/platforms/android-34/android.jar')
if beta.endswith('.apk'):
    pem = subprocess.run([BT + '/apksigner', 'verify', '--print-certs-pem', beta], capture_output=True, text=True).stdout
    cert = ''.join(re.findall(r'-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----', pem, re.S)[0].split())
else:
    cert = ''.join(open(beta).read().split())
base64.b64decode(cert, validate=True)
xml = f'''<?xml version="1.0" encoding="utf-8"?>
<webviewproviders>
    <webviewprovider description="Android WebView" packageName="com.android.webview" availableByDefault="true" />
    <webviewprovider description="Chrome WebView Beta" packageName="com.google.android.webview.beta" availableByDefault="true">
        <signature>{cert}</signature>
    </webviewprovider>
</webviewproviders>
'''
t = tempfile.mkdtemp(); os.makedirs(t + '/res/xml'); open(t + '/res/xml/config_webview_packages.xml', 'w').write(xml)
open(t + '/m.xml', 'w').write('<?xml version="1.0" encoding="utf-8"?><manifest xmlns:android="http://schemas.android.com/apk/res/android" package="org.tablet.xmlbuild"><application/></manifest>')
run = lambda *a: subprocess.run(a, check=True, cwd=t, stderr=subprocess.DEVNULL)
run(BT + '/aapt2', 'compile', '--dir', 'res', '-o', 'res.zip'); run(BT + '/aapt2', 'link', '-o', 'x.apk', '-I', PL, '--manifest', 'm.xml', '--min-sdk-version', '29', '--target-sdk-version', '34', 'res.zip')
new = zipfile.ZipFile(t + '/x.apk').read('res/xml/config_webview_packages.xml')
zi = zipfile.ZipFile(fr); zo = zipfile.ZipFile(t + '/u.apk', 'w')
for i in zi.infolist():
    n = zipfile.ZipInfo(i.filename, date_time=i.date_time); n.compress_type = i.compress_type; n.external_attr = i.external_attr
    zo.writestr(n, new if i.filename == 'res/xml/config_webview_packages.xml' else zi.read(i.filename))
zo.close()
run(BT + '/zipalign', '-f', '4', 'u.apk', 'a.apk'); subprocess.run([BT + '/apksigner', 'sign', '--key', key, '--cert', crt, '--out', out, t + '/a.apk'], check=True, stderr=subprocess.DEVNULL)
print('wrote', out)
