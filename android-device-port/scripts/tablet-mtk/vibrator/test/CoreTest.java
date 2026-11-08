package shim;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

/** Host check of VibratorCore: write order and values, callback timing, off(), superseding, the 15 s cap. Exits non-zero on failure. */
public class CoreTest {
    static final List<String> log = Collections.synchronizedList(new ArrayList<String>());

    static VibratorCore fresh() {
        log.clear();
        return new VibratorCore() {
            @Override void write(String node, int v) { log.add(node + "=" + v); }
        };
    }

    static void check(boolean ok, String what) {
        if (!ok) { System.err.println("FAIL: " + what + "  log=" + log); System.exit(1); }
        System.out.println("ok: " + what);
    }

    static Runnable count(AtomicInteger n, long[] t) { return () -> { n.incrementAndGet(); t[0] = System.nanoTime(); }; }

    public static void main(String[] a) throws Exception {
        // effect table
        check(VibratorCore.effect(VibratorCore.CLICK) != null && VibratorCore.effect(3) == null && VibratorCore.effect(21) == null, "THUD and TEXTURE_TICK unsupported");
        for (int e : VibratorCore.SUPPORTED) for (int i = 0; i < VibratorCore.effect(e).length; i += 2) check(VibratorCore.effect(e)[i] >= 25, "effect " + e + " pulse >= driver minimum");
        check(VibratorCore.total(VibratorCore.effect(VibratorCore.DOUBLE_CLICK)) == 120, "DOUBLE_CLICK reports 120 ms");

        // on(100): duration before activate, callback once, not early
        VibratorCore c = fresh(); AtomicInteger n = new AtomicInteger(); long[] t = new long[1];
        long t0 = System.nanoTime();
        c.play(new int[]{100}, count(n, t));
        check(log.equals(List.of("duration=100", "activate=1")), "on(100) writes duration then activate");
        Thread.sleep(50); check(n.get() == 0, "no callback at 50 ms");
        Thread.sleep(150); check(n.get() == 1 && (t[0] - t0) / 1_000_000 >= 95, "callback once after about 100 ms");
        Thread.sleep(100); check(n.get() == 1 && log.size() == 2, "nothing more after completion");

        // off() during on(): activate=0, callback fires at once and only once
        c = fresh(); n.set(0); c.play(new int[]{1000}, count(n, t));
        Thread.sleep(30); c.off(); Thread.sleep(50);
        check(log.get(log.size() - 1).equals("activate=0") && n.get() == 1, "off() writes activate=0 and fires the callback");
        Thread.sleep(200); check(n.get() == 1, "no second callback from the cancelled timer");

        // double click: two pulses 90 ms apart, callback at 120 ms
        c = fresh(); n.set(0); t0 = System.nanoTime(); c.play(VibratorCore.effect(VibratorCore.DOUBLE_CLICK), count(n, t));
        Thread.sleep(300);
        check(log.equals(List.of("duration=30", "activate=1", "duration=30", "activate=1")) && n.get() == 1 && (t[0] - t0) / 1_000_000 >= 115, "DOUBLE_CLICK plays two pulses, one callback at the end");

        // a new play supersedes: the old callback fires, the new one still fires
        c = fresh(); AtomicInteger n2 = new AtomicInteger(); n.set(0); c.play(new int[]{500}, count(n, t));
        Thread.sleep(20); c.play(new int[]{60}, count(n2, t)); Thread.sleep(30);
        check(n.get() == 1 && n2.get() == 0, "superseded callback fires at once");
        Thread.sleep(150); check(n.get() == 1 && n2.get() == 1, "new callback fires on its own time");

        // no callback binder
        c = fresh(); c.play(new int[]{30}, null); Thread.sleep(80); check(log.size() == 2, "null callback is fine");

        // 15 s cap
        c = fresh(); c.play(new int[]{60000}, null); c.off();
        check(log.get(0).equals("duration=15000"), "pulse capped at 15000 ms");
        System.out.println("all passed");
        System.exit(0);
    }
}
