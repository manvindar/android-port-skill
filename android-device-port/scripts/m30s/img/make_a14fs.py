#!/usr/bin/env python3
"""Make the extra files the M30s Android 17 image needs besides the GSI (input of build_a17.py --a14fs):
  init, linker64, lib64/*   Android 14's first-stage init and its library closure, dumped from the A14 system image (A17's init is second-stage only)
  launcher                  tools/debug/fslaunch.c, the static /init that runs A14's init through A14's linker
  tracer                    tools/debug/netbpfload_tracer.c (runs netbpfload.a17 under ptrace, logs to kmsg and /data/bpftrace.log)
  lmkd                      tools/lmkd/lmkd_inkernel.c of the tablet repo (userspace low memory killer)
Everything compiled is built with the NDK clang, static: zig/musl binaries die here with "TLS segment is underaligned" (bionic's linker64 refuses them).
usage: make_a14fs.py A14_SYSTEM.img OUT_DIR [TABLET_TOOLS]"""
import glob, os, re, subprocess, sys
img, out = sys.argv[1:3]; tools = os.path.expanduser(sys.argv[3] if len(sys.argv) > 3 else '~/Aistuff/tb-x606v-android17/tools'); here = os.path.dirname(os.path.abspath(__file__))
E2 = next(d for d in ('/opt/homebrew/opt/e2fsprogs/sbin', '/usr/local/opt/e2fsprogs/sbin', '/sbin', '/usr/sbin') if os.path.exists(d + '/debugfs'))
NDK = sorted(glob.glob(os.path.join(os.environ.get('ANDROID_NDK_ROOT') or os.environ.get('ANDROID_NDK_HOME') or os.path.join(os.environ.get('ANDROID_HOME') or os.path.expanduser('~/Library/Android/sdk'), 'ndk', '*'), 'toolchains/llvm/prebuilt/*/bin')))[-1]
lib = os.path.join(out, 'lib64'); os.makedirs(lib, exist_ok=True)
def dump(src, dst): subprocess.run([E2 + '/debugfs', '-R', f'dump {src} {dst}', img], capture_output=True); return os.path.exists(dst) and os.path.getsize(dst) > 0
for src, n in (('/system/bin/init', 'init'), ('/system/bin/bootstrap/linker64', 'linker64')): assert dump(src, os.path.join(out, n)), n
def needed(f): return re.findall(r'Shared library: \[(.*?)\]', subprocess.run([NDK + '/llvm-readelf', '-d', f], capture_output=True, text=True).stdout)
seen, q = set(), [os.path.join(out, 'init')]
while q:
    for n in needed(q.pop()):
        if n in seen: continue
        seen.add(n); dst = os.path.join(lib, n)
        if dump(('/system/lib64/bootstrap/' if n in ('libc.so', 'libm.so', 'libdl.so', 'libdl_android.so') else '/system/lib64/') + n, dst): q.append(dst)
print('closure:', len(os.listdir(lib)), 'libs')
for src, name in ((os.path.join(here, '..', 'debug', 'fslaunch.c'), 'launcher'), (os.path.join(here, '..', 'debug', 'netbpfload_tracer.c'), 'tracer'), (os.path.join(tools, 'lmkd', 'lmkd_inkernel.c'), 'lmkd')):
    subprocess.run([NDK + '/aarch64-linux-android30-clang', '-static', '-O2', '-D_GNU_SOURCE', '-o', os.path.join(out, name), src], check=True)
print('done:', sorted(os.listdir(out)))
