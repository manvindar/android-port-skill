# Patch index: symptom -> cause -> fix -> file

Paths are relative to `scripts/` (or `patches/`). "M30s" = Samsung SM-M307F (kernel 4.14.113, vendor Android 11), "MTK" = Lenovo TB-X606V (kernel 4.9.190, vendor Android 10). Offsets in the scripts are located by pattern or symbol, not hard-coded, unless the row says "per build". Re-run a patcher against every new GSI or donor build and expect an assertion failure when the build changed: that is by design.

Contents: 1 kernel, 2 init and SELinux, 3 native libraries, 4 tethering apex and BPF, 5 framework jars and resources, 6 audio, 7 HAL shims, 8 One UI donor track, 9 Pixel track, 10 Samsung hardware quirks, 11 MTK-only.

## 1. Kernel (see kernel.md)

| Symptom | Cause | Fix | File |
|---|---|---|---|
| lmkd of Android 12+ refuses to start, no `/proc/pressure` | no PSI in 4.14 | 28 android-common patches (PSI, psi monitor, cgroup poll) plus `CONFIG_PSI=y` | `patches/kernel-4.14/psi/*.patch`, `patches/kernel-config/a17.fragment` |
| netbpfload: "Kernel eBPF JIT failure" on every program | `CONFIG_BPF_JIT` unset | enable JIT (+ `JIT_ALWAYS_ON`); fallback userspace patch NOPs the check | `a17.fragment`, `m30s/img/patch_netbpfload_jit.py` |
| ART userfaultfd GC aborts | no userfaultfd | `CONFIG_USERFAULTFD=y` | `a17.fragment` |
| Android 17 libc aborts at startup (arc4random) | no `MADV_WIPEONFORK` (4.9) | backport (needs `restart_block` in thread_info) | `patches/kernel-4.9-mtk/0002*`, `0003*`; userspace alternative `scripts/tablet-mtk/libc/patch_libc.py` |
| Android 16 libhwui: bitmaps over 16 KB cannot cross binder | no `F_SEAL_FUTURE_WRITE` (5.1) | backport, or patch libhwui | `patches/kernel-4.9-mtk/0001*`; `scripts/tablet-mtk/android16/patch_libhwui.py` |
| cgroup mount errors at boot | 4.9 rejects cgroup2 data `memory_recursiveprot` and cpuset option `cpuset_v2_mode` | kernel patches, or patch libprocessgroup_setup | `patches/kernel-4.9-mtk/0006*`, `0007*`; `scripts/tablet-mtk/libc/patch_pgsetup.py` |
| Black video when panel advertises HDR10 | the M30s DT has no HDR node, driver synthesised one, HWC then tone-maps wrongly | do not ship; experiment kept for reference | `patches/kernel-4.14/hdr/0001*` |
| Stock kernel forces SELinux enforcing (`CONFIG_ALWAYS_ENFORCE`) | `setenforce 0` and `typepermissive` do nothing | build a kernel with permissive support, or append an allow-all block to `plat_sepolicy.cil` | `patches/kernel-config`, `m30s/img/make_allowall_cil.py` |
| Touch lag at first touch | CPU idles at min frequency | input boost driver (150 ms min freq) | `patches/kernel-4.14/boost-input/` |
| Display never comes up on a self-built 4.9 | PowerVR driver rejects vendor GPU firmware | keep stock boot image, patch userspace instead | `patches/kernel-4.9-mtk/README.md` |

## 2. Init, SELinux, first stage (see system-patches.md)

| Symptom | Cause | Fix | File |
|---|---|---|---|
| A17 `/system/bin/init` aborts, boot image has no ramdisk | A17 init is second-stage only | `/init` = static launcher that runs Android 14's init with its own linker and 35-lib closure, which ends in `exec /system/bin/init selinux_setup` | `m30s/debug/fslaunch.c`, `m30s/img/make_a14fs.py` |
| Everything denied or init cannot compile policy | vendor sepolicy is v29/30 | SELinux mapping `29.0`/`30.0.cil` + `compat.cil` and the matching VNDK APEX from an Android 14 GSI | `build_a17.py` step 4 (`m30s/img`) |
| init policy compile fails after merging donor + vendor | donor and vendor both declare the same typealiases | drop system-side duplicates until a host `secilc` compiles | `m30s/oneui/sepol_check.py`, `m30s/policy/build_secilc.sh` |
| `vendor_mac_permissions.xml` rejected: "Unable to load SELinux MMAC policy" | A17 parser rejects package-only signers of the Android 11 file | drop those signers | `m30s/img/build_vendor_a17.py` |
| Boot on a user-build init needs permissive | GSI is a user build | pattern patch of init (find the `selinux_setup` enforcing branch) | `build_a17.py` step 2, `m30s/oneui/build_oneui_port.py` step 1 |
| Vendor fstab: system_server/zygote need `/metadata` but device has none | A17 init mounts `/metadata` | tmpfs line in vendor fstab | `m30s/img/build_vendor_a17.py` |
| surfaceflinger aborts "couldn't find an OpenGL ES implementation" | `ro.hardware.egl` unset | `ro.hardware.egl=mali` in build.prop | `build_a17.py` |
| zig/musl static helper dies "TLS segment is underaligned" | musl binaries under bionic linker | build static helpers with the NDK | `m30s/img/make_a14fs.py` |

