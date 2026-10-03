import sys, bisect
from datetime import timedelta
sys.argv=['x']
import crypto_lab as cl, crypto_fiel as cf
src=open('crypto_atrbk2.py').read(); exec(src[src.index("def run_pyr"):src.index("YRS=")])
H1=timedelta(hours=1)
def sim1h(d1,d5,sig,trail,pyr,t_from):
    # misma logica que crypto_fiel.sim pero con velas de senal de 1h
    T4,C4,A4=d1["T"],d1["C"],d1["ATR"]; T5=d5["T"]; Ob,Oa,Hb,Ha,Lb,La=d5["Ob"],d5["Oa"],d5["Hb"],d5["Ha"],d5["Lb"],d5["La"]
    n4=d1["n"]; n5=len(T5); tr=[]; pos=None
    def close(px,tm):
        r=0
        for e,te in pos["u"]:
            days=max(0,(tm-te).total_seconds()/86400); r+=((px/e-1) if pos["s"]=="L" else (1-px/e))-cl.SLIP-(cl.FIN_LONG if pos["s"]=="L" else cl.FIN_SHORT)*days
        tr.append({"r":r,"t_in":pos["t"],"t_out":tm,"s":pos["s"],"units":len(pos["u"]),"days":(tm-pos["t"]).total_seconds()/86400})
    t0=max(60,bisect.bisect_left(T4,t_from)); j=bisect.bisect_left(T5,T4[t0]+H1)
    for t in range(t0,n4):
        D=T4[t]+H1; Dn=T4[t+1]+H1 if t+1<n4 else D+H1; act=None
        if pos is None and sig[t]: act=("in",sig[t],A4[t])
        elif pos and pyr and len(pos["u"])<pyr[1]:
            lvl=pos["last"]+(1 if pos["s"]=="L" else -1)*pyr[0]*pos["atr"]
            if (pos["s"]=="L" and C4[t]>=lvl) or (pos["s"]=="S" and C4[t]<=lvl): act=("add",)
        while j<n5 and T5[j]<D: j+=1
        first=True
        while j<n5 and T5[j]<Dn:
            tm=T5[j]
            if first and act:
                if act[0]=="in" and pos is None and act[2]:
                    s=act[1]; e=Oa[j]*(1+cl.SLIP) if s=="L" else Ob[j]*(1-cl.SLIP); dist=trail*act[2]
                    pos={"s":s,"u":[(e,tm)],"t":tm,"ext":e,"stop":e-dist if s=="L" else e+dist,"dist":dist,"atr":act[2],"last":e}
                elif act[0]=="add" and pos:
                    e=Oa[j]*(1+cl.SLIP) if pos["s"]=="L" else Ob[j]*(1-cl.SLIP); pos["u"].append((e,tm)); pos["last"]=e
            first=False
            if pos:
                if pos["s"]=="L" and Lb[j]<=pos["stop"]: close(min(pos["stop"],Ob[j]),tm); pos=None
                elif pos["s"]=="S" and Ha[j]>=pos["stop"]: close(max(pos["stop"],Oa[j]),tm); pos=None
                else:
                    if pos["s"]=="L": pos["ext"]=max(pos["ext"],Hb[j]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                    else: pos["ext"]=min(pos["ext"],La[j]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
            j+=1
    return tr
print(f"{'config 1h':<34} {'act':<4} | {'MODELO 1h 3 anios: n/sem tot% PF':^30} | {'FIEL 5m 2.7 anios: n tot% PF DD':^32} | por anio (fiel)")
for e in ("BTCUSD","ETHUSD"):
    d1=cl.load(e,"HOUR",1100); d5=cf.load5(e); t_from=d5["T"][0]+timedelta(days=2); weeks=(d1["T"][-1]-d1["T"][60]).days/7
    for k,tl,el,py in ((3.0,2.0,800,(2.0,2)),(3.5,2.0,800,(2.0,2)),(3.0,3.0,800,(2.0,2)),(3.5,3.0,800,(2.0,2)),(3.0,2.0,1200,(2.0,2)),(3.5,2.0,1200,(2.0,2)),(3.5,2.0,800,None),(4.0,2.0,800,(2.0,2))):
        sg=cf.atrbk(d1,k,el); m=cl.stats(run_pyr(d1,sg,tl,py[0],py[1]) if py else cl.run(d1,sg,tl,None,("L","S")))
        s=cl.stats(sim1h(d1,d5,sg,tl,py,t_from))
        print(f"k{k} t{tl} EMA{el} {'pir'+str(py[0])+'x'+str(py[1]) if py else 'sin pir':<10} {e[:3]:<4} | {m['n']/weeks:>4.2f}/sem {m['tot']:>+6.0f} {m['pf']:>5.2f} | {s['n']:>4} {s['tot']:>+6.0f} {s['pf']:>5.2f} {s['dd']:>+5.0f} | "+" ".join(f"{y}:{s['years'].get(y,0):+.0f}" for y in sorted(s['years'])))
