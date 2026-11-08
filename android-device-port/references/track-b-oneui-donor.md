# Track B: Samsung One UI donor, whole-system port

Result on the M30s (Exynos 9611, Android 11 vendor, kernel 4.14.113): One UI 9 (Android 17) from a Galaxy A26 donor (`A266BXXUCDZJ6`) boots to the Samsung setup wizard, display and Wi-Fi scan work, system_server stays up, and a clean flash of the rebuilt image reproduces it (2026-11-08). Features beyond the wizard were not yet tested when this was written; see `testing.md` for the matrix and `docs/oneui9/RESULTS.md` of the port repo if present. Contents: 1 why a whole system, 2 donor choice, 3 acquire and unpack, 4 ext4 repack and debloat, 5 build steps, 6 Google layer, 7 first-boot blockers, 8 data and FRP, 9 flash and regression proof.

## 1. Why a whole system

Samsung SystemUI, launcher and Settings call `com.samsung.android.*` and `Sem*` APIs that exist only in Samsung's `framework.jar` / `services.jar` (`sec_platform_library.jar`, `semwifi-service.jar`, `secinputdev-service.jar`...). They cannot run on a Google framework, so there is no "layer" shortcut: you take the donor `system` (framework, services, 200+ priv-apps) and keep only the device's vendor, boot and modem. The donor `product` partition of the A26 was 2.3 GiB of Google apps only (Velvet, Chrome, Gmail, Maps, Phonesky...) and adds no One UI look: it is dropped.

## 2. Donor choice

Pick a donor with the newest One UI whose hardware is closest and whose firmware is free to download. Community ports exist for some SoC siblings but are closed and not reproducible; plan to build your own with a CI-independent local build (donor files never go to git or CI).
- M30s: no official firmware beyond Android 11; siblings of the same SoC family stop at Android 12-13. Ports on the SoC family used S25 FE (One UI 8.5), A54/M34 (One UI 6.1). The A26 5G (Exynos 1380) gave One UI 9 with a free update server.
- Samsung's vendor stays at Android 11 (VNDK 30, HIDL only). The donor framework still ships HIDL clients for graphics (allocator 2-4, mapper 2-4, composer 2.1-2.4), camera provider 2.4-2.6, radio 1.0-1.4, keymaster, health, gnss, drm, media c2/omx. AOSP A17 dropped those; Samsung's did not, so One UI needs fewer graphics/camera/radio shims than the GSI (the desk analysis is `vintf_gap.py`).
- Where it needs work: audio (donor has libaudiohal 6.0/7.x/aidl, no 5.0), VNDK (donor carries v33 only), SELinux mapping, init, kernel-facing network code (tethering apex, netbpfload), Knox/TEE clients.

## 3. Acquire and unpack

- The AP file only (7.98 GB zip from the free SamFw server, headless browser, no login). BL, CP, CSC and HOME_CSC are never touched. Keep about 15-20 GB free.
- `scripts/m30s/oneui/unpack_donor.py FIRMWARE.zip OUT [--parts ...]`: finds `AP_*.tar.md5`, streams `super.img.lz4` through `lz4 -d` (needs `brew install lz4 erofs-utils`), `lpunpack.py` cuts the partitions out of the sparse `super` (system 7323 MiB, product 2332, vendor 1044, odm 1; no system_ext partition, it is `/system/system_ext`), `fsck.erofs --extract` unpacks.
- Without an EROFS mount (macOS), read EROFS directly: `scripts/m30s/oneui/erofs.py` is a read-only reader for the uncompressed images Samsung ships and returns mode, uid, gid, `security.selinux`, `security.capability` per file. `fsck.erofs --extract` as a normal user loses uid/gid. `erofs_du.py` gives per-directory sizes for debloat planning.
- The donor's `system.img` EROFS (7.2 GB) cannot be regenerated quickly: keep it. Delete everything else you can rebuild.

## 4. EROFS to ext4 and debloat

