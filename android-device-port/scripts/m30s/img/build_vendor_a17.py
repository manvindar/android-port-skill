#!/usr/bin/env python3
"""Offline vendor edits Android 17 needs on the M30s's stock Android 11 vendor (the M30s counterpart of the tablet's apply_vendor_a17.sh, done with debugfs on an image copy).
usage: build_vendor_a17.py VENDOR_IN.img VENDOR_OUT.img HEALTH_VINTF.xml     (VENDOR_IN = work/a14/vendor-mp2.img: stock vendor without the audio/mpeg-L2 type)
  1. /vendor/etc/fstab.exynos9611: a tmpfs /metadata (the phone has no metadata partition; A17 init/aconfig/bootstat expect the mount). Volatile: persistent stand-in is future work.
  2. /vendor/etc/ueventd.rc = copy of /vendor/ueventd.rc (A17 ueventd reads only the /vendor/etc one; /dev/ion is already 0666 system in the Samsung file)
  3. seccomp policies (configstore@1.1, mediacodec, mediaextractor_sec, samsung c2): syscalls the A17 media/configstore code uses (same list as the tablet's seccomp_add.sh)
  4. /vendor/etc/vintf/manifest/android.hardware.health-aidl.xml for the health shim in the system image (HIDL health 2.1 stays declared; the shim registers AIDL IHealth)
  5  userdata fstab line without fileencryption=ice: the stock kernel's ICE key path does not work with A17's vold/keymint here (userdata is then plain, readable from TWRP; format userdata once after flashing)
  6  /vendor/etc/selinux/vendor_mac_permissions.xml without the package-only signers: A17's SELinuxMMAC parser rejects the Samsung (A11 format) file ("Unable to load SELinux MMAC policy", system_server dies)
Lights: the Samsung vendor already declares AIDL ILights/default, no shim. Vibrator: HIDL 1.3 only, no shim in this first image. Originals are kept as *.orig-a17.
Each edit keeps owner, mode and SELinux label of the file it replaces; e2fsck -fn must be clean."""
import os, re, shutil, subprocess, sys, tempfile
src, dst, health = sys.argv[1:4]
E2 = next(d for d in ('/opt/homebrew/opt/e2fsprogs/sbin', '/usr/local/opt/e2fsprogs/sbin', '/sbin', '/usr/sbin') if os.path.exists(d + '/debugfs'))
shutil.copyfile(src, dst)
W = tempfile.mkdtemp(prefix='vend17')
def dbg(*c): return subprocess.run([E2 + '/debugfs', '-R', ' '.join(c), dst], capture_output=True)
def cat(p): r = dbg('cat', p).stdout; assert r, p; return r
def attrs(p):
    st = dbg('stat', p).stdout.decode('latin1')
    m = re.search(r'Mode:\s+0?(\d+)', st).group(1)[-3:]; u, g = map(int, re.search(r'User:\s+(\d+)\s+Group:\s+(\d+)', st).groups())
    lbl = dbg('ea_get', '-V', p, 'security.selinux').stdout.decode('latin1').split('\0')[0].strip()
    assert lbl, p; return m, u, g, lbl
cmds = []
def put(path, data, like=None, label='u:object_r:vendor_configs_file:s0', mode='644'):
    if like: mode, u, g, label = attrs(like)
    else: u = g = 0
    f = os.path.join(W, 'f%d' % len(cmds)); open(f, 'wb').write(data); l = f + '.lbl'; open(l, 'wb').write(label.encode() + b'\0')
    cmds.extend([f'rm {path}', f'write {f} {path}', f'set_inode_field {path} mode 0100{mode}', f'set_inode_field {path} uid {u}', f'set_inode_field {path} gid {g}', f'ea_set -f {l} {path} security.selinux'])

fs = cat('/etc/fstab.exynos9611').decode()
assert '/metadata' not in fs
out = []
for l in fs.split('\n'):
    if l.startswith('/dev/block/platform/13520000.ufs/by-name/userdata'):
        assert ',fileencryption=ice' in l; l = l.replace(',fileencryption=ice', '')
    out.append(l)
    if l.startswith('/dev/block/platform/13520000.ufs/by-name/userdata'):
        out.append('tmpfs\t/metadata\ttmpfs\tnosuid,nodev,noatime,size=32m,mode=0771\tdefaults')
put('/etc/fstab.exynos9611.orig-a17', fs.encode(), like='/etc/fstab.exynos9611'); put('/etc/fstab.exynos9611', '\n'.join(out).encode(), like='/etc/fstab.exynos9611')
ue = cat('/ueventd.rc'); assert b'/dev/ion' in ue
put('/etc/ueventd.rc', ue, like='/ueventd.rc')
SYSC = 'gettid tgkill getrandom newfstatat sched_getaffinity mremap brk fcntl dup ppoll pread64 readlinkat set_tid_address'.split()
for n in ('configstore@1.1.policy', 'mediacodec.policy', 'mediaextractor_sec.policy', 'samsung.hardware.media.c2@1.1-default-seccomp-policy'):
    p = '/etc/seccomp_policy/' + n; t = cat(p).decode(); add = [s for s in SYSC if not re.search(r'(?m)^%s:' % s, t)]
    if t and not t.endswith('\n'): t += '\n'
    put(p, (t + ''.join(f'{s}: 1\n' for s in add)).encode(), like=p); print(f'  seccomp {n}: +{len(add)} syscalls')
mp = '/etc/selinux/vendor_mac_permissions.xml'; mac = cat(mp).decode('latin1')
fixed = re.sub(r'<signer\b(?:(?!</signer>).)*?<package\b.*?</signer>', '', mac, flags=re.S); assert fixed != mac and '<package' not in fixed and '<signer' in fixed
put(mp + '.orig-a17', mac.encode('latin1'), like=mp); put(mp, fixed.encode('latin1'), like=mp)
put('/etc/vintf/manifest/android.hardware.health-aidl.xml', open(health, 'rb').read(), like='/etc/vintf/manifest/lights-default-sec.xml')
f = os.path.join(W, 'cmds'); open(f, 'w').write('\n'.join(cmds) + '\n')
r = subprocess.run([E2 + '/debugfs', '-w', '-f', f, dst], capture_output=True, text=True)
bad = [l for l in (r.stdout + r.stderr).split('\n') if re.search(r'(?i)(error|not found|no such|not enough|no space)', l) and 'File not found by ext2_lookup' not in l]
assert not bad, bad[:10]
subprocess.run([E2 + '/e2fsck', '-fn', dst], check=True, capture_output=True)
shutil.rmtree(W, ignore_errors=True); print('vendor image written:', dst, os.path.getsize(dst))
