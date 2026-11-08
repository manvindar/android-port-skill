#!/usr/bin/env python3
"""patch_lsc_ringbuf.py IN OUT: libservice-connectivity.so (tethering apex) for a kernel without BPF ringbuf (4.14).
ConnectivityService -> LocalNetEventListener (and LoopbackEventHandler) -> nativeGetLocalNetAccessRingbufFd() calls BpfRingbuf::Create on map_netd_local_net_note_op_ringbuf (not loaded here: kernel < 5.8),
and LocalNetEventHandler::GetRingbuf() aborts system_server when it fails. The JNI function is found by name in the .gnu_debugdata symbols
and its ringbuf lookup is replaced by `eventfd2(0, EFD_CLOEXEC)`: a valid fd that never becomes readable, i.e. no local-network-access events (the cgroup programs behind them are not loaded on 4.14 either)."""
import lzma, struct, sys
NAME = b'nativeGetLocalNetAccessRingbufFd\0'
d = bytearray(open(sys.argv[1], 'rb').read())
shoff, = struct.unpack_from('<Q', d, 0x28); shentsize, shnum = struct.unpack_from('<HH', d, 0x3a)
phoff, = struct.unpack_from('<Q', d, 0x20); phentsize, phnum = struct.unpack_from('<HH', d, 0x36)
loads = [(p[3], p[2], p[5]) for p in (struct.unpack_from('<IIQQQQQQ', d, phoff + i * phentsize) for i in range(phnum)) if p[0] == 1]    # (vaddr, offset, filesz)
def off2va(o): return next(va + (o - fo) for va, fo, sz in loads if fo <= o < fo + sz)
def va2off(v): return next(fo + (v - va) for va, fo, sz in loads if va <= v < va + sz)
def sections(buf):
    so, = struct.unpack_from('<Q', buf, 0x28); es, n, si = struct.unpack_from('<HHH', buf, 0x3a)
    return [struct.unpack_from('<IIQQQQIIQQ', buf, so + i * es) for i in range(n)], si
secs, shstr = sections(d)
dd = next(s for s in secs if d[secs[shstr][4] + s[0]:d.index(b'\0', secs[shstr][4] + s[0])] == b'.gnu_debugdata')      # minidebuginfo: xz ELF with the function symbols
dbg = lzma.decompress(d[dd[4]:dd[4] + dd[5]]); dsec, _ = sections(dbg)
symtab = next(s for s in dsec if s[1] == 2); strtab = dsec[symtab[6]]
def sym(sub):
    r = [v for o in range(symtab[4], symtab[4] + symtab[5], 24) for (nm, info, shn, v, sz) in [struct.unpack_from('<IBBHQ', dbg, o)[:3] + struct.unpack_from('<QQ', dbg, o + 8)]
         if sub in dbg[strtab[4] + nm:dbg.index(b'\0', strtab[4] + nm)] and v]
    assert len(r) == 1, (sub, r)
    return r[0]
fn = sym(b'nativeGetLocalNetAccessRingbufFd')
# nativeGetLocalNetAccessRingbufFd returns a FileDescriptor object: `bl GetRingbuf ; ldr w0,[x0,#0x18] ; mov w1,#0x406 ; mov w2,wzr ; bl fcntl` (dup of the ringbuf fd, F_DUPFD_CLOEXEC) feeds the
# unique_fd and jniCreateFileDescriptor. Replace just those five instructions with eventfd2(0, EFD_CLOEXEC); the result is in w0 like fcntl's.
o = va2off(fn); words = struct.unpack_from('<40I', d, o)
k = next(i for i in range(1, 39) if words[i] == 0xb9401800 and words[i + 1] == 0x528080c1 and words[i + 2] == 0x2a1f03e2)     # ldr w0,[x0,#0x18] ; mov w1,#0x406 ; mov w2,wzr
code = [0xd2800000, 0xd2a00101, 0xd2800268, 0xd4000001, 0xd503201f]   # mov x0,#0 ; mov x1,#0x80000 ; mov x8,#19 ; svc #0 ; nop
for j, w in enumerate(code): struct.pack_into('<I', d, o + 4 * (k - 1 + j), w)
# nativeInitLoopbackEventConsumer() (it tail-calls LoopbackEventHandler::Start() from ConnectivityService.systemReady) aborts the same way on map_netd_loopback_access_ringbuf: make it `mov x0,#0 ; ret` (void/false/null for any JNI return type)
st = va2off(sym(b'nativeInitLoopbackEventConsumer'))
struct.pack_into('<II', d, st, 0xd2800000, 0xd65f03c0)
open(sys.argv[2], 'wb').write(d); print(f'nativeGetLocalNetAccessRingbufFd at {fn:#x}: ringbuf fd -> eventfd2; nativeInitLoopbackEventConsumer -> ret;', sys.argv[2])
