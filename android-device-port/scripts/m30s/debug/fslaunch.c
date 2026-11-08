// /init for the M30s Android 17 image: A17's /system/bin/init is second-stage only (it aborts without an argument), and this phone's boot.img has no ramdisk that would carry a first stage.
// So /init -> this launcher, which runs Android 14's init (its first stage mounts /dev, /proc, /sys, vendor, ...) through Android 14's own linker and libraries in /system/a14fs, isolated from A17's libs.
// That init ends with execv("/system/bin/init", "selinux_setup"), which is A17's init. (The A14 linker has no --library-path, so LD_LIBRARY_PATH carries the lib dir; init's clearenv() drops it.)
// DEBUG: stdout/stderr go to /dev/kmsg (via a temporary devtmpfs) so linker errors show in the pstore console.
#include <fcntl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <unistd.h>
int main(void) {
    mkdir("/dev", 0755);
    mount("devtmpfs", "/dev", "devtmpfs", 0, 0);
    int k = open("/dev/kmsg", O_WRONLY);
    if (k >= 0) { dup2(k, 1); dup2(k, 2); }
    char* a[] = {"/system/a14fs/linker64", "/system/a14fs/init", 0};
    char* e[] = {"LD_LIBRARY_PATH=/system/a14fs/lib64", "HOME=/", "TERM=linux", 0};
    execve(a[0], a, e);
    return 127;
}
