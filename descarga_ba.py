#!/usr/bin/env python3
"""Descarga bid/ask reanudable para cualquier epic/resolucion. Uso: python descarga_ba.py EPIC RES DIAS"""
import os, sys, json, time
from datetime import datetime, timedelta, timezone
import capital_client as cc, backtest_real as br
EPIC,RES,DAYS=sys.argv[1],sys.argv[2],int(sys.argv[3])
step={"MINUTE":timedelta(hours=16),"MINUTE_5":timedelta(days=3),"MINUTE_15":timedelta(days=10),"HOUR":timedelta(days=40),"HOUR_4":timedelta(days=160),"DAY":timedelta(days=900)}[RES]
path=os.path.join(br.DATA_DIR,f"capital_{EPIC}_{RES}_{DAYS}d_bidask.json"); part=path+".parcial"
if os.path.exists(path): print("ya existe",path); sys.exit()
def login_robusto():
    for i in range(20):
        try: return cc.login()
        except (SystemExit, Exception): time.sleep(15)
    raise SystemExit("sin red")
now=datetime.now(timezone.utc).replace(tzinfo=None); end=now-timedelta(days=DAYS); rows={}; to=now
if os.path.exists(part):
    p=json.load(open(part)); rows={datetime.fromisoformat(k):v for k,v in p["rows"].items()}; to=datetime.fromisoformat(p["to"])
h=login_robusto(); t0=time.time(); k=0
while to>end:
    frm=to-step
    if time.time()-t0>420: h=login_robusto(); t0=time.time()
    r=None
    for _ in range(4):
        try: r=cc.get(h,f"/api/v1/prices/{EPIC}?resolution={RES}&from={frm:%Y-%m-%dT%H:%M:%S}&to={to:%Y-%m-%dT%H:%M:%S}&max=1000"); break
        except Exception: time.sleep(5); h=login_robusto(); t0=time.time()
    if r is None: continue
    if r.status_code==200:
        for p in r.json().get("prices",[]):
            try: dt=datetime.fromisoformat((p.get("snapshotTimeUTC") or "").replace("Z",""))
            except ValueError: continue
            rows[dt]=[p[kk][s] for s in ("bid","ask") for kk in ("openPrice","highPrice","lowPrice","closePrice")]
    elif r.status_code==429: time.sleep(5); continue
    elif r.status_code in (401,403): h=login_robusto(); t0=time.time(); continue
    to=frm; k+=1
    if k%60==0: json.dump({"to":to.isoformat(),"rows":{t.isoformat():v for t,v in rows.items()}},open(part,"w"))
    time.sleep(0.1)
ts=sorted(rows); keys=("Ob","Hb","Lb","Cb","Oa","Ha","La","Ca")
d={kk:[rows[t][i] for t in ts] for i,kk in enumerate(keys)}; d["T"]=[t.isoformat() for t in ts]
json.dump(d,open(path,"w"))
if os.path.exists(part): os.remove(part)
print(f"[bajado] {os.path.basename(path)}: {len(ts)} velas {ts[0]:%Y-%m-%d} -> {ts[-1]:%Y-%m-%d}",flush=True)