## 3. Native libraries (bionic and friends)

| Symptom | Cause | Fix | File |
|---|---|---|---|
| Chrome renderer cannot start, zygote fork fails ENOSYS | no `clone3` | stub the fork-style case with `clone()` | `tablet-mtk/libc/patch_libc.py` |
| SurfaceFlinger aborts "gralloc-mapper is missing" | libui falls back to HIDL mappers only when device API <= 35 | NOP `cmp w0,#0x23 ; b.gt` (all sites) | `tablet-mtk/libc/patch_libui.py`, `m30s/oneui/patch_libui_gate.py` |
| system_server dies `linkToDeath returned -38` / camera listener fails | libbinder frozen-state ioctl needs 6.x kernel | make `addFrozenStateChangeCallback` return 0 | `tablet-mtk/libc/patch_libbinder.py` |
| system_server killed every ~75 s | libmeminfo `abortOnMismatch` aborts for the missing gpuMem bpf map | return at function entry | `tablet-mtk/libc/patch_libmeminfo.py` |
| Maps and other apps crash "Failed to register package budget listener" | memory-budget watchers return 0 without memcg events | return dummy handle | `tablet-mtk/libc/patch_libandroid_runtime.py` |
| Hotspot turns off after a second | netd spawns dnsmasq with `CLOEXEC_DEFAULT`; bionic calls `close_range` (ENOSYS) | flags 0x140 -> 0x40 | `tablet-mtk/libc/patch_netd_spawn.py` |
| These libs live inside the runtime APEX too | apex is signed | `repack_apex.py` (own AVB key), or bind mount | `tablet-mtk/apex/repack_apex.py` |
| `com.android.virt` apex EROFS, kernel has no EROFS | apexd-bootstrap fails, framework still needs the jar | convert payload to ext4 and re-sign | `tablet-mtk/apex/virt_to_ext4.py` |

## 4. Tethering apex and BPF (netbpfload, netd, service-connectivity)

The apex is signed, so patched copies sit in `/system` and are bind-mounted over the apex files in `on load-bpf-programs` (rc `00_bpf_bind.rc`). The mount is per file; a missing bind shows as the unpatched error again.

| Symptom (first log line) | Cause | Fix | File |
|---|---|---|---|
| `NetBpfLoad: Android V requires kernel 4.19` and variants (25Q2 5.4, 26Q3 5.15, `V+ only supports LTS`, 25Q4 5.10); `reboot_on_failure` -> reboot loop, no adb | hard kernel gates | find each message by string, turn the guard branch into `b` | `m30s/oneui/patch_netbpfload.py` |
| SIGABRT in `ElfObject::ElfObject`: "file %s is on device X while we are on device Y" | patched copy is on /system, .o files on the apex loop device | NOP the device compare | same file |
| netd aborts "Failed to get program from .../prog_netd_egress_stats" | only 4.14 variant has api window [3300,3500) | api constant 3499 at the *program* skip site only (maps keep real api: 25Q2+ maps must exist) | same file |
| `nativeGetNextMapKey failed: errno 524` on `local_net_access_map` | LPM tries cannot be iterated before 4.20 | create LPM_TRIE maps as HASH (loader type rewrite) | same file |
| `BpfRingbuf init failed ... local_net_note_op_ringbuf` / `loopback_access_ringbuf` -> system_server SIGABRT | no BPF ringbuf (< 5.8) | `nativeGetLocalNetAccessRingbufFd` returns an eventfd, `nativeInitLoopbackEventConsumer` returns | `m30s/oneui/patch_lsc_ringbuf.py` |
| `libnetd_updatable` aborts on `V+ platform with kernel version <` | same gates in netd | same patcher with `WINDOW=96 MIN=2` and the two message prefixes | `patch_netbpfload.py` (see `build_oneui_port.py` step 6) |
| netd.o rejected on 4.9: LRU maps, atomic fetch-add `BPF_STX reserved fields` | 4.9 verifier | LRU_HASH -> HASH, atomic imm 1 -> 0 where the result is dead | `tablet-mtk/bpf/patch_netd_o.py`, `btfmaps.py` |
| `Cannot open local_net_access map` (4.9) | `BpfNetMaps.initBpfMaps` | skip branch in service-connectivity.jar | `tablet-mtk/framework/patch_service_connectivity_jar.py` |
| Bluetooth `log::fatal "was not expecting status event"` | vendor controller answers HCI 0x0c5a with UNKNOWN_HCI_COMMAND | retarget two `tbz` in libbluetooth_jni | `tablet-mtk/bpf/patch_bluetooth.py` |
| Which BPF helpers/map types does an apex object need that my kernel lacks? | desk question | `bpf_needs.py KERNEL_TREE OBJ.o` | `m30s/oneui/bpf_needs.py`, `m30s/debug/netbpfload_tracer.c` |

