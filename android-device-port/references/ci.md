# CI recipe (GitHub Actions)

The laptop is too small for kernels and 4.8 GB images, and a reproducible CI build is the proof that a port is not a pile of live edits. Workflows: `scripts/ci/m30s-build-image.yml` (image), `build-kernel.yml` + `merge-stable.yml` (kernel), tablet workflows `tablet-*.yml`. Contents: 1 repos and visibility, 2 inputs, 3 image workflow, 4 kernel workflow, 5 releases, 6 rules, 7 what CI cannot do.

## 1. Repos and visibility

Use the owner-selected public/private visibility and existing publication authorization. Keep source publication sanitized and separate from authorized binary inputs; never push historical private history or device logs. Separate repos: image/port repo (`tools/`, `docs/`, workflow), kernel repo (patches, configs, workflow, source zip as a release asset), and an optional mirror of One UI work (tools and docs only).

## 2. Inputs

- **Public inputs** are downloaded in the workflow with pinned SHA-256: Google GSI zip, LineageOS GSI donor (`.7z`), crDroid A14 GSI, Pixel factory zip, MindTheGapps, AOSP prebuilt toolchains (clang/gcc tag `android-9.0.0_r30` for Samsung's 4.14 Makefile).
- **Private inputs** live in a release tagged `inputs` of the repo: `vendor-mp2.img` (stock vendor with the MP2 codec type removed), `boot.img` (stock boot), `vbmeta-disabled.img`, optional kernel mirror. Verify each with `sha256sum -c`.
- **Mirror fallback**: upstream hosts fail (crDroid GitHub release returned 504): the workflow falls back to a copy in an `inputs-<name>` release. Same for the kernel: use the exact reviewed kernel tag and Image hash of the kernel repo, read with a token secret when the repo is private (`M30S_KERNEL_TOKEN`), else the mirrored `kernel-<tag>.Image` in `inputs`.
- Keep donor/binary inputs out of the source tree. Their download, storage and CI use follow the owner-authorized input scope and pinned hashes. The documented One UI pipeline is local; do not silently move it to CI.

## 3. Image workflow

`workflow_dispatch` with inputs `tag`, `publish`, `kernel_tag`, `dev_tools`. Steps: checkout; checkout the patch library repo at a pinned commit (`TABLET_REF`) as `tablet/` (the scripts call it as `A17_TOOLS`); free disk (`rm -rf /usr/share/dotnet /opt/ghc ...` and recreate `/usr/local/lib/android` owned by the runner); setup python 3.12, zig (shim for NDK clang), JDK 17, android sdk (`build-tools;35.0.0`, `platforms;android-34`, NDK 26.1); apt `e2fsprogs erofs-utils p7zip-full xz-utils`; pip `capstone pyelftools lz4`; download inputs; build A14 first stage closure; unpack Pixel pieces from the factory zip; build vendor; build system; kernel Image from the release; checks (`stat` size equals the partition, `e2fsck -fn`, `debugfs stat` of must-have files such as the zram rc, WebViewGoogle, launcher); compress (`xz -T0 -6`), **split at 1900 MiB** (`split -b 1900M -d -a 2`: a release asset is limited to 2 GiB), write `SHA256SUMS` (assets plus the hashes of the joined images and the kernel), publish as a **prerelease** with the flash instructions (`FLASH.md` with `@COMMIT@` and `@KERNEL_TAG@` substituted).

Use the latest major action versions (look up the tags before writing a workflow: checkout, setup-python, setup-java, cache, upload-artifact change often); a stale pin broke setup-android and CI once.

## 4. Kernel workflow

`ubuntu-22.04` (old kernel, python2, libtinfo.so.5 symlink for the old clang, `-fcommon` host gcc wrapper for the old dtc). Fetch the toolchains from `android.googlesource.com/platform/prebuilts/...` with retries; get the OEM source tarball from the release `source-<model>`; Samsung's Makefile looks for toolchains below `$(srctree)/toolchain`, so symlink them there; env `PLATFORM_VERSION=11 ANDROID_MAJOR_VERSION=r ARCH=arm64`. Inputs: `fragment`, `perf`, `boost`, `hdr`, `publish`, `tag`. Output: `Image`, config, sha256; `repack_boot.py` makes the flashable boot image.

## 5. Releases

- Experimental builds are **prereleases**. Pin the reviewed kernel tag/hash in the image workflow. Promote visibility only within owner scope; Latest is not kernel selection or acceptance proof.
- Tags are explicit: **never dispatch without `-f tag=...`** (the default tag would overwrite or collide). `gh workflow run build-image.yml -f tag=v0.3g-img -f publish=true`.
- `gh run watch`, then `gh release view TAG --json assets`: check every asset and the `SHA256SUMS` file exists before telling the owner.
- Hash the joined image from the parts locally and compare with the line in `SHA256SUMS` before flashing.

## 6. Rules

Pin SHA-256 for every download; `timeout-minutes: 240` for the image; cache toolchains and ccache for the kernel; no secrets printed; secrets only as `${{ secrets.NAME }}`; do not push private logs, identifiers or unauthorized binary inputs; keep `GH_TOKEN` scopes minimal; mirror fragile upstreams.

## 7. What CI cannot do

Compiled app code (oat/odex) cannot be produced offline: dexopt runs on the phone (first-boot services). The device cannot be tested in CI: flash and feature tests are manual (`testing.md`). The One UI image needs donor firmware and is therefore built on the maintainer's machine; CI only builds the Pixel track and the kernel.

For exact component reuse, raw window manifests, real SDK fixtures, owner authorship and published Release/Latest checks, read [verified-upgrades.md](verified-upgrades.md). Latest is metadata, not proof of runtime acceptance.
