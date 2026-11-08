#!/system/bin/sh
# Development safety net (builder option --dev-tools): when the boot does not finish (no sys.boot_completed after 600 s, or system_server was replaced 4 times = crash loop), reboot into recovery
# (TWRP: adb works there, the logs written by bootdiag.sh are readable, fixes can be pushed without touching the buttons).
M=/data/local/tmp/.boot_ok
last=; n=0; t=0
while [ "$(getprop sys.boot_completed)" != 1 ]; do
  p=$(pidof system_server)
  if [ -n "$p" ] && [ "$p" != "$last" ]; then [ -n "$last" ] && n=$((n + 1)); last=$p; fi
  if [ $n -ge 4 ] || [ $t -ge 600 ]; then
    echo "watchdog: boot failed (system_server restarts=$n, ${t}s): rebooting into recovery" > /dev/kmsg
    setprop sys.powerctl reboot,recovery
    exit 0
  fi
  sleep 5; t=$((t + 5))
done
touch $M