## 5. Framework jars and resources

| Symptom | Cause | Fix | File |
|---|---|---|---|
| system_server NPE in HintManagerService ctor | no AIDL power HAL (HIDL only) | NOP null check; catch NPE and return default SupportInfo | `tablet-mtk/framework/patch_services_jar.py`, `m30s/oneui/patch_services_oneui.py` |
| "There's an internal problem with your device" dialog | `Build.isBuildConsistent()` false (VINTF mismatch) | `const/4 v2,1` at the call | `patch_services_oneui.py` |
| BiometricService handler kills system_server (`registerAvailabilityCallback`) | camera service cannot init listener | no-op `subscribeToCameraEvents` | `patch_services_oneui.py` |
| One UI: `ISehHealth$Stub$Proxy.registerCallback` NPE in BatteryService.onStart | Samsung wants its AIDL health service; vendor has HIDL only | NOP both calls; see health in `hal-shims.md` | `patch_services_oneui.py` |
| `config_servicesExtensionPackage ... android.ext.services` missing | extservices apex ships `com.google.android.ext.services` | static overlay on `android` | `m30s/oneui/overlay-extservices/` |
| `Call to getInstalledModules before metadata loaded` | no `com.android.modulemetadata` package | minimal package with `android.content.pm.MODULE_METADATA` meta-data pointing at an empty `<module-metadata/>` | `m30s/oneui/modulemetadata/` |
| WebView Beta rejected or system_server dies "bad base-64" | provider signature list | use only the first certificate | `tablet-mtk/framework/allow_webview_beta.py` |
| Play network location provider disqualified | `INSTALL_LOCATION_PROVIDER` passed as service permission | pass null at the two call sites | `tablet-mtk/framework/patch_location_provider.py` |
| `PackageManager` refuses WebViewGoogle (arm64-only, declares multiArch) | phone also supports armeabi-v7a | clear `multiArch` and re-sign | `m30s/pixel/unset_multiarch.py` |
| Pixel overlay `config_servicesExtensionPackage` aborts system_server | Pixel config overlay names a package absent here | patch the overlay to `android.ext.services` | `m30s/pixel/stage_pixel_phone.py` |

## 6. Audio (vendor HIDL audio 5.0 under an A16/A17 framework)

Method: run Android 16's audioserver and its library closure privately from `/system/lib64/a16audio` (rc sets `LD_LIBRARY_PATH`), take it from a public LineageOS 23.2 GSI.

| Symptom | Cause | Fix | File |
|---|---|---|---|
| no libaudiohal 5.0 in the framework | framework dropped it | closure collector | `tablet-mtk/audio/a16_closure.py`, `install_a16_audio.sh` |
| A17 clients send wrong AIDL codes to the A16 server | transaction numbers shifted | rewrite `mov w1,#code` per class | `tablet-mtk/audio/fix_aidl_codes.py` |
| every AudioTrack fails "controller never populated by system_server" | A17 sends code 115 getPermissionController, A16 maps it to another method | repoint jump-table entry | `audio/patch_server_codes.py` |
| system_server dies on audioserver_lifecycle thread | A16 `populatePermissionState` returns EX_ILLEGAL_ARGUMENT for enum >= 16 | return success | `audio/patch_audiopermission.py` |
| `openOutputStream` crash (length_error) | metadata ABI changed 16 -> 17 | fail with -EINVAL (no output) as a last resort | `audio/patch_audiohal50.py` |

## 7. HAL shims (see hal-shims.md)

