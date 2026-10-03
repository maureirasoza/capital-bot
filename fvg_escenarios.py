#!/usr/bin/env python3
"""FVG oro: ESCENARIOS NUEVOS con ejecucion fiel 1m. Detector propio (verificado = funcion real) que
expone el hueco completo para variantes: fuerza del impulso, stop estructural, entrada con
confirmacion (toque + cierre a favor), senal en 4h, salida por tiempo, combos. 2024 | 600d."""
import sys, bisect
from datetime import datetime, timedelta
sys.argv=['x']
import backtest_real as br, fvg_sim1m as s1
fv=br._import_fvg(); d15,d1=s1.load(1000); cut=datetime(2025,2,9)
src=open('fvg_ultima_ronda.py').read(); exec(src[src.index("def agg("):src.index("def sim(")])   # agg(), d60
d240=agg(d15,240)
T1=d1["T"]; Ob,Hb,Lb,Oa,Ha,La=d1["Ob"],d1["Hb"],d1["Lb"],d1["Oa"],d1["Ha"],d1["La"]
def detector(O,H,L,C, imp=0.0, ema_len=None, min_gap=None):
    """= find_pending_fvg_ohlc pero devuelve j, gap_top/bot y la vela de impulso; imp = rango(j-1) >= imp x ATR."""
    i=len(C)-1; atr=fv.atr_series(H,L,C,fv.ATR_LEN); ema=fv.ema_series(C,ema_len or fv.EMA_TREND); mg=fv.MIN_GAP if min_gap is None else min_gap
    for j in range(i,max(i-fv.FILL_WIN,2)-1,-1):
        if j<2: break
        bull=L[j]>H[j-2] and C[j]>C[j-2]; bear=H[j]<L[j-2] and C[j]<C[j-2]
        if not(bull or bear): continue
        if (bull and C[j]<=ema[j]) or (bear and C[j]>=ema[j]): continue
        gt,gb,dr=(L[j],H[j-2],1) if bull else (L[j-2],H[j],-1); g=gt-gb; a=atr[j] or 0
        if g<mg*a: continue
        if imp and (H[j-1]-L[j-1])<imp*a: continue
        geff=min(g,fv.MAX_GAP*a) if a>0 else g
        if any((dr==1 and L[k]<=gt) or (dr==-1 and H[k]>=gb) for k in range(j+1,i+1)): continue
        rem=fv.FILL_WIN-(i-j)
        if rem<=0: continue
        return {"side":"BUY" if dr==1 else "SELL","gt":gt,"gb":gb,"g":g,"geff":geff,"atr":a,"j":j,"i":i,"rem":rem,
                "struct":L[j-2] if dr==1 else H[j-2],"close":C[i]}
    return None
def make(mode="borde", sl=None, tp=None, imp=0.0, ema_len=None, min_gap=None, depth=0.0, rr=None, conf=False, tbars=None):
    SLm=fv.SL_MULT if sl is None else sl; TPm=fv.TP_R if tp is None else tp
    def f(O,H,L,C):
        s=detector(O,H,L,C,imp,ema_len,min_gap)
        if not s: return None
        bull=s["side"]=="BUY"; sg=1 if bull else -1; lvl=(s["gt"] if bull else s["gb"])-sg*depth*s["g"]
        if mode=="estructura":
            slv=s["struct"]-sg*0.1*s["atr"]; risk=abs(lvl-slv); tpv=lvl+sg*(rr or 1.5)*risk
        else:
            slv=lvl-sg*SLm*s["geff"]; tpv=lvl+sg*TPm*s["geff"]
        return {"side":s["side"],"level":round(lvl,1),"sl":round(slv,1),"tp":round(tpv,1),"remaining_bars":s["rem"],"gap_eff":s["geff"],"conf":conf,"tbars":tbars,"edge":s["gt"] if bull else s["gb"]}
    return f
