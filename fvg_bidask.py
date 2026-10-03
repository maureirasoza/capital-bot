#!/usr/bin/env python3
"""Simulador FVG con precios BID/ASK reales de capital.com (no precio medio + spread fijo).
La senal se calcula con el precio medio (igual que el bot); la EJECUCION usa el lado correcto:
  compra limite: se llena cuando el ASK baja al nivel; su TP/SL se ejecutan contra el BID.
  venta limite : se llena cuando el BID sube al nivel; su TP/SL se ejecutan contra el ASK.
Modulo reutilizable: fetch_ba(), sim_ba(), sim_mid(), stats()."""
import os, sys, json, time
from datetime import datetime, timedelta, timezone
import backtest_real as br
DATA=br.DATA_DIR; WIN=br.WIN_FVG

def fetch_ba(epic="GOLD", resolution="MINUTE_15", days=600, step_days=10, refresh=False):
    path=os.path.join(DATA,f"capital_{epic}_{resolution}_{days}d_bidask.json")
    if os.path.exists(path) and not refresh:
        d=json.load(open(path)); d["T"]=[datetime.fromisoformat(t) for t in d["T"]]; return d
    import capital_client as cc
    h=cc.login(); now=datetime.now(timezone.utc).replace(tzinfo=None); rows={}; d0=0
    while d0<days:
        d1=min(d0+step_days,days)
        frm=(now-timedelta(days=d1)).strftime("%Y-%m-%dT%H:%M:%S"); to=(now-timedelta(days=d0)).strftime("%Y-%m-%dT%H:%M:%S")
        r=cc.get(h,f"/api/v1/prices/{epic}?resolution={resolution}&from={frm}&to={to}&max=1000")
        if r.status_code==200:
            for p in r.json().get("prices",[]):
                try: dt=datetime.fromisoformat((p.get("snapshotTimeUTC") or "").replace("Z",""))
                except ValueError: continue
                rows[dt]=[p[k][s] for s in ("bid","ask") for k in ("openPrice","highPrice","lowPrice","closePrice")]
        d0=d1; time.sleep(0.35)
    ts=sorted(rows); keys=("Ob","Hb","Lb","Cb","Oa","Ha","La","Ca")
    d={k:[rows[t][i] for t in ts] for i,k in enumerate(keys)}; d["T"]=[t.isoformat() for t in ts]
    json.dump(d,open(path,"w")); d["T"]=ts
    print(f"[bajado] {os.path.basename(path)}: {len(ts)} velas {ts[0]:%Y-%m-%d} -> {ts[-1]:%Y-%m-%d}")
    return d

def mids(d):
    m=lambda a,b:[(x+y)/2 for x,y in zip(d[a],d[b])]
    return m("Ob","Oa"),m("Hb","Ha"),m("Lb","La"),m("Cb","Ca")

