# Samsung Galaxy M30s (Exynos 9611) quirks

Facts and findings specific to the SoC family and Samsung vendor that matter on any Exynos 9610/9611 phone. Contents: 1 Wi-Fi and hotspot, 2 sensors, 3 camera, 4 display, HDR and jank, 5 storage and `/sdcard`, 6 boot and bootloader, 7 radio and identity, 8 Knox, FRP, TEE services, 9 memory and lmkd.

## 1. Wi-Fi and hotspot (SLSI "wlbt")

- Client Wi-Fi works on 2.4 and 5 GHz (5260/5660 MHz seen, 292-433 Mb/s).
- Hotspot errored, then the 5 GHz hotspot said "not available in your country or region". Not the country: the driver reported CA, the regulatory table loaded, channels 149-165 clean in nl80211. Cause chain:
  1. The Pixel Wi-Fi resources default `config_wifi5ghzSupport=false` (OEMs set it; the Samsung vendor overlay `/vendor/overlay/SoftapOverlay` only sets channel lists: 2.4 GHz "1-11", 5 GHz "149" and `config_wifi_softap_acs_supported=true`), so `isSoftApBandSupported(5GHz)` is false and the 5 GHz capability list is empty. Fix: static overlay on `com.android.wifi.resources` with `android:targetName="WifiCustomization"` setting `config_wifi5ghzSupport=true` (`m30s/pixel/overlay-m30s-wifi`).
  2. The vendor hostapd (Android 10 HIDL 1.0) cannot do ACS on 5 GHz ("Failed to create config params"): same overlay sets `config_wifi_softap_acs_supported=false`, so the framework picks a channel from the Samsung lists.
  3. Single-channel concurrency: the SLSI driver runs the AP only on the client's channel. With the client on a 5 GHz DFS channel (52-64, 100-144) hostapd fails with `slsi_start_ap: Rejecting AP start req at host (invalid channel)`. Not fixed; options are an init watcher that moves the client or an AP-only band choice. Workaround: client on 2.4 GHz or non-DFS.
- The vendor HAL has no `getUsableChannels`, the framework falls back to the nl80211 channel list. The `IOffload` HAL is absent and harmless; BPF tether maps are fine once netbpfload works.
- Country code is auto-detected; do not hard-code anything beyond what the driver or framework needs. Time zone is a separate setting.
- Debug: `logcat -s hostapd WifiService SoftApManager`, `iw`/`cmd wifi status`, `dumpsys wifi | grep SupportedChannelListIn5g`.

## 2. Sensors

- Accelerometer, gyro (ICM42605M), magnetometer (AK09918C), step counter work. No ambient light sensor in hardware.
- Proximity is exposed only as `com.samsung.sensor.physical_proximity` (type 65592, permission `com.samsung.permission.SSENSOR`, wake-up flag). Android's `TYPE_PROXIMITY` is missing, so the screen does not blank against the ear and apps see no proximity sensor. Stock Samsung framework synthesises it; on a GSI it needs a vendor sensor HAL change or a shim. On One UI the donor framework handles the Samsung type (not yet verified in a call).
- GMS Personal Safety (`SensorStreamer`, 10 ms accelerometer) burns 10 % of an RT thread and 26-55 % of system_server when idle: disable the three services at boot (`m30s/img/rc/06_nosensorhog.rc`).
- Magnetometer-less tablets get a software compass shim (`tablet-mtk/compass`).

## 3. Camera

- Rear camera works on the GSI track (stock camera opens, a 3000x4000 JPEG with real content is saved). Front camera opens and streams (S5K3P8SP, 2304x1728).
- Samsung's camera HAL makes device 1 conflict with device 0: a process holding the rear camera (an adb session, a stuck app) produces "camera error, cannot connect" for the front one. Force-stop the camera app first; this was the user's reported error, not a front camera fault.
- HAL noise while previewing (`PIPE_VRA wait timeout`, `Failed to get Internal Bayer Buffer`) is harmless. GCam is impossible (no Camera2 FULL level 3 here).
- One UI: donor camera provider client 2.4-2.6 + Samsung 4.0 matches the vendor; camera device 5.0 client has no vendor HAL; test by opening the camera app and `dumpsys media.camera`.

## 4. Display, HDR, jank

