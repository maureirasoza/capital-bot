import sys; sys.argv=['x']
src=open('rf_prog_fiel.py').read(); exec(src[:src.index("base=sim_p(")])
base=sim_p(48,2,3.0); a0=s1.stats([x for x in base if x["t_in"]<mid]); b0=s1.stats([x for x in base if x["t_in"]>=mid]); c0=s1.stats(base)
print(f"{'regla':<22} | {'mitad1':>8} {'mitad2':>8} | {'total':>8} {'PF':>5} {'DD':>6} | mejora")
for M,k in ((2.5,1.5),(3,1.25),(3,1.75),(3.5,1.25),(3.5,1.5),(3.5,1.75),(3.5,2.0),(4,1.25),(4,1.75),(3,2.5),(4,2.5)):
    tr=sim_p(48,2,3.0,M,k); a=s1.stats([x for x in tr if x["t_in"]<mid]); b=s1.stats([x for x in tr if x["t_in"]>=mid]); c=s1.stats(tr)
    ok="*" if a["tot"]>a0["tot"] and b["tot"]>b0["tot"] else " "
    print(f"tras +{M}xATR -> {k}x     | {a['tot']:>+8.0f} {b['tot']:>+8.0f} | {c['tot']:>+8.0f} {c['pf']:>5.2f} {c['dd']:>+6.0f} | {100*(c['tot']-c0['tot'])/abs(c0['tot']):>+4.0f}% {ok}")
