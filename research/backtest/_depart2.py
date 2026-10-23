"""Suite de _depart.py : accélération précoce (repérer plus tôt les futures 🎯), recul depuis le plus haut, plus haut plus bas,
moyenne 10 semaines qui se retourne, ampleur de la hausse déjà faite, et force du signal (nombre de repères favorables)."""
import numpy as np
exec(open('_depart.py').read().split('print(f"Données')[0])
r13 = P / shift(P, 13) - 1
r26 = P / shift(P, 26) - 1


def xpct(A):
    o = np.full_like(A, np.nan)
    for t in range(T):
        ok = valid[:, t] & fin(A[:, t])
        if ok.sum() > 30:
            o[ok, t] = A[ok, t].argsort().argsort() / (ok.sum() - 1)
    return o


p13, p26 = xpct(r13), xpct(r26)
hot = vx >= 1.5
print("=== 1. Accélération précoce : forte hausse récente avant que la hausse sur 12 mois ne qualifie pour le 🎯")
line('🎯 (référence)', Q)
acc = valid & (p13 >= .9) & (mp < 2/3) & (m10 > m40)
line('3 mois dans les 10 % meilleurs, 12 mois pas encore (tendance)', acc)
line('  … après un creux de −30 % (creux en « V »)', acc & deep26)
line('  … avec volumes en hausse (🔊 ×1,5)', acc & hot)
line('  … creux et volumes en hausse', acc & deep26 & hot)
line('6 mois dans les 10 % meilleurs, 12 mois pas encore (tendance)', valid & (p26 >= .9) & (mp < 2/3) & (m10 > m40))
line('  … et pente forte (≥ +41 %/an)', valid & (p26 >= .9) & (mp < 2/3) & (m10 > m40) & (s26 >= .41))
print("\n  À 12 mois :")
for k, M in [('🎯 (référence)', Q), ('3 mois dans les 10 % meilleurs, 12 mois pas encore', acc), ('  … creux et volumes en hausse', acc & deep26 & hot),
             ('6 mois 10 % meilleurs + pente forte, 12 mois pas encore', valid & (p26 >= .9) & (mp < 2/3) & (m10 > m40) & (s26 >= .41))]:
    e, cr, bg, n = st(M, F=fut52)
    print(f"  {k:58s} {e:+5.1f} pts à 12 mois · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n} cas")

print("\n=== 2. Essoufflement, autres repères (parmi les sociétés 🎯)")
d26 = P / roll(P, 26, np.nanmax) - 1
for lab, a, b in [('au plus haut de 6 mois (≤ 2 %)', -.02, 1), ('2 à 5 % sous', -.05, -.02), ('5 à 10 % sous', -.10, -.05), ('plus de 10 % sous', -1, -.10)]:
    line(lab, Q & (d26 > a) & (d26 <= b) if b < 1 else Q & (d26 > a))
h13, h26p = roll(P, 13, np.nanmax), shift(roll(P, 13, np.nanmax), 13)
compare('plus haut des 3 derniers mois inférieur de 3 % au précédent / sinon', Q & (h13 < h26p * .97), Q & ~(h13 < h26p * .97))
compare('moyenne 10 sem. en baisse sur 4 sem. / en hausse', Q & (m10 < shift(m10, 4)), Q & (m10 >= shift(m10, 4)))
from_lo = P / lo52 - 1
for lab, a, b in [('hausse depuis le plus bas de l\'année < +100 %', -1, 1), ('+100 à +150 %', 1, 1.5), ('+150 à +250 %', 1.5, 2.5), ('plus de +250 %', 2.5, 99)]:
    line(lab, Q & (from_lo > a) & (from_lo <= b))
lo_age = np.full_like(P, np.nan)
for t in range(52, T):
    lo_age[:, t] = 51 - np.nanargmin(np.where(fin(P[:, t-51:t+1]), P[:, t-51:t+1], np.inf), 1)
for lab, a, b in [('plus bas de l\'année il y a moins de 20 sem.', -1, 20), ('20 à 35 sem.', 20, 35), ('plus de 35 sem.', 35, 99)]:
    line(lab, Q & (lo_age >= a) & (lo_age < b))

print("\n=== 3. Même repères d'essoufflement, à 3 mois (13 semaines)")
F13 = np.full_like(P, np.nan); F13[:, :-13] = P[:, 13:] / P[:, :-13] - 1


def st13(M, a=t0, b=T):
    ex, n, cr = [], 0, 0
    for t in range(a, min(b, T - 13)):
        ok = valid[:, t] & fin(F13[:, t]); m = M[:, t] & ok
        if ok.sum() < 30 or not m.any():
            continue
        f = np.clip(F13[:, t], *np.nanpercentile(F13[ok, t], [2, 98]))
        ex.append(np.nanmean(f[m]) - np.nanmean(f[ok])); n += m.sum(); cr += (F13[m, t] <= -.2).sum()
    return np.mean(ex) * 100, cr / max(n, 1) * 100, n


for lab, M1, M0 in [('RSI hebdomadaire ≥ 80 / < 70', Q & (rsi >= 80), Q & (rsi < 70)),
                    ('séquence d\'épuisement ≥ 9 / < 9', Q & (td >= 9), Q & (td < 9)),
                    ('MACD-V sous sa ligne de signal / au-dessus', Q & (macdv < macdv_sig), Q & (macdv >= macdv_sig)),
                    ('divergence baissière RSI (≤ 8 sem.) / sans', Q & ago_any(bear_div, 8), Q & ~ago_any(bear_div, 8)),
                    ('plus de +60 % au-dessus de la moyenne 40 sem. / moins de +30 %', Q & (ext40 > .6), Q & (ext40 < .3)),
                    ('moyenne 10 sem. en baisse / en hausse', Q & (m10 < shift(m10, 4)), Q & (m10 >= shift(m10, 4)))]:
    a, b = st13(M1), st13(M0)
    per = '  '.join(f"{l} {st13(M1, x, y)[0] - st13(M0, x, y)[0]:+5.1f}" for l, x, y in E3)
    print(f"  {lab:58s} {a[0]:+5.1f} contre {b[0]:+5.1f} (écart {a[0]-b[0]:+5.1f}) · chutes −20 % {a[1]:4.1f} contre {b[1]:4.1f} % | {per}")

print("\n=== 4. Force du signal : nombre de repères favorables parmi les sociétés 🎯")
marks = (hot.astype(int) + (s26 >= .8).astype(int) + (mp >= .9).astype(int) + (d26 > -.02).astype(int) + (mans > shift(mans, 8)).astype(int))
print("  repères : volumes ×1,5 · pente ≥ +80 %/an · 12 mois dans les 10 % meilleurs · au plus haut de 6 mois · force relative en hausse")
for k in range(6):
    line(f'{k} repère(s)', Q & (marks == k))
