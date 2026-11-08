#define _GNU_SOURCE
// run a command (optionally chrooted) under ptrace, keep the last 80 syscalls, dump them (and any write(1|2) text, openat paths) to the log when the tracee exits or crashes
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
#include <signal.h>
#include <stdarg.h>
static FILE *lg;
static void L(const char *f, ...) { va_list ap; va_start(ap, f); vfprintf(lg, f, ap); va_end(ap); fputc('\n', lg); fflush(lg); }
static void rstr(pid_t p, unsigned long a, char *o, size_t n) { o[0] = 0; struct iovec l = {o, n - 1}, r = {(void *)a, n - 1}; ssize_t k = process_vm_readv(p, &l, 1, &r, 1, 0); if (k < 0) { strcpy(o, "?"); return; } o[k] = 0; }
#define R 120
static char ring[R][200]; static int cnt;
int main(int argc, char **argv) {
  lg = fopen(argv[1], "w"); const char *root = argv[2]; char **cmd = argv + 3;
  pid_t pid = fork();
  if (!pid) { ptrace(PTRACE_TRACEME, 0, 0, 0); if (strcmp(root, "-") && (chroot(root) || chdir("/"))) { perror("chroot"); _exit(126); } execv(cmd[0], cmd); perror("execv"); _exit(127); }
  int st; waitpid(pid, &st, 0);
  ptrace(PTRACE_SETOPTIONS, pid, 0, PTRACE_O_TRACESYSGOOD | PTRACE_O_EXITKILL);
  int insys = 0; unsigned long cur[4] = {0};
  for (;;) {
    ptrace(PTRACE_SYSCALL, pid, 0, 0);
    if (waitpid(pid, &st, 0) < 0) break;
    if (WIFEXITED(st) || WIFSIGNALED(st)) { L("tracee ended: exited=%d status=%d signaled=%d sig=%d", WIFEXITED(st), WEXITSTATUS(st), WIFSIGNALED(st), WTERMSIG(st)); break; }
    int sig = WSTOPSIG(st);
    if (sig != (SIGTRAP | 0x80)) { if (sig != SIGTRAP) { L("signal %d", sig); ptrace(PTRACE_SYSCALL, pid, 0, sig); } continue; }
    struct { unsigned long long regs[31], sp, pc, pstate; } r; struct iovec io = {&r, sizeof r};
    if (ptrace(PTRACE_GETREGSET, pid, (void *)NT_PRSTATUS, &io)) continue;
    if (!insys) { insys = 1; cur[0] = r.regs[8]; cur[1] = r.regs[0]; cur[2] = r.regs[1]; cur[3] = r.regs[2];
      char s[120] = ""; if (cur[0] == 56 || cur[0] == 48 || cur[0] == 221) rstr(pid, cur[0] == 56 ? cur[2] : cur[1], s, sizeof s);
      if (cur[0] == 64 && (cur[1] == 1 || cur[1] == 2)) { char b[300]; rstr(pid, cur[2], b, cur[3] < 290 ? cur[3] + 1 : 290); for (char *q = b; *q; q++) if (*q == '\n') *q = ' '; L("WRITE fd%lu: %s", cur[1], b); }
      snprintf(ring[cnt++ % R], 200, "nr=%lu a0=%#lx a1=%#lx a2=%#lx %s", cur[0], cur[1], cur[2], cur[3], s);
      if (cur[0] == 94 || cur[0] == 93) { L("EXIT_GROUP/EXIT code=%lu; last syscalls:", cur[1]); int n = cnt < R ? cnt : R; for (int k = n; k > 0; k--) L("  %s", ring[(cnt - k) % R]); }
      if (cur[0] == 56 && (strstr(s, "selinux/load") || strstr(s, "selinux/enforce") || strstr(s, "selinux/disable")) ) { L("reached policy files: %s -> kill", s); kill(pid, SIGKILL); }
    } else { insys = 0; char *e = ring[(cnt - 1) % R]; size_t n = strlen(e); if (n < 150) snprintf(e + n, 50, " = %ld", (long)r.regs[0]); }
  }
  return 0;
}
