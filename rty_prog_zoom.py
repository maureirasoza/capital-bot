import sys; sys.argv=['x']
exec(open('prog_bots.py').read().split('if __name__=="__main__":')[0])
import bot_rty as rt
D=load_mid("RTY","MINUTE_15",300); sig,atr=precompute(*D[:4],rt.signal_last,300)
analizar("RTY (zoom)",D,sig,atr,rt.TRAIL_ATR,0.5,300,[10,11,12,13,14,15,18],[1.5,2.0,2.5,3.0,3.5],1.0)
