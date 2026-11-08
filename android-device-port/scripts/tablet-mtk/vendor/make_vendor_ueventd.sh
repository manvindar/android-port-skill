#!/bin/sh
# Run in TWRP with the vendor partition mounted rw at /mnt/v2 (mount -t ext4 /dev/block/mmcblk0p36 /mnt/v2).
# Android 17's ueventd no longer reads /vendor/ueventd.rc; copy it to /vendor/etc/ueventd.rc and open /dev/ion
# (the stock kernel creates it 0600 root, so the vendor gralloc HAL, which runs as system, cannot open it).
{ cat /mnt/v2/ueventd.rc; echo; echo "/dev/ion 0666 system system"; } > /mnt/v2/etc/ueventd.rc
chmod 644 /mnt/v2/etc/ueventd.rc; chown 0:0 /mnt/v2/etc/ueventd.rc; chcon u:object_r:vendor_configs_file:s0 /mnt/v2/etc/ueventd.rc
