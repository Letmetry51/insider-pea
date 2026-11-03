"""Drapeau : solidité des réglages (mât, durée du repos, repli permis), détection vectorisée identique à _figures.py ; et relance
après un 📣 (cassure du plus haut atteint depuis le bond, 3 à 8 semaines plus tard), avec ou sans forme de drapeau."""
import numpy as np
exec(open('_longue_base2.py').read().split("\nif __name__ == '__main__':")[0])
R0 = (r1 >= .08) & (vy >= 3); R1_ = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
BOND = (R0 | R1_)
okb = valid & ~(v52 >= .8)
P1 = shift(P, 1)
RM = {w: shift(roll(P, w, np.nanmax), 1) for w in range(1, 11)}      # plus haut des w semaines avant celle-ci
Rm = {w: shift(roll(P, w, np.nanmin), 1) for w in range(1, 11)}
LO = {k: roll(P, k, np.nanmin) for k in (4, 8, 13)}


def flag(pole=.30, K=8, wmin=2, wmax=6, dd=.15):
    out = np.zeros_like(P, dtype=bool); taken = np.zeros_like(P, dtype=bool)
    for w in range(1, wmax + 1):
        top = shift(P, w + 1)
        c = (P > top) & (P1 <= top) & (RM[w] <= top) & ~taken
        if w >= wmin:                                       # premier repos (le plus court) dont le haut est cassé, comme _figures.py
            base = shift(LO[K], w + 2)                      # plus bas des K semaines avant le haut du mât
            ok = c & (top / base - 1 >= pole) & (Rm[w] >= top * (1 - dd))
            out |= ok
            taken |= c
    return out


if __name__ == '__main__':
    print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]} (à 6 mois ; hors 🎯 ; drapeau de référence : mât +30 % en 8 semaines, "
          "repos 2 à 6 semaines, repli ≤ 15 %)")
    F0 = flag()
    ev('référence', okb & F0 & ~Q, 26)
    print("— mât")
    for pole in (.15, .20, .40, .60):
        ev(f'mât ≥ +{pole*100:.0f} %', okb & flag(pole=pole) & ~Q, 26)
    for K in (4, 13):
        ev(f'mât en {K} semaines', okb & flag(K=K) & ~Q, 26)
    print("— repos")
    for a, b in ((1, 3), (1, 6), (2, 4), (3, 8), (2, 10)):
        ev(f'repos de {a} à {b} semaines', okb & flag(wmin=a, wmax=b) & ~Q, 26)
    print("— repli permis")
    for dd in (.08, .10, .20, .25):
        ev(f'repli ≤ {dd*100:.0f} %', okb & flag(dd=dd) & ~Q, 26)
    print("— à 12 mois")
    ev('référence', okb & F0 & ~Q, 52)
    print("\n=== relance après un 📣")
    for lo, hi in ((3, 8), (2, 6), (4, 12)):
        Bago = np.zeros_like(Q)
        for k in range(lo, hi + 1):
            Bago |= bshift(BOND & trend, k)
        hiS = np.full_like(P, np.nan)          # plus haut depuis le bond (bond compris), avant cette semaine
        for k in range(lo, hi + 1):
            m = bshift(BOND & trend, k)
            hk = shift(roll(P, k + 1, np.nanmax), 1)
            hiS = np.where(m & ~np.isfinite(hiS), hk, hiS)
        rel = Bago & (P > hiS) & ~(shift(P, 1) > hiS)
        ev(f'📣 il y a {lo} à {hi} sem., cassure du plus haut depuis', okb & rel & ~Q, 26)
        ev(f'  … avec forme de drapeau', okb & rel & F0 & ~Q, 26)
        ev(f'  … sans forme de drapeau', okb & rel & ~F0 & ~Q, 26)
    ev('drapeau, 📣 dans les 4 sem. (rappel)', okb & F0 & ago_any(BOND, 4) & ~Q, 26)
    ev('drapeau, 📣 dans les 8 sem.', okb & F0 & ago_any(BOND, 8) & ~Q, 26)
    ev('drapeau, sans 📣 depuis 8 sem.', okb & F0 & ~ago_any(BOND, 8) & ~Q, 26)
    ev('📣 bond en tendance hors 🎯 (rappel)', okb & BOND & trend & ~Q, 26)
    np.save('flag0.npy', F0)
