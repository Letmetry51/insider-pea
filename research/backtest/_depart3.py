"""Variantes proches des creux en « V » des graphiques (creux, rebond franc, moyennes courtes qui se retournent) et de Weinstein (étape 2
avec force relative et volumes, comme dans son livre)."""
import numpy as np
exec(open('_depart.py').read().split('print(f"Données')[0])
m4 = sma(P, 4); lo13 = roll(P, 13, np.nanmin); hot = vx >= 1.5
V1 = valid & deep26 & (P >= lo13 * 1.25) & (m4 > m10) & (m10 > shift(m10, 2))
fresh2 = st2 & ~bshift(ago_any(st2, 26), 1) & bshift(ago_any(st4, 52), 1)
cases = [('🎯 (référence)', Q),
         ('creux −30 %, rebond ≥ +25 % du plus bas, moyennes 4 > 10 montante', V1),
         ('  … et cours au-dessus de la moyenne 40 sem.', V1 & (P > m40)),
         ('  … et volumes en hausse (🔊 ×1,5)', V1 & hot),
         ('  … au-dessus de la moyenne 40 et 🔊', V1 & (P > m40) & hot),
         ('Weinstein étape 2 neuve + force relative > 0 + volumes ×1,5', valid & ago_any(fresh2 & (mans > 0) & hot, 4)),
         ('Weinstein étape 2 neuve + force relative > 0', valid & ago_any(fresh2 & (mans > 0), 4))]
for k, M in cases:
    line(k, M)
print('\n  À 12 mois :')
for k, M in cases:
    e, cr, bg, n = st(M, F=fut52)
    print(f"  {k:58s} {e:+5.1f} pts à 12 mois · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n} cas")
