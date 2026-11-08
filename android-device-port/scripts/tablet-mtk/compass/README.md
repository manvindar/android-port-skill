# Virtual compass (no magnetometer on the TB-X606V)

The tablet has no magnetometer (Lenovo's spec lists accelerometer, light, proximity and Hall only). This adds a software one to the vendor sensors HAL so apps that want
TYPE_MAGNETIC_FIELD get a vector. Its data is the **GPS course** (direction of travel), not a measurement: the tablet has to be mounted facing along the car. Without Magisk.

| Part | Where | What |
|---|---|---|
| `src/shim.c` | `/vendor/lib64/hw/sensors.mt6765.so` | The vendor library moved to `sensors.mt6765.orig.so`; this one loads it, forwards everything and adds a MAGNETIC_FIELD sensor (handle = highest + 1). Tilt comes from the real accelerometer, which the shim keeps running while the compass is on and hides from clients that did not ask for it. |
| `src/compass/CompassDaemon.java` | `/system/etc/compassd.jar`, `/system/etc/init/compassd.rc` | Root-less (`system`) service. Turns the GPS on only while the shim's flag file `/data/local/tmp/compass/active` exists, listens to the passive provider all the time, and writes `/data/local/tmp/compass/heading` (`valid heading_magnetic field_uT inclination offset`). The course is used above 2 m/s, converted to magnetic north with the WMM field of the fix (apps convert back with the declination). |
| `install.sh` / `uninstall.sh` | host | Over adb. **Swapping the HAL restarts the Android framework** (apps close, the screen blinks); do it when the tablet is idle. |
| `build.sh` | host | NDK (aarch64, API 29) + javac/d8. `inc/` holds the legacy HAL headers from android10-release (graphics.h is an empty stub). |

Behaviour: the vector is built from the heading, the field strength and inclination of the fix, and the tilt (up = accelerometer). "Forward" is the back of the screen (-Z) when the
tablet stands up, the top edge (+Y) when it lies flat. `/data/local/tmp/compass/offset` (degrees, optional) is added when the tablet is not mounted along the car.
Before the first fix that was moving, or with no heading file, the status is UNRELIABLE and the heading is north. When the car stops the last heading is held.

Checked on the tablet (2026-11-05): the HAL loads the shim and the original, the sensor list has 15 sensors, a client got the vector (48 uT, azimuth 90 for a written heading of 90 with the tablet flat), the
accelerometer still works and is not delivered to clients that did not ask for it, the daemon's GPS request follows the flag file. **Not checked:** a real drive (course from moving GPS fixes), the tablet standing in a mount,
a reboot (the rc file and daemon start at boot), and ROTATION_VECTOR / ORIENTATION: this tablet has no gyroscope, so SensorService does not synthesise them; apps that use accelerometer + magnetometer (most compasses, Godwit) work.

Undo: `sh uninstall.sh` (restores the vendor library and removes the daemon; takes effect after a framework restart or reboot). If the sensors ever die, restore by hand:
`su -c 'mount -o remount,rw /vendor; cat /vendor/lib64/hw/sensors.mt6765.orig.so > /vendor/lib64/hw/x && mv /vendor/lib64/hw/x /vendor/lib64/hw/sensors.mt6765.so'` and reboot.
The original vendor library (md5 3270e0fc9791b7f42dd0b046c9eb329e) is also in `work/compass/sensors.mt6765.so`.

## Experimental: not in release images

The image build leaves this out unless `build/build_image17.py --experimental` is passed (run `sh tools/compass/build.sh` first, it makes `out/compassd.jar`). The flag adds only the system half (`compassd.jar`, `compassd.rc`). The vendor half, the sensors HAL shim, is never part of the image: `sh tools/compass/install.sh` puts it on `/vendor`, and `uninstall.sh` removes it.
