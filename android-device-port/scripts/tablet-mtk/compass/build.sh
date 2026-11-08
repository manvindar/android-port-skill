#!/bin/sh
# builds out/sensors.mt6765.so (the HAL shim, arm64) and out/compassd.jar (dex)
set -e
cd "$(dirname "$0")"; SDK=${ANDROID_HOME:-$HOME/Library/Android/sdk}; BT=${BUILD_TOOLS:-$SDK/build-tools/35.0.0}; AJ=$SDK/platforms/android-34/android.jar
NDK=${NDK:-$(ls -d $SDK/ndk/* | tail -1)}; CC=$NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin/aarch64-linux-android29-clang
rm -rf out; mkdir -p out/cls
$CC -shared -fPIC -O2 -Wall -Iinc -o out/sensors.mt6765.so src/shim.c -llog -ldl -lm
javac --release 8 -cp "$AJ" -d out/cls src/compass/*.java
$BT/d8 --release --min-api 29 --lib "$AJ" --output out out/cls/compass/*.class
(cd out && zip -q compassd.jar classes.dex && rm classes.dex) && echo built out/sensors.mt6765.so out/compassd.jar
