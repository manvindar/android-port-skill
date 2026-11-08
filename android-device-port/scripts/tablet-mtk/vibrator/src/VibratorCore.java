package shim;

import java.io.FileOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

/** Timing and sysfs side of the vibrator shim. No Android classes, so tools/vibrator/test.sh runs it on a host JVM.
 *
 *  Kernel side (drivers/misc/mediatek/vibrator/vibrator_drv.c of the X606F kernel): `duration` (write only, ms) is only stored,
 *  `activate`=1 then starts a pulse of the stored duration and the driver stops it with its own hrtimer, `activate`=0 stops it.
 *  The driver raises any duration above vib_limit (9) and below vib_timer (25, from the device tree) to 25 ms and caps one pulse at
 *  15000 ms. There is no amplitude node. */
class VibratorCore {
    static final String DIR = "/sys/class/leds/vibrator";
    static final int MAX_MS = 15000;                       // the driver cuts a pulse here
    // Effect ids of android.hardware.vibrator.Effect. Each effect is a list of on, off, on ... times in ms. Calibration knob: with no
    // amplitude control the pulse length is the only thing that tells these apart. Keep every "on" at 25 ms or more (the driver minimum).
    static final int CLICK = 0, DOUBLE_CLICK = 1, TICK = 2, HEAVY_CLICK = 5;
    static final int[] SUPPORTED = {CLICK, DOUBLE_CLICK, TICK, HEAVY_CLICK};

    static int[] effect(int id) {
        switch (id) {
            case CLICK: return new int[]{30};
            case TICK: return new int[]{25};
            case HEAVY_CLICK: return new int[]{50};
            case DOUBLE_CLICK: return new int[]{30, 60, 30};
            default: return null;
        }
    }

    static int total(int[] segs) { int t = 0; for (int s : segs) t += s; return t; }

    private final ScheduledExecutorService ex = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "vibshim"); t.setDaemon(true); return t;
    });
    private final List<ScheduledFuture<?>> pending = new ArrayList<>();
    private Runnable done;
    private long gen;                                      // bumped by every play/off, so late timer tasks of an older play do nothing

    /** Plays on/off segments, runs `cb` (may be null) when the last one ends. A running play is stopped first and its callback runs. */
    synchronized void play(int[] segs, Runnable cb) {
        stop();
        done = cb;
        final long g = gen;
        int at = 0;
        for (int i = 0; i < segs.length; i++) {
            final int ms = Math.min(segs[i], MAX_MS);
            if (i % 2 == 0) {
                if (at == 0) pulse(ms); else pending.add(ex.schedule(() -> later(g, ms), at, TimeUnit.MILLISECONDS));
            }
            at += ms;
        }
        pending.add(ex.schedule(() -> finish(g), at, TimeUnit.MILLISECONDS));
    }

    /** IVibrator.off(): stops the motor; the callback of a running play still runs, as the HAL contract says. */
    synchronized void off() {
        stop();
        write("activate", 0);
    }

    private void stop() {
        for (ScheduledFuture<?> f : pending) f.cancel(false);
        pending.clear();
        gen++;
        if (done != null) { ex.execute(done); done = null; }
    }

    private synchronized void later(long g, int ms) { if (g == gen) pulse(ms); }

    private synchronized void finish(long g) {
        if (g != gen) return;
        pending.clear();
        if (done != null) { ex.execute(done); done = null; }
    }

    // duration first: the driver latches it when activate is written
    private void pulse(int ms) { write("duration", ms); write("activate", 1); }

    void write(String node, int v) {
        try (FileOutputStream f = new FileOutputStream(DIR + "/" + node)) {
            f.write(Integer.toString(v).getBytes());
        } catch (IOException e) {
            System.err.println("vibrator shim: " + node + ": " + e);
        }
    }
}
