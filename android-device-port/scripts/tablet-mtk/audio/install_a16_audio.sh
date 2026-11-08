#!/bin/sh
# Audio on Android 17 with the stock Android 10 vendor (audio HAL 5.0): run Android 16's audioserver and its whole library closure privately.
# Why: Android 17 dropped libaudiohal@5.0, and a 5.0 client built for A16 does not match A17's C++ vtables; HIDL audio@6.0 has a different wire format.
# Steps (adb root, / and /vendor remounted rw; ANDROID16_IMG = your A16 system image):
#  1. python3 a16_closure.py            -> /tmp/a16/stage-like dir of the ~164 libs audioserver needs (A16 copies), plus ./audioserver
#     push them to /system/lib64/a16audio (chcon u:object_r:system_lib_file:s0), replace /system/bin/audioserver with the A16 binary (stop audioserver first),
#     keep the A17 one as audioserver.a17orig.
#  2. /system/etc/init/audioserver.rc: add `setenv LD_LIBRARY_PATH /system/lib64/a16audio` right under the `service audioserver` line.
#  3. The A17 clients must send A16's AIDL numbers (IAudioPolicyService, IAudioTrack and IMmapStream differ between the releases):
#       python3 fix_aidl_codes.py audiopolicy-aidl-cpp.so(A17) audiopolicy-aidl-cpp.so(A16) OUT BpAudioPolicyService
#       python3 fix_aidl_codes.py audioflinger-aidl-cpp.so(A17) audioflinger-aidl-cpp.so(A16) OUT BpAudioTrack,BpMmapStream
#     and install the two outputs over /system/lib64 (originals kept as *.a17orig outside the lib dir).
#  3b. Apps' AudioTracks also need the audio permission controller to be populated by system_server (A17's AudioService does it through the Java IAudioPolicyService proxy, which
#     sends A17's number 115 for getPermissionController; A16 uses 113, and A16's 115 is something else). Patch the private A16 libs:
#       python3 patch_server_codes.py a16audio/audiopolicy-aidl-cpp.so OUT      (jump table: code 115 -> the getPermissionController handler)
#       python3 patch_audiopermission.py a16audio/libaudiopermission.so OUT      (populatePermissionState accepts A17's larger enum instead of throwing)
#     Install BOTH or neither: with only the first, populate throws inside system_server and the tablet boot-loops on the boot animation (needs TWRP to undo).
#  4. reboot. Test: ToneTest.java (javac + d8, `CLASSPATH=tone.jar app_process /system/bin Tone`) plays 3 s of 440 Hz.
echo "see the comments; the steps are manual on purpose"
