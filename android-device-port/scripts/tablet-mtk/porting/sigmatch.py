import struct
HINTS={0xd503233f,0xd50323bf,0xd503245f,0xd503249f,0xd50324df,0xd503201f}
def norm(w):
    top=w>>24
    if (w>>26) in (0x05,0x25): return w & 0xfc000000                 # b / bl
    if top==0x54: return w & 0xff00001f                               # b.cond
    if top in (0x34,0x35,0xb4,0xb5): return w & 0xff000000 | (w&31)   # cbz/cbnz
    if top in (0x36,0x37,0xb6,0xb7): return w & 0xfff8001f            # tbz/tbnz
    if (w&0x9f000000)==0x90000000: return w & 0x9f00001f              # adrp
    if (w&0x9f000000)==0x10000000: return w & 0x9f00001f              # adr
    if (w&0xff000000)==0x58000000: return w & 0xff00001f              # ldr literal
    if (w&0xffc00000)==0x91000000: return w & 0xffc003ff              # add imm: mask imm12
    if (w&0x3b000000)==0x39000000: return w & 0xffc003ff              # ldr/str unsigned imm: mask imm12
    return w
def stream(d,limit=None):
    n=(limit or len(d))//4; W=struct.unpack_from('<%dI'%n,d,0)
    return [(i*4,norm(w),w) for i,w in enumerate(W) if w not in HINTS]
def locate(old,new,addr,win=8,ostream=None,nstream=None):
    os_=ostream or stream(old); ns=nstream or stream(new)
    idx=next(k for k,(a,_,_) in enumerate(os_) if a==addr)
    res=[]
    for w in (win,win+4,win+8,win+16):
        lo=max(0,idx-w); hi=min(len(os_),idx+w+1)
        pat=[x[1] for x in os_[lo:hi]]; off=idx-lo
        hits=[]
        n=len(pat)
        keys=[x[1] for x in ns]
        for k in range(len(ns)-n):
            if keys[k:k+n]==pat: hits.append(ns[k+off][0])
        if len(hits)==1: return hits[0],w
        res=hits
    return None,res
