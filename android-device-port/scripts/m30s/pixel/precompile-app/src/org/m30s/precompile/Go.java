package org.m30s.precompile;

import android.app.Activity;
import android.os.Bundle;
import android.widget.Toast;

/** Launcher icon: asks init to start the compile job (see tools/img/rc/04_precompile.rc) and closes. */
public class Go extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        Toast.makeText(this, start() ? "Compiling apps in the background (10 to 15 min); the status bar restarts once" : "Could not start the compile job", Toast.LENGTH_LONG).show();
        finish();
    }

    static boolean start() {
        try { return new ProcessBuilder("setprop", "sys.m30s.precompile", "1").start().waitFor() == 0; } catch (Exception e) { return false; }
    }

    static boolean running() {
        try {
            Process p = new ProcessBuilder("getprop", "init.svc.precompile").start();
            String s = new java.io.BufferedReader(new java.io.InputStreamReader(p.getInputStream())).readLine();
            return "running".equals(s);
        } catch (Exception e) { return false; }
    }
}
