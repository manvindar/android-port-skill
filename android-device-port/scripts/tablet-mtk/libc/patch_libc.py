#!/usr/bin/env python3
"""Make bionic's arc4random MADV_WIPEONFORK failure non-fatal (kernel 4.9 has no MADV_WIPEONFORK).
Android 17's libc calls madvise(p, n, 18) while setting up its random state and aborts on -1.
The patch turns the failure branch into a NOP. A forked child then shares the random state (a security weakening, acceptable here).

aarch64 only: bionic's clone3() wrapper (used by the native zygote, zygote_next, to fork app zygotes) calls the clone3 syscall, which kernel 4.9 lacks (ENOSYS).
Without it Chrome's sandboxed renderer cannot start (Android 17 hosts it in a native app zygote), so Chrome loads no page. The patch sends the fork-style case
(stack == 0) to a small stub placed in the unused tail of the last executable page that calls clone(flags | exit_signal, 0, parent_tid, tls, child_tid).
Dropped on purpose: the clone3-only flags (CLONE_PIDFD, CLONE_CLEAR_SIGHAND, CLONE_INTO_CGROUP).
Second problem in the same child: it loops over capabilities 0..38 with prctl(PR_CAPBSET_READ / PR_CAPBSET_DROP) and panics on EINVAL, but kernel 4.9 knows only 0..37.
prctl() is replaced by a stub in the same cave that turns EINVAL for those two options into success, but only for capabilities 38..40 (not in the bounding set, nothing to drop).
Not for every capability: zygote's own C++ loop runs until PR_CAPBSET_READ fails, so a blanket success made system_server loop forever and the boot never finished.
usage: patch_libc.py IN OUT   (auto-detects arm64 / arm32)"""
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
hits = []
if d[4] == 2:  # aarch64
    MOV_W2_18, CMN_W0_1 = 0x52800242, 0x3100041f
    for i in range(0, len(d) - 24, 4):
        if struct.unpack_from('<I', d, i)[0] == MOV_W2_18:
            for j in range(i + 4, i + 20, 4):   # bl madvise, cmn w0,#1, b.eq
                if struct.unpack_from('<I', d, j)[0] == CMN_W0_1:
                    o = struct.unpack_from('<I', d, j + 4)[0]
                    if (o & 0xff00001f) == 0x54000000:   # b.eq
                        hits.append(j + 4)
    for a in hits: struct.pack_into('<I', d, a, 0xd503201f)
else:          # thumb-2
    for i in range(0, len(d) - 12, 2):
        if d[i:i + 2] == b'\x12\x22' and d[i + 6:i + 8] == b'\x01\x30' and d[i + 9] == 0xd0:   # movs r2,#0x12 ; blx ; adds r0,#1 ; beq
            hits.append(i + 8)
    for a in hits: d[a:a + 2] = b'\x00\xbf'
assert len(hits) == 1, hits

def patch_clone3(d):
    """aarch64: mov w0,#435 ; mov x1,x21 ; mov x2,x20 ; bl syscall   ->   nop ; mov x1,x21 ; mov x2,x20 ; bl stub   (stub ends with b syscall)"""
    site = d.find(struct.pack('<3I', 0x52803660, 0xaa1503e1, 0xaa1403e2))
    assert site > 0 and d.find(struct.pack('<3I', 0x52803660, 0xaa1503e1, 0xaa1403e2), site + 1) < 0, 'clone3 site'
    bl = struct.unpack_from('<I', d, site + 12)[0]; assert bl >> 26 == 0x25, 'bl'
    off = bl & 0x3ffffff; off -= (1 << 26) if off >> 25 else 0
    sysc = site + 12 + off * 4                      # address of bionic syscall()
    phoff = struct.unpack_from('<Q', d, 0x20)[0]; ent, num = struct.unpack_from('<HH', d, 0x36)
    for i in range(num):
        t, fl, o, va, pa, fs, ms, al = struct.unpack_from('<IIQQQQQQ', d, phoff + i * ent)
        if t == 1 and fl == 5: end = o + fs; assert o == va and fs == ms and fl == 5
    cave = (end + 3) & ~3
    STUB = [0xf9400029, 0xf940102a, 0xd282000b, 0x8a2b0129, 0x2a0903e9, 0x92401d4a, 0xaa0a0129, 0xf9400824, 0xf9400c2b, 0xf9401c2c, 0xaa0403e5, 0xaa0c03e4, 0xaa0b03e3, 0xaa1f03e2, 0xaa0903e1, 0x52801b80, 0x14000000]
    n = len(STUB) * 4
    page_end = (cave + 0xfff) & ~0xfff
    assert cave + n <= page_end and not any(d[cave:cave + n]), 'no room in the last executable page'
    STUB[-1] = 0x14000000 | (((sysc - (cave + n - 4)) >> 2) & 0x3ffffff)
    for k, w in enumerate(STUB): struct.pack_into('<I', d, cave + 4 * k, w)
    # prctl(): mov x8,#167 ; svc #0 ; cmn x0,#0xfff ; b.hs errno_helper ; ret
    pr = d.find(struct.pack('<4I', 0xd28014e8, 0xd4000001, 0xb13ffc1f, 0) [:12])
    while pr >= 0 and (struct.unpack_from('<I', d, pr + 12)[0] & 0xff00001f) != 0x54000002 or (pr >= 0 and struct.unpack_from('<I', d, pr + 16)[0] != 0xd65f03c0):
        pr = d.find(struct.pack('<3I', 0xd28014e8, 0xd4000001, 0xb13ffc1f), pr + 1)
    assert pr > 0 and d.find(struct.pack('<3I', 0xd28014e8, 0xd4000001, 0xb13ffc1f), pr + 1) < 0, 'prctl'
    bhs = struct.unpack_from('<I', d, pr + 12)[0]; imm = (bhs >> 5) & 0x7ffff; imm -= (1 << 19) if imm >> 18 else 0
    helper = pr + 12 + imm * 4                       # shared "set errno from -x0 and return -1" tail
    c2 = cave + n
    STUB2 = [0xaa0003e9, 0xd28014e8, 0xd4000001, 0xb13ffc1f, 0x54000143, 0xb100581f, 0x54000121, 0x51005d2a, 0x7100055f, 0x540000c8, 0x5100982b, 0x7100097f, 0x54000068, 0xaa1f03e0, 0xd65f03c0, 0]
    n2 = len(STUB2) * 4
    assert c2 + n2 <= page_end and not any(d[c2:c2 + n2]), 'no room for the prctl stub'
    STUB2[-1] = 0x14000000 | (((helper - (c2 + n2 - 4)) >> 2) & 0x3ffffff)
    for k, w in enumerate(STUB2): struct.pack_into('<I', d, c2 + 4 * k, w)
    struct.pack_into('<I', d, pr, 0x14000000 | (((c2 - pr) >> 2) & 0x3ffffff))
    struct.pack_into('<I', d, site, 0xd503201f)
    struct.pack_into('<I', d, site + 12, 0x94000000 | (((cave - (site + 12)) >> 2) & 0x3ffffff))
    return site, cave

if d[4] == 2 and d.find(struct.pack('<3I', 0x52803660, 0xaa1503e1, 0xaa1403e2)) > 0:   # libc.so only; the linkers embed the madvise code but have no clone3
    print('clone3 stub', [hex(x) for x in patch_clone3(d)])
open(sys.argv[2], 'wb').write(d); print('patched', hex(hits[0]), '->', sys.argv[2])
