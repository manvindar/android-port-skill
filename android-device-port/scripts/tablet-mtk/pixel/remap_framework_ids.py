#!/usr/bin/env python3
"""Re-point framework resource ids in an APK (built against another Android 17 build) to the device's framework-res numbering.

usage: remap_framework_ids.py IN.apk OUT.apk MAP.json      (MAP.json from framework_id_map.py; output is unsigned: zipalign + apksigner afterwards)
Patched places (all by structure, no byte search):
  resources.arsc  simple and compact entries, map (style/array/plurals) values, style parents, map names
  binary XML      typed attribute values, the attribute-name resource map
  classes*.dex    `const vX, ID` instructions (SystemUI and Settings are built in-tree and inline com.android.internal.R ids), found with dexdump -d
Prints counts per file, and the references to ids that do not exist on the device (cannot be fixed by remapping).
env: BUILD_TOOLS (dexdump)"""
import glob, hashlib, json, os, re, struct, subprocess, sys, tempfile, zipfile, zlib

def u16(b, o): return struct.unpack_from('<H', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]

class R:
    def __init__(self, mp, missing): self.mp, self.missing, self.n, self.miss = mp, missing, 0, {}
    def fix(self, b, o):
        v = u32(b, o)
        if v in self.mp: struct.pack_into('<I', b, o, self.mp[v]); self.n += 1
        elif v in self.missing: self.miss[v] = self.miss.get(v, 0) + 1
    def value(self, b, o):          # Res_value at o: size u16, res0 u8, dataType u8, data u32
        if b[o + 3] in (1, 2): self.fix(b, o + 4)

def chunks(b, o, end):
    while o + 8 <= end:
        t, h, s = u16(b, o), u16(b, o + 2), u32(b, o + 4)
        if s < 8: break
        yield t, h, s, o; o += s

def arsc(b, r):
    for t, h, s, o in chunks(b, 12, len(b)):
        if t != 0x0200: continue
        for t2, h2, s2, o2 in chunks(b, o + h, o + s):
            if t2 != 0x0201: continue
            flags, count, start = b[o2 + 9], u32(b, o2 + 12), u32(b, o2 + 16)
            offs = []
            if flags & 1:                                           # sparse: (idx u16, offset/4 u16)
                offs = [u16(b, o2 + h2 + 4 * i + 2) * 4 for i in range(count)]
            elif flags & 2:                                         # 16 bit offsets/4
                offs = [u16(b, o2 + h2 + 2 * i) * 4 for i in range(count) if u16(b, o2 + h2 + 2 * i) != 0xffff]
            else:
                offs = [u32(b, o2 + h2 + 4 * i) for i in range(count) if u32(b, o2 + h2 + 4 * i) != 0xffffffff]
            for off in offs:
                e = o2 + start + off; size, fl = u16(b, e), u16(b, e + 2)
                if fl & 8:                                          # compact: type in flags >> 8, data at +4
                    if (fl >> 8) in (1, 2): r.fix(b, e + 4)
                elif fl & 1:                                        # complex: parent, count, (name, Res_value) x count
                    r.fix(b, e + 8); n = u32(b, e + 12)
                    for i in range(n):
                        m = e + size + 12 * i; r.fix(b, m); r.value(b, m + 4)
                else: r.value(b, e + size)

def xml(b, r):
    for t, h, s, o in chunks(b, 8, len(b)):
        if t == 0x0180:
            for p in range(o + 8, o + s, 4): r.fix(b, p)
        elif t == 0x0102:
            ext = o + 16; astart, asize, n = u16(b, ext + 8), u16(b, ext + 10), u16(b, ext + 12)
            for i in range(n): r.value(b, ext + astart + asize * i + 12)

def dex(raw, r, bt):
    with tempfile.NamedTemporaryFile(suffix='.dex') as t:
        t.write(raw); t.flush()
        dump = subprocess.run([os.path.join(bt, 'dexdump'), '-d', t.name], capture_output=True, text=True, errors='replace', env=dict(os.environ, LC_ALL='C')).stdout
    b = bytearray(raw); starts = []; pos = 0; seen = set()          # dex 041 containers hold several dex files back to back
    while pos < len(b): starts.append(pos); pos += u32(b, pos + 32)
    for m in re.finditer(r'^([0-9a-f]{6,}): 14[0-9a-f]{2} .*?\| ?[0-9a-f]+: const v\d+, #[^/]*// #([0-9a-f]{8})$', dump, re.M):      # 31i: opcode, reg, 32 bit literal
        off = int(m.group(1), 16); v = int(m.group(2), 16)
        if off in seen: continue                           # identical code items are shared by several methods and listed once per method
        seen.add(off)
        if v in r.mp:
            # dexdump prints offsets relative to the start of the dex it is dumping (the container start for the first one): find the one dex where the literal is
            hit = [p for p in starts if p + off + 6 <= len(b) and b[p + off] == 0x14 and u32(b, p + off + 2) == v]
            assert len(hit) == 1, f'dexdump offset {off:#x} (literal {v:#x}) matches {len(hit)} dex files'
            struct.pack_into('<I', b, hit[0] + off + 2, r.mp[v]); r.n += 1
        elif v in r.missing: r.miss[v] = r.miss.get(v, 0) + 1
    for pos in starts:                                    # every header: signature = SHA-1 of [32, file_size), checksum = adler32 of [12, file_size)
        fs = u32(b, pos + 32); b[pos + 12:pos + 32] = hashlib.sha1(bytes(b[pos + 32:pos + fs])).digest(); struct.pack_into('<I', b, pos + 8, zlib.adler32(bytes(b[pos + 12:pos + fs])) & 0xffffffff)
    return bytes(b)

def remap(src, dst, mapfile, bt):
    j = json.load(open(mapfile)); mp = {int(k, 16): int(v, 16) for k, v in j['map'].items()}; missing = {int(k, 16): v for k, v in j['missing'].items()}
    zin = zipfile.ZipFile(src); tot, allmiss = {}, {}
    with zipfile.ZipFile(dst, 'w') as z:
        for info in zin.infolist():
            data = zin.read(info); n = info.filename; r = R(mp, missing)
            if n == 'resources.arsc': data = bytearray(data); arsc(data, r); data = bytes(data)
            elif n.endswith('.xml') and data[:2] == b'\x03\x00': data = bytearray(data); xml(data, r); data = bytes(data)
            elif re.fullmatch(r'classes\d*\.dex', n): data = dex(data, r, bt)
            if r.n: tot[n] = r.n
            for k, v in r.miss.items(): allmiss.setdefault(k, [0, ''])[0] += v
            zi = zipfile.ZipInfo(n, info.date_time); zi.compress_type = info.compress_type; zi.external_attr = info.external_attr
            z.writestr(zi, data)
    xs = sum(v for k, v in tot.items() if k.endswith('.xml')); print(f'{os.path.basename(src)}: remapped', {k: v for k, v in tot.items() if not k.endswith('.xml')}, f'xml x{xs} in {sum(1 for k in tot if k.endswith(".xml"))} files')
    for k, (c, _) in sorted(allmiss.items()): print(f'  MISSING on device: {hex(k)} {missing[k]} x{c}')
    return sum(tot.values()), allmiss

if __name__ == '__main__':
    bt = os.environ.get('BUILD_TOOLS') or sorted(glob.glob(os.path.expanduser('~/Library/Android/sdk/build-tools/*')))[-1]
    n, miss = remap(sys.argv[1], sys.argv[2], sys.argv[3], bt); print(n, 'references remapped,', len(miss), 'distinct missing ids referenced')
