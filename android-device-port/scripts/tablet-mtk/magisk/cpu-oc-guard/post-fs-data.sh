#!/system/bin/sh
# Runs before the zygote. Harmless on the stock kernel (2301000 is its top step).
P=/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq
i=0; while [ ! -w $P ] && [ $i -lt 20 ]; do sleep 1; i=$((i + 1)); done
echo 2301000 > $P
