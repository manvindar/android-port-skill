#!/bin/sh
# builds lightsshim.jar (dex) from src/LightsShim.java
set -e
cd "$(dirname "$0")"; SDK=${ANDROID_HOME:-$HOME/Library/Android/sdk}; BT=${BUILD_TOOLS:-$SDK/build-tools/35.0.0}; AJ=$SDK/platforms/android-34/android.jar
rm -rf out; mkdir -p out/cls
javac --release 8 -cp "$AJ" -d out/cls src/LightsShim.java
$BT/d8 --release --min-api 29 --lib "$AJ" --output out out/cls/shim/LightsShim.class
cd out && zip -q lightsshim.jar classes.dex && echo built out/lightsshim.jar
