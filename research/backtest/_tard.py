"""« Arriver après la bataille » : que fait une société déjà en forte hausse ? Et le rattrapage dans un secteur qui démarre."""
import json, glob, numpy as np, sys
sys.path.insert(0, 'scrapers')
from _audit import load_cat, load_8y
def run(dates, meta, P, label):
    P = np.where(P > 0, P, np.nan)
    jr = P[:, 1:] / P[:, :-1]; bad = (np.nanmax(jr, 1) > 2.5) | (np.nanmin(jr, 1) < 0.35); P = P[~bad]; meta = [m for m, b in zip(meta, bad) if not b]; N, T = P.shape
    sec = np.array([m[0] for m in meta])
    print(f"\n=== {label} : {N} sociétés, {T} semaines {dates[0]} → {dates[-1]}")
    def sma(k):
        o = np.full_like(P, np.nan)
        for t in range(k-1, T): o[:, t] = np.nanmean(P[:, t-k+1:t+1], 1)
        return o
    m10, m40 = sma(10), sma(40); trend = (m10 > m40) & (P > m40)
    mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
    r13 = np.full_like(P, np.nan); r13[:, 13:] = P[:, 13:] / P[:, :-13] - 1
    H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
    valid = np.isfinite(mom) & np.isfinite(fut)
    mp = np.full_like(P, np.nan)
    for t in range(T):
        ok = valid[:, t]
        if ok.sum() > 30: mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
    secs = [s for s in set(sec) if (sec == s).sum() >= 8 and s != '?']
    sm13 = np.full_like(P, np.nan); smom = np.full_like(P, np.nan)
    for t in range(T):
        for s in secs:
            m = (sec == s) & valid[:, t]
            if m.sum() >= 5: sm13[sec == s, t] = np.nanmedian(r13[m, t]); smom[sec == s, t] = np.nanmedian(mom[m, t])
    srk = np.full_like(P, np.nan)
    for t in range(T):
        v = sm13[:, t]; ok = np.isfinite(v) & valid[:, t]
        if ok.sum() > 30: srk[ok, t] = v[ok].argsort().argsort() / (ok.sum() - 1)
    def stats(M, a=52, b=None):
        b = b or T; hit = cr = win = n = 0; ex = []
        for t in range(a, min(b, T - H)):
            ok = valid[:, t]; m = M[:, t] & ok
            if not m.any(): continue
            f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
            hit += (fut[m, t] >= 0.4).sum(); cr += (fut[m, t] <= -0.25).sum(); win += (fut[m, t] > 0).sum(); n += m.sum(); ex.append((np.nanmean(f[m]) - np.nanmean(f[ok])) * m.sum())
        return (win / n, hit / n, cr / n, sum(ex) / n, n) if n else (np.nan,) * 4 + (0,)
    mid = (52 + T) // 2
    def line(lab, M):
        w, h, c, e, n = stats(M); e1 = stats(M, 52, mid)[3]; e2 = stats(M, mid, T)[3]
        print(f"{lab:62s} {w*100:5.0f} % {h*100:6.1f} % {c*100:6.1f} % {e*100:+6.1f} pt ({e1*100:+5.1f}/{e2*100:+5.1f}) {n/(T-H-52):6.1f}")
    print(f"{'déjà monté de… (sur 12 mois, en tendance haussière)':62s} {'gagne':>7s} {'≥+40 %':>8s} {'≤−25 %':>8s} {'excès 6 m':>10s} {'moitiés':>13s} {'cas/sem':>6s}")
    line('toutes les sociétés', valid)
    for lo, hi, lab in ((-9, 0, 'en baisse'), (0, .3, '0 à +30 %'), (.3, .6, '+30 à +60 %'), (.6, 1, '+60 à +100 %'), (1, 2, '+100 à +200 % (comme Wallenius, Repsol)'), (2, 99, 'plus de +200 %')):
        line('  ' + lab, valid & trend & (mom >= lo) & (mom < hi))
    print('— rattrapage dans un secteur qui démarre (secteur parmi le tiers le plus fort sur 3 mois) —')
    line('  secteur qui démarre, société encore en retard (12 mois tiers bas/moyen)', valid & (srk >= 2/3) & (mp < 2/3))
    line('  … et la société vient de passer en tendance haussière', valid & (srk >= 2/3) & (mp < 2/3) & trend)
    line('  secteur qui démarre, société déjà en tête (12 mois tiers haut)', valid & (srk >= 2/3) & (mp >= 2/3))
    line('  secteur à la traîne, société en tête', valid & (srk < 1/3) & (mp >= 2/3))
if __name__ == '__main__':
    run(*load_cat(), '5 ans, catalogue liquide')
    try: run(*load_8y(), '8 ans, sociétés > 500 M€')
    except Exception as e: print('8 ans indisponible', e)
