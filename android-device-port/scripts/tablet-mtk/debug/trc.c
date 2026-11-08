#define _GNU_SOURCE
// build: python -m ziglang cc -target aarch64-linux-musl -static -O1 trc.c -o trc; run on the tablet as root: trc <pid of zygote_next>
// ptrace a running process tree; keep the last 60 syscalls per pid and dump them to /data/local/tmp/trc.log when a pid gets SIGABRT/SIGSEGV
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
static int kfd;
static void klog(const char *fmt, ...) { char b[700], o[720]; va_list ap; va_start(ap, fmt); vsnprintf(b, sizeof b, fmt, ap); va_end(ap); int m = snprintf(o, sizeof o, "%s\n", b); if (write(kfd, o, m) < 0) {} }
#define R 60
struct ent { unsigned long nr, a0, a1, a2; long ret; };
static struct ent ring[32768][R]; static int cnt[32768], st_[32768]; static unsigned long cur[32768][4];
int main(int argc, char **argv) {
  kfd = open("/data/local/tmp/trc.log", O_WRONLY|O_CREAT|O_APPEND, 0644); pid_t target = atoi(argv[1]);
  if (ptrace(PTRACE_SEIZE, target, 0, PTRACE_O_TRACESYSGOOD | PTRACE_O_TRACEFORK | PTRACE_O_TRACECLONE | PTRACE_O_TRACEVFORK) < 0) { klog("seize failed %d", errno); return 1; }
  klog("seized %d", target);
  int st;
  for (;;) {
    pid_t w = waitpid(-1, &st, __WALL); if (w < 0) break;
    int i = w & 0x7fff;
    if (WIFEXITED(st) || WIFSIGNALED(st)) { continue; }
    if (!WIFSTOPPED(st)) continue;
    int sig = WSTOPSIG(st); int ev = st >> 16;
    if (ev) { if (ev == PTRACE_EVENT_FORK || ev == PTRACE_EVENT_CLONE || ev == PTRACE_EVENT_VFORK) { unsigned long np; ptrace(PTRACE_GETEVENTMSG, w, 0, &np); klog("pid %d forked %lu", w, np); } ptrace(PTRACE_SYSCALL, w, 0, 0); continue; }
    if (sig == (SIGTRAP | 0x80)) {
      struct { unsigned long long regs[31], sp, pc, pstate; } r; struct iovec io = {&r, sizeof r};
      if (ptrace(PTRACE_GETREGSET, w, (void *)NT_PRSTATUS, &io) == 0) {
        if (!st_[i]) { st_[i] = 1; cur[i][0] = r.regs[8]; cur[i][1] = r.regs[0]; cur[i][2] = r.regs[1]; cur[i][3] = r.regs[2];
          if (r.regs[8] == 64 && (r.regs[0] == 1 || r.regs[0] == 2) && r.regs[2] < 400) { char b[420]; struct iovec l = {b, r.regs[2]}, rr = {(void *)r.regs[1], r.regs[2]}; ssize_t k = process_vm_readv(w, &l, 1, &rr, 1, 0); if (k > 0) { b[k] = 0; for (int q = 0; q < k; q++) if (b[q] == '\n') b[q] = ' '; klog("pid %d write(fd %lu): %s", w, (unsigned long)r.regs[0], b); } } }
        else { st_[i] = 0; struct ent *e = &ring[i][cnt[i]++ % R]; e->nr = cur[i][0]; e->a0 = cur[i][1]; e->a1 = cur[i][2]; e->a2 = cur[i][3]; e->ret = (long)r.regs[0]; }
      }
      ptrace(PTRACE_SYSCALL, w, 0, 0); continue;
    }
    if (sig == SIGABRT || sig == SIGSEGV || sig == SIGBUS || sig == SIGILL) {
      klog("pid %d got signal %d after %d syscalls (in syscall=%d nr=%lu)", w, sig, cnt[i], st_[i], cur[i][0]);
      int n = cnt[i] < R ? cnt[i] : R;
      for (int k = n; k > 0; k--) { struct ent *e = &ring[i][(cnt[i] - k) % R]; klog("  nr=%lu a0=%#lx a1=%#lx a2=%#lx ret=%ld", e->nr, e->a0, e->a1, e->a2, e->ret); }
      ptrace(PTRACE_SYSCALL, w, 0, sig); continue;
    }
    if (sig == SIGTRAP || sig == SIGSTOP || sig == SIGTRAP) { ptrace(PTRACE_SYSCALL, w, 0, 0); continue; }
    ptrace(PTRACE_SYSCALL, w, 0, sig);
  }
  return 0;
}
