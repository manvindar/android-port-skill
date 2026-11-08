// boot probe: run from an init rc (`exec - root root -- /system/bin/dbgprobe TAG`), logs to /dev/kmsg what the M30s boot needs to know:
// SELinux enforce flag, our own context, whether /system/bin/sh can be executed, and the tethering apex bind mounts.
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static int k;
static void L(const char* tag, const char* fmt, const char* a, const char* b) {
    char m[600], o[700];
    snprintf(m, sizeof m, fmt, a, b);
    int n = snprintf(o, sizeof o, "<6>dbgprobe[%s]: %s\n", tag, m);
    if (write(k, o, n) < 0) {}
    int f = open("/data/dbgprobe.log", O_WRONLY | O_CREAT | O_APPEND, 0644);   // survives the reboot, readable from TWRP (userdata has no encryption now)
    if (f >= 0) { if (write(f, o, n) < 0) {} close(f); }
}
static void rd(const char* tag, const char* what, const char* path) {
    char b[300] = "?";
    int fd = open(path, O_RDONLY);
    if (fd >= 0) { int n = read(fd, b, sizeof b - 1); b[n > 0 ? n : 0] = 0; close(fd); }
    else snprintf(b, sizeof b, "open errno=%d", errno);
    for (char* p = b; *p; p++) if (*p == '\n' || *p == '\0') *p = ' ';
    L(tag, "%s = %s", what, b);
}
int main(int argc, char** argv) {
    const char* t = argc > 1 ? argv[1] : "x";
    k = open("/dev/kmsg", O_WRONLY);
    { char e[40]; snprintf(e, sizeof e, "%d", k < 0 ? errno : 0); L(t, "start, kmsg open errno=%s", e, ""); }
    rd(t, "enforce", "/sys/fs/selinux/enforce");
    rd(t, "self context", "/proc/self/attr/current");
    pid_t c = fork();
    if (c == 0) { execl("/system/bin/sh", "sh", "-c", "exit 0", (char*)0); _exit(100 + (errno & 0x7f)); }
    int st = 0; waitpid(c, &st, 0);
    char r[40]; snprintf(r, sizeof r, "%d", WIFEXITED(st) ? WEXITSTATUS(st) : -1);
    L(t, "exec sh -> exit %s (100+errno means exec failed; 113 = EACCES)", r, "");
    struct stat s;
    char z[40] = "";
    if (stat("/apex/com.android.tethering/bin/netbpfload", &s) == 0) snprintf(z, sizeof z, "%lld", (long long)s.st_size); else snprintf(z, sizeof z, "errno %d", errno);
    L(t, "apex netbpfload size = %s (tracer 3503360, stock apex differs)", z, "");
    FILE* f = fopen("/proc/self/mountinfo", "r"); char line[500]; int shown = 0;
    while (f && fgets(line, sizeof line, f)) {
        if (strstr(line, "netbpfload") || strstr(line, "bpf.a17") || strstr(line, "tethering")) { line[strcspn(line, "\n")] = 0; if (shown++ < 6) L(t, "mount: %s", line, ""); }
    }
    L(t, "tethering/bpf mounts seen: %s", shown ? "yes" : "none", "");
    return 0;
}