- One mode, 1080x2340 at 60.00 Hz (Super AMOLED): no refresh rate to unlock.
- HDR: the DT has no HDR node. Synthesising HDR10 caps in the DSIM driver (`patches/kernel-4.14/hdr`) produced black HDR video in YouTube. Keep HDR off (the `display-app` screen-mode app has an HDR toggle; its summary text was reworded so it does not read like a state).
- Rendering is real: GLES `ARM, Mali-G72, OpenGL ES 3.2`, Vulkan, HWC layers `DEVICE`, Skia (OpenGL). The Pixel 9a shade is simply heavy for 3 Mali cores at 1080x2340: GPU time scales with pixels (720x1560 halves GPU time). Mali power policy, MIF max, Skia Vulkan, `debug.sf.latch_unsignaled` gave no measurable win. Reduce drawing instead of tuning.
- Cutout/corners: the Pixel overlay assumes its own panel; ship `overlay-m30s` (corner radius).

## 5. Storage and `/sdcard`

The internal `/sdcard` is `/data/media` on the f2fs userdata partition (sda32); an exFAT SD card is separate. Never delete, overwrite, move or format anything under `/sdcard`, `/storage/*` or the SD card. TWRP "Format Data"/"Wipe Data" delete `/data/media`. Backup plus selective wipe: `flashing.md`.

## 6. Boot and bootloader

- A-only, no `super`, system-as-root (`/dev/root` is `/system`), vbmeta 64 KB, boot has no ramdisk.
- Bootloader command line (from a disassembly of `sboot.bin`): the bootloader itself appends `skip_initramfs rootwait ro init=/init root=/dev/sdaN` with N the PIT id of `SYSTEM` (25), independent of vbmeta, so a disabled vbmeta only removes the `root=/dev/dm-0` verity path. It also appends `androidboot.dtbo_idx` and the `em.*` values: keep `dtb` and `dtbo` stock. The fallback `boot-a14-permissive-root.img` was never needed.
- Samsung boot image header v1 with an AVB footer; swapping the kernel with `repack_boot.py` works; flash vbmeta-disabled once.
- Stock kernel is `CONFIG_ALWAYS_ENFORCE`; a kernel with permissive support is needed for a ported policy.
- Samsung init prints boot reasons (`persist.sys.boot.reason`) and runs `fsdbg` on shutdown; `init: Service X has 'reboot_on_failure'` is the usual loop cause.
- Samsung SLMK: `ro.slmk.*` props, in-kernel lowmemorykiller parameters read 0; stock `lmkd` is Samsung's build and ignores props a GSI lmkd would use.

## 7. Radio and identity

- Shannon modem, Samsung RIL v4.0 (`libsec-ril`), HIDL radio 1.4 on slot1 and slot2 plus `vendor.samsung.hardware.radio` 2.x. `efs`, `sec_efs`, `cpefs` hold IMEI and calibration: back up, never write. Never invent or reuse an IMEI; keep IMEIs and serials out of the repo (a `DEVICE-IDS.md` is gitignored).
- No SIM during development: `gsm.sim.state=ABSENT`; calls, SMS, data, proximity blanking in calls are human-test items. IMS/VoLTE is not provided by a GSI; on One UI it is an open item (`imsservice`/`imsd` vs the vendor's IMS).

## 8. Knox, FRP, TEE services

- Bootloader unlock trips Knox; Samsung Pay/Wallet, Secure Folder, Play Integrity strong attest do not work.
- FRP: a fresh Samsung wizard after a `/data` wipe shows "An unauthorised attempt has been made to reset your device..." and requires the Google/Samsung account that was on the phone. Tell the owner beforehand; do not bypass.
- TEEgris (TrustZone) Samsung clients: `TEEgrisTuiService` polls a socket the 4.14 TZ driver cannot handle and oopses the kernel (`tz_uiwsock_poll`); remove the app. Other Knox/TEE clients log failures and are non-fatal: `engmode_binder_server`, `STORK_BIRD`, `vaultkeeper`, `cass`.
- Missing Samsung HALs the donor expects (non-fatal): `biometrics.face`, `tlc.hdm`, `mpos_tui`, `eden_runtime`/`enn_aux` (NPU), `ofi` 2.x (vendor has 1.0), AIDL keymint V5 (keymaster stays HIDL 4.0), `hermes`, `rtts`, `skpm`, `snap` V3 (vendor 1.2), `vibrator` V5 (vendor 2.1).

## 9. Memory

5.5 GiB RAM and no zram line in the vendor fstab: add 3 GB zstd zram (`03_zram.rc`); the first dexopt otherwise starves the phone. First-boot load average above 20 for ten minutes is normal on One UI.
