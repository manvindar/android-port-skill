#!/usr/bin/env python3
"""patch_netbpfload.py IN OUT [MESSAGE_PREFIX ...]: make Android's mainline netbpfload (tethering apex, aarch64) run on kernel 4.14.
The loader refuses old kernels with fatal messages ("Android V requires kernel 4.19.", "Android 25Q2 requires kernel 5.4.", "Android 26Q3 requires kernel 5.15.", "Android 25Q4 requires kernel 5.10.", "Android V+ only supports LTS kernels.",
"Android V+ requires %d.%d kernel to be %d.%d.%d+."). Each message is printed after `cmp ; b.cc skip ; ldrb ; cbz/tbz skip ; adrp x1,tag ; add ; adrp x2,msg ; add x2,...`.
This finds every reference to those strings (adrp+add, no per-build offsets) and turns the nearest conditional branch before the message that skips it into an unconditional branch.
Program selection by kernel version stays on the real uname (4.14), so only the programs that suit 4.14 are loaded (docs/oneui9/M2-GAPS.md, tools/oneui/bpf_needs.py)."""
import os, struct, sys
WINDOW, MIN = int(os.environ.get('WINDOW', 16)), int(os.environ.get('MIN', 4))   # libnetd_updatable builds its message strings 40+ instructions after the guard: WINDOW=96 MIN=2
MSGS = [b'Android U requires kernel', b'Android V requires kernel', b'Android 25Q2 requires kernel', b'Android 26Q3 requires kernel', b'Android 25Q4 requires kernel', b'Android V+ only supports LTS', b'Android V+ requires %d.%d kernel to be']
if len(sys.argv) > 3: MSGS = [m.encode() for m in sys.argv[3:]]      # libnetd_updatable.so: WINDOW=96 MIN=2 ... 'V+ platform with kernel version <' '25Q2+ platform with kernel version <'
d = bytearray(open(sys.argv[1], 'rb').read())
phoff, = struct.unpack_from('<Q', d, 0x20); phentsize, phnum = struct.unpack_from('<HH', d, 0x36)
loads = [(p[3], p[2], p[5]) for p in (struct.unpack_from('<IIQQQQQQ', d, phoff + i * phentsize) for i in range(phnum)) if p[0] == 1]   # (vaddr, offset, filesz) PT_LOAD
exec_seg = [(va, fo, sz) for (va, fo, sz), p in zip(loads, [struct.unpack_from('<IIQQQQQQ', d, phoff + i * phentsize) for i in range(phnum) if struct.unpack_from('<I', d, phoff + i * phentsize)[0] == 1]) if p[1] & 1]
def off2va(o): return next(va + (o - fo) for va, fo, sz in loads if fo <= o < fo + sz)
def sx(v, bits): return v - (1 << bits) if v >> (bits - 1) else v
def cond_target(w, a):
    """target of a conditional branch word at address a, or None"""
    if w & 0xff000010 == 0x54000000: return a + 4 * sx((w >> 5) & 0x7ffff, 19)          # b.cond
    if w & 0x7e000000 == 0x34000000: return a + 4 * sx((w >> 5) & 0x7ffff, 19)          # cbz / cbnz
    if w & 0x7e000000 == 0x36000000: return a + 4 * sx((w >> 5) & 0x3fff, 14)           # tbz / tbnz
    return None
