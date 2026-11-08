#!/usr/bin/env python3
"""service-connectivity.jar (tethering apex), three patches. (1) BpfNetMaps.initBpfMaps() opens the local_net_* maps when SdkLevel.isAtLeastC().
Those maps (LPM_TRIE, ringbuf) cannot exist on kernel 4.9, so NetworkStatsServiceInitializer (and with it system_server) dies with
"Cannot open local_net_access map". Make that branch unconditional-skip: `if-eqz v9, :skip` -> `goto/16 :skip`.
Then fix the dex checksum + SHA-1 and rewrite the jar. The patched jar is bind-mounted over the apex copy.
Method and field indices and code offsets are looked up by name in the dex tables, so the same script handles DP11.261002.005 and DP11.261016.003.
usage: patch_service_connectivity_jar.py IN.jar OUT.jar"""
import hashlib, re, struct, sys, zipfile, zlib
src, dst = sys.argv[1:3]
zin = zipfile.ZipFile(src); raw = bytearray(zin.read('classes.dex'))
assert raw[:8] == b'dex\n039\0', raw[:8]
def uleb(o):
    v = sh = 0
    while True:
        x = raw[o]; o += 1; v |= (x & 0x7f) << sh; sh += 7
        if not x & 0x80: return v, o
str_off, type_off, meth_off = (struct.unpack_from('<I', raw, a)[0] for a in (0x3c, 0x44, 0x5c)); meth_n = struct.unpack_from('<I', raw, 0x58)[0]
cls_n, cls_off = struct.unpack_from('<II', raw, 0x60)
def string(i):
    o = struct.unpack_from('<I', raw, str_off + 4 * i)[0]; _, o = uleb(o); return raw[o:raw.index(b'\0', o)].decode('latin1')
def tname(t): return string(struct.unpack_from('<I', raw, type_off + 4 * t)[0])
def mname(i):
    c, _, n = struct.unpack_from('<HHI', raw, meth_off + 8 * i); return tname(c) + '.' + string(n)
names = {i: mname(i) for i in range(meth_n)}
def idx_of(suffix):
    r = [i for i, n in names.items() if n.endswith(suffix)]; assert len(r) == 1, (suffix, r); return r[0]
def code_offs(cls_suffix, wanted):
    """code_item offset of each wanted method of the class (by name)"""
    out = {}
    for k in range(cls_n):
        cls_idx, _, _, _, _, _, cdo, _ = struct.unpack_from('<8I', raw, cls_off + 32 * k)
        if not cdo or not tname(cls_idx).endswith(cls_suffix): continue
        o = cdo; sf, o = uleb(o); inf, o = uleb(o); dm, o = uleb(o); vm, o = uleb(o)
        for _ in range(sf + inf): _, o = uleb(o); _, o = uleb(o)
        for count in (dm, vm):
            idx = 0
            for _ in range(count):
                d, o = uleb(o); idx += d; _, o = uleb(o); co, o = uleb(o)
                n = names[idx].split('.')[-1]
                if n in wanted: out[n] = co
    assert set(out) == set(wanted), set(wanted) - set(out)
    return out
def find_unique(pattern, what):
    ms = list(re.finditer(pattern, raw, re.DOTALL)); assert len(ms) == 1, (what, len(ms)); return ms[0]
LE = lambda i: struct.pack('<H', i)
# (1) BpfNetMaps.initBpfMaps() opens the local_net_* maps when SdkLevel.isAtLeastC(); those maps (LPM_TRIE, ringbuf) cannot exist on kernel 4.9, so
#     NetworkStatsServiceInitializer (and system_server with it) dies with "Cannot open local_net_access map". Skip the branch: `if-eqz v9, :skip` -> `goto/16 :skip`.
pat1 = re.escape(b'\x71\x00' + LE(idx_of('SdkLevel;.isAtLeastC')) + b'\0\0' + bytes.fromhex('0a09' + '3809')) + b'(..)'
# initBpfMaps is the one whose skip target lands on `sget-boolean v9, sL4sSupported` (unit opcode 0x63, register 9)
cands = [m for m in re.finditer(pat1, raw, re.DOTALL)
         if raw[m.start() + 8 + struct.unpack_from('<h', raw, m.start(1))[0] * 2:][:2] == b'\x63\x09']
assert len(cands) == 1, ('isAtLeastC pattern', len(cands))
i = cands[0].start(); off1 = struct.unpack_from('<h', raw, cands[0].start(1))[0]
raw[i + 8:i + 12] = bytes.fromhex('2900') + struct.pack('<h', off1)               # goto/16 (same unit count as the 2-unit if-eqz)
# (2) ConnectivityService.<init>: `if (deps.isAtLeast26Q2()) mLocalNetEventListener = deps.getLocalNetEventListener(..)` -> LocalNetEventListener's native init
#     abort()s because the local_net_note_op ringbuf does not exist. Take the null branch (the code already handles null).
m2 = find_unique(re.escape(b'\x6e\x10' + LE(idx_of('ConnectivityService$Dependencies;.isAtLeast26Q2')) + bytes.fromhex('0800' + '0a00' + '3800')) + b'(..)', 'isAtLeast26Q2 pattern')
raw[m2.start() + 8:m2.start() + 12] = bytes.fromhex('2900') + m2.group(1)               # goto/16 with the same offset
# (3) ConnectivityService$Dependencies.initLoopbackEventConsumer(): its native side (LoopbackEventHandler::Start) abort()s because the loopback ringbuf map
#     does not exist on kernel 4.9. nop out the invoke-static (3 units).
m3 = find_unique(re.escape(b'\x71\x00' + LE(idx_of('BpfEventPoller;.nativeInitLoopbackEventConsumer')) + b'\0\0' + bytes.fromhex('0e00')), 'loopback pattern')
raw[m3.start():m3.start() + 6] = bytes(6)
# (4) kernel 4.9 has none of the local_net_* maps (see 1), so every BpfNetMaps method that writes them throws NPE on the ConnectivityServiceThread when wifi
#     connects (updateLocalNetworkAddresses -> addLocalNetAccess -> incrementLnpGenerationId) and kills system_server. Make them `return-void`.
#     The first instruction of each (16 bytes into its code_item) is 2 code units long.
for n, co in sorted(code_offs('BpfNetMaps;', ('incrementLnpGenerationId', 'updateLocalNetAccessMap', 'updateLocalNetUidHostAllowlistMap', 'addLocalNetAccess', 'addLocalNetUidAccess',
                                              'addLocalNetUidHostAccess', 'removeLocalNetAccess', 'removeLocalNetHostAllowlistForInterface', 'removeLocalNetUidAccess')).items()):
    raw[co + 16:co + 20] = bytes.fromhex('0e000000')
fs = struct.unpack_from('<I', raw, 0x20)[0]
raw[12:32] = hashlib.sha1(bytes(raw[32:fs])).digest()
struct.pack_into('<I', raw, 8, zlib.adler32(bytes(raw[12:fs])) & 0xffffffff)
zout = zipfile.ZipFile(dst, 'w')
for zi in zin.infolist():
    data = bytes(raw) if zi.filename == 'classes.dex' else zin.read(zi.filename)
    o = zipfile.ZipInfo(zi.filename, zi.date_time); o.compress_type = zi.compress_type; o.external_attr = zi.external_attr
    zout.writestr(o, data)
zout.close(); print('patched at', hex(i + 8), '; wrote', dst)
