/* Virtual compass for the TB-X606V, which has no magnetometer.
 *
 * Loaded by the vendor sensors HAL service in place of sensors.mt6765.so; the real library sits next to it as sensors.mt6765.orig.so. Everything is forwarded to it.
 * One sensor is added: a MAGNETIC_FIELD whose vector is built from the GPS course (compassd writes it to /data/local/tmp/compass/heading) and the tilt from the real
 * accelerometer. SensorService then derives ORIENTATION and ROTATION_VECTOR from accelerometer + magnetometer on its own.
 *
 * The heading is the direction of travel, so it follows the tablet only if the tablet is mounted facing along the car.
 * ponytail: no gyro smoothing and no stop detection beyond what compassd does; add when the compass needs to hold a turn between GPS fixes.
 */
#define LOG_TAG "compassshim"
#include <android/log.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <hardware/sensors.h>
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

#define REAL_PATH "/vendor/lib64/hw/sensors.mt6765.orig.so"
#define DIR_PATH "/data/local/tmp/compass"
#define HEADING_FILE DIR_PATH "/heading"   /* "valid heading_magnetic_deg field_uT inclination_deg offset_deg" */
#define ACTIVE_FILE DIR_PATH "/active"     /* exists while the virtual sensor is enabled; compassd turns the GPS on for it */
#define QN 512
#define MIN_PERIOD_NS 20000000LL
#define DEFAULT_PERIOD_NS 50000000LL

static struct sensor_t virt = {
    .name = "Virtual Compass (GPS course)", .vendor = "tb-x606v", .version = 1, .handle = 0, .type = SENSOR_TYPE_MAGNETIC_FIELD,
    .maxRange = 4912.0f, .resolution = 0.15f, .power = 0.1f, .minDelay = 20000, .fifoReservedEventCount = 0, .fifoMaxEventCount = 0,
    .stringType = SENSOR_STRING_TYPE_MAGNETIC_FIELD, .requiredPermission = "", .maxDelay = 1000000, .flags = SENSOR_FLAG_CONTINUOUS_MODE,
};

static struct {
    struct sensors_module_t *real;
    sensors_poll_device_1_t *rdev;
    sensors_poll_device_1_t wdev;
    struct sensor_t *list;
    int count, vh, acc_h, added;
    pthread_mutex_t mu;
    pthread_cond_t cv;
    int v_active, acc_user;
    int64_t v_period, v_next;
    float g[3];
    int have_g;
    sensors_event_t q[QN];
    int qh, qn;
    int th_started;
    int hd_valid;
    float hd_deg, hd_field, hd_incl, hd_off;
    int64_t hd_read;
} S = {.mu = PTHREAD_MUTEX_INITIALIZER, .v_period = DEFAULT_PERIOD_NS, .hd_field = 48.f, .hd_incl = 55.f};

struct sensors_module_t HMI;

static int64_t now_ns(clockid_t c) {
    struct timespec t;
    clock_gettime(c, &t);
    return (int64_t)t.tv_sec * 1000000000LL + t.tv_nsec;
}

static void push(const sensors_event_t *e) { /* caller holds mu; drops the oldest event when full */
    if (S.qn == QN) { S.qh = (S.qh + 1) % QN; S.qn--; }
    S.q[(S.qh + S.qn) % QN] = *e;
    S.qn++;
}

static void read_heading(int64_t now) { /* caller holds mu */
    if (now - S.hd_read < 500000000LL) return;
    S.hd_read = now;
    char buf[96];
    int fd = open(HEADING_FILE, O_RDONLY | O_CLOEXEC);
    if (fd < 0) { S.hd_valid = 0; return; }
    ssize_t n = read(fd, buf, sizeof buf - 1);
    close(fd);
    if (n <= 0) { S.hd_valid = 0; return; }
    buf[n] = 0;
    int v; float h, f, i, o = 0;
    int k = sscanf(buf, "%d %f %f %f %f", &v, &h, &f, &i, &o);
    if (k >= 4) { S.hd_valid = v; S.hd_deg = h; S.hd_field = f; S.hd_incl = i; S.hd_off = k >= 5 ? o : 0; }
}

