package org.m30s.fphal;

import android.hardware.biometrics.common.CommonProps;
import android.hardware.biometrics.common.ICancellationSignal;
import android.hardware.biometrics.common.OperationContext;
import android.hardware.biometrics.fingerprint.*;
import android.hardware.keymaster.HardwareAuthToken;
import android.hardware.keymaster.Timestamp;
import android.os.*;
import android.util.Log;
import java.io.File;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;

/**
 * Registers the AIDL fingerprint HAL android.hardware.biometrics.fingerprint.IFingerprint/default for Android 17's FingerprintService
 * and serves it over the vendor's HIDL android.hardware.biometrics.fingerprint@2.1::IBiometricsFingerprint (Samsung's service, same process as ISehBiometricsFingerprint@3.0).
 * Runs as a plain app_process (rc/05_fphal.rc), uid system, no framework services needed. The HIDL side is hand-marshalled HwParcels (hidl-gen is not available, the native route clashes on the libc++ ABI).
 */
public class Main {
    static final String TAG = "m30s-fphal";
    static final String HIDL = "android.hardware.biometrics.fingerprint@2.1::IBiometricsFingerprint";
    static final String HIDL_CB = "android.hardware.biometrics.fingerprint@2.1::IBiometricsFingerprintClientCallback";
    static final int SENSOR_ID = 0, MAX_ENROLLMENTS = 5;
    static final int T_SETNOTIFY = 1, T_PREENROLL = 2, T_ENROLL = 3, T_POSTENROLL = 4, T_GETAUTHID = 5, T_CANCEL = 6, T_ENUMERATE = 7, T_REMOVE = 8, T_SETACTIVEGROUP = 9, T_AUTHENTICATE = 10;
    static final int FLAG_ONEWAY = 1, AIDL_VERSION = 4;   // matches the vintf fragment

    static IHwBinder hal;
    static Session session;   // the one live session (the HAL has a single active group)
    static Handler lockoutTimer;

    public static void main(String[] args) throws Exception {
        hatSelfTest();
        HandlerThread ht = new HandlerThread("lockout"); ht.start(); lockoutTimer = new Handler(ht.getLooper());
        HwBinder.configureRpcThreadpool(4, true);
        while (true) {
            try { hal = HwBinder.getService(HIDL, "default"); break; } catch (Exception e) { Log.w(TAG, "waiting for " + HIDL + ": " + e); Thread.sleep(1000); }
        }
        hal.linkToDeath(c -> { Log.e(TAG, "HAL died, exiting for init to restart"); System.exit(1); }, 0);
        HidlCallback cb = new HidlCallback();
        HwParcel rep = call(T_SETNOTIFY, req -> req.writeStrongBinder(cb));
        Log.i(TAG, "setNotify -> deviceId " + rep.readInt64()); rep.release();

        Fp fp = new Fp();
        Method mark = Binder.class.getMethod("markVintfStability");   // hidden; the generated stubs call it too (patched by make_fphal_jar.py)
        mark.invoke(fp);
        Class<?> sm = Class.forName("android.os.ServiceManager");
        sm.getMethod("addService", String.class, IBinder.class, boolean.class, int.class).invoke(null, IFingerprint.DESCRIPTOR + "/default", fp, false, 8);
        Log.i(TAG, "registered " + IFingerprint.DESCRIPTOR + "/default");
        HwBinder.joinRpcThreadpool();
    }

    /** HwParcel.readInt8VectorAsArray is private (IllegalAccessError); the public readInt8Vector boxes. */
    static byte[] bytes(ArrayList<Byte> l) { byte[] a = new byte[l.size()]; for (int i = 0; i < a.length; i++) a[i] = l.get(i); return a; }

    interface Writer { void write(HwParcel req); }

