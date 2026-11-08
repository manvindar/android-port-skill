#!/system/bin/sh
# Compiles the apps in speed mode by itself after a data wipe. Started once per boot by zz_firstboot_dexopt.rc; does nothing when /data/local/tmp/.dexopt_done exists.
# Pass 1 runs a few minutes after boot, pass 2 about 45 minutes later, after the Play Store has updated Play services, Maps and YouTube (an update resets them to
# interpreted code). Apps that are already compiled are skipped (DEXOPT_FORCE empty). Log: /data/local/tmp/dexopt.log
# Network location (Wi-Fi positioning): without the setup wizard Play services has no location opt-in and its location app ops stay on "ignore", so
# its network location service refuses its own requests ("Appop Denial ... requires appop COARSE_LOCATION"). Once, when Play services is installed.
L=/data/local/tmp/.location_done
if [ ! -f $L ] && pm path com.google.android.gms >/dev/null 2>&1; then
  for p in ACCESS_FINE_LOCATION ACCESS_COARSE_LOCATION ACCESS_BACKGROUND_LOCATION NEARBY_WIFI_DEVICES; do pm grant com.google.android.gms android.permission.$p; done
  appops reset com.google.android.gms
  for o in COARSE_LOCATION FINE_LOCATION NEARBY_WIFI_DEVICES; do appops set --uid com.google.android.gms $o allow; done
  settings put secure google_location_accuracy_enabled 1
  settings put secure network_location_opt_in 1
  settings put global network_location_opt_in 1
  touch $L
fi
M=/data/local/tmp/.dexopt_done
[ -f $M ] && exit 0
export DEXOPT_FORCE=""
echo "$(date) firstboot dexopt pass 1" >> /data/local/tmp/dexopt.log
sleep 60
sh /system/bin/dexopt_all.sh >> /data/local/tmp/dexopt.log 2>&1
sleep 2700
echo "$(date) firstboot dexopt pass 2" >> /data/local/tmp/dexopt.log
sh /system/bin/dexopt_all.sh >> /data/local/tmp/dexopt.log 2>&1
touch $M