static void norm3(float *v) {
    float l = sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    if (l > 1e-6f) { v[0] /= l; v[1] /= l; v[2] /= l; }
}

static void cross3(const float *a, const float *b, float *r) {
    r[0] = a[1] * b[2] - a[2] * b[1];
    r[1] = a[2] * b[0] - a[0] * b[2];
    r[2] = a[0] * b[1] - a[1] * b[0];
}

/* Magnetic vector in the device frame for a "forward" axis heading psi (clockwise from magnetic north), with up taken from the accelerometer. */
static void make_mag(sensors_event_t *e, int64_t ts) {
    float u[3] = {0, 0, 1};
    if (S.have_g) { u[0] = S.g[0]; u[1] = S.g[1]; u[2] = S.g[2]; norm3(u); }
    /* forward = the back of the screen (-Z) when the tablet stands up, the top edge (+Y) when it lies down */
    float f[4][3] = {{0, 0, -1}, {0, 1, 0}};
    float fh[3];
    for (int c = 0; c < 2; c++) {
        float d = f[c][0] * u[0] + f[c][1] * u[1] + f[c][2] * u[2];
        for (int j = 0; j < 3; j++) fh[j] = f[c][j] - d * u[j];
        float l = sqrtf(fh[0] * fh[0] + fh[1] * fh[1] + fh[2] * fh[2]);
        if (l >= 0.5f || c == 1) { if (l > 1e-6f) { fh[0] /= l; fh[1] /= l; fh[2] /= l; } break; }
    }
    float psi = (S.hd_deg + S.hd_off) * (float)M_PI / 180.f;
    float fu[3], n[3];
    cross3(fh, u, fu);
    for (int j = 0; j < 3; j++) n[j] = cosf(psi) * fh[j] - sinf(psi) * fu[j];
    float inc = S.hd_incl * (float)M_PI / 180.f;
    float H = S.hd_field * cosf(inc), V = S.hd_field * sinf(inc);
    memset(e, 0, sizeof *e);
    e->version = sizeof *e;
    e->sensor = S.vh;
    e->type = SENSOR_TYPE_MAGNETIC_FIELD;
    e->timestamp = ts;
    for (int j = 0; j < 3; j++) e->magnetic.v[j] = H * n[j] - V * u[j];
    e->magnetic.status = S.hd_valid ? SENSOR_STATUS_ACCURACY_MEDIUM : SENSOR_STATUS_UNRELIABLE;
}

static void *poll_thread(void *arg) {
    (void)arg;
    sensors_event_t buf[16];
    for (;;) {
        int n = S.rdev->poll((struct sensors_poll_device_t *)S.rdev, buf, 16);
        if (n <= 0) { usleep(10000); continue; }
        pthread_mutex_lock(&S.mu);
        for (int i = 0; i < n; i++) {
            if (buf[i].type == SENSOR_TYPE_ACCELEROMETER && buf[i].sensor == S.acc_h) {
                S.g[0] = buf[i].acceleration.x; S.g[1] = buf[i].acceleration.y; S.g[2] = buf[i].acceleration.z; S.have_g = 1;
                if (!S.acc_user) continue;
            }
            push(&buf[i]);
        }
        pthread_cond_signal(&S.cv);
        pthread_mutex_unlock(&S.mu);
    }
    return NULL;
}

static int w_poll(struct sensors_poll_device_t *d, sensors_event_t *data, int count) {
    (void)d;
    pthread_mutex_lock(&S.mu);
    for (;;) {
        int n = 0;
        while (n < count && S.qn) { data[n++] = S.q[S.qh]; S.qh = (S.qh + 1) % QN; S.qn--; }
        int64_t now = now_ns(CLOCK_BOOTTIME);
        if (S.v_active && n < count && now >= S.v_next) {
            read_heading(now);
            make_mag(&data[n++], now);
            S.v_next = now + S.v_period;
        }
        if (n > 0) { pthread_mutex_unlock(&S.mu); return n; }
        if (S.v_active) {
            struct timespec t;
            clock_gettime(CLOCK_MONOTONIC, &t);
            int64_t at = (int64_t)t.tv_sec * 1000000000LL + t.tv_nsec + (S.v_next - now);
            t.tv_sec = at / 1000000000LL; t.tv_nsec = at % 1000000000LL;
            pthread_cond_timedwait(&S.cv, &S.mu, &t);
        } else {
            pthread_cond_wait(&S.cv, &S.mu);
        }
    }
}

