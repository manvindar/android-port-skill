#!/usr/bin/env python3
"""sepol_check.py (run in a dir holding plat.cil map30.cil compat30.cil sext.cil sextmap.cil pubv.cil vendor.cil; SECILC=path of a host secilc, selinux userspace 3.11 built from source): compile the donor system policy together with the stock M30s vendor policy the way init does and drop system-side declarations that the vendor policy also declares until it compiles. A266B donor: 6 felica typealiases in system_ext_sepolicy.cil (build_oneui_port.py step 4b)."""
import re, subprocess, sys, os
S=os.environ.get('SECILC', 'secilc')
files=['plat.cil','map30.cil','compat30.cil','sext.cil','sextmap.cil','pubv.cil','vendor.cil']
sysside={'plat.cil','sext.cil'}
removed=[]
for rnd in range(400):
    r=subprocess.run([S,'-m','-M','true','-G','-N','-c','30','-o','out.bin','-f','/dev/null']+files,capture_output=True,text=True)
    out=r.stdout+r.stderr
    if r.returncode==0: print('COMPILED after',rnd,'rounds; removed',len(removed)); break
    m=re.search(r'Re-declaration of (\S+) (\S+)\n(?:.*\n)*?Previous declaration of \S+ at (\S+):(\d+)',out)
    if not m: print(out[:800]); break
    kind,name=m.group(1),m.group(2)
    # remove every declaration of this name from system-side files
    done=False
    for f in sysside:
        L=open(f,encoding='latin1').read().split('\n'); N=[]
        for l in L:
            if re.match(r'^\((%s|typealiasactual) %s[ )]'%(re.escape(kind),re.escape(name)),l) or (kind=='typealias' and re.match(r'^\(typealiasactual %s '%re.escape(name),l)):
                removed.append((f,l)); done=True; continue
            N.append(l)
        open(f,'w',encoding='latin1').write('\n'.join(N))
    if not done: print('cannot remove',kind,name,out[:500]); break
print(removed[:12]); open('removed.txt','w').write('\n'.join('%s: %s'%x for x in removed))
