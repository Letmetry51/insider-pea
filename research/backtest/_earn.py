"""Calendrier des résultats (2020-2026) : acheter juste avant, juste après ou loin des résultats ? 6 mois et 4 semaines."""
import numpy as np, json
src = open('_pead.py').read(); exec(src.split("G = covered")[0])
ED = {}
for i, c in enumerate(cols):
    ds = sorted(d for d, v in (est.get(c) or {}).get('surprises') or [])
    if ds: ED[i] = np.array([int(np.searchsorted(D, d)) for d in ds])
nxt = np.full_like(P, np.nan); lst = np.full_like(P, np.nan)
for i, idx in ED.items():
    for t in range(T):
        k = np.searchsorted(idx, t, side='right')  # annonces strictement après t
        if k < len(idx): nxt[i, t] = idx[k] - t
        if k > 0: lst[i, t] = t - idx[k - 1]
f4 = np.full_like(P, np.nan); f4[:, :-4] = P[:, 4:] / P[:, :-4] - 1
def stx(M, F, a, b, cut):
    ex = []; n = 0; cr = 0
    for t in range(a, min(b, T - 26)):
        ok = valid[:, t] & np.isfinite(F[:, t]); m = M[:, t] & ok
        if ok.sum() < 30 or not m.any(): continue
        f = np.clip(F[:, t], *np.nanpercentile(F[ok, t], [2, 98]))
        ex.append(np.nanmean(f[m]) - np.nanmean(f[ok])); n += m.sum(); cr += (F[m, t] <= cut).sum()
    return np.mean(ex) * 100, cr / max(n, 1) * 100, n
def row3(lab, M):
    a = stx(M, fut, t20, T, -.25); b = stx(M, f4, t20, T, -.15)
    per = '  '.join(f"{l} {stx(M, fut, x, y, -.25)[0]:+5.1f}" for l, x, y in E3)
    print(f"  {lab:40s} 6 m {a[0]:+5.1f} (chutes {a[1]:4.1f} %) | 4 sem. {b[0]:+5.1f} (≤ −15 % : {b[1]:4.1f} %) n={a[2]:5d} | {per}")
U = Qs & covered & np.isfinite(nxt) & np.isfinite(lst)
for nm, G in [('🎯 strict au-dessus de la moyenne 10 sem.', U), ('tout l\'univers suivi', valid & covered & np.isfinite(nxt) & np.isfinite(lst))]:
    print('\n==', nm); row3('référence', G)
    row3('résultats dans 1 à 2 semaines', G & (nxt <= 2)); row3('résultats dans 3 à 6 semaines', G & (nxt >= 3) & (nxt <= 6)); row3('résultats dans 7 semaines ou plus', G & (nxt >= 7))
    row3('résultats publiés il y a 0 à 3 semaines', G & (lst <= 3)); row3('publiés il y a 4 à 8 semaines', G & (lst >= 4) & (lst <= 8))
    row3('juste avant, avec 📣 récent', G & (nxt <= 2) & rec)
