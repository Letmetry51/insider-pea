"""Tailles de ligne : égales ou selon les secousses du cours (inverse de la volatilité sur 52 semaines). Portefeuille 🎯, 1997-2026."""
import numpy as np, sys
src = open('stress2.py').read(); exec(src.split("rng = np.random")[0])
v52 = np.load('v52.npy').astype(float)
def pick(t): return [i for i in picker(t, perSec=2, n=12) if not (v52[i, t] >= .8)][:10]
def simw(wfun, a, b, step=4, hold=26, cost=.003):
    sleeves = []; R = []; M = []
    for t in range(a, min(b, T - 1)):
        if (t - a) % step == 0:
            s = np.array(pick(t))
            if len(s): w = wfun(s, t); sleeves.append([t, s, w / w.sum()])
        sleeves = [s for s in sleeves if t - s[0] < hold]
        if not sleeves: continue
        r = 0
        for s in sleeves:
            rr = np.nan_to_num(ret[s[1], t + 1]); r += (s[2] * rr).sum(); s[2] = s[2] * (1 + rr)
        r = r / len(sleeves); r -= cost * 2 * sum(1 for s in sleeves if s[0] == t) / (hold / step)
        R.append(r); M.append(mk[t + 1])
    R, M = np.array(R), np.array(M); eq = np.cumprod(1 + R); yrs = len(R) / 52
    cagr = eq[-1] ** (1 / yrs) - 1; dd = (eq / np.maximum.accumulate(eq) - 1).min(); vol = R.std() * np.sqrt(52)
    worst = min(np.prod(1 + R[k:k+26]) - 1 for k in range(0, len(R) - 26, 4))
    return cagr, vol, dd, worst, cagr / vol
def vol_of(s, t): v = v52[s, t]; return np.where(np.isfinite(v) & (v > .05), v, np.nanmedian(v52[:, t]))
W = [('lignes égales (actuel)', lambda s, t: np.ones(len(s))),
     ('selon les secousses (1 / volatilité)', lambda s, t: 1 / vol_of(s, t)),
     ('… plafonnée : 5 à 15 % par ligne', lambda s, t: np.clip((1 / vol_of(s, t)) / (1 / vol_of(s, t)).sum(), .05, .15)),
     ('selon les secousses au carré (1 / variance)', lambda s, t: 1 / vol_of(s, t) ** 2)]
for lab, a, b in ERAS + [('1997-2026 (tout)', t0, T)]:
    print('---', lab)
    for wl, f in W:
        c, v, dd, w6, sh = simw(f, a, b)
        print(f"  {wl:42s} {c*100:+6.1f} %/an  volatilité {v*100:4.0f} %  perte max {dd*100:+5.0f} %  pire 6 mois {w6*100:+5.0f} %  rendement/risque {sh:4.2f}")
