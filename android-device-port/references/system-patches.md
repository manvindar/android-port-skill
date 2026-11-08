# System-side patching techniques

How the patches in `patch-index.md` are made, so you can write the next one. Contents: 1 offline image editing, 2 native binaries, 3 signed apex files, 4 dex and jar patching, 5 overlays, 6 init rc overlays, 7 SELinux and VNDK, 8 audio closure.

## 1. Offline image editing with debugfs

All image work is `debugfs -w -f cmds` on an ext4 file: `write`, `mkdir`, `symlink`, `set_inode_field mode/uid/gid`, `ea_set -f label.bin path security.selinux` (label files are NUL-terminated, e.g. `u:object_r:system_file:s0\0`), `rm`, `dump`, `rdump`. No mount, works as a normal user on macOS (e2fsprogs is keg-only: `/opt/homebrew/opt/e2fsprogs/sbin`). Run `debugfs` by its path, not through a variable containing spaces. Always `e2fsck -fn` the result and check block count: `shared_blocks` must be gone for a writable image.

Rules learned: new file labels matter (an unlabeled file gets `unlabeled`, a denial in enforcing mode); copy executables with mode 755 and the right label (`u:object_r:bpfloader_exec:s0` for netbpfload copies); libraries `system_lib_file`; the builders have `put(src, dst, mode, uid, gid, ctx)` and `replace()` helpers; a `made` set avoids re-creating directory chains.

## 2. Native binaries (aarch64)

Technique used by every `patch_*.py`: find the code by something that survives rebuilds, assert what is there, change one or two instructions.
- By string: find the message text, then the `adrp x,PAGE ; add x,x,#OFF` pair that builds its address (`xref_str.py`), then walk back to the guard branch (`b.cond`, `cbz`, `tbz`) that skips the message and turn it into `b` (`0x14000000 | imm26`). NOP is `0xd503201f`, `mov w0,wzr` `0x2a1f03e0`, `ret` `0xd65f03c0`, `mov x0,#0` `0xd2800000`.
- By symbol: `.dynsym`, or `.gnu_debugdata` (an xz-compressed mini ELF with function symbols; used to find `nativeGet...` JNI functions in libservice-connectivity).
- By instruction pattern: wildcard immediates and registers (`pat('7120', None, '5200')`), assert exactly one match, mask hint instructions (`bti c`, `paciasp`) that new compilers insert.
- By call: a function that makes one distinctive syscall (`bpf` with `mov w0,#280`), then the `sub sp,sp` before it.
Always assert the original bytes or match count; an unknown build must stop the tool. Keep a per-build table only when pattern matching cannot disambiguate.

Never overwrite a library in place on a running system: write a new file and `mv`, or `cat >` from recovery.

## 3. Signed apex files

APEX contents are verified (AVB, signature), so edit by bind mount: put the patched copy in `/system` and add to an rc `on load-bpf-programs` (or `early-init` for non-bpf) a `mount none /system/lib64/x.oneui.so /apex/com.android.tethering/lib64/x.so bind`. For `/system/apex/*.apex` that you must change in place (libc in the runtime APEX), `repack_apex.py` replaces files in the ext4 payload and re-signs with a generated AVB key (apexd accepts it: system apexes are trusted, only the embedded pubkey must match). Compressed apexes (`.capex`, `*_compressed.apex`) hold the real payload as `original_apex` inside the outer zip; `apex_member()` in `build_oneui_port.py` and `apex_extract.py` unwrap it. EROFS payloads (virt apex) become ext4 with `virt_to_ext4.py`.

## 4. Dex and jar patching

- `classes.dex` of `services.jar` is a dex 041 container: several dex files back to back (each begins `dex\n041\0`; header offsets are absolute in the container). Find a method by name through the string/type/method tables (`method_name()` helpers), or by bytecode pattern with wildcarded 16-bit indices.
- Typical edits: NOP an `if-eqz` (`0x38xx` -> `0000`), `goto/16` (`0x29 0x00 off16`), `const/4 v2,#1 ; nop` replacing `invoke-static ; move-result`, change a catch type index (uleb128 re-encode must keep the length), return-void at entry.
- After editing fix each touched dex's SHA-1 signature (bytes 12..32 over the file after byte 32) then the Adler-32 checksum (bytes 8..12 over the file after byte 12). Rewrite the jar with the same entry names and compression. Delete stale `oat/arm64/services.{art,odex,vdex}` so ART does not map a mismatching oat.
- `dexdump -d` (build-tools 36) on the extracted `classes.dex` is the reading tool; it needs the container, not a slice.
- Framework resources (`framework-res.apk`): rebuilt with aapt2, signed with the platform test key; write from recovery with `cat`.

