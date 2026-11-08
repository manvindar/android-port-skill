// Static arm64 kernel capability probe for the M30s (kernel 4.14). Read-only: no setting changes,
// no files written. Each test prints "name: present|absent|n/a (detail)".
// Build: tools/probe/build.sh   Run: adb -s <serial> shell /data/local/tmp/kprobe
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/bpf.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <unistd.h>

#ifndef F_ADD_SEALS
#define F_ADD_SEALS 1033
#endif
#define SEAL_SEAL 0x1
#define SEAL_SHRINK 0x2
#define SEAL_GROW 0x4
#define SEAL_WRITE 0x8
#define SEAL_FUTURE_WRITE 0x10

// ENOSYS = syscall absent; any other errno = the kernel knows it (we pass invalid args on purpose).
static void sc(const char *name, long nr, long a, long b, long c, long d) {
  errno = 0;
  long r = syscall(nr, a, b, c, d, 0, 0);
  int e = errno;
  printf("syscall %-16s nr=%-3ld %s (ret=%ld errno=%d %s)\n", name, nr,
         (r < 0 && e == ENOSYS) ? "ABSENT" : "present", r, e, e ? strerror(e) : "");
}

static int bpf_load(int type, struct bpf_insn *p, int n, char *log, size_t logsz) {
  union bpf_attr at;
  memset(&at, 0, sizeof at);
  at.prog_type = type;
  at.insn_cnt = n;
  at.insns = (unsigned long)p;
  at.license = (unsigned long)"GPL";
  at.log_level = 1;
  at.log_size = logsz;
  at.log_buf = (unsigned long)log;
  log[0] = 0;
  return syscall(__NR_bpf, BPF_PROG_LOAD, &at, sizeof at);
}

#define I(c, d, s, o, i) ((struct bpf_insn){.code = c, .dst_reg = d, .src_reg = s, .off = o, .imm = i})
static void bpf_try(const char *name, int atomic_op, int size_flag) {
  char log[4096];
  struct bpf_insn p[] = {
      I(0xb7, 0, 0, 0, 0),                      // r0 = 0
      I(0x62, 10, 0, -8, 0),                    // *(u32 *)(r10-8) = 0   (init stack)
      I(0x62, 10, 0, -4, 0),
      I(0xb7, 1, 0, 0, 1),                      // r1 = 1
      I(0xc3 | size_flag, 10, 1, -8, atomic_op),// atomic (xadd / fetch-add) on stack slot
      I(0x95, 0, 0, 0, 0),                      // exit
  };
  int fd = bpf_load(BPF_PROG_TYPE_SOCKET_FILTER, p, 6, log, sizeof log);
  int e = errno;
  printf("bpf %-26s %s (fd/ret=%d errno=%d %s)\n", name, fd >= 0 ? "LOADS" : "REJECTED", fd, e,
         fd >= 0 ? "" : strerror(e));
  if (fd < 0 && log[0]) printf("  verifier: %.200s\n", log);
  if (fd >= 0) close(fd);
}

static void cat(const char *path, int maxlines) {
  FILE *f = fopen(path, "r");
  if (!f) { printf("%s: cannot open (%s)\n", path, strerror(errno)); return; }
  char l[512]; int n = 0;
  printf("--- %s\n", path);
  while (fgets(l, sizeof l, f) && n++ < maxlines) fputs(l, stdout);
  fclose(f);
}

