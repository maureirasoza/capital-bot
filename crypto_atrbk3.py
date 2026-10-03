import sys; sys.argv=['x']
src=open('crypto_atrbk2.py').read(); exec(src[:src.index('print("cartera')])
print("cartera BTC+ETH, k3.0 trail2.0 (centro), costos reales\n-- meseta del filtro EMA --")
for el in (100,150,200,250,300,400): line(f"EMA{el}",[cl.run(d,atrbk(d,3.0,el),2.0,None,("L","S")) for d in data.values()])
print("-- EMA200 + piramide --")
for st,mu in ((2.0,2),(3.0,2),(2.0,3)): line(f"EMA200 + pir {st}x max{mu}",[run_pyr(d,atrbk(d,3.0,200),2.0,st,mu) for d in data.values()])
print("-- vecinos con EMA200 + pir 2x max2 --")
for k in (2.5,3.0,3.5):
    for t in (2.0,2.5,3.0): line(f"k{k} trail{t} EMA200 pir2x2",[run_pyr(d,atrbk(d,k,200),t,2.0,2) for d in data.values()])
print("-- por activo (k3 t2 EMA200 pir2x2) --")
for e,d in data.items():
    tr=run_pyr(d,atrbk(d,3.0,200),2.0,2.0,2); s=cl.stats(tr)
    print(f"  {e}: {s['n']} tr, tot {s['tot']:+.0f}% PF {s['pf']:.2f} acc {s['acc']:.0f}% DD {s['dd']:+.0f}% L {s['L']:+.0f} S {s['S']:+.0f} dias/op {s['days']:.1f} | "+" ".join(f"{y}:{s['years'].get(y,0):+.0f}" for y in YRS))
