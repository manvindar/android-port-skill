package shim;

import android.os.Binder;
import android.os.IBinder;
import android.os.Parcel;

/** android.hardware.vibrator.IVibrator/default (AIDL version 1) for Android 17: the framework (libandroid_servers, android.hardware.vibrator-V5-ndk)
 *  only looks for the AIDL service and the stock vendor only has the HIDL vibrator@1.0 HAL, so every haptic was "ignored_unsupported".
 *  Same method as the lights shim: the AIDL wire format is parsed by hand. Transaction codes are the method order of IVibrator.aidl from
 *  frozen version 1 (code = 1 + index, checked against BpVibrator in the device's android.hardware.vibrator-V5-ndk.so).
 *  Only on/off with a completion callback and four predefined effects are real; the motor has no amplitude control. */
public class VibratorShim extends Binder {
    static final String DESC = "android.hardware.vibrator.IVibrator";
    static final String CB_DESC = "android.hardware.vibrator.IVibratorCallback";
    static final int CAP_ON_CALLBACK = 1, CAP_PERFORM_CALLBACK = 2;

    final VibratorCore core = new VibratorCore();

    @Override
    protected boolean onTransact(int code, Parcel data, Parcel reply, int flags) {
        switch (code) {
            case 1: // int getCapabilities()
                data.enforceInterface(DESC);
                reply.writeNoException();
                reply.writeInt(CAP_ON_CALLBACK | CAP_PERFORM_CALLBACK);
                return true;
            case 2: // void off()
                data.enforceInterface(DESC);
                core.off();
                reply.writeNoException();
                return true;
            case 3: { // void on(int timeoutMs, IVibratorCallback callback)
                data.enforceInterface(DESC);
                int ms = data.readInt();
                IBinder cb = data.readStrongBinder();
                core.play(new int[]{Math.max(ms, 0)}, completion(cb));
                reply.writeNoException();
                return true;
            }
            case 4: { // int perform(Effect effect, EffectStrength strength, IVibratorCallback callback)
                data.enforceInterface(DESC);
                int[] segs = VibratorCore.effect(data.readInt());
                data.readByte();                      // strength: no amplitude control, so nothing to scale
                IBinder cb = data.readStrongBinder();
                if (segs == null) return unsupported(reply);
                core.play(segs, completion(cb));
                reply.writeNoException();
                reply.writeInt(VibratorCore.total(segs));
                return true;
            }
            case 5: // Effect[] getSupportedEffects()
                data.enforceInterface(DESC);
                reply.writeNoException();
                reply.writeIntArray(VibratorCore.SUPPORTED);
                return true;
            case 0x00FFFFFF: // getInterfaceVersion
                reply.writeNoException();
                reply.writeInt(1);
                return true;
            case 0x00FFFFFE: // getInterfaceHash
                reply.writeNoException();
                reply.writeString("notfrozen");
                return true;
        }
        // 6 setAmplitude, 7 setExternalControl, 8 and 9 composition limits, 10 and 11 primitives, 12 compose, 13 to 15 always-on, and
        // any newer method a V5 client might still call: not supported (the client only calls most of them when a capability bit says so)
        if (code >= 1 && code < 0x00FFFFFE) return unsupported(reply);
        try { return super.onTransact(code, data, reply, flags); }   // INTERFACE_TRANSACTION (interface descriptor): without it the NDK client sees descriptor '' and refuses the binder
        catch (android.os.RemoteException e) { return false; }
    }

    static boolean unsupported(Parcel reply) {
        reply.writeException(new UnsupportedOperationException());
        return true;
    }

    /** IVibratorCallback.onComplete() (oneway, transaction 1) on the client's binder. */
    static Runnable completion(final IBinder cb) {
        if (cb == null) return null;
        return () -> {
            Parcel d = Parcel.obtain();
            try {
                d.writeInterfaceToken(CB_DESC);
                cb.transact(1, d, null, IBinder.FLAG_ONEWAY);
            } catch (Exception e) {
                System.err.println("vibrator shim: callback: " + e);
            } finally {
                d.recycle();
            }
        };
    }

    public static void main(String[] a) throws Exception {
        VibratorShim s = new VibratorShim();
        s.attachInterface(null, DESC);
        Class<?> sm = Class.forName("android.os.ServiceManager");
        sm.getMethod("addService", String.class, IBinder.class).invoke(null, DESC + "/default", s);
        Thread.sleep(Long.MAX_VALUE);
    }
}