    /** One HIDL call; the caller reads the reply and releases it. */
    static synchronized HwParcel call(int code, Writer w) throws RemoteException {
        HwParcel req = new HwParcel(), rep = new HwParcel();
        try {
            req.writeInterfaceToken(HIDL);
            if (w != null) w.write(req);
            hal.transact(code, req, rep, 0);
            rep.verifySuccess();
            req.releaseTemporaryStorage();
            return rep;
        } catch (RuntimeException | RemoteException e) { rep.release(); throw e; }
    }
    static int callStatus(int code, Writer w) throws RemoteException { HwParcel r = call(code, w); try { return r.readInt32(); } finally { r.release(); } }
    static long callLong(int code, Writer w) throws RemoteException { HwParcel r = call(code, w); try { return r.readInt64(); } finally { r.release(); } }

    // hw_auth_token_t: version u8, challenge/userId/authenticatorId host order (little endian), authenticatorType u32 and timestamp u64 big endian, mac[32] = 69 bytes
    static byte[] hat(HardwareAuthToken t) {
        ByteBuffer b = ByteBuffer.allocate(69).order(ByteOrder.LITTLE_ENDIAN);
        if (t == null) return b.array();
        b.put((byte) 0).putLong(t.challenge).putLong(t.userId).putLong(t.authenticatorId);
        b.order(ByteOrder.BIG_ENDIAN).putInt(t.authenticatorType).putLong(t.timestamp == null ? 0 : t.timestamp.milliSeconds);
        if (t.mac != null) b.put(t.mac, 0, Math.min(32, t.mac.length));
        return b.array();
    }
    static HardwareAuthToken hat(byte[] a) {
        HardwareAuthToken t = new HardwareAuthToken();
        t.timestamp = new Timestamp(); t.mac = new byte[32];
        if (a == null || a.length != 69) return t;
        ByteBuffer b = ByteBuffer.wrap(a).order(ByteOrder.LITTLE_ENDIAN); b.get();
        t.challenge = b.getLong(); t.userId = b.getLong(); t.authenticatorId = b.getLong();
        b.order(ByteOrder.BIG_ENDIAN); t.authenticatorType = b.getInt(); t.timestamp.milliSeconds = b.getLong(); b.get(t.mac);
        return t;
    }
    static void hatSelfTest() {
        HardwareAuthToken t = new HardwareAuthToken(); t.challenge = 1; t.userId = 2; t.authenticatorId = 3; t.authenticatorType = 2; t.timestamp = new Timestamp(); t.timestamp.milliSeconds = 4; t.mac = new byte[32]; t.mac[31] = 9;
        HardwareAuthToken u = hat(hat(t));
        if (u.challenge != 1 || u.userId != 2 || u.authenticatorId != 3 || u.authenticatorType != 2 || u.timestamp.milliSeconds != 4 || u.mac[31] != 9) throw new AssertionError();
    }

    // ---- AIDL IFingerprint ----
    static class Fp extends IFingerprint.Stub {
        public int getInterfaceVersion() { return AIDL_VERSION; }
        public String getInterfaceHash() { return "notfrozen"; }
        public SensorProps[] getSensorProps() {
            CommonProps c = new CommonProps();
            c.sensorId = SENSOR_ID; c.sensorStrength = android.hardware.biometrics.common.SensorStrength.STRONG; c.maxEnrollmentsPerUser = MAX_ENROLLMENTS; c.componentInfo = new android.hardware.biometrics.common.ComponentInfo[0];
            SensorProps p = new SensorProps();
            p.commonProps = c; p.sensorType = FingerprintSensorType.REAR; p.sensorLocations = new SensorLocation[0];
            return new SensorProps[] { p };
        }
        public ISession createSession(int sensorId, int userId, ISessionCallback cb) throws RemoteException {
            File dir = new File("/data/system/users/" + userId + "/fpdata"); dir.mkdirs();
            int st = callStatus(T_SETACTIVEGROUP, r -> { r.writeInt32(userId); r.writeString(dir.getAbsolutePath()); });
            Log.i(TAG, "createSession user " + userId + " setActiveGroup -> " + st);
            return session = new Session(userId, cb);
        }
    }

    // ---- AIDL ISession ----
    static class Session extends ISession.Stub {
        final int user; final ISessionCallback cb;
        final ArrayList<Integer> found = new ArrayList<>();   // fingerIds collected from onEnumerate / onRemoved
        Session(int user, ISessionCallback cb) { this.user = user; this.cb = cb; }
        public int getInterfaceVersion() { return AIDL_VERSION; }
        public String getInterfaceHash() { return "notfrozen"; }

