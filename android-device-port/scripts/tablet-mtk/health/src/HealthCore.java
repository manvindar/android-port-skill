package shim;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.util.Arrays;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** sysfs side of the health shim. No Android classes, so tools/health/test.sh runs it on a host JVM.
 *
 *  The mapping follows the standard healthd BatteryMonitor (what the vendor android.hardware.health@2.0-service runs) with two differences that matter on this tablet:
 *  - The kernel registers a second, fake BATTERY supply `mm8013` (an external gauge chip that is not fitted: drivers/power/supply/mediatek/battery/mm8013.c answers
 *    every property with an error value, -99 here). BatteryMonitor takes the first BATTERY supply it finds for each file, so the vendor HAL reports voltage 0 and
 *    temperature -9.9 C ("healthd: battery l=100 v=0 t=-9.9 ..." in dmesg). This code only uses the BATTERY supply that has a `capacity` node (`battery`).
 *  - `battery/capacity` and `battery/status` can be stale (100 and Full while the gauge is at 60 to 70 percent and charging at 1 A). See correctLevel(). */
class HealthCore {
    static final String ROOT = "/sys/class/power_supply";

    // android.hardware.health.BatteryStatus and BatteryHealth (int backed enums)
    static final int STATUS_UNKNOWN = 1, CHARGING = 2, DISCHARGING = 3, NOT_CHARGING = 4, FULL = 5;
    static final int HEALTH_UNKNOWN = 1, GOOD = 2, OVERHEAT = 3, DEAD = 4, OVER_VOLTAGE = 5, UNSPECIFIED_FAILURE = 6, COLD = 7;
    static final int CAPACITY_LEVEL_UNSUPPORTED = 0;

    // Calibration knobs. The level correction only fires when the kernel's own charge_counter / charge_full disagrees with capacity by more than this many points.
    static boolean correctLevel = true;
    static int maxDisagreement = 10;
    static final int DEFAULT_MAX_CURRENT_UA = 500000, DEFAULT_MAX_VOLTAGE_UV = 5000000;   // what BatteryService shows for a plain USB port

    /** One reading. Field order of parcelFields() is the HealthInfo parcel order. */
    static class Info {
        boolean ac, usb, wireless, dock, present;
        int maxCurrentUa, maxVoltageUv, status = STATUS_UNKNOWN, health = HEALTH_UNKNOWN;
        int level, voltageMv, tempTenthsC, currentUa, currentAvgUa, cycleCount, fullChargeUah, chargeCounterUah, designUah;
        String technology = "";
        boolean levelCorrected;
        int rawLevel, rawStatus;

        boolean anyCharger() { return ac || usb || wireless || dock; }

        /** True when nothing that the UI or power policy shows has changed (voltage, current and the counter are left out: they move all the time). */
        boolean sameState(Info o) {
            return o != null && ac == o.ac && usb == o.usb && wireless == o.wireless && dock == o.dock && present == o.present && maxCurrentUa == o.maxCurrentUa
                && status == o.status && health == o.health && level == o.level && tempTenthsC == o.tempTenthsC;
        }

        /** android.hardware.health.HealthInfo (AIDL V5 as compiled into this build's services.jar), fields after the parcelable size int, in order. Boolean: readBoolean,
         *  Integer: readInt, Long: readLong, String: readString, EMPTY_ARRAY and NULL_OBJECT: one int 0 (empty typed array, null typed object). */
        Object[] parcelFields() {
            return new Object[]{
                ac, usb, wireless, dock,                                   // chargerAcOnline, chargerUsbOnline, chargerWirelessOnline, chargerDockOnline
                maxCurrentUa, maxVoltageUv,                                // maxChargingCurrentMicroamps, maxChargingVoltageMicrovolts
                status, health, present,                                   // batteryStatus, batteryHealth, batteryPresent
                level, voltageMv, tempTenthsC, currentUa,                  // batteryLevel, batteryVoltageMillivolts, batteryTemperatureTenthsCelsius, batteryCurrentMicroamps
                cycleCount, fullChargeUah, chargeCounterUah,               // batteryCycleCount, batteryFullChargeUah, batteryChargeCounterUah
                technology,                                                // batteryTechnology
                currentAvgUa,                                              // batteryCurrentAverageMicroamps
                EMPTY_ARRAY, EMPTY_ARRAY,                                  // diskStats, storageInfos
                CAPACITY_LEVEL_UNSUPPORTED,                                // batteryCapacityLevel
                -1L,                                                       // batteryChargeTimeToFullNowSeconds (-1 = unknown)
                designUah,                                                 // batteryFullChargeDesignCapacityUah
                0, 0,                                                      // chargingState (NORMAL), chargingPolicy (INVALID: no policy support)
                NULL_OBJECT,                                               // batteryHealthData
                EMPTY_ARRAY,                                               // hingeInfos
            };
        }
    }

    static final Object EMPTY_ARRAY = new Object(), NULL_OBJECT = new Object();

    /** One letter per parcel field: Z boolean, I int, J long, S string, A empty array, O null object. */
    static String layout(Object[] f) {
        StringBuilder b = new StringBuilder();
        for (Object o : f) {
            if (o instanceof Boolean) b.append('Z'); else if (o instanceof Integer) b.append('I'); else if (o instanceof Long) b.append('J');
            else if (o instanceof String) b.append('S'); else if (o == EMPTY_ARRAY) b.append('A'); else if (o == NULL_OBJECT) b.append('O'); else b.append('?');
        }
        return b.toString();
    }

    private final String root;

    HealthCore(String root) { this.root = root; }

