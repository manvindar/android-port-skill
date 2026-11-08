#!/bin/sh
# Before/after check for a kernel change on the M30s, over adb: cold start time of a few apps, scroll jank in Settings, zram and pressure after a burst of app launches.
# usage: bench.sh OUT.txt [SERIAL]     (run with the phone idle: load average < 3, screen on and unlocked)
OUT=${1:-bench.txt}; S=${2:?adb serial}
a() { "${ADB:-$HOME/Library/Android/sdk/platform-tools/adb}" -s "$S" "$@"; }
{
echo "== $(date) kernel: $(a shell uname -r) $(a shell uname -v | tr -d '\r')"
echo "load: $(a shell cat /proc/loadavg | tr -d '\r')  tcp: $(a shell cat /proc/sys/net/ipv4/tcp_congestion_control | tr -d '\r')  zram: $(a shell cat /sys/block/zram0/comp_algorithm | tr -d '\r')"
a shell 'input keyevent 224; wm dismiss-keyguard; input keyevent 3'; sleep 2
for p in com.android.settings com.google.android.apps.messaging com.google.android.apps.photos com.android.chrome com.google.android.dialer com.google.android.calendar; do
  c=$(a shell "cmd package resolve-activity --brief -c android.intent.category.LAUNCHER $p | tail -1" | tr -d '\r')
  t=""
  for i in 1 2 3; do
    a shell "am force-stop $p; input keyevent 3; sync; echo 3 > /proc/sys/vm/drop_caches" >/dev/null; sleep 2
    v=$(a shell "am start -W -n $c | grep TotalTime" | tr -d '\r' | sed 's/.*: //'); t="$t $v"
  done
  echo "cold start $p ms:$t"
done
a shell 'am force-stop com.android.settings; am start -n com.android.settings/.Settings >/dev/null'; sleep 3
a shell 'dumpsys gfxinfo com.android.settings reset >/dev/null'
for i in 1 2 3 4 5 6 7 8 9 10; do a shell 'input swipe 540 1800 540 500 250; input swipe 540 500 540 1800 250'; done
a shell 'dumpsys gfxinfo com.android.settings' | grep -E "Total frames|Janky frames|50th|90th|95th|99th" | head -6
a shell 'input keyevent 3'
echo "zram mm_stat (orig compr mem_used limit same_pages ...): $(a shell cat /sys/block/zram0/mm_stat | tr -d '\r')"
a shell 'free -m | sed -n 2,3p'
a shell 'cat /proc/pressure/memory /proc/pressure/cpu /proc/pressure/io'
a shell 'grep -E "^(pswpin|pswpout|allocstall|pgmajfault) " /proc/vmstat'
} > "$OUT" 2>&1
cat "$OUT"
