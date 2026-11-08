# Flashing, verifying, wiping, rolling back

Both devices are flashed from TWRP over adb, never from the Android side. Contents: 1 rules, 2 entering recovery, 3 write and verify a system image, 4 vendor and boot, 5 selective wipe, 6 first boot, 7 rollback, 8 Samsung Download mode and Heimdall, 9 MTK fastboot notes.

## 1. Rules

- Ask the owner before flashing `system`, wiping userdata or rebooting into recovery. Approval for one flash is not approval for the next.
- Have the rollback image on the host and verified (hash) before you write anything.
- Never write `recovery`, modem, bootloader (`bota*`, `sboot`), `efs`, `cpefs`, `persist`, `nvram`.
- Never delete, overwrite, move or format anything under `/sdcard`, `/storage/*` or an SD card. On Samsung `/sdcard` is `/data/media` on the data partition: TWRP "Format Data" and "Wipe Data" delete it. Use the selective wipe in section 5.
- Back up first: `scripts/m30s/backup/dump_partitions.sh` reads each partition twice and keeps the image only if both SHA-256 agree. `adb pull` the media you care about and compare md5 against the device.
- The Mac or CI host needs more than 10 GB free; a 4.8 GB image plus its xz is easy to overrun.

## 2. Entering recovery

From Android: `adb reboot recovery` (works on both). From a hung or looping boot: hold Volume Up + Volume Down while connecting USB until TWRP appears (the owner has to do that; send one short numbered ask). In TWRP `adb devices` shows `recovery`, `adb shell` is root, `/data` is mounted (f2fs on M30s; FBE-encrypted `/data/local/tmp` is unreadable on the MTK tablet, readable on the M30s because the userdata fstab line had `fileencryption=ice` removed).

## 3. Write and verify a system image

```
cat system.img | adb exec-in 'dd of=/dev/block/by-name/system bs=1048576'
```
- `adb exec-in` is the raw-stdin variant of `adb shell`; plain `adb shell` corrupts binary stdin. TWRP's `dd` rejects `bs=4M`: give bytes (`bs=1048576`).
- The image must be exactly the partition size (M30s 5033164800 bytes = 4800 MiB, 1228800 4 KiB blocks; check with `blockdev --getsize64 /dev/block/by-name/system`). `e2fsck -fn image` must be clean and `shared_blocks` removed (a GSI ext4 with `shared_blocks` is read-only).
- A long single read through the TWRP shell is cut after about 700 MiB, so verify in 256 MiB windows (19 windows, the last one 192 MiB for 4800 MiB):
```
for i in $(seq 0 18); do n=256; [ $i = 18 ] && n=192
  adb exec-out "dd if=/dev/block/by-name/system bs=1048576 skip=$((i*256)) count=$n 2>/dev/null | sha256sum" | cut -c1-16; done
```
Compute the same on the host (`dd if=img bs=1048576 skip=.. count=256 | shasum -a 256`) and compare all 19.
- Streaming without an intermediate file (host disk tight): `cat part-* | xz -dc | adb exec-in 'dd of=/dev/block/by-name/system bs=1048576'`; verify from the SHA256SUMS of the release.
- Small fix without a reflash: mount `system` rw at `/s` in TWRP and `cat new > /s/path/file` (keeps inode and SELinux label; `adb push` and `sed -i` drop the label). Run `e2fsck -fn` afterwards. During a boot window the same works from Android: `adb root` is available on the ported builds, `mount -o remount,rw /`, push, `chcon` the label, `sync`. Every such live edit must be baked into the build script and hash-compared with a rebuilt image.
- Replace system libraries with a new file and `mv` on a running system; never overwrite in place.

## 4. Vendor and boot

- Vendor only when it changed (`vendor-a17.img`: MP2 codec removed, `/metadata` tmpfs line, ueventd, seccomp additions, AIDL health fragment). Same `dd`, same window check (vendor 600 MiB).
- Boot: `cat boot.img | adb exec-in 'dd of=/dev/block/by-name/boot bs=1048576'`. Keep the stock boot image; the M30s boot image is the stock header with the kernel Image swapped in (`scripts/kernel-build/repack_boot.py`, AVB footer kept, vbmeta disabled).
- vbmeta: flash a 4 KiB vbmeta with verification disabled (`vbmeta-disabled.img`) once.

## 5. Selective wipe (keeps `/data/media`)

When a new system makes the old `/data` unusable (different package state, different fingerprint templates) but the owner's files must stay:
```
adb shell 'cd /data && for d in * .[!.]*; do case "$d" in media|lost+found) ;; *) rm -rf "$d";; esac; done'
adb shell 'ls -A /data; ls /data/media/0 | wc -l'      # only media (and lost+found); same count as before
```
Never wipe from the Android UI or TWRP's wipe menu. This loses the user's apps, accounts, setup and enrolled fingerprints; say so in the OK request. If `userdata` was FBE and the fstab line still has `fileencryption=ice`, format is the only option and needs a separate OK.

Package signature mismatches: an app whose certificate changed between builds (an overlay or metadata package signed with a per-build keystore) is rejected on top of an old `/data`. After a clean flash always do the selective wipe, or `rm -rf /data/system/package_cache /data/dalvik-cache` at minimum.

## 6. First boot

`adb reboot`. The first boot builds the package cache (minutes) and dexopt runs for a long time afterwards: the phone is slow until it ends (`cmd package compile -m speed -a` by hand, or the `zz_firstboot_dexopt.rc` service). If adb never appears within about 60 s the device is looping before USB: go to `boot-diagnosis.md`. The ported builds turn on `ro.adb.secure=0` and adb root so a hung system can be inspected.

## 7. Rollback

Keep a known-good image per device (M30s: the Pixel A17 release `system-a17-pixel.img.xz.part-*` + `vendor-a17.img.xz` + `boot-a17.img` + `vbmeta-disabled.img` with `SHA256SUMS`). Rollback = write system (+ vendor, boot if they changed) as in sections 3 and 4, then the selective wipe, then confirm it boots and tell the owner. Stock firmware restore (Odin/Heimdall tar of the exact CSC/binary) is the last resort; never flash a bootloader of a different binary version (anti-rollback).

Set a debug window with the owner before the first flash of an experimental system ("if not at the home screen in two hours, roll back") and keep to it: the owner has no usable phone meanwhile.

## 8. Samsung Download mode and Heimdall

Odin mode via Vol Down + Vol Up + USB cable (model dependent). `heimdall flash --BOOT boot.img --VBMETA vbmeta-disabled.img` works on macOS (build it from source; the Mac needs libusb). Heimdall needs the PIT for partition names. OEM unlocking must be switched on in Developer options first, then the bootloader unlock in Download mode wipes the phone. Knox warranty bit trips on custom binaries; the owner must accept that.

## 9. MTK tablet notes (TB-X606V)

`adb reboot bootloader` then `fastboot flash system system.img`, then `fastboot format:ext4 userdata`, `fastboot erase metadata`, `fastboot erase cache`. Never flash `recovery`. `fastboot boot` does not work (root fs panic): every kernel test writes the `boot` partition, so keep the stock one (`restore_stock_boot.md` in `scripts/tablet-mtk`). TWRP backups of boot and system are in the TWRP format (`system.ext4.win000..`); restore needs TWRP Restore, vendor via `zcat vendor.img.gz | dd`. `lenovo-tb-x606v-mtk.md` has the rest.
