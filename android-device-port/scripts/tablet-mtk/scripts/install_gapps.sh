#!/bin/bash
# Installs MindTheGapps (Android 16 build, arm64) into the running system over adb: Google Play services, Play Store, Services Framework, the
# contact/calendar sync adapters, and the permission, sysconfig and overlay files they need. Setup Wizard is left out on purpose (the device is already set up).
#
#   install_gapps.sh [--zip FILE] [--with-velvet] [--with-speech] [--with-wellbeing] [--reboot]
#   install_gapps.sh --remove [--reboot]
#
# Needs: adb root, `gh` (to download the release) or --zip, python3. Free space on /system: GmsCore 187 MB + Phonesky 85 MB + a little (Google app +243 MB).
# Everything installed is listed in /system/etc/gapps-installed.txt on the device, which --remove uses. Do not wipe-flash over it without --remove.
set -e
ADB=${ADB:-$HOME/Library/Android/sdk/platform-tools/adb}
REPO=MindTheGapps/16.0.0-arm64
ZIP=; VELVET=0; SPEECH=0; WELL=0; REBOOT=0; REMOVE=0
while [ $# -gt 0 ]; do case $1 in
  --zip) ZIP=$2; shift;; --with-velvet) VELVET=1;; --with-speech) SPEECH=1;; --with-wellbeing) WELL=1;; --reboot) REBOOT=1;; --remove) REMOVE=1;;
  *) echo "unknown option $1"; exit 1;; esac; shift; done
$ADB root >/dev/null 2>&1 || true; sleep 1
$ADB get-state >/dev/null || { echo "no device"; exit 1; }
$ADB shell 'mount -o remount,rw /' >/dev/null

if [ $REMOVE = 1 ]; then
  $ADB shell 'if [ -f /system/etc/gapps-installed.txt ]; then while read p; do rm -rf "$p"; done < /system/etc/gapps-installed.txt; rm /system/etc/gapps-installed.txt; sync; echo removed; else echo "nothing recorded"; fi'
  [ $REBOOT = 1 ] && $ADB reboot; exit 0
fi

W=$(mktemp -d /tmp/gapps.XXXXXX)            # downloaded and extracted files are untrusted: own empty dir, python -I
if [ -z "$ZIP" ]; then
  TAG=$(gh release list -R $REPO --limit 1 --json tagName -q '.[0].tagName')
  (cd $W && gh release download "$TAG" -R $REPO -p '*.zip' -p '*.sha256sum')
  ZIP=$(ls $W/*.zip)
  [ "$(shasum -a 256 "$ZIP" | cut -d' ' -f1)" = "$(cut -d' ' -f1 $W/*.sha256sum)" ] || { echo "sha256 mismatch"; exit 1; }
fi
mkdir -p $W/x
WITH="velvet=$VELVET,speech=$SPEECH,well=$WELL" python3 -I - "$ZIP" $W/x <<'PY'
import os, sys, zipfile
zf, out = sys.argv[1:3]; opt = dict(kv.split('=') for kv in os.environ['WITH'].split(','))
keep_apps = ['GmsCore', 'Phonesky', 'GoogleServicesFramework', 'GooglePartnerSetup', 'GoogleCalendarSyncAdapter', 'GoogleContactsSyncAdapter', 'PrebuiltExchange3Google']
if opt['velvet'] == '1': keep_apps.append('Velvet')
if opt['speech'] == '1': keep_apps.append('SpeechServicesByGoogle')
if opt['well'] == '1': keep_apps.append('Wellbeing')
skip_overlay = ('GmsSetupWizardOverlay.apk',)
n = 0
for i in zipfile.ZipFile(zf).infolist():
    p = i.filename
    if i.is_dir() or not p.startswith(('system/product/', 'system/system_ext/')): continue
    parts = p.split('/')
    if len(parts) >= 5 and parts[2] in ('priv-app', 'app') and parts[3] not in keep_apps: continue
    if parts[2] == 'overlay' and parts[-1] in skip_overlay: continue
    if parts[2] == 'lib64': continue          # Google LatinIME JNI only, not needed
    dst = os.path.join(out, *parts[1:]); os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(zipfile.ZipFile(zf).read(i)); n += 1
print(n, 'files')
PY
NEED=$(du -sk $W/x | cut -f1); FREE=$($ADB shell "df -k /system | tail -1" | awk '{print $4}')
echo "need ${NEED} KB, free ${FREE} KB on /system"; [ "$FREE" -gt $((NEED + 51200)) ] || { echo "not enough space"; exit 1; }
$ADB shell 'rm -rf /data/local/tmp/gapps'; $ADB push $W/x /data/local/tmp/gapps >/dev/null
$ADB shell 'set -e; cd /data/local/tmp/gapps
: > /data/local/tmp/gapps.list
for top in product/priv-app product/app product/etc product/framework product/overlay system_ext/priv-app system_ext/etc; do
  [ -d $top ] || continue
  case $top in
    */etc) (cd $top && find . -type f) | sed "s|^\\.|/system/$top|" >> /data/local/tmp/gapps.list;;   # etc dirs are shared with the base system: record files only
    *) for e in $(ls $top); do echo /system/$top/$e >> /data/local/tmp/gapps.list; done;;
  esac
  mkdir -p /system/$top; cp -r $top/. /system/$top/
done
while read p; do chown -R 0:0 $p; chmod -R u=rwX,go=rX $p; chcon -R u:object_r:system_file:s0 $p; done < /data/local/tmp/gapps.list
cat /data/local/tmp/gapps.list > /system/etc/gapps-installed.txt; chmod 644 /system/etc/gapps-installed.txt
rm -rf /data/local/tmp/gapps /data/local/tmp/gapps.list; sync; echo installed; wc -l < /system/etc/gapps-installed.txt'
rm -rf $W
echo "Reboot to scan the new packages (the first boot takes a few minutes). Then: Settings > Accounts, and Play Store."
[ $REBOOT = 1 ] && $ADB reboot || true
