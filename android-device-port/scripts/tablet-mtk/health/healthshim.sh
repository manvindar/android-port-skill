#!/system/bin/sh
export CLASSPATH=/system/etc/healthshim.jar
exec /system/bin/app_process /system/bin shim.HealthShim
