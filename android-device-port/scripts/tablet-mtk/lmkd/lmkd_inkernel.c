/* Replacement for /system/bin/lmkd on the 4.9 stock kernel. The Android 17 lmkd only supports PSI/memcg (this kernel has neither);
 * the old in-kernel lowmemorykiller is still there and only needs minfree/adj and /proc/<pid>/oom_score_adj, which AMS sends through
 * the lmkd socket. Replies follow system/memory/lmkd/include/lmkd.h; unknown commands are ignored. */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

enum { TARGET, PROCPRIO, PROCREMOVE, PROCPURGE, GETKILLCNT, SUBSCRIBE, PROCKILL, UPDATE_PROPS, STAT_KILL, START_MON, BOOT_DONE, PROCS_PRIO };
#define MAXC 32

static void wfile(const char* p, const char* s) {
    int fd = open(p, O_WRONLY | O_CLOEXEC);
    if (fd < 0) return;
    if (write(fd, s, strlen(s)) < 0) {}
    close(fd);
}

static void setadj(int pid, int adj) {
    char p[48], v[16];
    snprintf(p, sizeof p, "/proc/%d/oom_score_adj", pid);
    snprintf(v, sizeof v, "%d", adj);
    wfile(p, v);
}

static void reply(int fd, int cmd, int val) {
    int r[2] = {htonl(cmd), htonl(val)};
    if (send(fd, r, sizeof r, MSG_NOSIGNAL) < 0) {}
}

static void handle(int fd, int* b, int len) {
    if (len < 4) return;
    int cmd = ntohl(b[0]), n = len / 4 - 1;
    switch (cmd) {
    case TARGET: {
        char mf[128] = "", ad[128] = "";
        for (int i = 0; i + 1 < n; i += 2) {
            char t[16];
            snprintf(t, sizeof t, "%s%d", i ? "," : "", (int)ntohl(b[1 + i]));
            strcat(mf, t);
            snprintf(t, sizeof t, "%s%d", i ? "," : "", (int)ntohl(b[2 + i]));
            strcat(ad, t);
        }
        wfile("/sys/module/lowmemorykiller/parameters/minfree", mf);
        wfile("/sys/module/lowmemorykiller/parameters/adj", ad);
        break;
    }
    case PROCPRIO:
        if (n >= 3) setadj(ntohl(b[1]), ntohl(b[3]));
        break;
    case PROCS_PRIO:
        for (int i = 0; i + 3 < n; i += 4) setadj(ntohl(b[1 + i]), ntohl(b[3 + i]));
        break;
    case GETKILLCNT: reply(fd, cmd, 0); break;
    case UPDATE_PROPS: reply(fd, cmd, 0); break;
    case BOOT_DONE: reply(fd, cmd, 0); break;
    }
}

int main(int argc, char** argv) {
    if (argc > 1) return 0; /* --reinit / --boot_completed helpers */
    const char* e = getenv("ANDROID_SOCKET_lmkd");
    if (!e) return 1;
    int ls = atoi(e);
    listen(ls, 8);
    struct pollfd p[MAXC + 1];
    int nc = 0, cs[MAXC];
    int buf[1024];
    for (;;) {
        p[0] = (struct pollfd){ls, POLLIN, 0};
        for (int i = 0; i < nc; i++) p[i + 1] = (struct pollfd){cs[i], POLLIN, 0};
        if (poll(p, nc + 1, -1) < 0) { if (errno == EINTR) continue; return 1; }
        if (p[0].revents & POLLIN) {
            int c = accept4(ls, NULL, NULL, SOCK_CLOEXEC);
            if (c >= 0) { if (nc < MAXC) cs[nc++] = c; else close(c); }
        }
        for (int i = nc - 1; i >= 0; i--) {
            if (!(p[i + 1].revents & (POLLIN | POLLHUP | POLLERR))) continue;
            int len = recv(cs[i], buf, sizeof buf, 0);
            if (len <= 0) { close(cs[i]); cs[i] = cs[--nc]; continue; }
            handle(cs[i], buf, len);
        }
    }
}
