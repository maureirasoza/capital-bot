#!/usr/bin/env python3
"""Descarga GOLD bid/ask de capital.com: 15m (senales) y 1m (ejecucion) para N dias.
REANUDABLE: guarda avance parcial cada 60 ventanas y retoma donde quedo (reintenta login ante red caida).
Uso: python fvg_descarga_1m.py DIAS"""
import os, sys, json, time
from datetime import datetime, timedelta, timezone
import capital_client as cc, backtest_real as br
DAYS=int(sys.argv[1]) if len(sys.argv)>1 else 600
def login_robusto():
    for i in range(20):
        try: return cc.login()
        except (SystemExit, Exception) as e:
            print(f"  login fallo ({str(e)[:60]}), reintento en 15s",flush=True); time.sleep(15)
    raise SystemExit("sin red")
def bajar(res, step, tag):
    path=os.path.join(br.DATA_DIR,f"capital_GOLD_{res}_{DAYS}d_bidask.json"); part=path+".parcial"
    if os.path.exists(path): print("ya existe",path); return
    now=datetime.now(timezone.utc).replace(tzinfo=None); end=now-timedelta(days=DAYS)
    rows={}; to=now
    if os.path.exists(part):
        p=json.load(open(part)); rows={datetime.fromisoformat(k):v for k,v in p["rows"].items()}; to=datetime.fromisoformat(p["to"]); print(f"  {tag}: retomo desde {to:%Y-%m-%d} con {len(rows)} velas",flush=True)
    h=login_robusto(); t_login=time.time(); k=0
    while to>end:
        frm=to-step
        if time.time()-t_login>420: h=login_robusto(); t_login=time.time()
        r=None
        for intento in range(4):
            try: r=cc.get(h,f"/api/v1/prices/GOLD?resolution={res}&from={frm:%Y-%m-%dT%H:%M:%S}&to={to:%Y-%m-%dT%H:%M:%S}&max=1000"); break
            except Exception: time.sleep(5); h=login_robusto(); t_login=time.time()
        if r is None: continue
        if r.status_code==200:
            for p in r.json().get("prices",[]):
                try: dt=datetime.fromisoformat((p.get("snapshotTimeUTC") or "").replace("Z",""))
                except ValueError: continue
                rows[dt]=[p[kk][s] for s in ("bid","ask") for kk in ("openPrice","highPrice","lowPrice","closePrice")]
        elif r.status_code==429: time.sleep(5); continue
        elif r.status_code in (401,403): h=login_robusto(); t_login=time.time(); continue
        to=frm; k+=1
        if k%60==0:
            json.dump({"to":to.isoformat(),"rows":{t.isoformat():v for t,v in rows.items()}},open(part,"w"))
            print(f"  {tag}: {k} ventanas, {len(rows)} velas, hasta {to:%Y-%m-%d}",flush=True)
        time.sleep(0.1)
    ts=sorted(rows); keys=("Ob","Hb","Lb","Cb","Oa","Ha","La","Ca")
    d={kk:[rows[t][i] for t in ts] for i,kk in enumerate(keys)}; d["T"]=[t.isoformat() for t in ts]
    json.dump(d,open(path,"w"))
    if os.path.exists(part): os.remove(part)
    print(f"[bajado] {os.path.basename(path)}: {len(ts)} velas {ts[0]:%Y-%m-%d} -> {ts[-1]:%Y-%m-%d}",flush=True)
bajar("MINUTE_15",timedelta(days=10),"15m")
bajar("MINUTE",timedelta(hours=16),"1m")
