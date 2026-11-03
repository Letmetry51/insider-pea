"""📣 qui casse un drapeau : est-ce le repos (la figure) ou seulement la forte hausse d'avant ? Contrôles."""
import numpy as np
exec(open('_selection_sim7.py').read().split("\nif __name__ == '__main__':")[0])
okb = valid & ~(v52 >= .8)
BT = (R0 | R1) & trend & ~Q & okb
F = flag()
lo8p = shift(roll(P, 8, np.nanmin), 1)
run30 = P / lo8p - 1 >= .30                       # +30 % ou plus en 8 semaines, semaine du bond comprise
pre30 = ago_any(shift(P, 1) / shift(lo8p, 1) - 1 >= .30, 6)   # +30 % en 8 sem. atteint dans les 6 semaines avant le bond
hi26p = shift(roll(P, 26, np.nanmax), 1)
ev('📣 qui casse un drapeau', BT & F, 26)
ev('📣 après +30 % en 8 sem. (avant le bond), sans drapeau', BT & pre30 & ~F, 26)
ev('📣 qui fait à lui seul +30 % en 8 sem., sans drapeau', BT & run30 & ~pre30 & ~F, 26)
ev('📣 au plus haut de 26 sem., sans forte hausse avant', BT & (P > hi26p) & ~pre30 & ~F, 26)
ev('📣 sans rien de tout ça', BT & ~pre30 & ~run30 & ~F, 26)
