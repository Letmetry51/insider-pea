import numpy as np
src = open('_detect.py').read(); exec(src.split("print('Référence")[0])
v10 = None
z = np.load('long.npz', allow_pickle=True); VO = z['V'].astype(float)
def sma2(A, k):
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(fin(A), 1)
    o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
    cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan; return o
vx = sma2(VO, 10) / sma2(VO, 52)
rRA, rRES = xrank(RA), xrank(RES)
def cnt(M): return int(M.sum())
print('🎯 total', cnt(Q), '| RA défavorable', cnt(Q & (rRA < .5)), '| RES défavorable', cnt(Q & (rRES < .5)))
print('volatilité annuelle médiane : 🎯 RA favorable %.0f %%, défavorable %.0f %%' % (np.nanmedian(vol[Q & (rRA >= .5)]) * 100, np.nanmedian(vol[Q & (rRA < .5)]) * 100))
# rang à l'intérieur du groupe 🎯 de la semaine (utile pour l'ordre des choix)
def inrank(A, M):
    o = np.full_like(A, np.nan)
    for t in range(T):
        m = M[:, t] & fin(A[:, t])
        if m.sum() >= 4: o[m, t] = A[m, t].argsort().argsort() / (m.sum() - 1)
    return o
for nm, A in [('ajusté du risque', RA), ('résiduel', RES), ('volume vx', vx), ('note simple (12 mois)', mom)]:
    r = inrank(A, Q); a, b = st(Q & (r >= .5)), st(Q & (r < .5))
    per = '  '.join(f"{lab} {st(Q & (r >= .5), x, y)[0]-st(Q & (r < .5), x, y)[0]:+5.1f}" for lab, x, y in E3)
    print(f"dans 🎯, moitié haute vs basse par {nm:22s} {a[0]:+5.1f} vs {b[0]:+5.1f} (chutes {a[1]:.1f} vs {b[1]:.1f} %) | {per}")
both = Q & (rRA >= .5) & (rRES >= .5)
print('🎯 + RA et résiduel favorables', '%+.1f (chutes %.1f %%)' % st(both), 'n', cnt(both), '| par période', '  '.join(f"{lab} {st(both, x, y)[0]:+5.1f}" for lab, x, y in E3))
print('🎯 + vx≥1.5', '%+.1f (chutes %.1f %%)' % st(Q & (vx >= 1.5)), '| + RA favorable', '%+.1f (chutes %.1f %%)' % st(Q & (vx >= 1.5) & (rRA >= .5)), 'n', cnt(Q & (vx >= 1.5) & (rRA >= .5)))
