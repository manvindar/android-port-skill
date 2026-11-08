package org.m30s.display;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.hardware.display.DisplayManager;
import android.os.Bundle;
import android.preference.ListPreference;
import android.preference.Preference;
import android.preference.PreferenceActivity;
import android.preference.PreferenceCategory;
import android.preference.PreferenceManager;
import android.preference.PreferenceScreen;
import android.preference.SwitchPreference;
import android.view.Display;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.List;

/** Launcher icon (the Pixel Settings app does not list injected entries): Samsung style screen mode (mdnie panel tuning), True black, and a switch per HDR format the panel reports. */
public class Screen extends PreferenceActivity {
    static final String MDNIE_MODE = "/sys/class/mdnie/mdnie/mode";    // 0 dynamic, 1 standard, 2 natural, 3 movie, 4 adaptive (picks per app)
    static final String[] MODES = {"Dynamic", "Standard", "Natural", "Movie", "Adaptive"};
    static final String[] HDR_NAMES = {"", "Dolby Vision", "HDR10", "HLG", "HDR10+"};    // Display.HdrCapabilities types 1..4

    static void writeMode(int m) {
        try (FileOutputStream f = new FileOutputStream(MDNIE_MODE)) { f.write(Integer.toString(m).getBytes()); } catch (Exception e) { }
    }

    static DisplayManager dm(Context c) { return c.getSystemService(DisplayManager.class); }

    /** The DisplayManager setter for disabled HDR types is hidden, so go through `cmd display` (this app runs as the system uid). */
    static String cmd(String... args) {
        try {
            List<String> c = new ArrayList<>(); c.add("cmd"); c.add("display");
            for (String x : args) c.add(x);
            Process p = new ProcessBuilder(c).redirectErrorStream(true).start();
            String o = new String(p.getInputStream().readAllBytes());
            return p.waitFor() == 0 ? o : null;
        } catch (Exception e) { return null; }
    }

    static int[] disabledHdr(Context c) {
        String o = cmd("get-user-disabled-hdr-types");    // "User disabled HDR types: [2, 3]"
        if (o == null || o.indexOf('[') < 0) return new int[0];
        String[] t = o.substring(o.indexOf('[') + 1, o.indexOf(']')).split(",");
        List<Integer> l = new ArrayList<>();
        for (String x : t) if (!x.trim().isEmpty()) l.add(Integer.parseInt(x.trim()));
        int[] r = new int[l.size()];
        for (int i = 0; i < r.length; i++) r[i] = l.get(i);
        return r;
    }

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        setTitle("Screen mode and HDR");
        PreferenceScreen ps = getPreferenceManager().createPreferenceScreen(this);
        ListPreference mode = new ListPreference(this);
        mode.setKey("mode"); mode.setTitle("Screen mode"); mode.setDialogTitle("Screen mode"); mode.setSummary("%s");
        String[] vals = new String[MODES.length];
        for (int i = 0; i < vals.length; i++) vals[i] = Integer.toString(i);
        mode.setEntries(MODES); mode.setEntryValues(vals); mode.setDefaultValue("4");
        mode.setOnPreferenceChangeListener((p, v) -> { writeMode(Integer.parseInt((String) v)); return true; });
        ps.addPreference(mode);

        SwitchPreference black = new SwitchPreference(this);
        black.setKey("black"); black.setTitle("True black"); black.setSummary("Pure black dark theme, saves power on the OLED panel"); black.setDefaultValue(true);
        black.setOnPreferenceChangeListener((p, v) -> { boolean on = (Boolean) v; new Thread(() -> Black.apply(this, on)).start(); return true; });
        ps.addPreference(black);

        int[] supported = dm(this).getDisplay(Display.DEFAULT_DISPLAY).getHdrCapabilities().getSupportedHdrTypes();
        PreferenceCategory hdr = new PreferenceCategory(this);
        hdr.setTitle("HDR formats");
        ps.addPreference(hdr);
        if (supported.length == 0) {
            Preference none = new Preference(this); none.setTitle("This display reports no HDR formats"); hdr.addPreference(none);
        }
        for (int t : supported) {
            SwitchPreference s = new SwitchPreference(this);
            s.setPersistent(false); s.setTitle(t < HDR_NAMES.length ? HDR_NAMES[t] : "HDR type " + t);
            s.setSummary("When off, videos in this format play tone mapped to SDR");
            boolean off = false;
            for (int d : disabledHdr(this)) off |= d == t;
            s.setChecked(!off);
            s.setOnPreferenceChangeListener((p, v) -> {
                List<Integer> l = new ArrayList<>();
                for (int d : disabledHdr(this)) if (d != t) l.add(d);
                if (!(Boolean) v) l.add(t);
                String[] args = new String[l.size() + 1];
                args[0] = "set-user-disabled-hdr-types";
                for (int i = 0; i < l.size(); i++) args[i + 1] = Integer.toString(l.get(i));
                return cmd(args) != null;
            });
            hdr.addPreference(s);
        }
        setPreferenceScreen(ps);
    }

    static void applySaved(Context c) {
        SharedPreferences p = PreferenceManager.getDefaultSharedPreferences(c);
        if (p.contains("mode")) writeMode(Integer.parseInt(p.getString("mode", "4")));
        if (p.getBoolean("black", true)) {
            c.startService(new Intent(c, Black.Watch.class));
            new Thread(() -> Black.apply(c, true)).start();
        }
    }
}
