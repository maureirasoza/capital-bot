#!/usr/bin/env python3
"""Bot CRIPTO (ATR-breakout 4h, EMA200, trailing 2x, piramide 2x): apretar tras ganancia grande. Costos reales
(bid/ask, financiamiento largo, desliz). Cartera BTC+ETH en % por unidad. Mitades + 6 tramos."""
import crypto_lab as cl, crypto_fiel as cf
data={e:cl.load(e,"HOUR_4",2200) for e in ("BTCUSD","ETHUSD")}
def run(d,sig,trail,step,maxu,M=None,k=None):
    O,C,T,A=d["O"],d["C"],d["T"],d["ATR"]; Ob,Oa,Hb,Ha,Lb,La=d["Ob"],d["Oa"],d["Hb"],d["Ha"],d["Lb"],d["La"]; n=d["n"]
    tr=[]; pos=None; pend=None; add=False
    def close(ex,tout):
        r=0
        for e,te in pos["u"]:
            dd=max(0,(tout-te).total_seconds()/86400); r+=((ex/e-1) if pos["s"]=="L" else (1-ex/e))-cl.SLIP-(cl.FIN_LONG if pos["s"]=="L" else cl.FIN_SHORT)*dd
        tr.append({"r":r,"t_in":pos["t"]})
    for t in range(60,n):
        if add and pos:
            px=Oa[t]*(1+cl.SLIP) if pos["s"]=="L" else Ob[t]*(1-cl.SLIP); pos["u"].append((px,T[t])); pos["last"]=px
        add=False
        if pend and pos is None:
            s=pend; e=Oa[t]*(1+cl.SLIP) if s=="L" else Ob[t]*(1-cl.SLIP); a=A[t-1]
            pos={"s":s,"u":[(e,T[t])],"t":T[t],"ext":e,"stop":e-trail*a if s=="L" else e+trail*a,"dist":trail*a,"atr":a,"last":e,"e0":e,"tight":False}
        pend=None
        if pos:
            if pos["s"]=="L" and Lb[t]<=pos["stop"]: close(min(pos["stop"],Ob[t]),T[t]); pos=None
            elif pos["s"]=="S" and Ha[t]>=pos["stop"]: close(max(pos["stop"],Oa[t]),T[t]); pos=None
            else:
                sg=1 if pos["s"]=="L" else -1
                pos["ext"]=max(pos["ext"],Hb[t]) if sg==1 else min(pos["ext"],La[t])
                if M and not pos["tight"] and sg*(pos["ext"]-pos["e0"])>=M*pos["atr"]: pos["dist"]=k*pos["atr"]; pos["tight"]=True
                pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"]) if sg==1 else min(pos["stop"],pos["ext"]+pos["dist"])
        if t+1>=n: break
        if pos:
            if maxu>1 and len(pos["u"])<maxu:
                lvl=pos["last"]+(1 if pos["s"]=="L" else -1)*step*pos["atr"]
                if (pos["s"]=="L" and C[t]>=lvl) or (pos["s"]=="S" and C[t]<=lvl): add=True
            continue
        if sig[t]: pend=sig[t]
    return tr
SG={e:cf.atrbk(d,3.0,200) for e,d in data.items()}
def cartera(M=None,k=None):
    trs=[x for e,d in data.items() for x in run(d,SG[e],2.0,2.0,2,M,k)]; return sorted(trs,key=lambda x:x["t_in"])
def st(tr):
    tot=100*sum(x["r"] for x in tr); w=sum(x["r"] for x in tr if x["r"]>0); l=-sum(x["r"] for x in tr if x["r"]<=0)
    eq=pk=dd=0
    for x in tr: eq+=x["r"]; pk=max(pk,eq); dd=min(dd,eq-pk)
    return tot,(w/l if l else 9),100*dd
base=cartera(); T0=base[0]["t_in"]; T1=base[-1]["t_in"]; mid=T0+(T1-T0)/2; span=(T1-T0)/6
def seg6(tr):
    o=[0.0]*6
    for x in tr: o[min(5,int((x["t_in"]-T0)/span))]+=x["r"]
    return o
b1=st([x for x in base if x["t_in"]<mid]); b2=st([x for x in base if x["t_in"]>=mid]); bt_=st(base); s0=seg6(base)
print(f"######## CRIPTO BTC+ETH 4h: {len(base)} ops | ACTUAL trailing 2x: cartera {bt_[0]:+.0f}% PF {bt_[1]:.2f} DD {bt_[2]:+.0f}% | mitades {b1[0]:+.0f}% / {b2[0]:+.0f}%")
Ms=[2,3,4,5,6,8,10]; ks=[0.75,1.0,1.25,1.5]
print(f"   {'umbral':>8} | "+" | ".join(f"{'->'+str(k)+'x':^22}" for k in ks)); ok=[]
for M in Ms:
    cells=[]
    for k in ks:
        tr=cartera(M,k); a=st([x for x in tr if x["t_in"]<mid]); c=st([x for x in tr if x["t_in"]>=mid]); tt=st(tr); s=seg6(tr)
        nseg=sum(1 for x,y in zip(s,s0) if x>y+1e-12); good=a[0]>b1[0] and c[0]>b2[0] and nseg>=4
        if good: ok.append((tt[0],M,k,tt,a,c,nseg))
        cells.append(f"{100*(tt[0]-bt_[0])/abs(bt_[0]):>+5.0f}% {a[0]-b1[0]:>+5.0f}/{c[0]-b2[0]:<+5.0f}{'*' if good else ' '}")
    print(f"   +{M:>4}xATR | "+" | ".join(f"{x:^22}" for x in cells))
print(f"   celdas que mejoran en ambas mitades: {len(ok)}/{len(Ms)*len(ks)}")
if ok:
    x=max(ok); print(f"   MEJOR: tras +{x[1]}xATR -> {x[2]}x: cartera {x[3][0]:+.0f}% PF {x[3][1]:.2f} DD {x[3][2]:+.0f}% | mitades {x[4][0]:+.0f}/{x[5][0]:+.0f} | tramos {x[6]}/6")
