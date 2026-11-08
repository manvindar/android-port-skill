#define _GNU_SOURCE
// tiny strace for the A17 bpfloader experiment: runs argv[1..] under ptrace, logs bpf() calls and failing syscalls to /dev/kmsg
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
#include <sys/types.h>
#include <stdarg.h>
#include <signal.h>
static int kfd = -1;
static void klog(const char *fmt, ...) {
  char b[400]; va_list ap; __builtin_va_start(ap, fmt);
  int n = vsnprintf(b, sizeof b - 8, fmt, ap); __builtin_va_end(ap);
  char o[420]; int m = snprintf(o, sizeof o, "<6>strace: %s\n", b); if (kfd >= 0) { if (write(kfd, o, m) < 0) {} }
}
// everything the loader writes to /dev/kmsg is also appended to a file: the kernel rate-limits a process's kmsg writes (310 lines became 14), which hides why it fails
static void F(const char *f, ...) { int fd = open("/dev/bpftrace.log", O_WRONLY | O_CREAT | O_APPEND, 0666); if (fd < 0) return; char b[700]; va_list ap; va_start(ap, f); int n = vsnprintf(b, sizeof b - 1, f, ap); va_end(ap); b[n++] = '\n'; if (write(fd, b, n) < 0) {} close(fd); }
static int peek(pid_t p, unsigned long addr, void *buf, size_t len) {
  struct iovec l = {buf, len}, r = {(void *)addr, len};
  return process_vm_readv(p, &l, 1, &r, 1, 0) == (ssize_t)len ? 0 : -1;
}
static void rstr(pid_t p, unsigned long addr, char *out, size_t n) {
  out[0] = 0; if (!addr) return; struct iovec l = {out, n - 1}, r = {(void *)addr, n - 1};
  ssize_t k = process_vm_readv(p, &l, 1, &r, 1, 0); if (k < 0) { out[0] = '?'; out[1] = 0; return; } out[k] = 0;
}
int main(int argc, char **argv) {
  kfd = open("/dev/kmsg", O_WRONLY);
  pid_t pid = fork();
  if (pid == 0) { ptrace(PTRACE_TRACEME, 0, 0, 0); static char *def[] = {"/system/bin/netbpfload.a17", 0}; if (argc > 1) execv(argv[1], argv + 1); else execv(def[0], def); _exit(127); }
  int st, status = 0; long n = 0;
  waitpid(pid, &st, 0);
  ptrace(PTRACE_SETOPTIONS, pid, 0, PTRACE_O_TRACESYSGOOD | PTRACE_O_TRACEFORK | PTRACE_O_TRACECLONE);
  ptrace(PTRACE_SYSCALL, pid, 0, 0);
  for (;;) {
    pid_t w = waitpid(-1, &st, __WALL);
    if (w < 0) break;
    if (WIFEXITED(st) || WIFSIGNALED(st)) {
      if (w == pid) { status = WIFEXITED(st) ? WEXITSTATUS(st) : 128 + WTERMSIG(st); klog("exit pid=%d status=%d (raw %#x)", w, status, st); F("EXIT pid=%d status=%d", w, status); break; }
      continue;
    }
    if (!WIFSTOPPED(st)) continue;
    int sig = WSTOPSIG(st);
    if (sig != (SIGTRAP | 0x80)) { int inj = 0; if (sig != SIGTRAP && sig != SIGSTOP) { klog("pid=%d signal %d", w, sig); inj = sig; } if ((st >> 16) == PTRACE_EVENT_FORK || (st >> 16) == PTRACE_EVENT_CLONE) {} ptrace(PTRACE_SYSCALL, w, 0, inj); continue; }
    struct { unsigned long long regs[31], sp, pc, pstate; } regs; struct iovec io = {&regs, sizeof regs};
    if (ptrace(PTRACE_GETREGSET, w, (void *)NT_PRSTATUS, &io) < 0) { ptrace(PTRACE_SYSCALL, w, 0, 0); continue; }
    static unsigned long pend[65536]; static int pstate[65536];
    int idx = w & 0xffff;
    if (!pstate[idx]) { // syscall entry
      pstate[idx] = 1; pend[idx] = regs.regs[8];
      if (regs.regs[8] == 64 && regs.regs[0] > 2) { char b[500]; rstr(w, regs.regs[1], b, regs.regs[2] < 490 ? regs.regs[2] + 1 : 490); for (char *q = b; *q; q++) if (*q == '\n') *q = ' '; F("%d WRITE: %s", (int)w, b); }
      if (regs.regs[8] == 280) {
        unsigned w32[16] = {0}; peek(w, regs.regs[1], w32, sizeof w32 < regs.regs[2] ? sizeof w32 : regs.regs[2]);
        if (regs.regs[0] == 0) klog("bpf(MAP_CREATE) type=%u ks=%u vs=%u max=%u flags=%#x inner=%u numa=%u name=%.16s ifindex=%u btf_fd=%d key_id=%u val_id=%u", w32[0], w32[1], w32[2], w32[3], w32[4], w32[5], w32[6], (char *)&w32[7], w32[11], (int)w32[12], w32[13], w32[14]);
        else if (regs.regs[0] == 5) klog("bpf(PROG_LOAD) type=%u insn_cnt=%u size=%lu", w32[0], w32[1], regs.regs[2]);
        else klog("bpf(cmd=%lu) size=%lu a0=%u a1=%u a2=%u", regs.regs[0], regs.regs[2], w32[0], w32[1], w32[2]);
      } else if (regs.regs[8] == 221) {
        char p[160], a0[96] = "", a1[64] = "", a2[64] = ""; rstr(w, regs.regs[0], p, sizeof p);
        unsigned long av[3] = {0, 0, 0}; peek(w, regs.regs[1], av, 24); rstr(w, av[0], a0, sizeof a0); rstr(w, av[1], a1, sizeof a1); rstr(w, av[2], a2, sizeof a2);
        klog("execve(x0=%#llx '%s', argv=['%s','%s','%s'])", regs.regs[0], p, a0, a1, a2);
      }
    } else {
      pstate[idx] = 0; long ret = (long)regs.regs[0];
      unsigned long nr = pend[idx];
      if (nr == 280) { klog("  -> bpf ret=%ld", ret); if (ret < 0) F("  -> bpf ret=%ld", ret); }
      else if (ret < 0 && ret > -4096 && n < 400 && nr != 56 /*openat*/ ) { klog("syscall %lu ret=%ld", nr, ret); n++; F("syscall %lu ret=%ld", nr, ret); }
      else if (ret < 0 && ret > -4096 && n < 400 && nr == 56) { klog("openat ret=%ld", ret); n++; }
      else if (nr == 221 /*execve*/) {}
    }
    ptrace(PTRACE_SYSCALL, w, 0, 0);
  }
  if (status == 0) { // the platform bpfloader's final "netbpfload done" re-exec fails here; do what it would have done
    pid_t c = fork();
    if (c == 0) { execl("/system/bin/setprop", "setprop", "bpf.progs_loaded", "1", (char *)0); _exit(127); }
    waitpid(c, &st, 0); klog("setprop bpf.progs_loaded 1 -> %d", WIFEXITED(st) ? WEXITSTATUS(st) : -1);
  }
  return status;
}
