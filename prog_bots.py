#!/usr/bin/env python3
"""'Apretar el stop tras una ganancia grande' bot por bot. Senal REAL de cada bot (ventana movil), datos reales.
Base = la salida actual de cada bot (trailing X x ATR, piramide si la tiene, stop comun). Variante: cuando la
ganancia maxima >= M x ATR(entrada), el trailing pasa a k x ATR re-anclado desde el extremo (como capital.com).
Chequeo al cierre de cada vela (como corren los bots). Dos mitades + 6 tramos. Uso: python prog_bots.py BOT [BOT...]"""
import sys, os, json, statistics
from datetime import datetime
BOTS_ARG=[a for a in sys.argv[1:]]; sys.argv=['x','--source','capital']
sys.path.insert(0,'../gold-bot')
import backtest_real as br
def load_mid(epic,res,days):
    O,H,L,C,T=br.fetch_capital(epic,res,days); return O,H,L,C,[t.replace(tzinfo=None) for t in T]
def precompute(O,H,L,C,fn,W):
    n=len(C); sig=[None]*n; atr=[None]*n
    for t in range(W,n):
        lo=t-W+1; s=fn(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
        if s and s.get("side") and s.get("atr"): sig[t]=s["side"]; atr[t]=s["atr"]
        elif s and s.get("atr"): atr[t]=s["atr"]
    return sig,atr
def sim(D,sig,atr,trail,cost,W,M=None,k=None,pyr=None,gaps=False,fin_long=0.0,bar_days=0.0):
    O,H,L,C,T=D; n=len(C); tr=[]; pos=None
    for t in range(W,n):
        if pos:
            sg=pos["sg"]; ex=None
            if sg==1 and L[t]<=pos["stop"]: ex=min(pos["stop"],O[t]) if gaps else pos["stop"]
            elif sg==-1 and H[t]>=pos["stop"]: ex=max(pos["stop"],O[t]) if gaps else pos["stop"]
            if ex is not None:
                net=0
                for e,t0 in pos["u"]: net+=sg*(ex-e)-cost-(fin_long*e*(t-t0)*bar_days if sg==1 else 0)
                tr.append({"net":net,"t":T[pos["t0"]]}); pos=None
            else:
                pos["x"]=max(pos["x"],H[t]) if sg==1 else min(pos["x"],L[t])
                if M and not pos["tight"] and sg*(pos["x"]-pos["u"][0][0])>=M*pos["atr"]:
                    pos["d"]=k*pos["atr"]; pos["tight"]=True
                pos["stop"]=max(pos["stop"],pos["x"]-pos["d"]) if sg==1 else min(pos["stop"],pos["x"]+pos["d"])
                if pyr and len(pos["u"])<pyr[1]:
                    lvl=pos["u"][-1][0]+sg*pyr[0]*pos["atr"]
                    if (sg==1 and C[t]>=lvl) or (sg==-1 and C[t]<=lvl): pos["u"].append((C[t],t))
            continue
        s=sig[t]
        if not s: continue
        if gaps and (t+1>=n or (T[t+1]-T[t]).total_seconds()>1350): continue
        sg=1 if s in ("BUY","L") else -1; d=trail*atr[t]
        pos={"sg":sg,"u":[(C[t],t)],"x":C[t],"d":d,"atr":atr[t],"stop":C[t]-sg*d,"t0":t,"tight":False}
    return tr
def st(tr):
    tot=sum(x["net"] for x in tr); w=sum(x["net"] for x in tr if x["net"]>0); l=-sum(x["net"] for x in tr if x["net"]<=0)
    eq=pk=dd=0
    for x in tr: eq+=x["net"]; pk=max(pk,eq); dd=min(dd,eq-pk)
    return tot,(w/l if l else 9),dd
def analizar(nombre,D,sig,atr,trail,cost,W,Ms,ks,unit_usd,**kw):
    T=D[4]; mid=T[len(T)//2]; t0=T[W]; span=(T[-1]-t0)/6
    def seg6(tr):
        o=[0.0]*6
        for x in tr: o[min(5,int((x["t"]-t0)/span))]+=x["net"]
        return o
    b=sim(D,sig,atr,trail,cost,W,**kw); b1=st([x for x in b if x["t"]<mid]); b2=st([x for x in b if x["t"]>=mid]); bt_=st(b); s0=seg6(b)
    print(f"\n######## {nombre}: {len(b)} ops | {T[W]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | ACTUAL trailing {trail}x: total {bt_[0]:+.0f} pts (~${bt_[0]*unit_usd:+.0f}) PF {bt_[2] and bt_[1]:.2f} DD {bt_[2]:+.0f} | mitades {b1[0]:+.0f} / {b2[0]:+.0f}")
    print("   celda = mejora % del total (mitad1/mitad2 en pts) ; * = mejora en ambas mitades y >=4/6 tramos")
    print(f"   {'umbral':>8} | "+" | ".join(f"{'->'+str(k)+'x':^22}" for k in ks))
    grid={}
    for M in Ms:
        cells=[]
        for k in ks:
            tr=sim(D,sig,atr,trail,cost,W,M=M,k=k,**kw); a=st([x for x in tr if x["t"]<mid]); c=st([x for x in tr if x["t"]>=mid]); tt=st(tr); s=seg6(tr)
            imp=100*(tt[0]-bt_[0])/abs(bt_[0]) if bt_[0] else 0; nseg=sum(1 for x,y in zip(s,s0) if x>y+1e-9)
            ok=a[0]>b1[0] and c[0]>b2[0] and nseg>=4
            grid[(M,k)]=(imp,ok,tt,a,c,nseg)
            cells.append(f"{imp:>+5.0f}% {a[0]-b1[0]:>+6.0f}/{c[0]-b2[0]:<+6.0f}{'*' if ok else ' '}")
        print(f"   +{M:>4}xATR | "+" | ".join(f"{x:^22}" for x in cells))
    oks=[(v[0],key) for key,v in grid.items() if v[1]]
    print(f"   celdas que mejoran en ambas mitades: {len(oks)}/{len(grid)}")
    if oks:
        best=max(oks)[1]; v=grid[best]
        # meseta: vecinos inmediatos que tambien cumplen
        Mi=Ms.index(best[0]); ki=ks.index(best[1]); vec=[(Ms[i],ks[j]) for i in (Mi-1,Mi,Mi+1) for j in (ki-1,ki,ki+1) if 0<=i<len(Ms) and 0<=j<len(ks) and (i,j)!=(Mi,ki)]
        nv=sum(1 for q in vec if grid[q][1])
        print(f"   MEJOR: tras +{best[0]}xATR -> {best[1]}x: total {v[2][0]:+.0f} pts (~${v[2][0]*unit_usd:+.0f}, {v[0]:+.0f}%) PF {v[2][1]:.2f} DD {v[2][2]:+.0f} | mitades {v[3][0]:+.0f}/{v[4][0]:+.0f} | tramos {v[5]}/6 | vecinos que tambien mejoran: {nv}/{len(vec)}")
    return grid
if __name__=="__main__":
    import bot_sp500 as sp, bot_us30 as us, bot_us100 as nq, bot_rty as rt, bot_nl25 as nl, bot_us30_rf as rf, bot_gold as bg
    CFG={
     "SP500":   lambda: ("US500","MINUTE_15",300,sp.signal_last,sp.TRAIL_ATR,0.6,300,1.0,{}),
     "US30":    lambda: ("US30","MINUTE_15",300,us.signal_last,us.TRAIL_ATR,2.0,300,0.1,{}),
     "US100":   lambda: ("US100","MINUTE_15",300,nq.signal_last,nq.TRAIL_ATR,1.8,300,0.1,{}),
     "RTY":     lambda: ("RTY","MINUTE_15",300,rt.signal_last,rt.TRAIL_ATR,0.5,300,1.0,{}),
     "NL25":    lambda: ("NL25","MINUTE_15",300,nl.signal_last,nl.TRAIL_ATR,0.1,300,5.0,{"gaps":True}),
     "US30RF":  lambda: ("US30","HOUR",600,rf.signal_last,rf.TRAIL_ATR,2.0,200,0.12,{}),
     "BOLL_ORO":lambda: ("GOLD","MINUTE_15",600,bg.signal_last,bg.TRAIL_ATR,0.6,300,0.8,{"pyr":(bg.PYR_STEP,bg.PYR_MAX)}),
    }
    for name in BOTS_ARG:
        epic,res,days,fn,trail,cost,W,usd,kw=CFG[name]()
        D=load_mid(epic,res,days); sig,atr=precompute(*D[:4],fn,W)
        if trail>=4: Ms,ks=[4,6,8,10,12,15],[1.5,2.0,2.5,3.0,4.0 if trail>=5 else 3.5]
        elif trail>=3: Ms,ks=[3,4,6,8,10,12],[1.0,1.5,2.0,2.5]
        else: Ms,ks=[2,3,4,5,6,8],[0.75,1.0,1.25,1.5]
        analizar(name,D,sig,atr,trail,cost,W,Ms,ks,usd,**kw)
