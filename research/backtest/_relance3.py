"""📣 qui sort d'un drapeau (cassure du drapeau la semaine du bond) contre les autres 📣."""
import numpy as np
exec(open('_figures3.py').read().split("\nif __name__ == '__main__':")[0])
F0 = np.load('flag0.npy')
BT = BOND & trend & ~Q & okb
for h in (26, 52):
    ev(f'📣 qui casse un drapeau la même semaine (à {h} sem.)', BT & F0, h)
    ev(f'📣 dans les 4 sem. après une cassure de drapeau (à {h} sem.)', BT & ago_any(F0, 5) & ~F0, h)
    ev(f'📣 sans drapeau (à {h} sem.)', BT & ~ago_any(F0, 5), h)
