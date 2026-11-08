# hide-debug-props (Magisk module)

LG ThinQ shows "a security issue has been found in the app execution environment" and exits, because its security checker (`libsecuritychecker-lib.so`) logs `DEBUG_CHECK_FAILED` on a build with `ro.debuggable=1` and `ro.secure=0`. Setting `ro.debuggable=0` and `ro.secure=1` at runtime is enough: the check then logs `SecureModule check in Dashboard: SUCCESS` and the app reaches its sign in screen.

The module does it from `service.sh` after `sys.boot_completed`, so adbd (which reads the two properties only when it starts) keeps its root shell. After an `adb` restart you lose `adb root`; `su -c` from Magisk still works.

Build and install: `zip -r hide-debug-props.zip module.prop service.sh` then `adb push` it and `su -c 'magisk --install-module /data/local/tmp/hide-debug-props.zip'`, then reboot.
