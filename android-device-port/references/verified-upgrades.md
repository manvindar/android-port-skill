# Verified releases, upgrades and performance kernels

Use for an existing-ROM upgrade, exact automated flash review, release publication or a dated performance build. First installation from encrypted stock has different data requirements.

## Simple TWRP upgrade

For the tested Galaxy M30s SM-M307F already running the Pixel port with compatible TWRP:

1. Back up important files off-device. Download the reviewed system compressed part(s), `boot-a17.img` and checksum manifests.
2. Verify downloads, then extract the system on a computer. For the single-part v0.6 release: `xz -dc system-a17-pixel.img.xz.part-00 > system-a17-pixel.img`. Verify the raw checksum and 5033164800-byte size. The compressed file is not flashable.
3. Copy both raw images to accessible storage and reboot into TWRP. FAT32 cannot hold the system image; use storage supporting files over 4 GB.
4. **Install → Install Image → system-a17-pixel.img → System Image → swipe.**
5. **Install Image → boot-a17.img → Boot → swipe.**
6. **Reboot → System** and allow compilation to progress.

Write System and Boot only for this upgrade. Do not Format Data or wipe Data/Internal Storage. Keep existing Vendor, Recovery, VBMETA, EFS and modem unchanged. A first installation from encrypted stock requires the separately documented format and external backup; TWRP being installed alone does not make it an existing-ROM upgrade.

## Automated transaction contract

One operator owns the phone. Before writing, bind the exact source/release/asset/raw hashes to one reviewed attempt/output directory. Keep failed attempts immutable and stop on the first failure; do not silently retry under another directory.

Fresh gates must prove serial/model/recovery, UID/domain, boot ID, root mount namespace, resolved block paths, geometry, original readable userdata and unmounted write targets. Resolve mount aliases with `readlink -f`; `/dev/block/platform/.../by-name/userdata` can be the same partition as `/dev/block/sda32`. Do not reject or admit a mount by spelling alone.

Some TWRP `id -Z` outputs are exactly `context=u:r:su:s0`, others `u:r:su:s0`, with an optional final newline. Use a narrow observed allowlist; do not strip arbitrary fields or accept foreign domains. A fixture correction changes a frozen operator hash and requires an explicit dependency/plan addendum, not silent packet edits.

Verify protected partition hashes, media inventory/metadata and settings backing files before and after the write. If settings are Android binary XML, decode with the matching `abx2xml` and bind the decoded stay-on value to identical before/after backing bytes. Preserve the setting; an inspection is not permission to change it. Retain identifiers/media details privately.

Use non-TTY binary transport with exact byte counts, separate stderr, deadlines and exit checks. Handle short writes; terminate/reap owned children on failure. Verify full SHA256 values, never short prefixes. A 4800 MiB system needs 19 contiguous 256 MiB windows, last 192 MiB. Generate these from the final raw image and independently check complete decompression/raw SHA before writing. On a system-then-boot upgrade, accept the successful system readback before binding the separate boot transaction to it.

A boot image can have a genuine zero-length ramdisk on Samsung system-as-root. Check the real header/layout, not a generic `ramdisk > 0` rule. An image-prefix hash is not a whole-partition hash: if the partition is larger, back up/hash its full current size, verify the image prefix separately, and preserve/verify the extra tail. Repacking changes kernel size/content ID and moves the Samsung trailer; compare exact preserved header/trailer/footer ranges and the complete new readback.

## Release and source provenance

Pin repository/source tree, owner author, Actions run, tag target, component source commits, uploaded asset sizes/digests, raw hashes and readback windows. A tag alone is not a published GitHub Release. Check `draft`, `prerelease` and `releases/latest` when the owner expects the sidebar to show a Latest release. This metadata does not establish device stability.

Verified unchanged system/vendor assets can be reused with a separately verified new boot. Record distinct system and kernel source/run provenance explicitly; do not claim all bytes came from the final documentation commit or rebuild an unchanged 5 GB image unnecessarily. Documentation-only commits and release-body/Latest changes leave frozen binary checksums intact.

Use a sanitized source checkout for public publication; do not push private history. Honor requested commit identity. CI tests must cover real layout: dependency checkout may be `tablet/` rather than a local sibling, and module resource APKs can be under `/app` or `/priv-app`. Validate real compiled resource-map numeric IDs, qualifier/value pairs and distinct signer failure paths. Exclude Python caches and auxiliary source JSON from packages.

## Dated functional performance kernel

Set the real native kernel release/localversion, build identity and reproducible build date. Verify generated config, `include/config/kernel.release`, compiled Linux banner, packaged kernel and actual runtime `uname`/About. Do not spoof a higher kernel line. Distinguish a metadata-only label rebuild from a functional profile.

The reviewed M30s profile1 uses -O2, LZ4 support availability, BBR plus Fair Queue defaults, reduced debug instrumentation and an existing 150 ms minimum-frequency touch boost. It preserves maximum clocks, thermal/security behavior, storage mode and module CRC enforcement. zram remains zstd; Android may override network defaults. Benefits require comparable speed/battery measurements.

Generated config dependencies matter: disabling PM_DEBUG also disables PM_SLEEP_DEBUG. Compare native final config with an exact allowed delta rather than only checking requested fragments. A touch event driver needs synchronized shared throttling, READ_ONCE tunables and Quality of Service unwind on registration failure.

BFQ is not an active benefit when SCSI_MQ_DEFAULT is off. Do not silently enable storage mode to make a toggle useful. Exclude known black-video HDR changes when the owner requests that. High GPU/MIF locks showed no convincing benefit in the documented measurements; reduced resolution changes display scope.

Before a changed localversion, inspect actual loaded modules and compatibility requirements. An empty `/proc/modules` is useful evidence; driver `client_module_probe` messages alone do not prove loadable modules. Never disable module/version/CRC checks just to make a build boot.

A same-SoC donor is a candidate inventory, not a patch license to import everything. Establish exact baseline feature/config context: an absent EROFS filesystem makes an EROFS optimization irrelevant. Apply-context success is weaker than native compilation and device behavior; broad USB/system-as-root changes need their own justification.

## Host storage and reporting

Before multi-GB work, check physical free space. Delete only authorized, identified obsolete or genuinely regenerable outputs; pin exact candidates, preserve sources, logs, backups, donor inputs and rollback images. APFS shared extents mean logical bytes removed may not equal physical space freed.

Report boot completion, stable core processes, actual kernel, overlay/resource/parser results and protected-storage readback separately. Keep three-button navigation until gestures pass. Do not translate a successful boot into tested calls, camera modes, battery gains or a crash-free daily-driver claim.

Bundled authenticated baseline/profile helpers: `scripts/kernel-build/m30s-profile/`. Run tests from its `scripts/` directory with `python3 -m unittest test_kernel_label test_perf_profile`. These verify permitted config deltas; native compilation and runtime checks remain separate. The touch driver is source to integrate through its Kconfig snippet, not a prebuilt live patch.

For this maintainer's future kernel builds, the published workflow uses `KBUILD_BUILD_USER="Manvindar Singh"` and host `github-actions`. Verify the actual compiled banner on the next build; existing binaries retain their original identity/checksums.
