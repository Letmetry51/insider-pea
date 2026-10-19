"""Suite moment d'achat : 📣 face aux paliers, détail du bond (récence, taille, tenue), momentum du secteur, ampleur du marché, distance au plus haut."""
import numpy as np
src = open('_timing2.py').read(); exec(src.split("# 1. volumes en hausse")[0])
VO2 = np.where(VO > 0, VO, np.nan)
v52b = np.full_like(P, np.nan)
for t in range(52, T): v52b[:, t] = np.nanmean(VO2[:, t-52:t], 1)
jump = (r1 >= .08) & (VO2 >= 3 * v52b)
ago = np.full_like(P, np.nan); jr = np.full_like(P, np.nan); jp = np.full_like(P, np.nan)
for t in range(8, T):
    for k in range(7, -1, -1):
        m = jump[:, t-k] & np.isnan(ago[:, t])
        if k < 7: pass
    # plus récent d'abord
    for k in range(0, 8):
        m = jump[:, t-k] & np.isnan(ago[:, t]); ago[m, t] = k; jr[m, t] = r1[m, t-k]; jp[m, t] = P[m, t-k]
rec = np.isfinite(ago); hot = vx >= 1.5
above10 = ~(ext10 < 0)
Qs = Q & above10   # 🎯 palier 0, au-dessus de la moyenne 10 semaines
base = valid & (mp >= 2/3) & trend
T1 = base & (((s26 >= .14) & (s26 < .41) & (mom >= .6) & (mom <= 2)) | ((s26 >= .41) & (mom >= .3) & (mom < .6))) & ~(v52 >= .8) & above10
Q = Qs
print('référence'); row('🎯 strict, au-dessus de la moyenne 10 sem.', Qs)
print('\n1. 📣 doit-il passer avant les règles strictes ?')
row('strict sans 📣', Qs & ~rec); row('strict avec 📣', Qs & rec); row('assoupli (pente moyenne ou +30-60 %) sans 📣', T1 & ~rec); row('assoupli avec 📣', T1 & rec)
row('assoupli avec 📣 et 🔊', T1 & rec & hot); row('strict avec 🔊 sans 📣', Qs & hot & ~rec)
print('\n2. détail du bond (🎯 strict avec 📣)')
for l, m in [('cette semaine ou la précédente', ago <= 1), ('il y a 2 à 4 semaines', (ago >= 2) & (ago <= 4)), ('il y a 5 à 7 semaines', ago >= 5)]: row(l, Qs & rec & m)
for l, m in [('bond +8 à +15 %', jr < .15), ('bond +15 à +25 %', (jr >= .15) & (jr < .25)), ('bond de plus de +25 %', jr >= .25)]: row(l, Qs & rec & m)
hold = P / jp - 1
for l, m in [('cours sous la clôture du bond', hold < 0), ('0 à +10 % au-dessus', (hold >= 0) & (hold < .1)), ('plus de +10 % au-dessus', hold >= .1)]: row(l, Qs & rec & m)
print('\n3. momentum du secteur (hausse moyenne des 26 dernières semaines, rang parmi les secteurs)')
secs = np.array([str(s) for s in z['sec']]); r26 = np.full_like(P, np.nan); r26[:, 26:] = P[:, 26:] / P[:, :-26] - 1
srk = np.full_like(P, np.nan); U = sorted(set(secs))
for t in range(26, T):
    ok = valid[:, t] & np.isfinite(r26[:, t]); sm = {}
    for s in U:
        m = ok & (secs == s)
        if m.sum() >= 5: sm[s] = np.nanmedian(r26[m, t])
    if len(sm) < 5: continue
    order = sorted(sm, key=sm.get); rk = {s: i / (len(order) - 1) for i, s in enumerate(order)}
    for s in rk: srk[secs == s, t] = rk[s]
for l, a, b in [('secteur dans le tiers faible', 0, 1/3), ('secteur moyen', 1/3, 2/3), ('secteur dans le tiers fort', 2/3, 1.01)]: row(l, Qs & (srk >= a) & (srk < b))
print('\n4. ampleur du marché (part des sociétés au-dessus de leur moyenne 40 semaines)')
br = np.array([np.nanmean((P[:, t] > m40[:, t])[valid[:, t]]) if valid[:, t].sum() > 30 else np.nan for t in range(T)])
BR = np.tile(br, (N, 1))
for l, a, b in [('moins de 40 %', 0, .4), ('40 à 60 %', .4, .6), ('60 à 75 %', .6, .75), ('plus de 75 %', .75, 1.01)]: row(l, Qs & (BR >= a) & (BR < b))
print('\n5. distance au plus haut sur 52 semaines')
for l, a, b in [('au plus haut (≤ 2 %)', .98, 9), ('2 à 5 % sous', .95, .98), ('5 à 10 % sous', .9, .95), ('plus de 10 % sous', 0, .9)]: row(l, Qs & (ratio >= a) & (ratio < b))
