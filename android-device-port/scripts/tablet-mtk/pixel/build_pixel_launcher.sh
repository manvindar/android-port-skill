#!/bin/bash
# Build a Pixel Launcher (Android 17 build from APKMirror, versionCode 907) that runs on the TB-X606V's GSI.
#   build_pixel_launcher.sh PixelLauncher17.apk OUT.apk
# needs: apktool, Android build-tools (zipalign, apksigner, dexdump), python3. Output is signed with the public AOSP platform test key
# (the GSI is platform-signed with it), so signature permissions are granted. Install with install_pixel.sh.
set -e
D=$(cd "$(dirname "$0")" && pwd); IN=$1; OUT=$2; W=$(mktemp -d); BT=${BUILD_TOOLS:-$HOME/Library/Android/sdk/build-tools/35.0.0}
apktool d -r -f -o $W/s "$IN" >/dev/null
S=$W/s/smali; S2=$W/s/smali_classes2
# 1. framework flag enum constants this GSI no longer has -> an existing constant (desktop mode is unused here)
grep -rl 'ENABLE_DESKTOP_FIRST_BASED_DEFAULT_TO_DESKTOP_BUGFIX' $W/s/smali* | xargs sed -i.bak 's/DesktopExperienceFlags;->ENABLE_DESKTOP_FIRST_BASED_DEFAULT_TO_DESKTOP_BUGFIX/DesktopExperienceFlags;->ENABLE_PROJECTED_DISPLAY_DESKTOP_MODE/'
# 2. TaskSnapshotManager.takeTaskSnapshot(IZ) was renamed takeSystemTaskSnapshot(IZ)
grep -rl 'TaskSnapshotManager;->takeTaskSnapshot' $W/s/smali* | xargs sed -i.bak 's/TaskSnapshotManager;->takeTaskSnapshot/TaskSnapshotManager;->takeSystemTaskSnapshot/'
# 3. no SearchUiManager service on this GSI: skip creating the all-apps search session
python3 "$D/patch_search_session.py" $W/s
python3 "$D/patch_desktop_mode.py" $W/s
apktool b -f -o $W/b.apk $W/s >/dev/null
# 4. framework resource ids that moved between the launcher's build and this GSI (see remap_res_ids.py)
python3 "$D/remap_res_ids.py" $W/b.apk $W/r.apk 0x01050148=0x01050149 0x0105027b=0x0105027d 0x0105033a=0x0105033c 0x01050374=0x01050376 0x01050375=0x01050377
$BT/zipalign -p -f 4 $W/r.apk $W/a.apk
KEYS=${PLATFORM_KEY_DIR:-$D}
$BT/apksigner sign --key $KEYS/platform.pk8 --cert $KEYS/platform.x509.pem --v1-signing-enabled false --out "$OUT" $W/a.apk
rm -rf $W; echo "built $OUT"
