#!/usr/bin/env python3
"""netd (Android 17): the hotspot turned itself off a second after it started.
netd starts dnsmasq with posix_spawn and the flags POSIX_SPAWN_USEVFORK|POSIX_SPAWN_CLOEXEC_DEFAULT (0x140). With CLOEXEC_DEFAULT bionic's child calls
close_range(3, ~0, CLOSE_RANGE_CLOEXEC), which kernel 4.9 does not have (ENOSYS), and the child does _exit(127) before the exec. netd keeps a pipe to a dnsmasq that is not there,
so `tetherDnsSet` fails with EREMOTEIO (121) and Tethering shuts the hotspot down.
Fix: `mov w1,#0x140` before the call to posix_spawnattr_setflags becomes `mov w1,#0x40` (netd's own descriptors are O_CLOEXEC already).
usage: patch_netd_spawn.py IN OUT"""
import struct, sys
from elftools.elf.elffile import ELFFile
d = bytearray(open(sys.argv[1], 'rb').read()); e = ELFFile(open(sys.argv[1], 'rb'))
dynsym = e.get_section_by_name('.dynsym'); got = [r['r_offset'] for r in e.get_section_by_name('.rela.plt').iter_relocations() if dynsym.get_symbol(r['r_info_sym']).name == 'posix_spawnattr_setflags']
assert len(got) == 1
plt = e.get_section_by_name('.plt'); w = struct.unpack_from('<%dI' % (plt['sh_size'] // 4), d, plt['sh_offset']); stub = None
for i in range(len(w) - 1):                                   # adrp x16,page ; ldr x17,[x16,#off]
    if (w[i] & 0x9f00001f) == 0x90000010 and (w[i + 1] & 0xffc003ff) == 0xf9400211:
        a = plt['sh_addr'] + i * 4; imm = ((w[i] >> 29) & 3) | (((w[i] >> 5) & 0x7ffff) << 2)
        if (a & ~0xfff) + (imm << 12) + ((w[i + 1] >> 10) & 0xfff) * 8 == got[0]: stub = a
assert stub
text = e.get_section_by_name('.text'); hits = []
for off in range(text['sh_offset'], text['sh_offset'] + text['sh_size'], 4):
    ins = struct.unpack_from('<I', d, off)[0]
    if (ins & 0xfc000000) == 0x94000000:                      # bl
        t = off - text['sh_offset'] + text['sh_addr'] + (((ins & 0x3ffffff) ^ 0x2000000) - 0x2000000) * 4
        if t == stub: hits.append(off)
assert len(hits) == 1, hits
prev = hits[0] - 4
assert struct.unpack_from('<I', d, prev)[0] == 0x52802801, 'expected mov w1,#0x140'
struct.pack_into('<I', d, prev, 0x52800801)
open(sys.argv[2], 'wb').write(d); print('netd: posix_spawn flags 0x140 -> 0x40 at', hex(prev))
