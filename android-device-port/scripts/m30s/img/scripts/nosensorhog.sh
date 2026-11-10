#!/system/bin/sh
# Keep shell variables out of init.rc's property expansion.
# Same three Personal Safety components as the existing startup helper.
sleep 30
for c in PSAService PersonalSafetyService SndDetectionService; do
    pm disable "com.google.android.gms/com.google.android.gms.personalsafety.service.$c"
done
