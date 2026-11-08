mount -o remount,rw /mnt/v2 || exit 1
cd /mnt/v2/etc/seccomp_policy
for f in configstore@1.1.policy mediacodec.policy mediaextractor.policy mediaswcodec.policy; do
  cp $f $f.orig-a17 2>/dev/null
  for s in gettid tgkill getrandom newfstatat sched_getaffinity mremap brk fcntl dup ppoll pread64 readlinkat set_tid_address; do
    grep -q "^$s:" $f || echo "$s: 1" >> $f
  done
  ls -lZ $f
done
sync
