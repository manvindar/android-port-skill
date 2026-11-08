#!/system/bin/sh
export CLASSPATH=/system/etc/vibratorshim.jar
exec /system/bin/app_process /system/bin shim.VibratorShim
