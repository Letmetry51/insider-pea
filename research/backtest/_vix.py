"""Volatilité du marché (substitut du VIX/VSTOXX) et volatilité du momentum (Barroso–Santa-Clara) : ajoutent-elles quelque chose ?"""
import numpy as np
z = np.load('long.npz', allow_pickle=True); P = z['P'].astype(float); dates = z['dates']; N, T = P.shape
yr = np.array([int(d[:4]) for d in dates])
def sma(A, k):
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(np.isfinite(A), 1)
    o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
    cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan; return o
m10, m40 = sma(P, 10), sma(P, 40); trend = (m10 > m40) & (P > m40)
mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
L = np.log(P); x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)
for t in range(25, T):
    y = L[:, t-25:t+1]; ym = y.mean(1, keepdims=True); s26[:, t] = np.exp(((y - ym) * x).sum(1) / (x * x).sum() * 26) - 1
H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
valid = np.isfinite(mom) & np.isfinite(fut) & np.isfinite(s26)
mp = np.full_like(P, np.nan)
for t in range(T):
    ok = valid[:, t]
    if ok.sum() > 30: mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
ret = np.full_like(P, np.nan); ret[:, 1:] = P[:, 1:] / P[:, :-1] - 1
ret = np.clip(ret, -.5, 1)
alive = np.isfinite(ret).sum(0)
mk = np.array([np.nanmean(ret[:, t]) if alive[t] > 30 else np.nan for t in range(T)])
# volatilité réalisée du marché sur 13 semaines, annualisée (le VIX suit de près cette mesure)
vol = np.array([np.nanstd(mk[t-12:t+1]) * np.sqrt(52) if t >= 12 and np.isfinite(mk[t-12:t+1]).sum() >= 10 else np.nan for t in range(T)])
# momentum : gagnants (tiers haut) moins moyenne, rendement hebdo ; volatilité sur 26 semaines
wml = np.full(T, np.nan)
for t in range(1, T):
    w = (mp[:, t-1] >= 2/3) & np.isfinite(ret[:, t])
    if w.sum() > 10: wml[t] = np.nanmean(ret[w, t]) - mk[t]
mvol = np.array([np.nanstd(wml[t-25:t+1]) * np.sqrt(52) if t >= 25 and np.isfinite(wml[t-25:t+1]).sum() >= 20 else np.nan for t in range(T)])
m52 = np.full(T, np.nan); cm = np.cumprod(1 + np.nan_to_num(mk)); m52[52:] = cm[52:] / cm[:-52] - 1
def expq(s):  # rang de la valeur parmi tout son passé (pas de regard vers le futur)
    q = np.full(T, np.nan)
    for t in range(T):
        h = s[:t+1]; h = h[np.isfinite(h)]
        if len(h) >= 156 and np.isfinite(s[t]): q[t] = (h < s[t]).mean()
    return q
qv, qm = expq(vol), expq(mvol)
t0 = int(np.argmax(np.array([valid[:, t].sum() for t in range(T)]) > 30))
def st(M, cond, a=0, b=T):
    ex = []; n = 0; cr = 0
    for t in range(max(a, t0), min(b, T - H)):
        ok = valid[:, t]; m = M[:, t] & ok
        if not cond[t] or ok.sum() < 30 or not m.any(): continue
        f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
        ex.append(np.nanmean(f[m]) - np.nanmean(f[ok])); n += m.sum(); cr += (fut[m, t] <= -.25).sum()
    if not ex: return None
    ex = np.array(ex); return ex.mean() * 100, len(ex), cr / max(n, 1) * 100
G = {'classement + pente forte': valid & (mp >= 2/3) & trend & (s26 >= .41),
     '🎯 filtres (sans comptes)': valid & (mp >= 2/3) & trend & (s26 >= .41) & (mom >= .6) & (mom <= 2)}
E2 = [('1997-2008', 0, int(np.searchsorted(yr, 2009))), ('2009-2017', int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))), ('2018-2026', int(np.searchsorted(yr, 2018)), T)]
fin = np.isfinite
print('début', dates[t0], '| vol marché médiane', round(np.nanmedian(vol)*100), '% | max', round(np.nanmax(vol)*100), '%', dates[int(np.nanargmax(vol))])
for name, q in [('VOL MARCHÉ (≈ VIX)', qv), ('VOL DU MOMENTUM (Barroso)', qm)]:
    print('\n===', name, ': excès à 6 mois (pts) / semaines / part des chutes ≤ −25 %')
    for g, M in G.items():
        print(' ', g)
        for lab, c in [('calme (tiers bas)', fin(q) & (q < 1/3)), ('normal', fin(q) & (q >= 1/3) & (q < 2/3)), ('agité (tiers haut)', fin(q) & (q >= 2/3)), ('extrême (10 % haut)', fin(q) & (q >= .9))]:
            r = st(M, c); per = [st(M, c, a, b) for _, a, b in E2]
            print(f"    {lab:22s} {r[0]:+6.1f}  n={r[1]:4d}  chutes {r[2]:4.1f} %   | par période : " + '  '.join('—' if p is None else f"{p[0]:+5.1f}" for p in per))
print('\n=== croisement avec la baisse du marché sur 52 semaines (alerte actuelle à −20 %)')
for g, M in G.items():
    for lab, c in [('marché ≥ −20 %, vol normale/calme', fin(qv) & (qv < 2/3) & (m52 > -.2)), ('marché ≥ −20 %, vol agitée', fin(qv) & (qv >= 2/3) & (m52 > -.2)),
                   ('marché < −20 % (alerte actuelle)', fin(m52) & (m52 <= -.2)), ('marché < −20 % ET vol agitée', fin(qv) & (qv >= 2/3) & (m52 <= -.2))]:
        r = st(M, c); print(f"  {g:28s} {lab:36s} {r[0]:+6.1f}  n={r[1]:4d}  chutes {r[2]:4.1f} %" if r else f"  {g} {lab} —")
