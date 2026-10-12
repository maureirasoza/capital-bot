import sys; sys.argv=['x']
from datetime import datetime
import retest as R
CORTE=datetime(2025,7,1); m=R.cargar5("US30"); rf=R.rf
orig=(rf.ENT,rf.CONF); filas=[]
for ent in (24,48,96):
    for conf in (1,2,3):
        rf.ENT,rf.CONF=ent,conf
        for tr in (2.0,3.0,4.0):
            trs=R.simular(m,R.bot_rf(m,trail=tr))
            f=lambda v:(sum(x["pts"] for x in v)*rf.SIZE, len(v))
            a=f([x for x in trs if x["t_in"]<CORTE]); b=f([x for x in trs if x["t_in"]>=CORTE])
            filas.append(((ent,conf,tr),a,b)); print(f"ENT{ent} CONF{conf} t{tr}: entren ${a[0]:+6.0f} ({a[1]}) | prueba ${b[0]:+6.0f} ({b[1]}){' <- ACTUAL' if (ent,conf,tr)==(48,2,3.0) else ''}",flush=True)
rf.ENT,rf.CONF=orig
e=max((f for f in filas if f[1][1]>=40),key=lambda f:f[1][0])
print(f"ELEGIDA con entrenamiento: ENT{e[0][0]} CONF{e[0][1]} t{e[0][2]} -> prueba ${e[2][0]:+.0f}")
