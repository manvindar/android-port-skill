#!/bin/sh
# host-side check of the sysfs mapping, the level correction and the HealthInfo parcel layout (no device, no Android classes): sh tools/health/test.sh
set -e
cd "$(dirname "$0")"; rm -rf out/test; mkdir -p out/test
javac -d out/test src/HealthCore.java test/CoreTest.java
java -cp out/test shim.CoreTest
