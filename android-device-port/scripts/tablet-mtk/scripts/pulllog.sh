#!/bin/bash
# pulllog.sh N: wait for TWRP, pull bootdiag (skip big files), print bpf/netd/reboot-relevant lines of the last boot
A=~/Library/Android/sdk/platform-tools/adb; cd ~/Aistuff/android-aosp/work/a17/logs; N=$1
for i in $(seq 1 20); do $A devices | grep -q recovery && break; sleep 2; done
rm -rf d$N; mkdir d$N
$A shell 'mount | grep -q " /data " || mount /dev/block/by-name/userdata /data'
$A pull /data/local/tmp/bootdiag/kmsg.txt d$N/ >/dev/null 2>&1; $A pull /data/local/tmp/bootdiag/logcat.txt d$N/ >/dev/null 2>&1
K=d$N/kmsg.txt; S=$(grep -a -n "init first stage started" $K | tail -1 | cut -d: -f1); tail -n +$S $K > d$N/last.txt; wc -l d$N/last.txt
