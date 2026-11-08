#!/bin/sh
# Dump partitions from the phone while it is in TWRP (root adb). READ-ONLY on the phone.
# Usage: dump_partitions.sh OUT_DIR [small|big]     (default: small)
#   small = everything not in the firmware, plus boot/recovery/dtb/dtbo/vbmeta (about 300 MiB)
#   big   = system vendor product (about 5.7 GB; compare with the firmware hashes)
# Each partition is read TWICE and the two SHA-256 must match; the image is kept only then.
# Never writes to the phone, never touches /sdcard or the SD card. Always -s $ADB_SERIAL.
set -e
OUT=${1:?out dir}; SET=${2:-small}; S=${ADB_SERIAL:?set ADB_SERIAL to the adb serial}
ADB="$HOME/Library/Android/sdk/platform-tools/adb -s $S"
SMALL="efs sec_efs cpefs persistent keyrefuge keydata steady uhcfg nad_refer nad_fw dqmdbg misc bota0 bota1 bota2 bota3 param up_param keystorage uh omr radio cp_debug boot recovery dtb dtbo vbmeta"
BIG="system vendor product"
case $SET in small) LIST=$SMALL;; big) LIST=$BIG;; *) echo "small|big"; exit 2;; esac
mkdir -p "$OUT"
$ADB shell 'id -u' | grep -q '^0' || { echo "not root: boot TWRP first"; exit 1; }
for p in $LIST; do
  if ! $ADB shell "test -e /dev/block/by-name/$p" ; then echo "SKIP $p (no such partition)"; continue; fi
  $ADB exec-out "dd if=/dev/block/by-name/$p bs=1048576 2>/dev/null" > "$OUT/$p.img"
  a=$(shasum -a 256 "$OUT/$p.img" | cut -d' ' -f1)
  b=$($ADB exec-out "dd if=/dev/block/by-name/$p bs=1048576 2>/dev/null" | shasum -a 256 | cut -d' ' -f1)
  if [ "$a" = "$b" ]; then echo "OK   $p $(wc -c < "$OUT/$p.img") $a"; echo "$a  $p.img" >> "$OUT/SHA256SUMS"
  else echo "DIFF $p ($a vs $b): partition changes while read? retry"; fi
done
