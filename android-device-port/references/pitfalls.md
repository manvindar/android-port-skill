# Hard rules and expensive pitfalls

Read before touching a device. Contents: 1 hard rules, 2 privacy and publishing, 3 device safety, 4 host and tooling, 5 diagnosis traps, 6 build traps.

## 1. Hard rules

1. **Never touch `/sdcard`**: preserve existing files under `/sdcard`, `/storage/*` and an SD card. Copying explicitly requested new image files there is allowed; do not delete, overwrite or format existing contents. On Samsung `/sdcard` is `/data/media` on the data partition, so TWRP Format/Wipe Data destroys it. Reads and `adb pull` are fine; scratch files go in `/data/local/tmp`.
2. **Never write `recovery`, modem/CP, bootloader (`bota*`, `sboot`), `efs`, `cpefs`, `persist`, `nvram`.** TWRP lives in `recovery`.
3. **Honor current authorization.** Build/flash/reboot scope already granted persists across turns. Wipes, extra partitions and disruptive experiments are not implied. One operator owns device transactions; stop a failed transaction before diagnosing or retrying.
4. **No invented IMEIs**, no cloned identifiers. Radio identity partitions are backed up, never written.
5. **PIN/password rule**: an unlock PIN may be used for adb unlock only; never written to any file, doc, commit, log or message. Never bypass FRP or account locks.
6. **Separate source from binary inputs.** Honor owner-selected repository/release visibility. Sanitize public source in an isolated checkout; do not push historical private history, logs, credentials or device identifiers. Pin authorized binary downloads independently.
7. **Keep more than 10 GB free** on the build host; delete regenerable intermediates, keep irreplaceable ones.
8. **Commit and push as you go**; do not leave the only copy of a fix as a live edit on the device or in an uncommitted tree.
9. Set the debug window and rollback with the owner before an experimental flash; stop at the agreed time.

## 2. Privacy and publishing

- Keep the owner-selected visibility. If publishing is already authorized, complete and verify it without a repeated permission flow. Scrub before any commit: serials (`ro.serialno`, adb serial), IMEIs, MACs, SIM props, Wi-Fi names and passwords, tokens, account names, personal files, screenshots with personal content. Scan staged files: `git diff --cached | grep -iE "imei|serial|token|password|[0-9]{15}"`.
- Publish only the artifacts in the owner's requested scope, with accurate component provenance and the appropriate source/credits. Do not infer visibility from the firmware track.
- Do not extract a third party's bundled identity or credential (an accessory certificate in an app) into new builds.

## 3. Device safety

- Read-only first: probes as the shell user, nothing pushed, until the owner agrees; a pushed probe binary is removed afterwards.
- A flash that wipes userdata destroys the owner's apps, accounts and fingerprints: list that in the OK request and take the backup before.
- Check battery before a reboot or flash; keep the device charged.
- `fastboot boot` may not work (MTK tablet root fs panic): every kernel test writes `boot`; keep the stock image.
- Samsung: the Knox bit trips on custom binaries; OEM unlock toggle must be on; never flash a bootloader of another binary version.
- Do not hold the camera over adb while the owner tests; release the session.
- A live edit on a running system is a hypothesis until baked into the build script and hash-compared; a reflash will lose it.

## 4. Host and tooling

- Explicitly non-TTY binary transport (`exec-in` where supported or tested `shell -T`) with exact byte counts and separate stderr; `dd bs=1048576`, not `4M`, in TWRP; one long read through TWRP's shell is cut at about 700 MiB: verify in 256 MiB windows.
- `adb shell` quoting in zsh: use a shell function, not a string variable holding the command.
- macOS `cp` of multi-GB images was pathologically slow: use `dd bs=4m`.
- BSD `sed -i` needs `''`; prefer small Python edits for scripts you commit.
- Tool output can be filtered by a hook: if a result looks empty, re-run it; for debugfs/e2fsck check `$?` or logs.
- Long commands exceed tool timeouts: `nohup ... > log &` and poll the log; connection waits need an explicit deadline and stop after the target boot or causal failure is captured.
- Sandboxed shells may block writes outside the working tree; the temp directory differs between sandboxed and unsandboxed runs (files built in one may sit in the other).
- Host disk: a 4.8 GB image plus its copy plus the donor EROFS exhausts a 460 GB disk that is already 98 % full; check `df` before each rebuild (an image rebuild alone needs about 5 GB).
- `rm -f $VAR/*` is blocked by safety hooks when `$VAR` may be empty; write `"${VAR:?}"/*`.

## 5. Diagnosis traps

- The log file may hold several boots; read the newest.
- Read the first failing line, not the last: later lines are consequences.
- A black screenshot is often a sleeping screen.
- `adb devices` empty for a minute between boots is normal in a loop.
- A patch that "does nothing" often is not bind-mounted or not labelled; confirm with `mount | grep bind`, `ls -Z`, sha of the file in the running system.
- Faking a version or api window globally hides things you need (api 3499 at map sites removed the local_net maps): patch narrowly at the call site.
- A feature that "works" with the owner's adb session may fail for the owner (camera conflict).
- Estimates: do not promise a boot; report where it stops and with which log line.

## 6. Build traps

- Offsets are build-specific; use string/symbol/pattern location and assert. New GSI build -> rerun `check_patches.py`.
- Keystores and AVB keys generated per build change signatures: a rebuilt overlay or metadata package signed with a new key is rejected over old `/data`: diagnose exact certificate identity before any destructive data recovery; an upgrade is not permission to wipe.
- Path shadowing: the vendor fstab mounts the device's own partitions over image directories (`/product`). Verify at runtime what is mounted where.
- A vendor fragment the Pixel track needs (AIDL health) can break the One UI track: audit vendor edits per track.
- `adb remount`/overlayfs does not exist on these kernels; edit from TWRP or `mount -o remount,rw /` on a root-enabled build.
- Compressed apex: payload is nested in `original_apex`; EROFS payloads need conversion.
- musl static helpers die in bionic's linker ("TLS segment is underaligned"): use NDK builds.
- A GSI ext4 with `shared_blocks` is read-only; remove it and `resize2fs`/pad to the partition size.
- Keep generator and checked-in builder changes aligned, but inspect existing drift first. Blind regeneration can discard unrelated fingerprint/face corrections. Preserve those blocks and review the exact generated diff.
- Run Python that reads untrusted downloads with `-I`, and keep downloaded archives in their own directories.
