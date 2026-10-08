import sys; sys.argv=['x']
src=open('trend_salidas.py').read(); exec(src[:src.index("V=[(")])
def sim_vivo(M=None,k=None):
    """Como lo haria el BOT: corre al cierre de cada vela 1h; si la ganancia maxima de la base >= M x ATR(entrada)
    (calculada como stopLevel +/- distancia, sin estado), cambia la distancia del trailing de AMBAS unidades a k x ATR
    y capital.com re-ancla el stop al PRECIO ACTUAL (cierre) - k x ATR, si eso lo mejora."""
    tr=[]; base=None; pyr=None
    def cu(u,px,t,nm,size): g=(px-u["e"]) if u["s"]=="L" else (u["e"]-px); return {"net":g-2*SP,"usd":(g-2*SP)*size,"t":T[t],"t_in":u["t_in"],"unit":nm}
    for t in range(W,n):
        s=sig[t]
        for nm in ("base","pyr"):
            u=base if nm=="base" else pyr
            if u is None: continue
            sg=1 if u["s"]=="L" else -1
            if (sg==1 and L[t]<=u["stop"]) or (sg==-1 and H[t]>=u["stop"]):
                tr.append(cu(u,u["stop"],t,nm,0.5 if nm=="base" else 0.51))
                if nm=="base": base=None
                else: pyr=None
        if base or pyr:
            u0=base or pyr
            if exit_ch(t,u0["s"],8):
                for nm,u in (("base",base),("pyr",pyr)):
                    if u: tr.append(cu(u,C[t],t,nm,0.5 if nm=="base" else 0.51))
                base=pyr=None; continue
        for u in (base,pyr):
            if u is None: continue
            sg=1 if u["s"]=="L" else -1
            u["x"]=max(u["x"],H[t]) if sg==1 else min(u["x"],L[t])
            u["stop"]=max(u["stop"],u["x"]-u["d"]) if sg==1 else min(u["stop"],u["x"]+u["d"])
        # --- decision del bot al cierre ---
        if M and base and not base.get("tight"):
            sg=1 if base["s"]=="L" else -1
            mfe=sg*((base["stop"]+sg*base["d"])-base["e"])        # extremo = stop +/- distancia
            if mfe>=M*base["atr"]:
                for u in (base,pyr):
                    if u is None: continue
                    u["d"]=k*base["atr"]; u["x"]=C[t]               # re-ancla al precio actual
                    new=C[t]-sg*u["d"]; u["stop"]=max(u["stop"],new) if sg==1 else min(u["stop"],new)
                base["tight"]=True
        if base and pyr is None and not base.get("pd"):
            sg=1 if base["s"]=="L" else -1; lvl=base["e"]+sg*bt.PYR_STEP*base["atr"]
            if (sg==1 and C[t]>=lvl) or (sg==-1 and C[t]<=lvl):
                e=C[t]; d=(k if base.get("tight") else 5.0)*base["atr"]
                pyr={"s":base["s"],"e":e,"d":d,"x":e,"stop":e-sg*d,"t_in":T[t]}; base["pd"]=True
        if base is None and pyr is None and s and s["atr"]:
            side="L" if s["long_break"] else ("S" if s["short_break"] else None)
            if side:
                sg=1 if side=="L" else -1; e=C[t]; d=5.0*s["atr"]
                base={"s":side,"e":e,"d":d,"atr":s["atr"],"x":e,"stop":e-sg*d,"t_in":T[t]}
    return tr
def seg6(tr):
    tr=sorted(tr,key=lambda z:z["t"]); t0=T[W]; span=(T[-1]-t0)/6; out=[0.0]*6
    for x in tr: out[min(5,int((x["t"]-t0)/span))]+=x["usd"]
    return out
b0=sim_vivo(); s0=seg6(b0); c0=st(b0)
print(f"{'version EN VIVO (bot horario)':<30} | {'TOTAL USD PF DD':>22} | {'6 tramos de ~165 dias (USD)':^48} | tramos que mejoran")
print(f"{'ACTUAL':<30} | {c0[0]:>+8.0f} PF{c0[1]:.2f} {c0[2]:>+5.0f} | "+" ".join(f"{v:>+7.0f}" for v in s0)+" |")
for M,k in ((8,2.5),(8,3.0),(9,2.5),(9,3.0),(10,2.5),(10,3.0),(12,2.5),(12,3.0),(9,2.0),(10,2.0)):
    tr=sim_vivo(M,k); c=st(tr); s=seg6(tr)
    print(f"{'tras +'+str(M)+'xATR -> '+str(k)+'x':<30} | {c[0]:>+8.0f} PF{c[1]:.2f} {c[2]:>+5.0f} | "+" ".join(f"{v:>+7.0f}" for v in s)+f" | {sum(1 for a,b in zip(s,s0) if a>b+1)}/6 (iguales {sum(1 for a,b in zip(s,s0) if abs(a-b)<=1)})")
n_t=sum(1 for x in sim_vivo(9,2.5) if x["unit"]=="base"); print(f"\noperaciones base en 1000d: {n_t}")
