package android.os;
// compile-only stub: the real class is in framework.jar
public class HwBinder implements IHwBinder {
    public static IHwBinder getService(String iface, String serviceName) throws RemoteException { throw new RuntimeException("stub"); }
    public static void configureRpcThreadpool(long maxThreads, boolean callerWillJoin) { throw new RuntimeException("stub"); }
    public static void joinRpcThreadpool() { throw new RuntimeException("stub"); }
    public void onTransact(int code, HwParcel request, HwParcel reply, int flags) throws RemoteException { throw new RuntimeException("stub"); }
    public void transact(int code, HwParcel request, HwParcel reply, int flags) throws RemoteException { throw new RuntimeException("stub"); }
    public boolean linkToDeath(DeathRecipient recipient, long cookie) { throw new RuntimeException("stub"); }
}
