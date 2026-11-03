"""📣 qui casse un drapeau : solidité des réglages du drapeau, et selon le type de bond (3 fois le volume, ou 2 fois au plus haut)."""
import numpy as np
exec(open('_figures3.py').read().split("\nif __name__ == '__main__':")[0])
BT = BOND & trend & ~Q & okb
print("à 6 mois, 📣 en tendance hors 🎯 qui casse un drapeau la même semaine")
ev('référence (mât +30 % en 8 sem., repos 2-6 sem., repli ≤ 15 %)', BT & flag(), 26)
for kw, lab in ((dict(pole=.2), 'mât +20 %'), (dict(pole=.4), 'mât +40 %'), (dict(pole=.15), 'mât +15 %'), (dict(K=4), 'mât en 4 sem.'),
                (dict(K=13), 'mât en 13 sem.'), (dict(wmin=1, wmax=3), 'repos 1-3 sem.'), (dict(wmin=3, wmax=8), 'repos 3-8 sem.'),
                (dict(wmin=2, wmax=10), 'repos 2-10 sem.'), (dict(dd=.10), 'repli ≤ 10 %'), (dict(dd=.25), 'repli ≤ 25 %'),
                (dict(pole=.2, dd=.25, wmin=1, wmax=10, K=13), 'large : +20 % en 13 sem., repos 1-10, repli 25 %')):
    ev(lab, BT & flag(**kw), 26)
ev('bond 3 fois le volume', BT & flag() & R0, 26)
ev('bond 2 fois le volume au plus haut, pas 3 fois', BT & flag() & R1_ & ~R0, 26)
ev('à 3 mois', BT & flag(), 13)
ev('sans tendance (même figure)', BOND & ~trend & ~Q & okb & flag(), 26)
ev('dans le 🎯 (même figure)', BOND & Q & flag(), 26)
ev('figure sans 📣 (cassure du drapeau sans gros volume)', okb & ~Q & flag() & ~BOND & (vy < 2), 26)
F = dedup(BT & flag(), 26)
print('cas par an :', {int(y): int(F[:, yr == y].sum()) for y in range(2010, 2027)})
