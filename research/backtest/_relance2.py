"""🚩 relance : toutes les semaines affichées (sans ne garder que la première), comme la page."""
import numpy as np
exec(open('_selection_sim6.py').read().split("\nif __name__ == '__main__':")[0])
okb = valid & ~(v52 >= .8)
disp = okb & trend & (mpn >= 1/3)
for h in (26, 52):
    ev(f'relance, chaque semaine affichée (à {h} sem.)', disp & REL & ~Q, h, k=0)
    ev(f'relance cette semaine ou la précédente (à {h} sem.)', disp & ago_any(REL, 2) & ~Q, h, k=0)
    ev(f'📣 bond il y a 2 à 6 sem., sans nouveau plus haut depuis (à {h} sem.)', disp & ~ago_any(REL, 2) & (ago_any(BND, 7) & ~ago_any(BND, 2)) & ~Q, h, k=0)
