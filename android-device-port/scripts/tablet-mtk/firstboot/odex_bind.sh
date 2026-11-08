#!/system/bin/sh
# /system is a full ext4 image with a few MB free, but ART (artd) writes the compiled code of a system app next to its APK (<app dir>/oat/arm64), so
# compiling SystemUI (about 100 MB) fails with "No space left on device" and the app stays interpreted. This bind mounts a directory on /data over the
# oat dir of every app (the empty mount points are in the image), before system_server scans packages (post-fs-data, blocking). Compiled code then lives in /data/odex and survives until a wipe.
D=/data/odex
mkdir -p $D
for a in /system/system_ext/priv-app/* /system/system_ext/app/* /system/product/priv-app/* /system/product/app/* /system/priv-app/* /system/app/*; do
  [ -d "$a" ] || continue
  n=$(echo "$a" | sed 's|^/system/||; s|/|_|g')
  [ -d "$a/oat" ] || continue          # / is read-only here: the builder puts an empty oat dir in every app dir
  grep -q " $a/oat " /proc/mounts && continue
  mkdir -p "$D/$n"
  chown system:system "$D/$n"; chmod 751 "$D/$n"
  mount -o bind "$D/$n" "$a/oat"
done
