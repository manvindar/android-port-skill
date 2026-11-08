#!/bin/sh
# builds healthshim.jar (dex) from src/*.java
set -e
cd "$(dirname "$0")"; SDK=${ANDROID_HOME:-$HOME/Library/Android/sdk}; BT=${BUILD_TOOLS:-$SDK/build-tools/35.0.0}; AJ=$SDK/platforms/android-34/android.jar
rm -rf out; mkdir -p out/cls
javac --release 8 -cp "$AJ" -d out/cls src/*.java
$BT/d8 --release --min-api 29 --lib "$AJ" --output out out/cls/shim/*.class
cd out && zip -q healthshim.jar classes.dex && echo built out/healthshim.jar
