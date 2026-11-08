# Track A: AOSP GSI plus a Pixel layer

Result on the M30s: Android 17 (Google GSI `aosp_arm64-exp-DP11`) with a Pixel 9a layer boots, runs the Pixel launcher, SystemUI and Settings, Wi-Fi (client, 5 GHz hotspot), rear and front camera, fingerprint (shim), Bluetooth, battery reporting. Telephony tested without a SIM only, audio needs a person. The same recipe ran Android 14, 16 and 17 GSIs on the MTK tablet. Contents: 1 inputs, 2 pipeline, 3 Pixel layer, 4 what the vendor needs, 5 first boot and dexopt, 6 known gaps.

## 1. Inputs (all public)

| Input | Source | Used for |
|---|---|---|
| Google GSI `aosp_arm64-exp-*.zip` (`system.img` raw ext4, `shared_blocks` set) | dl.google.com/developers/android/.../gsi | base system |
| LineageOS 23.2 (Android 16) GSI, ext4, GApps | SourceForge misterztr-gsi | donor for the Android 16 audioserver and library closure, `com.android.vndk` bits |
| crDroid 10.13 (Android 14) GSI `arm64_bgN` | github naz664/crDroid_gsi | Android 14's init + linker closure (first stage), VNDK v30 APEX, `30.0.cil` / `30.0.compat.cil` sepolicy mapping |
| Pixel factory image (e.g. `tegu` = 9a) | Google | Pixel apps, overlays, fonts, SystemUIGoogle, Launcher, setup wizard, Trichrome/WebView |
| MindTheGapps (arm64) | GitHub | GmsCore, Phonesky, GSF, partner setup, sync adapters |
| AOSP platform test key (`platform.pk8/x509.pem`) | public AOSP | re-signing Pixel apps so they can run as platform |

Pin SHA-256 of each in the workflow. The factory image nests a stored zip with a deflated `product.img` (4.8 GB): stream only that file with HTTP ranges (`scripts/m30s/oneui/fetch_factory_product.py`) instead of downloading 4 GB.

## 2. Pipeline (`scripts/m30s/img/build_a17.py`, forked from the tablet builder by `make_build_a17.py`)

Everything is debugfs on an ext4 copy; no mount, no root, works on macOS.

1. Grow to the partition size, drop `shared_blocks`.
2. init boots SELinux permissive; `build.prop`: debuggable (adb), `ro.hardware.egl=mali`, slow-device timeouts, Samsung identity props (real fingerprint of the phone stays; product brand/device/model).
3. Patched copies of libc and the linkers (clone3 stub, MADV_WIPEONFORK), libprocessgroup_setup, libui, libmeminfo, libbinder, libandroid_runtime in `/system`; libc and linkers also inside the runtime APEX (repacked and re-signed with a generated key). `patch-index.md` section 3.
4. VNDK APEX of the vendor's level plus SELinux mapping `30.0` (`29.0` on the tablet), cgroups.json without blkio, `vndk-sp` links.
5. `com.android.virt.apex` payload EROFS -> ext4 (the framework still references its jar; removing the APEX gives `NoClassDefFoundError` in zygote).
6. services.jar, service-connectivity.jar and the tethering/bluetooth/swcodec files that must be patched but are signed: patched copies in `/system/etc/bpf.a17`, `/system/bin/netbpfload.{a17,tracer}`, bind-mounted by `00_bpf_bind.rc`.
7. Audio: Android 16's audioserver and closure run privately from `/system/lib64/a16audio`; A17 clients are given A16's AIDL numbers.
8. lmkd replacement for the in-kernel LMK where PSI is absent; health, vibrator, lights shims; RT cgroup budgets; console only on request.
9. Optional layers: Pixel (stage with `scripts/m30s/pixel/stage_pixel_phone.py`), MindTheGapps, Dolby (tablet only, owner's own firmware).
10. Compress, split into parts under 2 GiB (GitHub release asset limit), `SHA256SUMS`.

First stage: the M30s `boot.img` has no ramdisk and A17's `/system/bin/init` is second-stage only. `/init` is a symlink to a static launcher (`scripts/m30s/debug/fslaunch.c`) that mounts devtmpfs, sends stderr to kmsg and runs Android 14's init through Android 14's `linker64` with `LD_LIBRARY_PATH=/system/a14fs/lib64`; that init mounts everything and ends in `execv /system/bin/init selinux_setup`. `scripts/m30s/img/make_a14fs.py` builds the closure (needs the NDK; use NDK builds for helpers, musl static binaries die in bionic's linker).

