package shim;

import java.io.File;
import java.nio.file.Files;

/** Host check of HealthCore on fake sysfs trees (the first one is a copy of what the tablet showed on 2026-11-01): supply selection, unit conversion, charger types, level
 *  and status correction, and the HealthInfo parcel layout. Exits non-zero on failure. */
public class CoreTest {
    static void check(boolean ok, String what) {
        if (!ok) { System.err.println("FAIL: " + what); System.exit(1); }
        System.out.println("ok: " + what);
    }

    static File root() throws Exception { return Files.createTempDirectory("ps").toFile(); }

    static void put(File root, String supply, String node, String v) throws Exception {
        File d = new File(root, supply); d.mkdirs();
        Files.write(new File(d, node).toPath(), (v + "\n").getBytes());
    }

    static void put(File root, String supply, String type, String... kv) throws Exception {
        put(root, supply, "type", type);
        for (int i = 0; i < kv.length; i += 2) put(root, supply, kv[i], kv[i + 1]);
    }

    /** The tablet: plugged in on USB, `battery` stuck at capacity 100 and Full while the gauge is at 67 percent and charging at about 1 A. */
    static File tablet() throws Exception {
        File r = root();
        put(r, "battery", "Battery", "capacity", "100", "status", "Full", "health", "Good", "present", "1", "technology", "Li-ion", "voltage_now", "4145000", "current_now", "964600",
            "current_avg", "1008000", "temp", "260", "charge_full", "2851000", "charge_counter", "1910170", "cycle_count", "896", "batt_id", "1,5000ma");
        put(r, "mm8013", "Battery", "batt_cap", "-99", "current_now", "-99", "temp", "-99", "voltage_now", "-99");   // no capacity node: the unfitted gauge
        put(r, "usb", "USB", "online", "1", "current_max", "500000", "voltage_max", "5000000");
        put(r, "ac", "Mains", "online", "0");
        put(r, "charger", "Unknown", "online", "1");
        put(r, "customer", "Unknown", "charge_usb", "1");
        return r;
    }

