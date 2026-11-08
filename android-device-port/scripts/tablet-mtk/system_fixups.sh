#!/bin/sh
# Live fixups applied over adb after a normal boot (run as: adb shell sh < tools/system_fixups.sh ; needs adb root = su context, /system remounted rw).
mount -o remount,rw /
# 1. slow device: scale AMS/Watchdog/ANR timeouts (Build.HW_TIMEOUT_MULTIPLIER)
grep -q hw_timeout_multiplier /system/build.prop || echo "ro.hw_timeout_multiplier=5" >> /system/build.prop
# 2. the Android 10 vendor's libhidlbase looks for passthrough HALs (android.hidl.memory@1.0-impl, ...) in /system/lib64/vndk-sp-29/hw; the A17 image has no such link
[ -e /system/lib64/vndk-sp-29 ] || ln -s /apex/com.android.vndk.v29/lib64 /system/lib64/vndk-sp-29
[ -e /system/lib/vndk-sp-29 ] || ln -s /apex/com.android.vndk.v29/lib /system/lib/vndk-sp-29
chcon -h u:object_r:system_lib_file:s0 /system/lib64/vndk-sp-29 /system/lib/vndk-sp-29
sync
