package shim;

import android.os.Binder;
import android.os.IBinder;
import android.os.Parcel;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/** android.hardware.health.IHealth/default (declared as AIDL version 3) for Android 17. Without it BatteryService (HealthServiceWrapper) falls back to the vendor's HIDL
 *  health@2.0 service, which reads voltage and temperature from the fake `mm8013` supply and reports 0 V and -9.9 C (see HealthCore). The vendor service keeps running for its
 *  other clients; the framework just prefers this AIDL instance when it is declared and registered.
 *
 *  Same method as the vibrator shim: the AIDL wire format is parsed by hand. Transaction codes are 1 + the method index of IHealth.aidl, checked against the const codes in
 *  IHealth$Stub$Proxy of this build's services.jar: 1 registerCallback, 2 unregisterCallback, 3 update, 4 getChargeCounterUah, 5 getCurrentNowMicroamps,
 *  6 getCurrentAverageMicroamps, 7 getCapacity, 8 getEnergyCounterNwh, 9 getChargeStatus, 10 getStorageInfo, 11 getDiskStats, 12 getHealthInfo, 13 setChargingPolicy,
 *  14 getChargingPolicy, 15 getBatteryHealthData, 16 getHingeInfo. Everything the sysfs cannot answer gets EX_UNSUPPORTED_OPERATION, which HealthServiceWrapperAidl catches. */
public class HealthShim extends Binder {
    static final String DESC = "android.hardware.health.IHealth";
    static final String CB_DESC = "android.hardware.health.IHealthInfoCallback";
    static final int VERSION = 3;
    static final long POLL_SECONDS = 10, REFRESH_MS = 60000;   // poll the sysfs this often; push to the callbacks on a change, and at least once a minute (voltage, current, counter)

    final HealthCore core = new HealthCore(HealthCore.ROOT);
    final Map<IBinder, IBinder.DeathRecipient> callbacks = new ConcurrentHashMap<IBinder, IBinder.DeathRecipient>();
    private HealthCore.Info last;
    private long lastPushMs;

    @Override
    protected boolean onTransact(int code, Parcel data, Parcel reply, int flags) {
        switch (code) {
            case 1: { // void registerCallback(IHealthInfoCallback callback)
                data.enforceInterface(DESC);
                register(data.readStrongBinder());
                reply.writeNoException();
                return true;
            }
            case 2: { // void unregisterCallback(IHealthInfoCallback callback)
                data.enforceInterface(DESC);
                unregister(data.readStrongBinder());
                reply.writeNoException();
                return true;
            }
            case 3: // void update(): re-read and tell every callback (the framework calls it right after registerCallback)
                data.enforceInterface(DESC);
                push(core.read());
                reply.writeNoException();
                return true;
            case 4: return intReply(data, reply, core.read().chargeCounterUah);
            case 5: return intReply(data, reply, core.read().currentUa);
            case 6: return intReply(data, reply, core.read().currentAvgUa);
            case 7: return intReply(data, reply, core.read().level);
            case 9: return intReply(data, reply, core.read().status);
            case 12: { // HealthInfo getHealthInfo()
                data.enforceInterface(DESC);
                reply.writeNoException();
                reply.writeInt(1);                    // non-null typed object
                writeHealthInfo(reply, core.read());
                return true;
            }
            case 0x00FFFFFF: // getInterfaceVersion
                reply.writeNoException();
                reply.writeInt(VERSION);
                return true;
            case 0x00FFFFFE: // getInterfaceHash
                reply.writeNoException();
                reply.writeString("notfrozen");
                return true;
        }
        // 8 energy counter, 10 and 11 storage info and disk stats, 13 and 14 charging policy, 15 battery health data, 16 hinge info (the kernel has none of these),
        // and any newer method: not supported
        if (code >= 1 && code < 0x00FFFFFE) return unsupported(reply);
        try { return super.onTransact(code, data, reply, flags); }   // INTERFACE_TRANSACTION (interface descriptor): without it the NDK client sees descriptor '' and refuses the binder
        catch (android.os.RemoteException e) { return false; }
    }

    static boolean intReply(Parcel data, Parcel reply, int v) {
        data.enforceInterface(DESC);
        reply.writeNoException();
        reply.writeInt(v);
        return true;
    }

    static boolean unsupported(Parcel reply) {
        reply.writeException(new UnsupportedOperationException());
        return true;
    }

    /** Parcelable layout: int size (counted from its own start), then the fields in HealthCore.Info.parcelFields() order. The reader skips what it does not know by the size. */
    static void writeHealthInfo(Parcel p, HealthCore.Info info) {
        int start = p.dataPosition();
        p.writeInt(0);
        for (Object o : info.parcelFields()) {
            if (o instanceof Boolean) p.writeInt(((Boolean) o) ? 1 : 0);
            else if (o instanceof Integer) p.writeInt((Integer) o);
            else if (o instanceof Long) p.writeLong((Long) o);
            else if (o instanceof String) p.writeString((String) o);
            else p.writeInt(0);                       // empty array or null object
        }
        int end = p.dataPosition();
        p.setDataPosition(start);
        p.writeInt(end - start);
        p.setDataPosition(end);
    }

    void register(final IBinder cb) {
        if (cb == null || callbacks.containsKey(cb)) return;
        IBinder.DeathRecipient dr = new IBinder.DeathRecipient() {
            @Override public void binderDied() { callbacks.remove(cb); }
        };
        try {
            cb.linkToDeath(dr, 0);
            callbacks.put(cb, dr);
        } catch (Exception e) {
            System.err.println("health shim: callback already dead: " + e);
        }
    }

    void unregister(IBinder cb) {
        IBinder.DeathRecipient dr = cb == null ? null : callbacks.remove(cb);
        if (dr != null) cb.unlinkToDeath(dr, 0);
    }

    /** IHealthInfoCallback.healthInfoChanged(HealthInfo) (oneway, transaction 1) on every registered binder. */
    synchronized void push(HealthCore.Info info) {
        last = info;
        lastPushMs = System.currentTimeMillis();
        for (IBinder cb : callbacks.keySet()) {
            Parcel d = Parcel.obtain();
            try {
                d.writeInterfaceToken(CB_DESC);
                d.writeInt(1);
                writeHealthInfo(d, info);
                cb.transact(1, d, null, IBinder.FLAG_ONEWAY);
            } catch (Exception e) {
                System.err.println("health shim: callback: " + e);
            } finally {
                d.recycle();
            }
        }
    }

    synchronized void tick() {
        try {
            HealthCore.Info i = core.read();
            if (!i.sameState(last) || System.currentTimeMillis() - lastPushMs >= REFRESH_MS) push(i);
        } catch (Throwable t) {                       // an exception would cancel the periodic task for good
            System.err.println("health shim: tick: " + t);
        }
    }

    public static void main(String[] a) throws Exception {
        final HealthShim s = new HealthShim();
        s.attachInterface(null, DESC);
        Class<?> sm = Class.forName("android.os.ServiceManager");
        sm.getMethod("addService", String.class, IBinder.class).invoke(null, DESC + "/default", s);
        ScheduledExecutorService ex = Executors.newSingleThreadScheduledExecutor(new java.util.concurrent.ThreadFactory() {
            @Override public Thread newThread(Runnable r) { Thread t = new Thread(r, "healthshim"); t.setDaemon(true); return t; }
        });
        ex.scheduleWithFixedDelay(new Runnable() { @Override public void run() { s.tick(); } }, POLL_SECONDS, POLL_SECONDS, TimeUnit.SECONDS);
        Thread.sleep(Long.MAX_VALUE);
    }
}
