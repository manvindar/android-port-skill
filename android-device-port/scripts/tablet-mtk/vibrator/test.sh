#!/bin/sh
# host-side check of the timing and sysfs write logic (no device, no Android classes): sh tools/vibrator/test.sh
set -e
cd "$(dirname "$0")"; rm -rf out/test; mkdir -p out/test
javac -d out/test src/VibratorCore.java test/CoreTest.java
java -cp out/test shim.CoreTest
