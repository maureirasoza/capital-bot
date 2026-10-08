import sys; sys.argv=['x']
src=open('trend_salidas.py').read(); exec(src[:src.index("V=[(")])
print(f"{'variante':<32} | {'2024 USD PF':>16} | {'600d USD PF DD':>22} | {'TOTAL USD PF':>16} | mejora vs actual")
base=st(sim()); print(f"{'ACTUAL':<32} | {'':>16} | {'':>22} | {base[0]:>+9.0f} PF{base[1]:.2f} |")
def row(nm,**kw):
    tr=sim(**kw); a=st([x for x in tr if x["t"]<T[cut]]); b=st([x for x in tr if x["t"]>=T[cut]]); c=st(tr)
    print(f"{nm:<32} | {a[0]:>+9.0f} PF{a[1]:.2f} | {b[0]:>+8.0f} PF{b[1]:.2f} {b[2]:>+5.0f} | {c[0]:>+9.0f} PF{c[1]:.2f} | {c[0]-base[0]:>+6.0f}")
print("-- apretar tras ganancia grande: malla M (umbral) x k (nuevo trailing) --")
for M in (6,7,8,9,10,12):
    for k in (2.5,3.0,3.5,4.0): row(f"tras +{M}xATR -> {k}x",prog=(M,k))
print("-- objetivo fijo lejano --")
for T_ in (10,11,12,13,14,16,20): row(f"objetivo +{T_}xATR",tp=T_)
