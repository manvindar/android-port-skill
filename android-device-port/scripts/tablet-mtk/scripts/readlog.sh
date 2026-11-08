#!/bin/bash
# fastboot -> TWRP -> pull pstore -> print init-side lines after the SELinux step
FB=~/Library/Android/sdk/platform-tools/fastboot; ADB=~/Library/Android/sdk/platform-tools/adb
cd ~/Aistuff/android-aosp/work/a17/logs; N=${1:-10}; rm -rf pstore$N; mkdir pstore$N
if $FB devices | grep -q fastboot; then $FB reboot recovery >/dev/null 2>&1; fi
for i in $(seq 1 25); do $ADB devices | grep -q recovery && break; sleep 3; done
$ADB pull /sys/fs/pstore pstore$N/ >/dev/null 2>&1
python3 -I - "$N" <<'PY'
import re,glob,sys
p=glob.glob('pstore%s/**/console-ramoops'%sys.argv[1],recursive=True)[0]
L=open(p,'rb').read().decode('latin1').split('\n')
print(len(L),'lines; last ts',[l[:14] for l in L if l.strip()][-1])
i=[k for k,l in enumerate(L) if 'init first stage started' in l or 'Switching root' in l]; s=i[-1] if i else 0
skip=re.compile(r'Get |MTK_WDT|mrdump|bq2560x|charger_thread|batt maintain|sx9310|CH3_DBG|SW_JEITA|musb|MUSB|fg_sw|product time|Skip mounting|FTS_TS|dbmdx|CMDQ|PWM|usb_6765|msdc|kworker|dump_backtrace|show_stack|dump_stack|arch_reset|mtk_arch|notifier|machine_restart|kernel_restart|SyS_reboot|el0_svc|wdt|WDT|console_sem|rtc|ARCH_RESET|Hardware name|Call trace|CPU:')
n=0
for l in L[s:]:
    if skip.search(l) or not l.strip(): continue
    print(l[:250]); n+=1
    if n>120: break
PY
