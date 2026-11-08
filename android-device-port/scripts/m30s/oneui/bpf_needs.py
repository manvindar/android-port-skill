#!/usr/bin/env python3
"""bpf_needs.py KERNEL_TREE OBJ.o ...: which BPF helpers and map types the Android mainline bpf objects use that a kernel tree does not provide.
Helper ids are taken from the tree's include/uapi/linux/bpf.h (FN list order = id), the newest ids from the 5.10 list below. Map types are read from the `maps` section (struct bpf_map_def, first u32)."""
import re, struct, sys
import os
tree = sys.argv[1]
KV = tuple(int(x) for x in os.environ.get('KVER', '4.14').split('.'))   # kernel version the loader believes it runs on (KVER=5.4 shows what a spoof would need)
fn = re.findall(r'FN\((\w+)\)', open(f'{tree}/include/uapi/linux/bpf.h').read().split('#define __BPF_FUNC_MAPPER')[1].split('/* integer value in')[0])
# names for ids the tree lacks come from a newer bpf.h (REFHDR, default $TMPDIR/bpf510.h = linux v5.10 from github)
ref = os.environ.get('REFHDR', os.path.join(os.environ.get('TMPDIR', '/tmp'), 'bpf510.h'))
newfn = re.findall(r'FN\((\w+)\)', open(ref).read().split('#define __BPF_FUNC_MAPPER')[1].split('/* integer value in')[0]) if os.path.exists(ref) else []
NEW = {i: n for i, n in enumerate(newfn)}
MAPTYPES = {0: 'UNSPEC', 1: 'HASH', 2: 'ARRAY', 3: 'PROG_ARRAY', 4: 'PERF_EVENT_ARRAY', 5: 'PERCPU_HASH', 6: 'PERCPU_ARRAY', 7: 'STACK_TRACE', 8: 'CGROUP_ARRAY', 9: 'LRU_HASH', 10: 'LRU_PERCPU_HASH', 11: 'LPM_TRIE',
            12: 'ARRAY_OF_MAPS', 13: 'HASH_OF_MAPS', 14: 'DEVMAP', 15: 'SOCKMAP', 16: 'CPUMAP', 17: 'XSKMAP', 18: 'SOCKHASH', 19: 'CGROUP_STORAGE', 20: 'REUSEPORT_SOCKARRAY', 21: 'PERCPU_CGROUP_STORAGE',
            22: 'QUEUE', 23: 'STACK', 24: 'SK_STORAGE', 25: 'DEVMAP_HASH', 26: 'STRUCT_OPS', 27: 'RINGBUF'}
have_maps = set(re.findall(r'BPF_MAP_TYPE_(\w+)', open(f'{tree}/include/uapi/linux/bpf.h').read().split('enum bpf_map_type')[1].split('};')[0]))
for path in sys.argv[2:]:
    d = open(path, 'rb').read(); assert d[:4] == b'\x7fELF'
    shoff, = struct.unpack_from('<Q', d, 0x28); shentsize, shnum, shstr = struct.unpack_from('<HHH', d, 0x3a)
    sec = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * shentsize) for i in range(shnum)]
    names = d[sec[shstr][4]:sec[shstr][4] + sec[shstr][5]]
    nm = lambda s: names[s[0]:names.index(b'\0', s[0])].decode()
    helpers = {}; maps = {}; secs = {}
    for s_ in sec:
        if s_[2] & 4 and s_[1] == 1:              # SHF_EXECINSTR PROGBITS
            for o in range(s_[4], s_[4] + s_[5], 8):
                op, regs, off, imm = struct.unpack_from('<BBhi', d, o)
                if op == 0x85 and regs >> 4 == 0: helpers.setdefault(imm, set()).add(nm(s_)); secs.setdefault(nm(s_), set()).add(imm)
    print(f'== {path}')
    bad_h = [(i, (fn[i] if i < len(fn) else NEW.get(i, f'id{i}'))) for i in sorted(helpers) if i >= len(fn)]
    name = lambda i: fn[i] if i < len(fn) else NEW.get(i, f'id{i}')
    def minver(n):
        m = re.search(r'\$(?:opt)?(\d+)_(\d+)', n); return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    ok = {n: h for n, h in secs.items() if minver(n) <= KV}
    skip = [n for n in secs if minver(n) > KV]
    print(f' program sections: {len(secs)}; eligible at kernel {KV[0]}.{KV[1]}: {len(ok)}; skipped by the loader (newer kernel only): {len(skip)}')
    for n, h in sorted(ok.items()):
        miss = sorted(i for i in h if i >= len(fn))
        if miss: print(f'  eligible but needs helpers this kernel lacks: {n}: ' + ', '.join(name(i) for i in miss))
    allmiss = sorted({i for h in ok.values() for i in h if i >= len(fn)})
    print(' => helpers to backport for the eligible programs:', ', '.join(name(i) for i in allmiss) or 'none')
