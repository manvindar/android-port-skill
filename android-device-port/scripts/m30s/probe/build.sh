#!/bin/sh
# Static arm64 build with the Android NDK clang (macOS host). Output: tools/probe/kprobe
set -e
NDK=$(ls -d "$HOME"/Library/Android/sdk/ndk/* | tail -1)
CC=$NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin/aarch64-linux-android30-clang
"$CC" -static -O1 -Wall -o "$(dirname "$0")/kprobe" "$(dirname "$0")/kprobe.c"
