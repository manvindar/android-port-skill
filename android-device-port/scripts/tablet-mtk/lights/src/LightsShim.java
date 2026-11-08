package shim;

import android.os.Binder;
import android.os.Parcel;
import java.io.FileOutputStream;

/** android.hardware.light.ILights/default for Android 17: the stock vendor only has the HIDL light@2.0 HAL, which A17's LightsService no
 *  longer talks to ("no ILights HAL service available" -> no backlight control). Speaks the AIDL wire format by hand (no generated
 *  stubs needed) and writes the backlight straight to sysfs. Only the backlight (type 0) is exposed. */
public class LightsShim extends Binder {
    static final String DESC = "android.hardware.light.ILights";
    static final String BL = "/sys/class/leds/lcd-backlight/brightness";

    @Override
    protected boolean onTransact(int code, Parcel data, Parcel reply, int flags) {
        switch (code) {
            case 1: { // setLightState(int id, HwLightState state)
                data.enforceInterface(DESC);
                int id = data.readInt();
                if (data.readInt() != 0) {
                    data.readInt();                   // parcelable size
                    int color = data.readInt();
                    int b = ((77 * ((color >> 16) & 255)) + (150 * ((color >> 8) & 255)) + (29 * (color & 255))) >> 8;
                    if (id == 0) write(b);
                }
                if (reply != null) reply.writeNoException();
                return true;
            }
            case 2: { // getLights()
                data.enforceInterface(DESC);
                reply.writeNoException();
                reply.writeInt(1);
                reply.writeInt(1);                    // non-null parcelable
                int start = reply.dataPosition();
                reply.writeInt(0);                    // size, patched below
                reply.writeInt(0);                    // id
                reply.writeInt(0);                    // ordinal
                reply.writeByte((byte) 0);            // LightType.BACKLIGHT
                int end = reply.dataPosition();
                reply.setDataPosition(start);
                reply.writeInt(end - start);
                reply.setDataPosition(end);
                return true;
            }
            case 0x00FFFFFF: // getInterfaceVersion
                reply.writeNoException();
                reply.writeInt(2);
                return true;
            case 0x00FFFFFE: // getInterfaceHash
                reply.writeNoException();
                reply.writeString("notfrozen");
                return true;
        }
        return false;
    }

    static void write(int b) {
        try (FileOutputStream f = new FileOutputStream(BL)) {
            f.write(Integer.toString(b).getBytes());
        } catch (Exception e) {
            System.err.println("lights shim: " + e);
        }
    }

    public static void main(String[] a) throws Exception {
        LightsShim s = new LightsShim();
        s.attachInterface(null, DESC);
        Class<?> sm = Class.forName("android.os.ServiceManager");
        sm.getMethod("addService", String.class, android.os.IBinder.class).invoke(null, DESC + "/default", s);
        Thread.sleep(Long.MAX_VALUE);
    }
}
