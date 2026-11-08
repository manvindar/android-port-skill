#!/system/bin/sh
# The Pixel setup wizard treats "Not now" on the screen lock page as a cancel and returns to Date & time, so it can never be finished without a lock.
# (Settings reports RESULT_SKIP, the wizard wrapper hands the manager result 0.) Until setup is complete this watches the top activity: when the wizard
# shows Date & time again right after the lock page, setup is marked complete and the home screen opens. Choosing a PIN or pattern is not affected.
[ "$(settings get secure user_setup_complete)" = 1 ] && exit 0
seen_lock=0
while [ "$(settings get secure user_setup_complete)" != 1 ]; do
  top=$(dumpsys activity activities | grep -m1 topResumedActivity)
  case $top in
    *SetupChooseLock*) seen_lock=1;;
    *DateTimeActivity*) if [ $seen_lock = 1 ]; then
        settings put global device_provisioned 1; settings put secure user_setup_complete 1
        am force-stop com.google.android.setupwizard; am force-stop com.google.android.pixel.setupwizard
        am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1
        exit 0
      fi;;
  esac
  sleep 1
done
