/* On-device check: dlopens the shim, lists sensors, enables the virtual compass and accelerometer, prints events. Run as root with the HAL service stopped:
 *   COMPASS_REAL=/data/local/tmp/compass-test/sensors.orig.so ./harness /data/local/tmp/compass-test/sensors.mt6765.so [seconds] */
#include <dlfcn.h>
#include <hardware/sensors.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int main(int argc, char **argv) {
    void *h = dlopen(argv[1], RTLD_NOW);
    if (!h) { printf("dlopen: %s\n", dlerror()); return 1; }
    struct sensors_module_t *m = dlsym(h, "HMI");
    if (!m) { printf("no HMI\n"); return 1; }
    const struct sensor_t *l;
    int n = m->get_sensors_list(m, &l);
    int vh = -1, ah = -1;
    for (int i = 0; i < n; i++) {
        printf("%2d handle=%d type=%d %s\n", i, l[i].handle, l[i].type, l[i].name);
        if (l[i].type == SENSOR_TYPE_MAGNETIC_FIELD) vh = l[i].handle;
        if (l[i].type == SENSOR_TYPE_ACCELEROMETER && ah < 0) ah = l[i].handle;
    }
    struct hw_device_t *d;
    int r = m->common.methods->open(&m->common, SENSORS_HARDWARE_POLL, &d);
    printf("open=%d version=0x%x\n", r, d ? d->version : 0);
    struct sensors_poll_device_1 *p = (void *)d;
    p->batch(p, vh, 0, 100000000, 0);
    printf("activate virt=%d\n", p->activate((void *)p, vh, 1));
    int secs = argc > 2 ? atoi(argv[2]) : 5, accs = 0, mags = 0;
    time_t end = time(0) + secs;
    sensors_event_t ev[16];
    while (time(0) < end) {
        int k = p->poll((void *)p, ev, 16);
        for (int i = 0; i < k; i++) {
            if (ev[i].type == SENSOR_TYPE_ACCELEROMETER) accs++;
            if (ev[i].type == SENSOR_TYPE_MAGNETIC_FIELD) {
                if (mags++ % 10 == 0) printf("mag %.1f %.1f %.1f st=%d\n", ev[i].magnetic.x, ev[i].magnetic.y, ev[i].magnetic.z, ev[i].magnetic.status);
            }
        }
    }
    printf("accel leaked to client=%d (must be 0), mag events=%d\n", accs, mags);
    p->activate((void *)p, vh, 0);
    printf("done\n");
    return 0;
}
