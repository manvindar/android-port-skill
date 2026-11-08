#!/usr/bin/env python3
"""List framework fields/methods that an app dex references but the device's framework.jar no longer has (what NoSuchFieldError/NoSuchMethodError will hit).

usage: check_dex_refs.py app_dexdump_d.txt framework_dexdump.txt     (both from `dexdump -d` / `dexdump`, run with LC_ALL=C)
Only classes defined in the framework dump are checked; superclasses and interfaces are searched."""
import re, sys, collections
app, fw = sys.argv[1:3]
cls = {}                      # descriptor -> dict(super, ifaces, fields, methods)
cur = None; mode = None; name = None
for l in open(fw, errors='replace'):
    m = re.match(r"\s+Class descriptor\s+: '(L[^']+;)'", l)
    if m: cur = cls.setdefault(m.group(1), dict(sup=None, ifs=[], f=set(), m=set())); name = None; continue
    if cur is None: continue
    m = re.match(r"\s+Superclass\s+: '(L[^']+;)'", l)
    if m: cur['sup'] = m.group(1); continue
    m = re.match(r"\s+#\d+\s+: '(L[^']+;)'", l)
    if m: cur['ifs'].append(m.group(1)); continue
    if re.match(r'\s+(Static|Instance) fields', l): mode = 'f'; continue
    if re.match(r'\s+(Direct|Virtual) methods', l): mode = 'm'; continue
    m = re.match(r"\s+name\s+: '(.*)'", l)
    if m: name = m.group(1); continue
    m = re.match(r"\s+type\s+: '(.*)'", l)
    if m and name is not None:
        (cur['f'] if mode == 'f' else cur['m']).add((name, m.group(1))); name = None
def has(c, kind, key, seen=None):
    if c not in cls: return None      # not a framework.jar class: unknown
    seen = seen or set()
    if c in seen: return False
    seen.add(c); d = cls[c]
    if key in d[kind]: return True
    for p in ([d['sup']] if d['sup'] else []) + d['ifs']:
        r = has(p, kind, key, seen)
        if r: return True      # a parent outside framework.jar (java.lang.*) is assumed not to have it, see OBJ below
    return False
OBJ = {'toString', 'hashCode', 'equals', 'getClass', 'name', 'ordinal', 'wait', 'notify', 'notifyAll', 'clone', 'finalize', 'compareTo', 'getDeclaringClass', 'describeConstable'}
miss = collections.OrderedDict()
REF = re.compile(r'(L[^;\s]+;)\.([^:\s]+):(\S+) // (field|method)@')      # no backtracking over the register list: a 500 MB dump takes about a minute
count = collections.Counter()
for l in open(app, errors='replace'):
    if '// field@' in l or '// method@' in l:
        m = REF.search(l)
        if m: count[m.groups()] += 1
for (c, n, t, kind), k in count.items():
    r = has(c, 'f' if kind == 'field' else 'm', (n, t))
    if r is False and n not in OBJ: miss[(kind, c, n, t)] = k
for (kind, c, n, t), k in miss.items(): print(f'{kind}\t{c[1:-1].replace("/", ".")}.{n}:{t}\tx{k}')
