"""Portefeuille 🎯 : (a) ne rien acheter pendant l'alerte « krach du momentum » (marché −20 % sur un an) ; (b) à 6 mois, garder les lignes encore dans le 🎯."""
import numpy as np, sys
src = open('_beta.py').read(); exec(src.split("for lab, a, b in ERAS")[0])
cm = np.cumprod(1 + np.nan_to_num(mk)); m52 = np.full(T, np.nan); m52[52:] = cm[52:] / cm[:-52] - 1
def sim(a, b, mode='base', step=4, hold=26, cost=.003):
    sleeves = []; R = []; trades = 0
    for t in range(a, min(b, T - 1)):
        if (t - a) % step == 0:
            crash = np.isfinite(m52[t]) and m52[t] <= -.2
            s = [] if (mode == 'cash' and crash) else pick_with(t, 'actuel')
            sleeves.append([t, np.array(s, dtype=int), np.ones(len(s)) / max(len(s), 1), len(s)])
            trades += len(s)
        keep = []
        for sl in sleeves:
            if t - sl[0] < hold: keep.append(sl); continue
            if mode == 'garder' and len(sl[1]):
                now = set(pick_with(t, 'actuel')[:15]); stay = np.array([i in now for i in sl[1]])
                if stay.any():  # les lignes encore dans le 🎯 repartent pour 6 mois, sans frais
                    keep.append([t, sl[1][stay], sl[2][stay], 0]); trades -= stay.sum()
        sleeves = keep
        if not sleeves: R.append(0.0); continue
        r = 0; n = 0
        for sl in sleeves:
            if not len(sl[1]): n += 1; continue  # tranche en liquidités
            rr = np.nan_to_num(ret[sl[1], t + 1]); tot = sl[2].sum(); r += (sl[2] * rr).sum() / tot if tot > 0 else 0; sl[2] = sl[2] * (1 + rr); n += 1
        r = r / n - cost * 2 * sum(sl[3] for sl in sleeves if sl[0] == t) / 10 / (hold / step)
        R.append(r)
    R = np.array(R); eq = np.cumprod(1 + R); yrs = len(R) / 52
    return eq[-1] ** (1 / yrs) - 1, R.std() * np.sqrt(52), (eq / np.maximum.accumulate(eq) - 1).min(), trades
for lab, a, b in ERAS + [('1997-2026', t0, T)]:
    print('---', lab)
    for m, nm in [('base', 'actuel (tout vendre à 6 mois)'), ('cash', 'pas d\'achat pendant l\'alerte krach'), ('garder', 'à 6 mois, garder celles encore dans le 🎯')]:
        c, v, dd, tr = sim(a, b, m)
        print(f"  {nm:42s} {c*100:+6.1f} %/an  volatilité {v*100:3.0f} %  perte max {dd*100:+5.0f} %  achats {tr}")
print('semaines en alerte krach :', int(np.nansum(m52[t0:] <= -.2)), 'sur', T - t0)
