import android.content.Context;
import android.hardware.*;
import android.os.*;

/** Test only (not shipped): prints magnetic field and the heading computed from it. app_process as root: CLASSPATH=magtest.jar app_process /system/bin MagTest [seconds] */
public class MagTest {
    static float[] g, m;
    public static void main(String[] a) throws Exception {
        Looper.prepareMainLooper();
        Object at = Class.forName("android.app.ActivityThread").getMethod("systemMain").invoke(null);
        Context ctx = (Context) at.getClass().getMethod("getSystemContext").invoke(at);
        SensorManager sm = (SensorManager) ctx.getSystemService("sensor");
        Sensor mag = sm.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD), acc = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
        System.out.println("mag=" + mag + "\nacc=" + acc + "\nrot=" + sm.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR) + " orient=" + sm.getDefaultSensor(Sensor.TYPE_ORIENTATION));
        final long end = SystemClock.elapsedRealtime() + (a.length > 0 ? Integer.parseInt(a[0]) : 8) * 1000L;
        final int[] n = {0};
        SensorEventListener l = new SensorEventListener() {
            public void onAccuracyChanged(Sensor s, int x) {}
            public void onSensorChanged(SensorEvent e) {
                if (e.sensor.getType() == Sensor.TYPE_ACCELEROMETER) g = e.values.clone(); else m = e.values.clone();
                if (e.sensor.getType() == Sensor.TYPE_MAGNETIC_FIELD && g != null && n[0]++ % 10 == 0) {
                    float[] R = new float[9], I = new float[9], o = new float[3], R2 = new float[9];
                    SensorManager.getRotationMatrix(R, I, g, m);
                    // device upright facing along the car: heading of the back of the screen, like a compass app in portrait
                    SensorManager.remapCoordinateSystem(R, SensorManager.AXIS_X, SensorManager.AXIS_Z, R2);
                    SensorManager.getOrientation(R2, o);
                    System.out.printf("mag %.1f %.1f %.1f st=%d  g %.1f %.1f %.1f  azimuth(upright)=%.0f  azimuth(flat)=%.0f%n", m[0], m[1], m[2], e.accuracy, g[0], g[1], g[2],
                        (Math.toDegrees(o[0]) + 360) % 360, (Math.toDegrees(SensorManager.getOrientation(R, new float[3])[0] ) + 360) % 360);
                    float[] o2 = new float[3]; SensorManager.getOrientation(R, o2); }
            }
        };
        sm.registerListener(l, acc, SensorManager.SENSOR_DELAY_GAME);
        sm.registerListener(l, mag, SensorManager.SENSOR_DELAY_GAME);
        new Handler().postDelayed(new Runnable() { public void run() { System.out.println("done, mag events=" + n[0]); System.exit(0); } }, end - SystemClock.elapsedRealtime());
        Looper.loop();
    }
}
