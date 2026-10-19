import numpy as np, sys
exec(open(sys.argv[1]).read().split("print('=== VOLUMES ===')")[0].replace("d = np.load(sys.argv[1])", "d = np.load(sys.argv[2])"))
vw, v52 = sma(VO, 10), sma(VO, 52); vx = vw / v52
F3 = valid & (mp >= 2/3) & trend & (s26 >= 0.41) & (mom >= .6) & (mom <= 2)
eras('filtres 🎯 (sans comptes)', F3)
eras('filtres 🎯 + volumes ×2', F3 & (vx >= 2))
eras('filtres 🎯 + volumes ×1,5', F3 & (vx >= 1.5))
eras('filtres 🎯 + volumes en hausse (×1,2)', F3 & (vx >= 1.2))
eras('filtres 🎯 sans hausse de volume (< ×1,2)', F3 & (vx < 1.2))
cnt = [ (F3[:, t] & np.isfinite(vx[:, t])).sum() for t in range(t0, T) ]; c2 = [(F3[:, t] & (vx[:, t] >= 2)).sum() for t in range(t0, T)]; c15 = [(F3[:, t] & (vx[:, t] >= 1.5)).sum() for t in range(t0, T)]
print('par semaine : filtres', np.mean(cnt), '| dont ×2', np.mean(c2), 'semaines avec au moins 1 :', np.mean(np.array(c2) > 0), '| dont ×1,5', np.mean(c15), np.mean(np.array(c15) > 0))