    Info read() {
        Info i = new Info();
        File[] dirs = new File(root).listFiles();
        if (dirs == null) return i;
        Arrays.sort(dirs);
        File batt = null;
        for (File d : dirs) {
            String type = str(d, "type");
            if (type == null) continue;
            if (type.equals("Battery")) {
                if (new File(d, "capacity").exists() && (batt == null || d.getName().equals("battery"))) batt = d;
                continue;
            }
            int kind = chargerKind(type);                   // Unknown (the `charger` and `customer` nodes here) is not a charger, as in BatteryMonitor
            if (kind == 0 || num(d, "online", 0) == 0) continue;
            if (kind == 1) i.ac = true; else if (kind == 2) i.usb = true; else if (kind == 3) i.wireless = true; else i.dock = true;
            i.maxCurrentUa = Math.max(i.maxCurrentUa, num(d, "current_max", 0));
            i.maxVoltageUv = Math.max(i.maxVoltageUv, num(d, "voltage_max", 0));
        }
        if (i.anyCharger()) {
            if (i.maxCurrentUa <= 0) i.maxCurrentUa = DEFAULT_MAX_CURRENT_UA;
            if (i.maxVoltageUv <= 0) i.maxVoltageUv = DEFAULT_MAX_VOLTAGE_UV;
        } else { i.maxCurrentUa = 0; i.maxVoltageUv = 0; }
        if (batt == null) return i;                         // no battery: present=false, level 0

        i.present = num(batt, "present", 1) != 0;
        i.rawStatus = i.status = status(str(batt, "status"));
        i.health = health(str(batt, "health"));
        i.rawLevel = i.level = Math.max(0, Math.min(100, num(batt, "capacity", 0)));
        i.voltageMv = num(batt, "voltage_now", 0) / 1000;
        i.tempTenthsC = num(batt, "temp", 0);
        i.currentUa = num(batt, "current_now", 0);          // this driver: positive while charging, negative while discharging, same as Android
        i.currentAvgUa = num(batt, "current_avg", 0);
        i.cycleCount = num(batt, "cycle_count", 0);
        i.fullChargeUah = num(batt, "charge_full", 0);
        i.chargeCounterUah = num(batt, "charge_counter", 0);
        String t = str(batt, "technology");
        if (t != null) i.technology = t;
        Matcher m = DESIGN.matcher(String.valueOf(str(batt, "batt_id")));   // "1,5000ma": battery id, design capacity in mAh
        if (m.find()) i.designUah = Integer.parseInt(m.group(1)) * 1000;
        if (correctLevel) correctLevel(i);
        return i;
    }
    private static final Pattern DESIGN = Pattern.compile("(\\d{3,5})\\s*m[aA]");

    /** drivers/power/supply/mediatek/battery/mtk_battery.c computes charge_counter as ui_soc * q_max * 10 and charge_full as q_max * 1000, so charge_counter / charge_full is
     *  the gauge's own UI state of charge, while `capacity` is a separately stored value. On the tablet capacity stayed 100 and status Full while the gauge (dmesg
     *  "ui_soc:6656", fuelgauged) was at 66 percent and charging at 1 A, so when the two disagree by more than maxDisagreement points the ratio wins, and a Full
     *  status that goes with the stale 100 becomes Charging (a charger is online) or Discharging. If the files are missing, capacity is used as it is. */
    static void correctLevel(Info i) {
        if (i.fullChargeUah <= 0 || i.chargeCounterUah <= 0) return;
        int ratio = (int) Math.min(100, Math.round(100.0 * i.chargeCounterUah / i.fullChargeUah));
        if (Math.abs(i.level - ratio) <= maxDisagreement) return;
        i.level = ratio;
        i.levelCorrected = true;
        if (i.status == FULL && ratio < 100) i.status = i.anyCharger() ? CHARGING : DISCHARGING;
    }

    /** 0 not a charger, 1 AC, 2 USB, 3 wireless, 4 dock: the BatteryMonitor table. */
    static int chargerKind(String type) {
        switch (type) {
            case "UPS": case "Mains": case "USB_DCP": case "USB_HVDCP": case "USB_HVDCP_3": case "USB_CDP": case "USB_ACA": case "USB_C": case "USB_PD": return 1;
            case "USB": case "USB_PD_DRP": return 2;
            case "Wireless": return 3;
            case "Dock": return 4;
            default: return 0;
        }
    }

    static int status(String s) {
        if (s == null) return STATUS_UNKNOWN;
        switch (s) {
            case "Charging": return CHARGING;
            case "Discharging": return DISCHARGING;
            case "Not charging": return NOT_CHARGING;
            case "Full": return FULL;
            default: return STATUS_UNKNOWN;
        }
    }

    static int health(String s) {
        if (s == null) return HEALTH_UNKNOWN;
        switch (s) {
            case "Good": case "Warm": case "Cool": return GOOD;
            case "Overheat": case "Hot": return OVERHEAT;
            case "Dead": return DEAD;
            case "Over voltage": return OVER_VOLTAGE;
            case "Unspecified failure": return UNSPECIFIED_FAILURE;
            case "Cold": return COLD;
            default: return HEALTH_UNKNOWN;
        }
    }

    private static String str(File dir, String name) {
        try (BufferedReader r = new BufferedReader(new FileReader(new File(dir, name)))) {
            String s = r.readLine();
            return s == null ? null : s.trim();
        } catch (Exception e) {
            return null;                                    // missing node, or the driver answers EINVAL: treat as absent
        }
    }

    private static int num(File dir, String name, int def) {
        String s = str(dir, name);
        if (s == null || s.isEmpty()) return def;
        try {
            long v = Long.parseLong(s);
            return (int) Math.max(Integer.MIN_VALUE, Math.min(Integer.MAX_VALUE, v));
        } catch (NumberFormatException e) {
            return def;
        }
    }
}
