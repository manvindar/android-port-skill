#!/bin/bash
# usage: flashboot.sh RUN_ID   -> download kernel artifact, repack onto stock boot.img (+devkmsg), flash, reboot normally
set -e
RUN=$1; FB=~/Library/Android/sdk/platform-tools/fastboot; ADB=~/Library/Android/sdk/platform-tools/adb
D=~/Aistuff/android-aosp/work/kernel/run$RUN; rm -rf $D; mkdir -p $D; cd $D
gh run download $RUN -R manvindar/tb-x606v-kernel -n kernel >/dev/null
python3 -I ~/Aistuff/tb-x606v-kernel/scripts/repack_boot.py ~/Aistuff/android-aosp/work/kernel/stock/boot.img Image.gz-dtb boot.img - ~/Aistuff/android-aosp/work/kernel/dtb-a17.bin
if $ADB devices | grep -q recovery; then $ADB reboot bootloader; fi
for i in $(seq 1 25); do $FB devices | grep -q fastboot && break; sleep 3; done
$FB flash boot boot.img 2>&1 | tail -2
$FB reboot 2>&1 | tail -1
