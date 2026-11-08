#!/bin/bash
# Compile the apps on the tablet in speed mode, from the computer (tablet booted, USB debugging on, adb in PATH or ADB=...). About 10 to 15 minutes.
# Run it after a flash (CI images carry no compiled code) and again after the Play Store updates Play services, Maps or YouTube.
# Usage: tools/scripts/dexopt_on_tablet.sh
set -e
ADB=${ADB:-adb}; D=$(cd "$(dirname "$0")" && pwd)
$ADB root >/dev/null 2>&1 || true; sleep 2
$ADB push "$D/dexopt_all.sh" /data/local/tmp/dexopt_all.sh >/dev/null
$ADB shell 'rm -f /data/local/tmp/dexopt.log; nohup sh /data/local/tmp/dexopt_all.sh > /data/local/tmp/dexopt.log 2>&1 &'
echo "compiling on the tablet (the log is /data/local/tmp/dexopt.log)..."
last=
until $ADB shell 'tail -1 /data/local/tmp/dexopt.log' 2>/dev/null | grep -q DONE; do
  cur=$($ADB shell 'grep -E "^[a-z]+\.[a-z0-9_.]+$" /data/local/tmp/dexopt.log | tail -1' 2>/dev/null | tr -d '\r')
  [ -n "$cur" ] && [ "$cur" != "$last" ] && echo "  $cur" && last=$cur
  sleep 15
done
echo "done. Status of the main apps:"
for p in com.google.android.gms com.android.vending com.android.settings com.android.systemui com.android.launcher3; do
  printf '  %-34s %s\n' $p "$($ADB shell "dumpsys package $p | grep -m1 'arm64: \[status'" 2>/dev/null | sed -E 's/.*status=([a-z-]+).*/\1/' | tr -d '\r')"
done
