#!/usr/bin/env python3
"""ATR-breakout 4h BTC+ETH: variantes (filtro EMA, piramide) y PORTAFOLIO (suma de ambos).
Costos reales. Por anio y relacion ganancia/caida."""
import crypto_lab as cl
data={e:cl.load(e,"HOUR_4",2200) for e in ("BTCUSD","ETHUSD")}
def atrbk(d,k,ema_len=None):
    C,A=d["C"],d["ATR"]; n=d["n"]; s=[None]*n; E=cl.ema(C,ema_len) if ema_len else None
    for t in range(15,n):
        if A[t-1] and C[t]-C[t-1]>k*A[t-1] and (E is None or C[t]>E[t]): s[t]="L"
        elif A[t-1] and C[t-1]-C[t]>k*A[t-1] and (E is None or C[t]<E[t]): s[t]="S"
    return s
def run_pyr(d,sig,trail,step,maxu):
    """como cl.run pero piramidando: con la posicion ganando step x ATR(entrada) al CIERRE, agrega 1 unidad
    a la apertura siguiente (mismo stop comun). Devuelve trades con r = suma de unidades."""
    O,C,T,A=d["O"],d["C"],d["T"],d["ATR"]; Ob,Oa,Hb,Ha,Lb,La=d["Ob"],d["Oa"],d["Hb"],d["Ha"],d["Lb"],d["La"]; n=d["n"]
    tr=[]; pos=None; pend=None; add=False
    def close(ex,tout):
        days=max(0,(tout-pos["t"]).total_seconds()/86400); r=0
        for e,te in pos["u"]:
            dd=max(0,(tout-te).total_seconds()/86400)
            r+=((ex/e-1) if pos["s"]=="L" else (1-ex/e))-cl.SLIP-(cl.FIN_LONG if pos["s"]=="L" else cl.FIN_SHORT)*dd
        tr.append({"r":r,"t_in":pos["t"],"t_out":tout,"s":pos["s"],"days":days,"units":len(pos["u"])})
    for t in range(60,n):
        if add and pos:
            px=Oa[t]*(1+cl.SLIP) if pos["s"]=="L" else Ob[t]*(1-cl.SLIP); pos["u"].append((px,T[t])); pos["last"]=px
        add=False
        if pend and pos is None:
            s=pend; e=Oa[t]*(1+cl.SLIP) if s=="L" else Ob[t]*(1-cl.SLIP); a=A[t-1]
            pos={"s":s,"u":[(e,T[t])],"t":T[t],"ext":e,"stop":e-trail*a if s=="L" else e+trail*a,"dist":trail*a,"atr":a,"last":e}
        pend=None
        if pos:
            if pos["s"]=="L" and Lb[t]<=pos["stop"]: close(min(pos["stop"],Ob[t]),T[t]); pos=None
            elif pos["s"]=="S" and Ha[t]>=pos["stop"]: close(max(pos["stop"],Oa[t]),T[t]); pos=None
            else:
                if pos["s"]=="L": pos["ext"]=max(pos["ext"],Hb[t]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                else: pos["ext"]=min(pos["ext"],La[t]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
        if t+1>=n: break
        if pos:
            if maxu>1 and len(pos["u"])<maxu:
                lvl=pos["last"]+(1 if pos["s"]=="L" else -1)*step*pos["atr"]
                if (pos["s"]=="L" and C[t]>=lvl) or (pos["s"]=="S" and C[t]<=lvl): add=True
            continue
        if sig[t]: pend=sig[t]
    if pos: close(C[n-1],T[n-1])
    return tr
YRS=list(range(2020,2027))
def port(trs):
    allt=sorted([x for tr in trs for x in tr],key=lambda x:x["t_out"]); eq=pk=dd=0
    for x in allt: eq+=x["r"]; pk=max(pk,eq); dd=min(dd,eq-pk)
    yrs={y:100*sum(x["r"] for x in allt if x["t_in"].year==y) for y in YRS}
    return 100*eq,100*dd,yrs,len(allt)
def line(name,trs):
    tot,dd,yrs,n=port(trs); pb=cl.stats(trs[0])["pf"]; pe=cl.stats(trs[1])["pf"]; weeks=318
    print(f"{name:<40} | PF B/E {pb:.2f}/{pe:.2f} | cartera {tot:>+5.0f}% DD {dd:>+5.0f}% gan/caida {tot/abs(dd):>4.1f} | {n/weeks:.2f}/sem | "+" ".join(f"{y}:{yrs[y]:+4.0f}" for y in YRS)+f" | anios+ {sum(1 for y in YRS if yrs[y]>0)}/7")
print("cartera = BTC + ETH, 1 unidad cada uno, % sumados\n")
for k,t in ((3.0,3.0),(3.0,2.0),(3.5,3.0)):
    print(f"--- k{k} trail{t} ---")
    line("base 2 lados",[cl.run(d,atrbk(d,k),t,None,("L","S")) for d in data.values()])
    for el in (50,100,200): line(f"  + filtro EMA{el}",[cl.run(d,atrbk(d,k,el),t,None,("L","S")) for d in data.values()])
    for st,mu in ((1.0,2),(2.0,2),(3.0,2),(2.0,3)): line(f"  + piramide +1 cada {st}xATR max {mu}",[run_pyr(d,atrbk(d,k),t,st,mu) for d in data.values()])