## 5. Overlays

Static overlays are the cheapest "patch" for configuration:
- Manifest: `<overlay android:targetPackage="android" android:isStatic="true" android:priority="999"/>`. For `com.android.wifi.resources` (an overlayable APK in the Wi-Fi module) add `android:targetName="WifiCustomization"`, else the state is `STATE_NO_IDMAP`.
- Build with `aapt2 compile --dir res` + `aapt2 link -I <framework>` + `zipalign -p` + `apksigner`. Link against `android.jar` for public resources (`config_*` overlayable in `android`) and against the **donor `framework-res.apk`** for private ones (e.g. `config_servicesExtensionPackage`).
- Location: `/product/overlay`, `/vendor/overlay` or `/system/system_ext/overlay` (on the One UI image `/product` is shadowed, use system_ext). Static overlays need no signature match on system partitions; signing with the test key is fine.
- Examples shipped: `m30s/pixel/overlay-m30s` (display corners), `overlay-m30s-wifi` (5 GHz hotspot, ACS off), `m30s/oneui/overlay-extservices`.
- A minimal package can replace a missing module: `m30s/oneui/modulemetadata` (empty module metadata).

## 6. init rc overlays

Files in `/system/etc/init/*.rc` are processed alphabetically; `00_*` for early things, `zz_*` to override vendor and system rcs (e.g. `zz_sf_latch.rc` forced `debug.sf.latch_unsignaled=0` after `vndk.rc` reset it). Patterns used: services with `seclabel u:r:shell:s0` or `u:r:su:s0` for helper jobs, `disabled` + `oneshot` + `on property:sys.boot_completed=1` to start after boot, `on early-init` for bind mounts that must precede servicemanager reading vintf manifests, `on load-bpf-programs` for the tethering bind mounts. Examples: `m30s/img/rc/` (webview, zram, precompile, gesture, sensor hog), `tablet-mtk/bpf/00_bpf_bind.rc`, `m30s/oneui/rc/00_health_hidl.rc`.

To drop `reboot_on_failure` from an OEM service rc, rewrite the file in the image (`netbpfload.rc`); services defined by the apex rc cannot be edited that way, patch the binary instead.

## 7. SELinux and VNDK

- Vendor policy is old (v29/30): supply the platform mapping `NN.0.cil` and `NN.0.compat.cil` plus `com.android.vndk.vNN.apex` from a GSI of the vendor's era (Android 14's crDroid GSI for 30), and `vndk-sp-NN` links. The donor One UI image carries v33 only.
- First-stage mounts and policy compile happen in init: if there is no marker and the kernel log ends in `init`, read secilc errors in kmsg. Duplicated declarations between system_ext and vendor policy break the compile: `sepol_check.py` with a host `secilc` removes the system-side copies (6 felica typealiases on the A26 donor).
- Permissive: kernel with permissive support, else allow-all CIL (`make_allowall_cil.py`, `make_permissive_cil.py`). Expect thousands of denials; fix before enforcing only if the product needs enforcing.
- `vendor_mac_permissions.xml` of an Android 11 vendor breaks A17's parser: drop package-only signers.

## 8. Audio closure

Vendor audio HAL 5.0 is HIDL; A16/A17 frameworks dropped libaudiohal 5.0. Approach: copy Android 16's `audioserver` plus its library closure from a public GSI (`audio/a16_closure.py DONOR_IMG OUT`) into `/system/lib64/a16audio`, set `LD_LIBRARY_PATH` in the service rc (`install_a16_audio.sh`), then reconcile the AIDL transaction numbers (`fix_aidl_codes.py`, `patch_server_codes.py`) and the permission controller (`patch_audiopermission.py`). `patch_audiohal50.py` makes a crashing open fail cleanly. Audio output remained a human-test item.
