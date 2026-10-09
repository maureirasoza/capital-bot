#!/usr/bin/env python3
"""Evalua el MODO SOMBRA IA: junta los veredictos (artifacts 'sombra-ia-*' de los workflows de capital-bot y
gold-bot, y data/sombra_local.jsonl de la tarea programada local) y los cruza con el resultado REAL de cada operacion en capital.com (misma epic/size/lado, apertura
hasta 30 min despues del veredicto). Responde: si hubieramos hecho caso a la IA, ¿se ganaba mas?
Uso: python sombra_eval.py [DIAS=30]"""
import sys, os, json, glob, subprocess, tempfile, time
from datetime import datetime, timedelta, timezone
import capital_client as cc

REPOS = ["maureirasoza/capital-bot", "maureirasoza/gold-bot"]
DIAS = int(sys.argv[1]) if len(sys.argv) > 1 else 30


def veredictos():
    out = []
    tmp = tempfile.mkdtemp(prefix="sombra_")
    for repo in REPOS:
        r = subprocess.run(["gh", "api", f"repos/{repo}/actions/artifacts?per_page=100", "--paginate",
                            "--jq", ".artifacts[] | select(.name|startswith(\"sombra-ia-\")) | select(.expired|not) "
                                    "| [.name, .workflow_run.id] | @tsv"], capture_output=True, text=True)
        for line in r.stdout.split("\n"):
            if not line.strip():
                continue
            name, run_id = line.split("\t")
            d = os.path.join(tmp, name)
            subprocess.run(["gh", "run", "download", run_id, "-R", repo, "-n", name, "-D", d], capture_output=True)
            for f in glob.glob(os.path.join(d, "*.jsonl")):
                for l in open(f):
                    if l.strip():
                        out.append(json.loads(l))
    loc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sombra_local.jsonl")
    if os.path.exists(loc):
        for l in open(loc):
            if l.strip():
                d = json.loads(l); d["t"] = d.get("t_entrada_utc", d.get("t_veredicto_utc")); out.append(d)
    return out


def operaciones(h, desde):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    acts, tx = [], {}
    for d in range((now - desde).days + 2):
        a0 = now - timedelta(days=d + 1); a1 = now - timedelta(days=d)
        r = cc.get(h, f"/api/v1/history/activity?from={a0:%Y-%m-%dT%H:%M:%S}&to={a1:%Y-%m-%dT%H:%M:%S}&detailed=true")
        acts += r.json().get("activities", []) if r.status_code == 200 else []
        time.sleep(0.1)
    for d in range(0, (now - desde).days + 2, 10):
        a0 = now - timedelta(days=d + 10); a1 = now - timedelta(days=d)
        r = cc.get(h, f"/api/v1/history/transactions?from={a0:%Y-%m-%dT%H:%M:%S}&to={a1:%Y-%m-%dT%H:%M:%S}")
        for t in (r.json().get("transactions", []) if r.status_code == 200 else []):
            if t["transactionType"] == "TRADE":
                tx[t["dealId"]] = float(t["size"])
    ops = {}
    for a in acts:
        det = a.get("details") or {}
        if a.get("type") != "POSITION" or det.get("size") is None or det.get("openPrice") is not None:
            continue
        ops.setdefault(a["dealId"], {"t": datetime.strptime(a["dateUTC"][:19], "%Y-%m-%dT%H:%M:%S"),
                                     "epic": a["epic"], "size": round(float(det["size"]), 4),
                                     "side": det.get("direction"), "pnl": tx.get(a["dealId"])})
    return ops


def resumen(etq, v):
    if not v:
        print(f"  {etq:<28}    0 ops"); return
    print(f"  {etq:<28} {len(v):>4} ops  total ${sum(v):+8.2f}  media ${sum(v)/len(v):+6.2f}  "
          f"aciertos {100*sum(1 for x in v if x > 0)/len(v):.0f}%")


def main():
    desde = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=DIAS)
    vs = [v for v in veredictos() if datetime.fromisoformat(v["t"]) >= desde]
    print(f"{len(vs)} veredictos de la IA en {DIAS} dias | costo aprox ${sum(v.get('costo_usd_aprox') or 0 for v in vs):.2f}")
    h = cc.login(); ops = operaciones(h, desde); usados = set()
    filas = []
    for v in sorted(vs, key=lambda x: x["t"]):
        t = datetime.fromisoformat(v["t"]); m = v.get("dealId") if v.get("dealId") in ops else None
        for did, o in ([] if m else ops.items()):
            if did in usados or o["epic"] != v.get("epic") or o["side"] != v.get("side"):
                continue
            if v.get("size") and abs(o["size"] - v["size"]) > 1e-6:
                continue
            if t - timedelta(minutes=5) <= o["t"] <= t + timedelta(minutes=30):
                m = did; break
        if m:
            usados.add(m)
        filas.append((v, ops[m]["pnl"] if m else None, m))
    print(f"{'hora UTC':<17}{'bot':<14}{'lado':<5}{'IA':<11}{'conf':>5}{'P&L real':>10}  motivo")
    for v, pnl, m in filas:
        estado = f"{pnl:+10.2f}" if pnl is not None else ("   abierta" if m else "  sin llenar")
        print(f"{v['t'][5:16]:<17}{v.get('bot',''):<14}{(v.get('side') or ''):<5}{(v.get('veredicto') or 'ERROR'):<11}"
              f"{(v.get('confianza') or 0):>5}{estado}  {(v.get('motivo') or v.get('error') or '')[:70]}")
    cerr = [(v, p) for v, p, _ in filas if p is not None and v.get("veredicto")]
    print("\nRESULTADO REAL segun lo que dijo la IA:")
    resumen("IA dijo ENTRAR", [p for v, p in cerr if v["veredicto"] == "ENTRAR"])
    resumen("IA dijo NO_ENTRAR", [p for v, p in cerr if v["veredicto"] == "NO_ENTRAR"])
    resumen("NO_ENTRAR con confianza>=70", [p for v, p in cerr if v["veredicto"] == "NO_ENTRAR" and (v.get("confianza") or 0) >= 70])
    todo = sum(p for _, p in cerr); solo_ia = sum(p for v, p in cerr if v["veredicto"] == "ENTRAR")
    print(f"\n  Bots tal cual: ${todo:+.2f} | Haciendo caso a la IA (solo ENTRAR): ${solo_ia:+.2f} | diferencia ${solo_ia - todo:+.2f}")
    print("  OJO: con menos de ~100 operaciones cerradas la diferencia puede ser pura suerte.")


if __name__ == "__main__":
    main()
