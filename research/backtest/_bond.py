"""📣 bond sur gros volume hors 🎯 (comme Bravida le 08/05/2026) : solidité (périodes, hors échantillon, 12 mois), définition du calcul
du soir (volume de la semaine ≥ 3 fois la moyenne de l'année, semaine ≥ +8 %), et devenir (entrée 🎯 ensuite ?)."""
import numpy as np
exec(open('_reprise.py').read().split('print("=== Anciennes')[0])
vy = VO / shift(sma(VO, 52), 1)
bumpY = (ret1 >= .08) & (vy >= 3)                       # définition du calcul du soir (moyenne de l'année)
inT = valid & trend
cases = [
    ('📣 bond (semaine ≥ +8 %, volume ≥ 3× l\'année), en tendance', inT & bumpY),
    ('  … hors 🎯', inT & bumpY & ~Q),
    ('  … hors 🎯, 12 mois sous +60 % (pas encore en momentum)', inT & bumpY & ~Q & (mom < .6)),
    ('  … hors 🎯, sortie de base 13 sem. la même semaine', inT & bumpY & ~Q & B13),
    ('  … hors 🎯, au plus haut de l\'année', inT & bumpY & ~Q & (dd52 >= -.001)),
    ('  … hors 🎯, 12 mois dans la moitié haute', inT & bumpY & ~Q & (mp >= .5)),
    ('📣 bond sans tendance (rebond d\'une société en baisse)', valid & bumpY & ~trend),
    ('📣 bond dans le 🎯 (déjà retenu)', Q & bumpY),
]
for k, M in cases:
    line(k, M)
print("\n  À 12 mois :")
for k, M in [cases[0], cases[1], cases[2], cases[3]]:
    e, cr, bg, n = st(M, F=fut52)
    print(f"  {k:58s} {e:+5.1f} pts à 12 mois · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n} cas")
# devenir : 📣 hors 🎯 suivi d'une entrée 🎯 dans les 6 mois ; nombre de signaux par an
M = inT & bumpY & ~Q
first = M & ~bshift(ago_any(M, 13), 1)
led = np.zeros_like(Q)
for k2 in range(1, 27):
    led |= blead(Qentry, k2)
per_year = first[:, t0:].sum() / ((T - t0) / 52)
print(f"\n  📣 hors 🎯 : {int(first.sum())} signaux (≈ {per_year:.0f} par an sur ≈ 1 000 sociétés) ; suivis d'une entrée 🎯 dans les 6 mois : "
      f"{(first & led).sum() / max(first.sum(), 1) * 100:.0f} %")
# en 2025-2026 : les signaux de l'année et les 4 sociétés
i_s = {s: cols.index(s) for s in ['WAWI.OL', 'REP.MC', 'BRAV.ST', 'DEC.PA']}
for s, i in i_s.items():
    w = [f"{dates[t]} ({ret1[i,t]*100:+.0f} %, volume ×{vy[i,t]:.1f})" for t in range(T - 56, T) if bumpY[i, t]]
    w2 = [f"{dates[t]} ({ret1[i,t]*100:+.0f} %, ×{vy[i,t]:.1f})" for t in range(T - 56, T) if ret1[i, t] >= .08]
    print(f"  {s} : 📣 {w or 'aucun'} ; semaines ≥ +8 % : {w2}")
