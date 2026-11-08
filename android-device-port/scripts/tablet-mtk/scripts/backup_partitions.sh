#!/bin/bash
# Backs up the partitions you would need to get back to stock (and the ones MediaTek devices cannot rebuild: nvram, nvdata, proinfo, persist). Run with the tablet in TWRP
# (Volume Up + Volume Down while it starts) and adb connected. Output: ./tb-x606v-backup/<name>.img.gz. Keep these files; the flash scripts never write them.
set -e
ADB=${ADB:-adb}; OUT=${1:-tb-x606v-backup}; mkdir -p "$OUT"
$ADB devices | grep -q recovery || { echo "put the tablet in TWRP first"; exit 1; }
for n in boot recovery vbmeta lk dtbo logo nvcfg nvdata nvram persist proinfo protect1 protect2 seccfg boot_para system vendor product; do
  if $ADB shell "[ -e /dev/block/by-name/$n ]"; then echo "backing up $n"; $ADB exec-out "dd if=/dev/block/by-name/$n bs=1048576 2>/dev/null | gzip -1" > "$OUT/$n.img.gz"; fi
done
echo "backup in $OUT"
