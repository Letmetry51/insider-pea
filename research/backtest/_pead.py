"""Dérive après résultats (Bernard-Thomas 1989) : dernière surprise de bénéfice (Yahoo, 2020-2026) dans les 13 semaines, dans le 🎯 et dans tout l'univers."""
import numpy as np, json
src = open('_timing4.py').read(); exec(src.split("print('référence')")[0])
est = json.load(open('../../data/sectors/estimates.json'))
cols = [str(c) for c in z['cols']]; D = np.array([str(d) for d in dates])
SU = np.full_like(P, np.nan)
for i, c in enumerate(cols):
    for d, v in (est.get(c) or {}).get('surprises') or []:
        t = int(np.searchsorted(D, d))  # première semaine dont la clôture suit l'annonce
        if t < T: SU[i, t:min(T, t + 13)] = v
covered = np.zeros_like(valid)
for i, c in enumerate(cols):
    s = (est.get(c) or {}).get('surprises') or []
    if s: covered[i, int(np.searchsorted(D, s[0][0])):] = True
t20 = int(np.searchsorted(D, '2020-07-01')); t23 = int(np.searchsorted(D, '2023-01-01'))
E3 = [('20-22', t20, t23), ('23-26', t23, T)]
def row2(lab, M, base=None):
    r = st(M, t20, T)
    per = '  '.join(f"{l} {st(M, x, y)[0]:+5.1f}" for l, x, y in E3)
    print(f"  {lab:44s} {r[0]:+6.1f} pts  chutes {r[1]:4.1f} %  n={int(M[:, t20:].sum()):6d} | {per}")
G = covered & np.isfinite(SU)
for nm, U in [('tout l\'univers suivi', valid & covered), ('🎯 strict au-dessus de la moyenne 10 sem.', Qs & covered)]:
    print('\n==', nm); row2('référence', U)
    row2('surprise ≥ +10 %', U & (SU >= 10)); row2('+2 à +10 %', U & (SU >= 2) & (SU < 10)); row2('−2 à +2 %', U & (SU > -2) & (SU < 2))
    row2('−10 à −2 %', U & (SU > -10) & (SU <= -2)); row2('surprise ≤ −10 %', U & (SU <= -10)); row2('pas de résultats depuis 13 sem.', U & ~np.isfinite(SU))
print('\n== croisement avec 📣 (🎯)')
row2('📣 et surprise ≥ +2 %', Qs & covered & rec & (SU >= 2)); row2('📣 sans surprise positive', Qs & covered & rec & ~(SU >= 2)); row2('surprise ≥ +2 % sans 📣', Qs & covered & ~rec & (SU >= 2))
row2('surprise négative ≤ −2 % (🎯)', Qs & covered & (SU <= -2))
