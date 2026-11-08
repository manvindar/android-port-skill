#!/bin/bash
# One-command install of the Android 17 image on a Lenovo TB-X606V (Tab M10 FHD Plus). WIPES ALL DATA on the tablet.
#
#   install_a17.sh system-a17-tb-x606v-gapps.img.xz            (or the -nogapps one, or an already unpacked .img)
#   options: --no-vbmeta   skip flashing the verification-disabled vbmeta
#            --no-vendor   skip the vendor edits (only if you already ran apply_vendor_a17.sh on this tablet)
#
# Before you start (once): bootloader unlocked, TWRP in the recovery partition, stock Android 10 firmware (tested on V9.56, TB-X606V_USR_S300665_2206300345_V9.56_BMP_ROW),
# USB debugging on, `adb` and `fastboot` installed (Android platform-tools), xz installed. Take the backup first: tools/scripts/backup_partitions.sh.
#
# What it does: (1) unpacks the image, (2) puts the tablet in the bootloader, (3) flashes a verification-disabled vbmeta, the system image, formats userdata, erases metadata and cache,
# (4) reboots into TWRP by itself and applies the vendor changes (apply_vendor_a17.sh), (5) boots Android. recovery, boot, lk, nvram and every other partition are left alone.
set -e
D=$(cd "$(dirname "$0")" && pwd); ADB=${ADB:-adb}; FB=${FASTBOOT:-fastboot}
IMG=; VBMETA=1; VENDOR=1
for a in "$@"; do case $a in --no-vbmeta) VBMETA=0;; --no-vendor) VENDOR=0;; *) IMG=$a;; esac; done
[ -f "$IMG" ] || { echo "usage: $0 system-a17-tb-x606v-gapps.img.xz [--no-vbmeta] [--no-vendor]"; exit 1; }
command -v $ADB >/dev/null && command -v $FB >/dev/null || { echo "adb and fastboot are required (Android platform-tools)"; exit 1; }
echo "This erases everything on the tablet (userdata). Type YES to continue:"; read -r ok; [ "$ok" = YES ] || exit 1
case $IMG in *.xz) echo "unpacking..."; xz -dkf "$IMG"; IMG=${IMG%.xz};; esac
[ "$(stat -f %z "$IMG" 2>/dev/null || stat -c %s "$IMG")" = 4085252096 ] || { echo "unexpected image size (expected 4085252096 bytes)"; exit 1; }
if $ADB devices | grep -q -w device; then $ADB reboot bootloader; fi
echo "waiting for fastboot (if nothing happens: power off, hold Power + Volume Down)..."
until $FB devices | grep -q fastboot; do sleep 2; done
[ $VBMETA = 1 ] && $FB --disable-verity --disable-verification flash vbmeta "$D/../vbmeta/vbmeta-disabled.img"
$FB flash system "$IMG"
$FB format:ext4 userdata
$FB erase metadata; $FB erase cache
if [ $VENDOR = 1 ]; then
  echo "rebooting into TWRP to edit the vendor partition..."; $FB reboot recovery
  until $ADB devices | grep -q recovery; do sleep 2; done
  "$D/apply_vendor_a17.sh"
  $ADB reboot
else $FB reboot; fi
echo "done. The first boot takes several minutes (Settings and the apps are precompiled in this image)."
