# HAL shims: AIDL services over an old vendor

The newer framework looks for AIDL HALs (fingerprint, health, vibrator, lights, power); the old vendor serves HIDL or nothing. Without the service the feature silently does nothing, or system_server waits or aborts. Contents: 1 the pattern, 2 fingerprint, 3 health, 4 vibrator and lights, 5 how to write one, 6 power, 7 donor-specific traps.

## 1. The pattern (same for all shims)

A small Java program run by `app_process` (`/system/bin/app_process /system/bin shim.Main`, started by an rc service with `seclabel u:r:su:s0` or system uid, `class hal`), built offline with `javac --release 8` + `d8`, shipped as a jar in `/system/etc/`. It registers `<package>.<I>/default` with `ServiceManager.addService` and handles the AIDL wire format **by hand** (a `Binder` subclass with `onTransact`, transaction code = 1 + method index in the interface's frozen version, checked against the `Bp*` proxy in the device's own `*-V*-ndk.so`). It forwards to the vendor HAL (HIDL through `HwParcel`/`HwBinder`) or reads sysfs.

Needed besides the process: a **vintf fragment** declaring the instance (framework fragment in `/system/etc/vintf/manifest/` or a vendor fragment) because `addService` fails with "VINTF declaration error" otherwise, and servicemanager reads manifests only at its start (a reboot is required); and a **permissions/feature xml** where the framework gates on a feature (`android.hardware.fingerprint.xml`).

Why Java and not native: the NDK libc++ clashes with libhidl's std ABI, hidl-gen is not available on the host, the native route was ruled out.

Unsupported methods return `EX_UNSUPPORTED_OPERATION` (the framework catches it). Always implement `getInterfaceVersion` (code `0x00FFFFFF`) and `getInterfaceHash` (`0x00FFFFFE`, "notfrozen") and pass `INTERFACE_TRANSACTION` to `super.onTransact`: otherwise an NDK client sees an empty descriptor and refuses the binder, or an `AbstractMethodError` kills the process.

## 2. Fingerprint (`scripts/m30s/fphal/`)

Android 17 `FingerprintService` speaks only AIDL `android.hardware.biometrics.fingerprint.IFingerprint`; the Samsung vendor serves HIDL `IBiometricsFingerprint@2.1` (and `ISehBiometricsFingerprint@3.0`).
- `make_fphal_jar.py OUT.jar BUILD_TOOLS` (JDK 17): `aidl` (build-tools) turns the AOSP snapshot in `aidl-src` into Java, patches the hidden `markVintfStability`/`PARCELABLE_STABILITY_VINTF`, compiles against compile-only stubs of `android.os.Hw*` (not in the public SDK), `d8`.
- Installed files: jar, `fphal.sh`, `fphal.rc` (as `05_fphal.rc`), `android.hardware.biometrics.fingerprint-m30s.xml` (vintf), `android.hardware.fingerprint.xml` (feature).
- Mapping: HIDL acquired info +1 = AIDL; HIDL error 8 (vendor) = AIDL 7; HIDL lockout error = `onLockoutTimed(30000)` plus a timer for `onLockoutCleared`; `hw_auth_token_t` is 69 bytes; AIDL challenge = HIDL preEnroll, revoke = postEnroll; HAL group id = Android user id, store path `/data/system/users/<id>/fpdata`.
- **HwParcel private-method pitfall**: `HwParcel.readInt8VectorAsArray` is private and hidden-API-blocked; calling it makes the authentication result vanish (unlock does nothing, no crash). Read the token through the public `readInt8Vector`, lift the hidden-API check for the shim, and make callbacks never kill the process (catch Throwable).
- Debug: `logcat -s m30s-fphal`, `dumpsys fingerprint` (shows provider, prints count, HAL deaths). Enrolled templates live in `/data/vendor_de` or `/data/vendor/biometrics` and are lost by a selective wipe: re-enrol.
- On One UI the framework `fingerprint.ISession` is plain AOSP (no `sem*` methods) and services.jar also carries the HIDL `ISehBiometricsFingerprint@3.0` client, so the same shim works unchanged. The face feature xml must be removed (no face HAL).

