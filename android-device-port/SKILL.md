---
name: android-device-port
description: Port a newer Android (AOSP GSI plus a Pixel layer, or a Samsung One UI donor) onto an older Treble device whose vendor, kernel and bootloader stay as they are. Use when someone wants to run a newer Android on an old phone or tablet, when planning such a port (device recon, GSI or donor choice, size budget), when a ported system fails to boot (boot loop, no adb, system_server crash, kernel oops), when flashing and verifying system images through TWRP or fastboot, or when a ported image needs patches for an old kernel (4.9, 4.14), an old vendor (VNDK 29/30, HIDL-only HALs) or missing hardware shims (fingerprint, health, audio, hotspot).
---

# android-device-port

Field notes, scripts and patches from two real ports, each running a much newer Android on a frozen vendor and kernel:

- **M30s** (Samsung SM-M307F, Exynos 9611, kernel 4.14.113, A-only, Android 11 vendor): Android 17 GSI with a Pixel 9a layer (track A, shipped) and Samsung One UI 9 from a donor firmware (track B, booted to the setup wizard and stable).
- **TB-X606V** (Lenovo Tab M10 FHD Plus, MT8768, kernel 4.9.190, A-only, Android 10 vendor): Android 14, 16 and 17 GSIs plus a Pixel Tablet layer (MediaTek specifics).

Everything is private-use engineering: no donor firmware or vendor binaries are in this skill. You rebuild them from the user's own downloads.

## First: read the hard rules

Read `references/pitfalls.md` before touching a device. The short version: never touch `/sdcard` (it is `/data/media` on the same partition), never `recovery`, modem or bootloader partitions, never invent IMEIs, keep PINs and account passwords out of every file and message, donor firmware never goes to git or CI, wipes and flashes need the owner's explicit OK.

## Decision tree

