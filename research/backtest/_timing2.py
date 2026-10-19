"""Moment d'achat, nouvelles pistes (🎯 au-dessus de la moyenne 10 semaines) : volumes des semaines de hausse contre baisse,
saut récent sur gros volume (indice de résultats surprises, « dérive post-annonce »), ancienneté dans le 🎯."""
import numpy as np
src = open('_timing.py').read(); exec(src.split("print('référence")[0])
Q = Q & ~(ext10 < 0)
VO2 = np.where(VO > 0, VO, np.nan)
# 1. volumes en hausse contre volumes en baisse (13 semaines) : accumulation
udr = np.full_like(P, np.nan)
for t in range(13, T):
    r = r1[:, t-12:t+1]; v = VO2[:, t-12:t+1]
    up_v = np.nansum(np.where(r > 0, v, 0), 1); dn_v = np.nansum(np.where(r < 0, v, 0), 1)
    udr[:, t] = np.where(dn_v > 0, up_v / dn_v, np.nan)
# 2. saut récent sur gros volume : une semaine à +8 % ou plus avec un volume ≥ 3 fois la moyenne, dans les 8 dernières semaines
v52 = np.full_like(P, np.nan)
for t in range(52, T): v52[:, t] = np.nanmean(VO2[:, t-52:t], 1)
jump = (r1 >= .08) & (VO2 >= 3 * v52); jumpdn = (r1 <= -.08) & (VO2 >= 3 * v52)
recent = np.zeros_like(jump); recentdn = np.zeros_like(jump)
for t in range(8, T): recent[:, t] = np.any(jump[:, t-7:t+1], 1); recentdn[:, t] = np.any(jumpdn[:, t-7:t+1], 1)
# 3. ancienneté dans le 🎯 : nombre de semaines d'affilée
age = np.zeros_like(P)
for t in range(1, T): age[:, t] = np.where(Q[:, t], age[:, t-1] + 1, 0)
print('référence'); row('🎯 au-dessus de la moyenne 10 sem.', Q)
c = np.nanpercentile(udr[Q], [33.3, 66.7])
print('\n1. volumes des semaines de hausse / de baisse (13 sem.)'); [row(l, Q & m) for l, m in [('faible (< %.2f)' % c[0], udr < c[0]), ('moyen', (udr >= c[0]) & (udr < c[1])), ('fort (> %.2f) : accumulation' % c[1], udr >= c[1])]]
print('\n2. saut sur gros volume (≥ +8 %% et ×3) dans les 8 dernières semaines'); row('oui (dérive après une bonne nouvelle)', Q & recent); row('non', Q & ~recent); row('chute sur gros volume récente', Q & recentdn)
print('\n3. ancienneté dans le 🎯'); [row(l, Q & m) for l, m in [('1re semaine', age == 1), ('2 à 4 semaines', (age >= 2) & (age <= 4)), ('5 à 12 semaines', (age >= 5) & (age <= 12)), ('plus de 12 semaines', age > 12)]]
