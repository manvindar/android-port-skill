package org.m30s.display;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** The panel falls back to Adaptive at boot: put the chosen screen mode back and re-apply True black. (The HDR switches are kept by the system.) */
public class Boot extends BroadcastReceiver {
    @Override public void onReceive(Context c, Intent i) { Screen.applySaved(c); }
}
