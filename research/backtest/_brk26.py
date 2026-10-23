"""🚀 sortie de base (signal précoce de la page) sur 26 ans : seule, avec pente forte, selon l'humeur du marché."""
import numpy as np
exec(open('_regime.py').read().split('for a, b in [')[0])
w = [t for t in range(t1, T - 26) if ok_t[t]]
c1, c2 = np.percentile(up_sh[w], [100/3, 200/3])
reg = np.full(T, -1); 
for t in w:
    reg[t] = 0 if up_sh[t] < c1 else 2 if up_sh[t] > c2 else 1
RG = np.broadcast_to(reg, P.shape)
B0 = valid & brk & trend
for lab, M in [('toutes les sociétés', valid), ('🚀 seule (en tendance)', B0), ('🚀 + ⬆⬆ pente forte', B), ('🚀 + ⬆⬆, marché non euphorique', B & (RG >= 0) & (RG <= 1)),
               ('🚀 + ⬆⬆, marché euphorique', B & (RG == 2))]:
    n = M.sum(); b40 = (M & (fut >= .4)).sum() / max(n, 1)
    e, cr, bg, nn = st(M)
    print(f"  {lab:34s} +40 % en 6 mois : {b40*100:4.1f} % (1 sur {1/max(b40,1e-9):.1f}) · écart {e:+5.1f} pts · chutes {cr:4.1f} % · {n} cas")
    for l, a, b in E3:
        mm = M.copy(); mm[:, :a] = False; mm[:, b:] = False
        n2 = mm.sum(); print(f"      {l} : +40 % {((mm & (fut >= .4)).sum() / max(n2, 1))*100:4.1f} % ({n2})", end='')
    print()