static void internal_acc(int on) { /* caller holds mu; keeps the real accelerometer running for the tilt while no client wants it */
    if (S.acc_user || S.acc_h < 0) return;
    if (on && S.rdev->batch) S.rdev->batch(S.rdev, S.acc_h, 0, MIN_PERIOD_NS, 0);
    S.rdev->activate((struct sensors_poll_device_t *)S.rdev, S.acc_h, on);
}

static void flag_file(int on) {
    if (on) { int fd = open(ACTIVE_FILE, O_WRONLY | O_CREAT | O_CLOEXEC, 0666); if (fd >= 0) { fchmod(fd, 0666); close(fd); } }
    else unlink(ACTIVE_FILE);
}

static int w_activate(struct sensors_poll_device_t *d, int h, int en) {
    (void)d;
    int r = 0;
    pthread_mutex_lock(&S.mu);
    if (h == S.vh) {
        if (en && !S.v_active) { S.v_next = 0; internal_acc(1); flag_file(1); }
        if (!en && S.v_active) { internal_acc(0); flag_file(0); }
        S.v_active = en;
        pthread_cond_signal(&S.cv);
    } else if (h == S.acc_h) {
        S.acc_user = en;
        if (en || !S.v_active) r = S.rdev->activate((struct sensors_poll_device_t *)S.rdev, h, en);
        if (!en && S.v_active) internal_acc(1);
    } else {
        r = S.rdev->activate((struct sensors_poll_device_t *)S.rdev, h, en);
    }
    pthread_mutex_unlock(&S.mu);
    return r;
}

static void set_period(int64_t ns) {
    if (ns < MIN_PERIOD_NS) ns = MIN_PERIOD_NS;
    S.v_period = ns;
}

static int w_setDelay(struct sensors_poll_device_t *d, int h, int64_t ns) {
    (void)d;
    if (h == S.vh) { pthread_mutex_lock(&S.mu); set_period(ns); pthread_mutex_unlock(&S.mu); return 0; }
    return S.rdev->setDelay((struct sensors_poll_device_t *)S.rdev, h, ns);
}

static int w_batch(struct sensors_poll_device_1 *d, int h, int flags, int64_t period, int64_t timeout) {
    (void)d;
    if (h == S.vh) { pthread_mutex_lock(&S.mu); set_period(period); pthread_mutex_unlock(&S.mu); return 0; }
    return S.rdev->batch(S.rdev, h, flags, period, timeout);
}

static int w_flush(struct sensors_poll_device_1 *d, int h) {
    (void)d;
    if (h != S.vh) return S.rdev->flush(S.rdev, h);
    sensors_event_t e;
    memset(&e, 0, sizeof e);
    e.version = META_DATA_VERSION;
    e.type = SENSOR_TYPE_META_DATA;
    e.meta_data.what = META_DATA_FLUSH_COMPLETE;
    e.meta_data.sensor = S.vh;
    pthread_mutex_lock(&S.mu);
    push(&e);
    pthread_cond_signal(&S.cv);
    pthread_mutex_unlock(&S.mu);
    return 0;
}

static int w_inject(struct sensors_poll_device_1 *d, const sensors_event_t *e) { (void)d; return S.rdev->inject_sensor_data(S.rdev, e); }
static int w_reg_direct(struct sensors_poll_device_1 *d, const struct sensors_direct_mem_t *m, int n) {
    (void)d; return S.rdev->register_direct_channel(S.rdev, m, n);
}
static int w_cfg_direct(struct sensors_poll_device_1 *d, int s, int c, const struct sensors_direct_cfg_t *cfg) {
    (void)d; return S.rdev->config_direct_report(S.rdev, s, c, cfg);
}
static int w_close(struct hw_device_t *d) { (void)d; return S.rdev->common.close(&S.rdev->common); }

