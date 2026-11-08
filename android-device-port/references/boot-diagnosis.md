# Boot diagnosis: reading a failed first boot

The loop that fixed ten blockers in a row on One UI 9: read the first failing line, find the cause, patch live, bake the patch, reboot, repeat. Contents: 1 where logs are, 2 reading order, 3 loop patterns and what they mean, 4 live patching during the boot window, 5 capturing logs across reboots, 6 tools.

## 1. Where logs are when there is no adb

Install `bootdiag` in the image (`tablet-mtk/android16/debug/bootdiag.sh` + `zz_bootdiag.rc`, built into the ported images): it writes `logcat.txt`, `kmsg.txt`, `props.txt`, `ps.txt`, `dmesg.tail.txt` to `/data/local/tmp/bootdiag/` and `marker_*` files to `/cache/bootdiag/` (`marker_postfsdata` = init reached post-fs-data, `marker_boot_completed` = framework up). Enter TWRP and `adb pull` them.

- M30s: `/data` is readable in TWRP, so use `/data/local/tmp/bootdiag`. On the MTK tablet `/data/local/tmp` is FBE-encrypted and unreadable: use `/cache/bootdiag`.
- `/sys/fs/pstore/console-ramoops-0` is the kernel console of the failed boot (`loglevel=4` in the M30s cmdline: only level 3 and below reach it). `dmesg-ramoops-0` appears after a panic.
- `/data/tombstones/tombstone_NN` (text) and `.pb`: native crashes with backtraces and, for aborts, usually the abort message. `grep -a Cmdline` to find which process.
- `/data/anr`, `/data/system/dropbox` for Java crashes.
- The log buffer is a ring: the file may hold many boots back to back. Find the newest by timestamp, not by position.

## 2. Reading order

1. Does the device show on USB at all? No adb at all for 5 minutes: init stops or loops before USB. Enter TWRP.
2. `marker_postfsdata` present? If not, kernel log ends in init: first stage or SELinux policy compile.
3. `props.txt`: `persist.sys.boot.reason` names the last reboot cause (`reboot,bpfloader-failed`, `reboot,netd1shot-fail`, `reboot,rescueparty_by_bootchecker`). Samsung init prints the reason and `init: Service X has 'reboot_on_failure' option and failed`.
4. kmsg/logcat: `grep -nE "shutdown_command|Reboot start|reboot_on_failure|Fatal signal|FATAL EXCEPTION IN SYSTEM|WATCHDOG KILLING|Internal error|Unable to handle kernel"`.
5. Read 10 lines before the first hit, not the last hit. Later lines are consequences.

## 3. Loop patterns and what they mean

| Pattern | Meaning | Next step |
|---|---|---|
| Reboot about 11 s after power on, no adb | an init service with `reboot_on_failure` died (bpfloader, netd one-shot) | find the service's own last log line; patch the binary or drop the option |
| `Fatal signal 6` in `system_server` every ~30 s, `FATAL EXCEPTION IN SYSTEM PROCESS` | system_server throws during startup; each restart takes ~30 s, rescue party reboots after 5 | read the stack: the `Caused by` line is the cause (missing package, null service, missing bpf map) |
| `WATCHDOG KILLING SYSTEM PROCESS: Blocked in handler on main thread for 310s` | main thread waits for a service that never registers (e.g. `waitForDeclaredService` for an AIDL HAL declared in vintf but not running) | read the "main annotated stack trace" below the line |
| boot animation forever, adb works | framework up but no home screen | `dumpsys window`, `logcat -b all`, SystemUI crash loop (gesture ML, sensor hog) |
| Kernel oops in a Samsung TZ driver ~15 s after launcher | a TEEgris client app polls a socket the 4.14 driver cannot handle | `grep Comm:` and PID to the app, remove the app |
| Black screen, adb works, SurfaceFlinger running | graphics HAL mismatch or SystemUI crash | `dumpsys SurfaceFlinger`, `logcat -s SurfaceFlinger` |
| Services restart-loop (`init: Service ... exited`) | vendor half missing | list them, disable in an rc overlay (`m30s/img/rc/`) |
| `SELinux: ... avc: denied` thousands of lines | permissive is on; denials are noise until you enforce | ignore for bring-up |

## 4. Live patching during the boot window

When the phone reboots every minute you still get ~30-60 s of adb: `adb wait-for-device; adb shell 'mount -o remount,rw /'` (root is `/dev/root` ext4), push or `cat > file`, `chcon` the right label, `sync`, `adb reboot`. A running process keeps old files mapped, so a file changed in this boot only matters from the next one. Files bind-mounted by rc (the tethering apex patches) are replaced the same way; the rc itself is read at boot only. `mount --bind / /mnt/rv` gives a view of the underlying root without submounts (it showed that `/product` was shadowed by the phone's real product partition).

Write the fix into the build script right away, rebuild (about 5 s of debugfs), extract the file from the new image and compare its sha with the live file.

## 5. Capturing logs across reboots

```
D=./live; mkdir -p $D
( for n in 1 2 3 4 5 6; do adb wait-for-device; adb logcat -b all -v threadtime > $D/lc$n.txt; sleep 2; done ) &
```
One file per boot. Poll `grep -l "FATAL EXCEPTION IN SYSTEM\|WATCHDOG KILLING\|Fatal signal .*system_server" $D/lc*.txt` and `getprop sys.boot_completed`. `adb` may report `no devices` for a minute between boots: loop, do not fail.

## 6. Tools

- `scripts/m30s/debug/`: `fslaunch.c` (first-stage launcher), `dbginit.c`, `dbgprobe.c`, `netbpfload_tracer.c` (logs every bpf syscall netbpfload makes), `bench.sh` (jank bench).
- `scripts/m30s/oneui/xref_str.py ELF 'string'`: where an aarch64 binary loads a string (adrp+add), with disassembly. Needs capstone. This is how every kernel-version gate and the "device check" abort were located without symbols.
- `scripts/tablet-mtk/pulllog.sh`, `readlog.sh`: pull `/cache/bootdiag` from TWRP.
- `dexdump -d` (build-tools) on a split dex shows the bytecode of a framework method; the split of a `classes.dex` container: dex version 041 containers hold several dex files back to back (each starts with `dex\n041\0`), dexdump needs the whole container or one file with its own header.
