# Lenovo TB-X606V (MediaTek MT8768): reference for newer-Android-on-old-vendor ports

Worked example of putting a Treble GSI (Android 14, 16, 17) on a tablet whose vendor image and kernel stay at Android 10 / 4.9.
Each item reads: symptom -> root cause -> fix -> where it lives. Paths are repo-relative; the repo names are
`android-aosp` (notes, early tweaks, `tweaks/`), `tb-x606v-android16-port` (A16 build, ROM Tuner origin), `tb-x606v-android17`
(A17 build, most tools), `tb-x606v-kernel` (kernel experiment, a dead end). Only the non-obvious is kept.

## Contents
1. Device facts and hard rules
2. Method: image editing, flashing, getting logs
3. Android 14 baseline and Android 16 GSI failures
4. Android 17 port
5. Root: Magisk and hide-debug-props
6. Performance: CPU/GPU overclock, ROM Tuner, jank method and results
7. Audio: Dolby and ViPER
8. Android Auto and Open Headunit
9. Sensor and HAL shims: compass, health, vibrator, lights
10. Bluetooth, telephony, location, hotspot
11. CI and release layout
12. Moving the patches to a newer GSI build
13. Traps that cost a recovery

## 1. Device facts and hard rules

| Fact | Value |
|---|---|
| Model | Lenovo Tab M10 FHD Plus (2nd gen), TB-X606V, 1200x1920 panel, 60 Hz |
| SoC | MediaTek MT8768 (Helio P35 class tables: 2.30 GHz fast cluster cpu0-3, 1.80 GHz slow cpu4-7), PowerVR GE8320 GPU (680 MHz top step), MT6357 PMIC |
| Memory | 3.8 GB RAM (zram lz4, about 2 GB), eMMC 5.1 |
| Kernel | stock 4.9.190 (the vendor's; the public Lenovo 4.9.117 source is for the sibling X606F, not exact) |
| Layout | A-only. One 3.8 GiB `system` partition (4085252096 bytes); `/vendor` is separate and survives system flashes. Vendor is Android 10 (HIDL HALs) |
| Boot chain | bootloader unlocked, `vbmeta` already has the verification-disabled flag (flags 2), TWRP lives in `recovery` |
| Sensors | accelerometer, light, proximity, Hall. No magnetometer, no gyroscope |
| Entry points | TWRP: hold Volume Up + Volume Down while starting. Bootloader: Power + Volume Down, or `adb reboot bootloader`. A hung Android 15/16 boot never enumerates on USB |
| Fastboot flow | `fastboot flash system img`, then `fastboot format:ext4 userdata; fastboot erase metadata; fastboot erase cache`. `fastboot boot` does not work (root fs panic): every boot or kernel test means writing the real partition |

Hard rules that were never broken:
- Never flash, erase or overwrite `recovery` (TWRP is the only way home). Flash only `system` (plus `boot` or `vendor` when the user approved it). Never touch `lk`, `nvram`, `nvdata`, `proinfo`, `persist`.
- Wiping userdata, flashing another system, rebooting or switching to fastboot needs the user's OK. Anything that restarts the Android framework (a sensor HAL swap, killing system_server or zygote) counts as a reboot: ask first.
- Keep a stock `boot` backup and a TWRP backup of the running system before experiments (`tb-x606v-android17/tools/scripts/backup_partitions.sh`).
- When the user shares the device, never tap through the live UI to test (it changes their preset); snapshot state files first.
- Recovery from a tablet that no longer reaches TWRP or fastboot: MediaTek BROM with mtkclient (`tb-x606v-android17/tools/restore_stock_boot.md`).

## 2. Method

Nothing is built from AOSP. Flash a prebuilt GSI into `system` only, patch binaries and dex offline, layer root-level tweaks on top.

- **Edit the ext4 image offline with debugfs (no mount, runs on macOS and Linux).** e2fsprogs is keg-only on macOS. Use `debugfs -w -f cmds.txt image` with `write`, `set_inode_field mode/uid/gid`, `ea_set -f label.bin <path> security.selinux` (label file NUL-terminated). Images from GSI releases are raw ext4: `xz -dc`, `truncate` to the partition size, `e2fsck -fy`, `resize2fs`. Some GSIs ship `shared_blocks` (read-only fs): remove the feature to make it writable. Copy multi-GB images with `dd bs=4m`; macOS `cp` crawled.
  Where: `tb-x606v-android17/build/build_image17.py`, `tb-x606v-android16-port/build/build_image.py` (idempotent builders), `build/verify_image.py` (file-by-file mode/owner/label/sha256 comparison against a tested image).
- **Live edits.** `/` and `/vendor` are read-only after every boot: `mount -o remount,rw /`. Replace a system library with a new file then `mv`; overwriting a mapped file in place restarted the framework or crashed its users. Never `mv` a file that is bind-mounted over (the mount point becomes a deleted dentry until reboot); test libc changes inside `unshare -m` first. From TWRP, mount the system partition rw and use `cat src > dest` to keep inode and SELinux label (`sed -i` and `adb push` drop the label). On a nearly full system fs, set `reserved_clusters` to 0 for the write and back to 4096 after, then `e2fsck -fy`.
- **Boot logs from a failed boot** (the central trick). `/data/local/tmp` is FBE-encrypted and unreadable in TWRP, so a boot diagnostics service writes logcat to `/cache/bootdiag/` (unencrypted). After a hang reboot to TWRP and read `/cache/bootdiag/*`, `/sys/fs/pstore/console-ramoops` (the failed boot's kernel console; an MTK RT-scheduler debug print floods it) and `/proc/last_kmsg`. Where: `tb-x606v-android16-port/debug/bootdiag.sh`, `tb-x606v-android17/tools/bootdiag.sh`, `tools/pulllog.sh`, `tools/readlog.sh`. Leave the service out of release images (`--with-bootdiag`); it ran `logcat -f` forever otherwise.
- **Tracing without strace or kprobes.** A tiny ptrace tool that follows vfork children and keeps the last syscalls found the netd and zygote failures (`tb-x606v-android17/tools/debug/trcx.c`, `initwrap.c`). Cross-compile helpers with `python -m ziglang cc -target aarch64-linux-musl -static`.
- **Long jobs** exceed tool timeouts: `nohup ... > log &` and poll. `fastboot flash` prints nothing if the device vanished; check `fastboot devices`.
- **Persistence model.** Runtime tweaks hang off init rc files in `/system/etc/init/` that start root services (`seclabel u:r:su:s0`) at `sys.boot_completed`. rc files run alphabetically, so a `zz_*.rc` overrides vendor and system ones (example: `zz_sf_latch.rc` re-forces `debug.sf.latch_unsignaled=0` after `vndk.rc` resets it). Where: `android-aosp/tweaks/device-final/`.

## 3. Android 14 baseline and Android 16 GSI failures

Android 14 (LineageOS 21 GSI) works with only boot-script tweaks. Android 15 never became usable. Android 16 (LineageOS 23.2 GSI) booted only after four fixes, then three more:

| Symptom | Root cause | Fix | Where |
|---|---|---|---|
| Boot animation forever; `system_server` aborts about 2 s after start, restart loop (21 times in 5 min) | Android 16 does not know media type `audio/mpeg-L2`, declared by the Android 10 vendor entry `OMX.MTK.AUDIO.DECODER.MP2` in `/vendor/etc/media_codecs_mediatek_audio.xml`; `AudioCapabilities::getDefaultFormat` hits a UBSan sub-overflow abort (via `StorageManagerService.isHevcDecoderSupported` -> `MediaCodecList`). `mediaserver32` died on the same entry | Remove the MP2 block from the vendor XML (the real fix; `/vendor` survives system reflashes; keep the original beside it) | `tb-x606v-android16-port/patches/fix_vendor_codecs.py`, `tb-x606v-android17/tools/vendor/fix_vendor_codecs_mp2.py` |
| SELinux denials, zygote `vendor_default_prop` denials, binder -22, unusable logs | Boot cmdline `androidboot.selinux=permissive` is ignored by this bootloader | Patch one instruction in `/system/bin/init` so it boots permissive; keep the original as `/system/bin/init.enforcing`. The user accepted permissive on this device | `tb-x606v-android16-port/patches/patch_init.py` |
| YouTube and other apps crash: "Could not copy bitmap to parcel blob" | `libhwui` seals bitmap memfds with `F_SEAL_FUTURE_WRITE` (needs Linux 5.1); on 4.9 the call fails so no bitmap over 16 KB can cross binder | Drop the seal in the 64-bit and 32-bit `libhwui.so`. A kernel backport also exists (`tb-x606v-kernel/patches/`) but is unused | `tb-x606v-android16-port/patches/patch_libhwui.py`, repro `tb-x606v-android16-port/docs/BitmapParcelTest.java` |
| Diagnostics lost on every failed boot | No persistent log on a hung boot | `bootdiag` service writing to `/cache` | see section 2 |
| App audio plays about 10 ms then stops | Treble Settings > Audio effects attaches five effects (including DAP and Dynamics Processing) to every session | Keep them off; the ROM Tuner daemon enforces it (switch to allow) | `tb-x606v-android17/rom-tuner/device/tablet_tunerd.sh` |
| Bluetooth dead on A14/A16 | Controller returns UNKNOWN_HCI_COMMAND for opcode 0xc5a; the stack treats it as fatal | A14: a `ret` at the start of `Controller::impl::read_default_erroneous_data_reporting_handler` in `libbluetooth_jni.so`, patched copy bind-mounted over the btservices apex lib in init and both zygote namespaces (`nsenter`); site is build-specific, re-found by masked instruction search. A16 GSI: `persist.sys.bt.unsupported.commands=182` in build.prop | `android-aosp/tweaks/bluetooth/`, `tb-x606v-android17/tools/bpf/patch_bluetooth.py` |
| YouTube 1080p stutters (23 fps, media.codec at 276% CPU) | `OMX.MTK.VIDEO.DECODER.VP9` is software; YouTube prefers VP9 | Remove its entry from `/vendor/etc/media_codecs_mediatek_video.xml`; YouTube then takes hardware H.264 (301 frames in 10 s, 0 dropped). `enabled="false"` is ignored by this build | `android-aosp/tweaks/codecs/`, `tb-x606v-android17/tools/twrp/vendor_edits.sh` |

Other findings: the A16 failures were found from `/cache/bootdiag` logcat, not from pstore (flooded). Load average sits near 25 permanently (about 24 MediaTek kernel threads in D state); read CPU idle instead.

## 4. Android 17 port

Google's A17 GSI on the stock 4.9.190 boot image and Android 10 vendor. A custom 4.9.117 kernel was tried first and dropped: its PowerVR driver rejected the vendor GPU firmware so the display never came up (`tb-x606v-kernel/README.md` records the patch list as a map of what A16/A17 want from a 4.9 kernel). Userspace was patched to fit the kernel instead. Order of failures:

| Symptom | Root cause | Fix | Where |
|---|---|---|---|
| libc and linkers abort at startup | Kernel lacks `MADV_WIPEONFORK` | Patch out the madvise failure branch | `tb-x606v-android17/tools/libc/patch_libc.py` |
| Same file: `libui`, `libmeminfo`, `libbinder` | HIDL mapper fallback gated on API level; gpuMem BPF map missing; frozen-state callback ioctl missing on 4.9 | One patcher per library | `tools/libc/patch_libui.py`, `patch_libmeminfo.py`, `patch_libbinder.py`, `patch_pgsetup.py` (cgroup2 mount options) |
| `bpfloader` reboots the device about 30 s into boot | `netbpfload`, `netd`, `libservice-connectivity` need 4.14+ map types; new `netd.o` counters use BPF atomic fetch-add, rejected by 4.9 ("BPF_STX uses reserved fields"); `cpustatsd` needs ambient caps 38/39 that init cannot raise | Patch the binaries, convert LRU maps and fetch-add to XADD, wrap the loader in a ptrace shim that sets `bpf.progs_loaded`, bind-mount everything over the APEX paths, strip the caps from the rc | `tools/bpf/` (`patch_binaries.py`, `patch_netd_o.py`, `netbpfload_tracer.c`, `00_bpf_bind.rc`) |
| `system_server` fails: connectivity | Local-net and loopback BPF maps cannot exist on 4.9 | Make the touching methods no-ops (`return-void` plus a `nop`; writing only the first code unit failed verification) | `tools/framework/patch_service_connectivity_jar.py` |
| `system_server` NPE and dialogs | `HintManagerService` with the old power HAL (A17 first calls `getInterfaceVersion()`); a camera event subscription; `Build.isBuildConsistent()` dialog | Patch `services.jar` by name-resolved dex edits | `tools/framework/patch_services_jar.py` |
| Watchdog timeouts | Slow CPU | `ro.hw_timeout_multiplier=5` | build.prop in the builder |
| HALs refuse to open or start | `/dev/ion` permissions, seccomp, ueventd; fstab legacy flags (`forcefdeorfbe=`, `resize`) A17 rejects; no `/metadata` | One-time vendor edit from TWRP, originals saved as `*.orig-a17` | `tools/scripts/apply_vendor_a17.sh`, `tools/vendor/`, `tools/fix_vendor_a17.py` |
| Edited APEXes rejected | Signature chain | Re-sign with a local AVB key plus APK sign | `tools/apex/` |
| No audio output | Vendor audio HAL is HIDL 5.0, gone in A17, and A16's 5.0 client does not fit A17 vtables | Run Android 16's `audioserver` and its roughly 164-library closure from `/system/lib64/a16audio` via `LD_LIBRARY_PATH`; rewrite differing AIDL transaction codes in two A17 libs | `tools/audio/` (`a16_closure.py`, `fix_aidl_codes.py`) |
| Audio works from a shell but apps are silent: "NPC::validatedUidPackagePair: controller never populated" | A17 Java proxy sends transaction 115 for `getPermissionController` (113 in A16); then A17's permission enum is rejected and the exception kills `system_server` (boot loop, no adb) | Point jump-table entry 115 at the 113 handler; make `populatePermissionState` return success. Install both or neither | `tools/audio/patch_server_codes.py`, `patch_audiopermission.py` |
| Lowmemorykiller: `system_server` restarts, activity manager stalls | A17 `lmkd` needs PSI/memcg; an idle stub that never listened on its socket made the activity manager sleep-retry on every process change | Replacement `lmkd` that speaks the protocol and drives the in-kernel killer (built with zig) | `tools/lmkd/` |
| Chrome blank, "Failed to start a Native Child Zygote process" | `zygote_next` forks with `clone3` (ENOSYS on 4.9) then panics on `prctl(PR_CAPBSET_READ)` for caps 38 to 40 (kernel knows 0 to 37) | Stubs in the unused tail of libc's last executable page: `clone3` -> `clone()`; `prctl` returns success for caps 38 to 40 only. A blanket "EINVAL is success" hung boot | `tools/libc/patch_libc.py` (bootstrap libc and the runtime APEX copy; a new `system_server` is needed to see it) |
| Video green screen, "dequeueBuffer failed: BAD_VALUE", `gralloc-mapper is missing` | MediaTek OMX asks for gralloc usage bit 13 (0x2000); A17 `libui` Gralloc2 rejects it. The swcodec APEX carries its own `libui.so` with the same problem | Drop bit 13 from the invalid-bits mask in both validate functions (arm64 and 32-bit); APEX copies bind-mounted from `/system/etc/bpf.a17/libui_swcodec{64,32}.so` | `tools/libc/patch_libui.py`, `00_bpf_bind.rc` |
| Google Maps crash "Failed to register package budget listener" | `libandroid_runtime` MemoryBudgetManager natives return 0 when the kernel cannot deliver events | Both natives return a dummy handle | `tools/libc/patch_libandroid_runtime.py` |
| Hotspot turns off one second after enabling | `netd` starts dnsmasq with `POSIX_SPAWN_USEVFORK | CLOEXEC_DEFAULT` (0x140); bionic's child calls `close_range`, ENOSYS on 4.9, exits 127; `tetherDnsSet` fails (error 121) | `mov w1,#0x140` -> `#0x40` before `posix_spawnattr_setflags` in `/system/bin/netd`. After `setprop ctl.restart netd` Wi-Fi has no route until `svc wifi disable; svc wifi enable`. Other binaries using that flag need the same | `tools/libc/patch_netd_spawn.py` |
| Settings and SystemUI interpreted, minutes slow; "No space left on device" compiling | GSI ships no odex; ART writes compiled code next to the APK and the 3.8 GiB image is full. Also a verify-only copy in `/data/dalvik-cache` shadowed the compiled `.odex` (seen in `/proc/<pid>/maps`) | Empty `oat/` in every app dir at build time; service in `post-fs-data` bind-mounts `/data/odex/<app>` over each; compile script deletes the stale dalvik-cache copy (never touch `/vendor` packages: their Android 10 odex is rejected by this ART) | `tools/firstboot/odex_bind.sh`, `firstboot_dexopt.sh`, `tools/scripts/dexopt_all.sh` |
| Setup wizard crashes on the Wi-Fi page | GSI ships AOSP `Provision` as a second SETUP_WIZARD activity, so PackageManager names none and `NETWORK_SETUP_WIZARD` is never granted | Delete `Provision.apk` (a `pm disable` is not enough) | builder, `docs/PIXEL.md` |
| Serial console warning every boot | Debuggable image starts the UART console | Start it only when `persist.sys.console=1` | builder `init.rc` edit |
| WebView Beta installs but cannot be selected | `config_webview_packages.xml` in `framework-res.apk` only allows `com.android.webview`; a runtime overlay froze system_server | Rebuild `framework-res.apk` with Beta added and only the first signing cert in `<signature>`, write it from TWRP. Using both certs of the Chrome lineage gave "bad base-64" and a boot into TWRP | `tools/framework/allow_webview_beta.py` |
| Missing `<priv-app>` permission aborts boot | `ro.control_privapp_permissions=enforce`: a privileged app asking for a permission no allowlist grants makes `system_server` abort | The builder checks every priv-app against the allowlists and refuses to build | `build/build_image17.py` |

Pixel layer (optional branch `exp/pixel-tablet`): Pixel Tablet system apps need the factory image of the same A17 build as the GSI (resource ids and hidden APIs only line up on the same build). Stage and re-sign with the AOSP platform test key, which is the GSI's platform cert (`tools/pixel/stage_pixel_tablet.py`, `docs/PIXEL.md`). Clear `/data/system/package_cache` when flashing over data. Pixel boot animation canvas must be fitted to the panel (`tools/pixel/fit_bootanimation.py`).

## 5. Root: Magisk and hide-debug-props

- Magisk 31.1 patched into the stock `boot` image (on-device `boot_patch.sh`, KEEPVERITY and KEEPFORCEENCRYPT true) and flashed from fastboot. The boot partition is read-only while Android runs (even for root; `blockdev --setrw` denied): flash from fastboot. `su` lives in `/debug_ramdisk` (`u:r:magisk:s0`). A new `system` image needs no re-patching because the installer never writes `boot`. Restore stock: `fastboot flash boot <stock>.img`; from a hung boot use TWRP and `dd` to `/dev/block/by-name/boot`.
- With the image debuggable, `adb root` works; once `hide-debug-props` is active `adb shell` is the plain shell user, use `su -c`.
- `hide-debug-props` (`tb-x606v-android17/tools/magisk/hide-debug-props`): sets `ro.debuggable=0` and `ro.secure=1` after boot, because apps that check build integrity (a smart-home vendor's security checker logged `DEBUG_CHECK_FAILED`) refuse to run on a debuggable build.
- Other modules kept: Universal GMS Doze, ViPER4Android, `bt-carside-profiles`, `telephony-features`, `cpu-oc-guard`, `wallpaper-nozoom` (all under `tb-x606v-android17/tools/magisk/`). Install with `su -c 'magisk --install-module <zip>'` and reboot.
- A bad module that breaks boot triggers Magisk safe mode, which disables every module (`disable` files in `/data/adb/modules/*`). adb works in TWRP: delete those files from there.
- Do not add a swap-file module (the ROM already has 2 GB zram). A DNS app (1.1.1.1) crashed on launch next to a ZTNA agent app; disabled the agent.

## 6. Performance

### CPU overclock (kernel patch, boot image only)
- Stock kernel stops the fast cluster at 2.30 GHz but carries OPP tables for faster chip bins with 2.50 GHz at the same top voltage. `patch_cpu_opp.py` copies one over the table this die uses (24 bytes in the kernel image); the DVFS firmware table is filled once at boot from it and the EEM voltage logic scales voltage itself (1.125 V at 2.50 GHz). Nothing at run time can exceed the table: `cpufreq_freq` only accepts table values, the hybrid-build set calls are `#if 0` stubs, and PPM clamps above-maximum to entry 0.
- Result: 3 minutes of full load on four cores at 2.50 GHz stable, 63 to 78 C; about 8 percent faster compute. Not tested: hours, summer heat, trim below -12 mV. The little cluster has its own table and cannot be raised the same way.
- Flow: unpack the Magisk-patched boot with `magiskboot`, patch the kernel, repack, `fastboot flash boot` (never recovery). `fastboot boot` does not work.
- Where: `tb-x606v-android17/tools/kernel/patch_cpu_opp.py`, `docs/CPU_OC.md`. Guard module `tools/magisk/cpu-oc-guard` caps the fast cluster at the stock step in `post-fs-data` so the OC kernel behaves stock until the user chooses a step.

### GPU overclock and voltage trim (run time)
- `/proc/gpufreq/gpufreq_fixed_freq_volt "<kHz> <10uV>"` does not compare against the OPP table and programs the MFGPLL (valid 93.75 to 950 MHz). Voltage above 0.80 V is not offered: it is a request for a shared Vcore step owned by DVFSRC. The tuner always sends 80000. Keep the OPP lock at 680000 first so Vcore stays at step 0, then read the PLL back (`real freq` in `gpufreq_var_dump`); more than 2 percent off means revert.
- Measured on this die: 730 MHz is the family's own rated bin point; 920 MHz held about 90 s, 960 MHz was a kernel panic, 940 untested. CPU voltage trim goes through `/proc/eem/EEM_DET_{L,L_HI,2L,2L_HI}/eem_offset` (signed 6.25 mV steps, clamped; `cpufreq_volt` does nothing in the hybrid build). An undervolt fails as a random reset under sudden load.
- Safety built into the daemon: nothing applied until 30 s after daemon start; crash guard (`/data/local/tmp/oc_pending` with boot id, removed after 3 stable minutes; a different boot id at start resets OC keys and reports `reverted_after_crash`); thermal guard (hottest thermal zone above 85 C reverts everything); values from fixed whitelists checked twice.
- Where: `tb-x606v-android17/rom-tuner/device/tablet_tunerd.sh` (block "overclock"), `rom-tuner/tests/test_oc.sh`, `tests/oc_stress.sh` (stability test, 10 minutes per step; a failed step means go back one step), `rom-tuner/README.md` "Overclock".

### ROM Tuner (daemon + app)
- App never writes to the system: it appends `key=value` lines to its own `files/request`. A root daemon (`tablet_tunerd.sh` + rc, `u:r:su:s0`) watches that directory with `inotifyd` (use mask `nw`: toybox mis-parses single-letter masks), validates every value against a strict character set and whitelist, applies it, keeps the master state in `/data/local/tmp/tuner.state`, publishes a copy for the app. Log `/data/local/tmp/tuner.log`.
- The MediaTek power HAL rewrites power mode, boosts and `userlimit_min_cpu_freq` on touch boosts and screen changes, so an enforcer compares every 5 s and re-applies. Set `cpufreq_power_mode` before the clock limits (sports mode resets them). `down_throttle_nsec`, `up_throttle_nsec` exist only while the governor is `schedplus` and are forgotten on every governor change: write them after it.
- Per-app profiles are not built; what exists is saved global profiles (`profile_active` is cleared by any edit, `profile_base` survives), a "Boost while CarPlay is open" watcher (top-app check every 3 s, snapshot and restore, never over custom settings) and per-app compile (`cmd package compile -m speed|speed-profile`, queue worker, progress parsed from the dexopt log).
- Settings entry: inject through the `com.android.settings.action.IA_SETTINGS` intent filter (not `EXTRA_SETTINGS`). Build without Gradle: `sh rom-tuner/build.sh` (aapt2, javac, d8, zipalign, apksigner; throwaway keystore made on first build). `adb install -r` of the tuner while it runs leaves a stuck "Updating" overlay: force-stop first. Install as a system app: push the APK to `/system/app/RomTuner/`, script to `/system/bin/`, rc to `/system/etc/init/`, `restorecon`, reboot.
- Theme controller traps: overlays enabled with `cmd overlay enable` are switched off at boot unless listed in `theme_customization_overlay_packages`; a pure-black overlay shares the `system_palette` category with the colour seed, so it must be re-enabled after any theme rewrite and given `set-priority highest`; `cmd overlay enable-exclusive --category` is a flag, not an option; this SystemUI never switches font overlays from the setting, the daemon must enable them. Overlays signed with the public AOSP platform test key install without reboot on the GSI.
- Device shell is mksh: a bare `|` inside `${x%%|*}` is alternation, escape it.
- Where: `tb-x606v-android17/rom-tuner/`, origin `tb-x606v-android16-port/rom-tuner/`, early version `android-aosp/tweaks/rom-tuner/`.

### Picture engine
MediaTek MiraVision sits behind the PQ HAL (`pq-2-2`), which reads `persist.vendor.sys.pq.*` once at service start, so the daemon restarts it. DRE, HDR and ultra-resolution props are copied into shared memory that nothing consumes (kernel has no DRE30/AAL; HAL logs "not support"). Only picture mode 2 ("user defined") honours `contrastidx`, `gsatidx`, `gamma.index`, `shp.idx`. Crash safety: if `init.svc.pq-2-2` is not running 3 s after the restart, set `picmode` back to 0.

### Jank method and results
- Method: scripted fling (Settings, or app drawer swipes) then `dumpsys gfxinfo <pkg>` (janky %, 50th/95th percentile); for system animations `dumpsys SurfaceFlinger --timestats` over an app open/close plus recents workload (`android-aosp/tweaks/customization/scripts/sfbench.sh`); `atrace` plus per-thread parsing for hotspots. Run-to-run noise is huge (16 to 62 percent janky for the same build): judge a change on at least 4 runs, and a reboot changes which tuner profile is active.
- SurfaceFlinger on A14: `latch_unsignaled=0`, 3 acquired buffers, frame-queue limiting on cut missed frames 55 to 15 percent and timeline jank 76 to 31 percent.
- ROM Tuner presets (Settings fling, gfxinfo): Battery 7.4 percent janky, Balanced 2.8, Performance profile alone 2.6, Smooth 1.7, Performance preset 1.1. Big-task rotation slows an 8-thread compute loop 20 to 30 percent; overclock and thermal off gave no UI gain.
- What helped on A17: compile every app in `speed` including Google apps (Play Store updates reset them to `verify`), window blur off (launcher drawer 72 to 6 percent janky), USAP pool on, Launcher3 as home (median frame 12 ms vs 19 ms), tracing off (`persist.traced.enable=0`: Perfetto's `traced` crash-loops on 4.9). Compiled launcher drawer: 22-30 percent janky interpreted vs 0-2 compiled.
- What did not: forcing DDR to its top step, a different kernel compiler, Skia Vulkan (worse), newer PowerVR driver (refuses the 1.11 kernel module), PerfMTK, phh GED/backpressure toggles (not in Google's SurfaceFlinger).
- Known slow spot: A17 notification shade, about 100 to 115 ms per frame, GPU-bound render thread; turning off shade blur and flags changed nothing.
- Not changeable without a kernel rebuild: governors (built in; a `.ko` needs exact 4.9.190 symbol versions and a bad module panics boot); PSI, uclamp, KSM are absent.
- Where: `tb-x606v-android17/docs/PERFORMANCE.md`.

## 7. Audio: Dolby and ViPER

- **Dolby Atmos** from the stock Lenovo A10 firmware (not redistributable; the builder takes your own copy via `--dolby DIR`): the apps run as `platform_app` so the vendor policy lets them talk to the Dolby HAL. `/vendor/etc/selinux/vendor_mac_permissions.xml` maps the Lenovo cert and the local re-sign cert to `seinfo=platform`. `daxService` needs smali patches: catch `Throwable` where a hidden `IPackageManager.setComponentEnabledSetting` lost an argument, and `UserHandle.ALL/CURRENT` -> `Process.myUserHandle()` (a re-signed app can never hold `INTERACT_ACROSS_USERS_FULL`). Audio HAL crash on opening the Dolby UI: `EndpointParamCache` destructor frees an invalid chunk and Scudo aborts; `libswdap.so` (`/vendor/lib/soundfx`, 32-bit because the audio HAL is 32-bit) gets that one `blx _ZdlPv@plt` replaced by `nop.w` (a leak instead of a crash). Vendor edits persist across ROM changes. Where: `android-aosp/tweaks/dolby/`, `tb-x606v-android17/tools/dolby/`. Audible quality never listen-tested.
- **ViPER4Android**: the app's own installer hangs and leaves an empty module. Build the Magisk module by hand: the 32-bit ARM `libv4a_fx.so` from the app APK into `system/vendor/lib/soundfx/`, a copy of `/system/lib/libstdc++.so` into `system/vendor/lib/` (the vendor linker namespace has none), and the vendor `audio_effects.xml` plus a `v4a_fx` library line and `v4a_standard_fx` effect with uuid `41d3c987-e6cf-11e3-a88a-11aba5d5c51b` (the Audio Modification Library does not add it). Check `logcat | grep EffectsFactory` and the audio HAL's `/proc/<pid>/maps`. App driver status and real sound not verified. Where: `android-aosp/tweaks/magisk-viper4android/`.
- Voice-recognition microphone source at 48 kHz returns clipped, half-length data (16 kHz is fine); ordinary mic, camcorder and voice-communication are good. Cause not found.

## 8. Android Auto and Open Headunit

- Self Mode (this tablet as the car side, Open Headunit as the head unit) needs Android Auto's car process to hold `android.app.role.SYSTEM_AUTOMOTIVE_PROJECTION`. As a user app: `Failed to register vehicle with CDM`; `cmd role add-role-holder` says "Package does not qualify" even with `set-bypassing-role-qualification true`. So it must be a system app.
- User-app Android Auto also kills its own process in `GhApplication.onCreate` ("Unsupported device") when SDK >= 30 and the app is not a system app, which took down every app bound to its `ProjectionStateProvider` (a game crashed). Patch: replace `and-int/lit16 ... 0x81` by `const/16 ..., 0x1` (same size), swap only the five `classes*.dex` into the original `base.apk` (an apktool rebuild dropped 104 obfuscated resources and crashed AA's settings), re-sign all splits with one throwaway key. Costs: Play updates replace it. Where: `android-aosp/tweaks/README.md` (the Android Auto sections), patched files under the (untracked) `work/backup-a17/gearhead/`.
- Better: a Magisk module overlays the original Google-signed APKs at `/product/priv-app/AndroidAuto/`; `service.sh` enables `FirstActivityImpl` and adds the role holder. First boot failed: `ro.control_privapp_permissions=enforce` aborted `system_server` because the ROM allowlist lacked `GET_ROLE_HOLDERS` for that AA version; ship a `privapp-permissions-*-extra.xml` listing every privileged permission the app requests. Recovery was deleting the `disable` files from TWRP. Where: `android-aosp/tweaks/magisk-gearhead-system/`.
- Encoder limit: the session then reaches `projecting` (handshake, service discovery pass) but `OMX.MTK.VIDEO.ENCODER.AVC` (1280x720, surface input) never outputs a frame: `CAR.WM: Frame stuck or lost in encoder!`, Open Headunit "No video received yet", and AA shows its generic "reconnect USB cable" screen after about 15 s. The `CAR.AUTH ... isPackageAllowed=false` line is a harmless guard. Planned, not done (needs user approval, affects camera video, restarts mediacodec): hide the MTK AVC encoder from `media_codecs` so AA falls back to the software encoder. Treat the Self Mode result as unresolved.
- Enable AA developer mode: tap Version 10 times, menu > Start head unit server (port 5277 listens).

## 9. Sensor and HAL shims

Pattern: A17 only looks for AIDL HALs; the Android 10 vendor only has HIDL. Register an AIDL instance with a Java or native shim, declare it in a vendor VINTF fragment, and drive the sysfs node directly.

| Shim | Problem | What it does | Where |
|---|---|---|---|
| lights | No brightness control | `android.hardware.light.ILights/default`, writes `/sys/class/leds/lcd-backlight/brightness` | `tb-x606v-android17/tools/lights` |
| vibrator | Every haptic was `ignored_unsupported` | `android.hardware.vibrator.IVibrator/default` (v1) driving `/sys/class/leds/vibrator/{duration,activate}`; motor accepts 25 ms or longer pulses, no amplitude | `tools/vibrator` |
| health | Android showed 100 percent, 0 V, -99 C: vendor health HAL reads an unfitted gauge chip (`mm8013`) and kernel `capacity` and `status` are stale | `android.hardware.health.IHealth/default` (v3) reading the real `battery` supply; if `charge_counter / charge_full` disagrees with `capacity` by more than 10 points it uses the ratio. Behaviour after unplugging not checked | `tools/health` |
| compass | No magnetometer or gyro | Wrap the vendor sensors HAL: `/vendor/lib64/hw/sensors.mt6765.so` moved to `.orig.so`, the shim loads it, forwards everything and adds a MAGNETIC_FIELD sensor built from GPS course (above 2 m/s) plus accelerometer tilt. A system service `compassd` (system uid, no root) turns GPS on only while the shim's flag file exists and writes the heading file. Heading is travel direction, so the tablet must face along the car; below about 7 km/h it holds the last heading. No ROTATION_VECTOR (no gyro). Swapping the HAL restarts the framework: ask first | `tb-x606v-android17/tools/compass/`, `android-aosp/tweaks/compass-shim/` (experimental, `--experimental` in the builder; vendor half never in images) |

Apps that read the rotation vector instead of accelerometer plus magnetometer see no compass on this device.

## 10. Bluetooth, telephony, location, hotspot

- **A17 Bluetooth**: (1) the controller's unknown-command status for an optional command is fatal, and an SSP check then aborts: both branches patched in `tools/bpf/patch_bluetooth.py` (per-build table keyed by input SHA-256). (2) The GSI sets none of AOSP's `bluetooth.profile.*` properties, so pairing worked but nothing connected after SDP: the builder appends them to build.prop (a2dp source, avrcp target, hfp ag, hid, gatt, bas, opp, pan, asha and a class of device). Evidence: HFP and A2DP with a Bose headset.
- **Car-side profiles** (tablet as the car): A17's Bluetooth app re-reads `bluetooth.profile.*.enabled` at every BT restart, so `setprop` plus `svc bluetooth disable; svc bluetooth enable` turns on `a2dp.sink`, `avrcp.controller`, `hfp.hf`, `pbap.client`, `map.client` without reboot. Persist via Magisk `bt-carside-profiles` (`system.prop`, takes effect at next boot; reboot persistence not tested). An iPhone music session is untested. Never run `dumpsys bluetooth_manager` (crashes in `ControllerImpl::Dump`). A2DP input via the legacy `a2dp` module does not exist in the 5.0 HAL; A2DP output works.
- **Cellular**: A17 RIL only trusts a radio if `android.hardware.telephony.radio.access` is declared; the A10 vendor declares only `.telephony` and `.gsm`, so every radio service showed unavailable. Declare `radio.access`, `calling`, `data`, `messaging`; RILJ then binds vendor HIDL radio 1.4, the modem powers on and the IMEI reads. Tested without a SIM; calls, SMS, data and IMS (VoLTE) untested. Where: `tools/telephony/`, Magisk `tools/magisk/telephony-features`.
- **Network location**: `dumpsys location` showed the network provider disabled: MindTheGapps' Play services does not request `INSTALL_LOCATION_PROVIDER`, so the system disqualified it. Patch the two `ProxyLocationProvider` constructors in `services.jar` to pass no service permission (any app declaring a provider can then qualify; fine for a personal device). Then Play services refused its own requests: with no setup wizard its location app ops were `ignore` and the opt-in unset. Fix once: grant the location and nearby-Wi-Fi permissions, `appops reset`, `appops set --uid com.google.android.gms COARSE_LOCATION|FINE_LOCATION|NEARBY_WIFI_DEVICES allow`, `settings put secure google_location_accuracy_enabled 1`, `settings put secure network_location_opt_in 1`, same under `global`. A first fix then came in 20 s indoors. GNSS works end to end outdoors; indoors there are no satellites. Where: `tools/framework/patch_location_provider.py`, `tools/firstboot/firstboot_dexopt.sh`.
- **Hotspot**: see the netd item in section 4.
- **Other known gaps**: USB tethering and Widevine level untested (Netflix plays; `RkpdWidevine` provisioning logs `ERROR_DRM_CANNOT_HANDLE`); Cast discovery finds nothing and is untested against a real device; `UsbDeviceManager` falls back to the legacy handler (file transfer works); fs-verity and GPU memory BPF errors are noise.

## 11. CI and release layout

- GitHub Actions builds from public inputs only: `.github/workflows/build-image.yml` (inputs: edition plain or pixel, `mode: check` to dry-run every patcher against a GSI in about two minutes, `publish` to attach to a release, GSI URL plus SHA-256, release tag) and `build-tools.yml`. It downloads Google's GSI, verifies the checksum, builds with the donor GSI for the A16 audio stack and VNDK 29, optionally MindTheGapps, compresses with xz, uploads `SHA256SUMS.txt`. A16: `tb-x606v-android16-port/.github/workflows/build-rom.yml`. Kernel: `tb-x606v-kernel/.github/workflows/build-kernel.yml` (AOSP clang r353983c and gcc 4.9).
- CI images carry no compiled app code (dex2oat needs a booted device): a one-time job one minute after first boot compiles shade, launcher and Settings first, then the rest (10 to 15 minutes, into `/data/odex`). Releases that are dumps of a tested tablet are already compiled.
- Not in CI or releases: Dolby, Pixel apps (built locally from your own factory image), vendor images. Google apps appear only in the gapps variants.
- Installer: `tools/scripts/install_a17.sh <image.xz>` (flash, vendor edits through TWRP, reboot) and a single-zip TWRP route (`docs/TWRP_INSTALL.md`, `tools/twrp/make_twrp_zip.sh`). Never written by any script: `recovery`, `boot`, `lk`, `nvram`, `nvdata`, `proinfo`, `persist`.
- A GSI newer than the one the patches were developed on is untested until its README says so. Keep the previous release and a TWRP route.

## 12. Moving the patches to a newer GSI build

1. `python build/check_patches.py system.img` (or workflow `mode: check`) lists every patch that no longer applies, all at once.
2. Pattern- or symbol-searching tools normally survive (libc, libui, pgsetup, meminfo, binder, android_runtime, services.jar, service-connectivity jar); dex tools resolve methods, fields and strings by name because indices change every build.
3. Plain-address tools (`tools/bpf/patch_binaries.py`, `patch_bluetooth.py`) keep one table per build keyed by input SHA-256. Find sites in the new binary with masked-immediate instruction windows (`tools/porting/find_site.py OLD NEW 0xADDR ...`; newer builds add `bti c`/`paciasp`, and `cmp w,#1; b.eq` may become `cbz`), then confirm against both disassemblies.
4. A tool that passes on the new build must give byte-identical output on the old one.
5. Build, `e2fsck -fn`, and expect boot surprises: checks only prove the sites were found.
6. For a boot that restarts: wrap `init` under ptrace to replay its rate-limited log (`tools/debug/initwrap.c`); a panic "Attempted to kill init" after about 30 s was init rebooting on purpose (`bpfloader` has `reboot_on_failure`); the tracer log goes to `/dev/bpftrace.log`, copied to `/cache/bootdiag`.

## 13. Traps that cost a recovery

- Both signing certs of a lineage in a `<signature>` element: `bad base-64`, `system_server` dies at boot, device lands in TWRP.
- A blanket "EINVAL means success" `prctl` stub: zygote's own capability loop never ended, boot hung. Stub only the exact caps.
- A privileged app missing from the privapp allowlist: `system_server` aborts, Magisk then disables all modules.
- Writing the audio patches alone (one of the two): exception on `audioserver_lifecycle` kills `system_server`, boot loop with no adb.
- Overwriting a mapped library in place, or `mv` over a bind-mounted file.
- Leaving a stale state file across ROMs: a ROM Tuner state from A16 said `bootanim=arrow` and silently replaced the new boot animation.
- Removing a Google app from `/system` that another system app binds (removing the search app broke the hub screensaver); reinstall it as a normal `/data` app instead.
- Wi-Fi adb drops after a framework restart; keep a USB adb path. If `adb connect` says "No route to host" while the port answers, kill and restart the adb server from the current shell (a server started by another app lacked local-network access).
- SELinux permissive and `ro.debuggable=1` are conveniences of this personal build; `hide-debug-props` and a normal user-build identity matter for apps that check them.
