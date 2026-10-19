"""Pistes académiques dans le 🎯 : effet « loterie » (MAX, Bali 2011), persistance (ratio de variance, Lo-MacKinlay), bêta (Frazzini-Pedersen), asymétrie."""
import numpy as np
src = open('_timing.py').read(); exec(src.split("print('référence")[0])
Q = Q & ~(ext10 < 0)  # règle actuelle : au-dessus de la moyenne 10 semaines
MAX = np.full_like(P, np.nan)
for t in range(13, T): MAX[:, t] = np.nanmax(r1[:, t-12:t+1], 1)
VR = np.full_like(P, np.nan); BETA = np.full_like(P, np.nan); SK = np.full_like(P, np.nan)
for t in range(56, T):
    R1 = r1[:, t-51:t+1]
    v1 = np.nanvar(R1, 1)
    R4 = P[:, t-48:t+1:4][:, 1:] / P[:, t-48:t+1:4][:, :-1] - 1
    VR[:, t] = np.nanvar(R4, 1) / (4 * v1)
    M = mk[t-51:t+1]; Mc = M - np.nanmean(M); Rc = R1 - np.nanmean(R1, 1, keepdims=True)
    BETA[:, t] = np.nansum(Rc * Mc, 1) / np.nansum(Mc ** 2)
    SK[:, t] = np.nanmean(Rc ** 3, 1) / np.nanvar(R1, 1) ** 1.5
def split(lab, A, cuts, names):
    print('\n' + lab); row('référence', Q)
    for (a, b), n in zip(zip(cuts[:-1], cuts[1:]), names): row(n, Q & (A >= a) & (A < b))
def qcut(A, M):
    v = A[M & np.isfinite(A)]; return list(np.nanpercentile(v, [0, 33.3, 66.7, 100]))
c = qcut(MAX, Q); c[-1] += 1; split('1. plus forte hausse hebdomadaire sur 3 mois (effet « loterie »)', MAX, c, [f'faible (< {c[1]*100:.0f} %)', 'moyenne', f'forte (> {c[2]*100:.0f} %)'])
c = qcut(VR, Q); c[-1] += 1; split('2. persistance de la tendance (ratio de variance 4 semaines)', VR, c, [f'faible (< {c[1]:.2f})', 'moyenne', f'forte (> {c[2]:.2f})'])
c = qcut(BETA, Q); c[-1] += 1; split('3. bêta (sensibilité au marché, 1 an)', BETA, c, [f'faible (< {c[1]:.2f})', 'moyen', f'fort (> {c[2]:.2f})'])
c = qcut(SK, Q); c[-1] += 1; split('4. asymétrie des rendements hebdomadaires (1 an)', SK, c, ['négative', 'moyenne', 'positive'])
# 5. distribution des rendements à 6 mois des 🎯 (probabilités)
f = fut[Q & np.isfinite(fut)]
print('\n5. distribution à 6 mois (🎯 au-dessus de la moyenne 10 sem.) : médiane %+.0f %%, P(>0) %.0f %%, P(≥+20 %%) %.0f %%, P(≥+50 %%) %.0f %%, P(≤−25 %%) %.0f %%, P(≤−40 %%) %.0f %%' % (np.median(f)*100, (f>0).mean()*100, (f>=.2).mean()*100, (f>=.5).mean()*100, (f<=-.25).mean()*100, (f<=-.4).mean()*100))
a = fut[valid & np.isfinite(fut)]
print('   toutes les sociétés : médiane %+.0f %%, P(>0) %.0f %%, P(≥+20 %%) %.0f %%, P(≥+50 %%) %.0f %%, P(≤−25 %%) %.0f %%' % (np.median(a)*100, (a>0).mean()*100, (a>=.2).mean()*100, (a>=.5).mean()*100, (a<=-.25).mean()*100))
