#!/usr/bin/env python3
"""Binary patches that let the Android 17 tethering apex run on kernel 4.9 (apex files are signed, so patched copies are bind-mounted over them).
usage: patch_binaries.py netbpfload IN OUT | netd_updatable IN OUT | service_connectivity IN OUT
The patch sites are per tethering build (the table is chosen by the SHA-256 of the input; an unknown build stops with a message) and each site asserts the kind of instruction it patches.
DP11.261002.005 = tethering 374399999. DP11.261016.003 (new compiler output: `bti c` / `paciasp` at function starts, `cbz` where there was `cmp #1 ; b.eq`): the sites were found by matching
instruction windows between the two builds with immediates masked and hint instructions skipped (a scratch script, see docs/PORTING.md), then checked by hand against the disassembly.
Instruction encodings: NOP 0xd503201f, B imm26 0x14000000."""
import hashlib, struct, sys
NOP = 0xd503201f
def b(a, t): return 0x14000000 | (((t - a) >> 2) & 0x3ffffff)
def patch(d, a, kind, target=None):
    o = struct.unpack_from('<I', d, a)[0]
    if kind == 'nop-any':   # conditional branch / tbz / tbnz / cbz / cbnz
        assert (o >> 24) in (0x34, 0x35, 0x36, 0x37) or (o >> 24) == 0x54, hex(o)
        struct.pack_into('<I', d, a, NOP)
    elif kind == 'to-b':    # tbz/cbz -> unconditional branch to the existing target
        assert (o >> 24) in (0x34, 0x35, 0x36, 0x37), hex(o)
        struct.pack_into('<I', d, a, b(a, target))
# per tool: {sha256 prefix of the input: [(addr, kind, target)]}
NETBPFLOAD = {
  'b2baaffe8458f0b1': [   # DP11.261002.005
    # kernel-version gates (U 4.14, V 4.19, 25Q2 5.4, ...): make the "flag set" branch unconditional-skip
    (0x90c8, 'to-b', 0x9244), (0x9254, 'to-b', 0x9278), (0x928c, 'to-b', 0x92b0),
    (0x92c0, 'to-b', 0x92d8), (0x92e8, 'to-b', 0x9300), (0x9310, 'to-b', 0x9334),
    # sysctl writes that do not exist on 4.9 (bpf_jit_kallsyms ...) must not be fatal
    (0x97a8, 'nop-any'), (0x97c4, 'nop-any'), (0x97d4, 'nop-any'), (0x97e4, 'nop-any'),
    (0x9804, 'nop-any'), (0x9814, 'nop-any'), (0x9824, 'nop-any'), (0x9834, 'nop-any'),
    # "no bpf programs loaded yet" sanity check uses BPF_PROG_GET_NEXT_ID (4.13+)
    (0x9968, 'nop-any'), (0x9970, 'nop-any'), (0x9988, 'nop-any'), (0x9990, 'nop-any'),
    # object file must be on the same device as the binary (the patched copy lives on /system)
    (0xaf4c, 'nop-any'),
  ],
  'ca1b12368362d4f1': [   # DP11.261016.003
    (0x9098, 'to-b', 0x9214), (0x9224, 'to-b', 0x9248), (0x925c, 'to-b', 0x9280),
    (0x9290, 'to-b', 0x92a8), (0x92b8, 'to-b', 0x92d0), (0x92e0, 'to-b', 0x9304),
    (0x9770, 'nop-any'), (0x978c, 'nop-any'), (0x979c, 'nop-any'), (0x97ac, 'nop-any'),
    (0x97c8, 'nop-any'), (0x97d8, 'nop-any'), (0x97e8, 'nop-any'), (0x97f8, 'nop-any'),
    (0x992c, 'nop-any'), (0x9934, 'nop-any'), (0x994c, 'nop-any'), (0x9954, 'nop-any'),
    (0xaf10, 'nop-any'),
  ],
}
NETD_UPDATABLE = {
  'bce8613e979a7950': [   # DP11.261002.005
    (0x9094, 'nop-any'),                 # U gate: kernel < 4.14
    (0x94f8, 'to-b', 0x9600),            # V gate: kernel < 4.19
    (0x9614, 'to-b', 0x998c),            # 25Q2 gate: kernel < 5.4
    (0xaae0, 'nop-any'), (0xb004, 'nop-any'),  # newest-platform flag forces the sockops program (5.15+) to exist
  ],
  '686162d9cdb634f3': [   # DP11.261016.003
    (0x99e4, 'nop-any'), (0x9e48, 'to-b', 0x9f50), (0x9f64, 'to-b', 0xa2d4), (0xc200, 'nop-any'), (0xc718, 'nop-any'),
  ],
}
# libservice-connectivity.so: JNI_OnLoad (ClatCoordinator) verifies owner/mode/SELinux context of the pinned bpf files and abort()s on any mismatch;
# the stock 4.9 kernel labels everything under /sys/fs/bpf as fs_bpf (no per-directory genfs labels). NOP the branch to the abort.
SERVICE_CONNECTIVITY = {
  'a054e5ab609cc198': [(0xbce4, 'nop-any')],   # DP11.261002.005: cmp w8,#1 ; b.eq abort
  '9d6de5cc8419c5f2': [(0xbce0, 'nop-any')],   # DP11.261016.003: cbnz w8,abort
}
def main():
    which, src, dst = sys.argv[1:4]
    d = bytearray(open(src, 'rb').read())
    table = {'netbpfload': NETBPFLOAD, 'netd_updatable': NETD_UPDATABLE, 'service_connectivity': SERVICE_CONNECTIVITY}[which]
    sha = hashlib.sha256(d).hexdigest()[:16]
    if sha not in table: sys.exit(f'{which}: unknown build {sha}; the patch sites have to be ported (docs/PORTING.md)')
    for p in table[sha]:
        patch(d, p[0], p[1], p[2] if len(p) > 2 else None)
    open(dst, 'wb').write(d); print('patched', which, '->', dst)
main()