code_va, code_off, code_sz = exec_seg[0]
words = struct.unpack_from('<%dI' % (code_sz // 4), d, code_off)
adrp = {}                                                                                  # string address -> [index of the adrp that builds it]
for k in range(len(words) - 1):
    w, n = words[k], words[k + 1]
    if w & 0x9f000000 == 0x90000000 and n & 0xffc00000 == 0x91000000 and (n >> 5) & 31 == w & 31 and n & 31 == w & 31:
        a = code_va + 4 * k; imm = (((w >> 29) & 3) | (((w >> 5) & 0x7ffff) << 2)); imm = sx(imm, 21)
        tgt = ((a & ~0xfff) + (imm << 12)) + ((n >> 10) & 0xfff); adrp.setdefault(tgt, []).append(k)
done = 0
for m in MSGS:
    pos = 0
    while (i := bytes(d).find(m, pos)) >= 0:
        pos = i + 1; sva = off2va(i)
        for k in adrp.get(sva, []):
            # block start: the `adrp x1 (tag)` two instructions before the message's adrp; search back for the guard branch
            for j in range(k - 1, k - WINDOW, -1):
                a = code_va + 4 * j; t = cond_target(words[j], a)
                if t is not None and t > code_va + 4 * (k + 2):
                    struct.pack_into('<I', d, code_off + 4 * j, 0x14000000 | (((t - a) >> 2) & 0x3ffffff))
                    print(f'  {m.decode()}: {a:#x} {words[j]:#010x} -> b {t:#x}'); done += 1; break
            else: sys.exit(f'no guard branch found before {m!r} at {code_va + 4 * k:#x}')
# netbpfload (2026Q2+) aborts "file %s is on device %llu, while we are on device %llu" when the .o files (apex loop device) are not on the device of /proc/self/exe; a bind-mounted
# patched copy lives on /system, so that check must go. The message block is jumped TO (out of line): turn every branch that targets its first instruction (3 instructions before the message adrp) into a nop.
for i in ([bytes(d).find(b'is on device %llu')] if bytes(d).find(b'is on device %llu') >= 0 else []):
    i = bytes(d).rfind(b'\0', 0, i) + 1
    for k in adrp.get(off2va(i), []):
        blk = code_va + 4 * (k - 3)
        for j in range(len(words)):
            if cond_target(words[j], code_va + 4 * j) == blk:
                struct.pack_into('<I', d, code_off + 4 * j, 0xd503201f); print(f'  device check: {code_va + 4 * j:#x} {words[j]:#010x} -> nop'); done += 1
# Program/map variants carry an api window (egress_stats for 4.14 is only [3300,3500) = Android U/V; the 4.19+ ones need a newer kernel), and netd aborts without prog_netd_egress_stats.
# At the "skipping prog %s: api %d is outside ..." site the api level is loaded `ldr w4,[x8,#imm]` just before the range test: make it a constant inside the 4.14 window (kernel-version ranges still pick the variant).
API_FAKE = int(os.environ.get('API_FAKE', 3499))
for m in (b'skipping prog %s: api %d',):      # programs only: maps keep the real api level (the 25Q2+ local_net_* maps must exist, netd/NetworkStats open them)
    i = bytes(d).find(m)
    if i < 0: continue
    for k in adrp.get(off2va(i), []):
        for j in range(k - 1, k - 20, -1):
            if words[j] & 0xffc003ff == 0xb9400104:       # ldr w4,[x8,#imm] (x8 = adrp of the globals)
                struct.pack_into('<I', d, code_off + 4 * j, 0x52800004 | (API_FAKE << 5)); print(f'  api window: {code_va + 4 * j:#x} -> mov w4,#{API_FAKE}'); done += 1; break
        else: sys.exit(f'no api load before {m!r}')
# LPM_TRIE maps: kernels before 4.20 cannot BPF_MAP_GET_NEXT_KEY an LPM trie (ENOTSUPP, errno 524), and system_server's BpfMap.clear()/forEach on local_net_access_map dies with it. The loader has a
# `cmp w4,w28 ; b.hi ok ; cmp w1,#0xb(LPM_TRIE) ; b.ne ok ; log "skipping unsupported map type" ; skip` guard and a `set_type` call after `ok`: always create LPM maps as HASH (the 4.14 programs that need real LPM semantics are skipped anyway).
i = bytes(d).find(b'skipping unsupported map type(%d)')
if i >= 0:
    for k in adrp.get(off2va(i), []):
        b0 = k - 3                                           # first instruction of the skip block (ldr w8,[x24,#0xbc])
        if words[b0 - 2] != 0x71002c3f: print(f'  LPM guard: site {code_va + 4 * k:#x} is not a `cmp w1,#0xb` guard, left alone'); continue
        okt = cond_target(words[b0 - 1], code_va + 4 * (b0 - 1)); assert okt
        j = next(x for x in range(b0, b0 + 200) if code_va + 4 * x >= okt and words[x] == 0x52800021)      # mov w1,#1 (the HASH constant of the existing type rewrite)
        tgt = code_va + 4 * (j + 1)
        struct.pack_into('<I', d, code_off + 4 * (b0 - 3), 0xd503201f)                                  # nop the kernel-version `b.hi ok`
        struct.pack_into('<I', d, code_off + 4 * b0, 0x52800021)                                        # mov w1,#1
        struct.pack_into('<I', d, code_off + 4 * (b0 + 1), 0x14000000 | (((tgt - (code_va + 4 * (b0 + 1))) >> 2) & 0x3ffffff))
        print(f'  LPM_TRIE -> HASH: block {code_va + 4 * b0:#x}, set_type at {tgt:#x}'); done += 1
assert done >= MIN, f'only {done} gates patched: not a netbpfload this tool knows'
open(sys.argv[2], 'wb').write(d); print('patched', done, 'gates ->', sys.argv[2])
