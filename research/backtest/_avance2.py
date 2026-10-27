"""Qualité du 📣 : quels bonds valent mieux (volume du bond, accumulation avant, 🔊, force sur 12 mois) ?"""
import numpy as np
exec(open('_avance.py').read().split("\nif __name__ == '__main__':")[0])
D = base & (R0 | R1) & trend & ~Q
ud_prev = shift(ud13, 1)
for h in (26, 52):
    print(f"\n=== 📣 démarrage, à {h // 4.33:.0f} mois")
    ev('tous', D, h)
    ev('volume du bond 2 à 3×', D & (vy < 3), h)
    ev('volume du bond 3 à 5×', D & (vy >= 3) & (vy < 5), h)
    ev('volume du bond ≥ 5×', D & (vy >= 5), h)
    ev('accumulation avant le bond (13 sem. ≥ 1,5)', D & (ud_prev >= 1.5), h)
    ev('pas d\'accumulation avant (< 1)', D & (ud_prev < 1), h)
    ev('12 mois tiers fort', D & (mp >= 2/3), h)
    ev('12 mois tiers moyen', D & (mp < 2/3), h)
    ev('premier bond depuis 6 mois', D & ~bshift(ago_any(R0 | R1, 26), 1), h)
    ev('déjà un bond dans les 6 mois avant', D & bshift(ago_any(R0 | R1, 26), 1), h)
