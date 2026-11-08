#!/bin/sh
# Build secilc (SELinux CIL compiler) for macOS from upstream 3.7. Output: $OUT/secilc (default ./secilc)
# libsepol makes a Linux-style .so on macOS; link secilc against the .a instead. Needs network once.
set -e
OUT=${OUT:-$PWD/secilc}
W=$(mktemp -d "${TMPDIR:-/tmp}/sepol.XXXXXX")
cd "$W"
curl -sSL https://github.com/SELinuxProject/selinux/archive/refs/tags/3.7.tar.gz | tar xz
cd selinux-3.7
(cd libsepol && make -j8 CFLAGS="-O1 -Wno-everything -D_GNU_SOURCE=1" >/dev/null 2>&1 || true)   # test programs fail, the lib is fine
ln -s ../../cil/include/cil libsepol/include/sepol/cil
cd secilc
cc -O1 -Wno-everything -D_GNU_SOURCE=1 -I../libsepol/include -c secilc.c -o secilc.o
cc -o "$OUT" secilc.o ../libsepol/src/libsepol.a
echo "built $OUT"
