"""Longue base puis bond (Bravida sur 5 ans, montré le 27/10/2026) : toutes les sociétés qui ont eu ce tracé, 1990-2026.

Tracé : un plus haut vieux de 2 ans ou plus (sur 5 ans), une chute d'au moins 35 % depuis, une remontée, puis le retour à moins de 5 %
de ce plus haut. On distingue le retour par un bond (semaine ≥ +10 %) du retour progressif. Mesure commune (_depart.py) : écart de
rendement avec la société moyenne de la même semaine, à 6 et 12 mois.

    python _longue_base.py       (dans le dossier qui contient long.npz)
"""
import numpy as np
exec(open('_depart.py').read().split('print(f"Données')[0])
cols = list(z['cols'])

# ---------------------------------------------------------------- plus haut sur 5 ans, son âge, le plus bas depuis
W5 = 260
H5 = np.full_like(P, np.nan); AGE = np.full_like(P, np.nan); LOWS = np.full_like(P, np.nan)
jj = np.arange(W5)[None, :]
for t in range(W5, T):
    w = P[:, t-W5:t]
    ok = fin(w).sum(1) >= W5 * .85
    if not ok.any():
        continue
    wf = np.where(fin(w), w, -np.inf)
    am = wf.argmax(1)
    hi = wf[np.arange(N), am]
    lo = np.where((jj >= am[:, None]) & fin(w), w, np.inf).min(1)
    H5[ok, t] = hi[ok]; AGE[ok, t] = (W5 - am)[ok]; LOWS[ok, t] = lo[ok]
depth = LOWS / H5 - 1                 # creux depuis le plus haut (négatif)
gap5 = P / H5 - 1                     # distance au plus haut de 5 ans
near = gap5 >= -.05
longbase = (AGE >= 104) & (depth <= -.35)
vy = VO / shift(sma(VO, 52), 1)       # volume de la semaine / moyenne de l'année précédente
r4 = P / shift(P, 4) - 1
fut13 = np.full_like(P, np.nan); fut13[:, :-13] = P[:, 13:] / P[:, :-13] - 1

# rang 12 mois sans regarder la suite (pour les semaines récentes)
okn = fin(mom) & fin(s26)
mpn = np.full_like(P, np.nan)
for t in range(T):
    ok = okn[:, t]
    if ok.sum() > 30:
        mpn[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
Qn = okn & (mpn >= 2/3) & trend & (s26 >= .41) & (mom >= .6) & (mom <= 2) & ~(v52 >= .8)

# ---------------------------------------------------------------- les événements (première semaine du retour près du plus haut)
first_near = longbase & near & ~(shift(gap5, 1) >= -.05)
jump10 = r1 >= .10
E_all = first_near
E_jump = first_near & jump10
E_slow = first_near & ~(r1 >= .05)
E_new = longbase & (P > H5) & ~bshift(ago_any(P > H5, 26), 1)          # nouveau plus haut de 5 ans, premier en 6 mois
print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]}")
print(f"Tracé « longue base » (plus haut de 5 ans vieux de 2 ans ou plus, creux ≥ 35 %) : retours près du plus haut {int((valid & E_all).sum())}, "
      f"dont par un bond ≥ +10 % : {int((valid & E_jump).sum())}, progressifs (semaine < +5 %) : {int((valid & E_slow).sum())}")

print("\n=== 1. Que deviennent-elles ? (écart avec la société moyenne à 6 mois, toutes périodes)")
line('🎯 (référence)', Q)
line('retour près du plus haut de 5 ans après une longue base (tous)', valid & E_all)
line('  … par un bond (semaine ≥ +10 %)', valid & E_jump)
line('  … par un bond, volume ≥ 2× l\'année', valid & E_jump & (vy >= 2))
line('  … par un bond, volume ≥ 3× l\'année', valid & E_jump & (vy >= 3))
line('  … progressif (semaine < +5 %)', valid & E_slow)
line('nouveau plus haut de 5 ans après une longue base', valid & E_new)
line('  … la semaine d\'un bond ≥ +10 %', valid & E_new & jump10)
line('bond ≥ +10 % (volume ≥ 2×) sans longue base, près du plus haut', valid & jump10 & (vy >= 2) & near & ~longbase & ~bshift(ago_any(near, 4), 1))
line('bond ≥ +10 % (volume ≥ 2×) loin du plus haut (> 20 % dessous)', valid & jump10 & (vy >= 2) & (gap5 < -.2))
print("\n  À 12 mois :")
for k, M in [('🎯 (référence)', Q), ('retour près du plus haut, longue base (tous)', valid & E_all), ('  … par un bond ≥ +10 %', valid & E_jump),
             ('  … par un bond, volume ≥ 2×', valid & E_jump & (vy >= 2)), ('  … progressif', valid & E_slow),
             ('nouveau plus haut de 5 ans, longue base', valid & E_new)]:
    e, cr, bg, n = st(M, F=fut52)
    print(f"  {k:58s} {e:+5.1f} pts à 12 mois · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n} cas")

# ---------------------------------------------------------------- liste complète (pour la galerie)
rows = []
for i, t in zip(*np.where(E_all & (np.arange(T)[None, :] >= W5))):
    def g(a, k=0):
        return float(a[i, t]) if fin(a[i, t]) else None
    def fwd(h):
        return float(P[i, t+h] / P[i, t] - 1) if t + h < T and fin(P[i, t+h]) else None
    def mk(h):  # moyenne des sociétés sur la même période (écrêtée comme st())
        if t + h >= T:
            return None
        F = P[:, t+h] / P[:, t] - 1; ok = fin(F)
        if ok.sum() < 30:
            return None
        lo_, hi_ = np.nanpercentile(F[ok], [2, 98])
        return float(np.mean(np.clip(F[ok], lo_, hi_)))
    rows.append(dict(sym=cols[i], sec=str(z['sec'][i]) if 'sec' in z.files else '', date=str(dates[t]), p=float(P[i, t]),
                     r1=g(r1), vy=g(vy), depth=g(depth), age=g(AGE), gap=g(gap5), mom=g(mom), mp=g(mpn), s26=g(s26),
                     trend=bool(trend[i, t]), q=bool(Qn[i, t]), f13=fwd(13), f26=fwd(26), f52=fwd(52), m26=mk(26), m52=mk(52)))
import json
json.dump(rows, open('longue_base_events.json', 'w'))
print(f"\n{len(rows)} événements écrits dans longue_base_events.json")
