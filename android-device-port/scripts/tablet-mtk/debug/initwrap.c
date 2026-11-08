#define _GNU_SOURCE
// PID 1 wrapper: runs /system/bin/init.real under ptrace, copies write(1|2) text and the last syscalls to /dev/kmsg when it dies (the console log survives in ramoops)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <elf.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
#include <sys/uio.h>
#include <sys/reboot.h>
#include <signal.h>
#include <stdarg.h>
static int kfd = -1;
static void K(const char *f, ...) { char b[600], o[640]; va_list ap; va_start(ap, f); vsnprintf(b, sizeof b, f, ap); va_end(ap); int m = snprintf(o, sizeof o, "<6>initwrap: %s\n", b); if (kfd >= 0 && write(kfd, o, m) < 0) {} }
static void F(const char *f, ...) { int fd = open("/data/local/tmp/initwrap.log", O_WRONLY | O_CREAT | O_APPEND, 0666); if (fd < 0) return; char b[700]; va_list ap; va_start(ap, f); int n = vsnprintf(b, sizeof b - 1, f, ap); va_end(ap); b[n++] = '\n'; if (write(fd, b, n) < 0) {} close(fd); }
static void rstr(pid_t p, unsigned long a, char *o, size_t n) { o[0] = 0; struct iovec l = {o, n - 1}, r = {(void *)a, n - 1}; ssize_t k = process_vm_readv(p, &l, 1, &r, 1, 0); if (k < 0) { strcpy(o, "?"); return; } o[k] = 0; }
#define R 100
static char ring[R][160]; static int cnt;
#define M 80
static char msgs[M][210]; static int mcnt;
static void dumpmsgs(const char *why) { K("== %s: last %d init messages (written by init to /dev/kmsg)", why, mcnt < M ? mcnt : M); int n = mcnt < M ? mcnt : M; for (int k = n; k > 0; k--) { K("M %s", msgs[(mcnt - k) % M]); usleep(600000); } }
int main(int argc, char **argv) {
  if (getpid() != 1) { argv[0] = "/system/bin/init"; execv("/system/bin/init.real", argv); _exit(127); }   // second stage: replace ourselves, PID 1 keeps tracing this pid across the exec
  kfd = open("/dev/kmsg", O_WRONLY); K("wrapper started pid=%d argc=%d argv1=%s", getpid(), argc, argc > 1 ? argv[1] : "-");
  pid_t pid = fork();
  if (!pid) { ptrace(PTRACE_TRACEME, 0, 0, 0); argv[0] = "/system/bin/init"; execv("/system/bin/init.real", argv); K("execv init.real failed: %d", errno); _exit(127); }
  int st; waitpid(pid, &st, 0); ptrace(PTRACE_SETOPTIONS, pid, 0, PTRACE_O_TRACESYSGOOD | PTRACE_O_TRACEEXEC);
  int insys = 0; unsigned long cur[4] = {0};
  for (;;) {
    ptrace(PTRACE_SYSCALL, pid, 0, 0);
    pid_t w = waitpid(-1, &st, __WALL); if (w < 0) { if (errno == EINTR) continue; break; }
    if (w != pid) continue;
    if (WIFEXITED(st) || WIFSIGNALED(st)) {
      F("INIT ENDED exited=%d status=%d signaled=%d sig=%d", WIFEXITED(st), WEXITSTATUS(st), WIFSIGNALED(st), WTERMSIG(st)); { int n = cnt < R ? cnt : R; for (int k = n; k > 0; k--) F("  sys %s", ring[(cnt - k) % R]); }
      K("init.real ended: exited=%d status=%d signaled=%d sig=%d; last syscalls:", WIFEXITED(st), WEXITSTATUS(st), WIFSIGNALED(st), WTERMSIG(st));
      int n = cnt < R ? cnt : R; for (int k = n; k > 0; k--) K("  %s", ring[(cnt - k) % R]);
      sleep(3); break;
    }
    int sig = WSTOPSIG(st);
    if ((st >> 16) == PTRACE_EVENT_EXEC) { K("exec event"); insys = 0; continue; }
    if (sig != (SIGTRAP | 0x80)) { if (sig != SIGTRAP) { K("signal %d", sig); ptrace(PTRACE_SYSCALL, pid, 0, sig); } continue; }
    struct { unsigned long long regs[31], sp, pc, pstate; } r; struct iovec io = {&r, sizeof r};
    if (ptrace(PTRACE_GETREGSET, pid, (void *)NT_PRSTATUS, &io)) continue;
    if (!insys) { insys = 1; cur[0] = r.regs[8]; cur[1] = r.regs[0]; cur[2] = r.regs[1]; cur[3] = r.regs[2];
      char s[100] = ""; if (cur[0] == 56 || cur[0] == 221) rstr(pid, cur[0] == 56 ? cur[2] : cur[1], s, sizeof s);
      if (cur[0] == 64 && cur[1] > 2) { char b[210]; rstr(pid, cur[2], b, cur[3] < 200 ? cur[3] + 1 : 200); if (b[0] == '<') { for (char *q = b; *q; q++) if (*q == '\n') *q = ' '; strcpy(msgs[mcnt++ % M], b); if (strstr(b, "reboot-bootloader") || strstr(b, "powerctl") || strstr(b, "Reboot") || strstr(b, "reboot")) { static int done; if (!done) { done = 1; dumpmsgs("init is about to reboot"); } } } }
      if (cur[0] == 142) { K("reboot() syscall: magic %#lx cmd %#lx", cur[1], cur[2]); F("REBOOT syscall magic %#lx cmd %#lx", cur[1], cur[2]); { int n = cnt < R ? cnt : R; for (int k = n; k > 0; k--) F("  sys %s", ring[(cnt - k) % R]); } }
      if (cur[0] == 64 && (cur[1] == 1 || cur[1] == 2)) { char b[300]; rstr(pid, cur[2], b, cur[3] < 290 ? cur[3] + 1 : 290); for (char *q = b; *q; q++) if (*q == '\n') *q = ' '; K("WRITE fd%lu: %s", cur[1], b); }
      snprintf(ring[cnt++ % R], 160, "nr=%lu a0=%#lx a1=%#lx a2=%#lx %s", cur[0], cur[1], cur[2], cur[3], s);
    } else { insys = 0; char *e = ring[(cnt - 1) % R]; size_t n = strlen(e); if (n < 110) snprintf(e + n, 40, " = %ld", (long)r.regs[0]); }
  }
  return 0;
}
