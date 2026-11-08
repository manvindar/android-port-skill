# Vendor-partition changes Android 17 needs on the TB-X606V's stock Android 10 vendor, in plain busybox sh (runs inside TWRP, no host tools).
# Same edits as tools/scripts/apply_vendor_a17.sh. Idempotent; originals are kept as *.orig-a17 / *.orig-mp2 / *.orig-vp9.
# Source this file and call:  apply_vendor_edits /path/to/mounted/vendor /path/to/payload
# (payload holds light_aidl.xml, vibrator_aidl.xml and health_aidl.xml). Files are rewritten with `cat new > old`, which keeps the inode and the SELinux label.
apply_vendor_edits() {
  V=$1; P=$2
  # 1 fstabs: Android 17 treats the legacy flags forcefdeorfbe= and resize as a parse error (init cannot read the fstab, /data never mounts); add /metadata
  for n in fstab.mt6765 fstab.mt8768; do
    f=$V/etc/$n; [ -f $f ] || continue
    if grep -q forcefdeorfbe $f || ! grep -q 'by-name/metadata ' $f; then
      [ -f $f.orig-a17 ] || cat $f > $f.orig-a17
      awk '{
        if ($0 ~ /^\// && NF >= 5) {
          n = split($5, a, ","); out = ""
          for (i = 1; i <= n; i++) { if (a[i] == "" || a[i] ~ /^forcefdeorfbe=/ || a[i] == "resize") continue; out = out (out == "" ? "" : ",") a[i] }
          $5 = out
        }
        print
        if ($1 ~ /by-name\/cache$/) print "/dev/block/platform/bootdevice/by-name/metadata /metadata ext4 noatime,nosuid,nodev,discard wait,check,formattable"
      }' $f.orig-a17 > /tmp/$n.new
      grep -q 'by-name/metadata ' /tmp/$n.new && cat /tmp/$n.new > $f
      echo "vendor: $n fixed"
    else echo "vendor: $n already fixed"; fi
  done
  # 2 ueventd: Android 17 no longer reads /vendor/ueventd.rc; copy it and open /dev/ion (the stock kernel creates it 0600 root, gralloc runs as system)
  if [ -f $V/ueventd.rc ] && ! grep -q '^/dev/ion 0666' $V/etc/ueventd.rc 2>/dev/null; then
    { cat $V/ueventd.rc; echo; echo "/dev/ion 0666 system system"; } > /tmp/ueventd.new
    if [ -f $V/etc/ueventd.rc ]; then cat /tmp/ueventd.new > $V/etc/ueventd.rc
    else cat /tmp/ueventd.new > $V/etc/ueventd.rc; chmod 644 $V/etc/ueventd.rc; chcon u:object_r:vendor_configs_file:s0 $V/etc/ueventd.rc 2>/dev/null; fi
    echo "vendor: ueventd.rc written"
  else echo "vendor: ueventd.rc already done"; fi
  # 3 seccomp: syscalls the Android 17 media and configstore code uses
  for f in configstore@1.1.policy mediacodec.policy mediaextractor.policy mediaswcodec.policy; do
    s=$V/etc/seccomp_policy/$f; [ -f $s ] || continue
    [ -f $s.orig-a17 ] || cat $s > $s.orig-a17
    for sc in gettid tgkill getrandom newfstatat sched_getaffinity mremap brk fcntl dup ppoll pread64 readlinkat set_tid_address; do
      grep -q "^$sc:" $s || echo "$sc: 1" >> $s
    done
  done
  echo "vendor: seccomp policies done"
  # 4 and 5 codecs: the MP2 audio decoder (type audio/mpeg-L2 aborts system_server) and the software-only VP9 video decoder (YouTube then picks hardware H.264)
  strip_codec() {   # file codec-name backup-suffix
    [ -f $1 ] || return 0
    grep -q "<MediaCodec name=\"$2\"" $1 || { echo "vendor: $2 not present"; return 0; }
    [ -f $1.$3 ] || cat $1 > $1.$3
    awk -v n="<MediaCodec name=\"$2\"" 'index($0, n) { skip = 1 } !skip { print } skip && /<\/MediaCodec>/ { skip = 0 }' $1.$3 > /tmp/codecs.new
    ! grep -q "$2" /tmp/codecs.new && cat /tmp/codecs.new > $1 && echo "vendor: removed $2"
  }
  strip_codec $V/etc/media_codecs_mediatek_audio.xml OMX.MTK.AUDIO.DECODER.MP2 orig-mp2
  strip_codec $V/etc/media_codecs_mediatek_video.xml OMX.MTK.VIDEO.DECODER.VP9 orig-vp9
  # 7 no deep_buffer output: Dolby's DAP effect is attached to the primary output only, and media normally plays on the deep_buffer output, so Dolby had no audible effect
  f=$V/etc/audio_policy_configuration.xml
  if [ -f $f ] && grep -q 'name="deep_buffer"' $f; then
    [ -f $f.orig-dolby ] || cat $f > $f.orig-dolby
    awk 'index($0, "<mixPort name=\"deep_buffer\"") { skip = 1 } !skip { print } skip && /<\/mixPort>/ { skip = 0 }' $f.orig-dolby | sed 's/,deep_buffer//g' > /tmp/apc.new
    ! grep -q deep_buffer /tmp/apc.new && cat /tmp/apc.new > $f && echo "vendor: deep_buffer output removed (Dolby)"
  else echo "vendor: deep_buffer already removed"; fi
  # 6 AIDL lights HAL declaration for the Java brightness shim
  if [ -f $P/light_aidl.xml ]; then
    mkdir -p $V/etc/vintf/manifest
    cat $P/light_aidl.xml > $V/etc/vintf/manifest/android.hardware.light-aidl.xml
    chmod 644 $V/etc/vintf/manifest/android.hardware.light-aidl.xml; chcon u:object_r:vendor_configs_file:s0 $V/etc/vintf/manifest/android.hardware.light-aidl.xml 2>/dev/null
    echo "vendor: light AIDL declaration written"
  fi
  # 6b AIDL vibrator HAL declaration for the Java haptics shim (A17 has no HIDL vibrator client; the vendor only has vibrator@1.0)
  if [ -f $P/vibrator_aidl.xml ]; then
    cat $P/vibrator_aidl.xml > $V/etc/vintf/manifest/android.hardware.vibrator-aidl.xml
    chmod 644 $V/etc/vintf/manifest/android.hardware.vibrator-aidl.xml; chcon u:object_r:vendor_configs_file:s0 $V/etc/vintf/manifest/android.hardware.vibrator-aidl.xml 2>/dev/null
    echo "vendor: vibrator AIDL declaration written"
  fi
  # 6c AIDL health HAL declaration for the Java battery shim (the vendor only has health@2.0, whose BatteryMonitor reads voltage and temperature from the fake mm8013 supply)
  if [ -f $P/health_aidl.xml ]; then
    cat $P/health_aidl.xml > $V/etc/vintf/manifest/android.hardware.health-aidl.xml
    chmod 644 $V/etc/vintf/manifest/android.hardware.health-aidl.xml; chcon u:object_r:vendor_configs_file:s0 $V/etc/vintf/manifest/android.hardware.health-aidl.xml 2>/dev/null
    echo "vendor: health AIDL declaration written"
  fi
}
