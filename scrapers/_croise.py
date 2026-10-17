"""Sortie de base (nouveau plus haut 52 s < 4 sem après 6 mois à −25 %) croisée avec d'autres repères : probabilité de +40 % en 6 mois."""
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
        for t in range(k - 1, T): o[:, t] = np.nanmean(P[:, t-k+1:t+1], 1)
        return o
    m10, m40 = sma(10), sma(40); trend = (m10 > m40) & (P > m40)
    mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
    hi = np.full_like(P, np.nan); lo = np.full_like(P, np.nan)
    for t in range(51, T): hi[:, t] = np.nanmax(P[:, t-51:t+1], 1); lo[:, t] = np.nanmin(P[:, t-51:t+1], 1)
    ratio = P / hi; rl = np.full_like(P, np.nan); rl[:, 26:] = ratio[:, :-26]
    x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)
    for t in range(25, T):
        y = L[:, t-25:t+1]; ym = np.nanmean(y, 1, keepdims=True); s26[:, t] = np.exp(np.nansum((y-ym)*x, 1) / (x*x).sum() * 26) - 1
    ret = np.full_like(P, np.nan); ret[:, 1:] = P[:, 1:] / P[:, :-1] - 1
    v26 = np.full_like(P, np.nan)
    for t in range(26, T): v26[:, t] = np.nanstd(ret[:, t-25:t+1], 1)
    r4 = np.full_like(P, np.nan); r4[:, 4:] = P[:, 4:] / P[:, :-4] - 1
    H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
    valid = np.isfinite(mom) & np.isfinite(fut) & np.isfinite(s26) & np.isfinite(rl)
    def pct(a):
        r = np.full_like(a, np.nan)
        for t in range(T):
            ok = np.isfinite(a[:, t]) & valid[:, t]
            if ok.sum() > 30: r[ok, t] = a[ok, t].argsort().argsort() / (ok.sum() - 1)
        return r
    mp, vp, r4p = pct(mom), pct(v26), pct(r4)
    # ampleur du marché (part en tendance), régime par tiers de son histoire
    up = np.array([np.nanmean(trend[valid[:, t], t]) if valid[:, t].sum() > 30 else np.nan for t in range(T)])
    c1, c2 = np.nanpercentile(up, [33.3, 66.7]); reg = np.where(up < c1, 0, np.where(up < c2, 1, 2))
    brk0 = valid & (ratio >= 0.999) & (rl < 0.75)
    brk = np.zeros_like(brk0)
    for t in range(T): brk[:, t] = np.any(brk0[:, max(0, t-3):t+1], 1)
    brk &= valid
    # profondeur et durée de la base : plus bas des 6 derniers mois vs plus haut d'avant
    deep = rl < 0.6
    up2 = (P / lo >= 2)
    G = {
      'toutes les sociétés (référence)': valid,
      '🚀 sortie de base (< 4 sem)': brk,
      '  + pente forte (≥ +40 %/6 mois)': brk & trend & (s26 >= 0.41),
      '  + pente moyenne': brk & trend & (s26 >= 0.14) & (s26 < 0.41),
      '  + pente légère ou sans tendance': brk & ~(trend & (s26 >= 0.14)),
      '  + 12 mois tiers haut (dans le classement)': brk & (mp >= 2/3),
      '  + 12 mois tiers moyen': brk & (mp >= 1/3) & (mp < 2/3),
      '  + 12 mois tiers bas (encore écartée)': brk & (mp < 1/3),
      '  + base profonde (−40 % il y a 6 mois)': brk & deep,
      '  + base moins profonde (−25 à −40 %)': brk & ~deep,
      '  + déjà doublé depuis le plus bas': brk & up2,
      '  + moins de ×2 depuis le plus bas': brk & ~up2,
      '  + cours agité (tiers haut de volatilité)': brk & (vp >= 2/3),
      '  + cours calme (2 tiers bas)': brk & (vp < 2/3),
      '  + forte poussée sur 4 sem (tiers haut)': brk & (r4p >= 2/3),
      '  + marché pessimiste (peu de tendances)': brk & (reg == 0)[None, :],
      '  + marché neutre': brk & (reg == 1)[None, :],
      '  + marché euphorique': brk & (reg == 2)[None, :],
      '  + pente forte + marché pessimiste ou neutre': brk & trend & (s26 >= 0.41) & (reg <= 1)[None, :],
      '  + pente forte + agité': brk & trend & (s26 >= 0.41) & (vp >= 2/3),
      '  + pente forte + 12 mois tiers haut': brk & trend & (s26 >= 0.41) & (mp >= 2/3),
    }
    mid = (52 + T) // 2
    print(f"{'combinaison':52s} {'P(+40 %)':>9s} {'1 sur':>6s} {'P(−25 %)':>9s} {'excès 6 m':>10s} {'1re / 2e moitié':>16s} {'cas/sem':>7s} {'cas':>5s}")
    def stats(M, a, b):
        hit = crash = n = 0; ex = []; base_h = []; 
        for t in range(a, min(b, T - H)):
            ok = valid[:, t]; m = M[:, t] & ok
            if not m.any(): continue
            f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
            hit += (fut[m, t] >= 0.4).sum(); crash += (fut[m, t] <= -0.25).sum(); n += m.sum()
            ex.append((np.nanmean(f[m]) - np.nanmean(f[ok]), m.sum()))
        if not n: return np.nan, np.nan, np.nan, 0
        e = sum(a*w for a, w in ex) / sum(w for _, w in ex)
        return hit / n, crash / n, e, n
    for g, M in G.items():
        h, c, e, n = stats(M, 52, T); h1, _, _, n1 = stats(M, 52, mid); h2, _, _, n2 = stats(M, mid, T)
        print(f"{g:52s} {h*100:7.1f} % {1/h if h else 0:6.1f} {c*100:7.1f} % {e*100:+8.1f} pt {h1*100:6.1f} / {h2*100:4.1f} % {n/(T-H-52):7.1f} {n:5d}")
if __name__ == '__main__':
    run(*load_cat(), '5 ans, catalogue liquide')
    try: run(*load_8y(), '8 ans, sociétés > 500 M€')
    except Exception as e: print('8 ans indisponible', e)