int main(void) {
  struct utsname u; uname(&u);
  printf("kernel %s %s %s\n", u.sysname, u.release, u.machine);

  // 1. memfd + F_SEAL_FUTURE_WRITE (Android 16 libhwui seals bitmaps with it)
  int fd = syscall(__NR_memfd_create, "kprobe", 1 /*MFD_CLOEXEC*/);
  if (fd < 0) printf("memfd_create: FAILED errno=%d %s\n", errno, strerror(errno));
  else {
    ftruncate(fd, 4096);
    errno = 0; int r = fcntl(fd, F_ADD_SEALS, SEAL_FUTURE_WRITE);
    printf("F_SEAL_FUTURE_WRITE: %s (ret=%d errno=%d %s)\n", r == 0 ? "present" : "ABSENT", r, errno, errno ? strerror(errno) : "");
    errno = 0; r = fcntl(fd, F_ADD_SEALS, SEAL_SHRINK | SEAL_GROW | SEAL_SEAL);
    printf("F_SEAL_{SHRINK,GROW,SEAL}: ret=%d errno=%d\n", r, errno);
    close(fd);
  }

  // 2. syscalls newer than 4.14 (invalid args on purpose, harmless)
  sc("pidfd_send_signal", 424, -1, 0, 0, 0);
  sc("io_uring_setup", 425, 0, 0, 0, 0);
  sc("pidfd_open", 434, -1, 0, 0, 0);
  sc("clone3", 435, 0, 0, 0, 0);
  sc("close_range", 436, 5, 3, 0, 0);  // first>last => EINVAL, closes nothing
  sc("openat2", 437, -1, 0, 0, 0);
  sc("pidfd_getfd", 438, -1, -1, 0, 0);
  sc("faccessat2", 439, -100, 0, 0, 0);
  sc("process_madvise", 440, -1, 0, 0, 0);
  sc("epoll_pwait2", 441, -1, 0, 0, 0);
  sc("userfaultfd", 282, 0x7fffffff, 0, 0, 0);
  sc("membarrier", 283, 0, 0, 0, 0);
  sc("statx", 291, -100, 0, 0, 0);
  sc("rseq", 293, 0, 0, 0, 0);

  // 3. BPF: baseline then the 4.14-incompatible instruction forms
  { char log[4096]; struct bpf_insn p[] = {I(0xb7, 0, 0, 0, 0), I(0x95, 0, 0, 0, 0)};
    int f = bpf_load(BPF_PROG_TYPE_SOCKET_FILTER, p, 2, log, sizeof log); int e = errno;
    printf("bpf baseline (mov r0,0;exit) %s (ret=%d errno=%d %s)\n", f >= 0 ? "LOADS" : "REJECTED", f, e, f < 0 ? strerror(e) : "");
    if (f >= 0) close(f); }
  bpf_try("xadd32 (imm=0)", 0x00, 0x00);
  bpf_try("xadd64 (imm=0)", 0x00, 0x18);
  bpf_try("atomic fetch-add32", 0x01, 0x00);
  bpf_try("atomic fetch-add64", 0x01, 0x18);
  { union bpf_attr a; memset(&a, 0, sizeof a);
    a.map_type = BPF_MAP_TYPE_ARRAY; a.key_size = 4; a.value_size = 8; a.max_entries = 1;
    int m = syscall(__NR_bpf, BPF_MAP_CREATE, &a, sizeof a); int e = errno;
    printf("bpf map_create array %s (ret=%d errno=%d)\n", m >= 0 ? "ok" : "FAIL", m, e); if (m >= 0) close(m);
    memset(&a, 0, sizeof a); a.map_type = BPF_MAP_TYPE_RINGBUF; a.max_entries = 4096;
    m = syscall(__NR_bpf, BPF_MAP_CREATE, &a, sizeof a); e = errno;
    printf("bpf map_type RINGBUF %s (errno=%d)\n", m >= 0 ? "ok" : "ABSENT/FAIL", e); if (m >= 0) close(m); }

  // 4. binder protocol version (Android 12+ needs 8)
  const char *bn[] = {"/dev/binder", "/dev/hwbinder", "/dev/vndbinder"};
  for (int i = 0; i < 3; i++) {
    int b = open(bn[i], O_RDWR | O_CLOEXEC);
    if (b < 0) { printf("%s: open failed (%s)\n", bn[i], strerror(errno)); continue; }
    struct { int v; } ver = {0};
    int r = ioctl(b, _IOWR('b', 9, int), &ver);
    printf("%s: BINDER_VERSION ret=%d protocol=%d\n", bn[i], r, ver.v);
    close(b);
  }

  // 5. PSI, cgroups, memory, filesystems, misc nodes
  struct stat st;
  printf("/proc/pressure: %s\n", stat("/proc/pressure", &st) == 0 ? "PRESENT" : "absent");
  const char *nodes[] = {"/proc/pressure/memory", "/dev/memcg", "/sys/fs/cgroup", "/dev/cpuctl", "/dev/cpuset", "/dev/stune",
      "/sys/fs/bpf", "/dev/ashmem", "/dev/binderfs", "/dev/fuse", "/sys/module/lowmemorykiller", "/sys/module/lowmemorykiller/parameters/minfree",
      "/sys/kernel/memory_state_time", "/sys/fs/f2fs", "/dev/uinput", "/dev/ion", "/dev/dma_heap", "/proc/sys/kernel/sched_rt_runtime_us"};
  for (unsigned i = 0; i < sizeof nodes / sizeof *nodes; i++)
    printf("%-52s %s\n", nodes[i], stat(nodes[i], &st) == 0 ? "exists" : "absent");
  cat("/proc/sys/kernel/unprivileged_bpf_disabled", 1);
  cat("/proc/sys/kernel/perf_event_paranoid", 1);
  cat("/proc/filesystems", 60);
  cat("/proc/cgroups", 30);
  cat("/proc/mounts", 80);
  cat("/proc/meminfo", 8);
  cat("/proc/sys/vm/overcommit_memory", 1);
  cat("/sys/fs/selinux/enforce", 1);
  cat("/sys/fs/selinux/policyvers", 1);
  return 0;
}
