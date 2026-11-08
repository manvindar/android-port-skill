# Test checklist and method

Mark each row WORKS only when something measured it; anything that needs a person (sound, camera picture, SIM, GPS fix, jack, charger) is marked HUMAN. Write the results in `docs/FEATURES.md` (feature audit) and `docs/PERF.md` (numbers) of the port repo, with date and image sha. Contents: 1 order, 2 feature matrix with commands, 3 jank bench, 4 per-feature notes, 5 reporting.

## 1. Order

Boot to UI -> touch and display -> Wi-Fi client (2.4, 5 GHz) -> hotspot -> battery and charging -> sensors -> fingerprint -> cameras (rear, front, one at a time) -> Bluetooth -> audio (speaker, earpiece, jack, mic) -> telephony (SIM) -> GPS -> performance -> thermal and 24 h battery. Do not run audio tests at night; ask before touching the owner's settings or screen (they may be using the device).

Use the owner's own PIN only for adb unlock and never write it to any file, doc, commit, log or message. If a human step is needed (enrol a fingerprint, join Wi-Fi, FRP sign-in), send one short numbered ask.

## 2. Feature matrix and commands

| Area | Command or action | Pass when |
|---|---|---|
| Boot | `getprop sys.boot_completed`, uptime stays up 10 min | 1, no reboot |
| UI | `dumpsys window | grep mCurrentFocus`, screenshot with `adb exec-out screencap -p` (wake first: `input keyevent KEYCODE_WAKEUP`; a black PNG just means the screen is off) | real UI in the PNG |
| Touch | `getevent -lp` (sec_touchscreen), `input tap`, a human swipe | taps land |
| Wi-Fi client | wizard list or `cmd wifi list-scan-results`, join, `ip addr show wlan0`, `dumpsys wifi | grep -E "Frequency|Link speed"` | association on 2.4 and 5 GHz, link speed plausible |
| Hotspot | `cmd wifi start-softap` or UI; band 2.4 and 5; check `SupportedChannelListIn5g`; with the client on a DFS channel the known limit applies | AP up, a client joins, data flows |
| Battery | `dumpsys battery` (level, status, voltage, temp), a charger plugged in | values plausible, status changes |
| Sensors | `dumpsys sensorservice`, a human moves the phone | accel/gyro/mag live; proximity type |
| Fingerprint | `dumpsys fingerprint`, enrol with the human, unlock | enrol + unlock |
| Camera | `dumpsys media.camera`; stock camera app via `am start`, a photo saved (`ls /sdcard/DCIM/Camera` read-only) | real picture content; front and rear separately |
| Bluetooth | `dumpsys bluetooth_manager` is unsafe on the tablet; `settings get global bluetooth_on`, pair a device | pairing + A2DP: HUMAN |
| Audio | `dumpsys media.audio_flinger`, `tinymix`, play a tone | HUMAN |
| Telephony | `getprop gsm.sim.state`, `logcat -b radio | grep -E "getRadioProxy|HalVersion"` | HAL bound; calls/SMS/data need a SIM: HUMAN |
| GPS | `dumpsys location` provider present; fix needs sky | HUMAN |
| Video | local file in the gallery; YouTube HDR must not be black | plays |
| Storage | `ls /data/media/0 | wc -l` equals the pre-flash count | files intact |
| Memory | `free -m`, `cat /proc/swaps`, zram `mm_stat`, `/proc/pressure/*` | swap active |

Write what is absent in hardware too (no ambient light sensor, no NFC on the SM-M307F, FM radio without HAL).

## 3. Jank bench (`scripts/m30s/debug/bench.sh OUT.txt SERIAL`)

Run with the phone idle (load average < 3, screen on, unlocked): cold-start `am start -W` TotalTime of six apps (3 runs each, `drop_caches` before), then 10 up/down swipes in Settings with `dumpsys gfxinfo com.android.settings reset` before and the Janky frames / p50/p90/p95/p99 after, then zram `mm_stat`, `free`, `/proc/pressure/*`, `/proc/vmstat` swap counters.

Launcher and shade variant: `dumpsys gfxinfo <pkg> reset`, drive the surface (6 shade pulls down and up, or launcher scroll via `input swipe`), read `Janky frames`, `50th percentile`, `GPU p50`. Noise between identical runs is about 1 point of janky %, so compare changes over 3 runs. Record frame counts, not only percentages.

Observed (Exynos 9611, 1080x2340, 60 Hz): Pixel launcher janky 14-16 %, p50 21 ms, GPU p50 8-9 ms (UI-thread bound); Pixel SystemUI shade janky 12-19 %, p50 30-42 ms, GPU p50 19-21 ms (pixel bound: 720x1560 halves GPU time). A One UI first run is heavier for the first 10-20 minutes (dexopt load average above 20); measure after it settles and report a baseline against the Pixel image.

## 4. Per-feature notes

- A camera test over adb holds the camera: release it (`am force-stop`) before the human tries the other camera.
- The first boot after a flash is not a performance baseline.
- A screenshot taken with the screen off is black: wake it first.
- Avoid heavy `dumpsys` on the tablet (`bluetooth_manager` crashes `ControllerImpl::Dump`).
- On One UI keep the unlock method simple during tests; Samsung blocks features until the wizard and FRP are done.

## 5. Reporting

Per feature one line: working / not working / fix. Say what was measured, what needs a person, and what was not tested. Include date, image sha256, kernel tag. Keep screenshots out of git if they show personal content (Wi-Fi names, accounts).
