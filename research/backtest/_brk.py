"""Prémices d'une forte hausse : quels signaux précèdent une hausse d'au moins 40 % en 6 mois ? (5 ans catalogue, 8 ans > 500 M€)"""
import json, glob, numpy as np, sys
sys.path.insert(0, 'scrapers')
from _pente import load_cat, load_8y
def run(dates, names, P, label):
    P = np.where(P > 0, P, np.nan)
    jr = P[:, 1:] / P[:, :-1]; bad = (np.nanmax(jr, 1) > 2.5) | (np.nanmin(jr, 1) < 0.35); P = P[~bad]; N, T = P.shape
    print(f"\n=== {label} : {N} sociétés, {T} semaines {dates[0]} → {dates[-1]}")
    L = np.log(P)
    def sma(k):
        o = np.full_like(P, np.nan)
        for t in range(k - 1, T): o[:, t] = np.nanmean(P[:, t - k + 1:t + 1], 1)
        return o
    m10, m40 = sma(10), sma(40); trend = (m10 > m40) & (P > m40)
    mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
    r13 = np.full_like(P, np.nan); r13[:, 13:] = P[:, 13:] / P[:, :-13] - 1
    hi = np.full_like(P, np.nan); lo = np.full_like(P, np.nan); hi26 = np.full_like(P, np.nan); lo26 = np.full_like(P, np.nan)
    for t in range(51, T):
        hi[:, t] = np.nanmax(P[:, t-51:t+1], 1); lo[:, t] = np.nanmin(P[:, t-51:t+1], 1)
        hi26[:, t] = np.nanmax(P[:, t-25:t+1], 1); lo26[:, t] = np.nanmin(P[:, t-25:t+1], 1)
    ratio = P / hi
    def slope(W):
        x = np.arange(W) - (W - 1) / 2; s = np.full_like(P, np.nan)
        for t in range(W - 1, T):
            y = L[:, t-W+1:t+1]; ym = np.nanmean(y, 1, keepdims=True); s[:, t] = np.exp(np.nansum((y - ym) * x, 1) / (x * x).sum() * 26) - 1
        return s
    s26, s13 = slope(26), slope(13)
    ret = np.full_like(P, np.nan); ret[:, 1:] = np.log(P[:, 1:] / P[:, :-1])
    v10 = np.full_like(P, np.nan); v52 = np.full_like(P, np.nan)
    for t in range(52, T): v10[:, t] = np.nanstd(ret[:, t-9:t+1], 1); v52[:, t] = np.nanstd(ret[:, t-51:t+1], 1)
    squeeze = v10 / v52
    H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
    valid = np.isfinite(mom) & np.isfinite(fut) & np.isfinite(s26)
    def pct(a):
        r = np.full_like(a, np.nan)
        for t in range(T):
            v = a[:, t]; ok = np.isfinite(v) & valid[:, t]
            if ok.sum() > 30: r[ok, t] = v[ok].argsort().argsort() / (ok.sum() - 1)
        return r
    mp, r13p, sqp = pct(mom), pct(r13), pct(squeeze)
    rl = np.full_like(P, np.nan); rl[:, 26:] = ratio[:, :-26]
    t4 = np.zeros_like(trend); t4[:, 4:] = trend[:, 4:] & ~trend[:, :-4]
    brk = valid & (ratio >= 0.999) & (rl < 0.75)
    def recent(k):
        o = np.zeros_like(brk)
        for t in range(T): o[:, t] = np.any(brk[:, max(0, t-k+1):t+1], 1)
        return o
    G = {'référence': valid, 'cassure cette semaine': brk,
      'cassure < 4 sem': valid & recent(4), 'cassure < 4 sem, en tendance, ≥ 90 % du plus haut': valid & recent(4) & trend & (ratio >= 0.9),
      'cassure < 8 sem': valid & recent(8), 'cassure < 8 sem, en tendance, ≥ 90 % du plus haut': valid & recent(8) & trend & (ratio >= 0.9),
      'cassure < 13 sem, en tendance, ≥ 90 %': valid & recent(13) & trend & (ratio >= 0.9)}
    mid = (52 + T) // 2
    print(f"{'signal':62s} {'P(+40 % en 6 m)':>15s} {'× réf.':>7s} {'P(−25 %)':>9s} {'excès 6 m':>10s} {'1re/2e moitié (× réf.)':>23s} {'taille':>6s}")
    def stats(M, a, b):
        hit, crash, ex, base = [], [], [], []
        for t in range(a, min(b, T - H)):
            ok = valid[:, t]; m = M[:, t] & ok
            if m.sum() < 3: continue
            hit.append((fut[m, t] >= 0.4).mean()); crash.append((fut[m, t] <= -0.25).mean()); base.append((fut[ok, t] >= 0.4).mean())
            f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98])); ex.append(np.nanmean(f[m]) - np.nanmean(f[ok]))
        return np.mean(hit), np.mean(crash), np.mean(ex), np.mean(base)
    for g, M in G.items():
        h, c, e, b = stats(M, 52, T); h1, _, _, b1 = stats(M, 52, mid); h2, _, _, b2 = stats(M, mid, T)
        sz = np.nanmean([M[:, t].sum() for t in range(52, T - H)])
        print(f"{g:62s} {h*100:13.1f} % {h/b:6.1f}× {c*100:7.1f} % {e*100:+8.1f} pt {h1/b1:9.1f}× / {h2/b2:4.1f}× {sz:6.0f}")
if __name__ == '__main__':
    run(*load_cat(), '5 ans, catalogue liquide')
