#!/bin/bash
# After a failed boot: reach TWRP (fastboot -> recovery, or you hold Volume Up+Down), pull the kernel console of that boot and
# print init's side of it after the SELinux step. /proc/last_kmsg and /sys/fs/pstore hold the same record.
FB=${FB:-~/Library/Android/sdk/platform-tools/fastboot}; ADB=${ADB:-~/Library/Android/sdk/platform-tools/adb}
OUT=${1:-last_kmsg.txt}
if $FB devices | grep -q fastboot; then $FB reboot recovery >/dev/null 2>&1; fi
for i in $(seq 1 25); do $ADB devices | grep -q recovery && break; sleep 3; done
$ADB pull /proc/last_kmsg "$OUT" >/dev/null 2>&1
python3 - "$OUT" <<'PY'
import re,sys
L=open(sys.argv[1],'rb').read().decode('latin1').split('\n')
skip=re.compile(r'Get |MTK_WDT|mrdump|bq2560x|charger_thread|batt maintain|sx9310|CH3_DBG|SW_JEITA|musb|MUSB|fg_sw|product time|FTS_TS|dbmdx|CMDQ|PWM|usb_6765|msdc|wdt|WDT|console_sem|rtc|avc:  denied|audit:|Setting property|Overriding|Added .* to import|Parsing file|processing action|BOOTPROF|binder: .* ioctl|Read-only file system|dump_backtrace|show_stack|dump_stack|kworker')
i=[k for k,l in enumerate(L) if 'init second stage started' in l]
for l in L[(i[0] if i else 0):]:
    if skip.search(l) or not l.strip(): continue
    if re.search(r'init|exited|killed|Fatal|fatal|critical|Reboot|reboot|panic|Oops|Unable to handle|apexd|zygote|system_server|netd|bpf',l,re.I): print(l[:250])
PY