static int shim_list(struct sensors_module_t *m, struct sensor_t const **list) {
    (void)m;
    if (!S.list) {
        struct sensor_t const *rl = NULL;
        int n = S.real->get_sensors_list(S.real, &rl);
        if (n < 0 || !rl) { *list = rl; return n; }
        S.list = malloc(sizeof(struct sensor_t) * (n + 1));
        memcpy(S.list, rl, sizeof(struct sensor_t) * n);
        int maxh = 0, has_mag = 0;
        S.acc_h = -1;
        for (int i = 0; i < n; i++) {
            if (rl[i].handle > maxh) maxh = rl[i].handle;
            if (rl[i].type == SENSOR_TYPE_MAGNETIC_FIELD) has_mag = 1;
            if (rl[i].type == SENSOR_TYPE_ACCELEROMETER && S.acc_h < 0 && !(rl[i].flags & SENSOR_FLAG_WAKE_UP)) S.acc_h = rl[i].handle;
        }
        S.count = n;
        if (!has_mag && S.acc_h >= 0) {   /* a real magnetometer, if one ever shows up, wins */
            S.vh = virt.handle = maxh + 1;
            S.list[n] = virt;
            S.added = 1;
            S.count = n + 1;
        }
        LOGI("sensors: %d real, virtual compass %s (handle %d, accel %d)", n, S.added ? "added" : "not added", S.vh, S.acc_h);
    }
    *list = S.list;
    return S.count;
}

static int shim_open(const struct hw_module_t *m, const char *id, struct hw_device_t **dev) {
    (void)m;
    int r = S.real->common.methods->open(&S.real->common, id, dev);
    if (r) return r;
    S.rdev = (sensors_poll_device_1_t *)*dev;
    memcpy(&S.wdev, S.rdev, sizeof S.wdev);
    S.wdev.common.module = &HMI.common;
    S.wdev.common.close = w_close;
    S.wdev.poll = w_poll;
    S.wdev.activate = w_activate;
    S.wdev.setDelay = w_setDelay;
    if (S.rdev->common.version >= SENSORS_DEVICE_API_VERSION_1_0) {
        S.wdev.batch = w_batch;
        S.wdev.flush = w_flush;
        S.wdev.inject_sensor_data = w_inject;
        S.wdev.register_direct_channel = w_reg_direct;
        S.wdev.config_direct_report = w_cfg_direct;
    }
    if (!S.th_started) {
        pthread_t t;
        pthread_attr_t a;
        pthread_attr_init(&a);
        pthread_attr_setdetachstate(&a, PTHREAD_CREATE_DETACHED);
        if (!pthread_create(&t, &a, poll_thread, NULL)) S.th_started = 1;
    }
    *dev = &S.wdev.common;
    return 0;
}

static struct hw_module_methods_t methods = {.open = shim_open};

__attribute__((constructor)) static void init(void) {
    pthread_condattr_t ca;
    pthread_condattr_init(&ca);
    pthread_condattr_setclock(&ca, CLOCK_MONOTONIC);
    pthread_cond_init(&S.cv, &ca);
    const char *path = getenv("COMPASS_REAL");   /* test hook; the HAL service has no such variable */
    void *h = dlopen(path ? path : REAL_PATH, RTLD_NOW | RTLD_LOCAL);
    if (!h) { LOGE("cannot load %s: %s", path ? path : REAL_PATH, dlerror()); return; }
    S.real = (struct sensors_module_t *)dlsym(h, HAL_MODULE_INFO_SYM_AS_STR);
    if (!S.real) { LOGE("no HMI in real library"); return; }
    HMI = *S.real;
    HMI.common.methods = &methods;
    HMI.common.dso = NULL;
    HMI.get_sensors_list = shim_list;
    LOGI("loaded real HAL %s v%d", S.real->common.name, S.real->common.module_api_version);
}
