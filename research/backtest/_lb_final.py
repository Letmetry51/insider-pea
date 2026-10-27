"""Règle retenue pour l'affichage (27/10/2026) : semaine ≥ +8 % sur 3 fois le volume de l'année, ou sur 2 fois si elle fait un nouveau
plus haut de l'année ; en tendance ; hors 🎯 ; hors tiers le plus faible sur 12 mois. Chiffres de la note et de l'aide."""
import numpy as np
exec(open('_longue_base2.py').read().split("if __name__ == '__main__':")[0])
R0 = (r1 >= .08) & (vy >= 3); R1 = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
base = trend & ~Q & valid & (mp >= 1/3)
F = (R0 | R1) & base
r6 = ev('📣 retenu', F, 26); r12 = ev('📣 retenu, 12 mois', F, 52)
ev('📣 3 fois le volume seul (même filtre)', R0 & base, 26)
ev('  … ajout seul (2 à 3 fois, au plus haut)', R1 & ~R0 & base, 26)
ev('  … ajout seul, 12 mois', R1 & ~R0 & base, 52)
F1 = dedup(F, 26)
ev('entrée 3 semaines après', bshift(F1, 3) & valid & trend, 26, k=0)
ev('avec longue base', F & longbase, 26); ev('sans longue base', F & ~longbase & fin(H5), 26)
ev('avec longue base, 12 mois', F & longbase, 52); ev('sans longue base, 12 mois', F & ~longbase & fin(H5), 52)
ev('même bond sans tendance', (R0 | R1) & ~trend & ~Q & valid & (mp >= 1/3), 26)
Qentry = Q & ~bshift(ago_any(Q, 26), 1); lead = []
for i, t in zip(*np.where(F1)):
    lead.append(bool(Qentry[i, t+1:t+27].any()))
okn = fin(mom) & fin(s26); a = int(np.searchsorted(yr, 2018))
mpn2 = mpn
Fn = dedup(((R0 | R1) & trend & ~Qn & okn & (mpn2 >= 1/3)), 26)
print(f"rejoignent le 🎯 dans les 6 mois : {np.mean(lead)*100:.0f} % ; {Fn[:, a:].sum() / ((T - a) / 52):.0f} bonds par an depuis 2018 (≈ 1 000 sociétés)")