        public void generateChallenge() throws RemoteException { cb.onChallengeGenerated(callLong(T_PREENROLL, null)); }
        public void revokeChallenge(long challenge) throws RemoteException { callStatus(T_POSTENROLL, null); cb.onChallengeRevoked(challenge); }
        ICancellationSignal canceller() { return new ICancellationSignal.Stub() { public int getInterfaceVersion() { return AIDL_VERSION; } public String getInterfaceHash() { return "notfrozen"; } public void cancel() throws RemoteException { callStatus(T_CANCEL, null); } }; }
        public ICancellationSignal enroll(HardwareAuthToken h) throws RemoteException {
            byte[] a = hat(h);
            int st = callStatus(T_ENROLL, r -> { HwBlob b = new HwBlob(69); b.putInt8Array(0, a); r.writeBuffer(b); r.writeInt32(user); r.writeInt32(60); });
            if (st != 0) { Log.w(TAG, "enroll -> " + st); cb.onError(android.hardware.biometrics.fingerprint.Error.UNABLE_TO_PROCESS, 0); }
            return canceller();
        }
        public ICancellationSignal authenticate(long operationId) throws RemoteException {
            int st = callStatus(T_AUTHENTICATE, r -> { r.writeInt64(operationId); r.writeInt32(user); });
            Log.i(TAG, "authenticate(op " + operationId + ", user " + user + ") -> " + st);
            if (st != 0) { Log.w(TAG, "authenticate -> " + st); cb.onError(android.hardware.biometrics.fingerprint.Error.UNABLE_TO_PROCESS, 0); }
            return canceller();
        }
        public ICancellationSignal detectInteraction() { return null; }   // supportsDetectInteraction = false
        public void enumerateEnrollments() throws RemoteException { synchronized (found) { found.clear(); } if (callStatus(T_ENUMERATE, null) != 0) cb.onEnrollmentsEnumerated(new int[0]); }
        public void removeEnrollments(int[] ids) throws RemoteException {
            synchronized (found) { found.clear(); }
            for (int id : ids) callStatus(T_REMOVE, r -> { r.writeInt32(user); r.writeInt32(id); });
        }
        public void getAuthenticatorId() throws RemoteException { cb.onAuthenticatorIdRetrieved(callLong(T_GETAUTHID, null)); }
        public void invalidateAuthenticatorId() throws RemoteException { cb.onAuthenticatorIdInvalidated(callLong(T_GETAUTHID, null)); }   // the HAL changes it by itself on enroll/remove
        public void resetLockout(HardwareAuthToken h) throws RemoteException { lockoutTimer.removeCallbacksAndMessages(null); cb.onLockoutCleared(); }
        public void close() throws RemoteException { if (session == this) session = null; cb.onSessionClosed(); }
        public void onPointerDown(int pointerId, int x, int y, float minor, float major) {}
        public void onPointerUp(int pointerId) {}
        public void onUiReady() {}
        public ICancellationSignal authenticateWithContext(long operationId, OperationContext c) throws RemoteException { return authenticate(operationId); }
        public ICancellationSignal enrollWithContext(HardwareAuthToken h, OperationContext c) throws RemoteException { return enroll(h); }
        public ICancellationSignal detectInteractionWithContext(OperationContext c) { return null; }
        public void onPointerDownWithContext(PointerContext c) {}
        public void onPointerUpWithContext(PointerContext c) {}
        public void onContextChanged(OperationContext c) {}
        public void onPointerCancelWithContext(PointerContext c) {}
        public void setIgnoreDisplayTouches(boolean b) {}
    }

