"""Règle d'affichage proposée : 📣 actuel (≥ +8 %, volume ≥ 3×) OU bond ≥ +8 % sur volume ≥ 2× qui fait un nouveau plus haut de
l'année ; en tendance, hors 🎯. Fenêtre d'affichage : bond dans les 4 dernières semaines (comme le site)."""
import numpy as np
exec(open('_longue_base2.py').read().split("if __name__ == '__main__':")[0])
okn = fin(mom) & fin(s26)
R0 = (r1 >= .08) & (vy >= 3)
R1 = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
for h in (26, 52):
    print(f"--- {h} semaines, entrée la semaine du bond")
    ev('📣 actuel (≥ 3×), tendance, hors 🎯', valid & R0 & trend & ~Q, h)
    ev('📣 proposé (≥ 3×, ou ≥ 2× au plus haut de l\'année), tendance, hors 🎯', valid & (R0 | R1) & trend & ~Q, h)
    ev('  … ajout seul (2× à 3×, au plus haut de l\'année)', valid & R1 & ~R0 & trend & ~Q, h)
print("--- entrée pendant la fenêtre d'affichage (bond il y a 0 à 3 semaines, une entrée par bond, cours encore en tendance)")
for lab, R in [('actuel', R0), ('proposé', R0 | R1)]:
    E = valid & R & trend & ~Q
    for k in (0, 3):
        Mk = bshift(dedup(E, 26), k) if k else dedup(E, 26)
        ev(f'{lab}, entrée {k} semaine(s) après', Mk & valid & trend, 26, k=0)
# fréquence : signaux par semaine sur 2018-2026 (≈ 1 000 sociétés ; le site en classe ≈ 700)
for lab, R in [('actuel', R0), ('proposé', R0 | R1)]:
    E = dedup(okn & R & trend & ~Q, 26)
    a = int(np.searchsorted(yr, 2018))
    print(f"  {lab} : {E[:, a:].sum() / ((T - a) / 52):.0f} bonds par an (≈ {E[:, a:].sum() / (T - a) * 4:.1f} affichés à la fois sur 4 semaines)")
# les 4 sociétés en 2025-2026
for s in ['BRAV.ST', 'WAWI.OL', 'REP.MC', 'DEC.PA']:
    i = cols.index(s)
    w = [f"{dates[t]} {P[i,t]:.2f} ({r1[i,t]*100:+.0f} %, ×{vy[i,t]:.1f}{', plus haut an' if gap52[i,t] >= 0 else ''}{', tendance' if trend[i,t] else ''})"
         for t in range(T - 60, T) if (R0 | R1)[i, t]]
    print(f"  {s} : " + ('\n             '.join(w) if w else 'aucun'))