1. **Recon the device** (`references/recon.md`). Answer, with evidence from the device: SoC, kernel version and config (`/proc/config.gz`), A-only or A/B, dynamic partitions or not, system-as-root, `ro.vndk.version`, vendor VINTF target level and which HALs are HIDL or AIDL, partition sizes, bootloader unlock state and the flash path (TWRP, fastboot, Heimdall), verified-boot state, what is encrypted.
2. **Pick the track.**
   - Same SoC family has a newer official Samsung firmware, or the user wants the OEM UI: **track B** (donor). Whole-system port; the donor's framework and services come with it. `references/track-b-oneui-donor.md`.
   - The user wants stock-like Android, or no suitable donor exists: **track A** (AOSP GSI, optionally a Pixel layer taken from Google's factory image). `references/track-a-pixel-gsi.md`.
   - A donor's product partition that holds only Google apps adds nothing; SystemUI and launcher of a donor cannot be layered on a GSI (they call framework APIs that exist only in the donor framework).
3. **Budget size** before anything else: the system partition is fixed (M30s 4800 MiB, tablet 3.8 GiB). A GSI plus Pixel layer fits; a donor needs a debloat list (7.2 GiB to 3.9 GiB on the M30s).
4. **Kernel** (`references/kernel.md`): list what the target Android needs that the old kernel lacks (PSI, BPF JIT, userfaultfd, LPM-trie iteration, ringbuf, `F_SEAL_FUTURE_WRITE`, `MADV_WIPEONFORK`, `close_range`, SELinux permissive). Fix by config, backport or userspace patch, in that order of preference. A real `uname` is kept; patch the call sites instead of spoofing.
5. **Build the image offline** with the scripts in `scripts/` (debugfs on an ext4 copy, no mount, works on macOS and Linux). Apply the fixes from `references/patch-index.md` as they become necessary; each row there is symptom, cause, fix, script.
6. **Flash and verify** (`references/flashing.md`): TWRP over adb, `dd` of the image, hash in 256 MiB windows, selective `/data` wipe that keeps `/data/media`, vendor and boot as appropriate, rollback image ready first.
7. **Diagnose the first boot from logs, not guesses** (`references/boot-diagnosis.md`). Almost every blocker in both ports was found from TWRP logs or `adb logcat -b all` captured across reboots; the loop is: read first failing line, find the cause, patch the file on the live system (`mount -o remount,rw /` during the boot window), then bake the patch into the build script and prove it with a clean flash.
8. **Test** (`references/testing.md`): feature matrix, jank bench, per-feature checklist. Report what was measured and what needs a person.
9. **CI** (`references/ci.md`) once the build is reproducible: GitHub Actions, private release for inputs, split and xz assets, SHA256SUMS.

## Quick map of the references

| File | Use it for |
|---|---|
| `references/recon.md` | commands and questions for the first hour |
| `references/flashing.md` | TWRP, fastboot, Heimdall, windowed hash verification, selective wipe, rollback |
| `references/boot-diagnosis.md` | where logs live after a failed boot, reading order, loop patterns |
| `references/track-a-pixel-gsi.md` | GSI plus Pixel layer pipeline and what it needed |
| `references/track-b-oneui-donor.md` | donor unpack, EROFS to ext4, debloat, port steps, One UI 9 first-boot blockers |
| `references/kernel.md` | kernel gaps, backports, patch files, config fragments, CI build |
| `references/system-patches.md` | init, SELinux, VNDK, first stage, bionic, audio, services.jar, overlays |
| `references/hal-shims.md` | fingerprint, health, vibrator, lights shims; how to write one by hand |
| `references/m30s-quirks.md` | Exynos 9611 specifics (hotspot, sensors, HDR, camera, FRP, radio) |
| `references/lenovo-tb-x606v-mtk.md` | MediaTek tablet specifics (ROM Tuner, CPU-OC kernel, Magisk, Android Auto) |
| `references/ci.md` | workflows and release layout |
| `references/testing.md` | test checklist and jank method |
| `references/pitfalls.md` | hard rules and expensive mistakes |
| `references/patch-index.md` | every fix: symptom, cause, fix, file |

## Layout of the bundled material

- `scripts/m30s/`: the M30s toolchain. `img/` (image builders, rc overlays), `oneui/` (donor unpack, EROFS reader, ext4 repack, the One UI build script and its patchers), `fphal/` (fingerprint shim), `pixel/` (Pixel layer staging, overlays), `policy/`, `probe/` (kernel capability probe), `debug/` (boot-time tools, bench), `backup/` (verified partition dump).
- `scripts/tablet-mtk/`: the TB-X606V patch library. Several M30s scripts call it as `A17_TOOLS` (libc, linker, libui, libbinder, services.jar patchers, netd/bpf patches, health and vibrator shims, Magisk modules, ROM Tuner support).
- `scripts/ci/`: workflows. `scripts/kernel-build/`: boot image repack, stable-merge helper, local MTK build.
- `patches/kernel-4.14/` (PSI backport series, HDR10 caps, touch boost), `patches/kernel-4.9-mtk/` (eight patches), `patches/kernel-config/` (config fragments).

Path mapping for the Lenovo reference and old script comments: `tb-x606v-android17/tools` = `scripts/tablet-mtk`, `tb-x606v-android16-port/patches` = `scripts/tablet-mtk/android16`, `tb-x606v-kernel` = `patches/kernel-4.9-mtk`, `m30s-port-main/tools` = `scripts/m30s`, `m30s-kernel` = `patches/kernel-4.14` + `patches/kernel-config`.

Scripts keep their original repo-relative paths in comments; the layout above mirrors those repos (`tools/<dir>`), so run them from `scripts/m30s` or `scripts/tablet-mtk` as the docstrings say. Set `A17_TOOLS` to `scripts/tablet-mtk`. Docstrings at the top of each script give usage; read them before running.

## Working rules for the agent

- Read-only first. Probe with `adb shell` as the shell user, push nothing, until the owner agrees.
- One change per boot when diagnosing, and keep the previous state restorable.
- Every live edit on the phone must be baked into the build script and compared (hash) with the live files before it counts.
- Capture logs across reboots: `adb logcat -b all -v threadtime > file` in a loop with `adb wait-for-device`; the phone may reboot every minute.
- Free disk matters: images are 4-5 GB each; delete intermediates you can regenerate, keep the ones you cannot (a donor EROFS that took hours to fetch).
- Report honestly: say what booted, what failed, the first failing log line, and what was not tested.
