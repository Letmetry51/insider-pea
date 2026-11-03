"""Suite de _figures.py : t de chaque figure, et ce qui reste quand on retire ce que l'outil voit déjà (📣 bond, 🎯, forte hausse
récente sans repos). Dans le 🎯 : figure contre autres 🎯 de la même semaine (compare de _depart.py)."""
import numpy as np
exec(open('_figures.py').read().split("\nif __name__ == '__main__':")[0].split("\nDB = np.zeros_like")[0])
z2 = np.load('figures.npz')
DB, IHS, CUP, TRI, FLAG, HTF, DT, HS = (z2[k] for k in ('DB', 'IHS', 'CUP', 'TRI', 'FLAG', 'HTF', 'DT', 'HS'))
GC = (m10 > m40) & (shift(m10, 1) <= shift(m40, 1))
DC = (m10 < m40) & (shift(m10, 1) >= shift(m40, 1))
hi26p = shift(roll(P, 26, np.nanmax), 1)
R0 = (r1 >= .08) & (vy >= 3); R1_ = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
BOND = (R0 | R1_)
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
okb = valid & ~(v52 >= .8)
lo8 = shift(roll(P, 8, np.nanmin), 1)
pole30 = ago_any(P / lo8 - 1 >= .30, 8)                       # forte hausse récente (≥ +30 % en 8 semaines) dans les 2 derniers mois
newhi8 = P > shift(roll(P, 8, np.nanmax), 1)                  # nouveau plus haut de 8 semaines
bond4 = ago_any(BOND, 4)

if __name__ == '__main__':
    print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]} (à 6 mois, écart avec la moyenne des sociétés)")
    print("\n=== t de chaque figure (toutes)")
    for lab, M in [('golden cross', GC), ('death cross', DC), ('double creux', DB), ('tête-épaules inversée', IHS),
                   ('tasse avec anse', CUP), ('tasse avec anse, volume ≥ 1,4×', CUP & (vy >= 1.4)), ('triangle ascendant', TRI),
                   ('drapeau', FLAG), ('high tight flag', HTF), ('double sommet', DT), ('tête-épaules', HS)]:
        ev(lab, okb & M, 26)
    print("\n=== drapeau : ce qui reste sans 📣 ni 🎯, face à une forte hausse récente sans figure")
    ev('drapeau, sans 📣 dans les 4 semaines, hors 🎯', okb & FLAG & ~bond4 & ~Q, 26)
    ev('drapeau, avec 📣 dans les 4 semaines, hors 🎯', okb & FLAG & bond4 & ~Q, 26)
    ev('contrôle : +30 % en 8 sem. puis nouveau plus haut de 8 sem., sans drapeau, hors 🎯', okb & pole30 & newhi8 & ~FLAG & ~Q, 26)
    ev('contrôle : idem, sans 📣', okb & pole30 & newhi8 & ~FLAG & ~Q & ~bond4, 26)
    ev('📣 bond en tendance hors 🎯 (référence)', okb & BOND & trend & ~Q, 26)
    ev('drapeau en tendance, hors 🎯', okb & FLAG & trend & ~Q, 26)
    ev('drapeau en tendance, hors 🎯, sans 📣', okb & FLAG & trend & ~Q & ~bond4, 26)
    print("\n=== tasse avec anse : sans 📣")
    ev('tasse avec anse, sans 📣 (4 sem.), hors 🎯', okb & CUP & ~bond4 & ~Q, 26)
    ev('tasse avec anse, volume ≥ 1,4×, sans 📣, hors 🎯', okb & CUP & (vy >= 1.4) & ~bond4 & ~Q, 26)
    ev('tasse avec anse en tendance, hors 🎯, sans 📣', okb & CUP & trend & ~bond4 & ~Q, 26)
    print("\n=== dans le 🎯 : figure contre les autres 🎯 de la même semaine (écart, t semaine par semaine)")
    for lab, M in [('drapeau', FLAG), ('triangle ascendant', TRI), ('tasse avec anse', CUP), ('high tight flag', HTF),
                   ('death cross', DC), ('double sommet', DT), ('tête-épaules', HS)]:
        compare(f'🎯 avec {lab} cette semaine', Q & M, Q & ~M)
        compare(f'🎯 avec {lab} dans les 4 dernières semaines', Q & ago_any(M, 4), Q & ~ago_any(M, 4))
    print("\n=== entrée 🎯 précédée d'un drapeau (dans les 8 semaines) ou non")
    ev('entrée 🎯 après un drapeau', Qentry & ago_any(FLAG, 8), 26)
    ev('entrée 🎯 sans drapeau', Qentry & ~ago_any(FLAG, 8), 26)
