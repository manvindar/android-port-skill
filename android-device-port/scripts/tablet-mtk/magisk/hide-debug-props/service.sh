#!/system/bin/sh
# The image is a debuggable build (ro.debuggable=1, ro.secure=0). LG ThinQ's security module reports DEBUG_CHECK_FAILED and refuses to run.
# Wait for boot to finish so adbd (which reads these once at start) keeps its root shell, then change what apps read.
until [ "$(getprop sys.boot_completed)" = 1 ]; do sleep 2; done
sleep 5
resetprop -n ro.debuggable 0
resetprop -n ro.secure 1
