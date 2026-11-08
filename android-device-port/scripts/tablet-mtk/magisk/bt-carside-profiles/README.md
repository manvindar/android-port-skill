# bt-carside-profiles

Magisk module for the Android 17 tablet. It sets the car-side Bluetooth profile properties at boot so the tablet can be a Bluetooth music sink for a phone.
The phone-side profiles (a2dp.source, avrcp.target, hfp.ag, hid, pan, opp, bas.client, gatt, asha) stay on, as set in /system/build.prop.

Live (no reboot): `su -c 'setprop bluetooth.profile.a2dp.sink.enabled true'` (and the other four), then `svc bluetooth disable; svc bluetooth enable`. The Bluetooth process rereads the properties on every restart.
Undo: delete /data/adb/modules/bt-carside-profiles (or turn it off in the Magisk app) and reboot, or set the five properties to false and toggle Bluetooth.
