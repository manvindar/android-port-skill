#!/bin/sh
# Installs the virtual compass on the tablet over adb (no Magisk). Needs root (su) and a built out/ (sh build.sh).
#  /vendor/lib64/hw/sensors.mt6765.so      the shim; the original is kept next to it as sensors.mt6765.orig.so (vendor survives system reflashes)
#  /system/etc/compassd.jar, init/compassd.rc   the GPS course daemon (on a fresh system image this part comes from the image build)
# Undo: sh uninstall.sh
set -e
cd "$(dirname "$0")"
ADB="${ADB:-$HOME/Library/Android/sdk/platform-tools/adb} ${SERIAL:+-s $SERIAL}"
T=/data/local/tmp/compass-install
$ADB shell "mkdir -p $T" && $ADB push out/sensors.mt6765.so out/compassd.jar compassd.rc "$T/" >/dev/null
$ADB shell "su -c '
set -e
mount -o remount,rw /vendor; mount -o remount,rw /
H=/vendor/lib64/hw
stop vendor.sensors-hal-2-0
[ -f \$H/sensors.mt6765.orig.so ] || { cat \$H/sensors.mt6765.so > \$H/orig.tmp; chcon u:object_r:vendor_file:s0 \$H/orig.tmp; mv \$H/orig.tmp \$H/sensors.mt6765.orig.so; }
cat $T/sensors.mt6765.so > \$H/shim.tmp; chcon u:object_r:vendor_file:s0 \$H/shim.tmp; chmod 644 \$H/shim.tmp; mv \$H/shim.tmp \$H/sensors.mt6765.so
cat $T/compassd.jar > /system/etc/compassd.jar.tmp; chmod 644 /system/etc/compassd.jar.tmp; mv /system/etc/compassd.jar.tmp /system/etc/compassd.jar
cat $T/compassd.rc > /system/etc/init/compassd.rc.tmp; chmod 644 /system/etc/init/compassd.rc.tmp; mv /system/etc/init/compassd.rc.tmp /system/etc/init/compassd.rc
mkdir -p /data/local/tmp/compass; chmod 777 /data/local/tmp/compass
start vendor.sensors-hal-2-0
stop compassd 2>/dev/null; start compassd
echo installed
'"
