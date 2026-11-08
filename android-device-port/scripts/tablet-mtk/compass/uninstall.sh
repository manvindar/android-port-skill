#!/bin/sh
# Puts the original vendor sensors HAL back and removes the daemon. The sensor service picks the change up after the next framework restart or reboot.
set -e
ADB="${ADB:-$HOME/Library/Android/sdk/platform-tools/adb} ${SERIAL:+-s $SERIAL}"
$ADB shell "su -c '
mount -o remount,rw /vendor; mount -o remount,rw /
H=/vendor/lib64/hw
stop compassd 2>/dev/null; stop vendor.sensors-hal-2-0
[ -f \$H/sensors.mt6765.orig.so ] && { cat \$H/sensors.mt6765.orig.so > \$H/orig.tmp; chcon u:object_r:vendor_file:s0 \$H/orig.tmp; mv \$H/orig.tmp \$H/sensors.mt6765.so; rm -f \$H/sensors.mt6765.orig.so; }
rm -f /system/etc/compassd.jar /system/etc/init/compassd.rc /data/local/tmp/compass/active
start vendor.sensors-hal-2-0
echo restored
'"
