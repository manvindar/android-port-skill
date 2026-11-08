#!/system/bin/sh
export CLASSPATH=/system/etc/lightsshim.jar
exec /system/bin/app_process /system/bin shim.LightsShim
