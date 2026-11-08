# TB-X606V kernel patches (4.9) for Android 16/17

Patches, configs and a CI workflow for building a 4.9 kernel for the Lenovo Tab M10 FHD Plus (TB-X606V, MT8768). They were written while
trying to run Android 17 on the tablet; see [`tb-x606v-android17`](https://github.com/manvindar/tb-x606v-android17) for how that went.

**Outcome.** The kernel built from the Lenovo open-source drop (4.9.117, `UsrBinLuna/kernel_lenovo_achilles6`) boots Android 17 userspace far enough
for the framework to start, but its PowerVR driver rejects the vendor GPU firmware, so the display never comes up. The final setup uses the **stock
4.9.190 boot image** and patches Android userspace instead. Treat this repository as a record of what Android 16 and 17 need from a 4.9 kernel,
not as a kernel you should flash.

## Contents

- `patches/`
  1. `F_SEAL_FUTURE_WRITE` backport (Android 16's libhwui seals bitmap memfds with it).
  2. `thread_info`: include `restart_block` (needed by the MADV_WIPEONFORK backport).
  3. `MADV_WIPEONFORK` backport: Android 17's libc aborts at startup without it.
  4. MediaTek `fiq_cache_init` skipped.
  5. `ram_console`: clear the bad `_pa` pointer when the SRAM mapping fails (otherwise an oops at 0.6 s).
  6. cgroup2: ignore unknown mount options (`memory_recursiveprot`).
  7. cgroup v1 cpuset: accept `cpuset_v2_mode`.
  8. `disp_caps_info`: append the four fields the stock userland passes to the display driver.
- `config/`: the stock 4.9.190 config and the fragment for Android 16/17 features.
- `scripts/repack_boot.py`: repacks a kernel into the stock boot image header. `scripts/build-local.sh` builds locally.
- `.github/workflows/build-kernel.yml`: builds with the AOSP clang r353983c and gcc 4.9 toolchains and can publish the boot image as a release.
- `mainline/`: an early, unfinished attempt at a mainline device tree.

## Notes

The bootloader ignores `fastboot boot`, so every kernel test means writing the `boot` partition. Keep a backup of the stock one, and never touch `recovery`.
Device-tree bootargs also needed `cpuidle.off=1` (a NULL dereference in MediaTek MCDI idle after about 10 s) and `printk.devkmsg=on`.
No warranty: a bad kernel can leave the tablet unbootable.
