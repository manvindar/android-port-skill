# Runs on the tablet (sh). Compiles the apps in speed mode: Google apps first (Play services is the biggest background user; 'verify' leaves it
# interpreted), then the system apps, then everything else. About 10 to 15 minutes. DEXOPT_FORCE="" skips apps that are already compiled
# (the first-boot job uses that); the default -f recompiles.
F=${DEXOPT_FORCE--f}
# ART Service keeps using the verify-only copy that the first boot left in /data/dalvik-cache, even after a compile put a better one in <app dir>/oat/arm64
# (checked: the process maps the dalvik-cache vdex, not the speed odex). Deleting the stale copy makes the next process start use the odex.
fixcache() {
  pm list packages -f | sed 's/^package://; s/=[^=]*$//' | while read apk; do
    case $apk in /system/*|/product/*|/system_ext/*) ;; *) continue;; esac   # not /vendor: its Android 10 odex is rejected by this ART, so the dalvik-cache copy made by a compile is the one in use
    d=${apk%/*}; b=${apk##*/}; b=${b%.apk}
    [ -f "$d/oat/arm64/$b.odex" ] || continue
    rm -f /data/dalvik-cache/arm64/$(echo "${apk#/}" | sed 's|/|@|g')@classes.*
  done
}
# the parts of the UI that are on screen all the time first: SystemUI (notification shade, quick settings), the launcher and Settings
for p in com.android.systemui com.google.android.apps.nexuslauncher com.android.launcher3 com.android.settings com.google.android.apps.wallpaper.pixel; do
  pm path $p >/dev/null 2>&1 && { echo $p; cmd package compile -m speed $F $p; }
done
fixcache
# a compiled app only runs the new code after its process restarts (first boot job: nobody is using the shade yet, the setup wizard and Settings survive)
[ -z "$F" ] && killall com.android.systemui com.google.android.apps.nexuslauncher 2>/dev/null
for p in com.google.android.gms com.android.vending com.google.android.gsf com.google.android.apps.maps com.google.android.youtube com.google.android.apps.wallpaper com.google.android.apps.nexuslauncher com.google.android.contacts com.google.android.calendar com.google.android.calculator com.google.android.deskclock com.google.android.apps.nbu.files; do
  pm path $p >/dev/null 2>&1 && { echo $p; cmd package compile -m speed $F $p; }
done
for p in com.android.inputmethod.latin com.google.android.inputmethod.latin com.google.android.apps.messaging com.google.android.apps.photos com.google.android.googlequicksearchbox com.google.android.settings.intelligence com.android.phone com.android.permissioncontroller com.android.providers.media.module com.android.providers.settings; do echo $p; cmd package compile -m speed $F $p; done
cmd package compile -m speed -a $F
fixcache
echo DONE