    // ---- HIDL IBiometricsFingerprintClientCallback, served to the vendor HAL ----
    static class HidlCallback extends HwBinder {
        public void onTransact(int code, HwParcel in, HwParcel out, int flags) throws RemoteException {
            Session s = session;
            try {
                switch (code) {
                    case 1: { in.enforceInterface(HIDL_CB); in.readInt64(); int fid = in.readInt32(); in.readInt32(); int remaining = in.readInt32();
                        if (s != null) s.cb.onEnrollmentProgress(fid, remaining); break; }
                    case 2: { in.enforceInterface(HIDL_CB); in.readInt64(); int info = in.readInt32(), vendor = in.readInt32();
                        if (s != null) s.cb.onAcquired((byte) (info + 1), vendor); break; }   // HIDL GOOD..VENDOR (0..6) = AIDL GOOD..VENDOR (1..7)
                    case 3: { in.enforceInterface(HIDL_CB); in.readInt64(); int fid = in.readInt32(); int gid = in.readInt32(); byte[] tok = bytes(in.readInt8Vector());
                        Log.i(TAG, "onAuthenticated fid " + fid + " gid " + gid + " token " + (tok == null ? -1 : tok.length));
                        if (s != null) { if (fid != 0) s.cb.onAuthenticationSucceeded(fid, hat(tok)); else s.cb.onAuthenticationFailed(); } break; }
                    case 4: { in.enforceInterface(HIDL_CB); in.readInt64(); int err = in.readInt32(), vendor = in.readInt32();
                        if (s != null) error(s, err, vendor); break; }
                    case 5: { in.enforceInterface(HIDL_CB); in.readInt64(); int fid = in.readInt32(); in.readInt32(); int remaining = in.readInt32();
                        if (s != null) collect(s, fid, remaining, false); break; }
                    case 6: { in.enforceInterface(HIDL_CB); in.readInt64(); int fid = in.readInt32(); in.readInt32(); int remaining = in.readInt32();
                        if (s != null) collect(s, fid, remaining, true); break; }
                    case 256067662: { in.enforceInterface("android.hidl.base@1.0::IBase"); ArrayList<String> l = new ArrayList<>(); l.add(HIDL_CB); l.add("android.hidl.base@1.0::IBase"); out.writeStatus(HwParcel.STATUS_SUCCESS); out.writeStringVector(l); out.send(); return; }
                    case 256136003: { in.enforceInterface("android.hidl.base@1.0::IBase"); out.writeStatus(HwParcel.STATUS_SUCCESS); out.writeString(HIDL_CB); out.send(); return; }
                    case 256921159: { in.enforceInterface("android.hidl.base@1.0::IBase"); out.writeStatus(HwParcel.STATUS_SUCCESS); out.send(); return; }   // ping
                    default: Log.w(TAG, "callback: unhandled transaction " + code);
                }
            } catch (Throwable e) { Log.e(TAG, "callback " + code + " failed", e); }   // never let a callback take the process down
            if ((flags & FLAG_ONEWAY) == 0) { out.writeStatus(HwParcel.STATUS_SUCCESS); out.send(); }
        }

        void error(Session s, int err, int vendor) throws RemoteException {
            // HIDL FingerprintError: NO_ERROR 0, HW_UNAVAILABLE 1, UNABLE_TO_PROCESS 2, TIMEOUT 3, NO_SPACE 4, CANCELED 5, UNABLE_TO_REMOVE 6, LOCKOUT 7, VENDOR 8 (AIDL: same up to 6, VENDOR 7)
            if (err == 7) { s.cb.onLockoutTimed(30000); lockoutTimer.removeCallbacksAndMessages(null); lockoutTimer.postDelayed(() -> { Session c = session; if (c != null) try { c.cb.onLockoutCleared(); } catch (RemoteException e) {} }, 30000); }
            else s.cb.onError((byte) (err == 8 ? 7 : err), vendor);
        }

        // enumerate and remove both report one fingerId per call and "remaining" counting down to 0 (fingerId 0 = nothing)
        void collect(Session s, int fid, int remaining, boolean enumerate) throws RemoteException {
            int[] ids;
            synchronized (s.found) { if (fid != 0) s.found.add(fid); if (remaining != 0) return; ids = new int[s.found.size()]; for (int i = 0; i < ids.length; i++) ids[i] = s.found.get(i); s.found.clear(); }
            if (enumerate) s.cb.onEnrollmentsEnumerated(ids); else s.cb.onEnrollmentsRemoved(ids);
        }
    }
}
