# Device recon: the first hour

Goal: decide track, size budget, flash path and kernel work before any write. Everything here is read-only. Use `adb shell` as the shell user; some files need root (`/proc/cmdline`, `/apex`, sysfs nodes) and are marked.

Contents: 1 identity, 2 boot and partitions, 3 vendor interface, 4 kernel capabilities, 5 risk state, 6 what to record.

## 1. Identity (all `getprop`)

`ro.product.model`, `ro.product.device`, `ro.hardware`, `ro.board.platform`, `ro.build.fingerprint`, `ro.build.version.sdk`, `ro.build.version.security_patch`, `ro.product.cpu.abilist`, `ro.opengles.version`, `ro.boot.hardware`. SoC and GPU from `/proc/cpuinfo` and `dumpsys SurfaceFlinger` (GLES line). RAM from `/proc/meminfo`, swap from `/proc/swaps`.

Scrub before writing anything to a file: serial (`ro.serialno`, `androidboot.serialno`), IMEI, MAC, SIM and sales props. Keep raw dumps local and gitignored.

## 2. Boot and partitions

| Question | How | Why it matters |
|---|---|---|
| A-only or A/B | `ro.boot.slot_suffix`, `ls /dev/block/by-name` for `_a/_b` pairs | A-only: one system image, rollback is a reflash |
| Dynamic partitions | `ro.boot.dynamic_partitions`, a `super` partition | none on both reference devices; a GSI flashes straight to `system` |
| System-as-root | `ro.build.system_root_image`, `mount | grep ' / '` | `/dev/root` is `/system`; the image root is `/` |
| Treble | `ro.treble.enabled` | needed for GSI |
| Vendor level | `ro.vndk.version`, `ro.vendor.build.version.sdk` | decides VNDK APEX and SELinux mapping (29.0 / 30.0) you must supply |
| Sizes | `/proc/partitions`, `by-name` | M30s system 4800 MiB, TB-X606V 3.8 GiB: fixes the budget |
| Ramdisk | unpack boot.img: M30s boot has none (kernel gets `root=/dev/sdaN` from the bootloader); MTK has one | decides whether you need a first-stage launcher |
| Verified boot | `ro.boot.verifiedbootstate`, `vbmeta.device_state`, a `vbmeta` partition | flash a vbmeta with verification disabled, or `--disable-verity` |
| Encryption | `ro.crypto.type`, userdata fstab flags (`fileencryption=ice`) | the vendor fstab line may need the flag removed and userdata formatted once |
| Bootloader | `ro.boot.flash.locked`, `sys.oem_unlock_allowed`, `ro.oem_unlock_supported`, warranty bit | Samsung: OEM unlock toggle must be on in Developer options; knox bit trips |
| Flash path | Samsung: Download mode + Heimdall, TWRP for system/data; MTK: fastboot + TWRP | `fastboot boot` may not work (MTK tablet: root fs panic) |
| Recovery | TWRP image for the exact model | enter with Vol Up + Vol Down held; `adb reboot recovery` works from Android |
| Radio and identity partitions | `efs`, `sec_efs`, `cpefs`, `persist`, `nvram` | back up first; never write; they hold IMEI and calibration |

M30s facts: UFS `sda`, `system` sda25, `vendor` 600 MiB sda26, `product` 296 MiB sda27 (mounted at `/product` by the vendor fstab on One UI too), `userdata` f2fs sda32, internal `/sdcard` is `/data/media` on sda32.

Disk before downloading: a donor AP zip is 8 GB and unpacks to 7+ GB EROFS plus 5 GB ext4 copies. Keep more than 10 GB free on the host at all times.

## 3. Vendor interface

Pull `/vendor/etc/vintf/manifest.xml` and `manifest/*.xml` (rdump the vendor image or `adb pull`). Record: `target-level`, which HALs are HIDL (audio 5.0, fingerprint 2.1, graphics composer 2.1, mapper 2.1, allocator 2.0, camera provider 2.6, radio 1.4, health 2.x, power, thermal) and which are AIDL (the M30s vendor has AIDL lights only). The newer framework wants AIDL for fingerprint, health, vibrator, power, lights: each missing one is a shim or a framework patch (`hal-shims.md`).

Run `scripts/m30s/oneui/vintf_gap.py DONOR_SYSTEM.erofs VENDOR_DIR` to diff a donor against the vendor: it lists HIDL/AIDL client libraries the donor ships and which the vendor serves.

Codec trap: check `/vendor/etc/media_codecs*.xml` for `audio/mpeg-L2` declared by a decoder; on the tablet it aborted system_server. `tablet-mtk/vendor/fix_vendor_codecs_mp2.py` removes the type.

## 4. Kernel capabilities

Config: `adb shell zcat /proc/config.gz` (readable as shell on both devices). Check: `PSI`, `BPF_SYSCALL`, `BPF_JIT`, `CGROUP_BPF`, `USERFAULTFD`, `MEMCG`, `ZRAM`, `F2FS`, `EROFS`, `OVERLAY_FS`, `SECURITY_SELINUX` and `ALWAYS_ENFORCE` (Makefile of security/selinux in the source drop), `UID_SYS_STATS`.

Syscalls and features you cannot read from config: use `scripts/m30s/probe/kprobe.c` (static arm64, `build.sh`, push to `/data/local/tmp`, run once; it writes nothing). It reports `F_SEAL_FUTURE_WRITE`, `clone3`, `close_range`, `openat2`, `faccessat2`, `pidfd_*`, `userfaultfd`, `io_uring`, `rseq`, `MADV_WIPEONFORK`, binder protocol version, `/proc/pressure`. BPF needs root to test; as shell even a trivial program gets EACCES.

Typical results on the two devices: 4.9 and 4.14 both lack `close_range`, `clone3`, `F_SEAL_FUTURE_WRITE`, `openat2`, pidfd, io_uring, rseq; 4.14 stock lacks PSI, JIT, userfaultfd; 4.9 also lacks `MADV_WIPEONFORK` and cgroup2 mount options. Cgroup v1 memcg pressure and an in-kernel LMK may exist (Samsung: `/sys/module/lowmemorykiller`).

Read the kernel source drop licence: Samsung's open source zip (e.g. `SM-M307F_SWA_RR_Opensource.zip`) builds the exact kernel; keep the repo private.

## 5. Risk state

Daily-driver data: count packages, storage used, users (Samsung dual messenger user 95), SD card, SIM slots, battery. A flash that wipes `userdata` destroys all of it: take a read-only backup first (`scripts/m30s/backup/dump_partitions.sh`: every partition read twice, both SHA-256 must match; user files pulled with `adb pull` of `/sdcard`) and get an explicit OK.

Bootloader command line: from a bootloader disassembly the M30s adds `root=/dev/sdaN` itself even with a disabled vbmeta (`m30s-quirks.md`). Do not assume; verify on a spare boot image before relying on it.

## 6. What to write down

A single table in the project docs: identity, partitions, vendor level, HAL list, kernel gaps, flash path, unlock state, backup status, rollback image, and which of these were verified on the device versus inferred. Label every claim VERIFIED, RELAYED or UNVERIFIED; it avoids acting on guesses later.
