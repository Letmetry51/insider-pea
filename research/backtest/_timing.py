"""Moment d'entrée dans le 🎯 : repli récent, écart à la moyenne 10 semaines, série de hausses, calme récent, RSI hebdo, mois de l'année."""
import numpy as np
src = open('_moment.py').read(); exec(src.split("good = (ep")[0])
r4 = np.full_like(P, np.nan); r4[:, 4:] = P[:, 4:] / P[:, :-4] - 1
r1 = np.full_like(P, np.nan); r1[:, 1:] = P[:, 1:] / P[:, :-1] - 1
ext10 = P / m10 - 1
up = (r1 > 0).astype(float); streak = np.zeros_like(P)
for t in range(1, T): streak[:, t] = np.where(r1[:, t] > 0, streak[:, t-1] + 1, 0)
def rstd(k):
    o = np.full_like(P, np.nan)
    for t in range(k, T): o[:, t] = np.nanstd(r1[:, t-k+1:t+1], 1)
    return o
calm = rstd(4) / rstd(26)
# RSI hebdomadaire 14
g = np.where(r1 > 0, r1, 0); l = np.where(r1 < 0, -r1, 0); ag = np.full_like(P, np.nan); al = np.full_like(P, np.nan)
for t in range(14, T): ag[:, t] = np.nanmean(g[:, t-13:t+1], 1); al[:, t] = np.nanmean(l[:, t-13:t+1], 1)
rsi = 100 - 100 / (1 + ag / np.where(al > 0, al, np.nan))
mon = np.array([int(d[5:7]) for d in dates])
def row(lab, M):
    r = st(M)
    if r is None or M.sum() < 300: print(f"  {lab:40s} trop peu"); return
    per = '  '.join(f"{l} {st(M, x, y)[0]:+5.1f}" for l, x, y in E3)
    print(f"  {lab:40s} {r[0]:+6.1f} pts  chutes {r[1]:4.1f} %  part {M.sum()/Q.sum()*100:4.0f} % | {per}")
print('référence 🎯 (sans ⚡)'); row('tous', Q)
print('\n1. variation du dernier mois'); [row(l, Q & (r4 >= a) & (r4 < b)) for l, a, b in [('repli de plus de 5 %', -9, -.05), ('−5 à 0 %', -.05, 0), ('0 à +10 %', 0, .1), ('+10 à +20 %', .1, .2), ('plus de +20 %', .2, 9)]]
print('\n2. écart à la moyenne 10 semaines'); [row(l, Q & (ext10 >= a) & (ext10 < b)) for l, a, b in [('sous la moyenne', -9, 0), ('0 à +5 %', 0, .05), ('+5 à +10 %', .05, .1), ('+10 à +20 %', .1, .2), ('plus de +20 %', .2, 9)]]
print('\n3. semaines de hausse d\'affilée'); [row(l, Q & (streak >= a) & (streak < b)) for l, a, b in [('0 (dernière semaine en baisse)', 0, 1), ('1 à 2', 1, 3), ('3 à 4', 3, 5), ('5 ou plus', 5, 99)]]
print('\n4. calme récent (volatilité 4 sem. / 26 sem.)'); [row(l, Q & (calm >= a) & (calm < b)) for l, a, b in [('très calme (< 0,6)', 0, .6), ('calme (0,6 à 0,9)', .6, .9), ('normal (0,9 à 1,3)', .9, 1.3), ('agité (> 1,3)', 1.3, 99)]]
print('\n5. RSI hebdomadaire 14'); [row(l, Q & (rsi >= a) & (rsi < b)) for l, a, b in [('< 60', 0, 60), ('60 à 70', 60, 70), ('70 à 80', 70, 80), ('80 ou plus', 80, 101)]]
print('\n6. mois d\'entrée'); [row(m_, Q & (mon == k)) for k, m_ in enumerate(['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'], 1)]
