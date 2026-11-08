#!/usr/bin/env python3
"""Compare AIDL interfaces (apktool smali dirs) between an app and the system component it talks to (R8 removes the TRANSACTION_ constants, so
codes are read from the client side (Proxy: const before IBinder.transact) and the server side (Stub.onTransact switch)).
usage: compare_aidl.py APP_DECODED SYSTEM_DECODED [class-filter]  -> per interface: code/name/signature differences"""
import glob, os, re, sys
def regs(s): return [r.strip() for r in s.split(',')]
def methods(txt):
    for m in re.finditer(r'\.method [^\n]*? (\S+)\(([^)]*)\)(\S+)\n(.*?)\.end method', txt, re.S): yield m.group(1), '(' + m.group(2) + ')' + m.group(3), m.group(4)
def proxy_codes(path):
    out = {}
    for name, sig, body in methods(open(path, errors='replace').read()):
        lines = body.split('\n'); consts = {}
        for l in lines:
            m = re.match(r'\s+const(?:/4|/16)? (\S+), (-?0x[0-9a-f]+|-?\d+)', l)
            if m: consts[m.group(1)] = int(m.group(2), 0)
            m = re.match(r'\s+invoke-interface \{([^}]*)\}, Landroid/os/IBinder;->transact', l)
            if m:
                r = regs(m.group(1))
                if len(r) > 1 and r[1] in consts: out[consts[r[1]]] = (name, sig)
                break
    return out
def stub_codes(path):
    txt = open(path, errors='replace').read(); out = {}
    m = re.search(r'\.method public onTransact.*?\.end method', txt, re.S)
    if not m: return out
    body = m.group(0)
    first = re.search(r'\.packed-switch (-?0x[0-9a-f]+|\d+)\n(.*?)\.end packed-switch', body, re.S)
    tab = []
    if first:
        base = int(first.group(1), 0); tab = [(base + i, l.strip()) for i, l in enumerate(first.group(2).strip().split('\n'))]
    for sp in re.finditer(r'\.sparse-switch\n(.*?)\.end sparse-switch', body, re.S):
        for l in sp.group(1).strip().split('\n'):
            k, v = l.split('->'); tab.append((int(k.strip(), 0), v.strip()))
    for code, label in tab:
        i = body.find('    ' + label + '\n')
        if i < 0: continue
        seg = body[i:i + 4000]
        for im in re.finditer(r'invoke-interface \{[^}]*\}, L[^;]+;->(\w+)\(([^)]*)\)(\S+)', seg):
            if im.group(1) in ('readInt', 'enforceNoDataAvail', 'writeNoException'): continue
            out[code] = (im.group(1), '(' + im.group(2) + ')' + im.group(3)); break
    return out
def load(root):
    r = {}
    for f in glob.glob(root + '/smali*/**/*.smali', recursive=True):
        base = os.path.basename(f)
        if base.endswith('$Stub$Proxy.smali'): kind, key = 'proxy', f[:-len('$Stub$Proxy.smali')]
        elif base.endswith('$Stub.smali'): kind, key = 'stub', f[:-len('$Stub.smali')]
        else: continue
        cls = re.sub(r'.*/smali[^/]*/', '', key)
        d = proxy_codes(f) if kind == 'proxy' else stub_codes(f)
        if d: r.setdefault(cls, {}).setdefault(kind, d)
    return r
a, s = load(sys.argv[1]), load(sys.argv[2]); flt = sys.argv[3] if len(sys.argv) > 3 else ''
for cls in sorted(set(a) & set(s)):
    if flt not in cls: continue
    A = a[cls].get('proxy') or a[cls].get('stub'); S = s[cls].get('stub') or s[cls].get('proxy')
    bad = []
    for c in sorted(set(A) | set(S)):
        if c not in S: bad.append(f'  {c}: app {A[c][0]} / system -')
        elif c not in A: bad.append(f'  {c}: app - / system {S[c][0]}')
        elif A[c][0] != S[c][0]: bad.append(f'  {c}: app {A[c][0]} / system {S[c][0]}')
        elif A[c][1] != S[c][1]: bad.append(f'  {c}: {A[c][0]} app {A[c][1]} / system {S[c][1]}')
    print(f'{cls}: {len(A)} app / {len(S)} system methods, {len(bad)} differences')
    for b in bad: print(b)
