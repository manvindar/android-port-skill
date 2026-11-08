#!/bin/bash
# wait up to 3 min for either adb (booted), or fastboot (failed)
FB=~/Library/Android/sdk/platform-tools/fastboot; ADB=~/Library/Android/sdk/platform-tools/adb
for i in $(seq 1 60); do
  if $FB devices | grep -q fastboot; then echo FASTBOOT; exit 0; fi
  if $ADB devices | grep -w -q device; then echo ADB-DEVICE; exit 0; fi
  sleep 3
done; echo NEITHER
