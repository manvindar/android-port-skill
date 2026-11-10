# Pixel compatibility: resources, signers and startup

Use for a Pixel app layer on an older vendor/kernel when gesture models or Safety Center crash. These are narrowly scoped source patterns; host compilation does not establish device acceptance.

## Backgesture model guard

The matching Pixel SystemUI `EdgeBackGestureHandler` checks `config_useBackGestureML` before DeviceConfig. An explicit flag can defeat a startup-only flag change. Inspect the exact APK/resource consumer and listener first. A static runtime resource overlay (RRO) setting this one boolean false selects the existing plain gesture fallback without modifying DEX, the model, native code or global feature policy.

Sign for the exact target/policy. The documented AOSP-platform-signed SystemUI accepts the matching platform test identity; this does not imply any arbitrary Pixel SystemUI does. Verify target certificate, manifest, product placement, static policy and compiled resources. An upstream SIGNATURE/PRODUCT policy reading is not a live idmap result. Keep the owner-requested three-button workaround until actual resource resolution and gesture behavior pass.

## Safety Center AdvancedProtection

`Unexpected safety source: AdvancedProtection` can mean installed GMS submits a source absent from the AOSP SafetyResources raw configuration. It is not by itself a boot blocker. Use the same authenticated Pixel factory build as the app layer, including its Google permission module resource APK; compressed APEX payloads may nest inside `original_apex`.

The reviewed DP11 pattern adds only `AdvancedProtection` and `AdvancedProtectionIssueSource`, authentic package/certificate restrictions and corresponding localized strings to the original AOSP config. The donor has six permitted GMS certificate constraints and 93 locale variants. Compare the installed APK's actual v2/v3 signers with the allowed values; do not download another full APK merely for certificate inspection when the installed signer block is available.

SafetyResources uses its own resources signing identity, distinct from the SystemUI platform signer. Do not sign both overlays with one key, replace the Google APEX/handler, disable Safety Center or weaken restrictions. Public AOSP test identities match these documented test-signed targets; they are not production signing credentials.

The overlay must map `raw/safety_center_config` to the compiled numeric raw resource, and qualified string references must resolve through the exact installed managed parser's Context/Resources path. Verify manifest `resourcesMap`, compiled XML/raw IDs, only the intended resource names, qualifier-to-value binding and all locale strings. Exclude auxiliary donor insertion JSON from packaging. Validate actual idmap and parser behavior on device separately.

## Startup helpers

Init expands property syntax before shell execution. A shell loop using `$c` inside an rc command can abort as an init-named oneshot child. Externalize the small loop into a labelled executable, preserving service UID/domain and the original three component commands.

Automatic compilation must not kill SystemUI or the launcher after finishing. Keep any manual restart behind an explicit opt-in. A deliberate script restart and a later gesture-model SIGILL have different causes.

## Acceptance and reusable source

Separate source pins/tests, SDK compilation/signing, final-image placement, Android overlay admission, resolved resource values, parser behavior and human gesture testing. Passing one level does not imply the next.

Reference implementation: [Pixel compatibility source](https://github.com/manvindar/m30s-pixel-port/tree/938a0a04c19eba3e46adbe74bd64544f523a5521/tools). Its image audit covers the exact target APKs, overlay resources/signers and startup scripts. Use its inputs as a build-specific example, not universal offsets or certificate assumptions. See [verified-upgrades.md](verified-upgrades.md) for publication and device verification.

Bundled source: `scripts/m30s/pixel/make_compat_overlays.py`, `verify_compat_overlays.py`, the two overlay resource directories and SDK packaging tests. Use `scripts/m30s/img/verify_pixel_fixes.py` for final-image audit and `make_readback_manifest.py` for raw windows. The image workflow remains a repo-layout example requiring `tools/` and `tablet/`; map the documented bundle directories before use.