## 3. Health

AIDL `android.hardware.health.IHealth/default` v3 (`scripts/tablet-mtk/health/`): `HealthCore` reads `/sys/class/power_supply/battery` (and only the supply that has a `capacity` node), `HealthShim` implements registerCallback/unregisterCallback/update/getChargeCounterUah/getCurrentNow/getCapacity/getChargeStatus/getHealthInfo and pushes `healthInfoChanged` to callbacks on change and every minute. `build.sh` writes to `tools/health/out`. Vendor fragment `android.hardware.health-aidl.xml` goes on `/vendor` (the builder `build_vendor_a17.py`).

- Order matters on a live system: with the fragment declared and no service registered, BatteryService waits for the HAL forever (watchdog "Blocked in handler on main thread ... waitForDeclaredService"). Install the service first.
- MTK tablet: the kernel registers a fake second battery supply `mm8013` that answers -99, so the vendor HAL reported 0 V and -9.9 C; the shim uses only the `battery` supply and corrects a stale level. M30s: the gauge is real (`sm5713-fuelgauge`), plausible values.
- **One UI**: Samsung's `HealthRegCallbackAidl` takes HealthInfo only from the vendor-specific health service. With the AIDL fragment declared it takes the AIDL branch and NPEs on `ISehHealth$Stub$Proxy.registerCallback`. Do not ship the shim: hide the vendor AIDL fragment with an empty manifest bind-mounted at `early-init` (`m30s/oneui/rc/00_health_hidl.rc`), the framework then uses `vendor.samsung.hardware.health@2.0::ISehHealth` (HIDL). Also nop the two Samsung AIDL calls in services.jar as a safety.

## 4. Vibrator and lights

- Vibrator (`tablet-mtk/vibrator/`): AIDL v1 over sysfs (`activate`, `duration`; the MTK driver raises durations to 25 ms and has no amplitude) with four predefined effects and a completion callback. Samsung phone: better to forward to the vendor HIDL `vibrator@1.3` service (keeps amplitude/effects) than to write `/sys/class/timed_output/vibrator/enable` (root-only). Not built for the M30s yet: haptics untested.
- Lights (`tablet-mtk/lights/`): AIDL ILights brightness over backlight sysfs. The M30s vendor already declares AIDL `ILights/default`, so none is needed there if the AIDL version is compatible.

## 5. Writing a new shim

1. Get the interface: AIDL from the AOSP snapshot of the same release, `aidl` from build-tools generates Java (or hand-parse as the health/vibrator shims do).
2. Verify transaction codes in the device's `Bp*` code and the interface version.
3. Implement forwarding; test the pure logic on a host JVM (`test.sh` pattern: no Android classes in the core).
4. Add the vintf fragment and rc; install the service files before any fragment that declares it.
5. Test: `service list | grep <name>`, `lshal`, `dumpsys <service>`, `logcat -s <tag>`.

## 6. Power

A17 `HintManagerService` assumes an AIDL IPower: with only the HIDL power HAL its constructor NPEs and system_server restart-loops. Patch the framework (services.jar HintManager patch in `patch-index.md` section 5) instead of writing a shim.

## 7. Telephony

Android 17's `RIL.mIsCellularSupported` needs `android.hardware.telephony.radio.access` (plus `calling`, `data`, `messaging`); an Android 10/11 vendor declares only `.telephony` and `.gsm`, so every radio service shows "not available". Ship `android.hardware.telephony.a17.xml` as a permissions/vintf file. RILJ then binds the vendor HIDL radio 1.4 for radio/data/messaging/modem/network/sim/voice; IMS stays unsupported. The One UI donor binds HIDL radio 1.0-1.4 and `ISehRadio` 2.x natively, no bridge needed on paper; verify in `logcat -b radio` (`getRadioProxy`, `HalVersion`) with a SIM.
