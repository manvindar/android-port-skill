#define _GNU_SOURCE
// Debug /init for the M30s A17 boot: mounts /dev, then runs the real /system/bin/init as a ptrace'd child and logs its syscalls (and anything it prints) to /dev/kmsg.
// Static aarch64, built with the NDK clang. The child is not pid 1, which is fine for finding why first-stage init aborts.
#include <elf.h>
#include <sched.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/ptrace.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>
static int k = -1;
static void kl(const char* s) { char b[420]; int n = snprintf(b, sizeof b, "<3>M30DBG: %s", s); if (k >= 0) write(k, b, n); }
static void rd(pid_t p, unsigned long a, char* out, int max) {
    int i = 0;
    while (i < max - 1) {
        errno = 0; long w = ptrace(PTRACE_PEEKDATA, p, (void*)(a + i), 0);
        if (errno) break;
        for (int j = 0; j < 8 && i < max - 1; j++) { char c = (w >> (8 * j)) & 0xff; if (!c) { out[i] = 0; return; } out[i++] = (c >= 32 && c < 127) ? c : '?'; }
    }
    out[i] = 0;
}
int main(int argc, char** argv) {
    int ns = argc > 1 && !strcmp(argv[1], "-ns");   // TWRP test mode: run init as pid 1 of a new pid+mount namespace inside chroot /s
    if (!ns) { mkdir("/dev", 0755);
    mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
    mkdir("/proc", 0755); mount("proc", "/proc", "proc", 0, NULL); }
    int pd = open("/proc/sys/kernel/printk_devkmsg", O_WRONLY);   // the kernel rate-limits userspace /dev/kmsg writes (10 per 5 s) unless this is "on"
    if (pd >= 0) { write(pd, "on\n", 3); close(pd); }
    k = open("/dev/kmsg", O_WRONLY);
    if (k < 0 && !ns) { mknod("/dev/kmsg", S_IFCHR | 0600, makedev(1, 11)); k = open("/dev/kmsg", O_WRONLY); }
    kl("trace start");
    int pf[2]; pipe(pf);
    if (ns) { if (unshare(CLONE_NEWPID | CLONE_NEWNS)) kl("unshare failed"); mount(0, "/", 0, MS_REC | MS_PRIVATE, 0); }
    pid_t c = fork();
    if (c == 0) {
        if (ns) { chroot("/s"); chdir("/"); char* a[] = {"/init", 0}; argv = a; }
        ptrace(PTRACE_TRACEME, 0, 0, 0); dup2(pf[1], 1); dup2(pf[1], 2); close(pf[0]);
        if (access("/system/a14fs/init", X_OK) == 0) { char* a[] = {"/system/a14fs/linker64", "/system/a14fs/init", 0}; char* e[] = {"LD_LIBRARY_PATH=/system/a14fs/lib64", "HOME=/", "TERM=linux", 0}; execve(a[0], a, e); }
        execv("/system/bin/init", argv); _exit(126);
    }
    close(pf[1]); fcntl(pf[0], F_SETFL, O_NONBLOCK);
    int ws, entry = 1; long cur = 0; char l[400], s0[120], s1[120], s2[120];
    waitpid(c, &ws, 0);
    ptrace(PTRACE_SETOPTIONS, c, 0, PTRACE_O_TRACESYSGOOD | PTRACE_O_EXITKILL);
    for (;;) {
        ptrace(PTRACE_SYSCALL, c, 0, 0);
        if (waitpid(c, &ws, 0) < 0) break;
        char pb[300]; int n = read(pf[0], pb, sizeof pb - 1);
        if (n > 0) { pb[n] = 0; for (char* q = pb; *q; q++) if (*q == '\n') *q = ' '; snprintf(l, sizeof l, "OUT: %s", pb); kl(l); }
        if (WIFEXITED(ws) || WIFSIGNALED(ws)) { snprintf(l, sizeof l, "child ended ws=%d exit=%d sig=%d", ws, WIFEXITED(ws) ? WEXITSTATUS(ws) : -1, WIFSIGNALED(ws) ? WTERMSIG(ws) : 0); kl(l); break; }
        if (!WIFSTOPPED(ws)) continue;
        if (WSTOPSIG(ws) != (SIGTRAP | 0x80)) { snprintf(l, sizeof l, "signal %d", WSTOPSIG(ws)); kl(l); continue; }
        unsigned long long regs[34]; struct iovec iv = {regs, sizeof regs};
        ptrace(PTRACE_GETREGSET, c, (void*)NT_PRSTATUS, &iv);
        if (entry) {
            cur = regs[8]; s0[0] = s1[0] = s2[0] = 0;
            if (cur == 40) { rd(c, regs[0], s0, sizeof s0); rd(c, regs[1], s1, sizeof s1); rd(c, regs[2], s2, sizeof s2); }
            else if (cur == 56 || cur == 34 || cur == 33 || cur == 79 || cur == 48 || cur == 78 || cur == 35 || cur == 53 || cur == 54 || cur == 436 || cur == 439) rd(c, regs[1], s1, sizeof s1);
            else if (cur == 39 || cur == 43 || cur == 49 || cur == 51 || cur == 221 || cur == 36) rd(c, regs[0], s0, sizeof s0);
            snprintf(l, sizeof l, "> %ld(%llx,%llx,%llx) [%s|%s|%s]", cur, regs[0], regs[1], regs[2], s0, s1, s2);
            if (cur != 63 && cur != 64 && cur != 29) kl(l);   /* skip read/write/ioctl noise */
            if (cur == 131 || cur == 134) kl(l);
        } else if (cur != 63 && cur != 64 && cur != 29) { snprintf(l, sizeof l, "< %ld = %lld", cur, (long long)regs[0]); kl(l); }
        entry = !entry;
    }
    for (;;) sleep(1000);   // keep pid 1 alive: the phone then sits at the logo and the kmsg is readable through pstore after a manual reset
}
