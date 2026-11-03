"""🚩 Drapeau après 📣 (relance) : chiffres pour l'affichage (conditions de la page), une semaine plus tard, à 12 mois, dans le 🎯."""
import numpy as np
exec(open('_selection_sim6.py').read().split("\nif __name__ == '__main__':")[0])
okb = valid & ~(v52 >= .8)
disp = okb & trend & (mpn >= 1/3)
print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]}")
for h in (13, 26, 52):
    print(f"— à {h // 4.33:.0f} mois")
    ev('relance 2-6 sem. après un 📣, hors 🎯', okb & REL & ~Q, h)
    ev('  … conditions de la page (tendance, hors tiers faible)', disp & REL & ~Q, h)
    ev('  … achat une semaine plus tard', bshift(disp & REL & ~Q, 1) & valid, h)
    ev('📣 bond en tendance hors 🎯 (rappel)', okb & BND & ~Q, h)
compare('🎯 avec relance cette semaine', Q & REL, Q & ~REL)
compare('🎯 avec relance dans les 2 semaines', Q & ago_any(REL, 2), Q & ~ago_any(REL, 2))
F = dedup(disp & REL & ~Q, 26)
print('cas par an (dernières années) :', {int(y): int(F[:, yr == y].sum()) for y in range(2019, 2027)})