def sim_ba(d, fv, a=0, b=None, sigfn=None, extra=None):
    """Ejecucion bid/ask. sigfn(O,H,L,C)->setup (default: la funcion REAL del bot). extra(setup,t)->bool filtro."""
    O,H,L,C=mids(d); T=d["T"]; n=len(C) if b is None else b
    sigfn=sigfn or fv.find_pending_fvg_ohlc
    trades=[]; pos=None; order=None
    def exit_px(t):
        if pos["side"]=="BUY":
            if d["Lb"][t]<=pos["sl"]: return min(pos["sl"],d["Ob"][t]) if d["Ob"][t]<pos["sl"] else pos["sl"]
            if d["Hb"][t]>=pos["tp"]: return pos["tp"]
        else:
            if d["Ha"][t]>=pos["sl"]: return max(pos["sl"],d["Oa"][t]) if d["Oa"][t]>pos["sl"] else pos["sl"]
            if d["La"][t]<=pos["tp"]: return pos["tp"]
        return None
    def book(t,ex):
        nonlocal pos
        g=(ex-pos["entry"]) if pos["side"]=="BUY" else (pos["entry"]-ex)
        trades.append({"side":pos["side"],"entry":pos["entry"],"exit":ex,"t_in":pos["t_in"],"t_out":T[t],"net":g,"gross":g,
                       "sl":pos["sl"],"tp":pos["tp"],"t_sig":pos["t_sig"],"meta":pos.get("meta")}); pos=None
    for t in range(max(a,WIN),n):
        if pos:
            ex=exit_px(t)
            if ex is not None: book(t,ex)
            continue
        if order:
            hit=(order["side"]=="BUY" and d["La"][t]<=order["level"]) or (order["side"]=="SELL" and d["Hb"][t]>=order["level"])
            if hit:
                pos={"side":order["side"],"entry":order["level"],"sl":order["sl"],"tp":order["tp"],"t_in":T[t],"t_sig":order["t_sig"],"meta":order.get("meta")}; order=None
                ex=exit_px(t)
                if ex is not None: book(t,ex)
                continue
            elif t>=order["expiry"]: order=None
        if pos is None and order is None:
            lo=t-WIN+1; sig=sigfn(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
            if sig and sig.get("side"):
                # guarda del bot: el nivel debe seguir del lado correcto del precio actual
                if (sig["side"]=="BUY" and sig["level"]>=d["Ca"][t]) or (sig["side"]=="SELL" and sig["level"]<=d["Cb"][t]): continue
                if extra and not extra(sig,t): continue
                order={"side":sig["side"],"level":sig["level"],"sl":sig["sl"],"tp":sig["tp"],"expiry":t+sig["remaining_bars"],"t_sig":T[t],"meta":sig}
    return trades

def stats(tr,k=3,a=None,b=None,T=None):
    if not tr: return dict(n=0,tot=0,pf=0,acc=0,dd=0,seg=[0]*k,rob=0,w=0,l=0)
    tot=sum(x["net"] for x in tr); w=[x["net"] for x in tr if x["net"]>0]; l=[-x["net"] for x in tr if x["net"]<=0]
    eq=pk=dd=0
    for x in tr: eq+=x["net"]; pk=max(pk,eq); dd=min(dd,eq-pk)
    t0=tr[0]["t_in"]; t1=tr[-1]["t_in"]; span=(t1-t0)/k if t1>t0 else timedelta(days=1); seg=[0.0]*k
    for x in tr: seg[min(k-1,int((x["t_in"]-t0)/span))]+=x["net"]
    return dict(n=len(tr),tot=tot,pf=sum(w)/sum(l) if l else 9,acc=100*len(w)/len(tr),dd=dd,seg=seg,rob=sum(1 for v in seg if v>0),
                w=sum(w)/len(w) if w else 0,l=sum(l)/len(l) if l else 0)

if __name__=="__main__":
    fv=br._import_fvg()
    d=fetch_ba("GOLD","MINUTE_15",600,refresh="--refresh" in sys.argv); T=d["T"]; n=len(T)
    spr=[a-b for a,b in zip(d["Ca"],d["Cb"])]; print(f"{n} velas {T[0]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | spread medio {sum(spr)/n:.3f} (min {min(spr):.2f} max {max(spr):.2f})")
    O,H,L,C=mids(d); Tz=[t.replace(tzinfo=timezone.utc) for t in T]
    print("\n== MODELO precio medio + spread fijo  vs  MODELO bid/ask real (config actual del bot) ==")
    br.SPREAD=0.3; m=stats(br.simulate_fvg(O,H,L,C,Tz,fv)); ba_tr=sim_ba(d,fv); x=stats(ba_tr)
    for nm,r in (("medio + 0.6 fijo",m),("BID/ASK real",x)):
        print(f"  {nm:<18} {r['n']:>5} tr | neto {r['tot']:>+7.0f} | PF {r['pf']:.2f} | acierto {r['acc']:.1f}% | gan.media {r['w']:.2f} perd.media {r['l']:.2f} | DD {r['dd']:+.0f} | tercios {r['seg'][0]:+.0f}/{r['seg'][1]:+.0f}/{r['seg'][2]:+.0f}")
    print("\n== RECONCILIACION: simulador bid/ask desde el 24-sep 11:30 UTC (comparar con las 23 reales) ==")
    rec=[t for t in ba_tr if t["t_in"]>=datetime(2026,9,24,11,30)]
    for t in rec: print(f"  {t['t_in']:%m-%d %H:%M} {t['side']:<4} @ {t['entry']:<8} SL {t['sl']:<8} TP {t['tp']:<8} -> {t['t_out']:%m-%d %H:%M} {t['net']:>+6.2f}")
    r=stats(rec); print(f"  simulador: {r['n']} tr, {r['acc']:.0f}% acierto, neto {r['tot']:+.1f} pts (gan {r['w']:.2f} / perd {r['l']:.2f})")
