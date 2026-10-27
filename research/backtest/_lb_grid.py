"""Grille des bonds : taille de la semaine, volume, position (nouveau plus haut de l'année ou non), tendance, hors 🎯."""
import numpy as np
exec(open('_longue_base2.py').read().split("if __name__ == '__main__':")[0])
vy52 = vy
print("=== Grille (à 6 mois puis 12 mois) : semaine ≥ x %, volume ≥ y fois la moyenne de l'année, nouveau plus haut de l'année, hors 🎯")
for h in (26, 52):
    print(f"--- {h} semaines")
    for x in (.06, .08, .10, .12, .15):
        for y in (1.5, 2, 3):
            ev(f'semaine ≥ +{x*100:.0f} %, volume ≥ {y}×, plus haut de l\'année, hors 🎯', valid & (r1 >= x) & (vy52 >= y) & (gap52 >= 0) & ~Q, h)
print("\n=== Définition actuelle du 📣 (≥ +8 %, ≥ 3×, en tendance, hors 🎯) et variantes")
for h in (26, 52):
    print(f"--- {h} semaines")
    ev('📣 actuel : ≥ +8 %, ≥ 3×, tendance, hors 🎯', valid & (r1 >= .08) & (vy52 >= 3) & trend & ~Q, h)
    ev('  … dont au plus haut de l\'année', valid & (r1 >= .08) & (vy52 >= 3) & trend & ~Q & (gap52 >= 0), h)
    ev('  … dont pas au plus haut de l\'année', valid & (r1 >= .08) & (vy52 >= 3) & trend & ~Q & (gap52 < 0), h)
    ev('≥ +8 %, 2× à 3×, plus haut de l\'année, hors 🎯 (ajout possible)', valid & (r1 >= .08) & (vy52 >= 2) & (vy52 < 3) & (gap52 >= 0) & ~Q, h)
    ev('≥ +8 %, 2× à 3×, tendance, pas au plus haut, hors 🎯', valid & (r1 >= .08) & (vy52 >= 2) & (vy52 < 3) & (gap52 < 0) & trend & ~Q, h)
    ev('≥ +8 %, ≥ 2×, plus haut de l\'année, sans tendance, hors 🎯', valid & (r1 >= .08) & (vy52 >= 2) & (gap52 >= 0) & ~trend & ~Q, h)
    ev('≥ +8 %, ≥ 2×, plus haut de l\'année, en tendance, hors 🎯', valid & (r1 >= .08) & (vy52 >= 2) & (gap52 >= 0) & trend & ~Q, h)
    ev('≥ +8 %, ≥ 2×, plus haut de l\'année, dans le 🎯', valid & (r1 >= .08) & (vy52 >= 2) & (gap52 >= 0) & Q, h)
