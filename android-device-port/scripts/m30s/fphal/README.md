# Fingerprint HAL shim (AIDL over the vendor's HIDL)

Android 17's FingerprintService only uses the AIDL `android.hardware.biometrics.fingerprint.IFingerprint`; the Samsung vendor (Android 10) serves only HIDL `IBiometricsFingerprint@2.1` (and `ISehBiometricsFingerprint@3.0`).
`shim/` is a Java program run by `app_process` (`fphal.sh`, started by `fphal.rc`, uid system) that registers `IFingerprint/default` and forwards every call to the HIDL HAL with hand-marshalled `HwParcel`s
(native route ruled out: the NDK libc++ clashes with libhidl's std ABI; hidl-gen is not available). Same pattern as the health shim.

- `make_fphal_jar.py OUT.jar BUILD_TOOLS`: aidl (build-tools) turns `aidl-src` (AOSP snapshot) into Java, patches the hidden `markVintfStability`/`PARCELABLE_STABILITY_VINTF`, compiles with compile-only `shim/stubs` (android.os.Hw*, not in the public SDK), d8. Needs a JDK 17.
- `android.hardware.biometrics.fingerprint-m30s.xml` (framework vintf fragment, `/system/etc/vintf/manifest/`) declares the instance: addService fails with "VINTF declaration error" without it, and servicemanager reads manifests once at start, so a reboot is needed.
- `android.hardware.fingerprint.xml` (`/system/etc/permissions/`) is the feature that makes `fingerprint` service exist.
- `tools/img/build_a17.py` installs all of it; `hal21/` is the HIDL interface reference.
- Mapping: HIDL acquired info +1 = AIDL; HIDL error 8 (vendor) = AIDL 7; HIDL lockout error = `onLockoutTimed(30000)` plus a timer for `onLockoutCleared`; hw_auth_token_t is 69 bytes (see `Main.hat`); challenge = preEnroll, revoke = postEnroll; HAL group id = Android user id, store path `/data/system/users/<id>/fpdata`.
- `getInterfaceVersion()` must be implemented (the unversioned stubs leave it abstract: AbstractMethodError kills the process); it reports 4, as in the fragment.
- Debug: `logcat -s m30s-fphal`, `dumpsys fingerprint`.
