#!/system/bin/sh
# Boot diagnostics (builder option --dev-tools): logcat of the whole boot into /data/local/tmp/bootdiag (readable from TWRP), the netbpfload tracer log, process list and properties.
# It stops 3 minutes after sys.boot_completed: a hung boot never gets there, and a permanent `logcat -f` plus the 5 and 10 second loops cost CPU and flash writes while the tablet is in use.
D=/data/local/tmp/bootdiag; mkdir -p $D; chmod 777 $D; rm -f $D/logcat.txt*
logcat -b all -v threadtime -f $D/logcat.txt -r 16384 -n 6 &
L=$!
( while :; do cp /dev/bpftrace.log /cache/bootdiag/bpftrace.log 2>/dev/null; sleep 5; done ) &
B=$!
after=0
while [ $after -lt 18 ]; do
  ps -A -o PID,PPID,NAME > $D/ps.txt 2>/dev/null; getprop > $D/props.txt 2>/dev/null
  [ "$(getprop sys.boot_completed)" = 1 ] && after=$((after + 1))
  sleep 10
done
kill $L $B 2>/dev/null
