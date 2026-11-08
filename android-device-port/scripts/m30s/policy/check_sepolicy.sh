#!/bin/sh
# Offline version of what init does at boot with a GSI on a split-policy vendor: compile the
# platform + system_ext cil of a GSI image with the stock vendor cil. Usage:
#   check_sepolicy.sh GSI_RAW_EXT4 VENDOR_RAW_EXT4 [SECILC]   (read-only; uses debugfs)
set -e
G=$1; V=$2; S=${3:-secilc}; E=/opt/homebrew/opt/e2fsprogs/sbin
W=$(mktemp -d "${TMPDIR:-/tmp}/sepol.XXXXXX"); VERS=$($E/debugfs -R "cat /etc/selinux/plat_sepolicy_vers.txt" "$V" 2>/dev/null)
d() { $E/debugfs -R "dump $2 $3" "$1" >/dev/null 2>&1; }
d "$G" /system/etc/selinux/plat_sepolicy.cil "$W/plat.cil"
d "$G" "/system/etc/selinux/mapping/$VERS.cil" "$W/map.cil"
d "$G" "/system/etc/selinux/mapping/$VERS.compat.cil" "$W/compat.cil"
d "$G" /system/system_ext/etc/selinux/system_ext_sepolicy.cil "$W/sysext.cil"
d "$V" /etc/selinux/plat_pub_versioned.cil "$W/pub.cil"
d "$V" /etc/selinux/vendor_sepolicy.cil "$W/vendor.cil"
echo "vendor plat_sepolicy_vers: $VERS"
run() { "$S" -m -M true -G -N -c 30 -o "$W/out.policy" -f /dev/null "$@" 2>&1 | tail -12; }
echo "== as shipped"; run "$W/plat.cil" "$W/map.cil" "$W/compat.cil" "$W/sysext.cil" "$W/pub.cil" "$W/vendor.cil"
[ -s "$W/out.policy" ] && { echo "COMPILES as shipped"; exit 0; }
echo "== without the GSI's genfscon iso9660/udf in system_ext (vendor labels them vfat)"
grep -v -E '^\(genfscon (iso9660|udf) "/"' "$W/sysext.cil" > "$W/sysext.fixed.cil"
run "$W/plat.cil" "$W/map.cil" "$W/compat.cil" "$W/sysext.fixed.cil" "$W/pub.cil" "$W/vendor.cil"
[ -s "$W/out.policy" ] && echo "COMPILES after dropping those two lines" || echo "STILL FAILS"
