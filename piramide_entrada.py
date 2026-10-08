#!/usr/bin/env python3
"""Trend oro: CUANDO agregar la piramide (stop propio 5xATR como en vivo). Variantes de entrada:
  step k      : al cierre a +k x ATR(entrada) a favor (hoy k=2)
  +extremo    : ademas, el cierre debe ser el extremo de las ultimas N velas (el movimiento sigue vivo)
  +base_prot  : ademas, el stop de la base ya debe estar en o mas alla de su entrada (base sin riesgo)
  +ema        : ademas, el cierre sigue a favor de la EMA200 (la tendencia de fondo no se dio vuelta)
  +vela       : ademas, la vela de disparo cierra a favor (C>O en largo, C<O en corto)"""
import sys
sys.argv=['x','--source','capital','--days','1000']
src=open('piramide_stop.py').read(); exec(src[:src.index("def sim(")]); exec(src[src.index("def st("):src.index("print(f")])
def sim2(step=2.0,extremo=None,base_prot=False,ema=False,vela=False):
    tr=[]; base=None; pyr=None
    def cu(u,px,t): g=(px-u["e"]) if u["s"]=="L" else (u["e"]-px); return {"net":g-2*SP,"t":t}
    for t in range(W,n):
        s=sig[t]
        for nm in ("base","pyr"):
            u=base if nm=="base" else pyr
            if u is None: continue
            if (u["s"]=="L" and L[t]<=u["stop"]) or (u["s"]=="S" and H[t]>=u["stop"]):
                tr.append(dict(cu(u,u["stop"],T[t]),unit=nm))
                if nm=="base": base=None
                else: pyr=None
        if base or pyr:
            u0=base or pyr
            if (u0["s"]=="L" and s["exit_long"]) or (u0["s"]=="S" and s["exit_short"]):
                for nm,u in (("base",base),("pyr",pyr)):
                    if u: tr.append(dict(cu(u,C[t],T[t]),unit=nm))
                base=pyr=None; continue
        for u in (base,pyr):
            if u is None: continue
            if u["s"]=="L": u["x"]=max(u["x"],H[t]); u["stop"]=max(u["stop"],u["x"]-u["d"])
            else: u["x"]=min(u["x"],L[t]); u["stop"]=min(u["stop"],u["x"]+u["d"])
        if base and pyr is None and not base.get("pyr_done"):
            sg=1 if base["s"]=="L" else -1; lvl=base["e"]+sg*step*base["atr"]
            ok=(C[t]>=lvl) if sg==1 else (C[t]<=lvl)
            if ok and extremo: ok=(C[t]>=max(C[t-extremo:t])) if sg==1 else (C[t]<=min(C[t-extremo:t]))
            if ok and base_prot: ok=(base["stop"]>=base["e"]) if sg==1 else (base["stop"]<=base["e"])
            if ok and ema and s.get("ema") is not None: ok=(C[t]>s["ema"]) if sg==1 else (C[t]<s["ema"])
            if ok and vela: ok=(C[t]>O[t]) if sg==1 else (C[t]<O[t])
            if ok:
                e=C[t]; d=bt.ATR_STOP*base["atr"]; pyr={"s":base["s"],"e":e,"d":d,"x":e,"stop":e-sg*d}; base["pyr_done"]=True
        if base is None and pyr is None and s and s["atr"]:
            side="L" if s["long_break"] else ("S" if s["short_break"] else None)
            if side:
                d=bt.ATR_STOP*s["atr"]; e=C[t]; sg=1 if side=="L" else -1
                base={"s":side,"e":e,"d":d,"atr":s["atr"],"x":e,"stop":e-sg*d}
    return tr
print(f"{'cuando piramidar':<36} | {'2024 (no visto)':^20} | {'600d':^22} | {'TOTAL 1000d':^22} | piramides: n, neto, peor")
for nm,kw in (("step 1.5","dict(step=1.5)"),("step 2.0 (ACTUAL)","dict(step=2.0)"),("step 2.5","dict(step=2.5)"),("step 3.0","dict(step=3.0)"),
              ("step 2 + extremo 5 velas","dict(extremo=5)"),("step 2 + extremo 10 velas","dict(extremo=10)"),("step 2 + base protegida","dict(base_prot=True)"),
              ("step 2 + EMA200 a favor","dict(ema=True)"),("step 2 + vela a favor","dict(vela=True)"),("step 2 + vela + extremo 5","dict(vela=True,extremo=5)")):
    tr=sim2(**eval(nm and kw)); a=st([x for x in tr if x["t"]<T[cut]]); b=st([x for x in tr if x["t"]>=T[cut]]); c=st(tr)
    py=[x["net"] for x in tr if x["unit"]=="pyr"]
    print(f"{nm:<36} | {a[0]:>+6.0f} PF{a[1]:.2f} {a[2]:>+5.0f} | {b[0]:>+6.0f} PF{b[1]:.2f} {b[2]:>+6.0f} | {c[0]:>+6.0f} PF{c[1]:.2f} {c[2]:>+6.0f} | {len(py)}, {sum(py):+.0f}, {min(py) if py else 0:+.0f}")
