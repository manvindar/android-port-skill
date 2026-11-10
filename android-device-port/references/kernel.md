# Kernel: what a newer Android needs from an old kernel

Both devices kept the vendor's kernel line (4.9.190 and 4.14.113). Contents: 1 principle, 2 gap table, 3 how to build, 4 M30s kernel releases, 5 backported series, 6 what not to do, 7 MTK 4.9 notes.

## 1. Principle

Prefer, in this order: (1) a config option the source already supports (PSI, BPF JIT, userfaultfd, MEMCG), (2) a small upstream/android-common backport, (3) a userspace patch at the call site in the new Android (patched libc, libbinder, netbpfload...). Do not spoof `uname`: community Samsung ports report 5.10 from a 4.14 kernel and then need LPM-trie backports anyway; patching the gates by message string (`patch_netbpfload.py`) kept the real version and the right program variants load (the kernel-version windows in the BPF objects pick the 4.14 programs). Do not rebase onto a different tree without a reason: keep the vendor's source drop (Samsung's `SM-M307F_SWA_RR_Opensource.zip`, Lenovo's drop) as baseline so drivers stay known-good.

## 2. Gap table

| Feature missing | Needed by | Fix | Where |
|---|---|---|---|
| PSI (`/proc/pressure`) | lmkd of Android 12+ | 28 patches PSI + monitor + cgroup poll, `CONFIG_PSI=y`, `PSI_DEFAULT_DISABLED=n`; without it use the in-kernel LMK replacement lmkd | `patches/kernel-4.14/psi/`, `a17.fragment`, `tablet-mtk/lmkd/lmkd_inkernel.c` |
| BPF JIT | netbpfload loads every program | `BPF_JIT=y`, `BPF_JIT_ALWAYS_ON=y` (interpreter works but netbpfload checks) | `a17.fragment`, `m30s/img/patch_netbpfload_jit.py` |
| userfaultfd | ART GC | `USERFAULTFD=y` | `a17.fragment` |
| MEMCG, MEMCG_SWAP, CGROUP_BPF, SCHEDSTATS | lmkd, bpf cgroup programs | config | `a17.fragment` |
| `MADV_WIPEONFORK` (4.14+) | A17 libc | backport + `restart_block`, or patch libc | `patches/kernel-4.9-mtk/0002-*.patch`, `0003-*.patch`; `tablet-mtk/libc/patch_libc.py` |
| `F_SEAL_FUTURE_WRITE` | A16 libhwui | backport or patch libhwui | `patches/kernel-4.9-mtk/0001-*.patch` |
| `clone3`, `close_range`, `openat2`, `faccessat2`, `pidfd_*` | bionic, netd, Chrome zygote | bionic falls back for most; stub clone3 and netd's `CLOEXEC_DEFAULT` in userspace | `tablet-mtk/libc/` |
| BPF atomics (5.12), LRU maps used by netd.o, LPM trie iteration (4.20), ringbuf (5.8), `bpf_ktime_get_boot_ns` etc. | tethering apex bpf objects | on 4.9 rewrite the objects; on 4.14 pick the 4.14 variants (api window), LPM as hash, ringbuf stubs | `bpf/patch_netd_o.py`, `oneui/patch_netbpfload.py`, `oneui/patch_lsc_ringbuf.py`; `bpf_needs.py` lists what an object needs that the tree lacks |
| SELinux permissive | bring-up with a ported policy | build kernel with permissive support; else allow-all CIL block | `make_allowall_cil.py` |
| cgroup2 data options, cpuset option | libprocessgroup_setup | kernel patch or lib patch | `patches/kernel-4.9-mtk/0006-*.patch`, `0007-*.patch` |

## 3. Build

Build in CI, not on the laptop (the source tree is large, toolchains are old). `scripts/ci/build-kernel.yml` (M30s): inputs `fragment` (merge `a17.fragment`), `perf`, `boost`, `hdr`, `publish`, `tag`. Toolchains are the OEM's own (M30s: AOSP `clang-4639204` and gcc 4.9 from tag `android-9.0.0_r30`; TB-X606V: clang r353983c + gcc 4.9). The OEM source zip is a release asset of the (private) kernel repo because it exceeds git's file limit. Output: kernel `Image` + config + sha256, published as a release; pin an exact reviewed kernel tag/hash in the image build. Published Release/Latest metadata does not prove runtime acceptance; never select a different kernel merely because it is Latest.

Boot image: `scripts/kernel-build/repack_boot.py STOCK_boot.img Image OUT_boot.img` (header v1, no ramdisk, AVB footer kept; flash vbmeta disabled). The Samsung boot image has no ramdisk: the bootloader adds `root=/dev/sdaN`.

Variant name shows in Settings through `CONFIG_LOCALVERSION` in the fragment.

## 4. M30s kernel releases (reference)

- `a17` (baseline, Latest): stock config + PSI + BPF JIT + userfaultfd.
- Historical `a17-perf` candidate: `-O2`, LZ4 availability, BBR + fq, BFQ toggle and reduced debug options. LZ4 availability does not switch zram from zstd. BFQ is dormant with SCSI_MQ_DEFAULT off; do not claim a benefit without a separately reviewed storage-mode change.
- `a17-boost`: perf + touch boost driver `boost/input_boost_m30s.c`: min frequency on both clusters for 150 ms after touch; tune at `/sys/module/input_boost_m30s/parameters/`.
- `a17-hdr(-r2)`: panel advertises HDR10 (synthesised DSIM caps). Result: black HDR video. Do not use.
- CPU and GPU clocks were not raised: OPP tables come from ECT/ACPM firmware and the device tree (`dtb` partition), not this source; tops are 2.314 GHz (A73) and 1.742 GHz (A53). Measured effect of Mali power policy, MIF max, GPU clock locks: none on jank.

## 5. The PSI series

`patches/kernel-4.14/psi/` holds the 28 android-common backports in apply order (0001 workingset to 0026 uaf fix, with 0020a/0020b kernfs/cgroup poll). They apply on a 4.14.113 Samsung tree with small context fixes; the filenames carry UPSTREAM / BACKPORT / FROMLIST tags from the Android common kernel.

## 6. What not to do

- Do not flash a self-built kernel without a way back: the MTK tablet cannot `fastboot boot`, every test writes `boot`. Keep the stock image and a TWRP route.
- Do not trust a kernel that boots but whose display never comes up: the 4.9.117 Lenovo drop booted userspace but its PowerVR driver rejected the vendor GPU firmware. The stock 4.9.190 boot image was kept and userspace patched instead.
- Do not merge full upstream stable (4.14.y): rejected for risk; PSI/JIT/userfaultfd were enough.
- Do not use an experimental kernel as `Latest`.

## 7. MTK 4.9 extras

Device-tree bootargs needed `cpuidle.off=1` (a NULL dereference in MediaTek MCDI idle after ~10 s) and `printk.devkmsg=on`. Also patches for `fiq_cache_init`, `ram_console` (bad `_pa` after a failed SRAM mapping: oops at 0.6 s), `disp_caps_info` vendor ABI. CPU overclock: see `lenovo-tb-x606v-mtk.md`.

Read [verified-upgrades.md](verified-upgrades.md) for dated native kernel labels, generated-config dependency closure, bounded performance profiles, module checks and boot prefix/tail verification.
