#!/bin/sh
# Offline build of the Android 14 test image for the M30s. Usage: build_a14.sh GSI_RAW OUT_DIR [VENDOR_RAW]
# Writes OUT_DIR/system-a14.img (ext4, 4800 MiB = the partition, shared_blocks removed) and, when
# VENDOR_RAW is given, OUT_DIR/vendor-mp2.img (stock vendor without the audio/mpeg-L2 codec type).
# Nothing here touches the phone. Needs e2fsprogs (keg-only), ~10 GB free in OUT_DIR.
set -e
G=$1; O=$2; V=$3; E=/opt/homebrew/opt/e2fsprogs/sbin
mkdir -p "$O"
echo "== system: copy, grow to 4800 MiB, then unshare blocks (needs the free space)"
dd if="$G" of="$O/system-a14.img" bs=4m 2>/dev/null
truncate -s 5033164800 "$O/system-a14.img"
$E/e2fsck -fy "$O/system-a14.img" >/dev/null || [ $? -le 1 ]
$E/resize2fs "$O/system-a14.img" 1228800 >/dev/null 2>&1
$E/e2fsck -fy -E unshare_blocks "$O/system-a14.img" >/dev/null || [ $? -le 1 ]
$E/e2fsck -fn "$O/system-a14.img" | tail -2
$E/dumpe2fs -h "$O/system-a14.img" 2>/dev/null | grep -E "features|Block count|Free blocks"
[ -z "$V" ] && exit 0
echo "== vendor: drop <Type name=audio/mpeg-L2> from OMX.SEC.mp3.dec (media_codecs_sec_primary.xml)"
T=$(mktemp -d "${TMPDIR:-/tmp}/a14.XXXXXX"); P=/etc/media_codecs_sec_primary.xml
cp "$V" "$O/vendor-mp2.img"
$E/debugfs -R "cat $P" "$V" 2>/dev/null > "$T/x.xml"
python3 -I - "$T/x.xml" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
n, k = re.subn(r'\n\s*<Type name="audio/mpeg-L2">.*?</Type>', '', s, flags=re.S)
assert k == 1, 'expected exactly one audio/mpeg-L2 Type, found %d' % k
open(p, 'w').write(n)
PY
LBL=$($E/debugfs -R "ea_get -V $P security.selinux" "$V" 2>/dev/null | tr -d '\000"' | tail -1)
printf '%s\0' "$LBL" > "$T/lbl"
cat > "$T/cmds" <<CMDS
rm $P
write $T/x.xml $P
set_inode_field $P mode 0100644
set_inode_field $P uid 0
set_inode_field $P gid 0
ea_set -f $T/lbl $P security.selinux
CMDS
$E/debugfs -w -f "$T/cmds" "$O/vendor-mp2.img" >/dev/null 2>&1
$E/e2fsck -fn "$O/vendor-mp2.img" | tail -1
$E/debugfs -R "ls -l $P" "$O/vendor-mp2.img" 2>/dev/null | tail -1
$E/debugfs -R "ea_list $P" "$O/vendor-mp2.img" 2>/dev/null | tail -2