## 3. Pixel layer (`stage_pixel_phone.py`)

Take from the factory image: SystemUIGoogle (installed as SystemUI), SettingsGoogle (Settings), Nexus Launcher, wallpapers, setup wizard, Dialer, Messages, Photos, Gboard, Chrome, Trichrome, WebViewGoogle, about 26 overlays, fonts, media, permissions. Re-sign with the AOSP platform key. Fixes found on the way:
- GoogleConfigOverlay sets `config_servicesExtensionPackage` to a package the GSI lacks: patch it to `android.ext.services`, or system_server aborts.
- `.apk.gz` files: gunzip. WebViewGoogle is arm64-only with `multiArch`: `unset_multiarch.py` clears it, else PackageManager refuses it on a phone that also supports armeabi-v7a.
- Privileged apps need entries in the privapp allowlists; check every staged priv-app against the allowlists offline first: a missing entry hangs the boot on the animation (`tools/pixel/privapp-permissions-pixelphone-a17.xml`).
- Delete the face feature xml (no face HAL) and disable GMS Personal Safety sensor streaming (`m30s/img/rc/06_nosensorhog.rc`).
- Pixel back-gesture TFLite model SIGILLs on Exynos 9611: `05_gesture.rc` sets `use_back_gesture_ml_model false` at every boot.
- Display overlay (`overlay-m30s`) for corner radius and cutout; hotspot overlay (`overlay-m30s-wifi`), see `m30s-quirks.md`.
- Without the Pixel layer `02_webview.rc` picks the system WebView.

## 4. What the old vendor needs

- Vendor edits (`build_vendor_a17.py`): `/metadata` tmpfs line in the fstab (phone has no metadata partition), `ueventd.rc` copied into `/vendor/etc`, extra syscalls in the configstore/mediacodec/mediaextractor/c2 seccomp policies, the AIDL health fragment, MP2 codec type removed, `fileencryption=ice` dropped from the userdata line (format userdata once when coming from encrypted data), and the package-only signers removed from `vendor_mac_permissions.xml`. `/vendor` survives `system` reflashes.
- Kernel (`kernel.md`): PSI, BPF JIT, userfaultfd, permissive SELinux. The stock kernel is `CONFIG_ALWAYS_ENFORCE`, so without a custom kernel append an allow-all block to `plat_sepolicy.cil` (`make_allowall_cil.py`).
- zram: the Samsung fstab has no zram line; without swap the phone ran at 40 MB free and kswapd at 25 %. `03_zram.rc` creates 3 GB zstd zram.

## 5. First boot and dexopt

Offline builds cannot produce oat files. `zz_firstboot_dexopt.rc` runs pass 1 about 60 s after boot and pass 2 about 45 min later; `pm.dexopt.install=speed`. Expect an hour of slowness. Known non-fatal noise: fs-verity ENOTTY, no memevents ringbuffer, no power.stats HAL, `/efs/FactoryApp/cisd_*`, GMS safety-center `Unexpected safety source: AdvancedProtection`.

## 6. Known gaps and results

Measured results are in `testing.md` and `m30s-quirks.md`: launcher janky 14-16 % (Pixel 9a launcher on 3 Mali-G72 cores), shade 15-19 %; no vibrator shim in the first image (add `tablet-mtk/vibrator`); IMS/VoLTE absent (`telephony.ims` declared, no implementation); the image contains Google's apps and Samsung's vendor, so it is private only.
