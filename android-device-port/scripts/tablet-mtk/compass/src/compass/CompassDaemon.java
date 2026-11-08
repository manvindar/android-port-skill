package compass;

import android.hardware.GeomagneticField;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import java.io.File;
import java.io.FileOutputStream;
import java.util.Locale;

/** Writes the GPS course for the virtual compass in the sensors HAL (shim.c) to /data/local/tmp/compass/heading:
 *  "valid heading_magnetic_deg field_uT inclination_deg offset_deg". The passive provider is always listened to (free); the GPS is requested only while the HAL shim has
 *  its flag file /data/local/tmp/compass/active, which exists while some app has the magnetic field or rotation vector sensor on.
 *  The course counts only above MIN_SPEED (below it GPS bearing is noise) and is converted to magnetic north with the WMM field of the fix, because Android sensors are magnetic.
 *  An optional file .../offset holds degrees to add when the tablet is not mounted along the car. */
public class CompassDaemon {
    static final String DIR = "/data/local/tmp/compass";
    static final float MIN_SPEED = 2.0f;   // m/s, about 7 km/h
    static final long CHECK_MS = 2000;

    static boolean valid;
    static float heading, field = 48f, incl = 55f;
    static boolean gpsOn;

    public static void main(String[] args) throws Exception {
        Looper.prepareMainLooper();
        Object at = Class.forName("android.app.ActivityThread").getMethod("systemMain").invoke(null);
        android.content.Context ctx = (android.content.Context) at.getClass().getMethod("getSystemContext").invoke(at);
        final LocationManager lm = (LocationManager) ctx.getSystemService("location");
        new File(DIR).mkdirs();
        final LocationListener ll = new LocationListener() {
            public void onLocationChanged(Location l) { update(l); }
            public void onProviderEnabled(String p) {}
            public void onProviderDisabled(String p) {}
            public void onStatusChanged(String p, int s, Bundle b) {}
        };
        final Handler h = new Handler(Looper.getMainLooper());
        try { lm.requestLocationUpdates(LocationManager.PASSIVE_PROVIDER, 1000, 0, ll, Looper.getMainLooper()); } catch (Exception e) { log("passive: " + e); }
        h.post(new Runnable() {
            public void run() {
                boolean want = new File(DIR, "active").exists();
                try {
                    if (want && !gpsOn) { lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, ll, Looper.getMainLooper()); gpsOn = true; log("gps on"); }
                    if (!want && gpsOn) { lm.removeUpdates(ll); gpsOn = false; log("gps off");
                        try { lm.requestLocationUpdates(LocationManager.PASSIVE_PROVIDER, 1000, 0, ll, Looper.getMainLooper()); } catch (Exception e) { } }
                } catch (Exception e) { log("gps: " + e); }
                h.postDelayed(this, CHECK_MS);
            }
        });
        Looper.loop();
    }

    static void update(Location l) {
        GeomagneticField g = new GeomagneticField((float) l.getLatitude(), (float) l.getLongitude(), (float) l.getAltitude(), System.currentTimeMillis());
        field = g.getFieldStrength() / 1000f;
        incl = g.getInclination();
        if (l.hasBearing() && l.hasSpeed() && l.getSpeed() >= MIN_SPEED) {
            float m = (l.getBearing() - g.getDeclination()) % 360f;
            heading = m < 0 ? m + 360f : m;
            valid = true;
        }
        write();
    }

    static float offset() {
        try { return Float.parseFloat(new String(java.nio.file.Files.readAllBytes(new File(DIR, "offset").toPath())).trim()); } catch (Exception e) { return 0f; }
    }

    static void write() {
        try {
            File tmp = new File(DIR, "heading.tmp");
            FileOutputStream o = new FileOutputStream(tmp);
            o.write(String.format(Locale.US, "%d %.1f %.2f %.1f %.1f\n", valid ? 1 : 0, heading, field, incl, offset()).getBytes());
            o.close();
            tmp.setReadable(true, false);
            tmp.renameTo(new File(DIR, "heading"));
        } catch (Exception e) { log("write: " + e); }
    }

    static void log(String s) { android.util.Log.i("compassd", s); }
}
