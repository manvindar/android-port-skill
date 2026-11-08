#!/bin/sh
# Audio HAL 5.0 on Android 17 (experiment). The vendor audio HAL is HIDL 5.0, Android 17 removed libaudiohal@5.0 and its factory only probes 7.1/7.0/6.0.
# Take the Android 16 pieces and drop them into /system/lib64 (run in TWRP, system mounted rw at /mnt/s, files pushed to /tmp first):
#   libaudiohal.so (A16 factory; the A17 original is kept as libaudiohal.so.a17orig), libaudiohal@5.0.so (patched, see patch_audiohal50.py),
#   android.hardware.audio@5.0.so, android.hardware.audio@5.0-util.so, android.hardware.audio.common@5.0.so, android.hardware.audio.common@5.0-util.so,
#   android.hardware.audio.effect@5.0.so, android.hardware.audio.effect@5.0-util.so, android.media.audio.common.types-V4-cpp.so
# Result: AudioFlinger comes up and the MediaTek audio HAL opens; audioserver stays alive (no outputs).
for f in "$@"; do cat /tmp/$f > /mnt/s/system/lib64/$f; chmod 644 /mnt/s/system/lib64/$f; chown 0:0 /mnt/s/system/lib64/$f; chcon u:object_r:system_lib_file:s0 /mnt/s/system/lib64/$f; done