def sim(dS, bar_min, sigfn):
    O,H,L,C=s1.prep(dS); TS=dS["T"]; n=len(C); WIN=s1.WIN; M=timedelta(minutes=bar_min); m1=timedelta(minutes=1)
    j=bisect.bisect_left(T1,TS[WIN]+M); n1=len(T1); tr=[]; pos=None; order=None
    for t in range(WIN,n):
        D=TS[t]+M
        if pos is None and order is None:
            lo=t-WIN+1; s=sigfn(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
            if s: order=dict(s,start=D+m1,exp=D+m1+timedelta(minutes=bar_min*s["remaining_bars"]),first=True,touched=False)
        elif order and order.get("conf") and order["touched"] and pos is None:
            # CONFIRMACION: ya toco el borde; entra si esta vela cierra del lado correcto del borde
            if (order["side"]=="BUY" and C[t]>order["edge"]) or (order["side"]=="SELL" and C[t]<order["edge"]):
                order["go"]=D+m1
            elif D>=order["exp"]: order=None
        Dn=(TS[t+1]+M) if t+1<n else D+M
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"] and pos is None:
                if order["first"]:
                    order["first"]=False
                    if (order["side"]=="BUY" and order["level"]>=Oa[j]) or (order["side"]=="SELL" and order["level"]<=Ob[j]): order=None
                if order and tm>=order["exp"] and not order.get("go"): order=None
                if order:
                    long=order["side"]=="BUY"; fill=None
                    if order.get("conf"):
                        if not order["touched"] and ((long and La[j]<=order["level"]) or ((not long) and Hb[j]>=order["level"])): order["touched"]=True
                        if order.get("go") and tm>=order["go"]: fill=Oa[j] if long else Ob[j]
                    elif (long and La[j]<=order["level"]) or ((not long) and Hb[j]>=order["level"]): fill=min(order["level"],Oa[j]) if long else max(order["level"],Ob[j])
                    if fill is not None:
                        sg=1 if long else -1
                        if order.get("conf"):   # recalcular SL/TP desde el precio real de entrada manteniendo distancias
                            dsl=abs(order["level"]-order["sl"]); dtp=abs(order["tp"]-order["level"]); slv=fill-sg*dsl; tpv=fill+sg*dtp
                        else: slv,tpv=order["sl"],order["tp"]
                        pos={"long":long,"entry":fill,"sl":slv,"tp":tpv,"t_in":tm,"tbars":order.get("tbars")}; order=None
            if pos:
                long=pos["long"]; ex=None
                if long:
                    if Lb[j]<=pos["sl"]: ex=min(pos["sl"],Ob[j]) if (Ob[j]<pos["sl"] and tm>pos["t_in"]) else pos["sl"]
                    elif Hb[j]>=pos["tp"] and tm>pos["t_in"]: ex=pos["tp"]
                    elif pos["tbars"] and tm-pos["t_in"]>=timedelta(minutes=bar_min*pos["tbars"]): ex=Ob[j]
                else:
                    if Ha[j]>=pos["sl"]: ex=max(pos["sl"],Oa[j]) if (Oa[j]>pos["sl"] and tm>pos["t_in"]) else pos["sl"]
                    elif La[j]<=pos["tp"] and tm>pos["t_in"]: ex=pos["tp"]
                    elif pos["tbars"] and tm-pos["t_in"]>=timedelta(minutes=bar_min*pos["tbars"]): ex=Oa[j]
                if ex is not None: tr.append({"net":(ex-pos["entry"]) if long else (pos["entry"]-ex),"t_in":pos["t_in"],"t_out":tm}); pos=None
            j+=1
    return tr
def row(name,sigfn,dS=d15,bar_min=15):
    full=sim(dS,bar_min,sigfn); a=s1.stats([x for x in full if x["t_in"]<cut]); b=s1.stats([x for x in full if x["t_in"]>=cut])
    ok=" <<< positivo en ambos" if a["tot"]>0 and b["tot"]>0 else ""
    print(f"{name:<48} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['acc']:>3.0f}% | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['acc']:>3.0f}% {b['dd']:>+5.0f}{ok}")
# verificacion del detector vs la funcion real
O,H,L,C=s1.prep(d15); dif=0; nreal=0
for t in range(s1.WIN,len(C),7):
    lo=t-s1.WIN+1; r=fv.find_pending_fvg_ohlc(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); m=make()(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
    if r and r.get("side"):
        nreal+=1
        if not m or (m["side"],m["level"],m["sl"],m["tp"])!=(r["side"],r["level"],r["sl"],r["tp"]): dif+=1
    elif m: dif+=1
print(f"detector propio vs funcion real: {nreal} senales muestreadas, diferencias {dif}")
print(f"\n{'escenario':<48} | {'2024: tr neto PF acc':^26} | {'600d: tr neto PF acc DD':^32}")
row("ACTUAL (borde, SL2/TP0.75)",make())
print("-- fuerza del impulso (vela central >= k x ATR) --")
for k in (1.0,1.5,2.0,3.0): row(f"  impulso >= {k}xATR, SL2/TP0.75",make(imp=k))
for k in (1.5,2.0): row(f"  impulso >= {k}xATR, SL1.5/TP1.5",make(imp=k,sl=1.5,tp=1.5))
print("-- stop ESTRUCTURAL (bajo la vela previa al hueco) con TP en multiplos de R --")
for rr in (1.0,1.5,2.0,3.0): row(f"  borde, stop estructural, TP {rr}R",make(mode="estructura",rr=rr))
for rr in (1.5,2.0): row(f"  50% del hueco, stop estructural, TP {rr}R",make(mode="estructura",rr=rr,depth=0.5))
print("-- entrada con CONFIRMACION: toca el borde y cierra 15m a favor, entra a mercado --")
for sl_,tp_ in ((1.5,1.0),(2.0,0.75),(1.5,1.5),(1.0,2.0)): row(f"  confirmacion, SL{sl_}/TP{tp_}",make(conf=True,sl=sl_,tp=tp_))
row("  confirmacion, stop estructural TP 1.5R",make(conf=True,mode="estructura",rr=1.5))
print("-- salida por TIEMPO (sin TP cercano: TP 3x, SL 2x, cierra a N velas) --")
for N in (4,8,16): row(f"  SL2/TP3, salida a {N} velas",make(sl=2.0,tp=3.0,tbars=N))
print("-- senal en 4 HORAS --")
for sl_,tp_ in ((1.5,1.0),(2.0,0.75),(1.5,1.5),(1.0,2.0)): row(f"  4h borde SL{sl_}/TP{tp_}",make(sl=sl_,tp=tp_),d240,240)
row("  4h stop estructural TP 1.5R",make(mode="estructura",rr=1.5),d240,240)
row("  4h stop estructural TP 2R, impulso>=1.5",make(mode="estructura",rr=2.0,imp=1.5),d240,240)
print("-- combos --")
row("  impulso>=1.5 + estructural 1.5R",make(mode="estructura",rr=1.5,imp=1.5))
row("  impulso>=1.5 + confirmacion SL1.5/TP1.0",make(conf=True,imp=1.5,sl=1.5,tp=1.0))
row("  EMA20 + impulso>=1.5 + SL1.5/TP1.0",make(ema_len=20,imp=1.5,sl=1.5,tp=1.0))
row("  huecos>=0.8 + estructural 1.5R",make(mode="estructura",rr=1.5,min_gap=0.8))
