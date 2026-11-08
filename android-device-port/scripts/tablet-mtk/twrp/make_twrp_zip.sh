#!/bin/bash
# Build the TWRP-installable zip from a system image.
#   tools/twrp/make_twrp_zip.sh system-a17-tb-x606v-gapps.img.xz OUT.zip [--no-wipe] [--vendor-only]
# --vendor-only builds a small zip without the system image (vendor edits, first-boot job, vbmeta only), useful to test the installer.
# The image must be the 4085252096-byte raw ext4 that install_a17.sh flashes (.xz or raw). Needs: zip, xz, shasum.
set -e
D=$(cd "$(dirname "$0")" && pwd); T=$D/..; IMG=$1; OUT=$2; shift 2 || { sed -n 2,6p "$0"; exit 1; }
WIPE=1; FLASH=1
for a in "$@"; do case $a in --no-wipe) WIPE=0;; --vendor-only) FLASH=0; WIPE=0;; esac; done
OUT=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
SPLIT_MB=1536; W=$(mktemp -d); mkdir -p $W/zip/META-INF/com/google/android $W/zip/payload $W/zip/system
cp $D/update-binary $D/updater-script $W/zip/META-INF/com/google/android/
cp $D/vendor_edits.sh $T/lights/vintf_light_aidl.xml $T/vibrator/vintf_vibrator_aidl.xml $T/health/vintf_health_aidl.xml $T/firstboot/firstboot_dexopt.sh $T/firstboot/zz_firstboot_dexopt.rc $T/scripts/dexopt_all.sh $T/vbmeta/vbmeta-disabled.img $W/zip/payload/
mv $W/zip/payload/vintf_light_aidl.xml $W/zip/payload/light_aidl.xml; mv $W/zip/payload/vintf_vibrator_aidl.xml $W/zip/payload/vibrator_aidl.xml; mv $W/zip/payload/vintf_health_aidl.xml $W/zip/payload/health_aidl.xml
SIZE=0; SHA=none
if [ $FLASH = 1 ]; then
  case $IMG in *.xz) echo "unpacking..."; xz -dc "$IMG" > $W/system.img;; *) cp "$IMG" $W/system.img;; esac
  SIZE=$(stat -f %z $W/system.img 2>/dev/null || stat -c %s $W/system.img); [ "$SIZE" = 4085252096 ] || { echo "unexpected image size $SIZE"; exit 1; }
  SHA=$(shasum -a 256 $W/system.img | cut -d' ' -f1)
  split -b ${SPLIT_MB}m $W/system.img $W/zip/system/system.img.; rm $W/system.img
fi
printf 'FLASH_SYSTEM=%s\nWIPE=%s\nIMG_SIZE=%s\nIMG_SHA256=%s\nSPLIT_MB=%s\n' $FLASH $WIPE $SIZE $SHA $SPLIT_MB > $W/zip/install.conf
rm -f "$OUT"; (cd $W/zip && rmdir system 2>/dev/null; zip -q -r -1 "$OUT" .)
rm -rf $W; ls -l "$OUT"
