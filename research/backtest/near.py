import numpy as np, sys
d = np.load(sys.argv[1]); P = d['P'].astype(float); VO = d['V'].astype(float); dates = list(d['dates']); sec = d['sec']
P = np.where(P > 0, P, np.nan); VO = np.where(VO > 0, VO, np.nan); N, T = P.shape; L = np.log(P); yr = np.array([int(x[:4]) for x in dates])
def sma(A, k):
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(np.isfinite(A), 1)
    o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
    cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan; return o
m10, m40 = sma(P, 10), sma(P, 40); trend = (m10 > m40) & (P > m40)
mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
hi = np.full_like(P, np.nan)
for t in range(51, T): hi[:, t] = np.nanmax(P[:, t-51:t+1], 1)
ratio = P / hi
x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)
for t in range(25, T):
    y = L[:, t-25:t+1]; ym = y.mean(1, keepdims=True); s26[:, t] = np.exp(((y-ym)*x).sum(1)/(x*x).sum()*26)-1
vx = sma(VO, 10) / sma(VO, 52)
H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
valid = np.isfinite(mom) & np.isfinite(s26) & np.isfinite(ratio)
mp = np.full_like(P, np.nan)
for t in range(T):
    ok = valid[:, t]
    if ok.sum() > 30: mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
nval = valid.sum(0); t0 = int(np.argmax(nval > 60))
score = 50 * mp + 10 * np.clip((ratio - .6) / .4, 0, 1) + np.where(trend, 15, np.where(P > m40, 5, 0))
RANK = valid & (mp >= 2/3) & trend
e1, e2 = int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))
ERAS = [('1997-2008 (hors échantillon)', t0, e1), ('2009-2017 (hors échantillon)', e1, e2), ('2018-2026 (réglage)', e2, T)]
fv = valid & np.isfinite(fut)
def st(M, a, b):
    ex = []; win = n = cr = 0
    for t in range(a, min(b, T-H)):
        ok = fv[:, t]; m = M[:, t] & ok
        if ok.sum() < 30 or not m.any(): continue
        f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98])); ex.append(np.nanmean(f[m]) - np.nanmean(f[ok])); win += (fut[m, t] > 0).sum(); cr += (fut[m, t] <= -.25).sum(); n += m.sum()
    if len(ex) < 5: return '   n.d.'
    e = np.array(ex); return f"{e.mean()*100:+5.1f} pt (t {e.mean()/e.std()*np.sqrt(len(e))/np.sqrt(H):4.1f}) gagne {win/n*100:3.0f} % chute≤−25 {cr/n*100:4.1f} %"
# 2. portefeuille
ret = np.full_like(P, np.nan); ret[:, 1:] = P[:, 1:] / P[:, :-1] - 1; ret = np.clip(ret, -.6, 1.5)
mk = np.array([np.nanmean(ret[valid[:, t-1], t]) if t and nval[t-1] > 30 else 0 for t in range(T)]); mk = np.nan_to_num(mk)
def picker(t, n=10, momMin=.6, momMax=2, slope=.41, vol=1.5, relax=True, perSec=2, near=False):
    ok = valid[:, t] & np.isfinite(P[:, t])
    if near: ok = ok & (ratio[:, t] >= .9) & (ratio[:, t] < .98)
    tiers = [ok & (mp[:, t] >= 2/3) & trend[:, t] & (s26[:, t] >= slope) & (mom[:, t] >= momMin) & (mom[:, t] <= momMax)]
    if relax: tiers.append(ok & (mp[:, t] >= 1/3) & trend[:, t] & (s26[:, t] >= .14) & (mom[:, t] >= .3) & (mom[:, t] <= momMax))
    out, seen = [], {}
    for M in tiers:
        idx = np.where(M & ~np.isin(np.arange(N), out))[0]
        hot = (vx[idx, t] >= vol) if vol else np.zeros(len(idx), bool)
        order = idx[np.lexsort((-score[idx, t], ~hot))]
        for i in order:
            if len(out) >= n: break
            if seen.get(sec[i], 0) >= perSec: continue
            seen[sec[i]] = seen.get(sec[i], 0) + 1; out.append(i)
    return out
def rand_pick(t, n=10, rng=None):
    ok = np.where(valid[:, t] & (mp[:, t] >= 1/3))[0]; return list(rng.choice(ok, min(n, len(ok)), replace=False)) if len(ok) else []
def topn(t, n=10):
    ok = np.where(valid[:, t] & (mp[:, t] >= 1/3))[0]; return list(ok[np.argsort(-score[ok, t])][:n])
def simulate(pick, a, b, step=4, hold=26, cost=.003):
    """Tous les mois, une tranche de 10 lignes égales gardée 6 mois (6 tranches en parallèle). Rendement hebdomadaire du portefeuille."""
    sleeves = []; R = []; M = []
    for t in range(a, min(b, T - 1)):
        if (t - a) % step == 0:
            s = pick(t)
            if len(s): sleeves.append([t, np.array(s), np.ones(len(s)) / len(s)])
        sleeves = [s for s in sleeves if t - s[0] < hold]
        if not sleeves: continue
        r = 0; w = 0
        for s in sleeves:
            rr = np.nan_to_num(ret[s[1], t + 1]); r += (s[2] * rr).sum(); s[2] = s[2] * (1 + rr); w += 1
        r = r / w
        n_new = sum(1 for s in sleeves if s[0] == t); r -= cost * 2 * n_new / (hold / step)  # achat + vente de la tranche
        R.append(r); M.append(mk[t + 1])
    R, M = np.array(R), np.array(M)
    def stats(x):
        eq = np.cumprod(1 + x); yrs = len(x) / 52; cagr = eq[-1] ** (1 / yrs) - 1; dd = (eq / np.maximum.accumulate(eq) - 1).min(); vol = x.std() * np.sqrt(52)
        return cagr, vol, dd
    return stats(R), stats(M), (R - M).mean() / (R - M).std() * np.sqrt(52), np.mean(R > M)

for lab, a, b in ERAS + [('1997-2026', t0, T)]:
    r1 = simulate(lambda t: picker(t), a, b); r2 = simulate(lambda t: picker(t, near=True), a, b); r3 = simulate(lambda t: picker(t, n=5), a, b); r4 = simulate(lambda t: picker(t, n=5, near=True), a, b)
    print(f"{lab:30s} 10 sans filtre {r1[0][0]*100:+5.1f} %/an (perte max {r1[0][2]*100:+4.0f}) | 10 avec 2-10 % {r2[0][0]*100:+5.1f} ({r2[0][2]*100:+4.0f}) | 5 sans {r3[0][0]*100:+5.1f} ({r3[0][2]*100:+4.0f}) | 5 avec {r4[0][0]*100:+5.1f} ({r4[0][2]*100:+4.0f})")
