"""Parmi les bonds au plus haut de l'année (semaine ≥ +8 %, volume ≥ 2× l'année, en tendance, hors 🎯) : ce qui distingue les
gagnantes, et le moment d'entrée (semaine du bond, ou 1 à 8 semaines plus tard)."""
import numpy as np
exec(open('_longue_base2.py').read().split("if __name__ == '__main__':")[0])
J = valid & (r1 >= .08) & (vy >= 2) & (gap52 >= 0) & trend & ~Q
mon = np.array([int(d[5:7]) for d in dates])
earn = np.isin(mon, [1, 2, 4, 5, 7, 8, 10, 11])[None, :] & np.ones((N, 1), bool)   # mois de résultats (approché)
fresh = ~bshift(ago_any(gap52 >= 0, 13), 1)          # premier plus haut de l'année depuis 3 mois
new5 = P > H5
for h in (26, 52):
    print(f"\n=== Ce qui distingue les gagnantes (à {h // 4.33:.0f} mois)")
    ev('tous (≥ +8 %, ≥ 2×, plus haut de l\'année, tendance, hors 🎯)', J, h)
    for lab, M in [('bond +8 à 10 %', (r1 < .10)), ('bond +10 à 15 %', (r1 >= .10) & (r1 < .15)), ('bond ≥ +15 %', r1 >= .15),
                   ('volume 2 à 3×', vy < 3), ('volume 3 à 5×', (vy >= 3) & (vy < 5)), ('volume ≥ 5×', vy >= 5),
                   ('12 mois avant : < 0 %', mom < 0), ('12 mois : 0 à 30 %', (mom >= 0) & (mom < .3)), ('12 mois : 30 à 60 %', (mom >= .3) & (mom < .6)),
                   ('12 mois : ≥ 60 % (hors 🎯 pour une autre raison)', mom >= .6),
                   ('longue base (plus haut de 5 ans vieux de 2 ans, creux ≥ 35 %)', longbase), ('sans longue base', ~longbase & fin(H5)),
                   ('nouveau plus haut de 5 ans', new5), ('sous le plus haut de 5 ans', ~new5 & fin(H5)),
                   ('premier plus haut de l\'année depuis 3 mois', fresh), ('déjà au plus haut ces 3 mois', ~fresh),
                   ('mois de résultats', earn), ('hors mois de résultats', ~earn),
                   ('marché porteur (> 50 % des sociétés au-dessus de MM40)', (mkt_up > .5)[None, :]), ('marché faible', (mkt_up <= .5)[None, :])]:
        ev('  ' + lab, J & M, h)
print("\n=== Moment d'entrée : à 6 mois depuis l'entrée (excès), selon le délai et si le bond a tenu")
J1 = dedup(J, 26)
for k in (0, 1, 2, 4, 8, 13):
    Mk = bshift(J1, k) if k else J1
    held = P >= shift(P, k) * .95 if k else np.ones_like(J1)              # cours encore à 5 % près de celui de la semaine du bond
    ev(f'entrée {k} semaine(s) après le bond', Mk & valid, 26, k=0)
    if k:
        ev(f'  … bond tenu (cours ≥ 95 % de celui du bond)', Mk & valid & held, 26, k=0)
        ev(f'  … bond perdu', Mk & valid & ~held, 26, k=0)
# devenir : entrée 🎯 dans les 6 mois, hausse déjà faite
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
lead_w, lead_r = [], []
tot = 0
for i, t in zip(*np.where(J1)):
    tot += 1
    qs = np.where(Qentry[i, t+1:t+27])[0]
    if len(qs):
        lead_w.append(qs[0] + 1); lead_r.append(P[i, t + 1 + qs[0]] / P[i, t] - 1)
print(f"\n  {len(lead_w)} bonds sur {tot} ({len(lead_w)/tot*100:.0f} %) suivis d'une entrée 🎯 dans les 6 mois ; délai médian {np.median(lead_w):.0f} semaines ; "
      f"hausse déjà faite à l'entrée 🎯 : médiane {np.median(lead_r)*100:+.0f} %, moyenne {np.mean(lead_r)*100:+.0f} %")