| Need | Shim | File |
|---|---|---|
| AIDL IFingerprint over HIDL 2.1 | Java, `app_process`, hand-marshalled HwParcels | `m30s/fphal/` |
| AIDL IHealth over HIDL health 2.x | Java shim | `tablet-mtk/health/` |
| AIDL IVibrator over HIDL 1.3 or sysfs | Java shim | `tablet-mtk/vibrator/` |
| AIDL ILights | Java shim (backlight sysfs) | `tablet-mtk/lights/` |
| Telephony features missing (`radio.access`, `calling`, `data`, `messaging`) | permission/feature xml | `tablet-mtk/telephony/android.hardware.telephony.a17.xml` |
| lmkd with no PSI and an in-kernel LMK | replacement lmkd | `tablet-mtk/lmkd/lmkd_inkernel.c` |

## 8. One UI donor track (see track-b-oneui-donor.md)

| Symptom | Cause | Fix | File |
|---|---|---|---|
| `/product` of the image invisible, Google layer missing | the phone mounts its own product partition (sda27) over `/product` | put the Google layer under `/system/system_ext` | `m30s/oneui/build_oneui_port.py` step 5d |
| Health: `HealthInfo` null in BatteryService | AIDL IHealth declared by `vendor-a17` for the Pixel shim | hide that vendor fragment at `early-init` with an empty bind-mounted manifest | `m30s/oneui/rc/00_health_hidl.rc` |
| Kernel oops in `tz_uiwsock_poll` (`circ_buf_bytes_used`) ~15 s after launcher | `com.samsung.sec.android.teegris.tui_service` polls the TEEgris TUI socket | remove the apk | `build_oneui_port.py` |
| Factory Reset Protection page in the wizard | donor wizard honours FRP from `persistent`/`steady` | user signs in with the previous account; never bypass | `m30s-quirks.md` |
| SystemUI/launcher cannot be layered on a GSI | Samsung `Sem*` framework APIs | whole-system port | `docs` in `track-b-oneui-donor.md` |

## 9. Pixel layer track (see track-a-pixel-gsi.md)

| Symptom | Cause | Fix | File |
|---|---|---|---|
| SystemUI crash-loop, black screen with gesture navigation | back-gesture TFLite model SIGILL on Exynos 9611 | `device_config put systemui use_back_gesture_ml_model false` at every boot | `m30s/img/rc/05_gesture.rc` |
| system_server 26-55 % CPU at idle | GMS Personal Safety streams accelerometer at 10 ms | `pm disable` PSAService, PersonalSafetyService, SndDetectionService at every boot | `m30s/img/rc/06_nosensorhog.rc` |
| BiometricService spins on `IVirtualHal` (4 log lines/s) | face feature declared, no HAL | delete `android.hardware.biometrics.face.xml` | `build_a17.py` |
| 3 GB phone memory with no swap, kswapd 25 % | vendor fstab has no zram | 3 GB zstd zram service | `m30s/img/rc/03_zram.rc` |
| Phone slow for an hour after flash | no oat files can be built offline | first-boot dexopt service | `tablet-mtk/firstboot/`, `m30s/img/rc/04_precompile.rc` |
| 5 GHz hotspot "not available in your country or region" | `config_wifi5ghzSupport=false` in the Pixel Wi-Fi resources | static overlay on `com.android.wifi.resources` with `targetName="WifiCustomization"`, ACS off | `m30s/pixel/overlay-m30s-wifi/` |
| Display rounded corners / cutout | Pixel assumes its own panel | display overlay | `m30s/pixel/overlay-m30s/` |
| Pixel and Samsung HDR toggle | HDR10 black video | do not enable | `m30s/pixel/display-app/` |

## 10. Samsung hardware quirks (see m30s-quirks.md)

Hotspot single-channel concurrency on SLSI Wi-Fi, proximity sensor only as `com.samsung.sensor.physical_proximity`, front and rear camera conflict (HAL makes device 1 conflict with device 0), SD card and `/sdcard` being `/data/media`, SLMK userspace lmkd props, FRP, IMS. Not scripts, notes only.

## 11. MTK-only (see lenovo-tb-x606v-mtk.md)

MTK vendor codec XML (`audio/mpeg-L2` decoder aborts system_server): `tablet-mtk/vendor/fix_vendor_codecs_mp2.py`. Vendor ueventd and seccomp additions: `make_vendor_ueventd.sh`, `seccomp_add.sh`. TWRP zip for vendor edits: `tablet-mtk/twrp/`. Magisk modules, CPU overclock, ROM Tuner: `tablet-mtk/magisk/`, `tablet-mtk/kernel/`, `tablet-mtk/porting/`.
