#!/usr/bin/env python3
"""Derive tools/img/build_oneui.py from tools/img/build_a17.py (itself generated: run tools/img/make_build_a17.py first) by adding one option, --oneui DIR, and the block `9e One UI layer`.
usage: make_build_oneui.py > /dev/null      (writes tools/img/build_oneui.py; every substitution asserts its anchor, so a changed build_a17.py fails loudly)
DIR is what tools/oneui/stage_oneui_*.py write: <partition>/... trees (system, system_ext, product, optics, prism) that end up under /system/<partition>/ of the GSI image (the M30s has ONE system
partition; /system/system_ext and /system/product are plain directories), plus oneui-stage.json:
  {"remove": ["/system/system_ext/priv-app/Foo/Foo.apk", ...],   GSI files deleted first (apps the donor replaces under another directory name)
   "exec":   ["system/bin/foo", ...]}                            paths (relative to DIR) that get mode 755 instead of 644
`system/<x>` entries land in /system/<x> directly. Files under .../lib64/ get the system_lib_file label, everything else system_file (the kernel boots permissive, labels are cosmetic)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); IMG = os.path.join(HERE, '..', 'img')
s = open(os.path.join(IMG, 'build_a17.py')).read()
def sub(old, new):
    global s
    assert s.count(old) == 1, f'anchor not found exactly once ({s.count(old)}): ' + old[:80]
    s = s.replace(old, new)
sub("ap.add_argument('--pixel-launcher-apk',", "ap.add_argument('--oneui', help='directory made by tools/oneui/stage_oneui_*.py (Samsung One UI 9 donor layers, see tools/oneui/make_build_oneui.py)')\nap.add_argument('--pixel-launcher-apk',")
sub("if priv_apks:\n    # a priv-app with a privileged permission", """if a.oneui:
    print('9e One UI layer')
    st = a.oneui; man = json.load(open(os.path.join(st, 'oneui-stage.json'))) if os.path.exists(os.path.join(st, 'oneui-stage.json')) else {}
    for r in man.get('remove', []):
        if exists(S, r): cmds.append('rm ' + r)
    staged = sorted(os.path.relpath(os.path.join(r, f), st) for r, _, fs in os.walk(st) for f in fs if f != 'oneui-stage.json')
    dst_of = lambda f: '/' + f if f.startswith('system/') else '/system/' + f
    ensure_dirs(dst_of(f) for f in staged)
    for f in staged:
        put(os.path.join(st, f), dst_of(f), '755' if f in man.get('exec', []) else '644', 0, 0, LIB if '/lib64/' in f or '/lib/' in f else SYS)
    for part in ('system', 'system_ext', 'product'):
        allow_xmls += [os.path.join(st, f) + ':' + part for f in staged if f.startswith(part + '/etc/permissions/') and f.endswith('.xml')]
    priv_apks += [os.path.join(st, f) + ':' + f.split('/')[0] for f in staged if '/priv-app/' in f and f.endswith('.apk') and f.split('/')[0] in ('system', 'system_ext', 'product')]
    print(f'  {len(staged)} files, {sum(os.path.getsize(os.path.join(st, f)) for f in staged) >> 20} MiB')
if priv_apks:
    # a priv-app with a privileged permission""")
open(os.path.join(IMG, 'build_oneui.py'), 'w').write(s); print('tools/img/build_oneui.py written', file=sys.stderr)
