#!/system/bin/sh
# Boot diagnostics: everything lands in /data/local/tmp/bootdiag (readable from TWRP / adb); probes go to logcat as tag DIAG.
D=/data/local/tmp/bootdiag; mkdir -p $D; chmod 777 $D
logcat -b all -v threadtime -f $D/logcat.txt -r 16384 -n 4 &
cat /proc/kmsg >> $D/kmsg.txt 2>&1 &
while :; do
  for p in ro.vendor.api_level ro.board.api_level ro.board.first_api_level ro.product.first_api_level ro.vendor.build.version.sdk ro.build.version.sdk ro.vndk.version ro.product.vendor.name ro.treble.enabled; do
    log -t DIAG "$p=$(getprop $p)"
  done
  sleep 10
done
