package org.m30s.display;

import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.IBinder;
import android.content.om.FabricatedOverlay;
import android.content.om.OverlayIdentifier;
import android.content.om.OverlayManager;
import android.content.om.OverlayManagerTransaction;
import android.util.Log;
import android.util.TypedValue;

/**
 * True black for the OLED panel: the dark theme's surfaces become pure black, raised surfaces step up in dark greys.
 * Done as runtime (fabricated) overlays because the system UI's own palette overlay beats any static one, and it is
 * re-applied on top whenever the wallpaper colors change, so {@link Watch} puts ours back on top.
 */
class Black {
    static final String[][] COLORS = {   // android:color/system_<name>, ARGB without alpha
        {"surface_dark", "000000"}, {"background_dark", "000000"}, {"surface_dim_dark", "000000"},
        {"surface_container_lowest_dark", "000000"}, {"surface_container_low_dark", "000000"}, {"surface_container_dark", "000000"},
        {"surface_container_high_dark", "101010"}, {"surface_container_highest_dark", "181818"}, {"surface_bright_dark", "1c1c1c"}};

    static boolean listed() {
        try {
            Process p = new ProcessBuilder("cmd", "overlay", "list", "android").start();
            String o = new String(p.getInputStream().readAllBytes());
            p.waitFor();
            return o.contains(":blk");
        } catch (Exception e) { return false; }
    }

    /** Last enabled overlay on `android` is ours? (The system UI re-applies its palette on top of it when the wallpaper colors change.) */
    static boolean onTop() {
        try {
            Process p = new ProcessBuilder("cmd", "overlay", "list", "android").start();
            String last = "";
            for (String l : new String(p.getInputStream().readAllBytes()).split("\n")) if (l.startsWith("[x]")) last = l;
            p.waitFor();
            return last.contains(":blk");
        } catch (Exception e) { return false; }
    }

    /** Off: unregister. On: (re)register and enable, which also puts it above every other overlay. Hidden Builder API, hence the reflection. */
    static synchronized void apply(Context c, boolean on) {
        try {
            Class<?> fb = Class.forName("android.content.om.FabricatedOverlay$Builder");
            Object fbi = fb.getConstructor(String.class, String.class, String.class).newInstance(c.getPackageName(), "blk", "android");
            for (String[] k : COLORS) fb.getMethod("setResourceValue", String.class, int.class, int.class).invoke(fbi, "android:color/system_" + k[0], TypedValue.TYPE_INT_COLOR_ARGB8, 0xff000000 | Integer.parseInt(k[1], 16));
            FabricatedOverlay fo = (FabricatedOverlay) fb.getMethod("build").invoke(fbi);
            Class<?> bc = Class.forName("android.content.om.OverlayManagerTransaction$Builder");
            Object b = bc.getConstructor().newInstance();
            boolean exists = listed();
            if (!on && !exists) return;
            if (exists) bc.getMethod("unregisterFabricatedOverlay", OverlayIdentifier.class).invoke(b, fo.getIdentifier());
            if (on) {
                bc.getMethod("registerFabricatedOverlay", FabricatedOverlay.class).invoke(b, fo);
                bc.getMethod("setEnabled", OverlayIdentifier.class, boolean.class, int.class).invoke(b, fo.getIdentifier(), true, 0);
            }
            ((OverlayManager) c.getSystemService("overlay")).commit((OverlayManagerTransaction) bc.getMethod("build").invoke(b));
        } catch (Exception e) { Log.w("M30sBlack", "apply " + on, e); }
    }

    /** Started at boot when the switch is on; keeps the overlays on top. */
    public static class Watch extends Service {
        @Override public int onStartCommand(Intent i, int f, int id) {
            IntentFilter flt = new IntentFilter("android.intent.action.OVERLAY_CHANGED"); flt.addDataScheme("package");
            registerReceiver(new BroadcastReceiver() {
                @Override public void onReceive(Context c, Intent in) { if (!Black.onTop()) Black.apply(c, true); }
            }, flt, Context.RECEIVER_EXPORTED);
            return START_STICKY;
        }
        @Override public IBinder onBind(Intent i) { return null; }
    }
}