    public static void main(String[] a) throws Exception {
        // the tablet as measured
        HealthCore.Info i = new HealthCore(tablet().getPath()).read();
        check(i.voltageMv == 4145 && i.tempTenthsC == 260, "voltage and temperature come from `battery`, not from mm8013 (-99)");
        check(i.usb && !i.ac && !i.wireless && !i.dock, "USB online, AC offline, the Unknown `charger` node is not a charger");
        check(i.maxCurrentUa == 500000 && i.maxVoltageUv == 5000000, "max charging current and voltage from usb/current_max and voltage_max");
        check(i.health == HealthCore.GOOD && i.present && i.technology.equals("Li-ion") && i.cycleCount == 896, "health, present, technology, cycle count");
        check(i.currentUa == 964600 && i.currentAvgUa == 1008000, "current passes through unchanged (driver: positive while charging)");
        check(i.fullChargeUah == 2851000 && i.chargeCounterUah == 1910170 && i.designUah == 5000000, "charge counters as read, design capacity from batt_id");
        check(i.rawLevel == 100 && i.level == 67 && i.levelCorrected, "stale capacity 100 is replaced by charge_counter / charge_full = 67");
        check(i.rawStatus == HealthCore.FULL && i.status == HealthCore.CHARGING, "Full that goes with the stale level becomes Charging");

        // correction switched off: raw values
        HealthCore.correctLevel = false;
        i = new HealthCore(tablet().getPath()).read();
        check(i.level == 100 && i.status == HealthCore.FULL && !i.levelCorrected, "correctLevel=false reports capacity and status as the kernel does");
        HealthCore.correctLevel = true;

        // unplugged, everything agrees: no correction, negative current stays negative, no charger flags
        File r = root();
        put(r, "battery", "Battery", "capacity", "62", "status", "Discharging", "health", "Good", "present", "1", "technology", "Li-ion", "voltage_now", "3900000",
            "current_now", "-450000", "current_avg", "-430000", "temp", "301", "charge_full", "2851000", "charge_counter", "1767620", "cycle_count", "10");
        put(r, "usb", "USB", "online", "0", "current_max", "500000", "voltage_max", "5000000");
        put(r, "ac", "Mains", "online", "0");
        i = new HealthCore(r.getPath()).read();
        check(i.level == 62 && !i.levelCorrected && i.status == HealthCore.DISCHARGING, "agreeing capacity and counter: reported as is");
        check(!i.anyCharger() && i.maxCurrentUa == 0 && i.maxVoltageUv == 0, "unplugged: no charger, max charging values 0");
        check(i.currentUa == -450000 && i.tempTenthsC == 301 && i.voltageMv == 3900, "discharge current sign kept");
        check(i.designUah == 0, "no batt_id: design capacity 0");

        // really full: capacity 100 and the counter equals charge_full
        r = root();
        put(r, "battery", "Battery", "capacity", "100", "status", "Full", "health", "Good", "present", "1", "voltage_now", "4350000", "charge_full", "2851000", "charge_counter", "2851000");
        put(r, "ac", "Mains", "online", "1");
        i = new HealthCore(r.getPath()).read();
        check(i.level == 100 && i.status == HealthCore.FULL && !i.levelCorrected && i.ac, "genuinely full stays 100 and Full, AC online");
        check(i.maxCurrentUa == 500000, "charger online without current_max falls back to 500000");

        // within the tolerance: capacity wins (ratio 66 vs capacity 70)
        r = root();
        put(r, "battery", "Battery", "capacity", "70", "status", "Charging", "charge_full", "2851000", "charge_counter", "1881660");
        i = new HealthCore(r.getPath()).read();
        check(i.level == 70 && !i.levelCorrected, "difference of 4 points does not trigger the correction");

        // no counter files: nothing to compare with
        r = root();
        put(r, "battery", "Battery", "capacity", "100", "status", "Full");
        i = new HealthCore(r.getPath()).read();
        check(i.level == 100 && i.status == HealthCore.FULL && !i.levelCorrected, "without charge_counter and charge_full capacity is used as it is");

        // counter above full is clamped, no wild level
        r = root();
        put(r, "battery", "Battery", "capacity", "100", "status", "Charging", "charge_full", "1000", "charge_counter", "1300");
        i = new HealthCore(r.getPath()).read();
        check(i.level == 100, "ratio above 100 is clamped to 100");

        // no battery at all, empty and missing directories
        r = root();
        put(r, "usb", "USB", "online", "1");
        i = new HealthCore(r.getPath()).read();
        check(!i.present && i.level == 0 && i.usb, "no battery supply: present=false");
        i = new HealthCore("/nonexistent/power_supply").read();
        check(!i.present && i.status == HealthCore.STATUS_UNKNOWN, "missing sysfs directory does not throw");

        // unusable values
        r = root();
        put(r, "battery", "Battery", "capacity", "garbage", "voltage_now", "", "temp", "99999999999999", "status", "Whatever", "health", "???");
        i = new HealthCore(r.getPath()).read();
        check(i.level == 0 && i.voltageMv == 0 && i.tempTenthsC == Integer.MAX_VALUE && i.status == HealthCore.STATUS_UNKNOWN && i.health == HealthCore.HEALTH_UNKNOWN, "garbage and overflow are handled");

        // name tables
        check(HealthCore.chargerKind("Mains") == 1 && HealthCore.chargerKind("USB_PD") == 1 && HealthCore.chargerKind("USB") == 2 && HealthCore.chargerKind("USB_PD_DRP") == 2
            && HealthCore.chargerKind("Wireless") == 3 && HealthCore.chargerKind("Dock") == 4 && HealthCore.chargerKind("Unknown") == 0, "charger type table");
        check(HealthCore.status("Charging") == 2 && HealthCore.status("Discharging") == 3 && HealthCore.status("Not charging") == 4 && HealthCore.status("Full") == 5 && HealthCore.status("Unknown") == 1, "status table");
        check(HealthCore.health("Good") == 2 && HealthCore.health("Overheat") == 3 && HealthCore.health("Dead") == 4 && HealthCore.health("Over voltage") == 5
            && HealthCore.health("Unspecified failure") == 6 && HealthCore.health("Cold") == 7, "health table");

        // sameState ignores voltage and current noise but sees a level or plug change
        HealthCore.Info x = new HealthCore(tablet().getPath()).read(), y = new HealthCore(tablet().getPath()).read();
        y.voltageMv += 5; y.currentUa += 1000; y.chargeCounterUah += 300;
        check(x.sameState(y), "voltage, current and counter noise is not a state change");
        y.level++;
        check(!x.sameState(y) && !x.sameState(null), "a level change is a state change");

        // HealthInfo parcel layout: must match HealthInfo.readFromParcel of this build's services.jar (27 fields, see docs/ANALYSIS.md "Battery")
        Object[] f = x.parcelFields();
        check(HealthCore.layout(f).equals("ZZZZIIIIZIIIIIIISIAAIJIIIOA"), "parcel field types and order match readFromParcel: " + HealthCore.layout(f));
        check(f.length == 27 && f[0].equals(false) && f[1].equals(true) && f[4].equals(500000) && f[6].equals(HealthCore.CHARGING) && f[9].equals(67) && f[10].equals(4145)
            && f[11].equals(260) && f[12].equals(964600) && f[16].equals("Li-ion") && f[21].equals(-1L), "parcel values are in the expected slots");
        System.out.println("all passed");
    }
}
