"""Combien de fois la société a-t-elle déjà fait un nouveau plus haut sur un an dans l'année ? Effet sur les 6 mois suivants (1997-2026)."""
import numpy as np
src = open('_detect.py').read(); exec(src.split("# 1. grenouille")[0])
yr = np.array([int(d[:4]) for d in dates]); t0 = int(np.argmax(valid.sum(0) > 30))
E3 = [('97-08', t0, int(np.searchsorted(yr, 2009))), ('09-17', int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))), ('18-26', int(np.searchsorted(yr, 2018)), T)]
exec(src[src.index("def st("):src.index("B = valid")])
# plus haut sur 52 semaines et plus haut historique (sur l'historique disponible, au moins 5 ans)
hi = np.full_like(P, np.nan)
for t in range(51, T): hi[:, t] = np.nanmax(P[:, t-51:t+1], 1)
ratio = P / hi
prevhi = np.full_like(P, np.nan); prevhi[:, 52:] = np.fmax.reduce([P[:, 52-k:T-k] for k in range(1, 53)]) if False else np.nan
newhi = np.zeros_like(P, dtype=bool)
for t in range(52, T): newhi[:, t] = P[:, t] > np.nanmax(P[:, t-52:t], 1)
ath = np.zeros_like(P, dtype=bool); run = np.full(N, -np.inf); age = np.zeros(N)
for t in range(T):
    p = P[:, t]; ok = np.isfinite(p); age += ok
    ath[:, t] = ok & (p >= run * 0.999) & (age >= 260); run = np.where(ok, np.fmax(run, p), run)
# épisodes : début d'une série de nouveaux plus hauts après au moins 4 semaines sans nouveau plus haut
start = np.zeros_like(newhi)
for t in range(52, T): start[:, t] = newhi[:, t] & ~np.any(newhi[:, max(0, t-4):t], 1)
ep = np.zeros_like(P)  # nombre d'épisodes dans les 52 dernières semaines (celui en cours compris)
c = np.cumsum(start, 1)
ep[:, 52:] = c[:, 52:] - c[:, :-52]
# replis : nombre de baisses d'au moins 10 % depuis un plus haut suivies d'un nouveau plus haut, sur l'année
near = valid & (ratio >= 0.95) & trend
B = valid & (mp >= 2/3) & trend & (s26 >= .41); Q = B & (mom >= .6) & (mom <= 2)
def row(lab, M):
    r = st(M)
    if r is None: return
    per = '  '.join(f"{l} {st(M, x, y)[0]:+5.1f}" for l, x, y in E3)
    print(f"  {lab:34s} {r[0]:+6.1f} pts  chutes {r[1]:4.1f} %  n={int(M.sum()):6d} | {per}")
for g, G in [('près du plus haut (≤ 5 %) et en tendance', near), ('classement + pente forte, près du plus haut', B & (ratio >= .95)), ('🎯 filtres, près du plus haut', Q & (ratio >= .95))]:
    print('\n==', g, ': nombre d\'épisodes de nouveaux plus hauts sur 12 mois')
    for lab, M in [('1re fois (aucun autre dans l\'année)', ep == 1), ('2e fois', ep == 2), ('3e fois', ep == 3), ('4e fois', ep == 4), ('5e fois ou plus', ep >= 5)]:
        row(lab, G & M)
    row('au plus haut historique (≥ 5 ans)', G & ath)
    row('pas au plus haut historique', G & ~ath)
print('\nRépartition actuelle possible : part des 🎯 près du plus haut par nombre d\'épisodes :', [round(((Q & (ratio >= .95) & (ep == k)).sum() / (Q & (ratio >= .95)).sum()) * 100) for k in range(1, 6)])