The kernel has no EROFS driver (and no overlayfs), so the system is repacked as ext4 sized to the partition (4800 MiB).
- `scripts/m30s/oneui/erofs2ext4.py SRC OUT [--size-mib 4800] [--exclude debloat.txt] [--dry-run]`: writes with debugfs in 300 MiB batches (about a minute), keeps mode, uid, gid, symlinks, SELinux label and file capabilities. Dry-run prints the total.
- `debloat.txt` removed 77 paths (3253 MiB): OCR data 180, TTS voices ~570, SmartSuggestions 175, OneDrive, Samsung Cloud, Your Phone, Bixby voice, Routines, photo/video editors, Galaxy Store, AR Emoji, Samsung Pass, Secure Folder, Find My Mobile, device care, TalkBack, `saiv` AI models, `etc/*removal` data. Kept: framework, services, SystemUI, launcher, Settings, dialer/contacts/telephony, camera, gallery, keyboard, Knox core, My Files. Result 3949 MiB used of 4800; with the Google layer and shims 4681 MiB. Next candidates when tight: AI libs in lib64, fonts, SamsungCamera, SecMyFiles.
- Rule for the list: remove what is big and not needed for boot, phone, Wi-Fi, camera, settings, launcher; nothing that Settings/SystemUI/telephony binds to by name.
- Inventory what cannot work: `inventory_oneui.py TREE OUT.json` lists every APK with package, sharedUserId, required `<uses-library>` against the shared libraries the donor declares.

## 5. Build steps (`scripts/m30s/oneui/build_oneui_port.py`, about 5 s, debugfs on a copy)

```
python3 -I build_oneui_port.py --base system-oneui9.img --out system-oneui9-port.img \
  --a14fs DIR --vndk-dir DIR --audio-closure DIR --google-stage DIR --fphal   # JDK 17 on PATH for --fphal
```
1 init permissive (pattern patch); 2 build.prop (debuggable, egl, timeouts); 3 `/init` = launcher of Android 14's first stage + zram; 4 VNDK v30 APEX and sepolicy mapping 30.0 from the Android 14 GSI, system_ext policy de-duplicated against the vendor policy (host `secilc`, `sepol_check.py`); 4b `cgroups.json`; 5 bionic patches (clone3 stub, MADV_WIPEONFORK, libui gate, libbinder, libmeminfo, libprocessgroup_setup) in `/system` and inside the runtime APEX; 5b services.jar patches (`patch_services_oneui.py`: HintManager, isBuildConsistent, camera listener, Samsung health calls); 5c audio (Android 16 audioserver closure, `audio/a16_closure.py` on a public LineageOS GSI); 5d Google layer; 5e fingerprint shim (`--fphal`, face feature xml removed); 5f health (hidden vendor AIDL fragment); 6 bpf (netbpfload gates, device check, api window, LPM as hash; libnetd_updatable; libservice-connectivity ringbuf stubs; all bind-mounted by `00_bpf_bind.rc`); 7 overlay (ext.services); 7b module metadata; TUI service removed; bootdiag; adb root without authorisation (`ro.adb.secure=0`).

`patch_netbpfload.py` finds patch sites by the text of the kernel-gate messages (adrp+add xrefs), not by offsets, so it works on newer tethering builds; it asserts a minimum count of patched gates.

## 6. Google layer from public sources

The donor product was dropped, so WebView and Play come from public files: `fetch_factory_product.py` streams `product.img` out of the Pixel factory zip (HTTP range reader, sparse output, 4.6 GiB peak: delete it after staging); `stage_google.py product.img MindTheGapps.zip OUT --keys DIR --build-tools BT` stages TrichromeLibrary, WebViewGoogle (multiArch unset), GoogleWebViewOverlay, GmsCore, Phonesky, GoogleServicesFramework, GooglePartnerSetup and the Calendar/Contacts sync adapters. Skip the GMS Setup Wizard and Settings overlays (they target AOSP Settings). Check every priv-app against the donor framework-res allowlists offline (0 violations on the four priv-apps).

