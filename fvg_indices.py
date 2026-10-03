#!/usr/bin/env python3
"""FVG en INDICES con velas 15m bid/ask y regla CONSERVADORA (sin TP en la vela del llenado, SL si).
Se calibra contra el simulador fiel 1m en oro. Dos mitades de 300d. Uso: python fvg_indices.py EPIC [EPIC...]"""
import sys, os, json
from datetime import datetime, timedelta
import backtest_real as br, fvg_sim1m as s1, fvg_bidask as ba
fv=br._import_fvg(); base=dict(TP_R=fv.TP_R,SL_MULT=fv.SL_MULT,FILL_WIN=fv.FILL_WIN,MIN_GAP=fv.MIN_GAP,EMA_TREND=fv.EMA_TREND,MAX_GAP=fv.MAX_GAP)
def setp(**kw):
    for k,v in base.items(): setattr(fv,k,v)
    for k,v in kw.items(): setattr(fv,k,v)
def load15(epic,days=600):
    d=json.load(open(os.path.join(br.DATA_DIR,f"capital_{epic}_MINUTE_15_{days}d_bidask.json"))); d["T"]=[datetime.fromisoformat(t) for t in d["T"]]; return d
def sim_cons(d, trail=None):
    """15m bid/ask; llenado con ask/bid; en la vela del llenado solo puede saltar el SL (nunca el TP)."""
    O,H,L,C=ba.mids(d); T=d["T"]; n=len(C); WIN=s1.WIN; tr=[]; pos=None; order=None
    Ob,Hb,Lb,Oa,Ha,La=d["Ob"],d["Hb"],d["Lb"],d["Oa"],d["Ha"],d["La"]
    def ex_of(t,first):
        long=pos["side"]=="BUY"
        if long:
            if Lb[t]<=pos["sl"]: return pos["sl"]
            if pos["tp"] and not first and Hb[t]>=pos["tp"]: return pos["tp"]
        else:
            if Ha[t]>=pos["sl"]: return pos["sl"]
            if pos["tp"] and not first and La[t]<=pos["tp"]: return pos["tp"]
        return None
    for t in range(WIN,n):
        if pos:
            ex=ex_of(t,False)
            if ex is None and pos.get("dist"):
                if pos["side"]=="BUY": pos["ext"]=max(pos["ext"],Hb[t]); pos["sl"]=max(pos["sl"],pos["ext"]-pos["dist"])
                else: pos["ext"]=min(pos["ext"],La[t]); pos["sl"]=min(pos["sl"],pos["ext"]+pos["dist"])
            if ex is not None:
                g=(ex-pos["entry"]) if pos["side"]=="BUY" else (pos["entry"]-ex); tr.append({"net":g,"t_in":pos["t_in"],"t_out":T[t]}); pos=None
            continue
        if order:
            long=order["side"]=="BUY"
            hit=(long and La[t]<=order["level"]) or ((not long) and Hb[t]>=order["level"])
            if hit:
                e=order["level"]; d_=order.get("dist")
                pos={"side":order["side"],"entry":e,"sl":(e-d_ if long else e+d_) if d_ else order["sl"],"tp":None if d_ else order["tp"],"dist":d_,"ext":e,"t_in":T[t]}; order=None
                ex=ex_of(t,True)
                if ex is not None:
                    g=(ex-pos["entry"]) if pos["side"]=="BUY" else (pos["entry"]-ex); tr.append({"net":g,"t_in":pos["t_in"],"t_out":T[t]}); pos=None
                continue
            elif t>=order["expiry"]: order=None
        if pos is None and order is None:
            lo=t-WIN+1; s=fv.find_pending_fvg_ohlc(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
            if s and s.get("side"):
                if (s["side"]=="BUY" and s["level"]>=d["Ca"][t]) or (s["side"]=="SELL" and s["level"]<=d["Cb"][t]): continue
                dist=None
                if trail:
                    a=fv.atr_series(H[lo:t+1],L[lo:t+1],C[lo:t+1],fv.ATR_LEN)[-1]; dist=trail*a
                order={"side":s["side"],"level":s["level"],"sl":s["sl"],"tp":s["tp"],"dist":dist,"expiry":t+s["remaining_bars"]}
    return tr
def halves(tr,T):
    mid=T[len(T)//2]; a=s1.stats([x for x in tr if x["t_in"]<mid]); b=s1.stats([x for x in tr if x["t_in"]>=mid]); return a,b
def table(epic,d):
    T=d["T"]; print(f"\n===== {epic}: {len(T)} velas {T[0]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | mitad 1 | mitad 2 (300d c/u) =====")
    print(f"{'config':<24} | {'tr':>4} {'neto':>7} {'PF':>5} {'acc':>4} | {'tr':>4} {'neto':>7} {'PF':>5} {'acc':>4} {'DD':>6}")
    for sl_,tp_ in ((2.0,0.75),(1.5,1.0),(1.5,1.5),(1.0,2.0),(1.0,3.0),(2.0,2.0)):
        setp(SL_MULT=sl_,TP_R=tp_); a,b=halves(sim_cons(d),T)
        ok=" <<<" if a["tot"]>0 and b["tot"]>0 and a["pf"]>1.1 and b["pf"]>1.1 else ""
        print(f"SL{sl_}/TP{tp_:<16} | {a['n']:>4} {a['tot']:>+7.0f} {a['pf']:>5.2f} {a['acc']:>3.0f}% | {b['n']:>4} {b['tot']:>+7.0f} {b['pf']:>5.2f} {b['acc']:>3.0f}% {b['dd']:>+6.0f}{ok}")
    setp()
    for k in (3.0,5.0): 
        a,b=halves(sim_cons(d,trail=k),T); ok=" <<<" if a["tot"]>0 and b["tot"]>0 and a["pf"]>1.1 and b["pf"]>1.1 else ""
        print(f"{'trailing '+str(k)+'xATR':<24} | {a['n']:>4} {a['tot']:>+7.0f} {a['pf']:>5.2f} {a['acc']:>3.0f}% | {b['n']:>4} {b['tot']:>+7.0f} {b['pf']:>5.2f} {b['acc']:>3.0f}% {b['dd']:>+6.0f}{ok}")
if __name__=="__main__":
    if "--calibrar" in sys.argv:
        d=load15("GOLD",600); dG15,dG1=s1.load(1000); cutd=d["T"][0]
        setp(); c=s1.stats(sim_cons(d)); f=s1.stats([x for x in s1.sim(dG15,dG1,fv,a=cutd) if x["t_in"]>=cutd])
        print(f"CALIBRACION oro 600d, config actual: 15m-conservador {c['n']} tr {c['tot']:+.0f} PF{c['pf']:.2f} acc{c['acc']:.0f}% | fiel 1m {f['n']} tr {f['tot']:+.0f} PF{f['pf']:.2f} acc{f['acc']:.0f}%")
        setp(SL_MULT=1.5,TP_R=1.5); c=s1.stats(sim_cons(d)); f=s1.stats([x for x in s1.sim(dG15,dG1,fv,a=cutd) if x["t_in"]>=cutd])
        print(f"CALIBRACION oro 600d, SL1.5/TP1.5:  15m-conservador {c['n']} tr {c['tot']:+.0f} PF{c['pf']:.2f} | fiel 1m {f['n']} tr {f['tot']:+.0f} PF{f['pf']:.2f}"); setp()
    for e in [a for a in sys.argv[1:] if not a.startswith("--")]:
        try: table(e,load15(e,600))
        except FileNotFoundError: print(f"{e}: sin datos aun")
