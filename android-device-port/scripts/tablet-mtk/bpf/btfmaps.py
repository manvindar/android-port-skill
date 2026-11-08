#!/usr/bin/env python3
"""Dump the BTF-defined maps (.maps section) of an Android bpf .o: name, type, sizes, flags.
usage: btfmaps.py obj.o [--patch NEWFILE] (--patch rewrites LRU map types to HASH inside the BTF)"""
import struct, sys
MT={1:'HASH',2:'ARRAY',3:'PROG_ARRAY',4:'PERF_EVENT_ARRAY',5:'PERCPU_HASH',6:'PERCPU_ARRAY',7:'STACK_TRACE',8:'CGROUP_ARRAY',9:'LRU_HASH',10:'LRU_PERCPU_HASH',11:'LPM_TRIE',12:'ARRAY_OF_MAPS',13:'HASH_OF_MAPS',14:'DEVMAP',15:'SOCKMAP',16:'CPUMAP',17:'XSKMAP',18:'SOCKHASH',19:'CGROUP_STORAGE',20:'REUSEPORT_SOCKARRAY',21:'PERCPU_CGROUP_STORAGE',22:'QUEUE',23:'STACK',24:'SK_STORAGE',25:'DEVMAP_HASH',26:'STRUCT_OPS',27:'RINGBUF',28:'INODE_STORAGE',29:'TASK_STORAGE',30:'BLOOM_FILTER',31:'USER_RINGBUF'}
def sections(d):
    shoff=struct.unpack_from('<Q',d,0x28)[0]; shentsize,shnum,shstrndx=struct.unpack_from('<HHH',d,0x3A)
    sh=[struct.unpack_from('<IIQQQQIIQQ',d,shoff+i*shentsize) for i in range(shnum)]
    strt=sh[shstrndx]; names=d[strt[4]:strt[4]+strt[5]]
    out={}
    for s in sh:
        n=names[s[0]:names.index(b'\0',s[0])].decode(); out[n]=s
    return out
def main():
    f=sys.argv[1]; d=bytearray(open(f,'rb').read()); S=sections(d)
    b=S['.BTF']; off,sz=b[4],b[5]; B=d[off:off+sz]
    magic,ver,flags,hdr,toff,tlen,soff,slen=struct.unpack_from('<HBBIIIII',B,0)
    T=B[hdr+toff:hdr+toff+tlen]; STR=B[hdr+soff:hdr+soff+slen]
    nm=lambda o: bytes(STR[o:STR.index(b'\0',o)]).decode()
    types=[None]; p=0
    while p<len(T):
        n,info,sz_=struct.unpack_from('<III',T,p); kind=(info>>24)&0x1f; vlen=info&0xffff; start=p; p+=12
        ex=None
        if kind==1: p+=4
        elif kind==3: ex=start+12; p+=12
        elif kind in(4,5): ex=[struct.unpack_from('<III',T,p+12*i) for i in range(vlen)]; p+=12*vlen
        elif kind==6: p+=8*vlen
        elif kind==13: p+=8*vlen
        elif kind==14: p+=4
        elif kind==15: ex=[struct.unpack_from('<III',T,p+12*i) for i in range(vlen)]; p+=12*vlen
        elif kind==17: p+=4
        elif kind==19: p+=12*vlen
        types.append((kind,n,sz_,info,ex,start))
    arr_off={}
    def arr(t):  # PTR->ARRAY nelems
        k,n,sz_,info,ex,st=types[t]
        assert k==3
        _,idx,nel=struct.unpack_from('<III',T,st+12); return nel,st+12+8
    def tsize(t):
        k,n,sz_,info,ex,st=types[t]
        if k in (1,4,5): return sz_
        if k==2: return 8
        if k in (8,9,10,11): return tsize(sz_)
        if k==3:
            _,idx,nel=struct.unpack_from('<III',T,st+12); return nel*tsize(_)
        return None
    def ptrval(tid):
        k,n,sz_,info,ex,st=types[tid]
        if k==3: return arr(tid)
        if k==2: return ptrval(sz_)  # PTR: size_type field = target type
        return None,None
    res=[]
    for t in types[1:]:
        k,n,sz_,info,ex,st=t
        if k==15 and nm(n)=='.maps':
            for vt,o,sz2 in ex:
                kv,nv,_,_,_,_=types[vt]; var=nm(nv); sty=sz_ if False else types[vt][2]
                sk,sn,ssz,sinfo,sex,sst=types[sty]
                mem={}
                for mn,mt,mo in sex:
                    v,pos=ptrval(mt)
                    if v is None and types[mt][0]==2:
                        v=tsize(types[mt][2]); pos=None
                        mem[nm(mn)]=(v,pos); continue
                    mem[nm(mn)]=(v,pos)
                res.append((var,mem))
    for var,mem in res:
        ty=mem.get('type',(None,))[0]
        print('%-40s type=%-14s max_entries=%s key=%s value=%s flags=%s'%(var,MT.get(ty,ty),mem.get('max_entries',(None,))[0],(mem.get('key_size') or mem.get('key') or (None,))[0],(mem.get('value_size') or mem.get('value') or (None,))[0],mem.get('map_flags',(None,))[0]))
    if '--patch' in sys.argv:
        out=sys.argv[sys.argv.index('--patch')+1]
        for var,mem in res:
            ty,pos=mem['type']
            if ty in (9,10):
                new={9:1,10:5}[ty]; struct.pack_into('<I',B,hdr+toff+pos,new)
                # BTF nelems position relative to T
        d[off:off+sz]=B; open(out,'wb').write(d); print('patched ->',out)
main()