**Placement trap**: the vendor fstab mounts the phone's own product partition (sda27, Samsung stock content: `omc`, `preload`, `sipdb`) at `/product`. Anything under `/product` of the image is invisible at runtime. Put the layer under `/system/system_ext` (`app`, `priv-app`, `overlay`, `etc/permissions`, `etc/sysconfig`, `etc/default-permissions`). Find such shadowing with `mount --bind / /mnt/rv` and `ls /mnt/rv/product`.

## 7. First-boot blockers in the order they appeared (log line -> cause -> fix)

1. `NetBpfLoad: Android 25Q4 requires kernel 5.10.` -> reboot loop via `reboot_on_failure` -> add the message to the gate list.
2. SIGABRT in `ElfObject::ElfObject` "file ... is on device" -> bind-mounted copy lives on /system -> NOP device compare.
3. netd: `Failed to get program ... prog_netd_egress_stats` -> only 4.14 variant has api window [3300,3500) -> fake api 3499 at the program site only (faking it for maps hid the local_net_* maps).
4. system_server: `config_servicesExtensionPackage ... android.ext.services` -> overlay to `com.google.android.ext.services` (build it against the donor framework-res, not android.jar: private resource).
5. Google layer invisible -> /product shadowed -> move under system_ext.
6. BatteryService NPE on `ISehHealth` -> Samsung HealthRegCallbackAidl takes health data from the vendor's `vendor.samsung.hardware.health@2.0::ISehHealth` (HIDL) unless AIDL IHealth is declared; hide the vendor's AIDL fragment with an empty bind-mounted manifest at `early-init` (a Pixel-style health shim made it worse: BatteryService then wants the Samsung AIDL service); nop the two AIDL calls in services.jar.
7. `nativeGetNextMapKey failed: errno 524` on `local_net_access_map` -> LPM trie iteration needs kernel 4.20 -> create LPM maps as HASH.
8. `BpfRingbuf init failed` -> no ringbuf -> stub in libservice-connectivity (eventfd; `nativeInitLoopbackEventConsumer` returns).
9. `Call to getInstalledModules before metadata loaded` -> minimal `com.android.modulemetadata` (`MODULE_METADATA` meta-data pointing at an empty `<module-metadata/>`).
10. Kernel oops `tz_uiwsock_poll` -> remove `TEEgrisTuiService`.

Method note: each fix took 3-6 minutes because adb works for ~40 s per boot; the live patch + rebuild + hash compare loop is described in `boot-diagnosis.md`.

## 8. Data and FRP

- Selective wipe (`flashing.md` section 5) after changing systems. The previous system's package state, fingerprints and Google accounts are lost; say so.
- The Samsung setup wizard shows "An unauthorised attempt has been made to reset your device... connect to Wi-Fi or mobile to verify your identity": Factory Reset Protection from the persistent store survives the `/data` wipe. The owner signs in with the account that was on the phone. Never bypass FRP; if the owner cannot sign in, stop and discuss rollback (the GSI track has no FRP prompt).
- CSC and optics: the donor CSC content (`optics`, `prism`) is not part of the image; region features are off until a CSC is added. Radio/IMS: Samsung RIL and `libsec-ril` stay from the vendor; the donor telephony binds the vendor HIDL radio 1.4 and `ISehRadio` 2.x. IMS needs a separate effort.

## 9. Flash and regression proof

After the live patches pass, rebuild the image from the script, compare each patched file's sha256 with the live phone, flash the rebuilt image (`flashing.md`), selective wipe, reboot, and confirm boot_completed without any live edits. Keep the previous (GSI) release as rollback and agree a hard stop time with the owner before the experiment.

Sizing check at the end: e2fsck clean, 1228800 blocks, free about 118 MiB: in-place replacement of a patched file needs the same size or `cat >`.
