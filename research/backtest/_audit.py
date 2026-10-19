"""Audit des filtres : chaque repère testable sur l'historique, seul et croisé avec le classement et la combinaison 🚀 + pente forte + marché non euphorique."""
import json, glob, numpy as np, sys
sys.path.insert(0, 'scrapers')
def load_cat():
    ser=[];meta=[];dates=None
    for f in glob.glob('../../data/societes/*.json'):
        s=json.load(open(f)); dates=s['wDates']
        for k,x in s['items'].items():
            w=x.get('w') or []
            if len(w)==len(dates) and (x.get('turnoverEur') or 0)>=1e6:
                ser.append([v if v else np.nan for v in w]); meta.append((x.get('sector') or '?', x.get('capEur') or np.nan))
    return dates,meta,np.array(ser,float)
def load_8y():
    import pandas as pd
    W=pd.read_csv('../../data/sectors/weekly.csv.gz',index_col=0,parse_dates=True,compression='gzip').sort_index()
    uni=json.load(open('../../data/sectors/universe.json'))['items']
    cols=[c for c in W.columns if c in uni and W[c].notna().sum()>=120]
    return [str(d.date()) for d in W.index],[(uni[c].get('sector') or '?', uni[c].get('capEur') or np.nan) for c in cols],W[cols].values.T.astype(float)
def run(dates, meta, P, label):
    P = np.where(P > 0, P, np.nan)
    jr = P[:, 1:] / P[:, :-1]; bad = (np.nanmax(jr, 1) > 2.5) | (np.nanmin(jr, 1) < 0.35); P = P[~bad]; meta=[m for m,b in zip(meta,bad) if not b]; N, T = P.shape
    sec=np.array([m[0] for m in meta]); cap=np.array([m[1] for m in meta],float)
    print(f"\n=== {label} : {N} sociétés, {T} semaines {dates[0]} → {dates[-1]}")
    L = np.log(P)
    def sma(k):
        o = np.full_like(P, np.nan)
        for t in range(k-1, T): o[:, t] = np.nanmean(P[:, t-k+1:t+1], 1)
        return o
    m10, m30, m40 = sma(10), sma(30), sma(40); trend = (m10 > m40) & (P > m40)
    m40r = np.full_like(P, np.nan); m40r[:, 4:] = m40[:, 4:] / m40[:, :-4]
    mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
    hi = np.full_like(P, np.nan); lo = np.full_like(P, np.nan)
    for t in range(51, T): hi[:, t] = np.nanmax(P[:, t-51:t+1], 1); lo[:, t] = np.nanmin(P[:, t-51:t+1], 1)
    ratio = P / hi; rl = np.full_like(P, np.nan); rl[:, 26:] = ratio[:, :-26]
    x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)
    for t in range(25, T):
        y = L[:, t-25:t+1]; ym = np.nanmean(y, 1, keepdims=True); s26[:, t] = np.exp(np.nansum((y-ym)*x, 1) / (x*x).sum() * 26) - 1
    d = np.full_like(P, np.nan); d[:, 1:] = P[:, 1:] - P[:, :-1]
    rsi = np.full_like(P, np.nan)
    for t in range(14, T):
        g = np.nansum(np.clip(d[:, t-13:t+1], 0, None), 1); l = -np.nansum(np.clip(d[:, t-13:t+1], None, 0), 1); rsi[:, t] = 100 - 100 / (1 + g / np.where(l > 0, l, np.nan))
    H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
    valid = np.isfinite(mom) & np.isfinite(fut) & np.isfinite(s26) & np.isfinite(rl)
    mp = np.full_like(P, np.nan)
    for t in range(T):
        ok = valid[:, t]
        if ok.sum() > 30: mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
    up = np.array([np.nanmean(trend[valid[:, t], t]) if valid[:, t].sum() > 30 else np.nan for t in range(T)])
    c1, c2 = np.nanpercentile(up, [33.3, 66.7]); reg = np.where(up < c1, 0, np.where(up < c2, 1, 2))[None, :]
    # force du secteur : médiane des 12 mois du secteur, rang parmi les secteurs
    secs = [s for s in set(sec) if (sec == s).sum() >= 8 and s != '?']
    secR = np.full_like(P, np.nan)
    for t in range(T):
        med = {s: np.nanmedian(mom[(sec == s) & valid[:, t], t]) for s in secs if ((sec == s) & valid[:, t]).sum() >= 5}
        if len(med) < 6: continue
        order = sorted(med, key=med.get); rk = {s: i / (len(order) - 1) for i, s in enumerate(order)}
        for s, r in rk.items(): secR[sec == s, t] = r
    brk0 = valid & (ratio >= 0.999) & (rl < 0.75); brk = np.zeros_like(brk0)
    for t in range(T): brk[:, t] = np.any(brk0[:, max(0, t-3):t+1], 1)
    tmpl = (P > m30) & (P > m40) & (m30 > m40) & (m10 > m30) & (m40r > 1) & (P / lo >= 1.3) & (ratio >= 0.75)
    RANK = valid & (mp >= 2/3) & trend
    COMBO = brk & valid & trend & (s26 >= 0.41) & (reg <= 1)
    capm = np.nanmedian(cap)
    X = {
      'pente forte': trend & (s26 >= 0.41),
      'Minervini (approché en hebdo)': tmpl,
      'près du plus haut (≥ 95 %)': ratio >= 0.95,
      'en repli de 5 à 25 %': (ratio < 0.95) & (ratio >= 0.75),
      'secteur fort (tiers haut des secteurs)': secR >= 2/3,
      'secteur faible (tiers bas)': secR < 1/3,
      'marché non euphorique': np.broadcast_to(reg <= 1, P.shape),
      'marché euphorique': np.broadcast_to(reg == 2, P.shape),
      'RSI 14 sem > 70 (surachat)': rsi > 70,
      'très étiré (> 50 % au-dessus MM40)': P / m40 > 1.5,
      f'petite capitalisation (< médiane {capm/1e9:.1f} Md€, taille actuelle)': (cap < capm)[:, None] & np.ones((1, T), bool),
      'grande capitalisation (≥ médiane)': (cap >= capm)[:, None] & np.ones((1, T), bool),
    }
    mid = (52 + T) // 2
    def stats(M, a=52, b=None):
        b = b or T; hit = cr = n = 0; ex = []
        for t in range(a, min(b, T - H)):
            ok = valid[:, t]; m = M[:, t] & ok
            if not m.any(): continue
            f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
            hit += (fut[m, t] >= 0.4).sum(); cr += (fut[m, t] <= -0.25).sum(); n += m.sum(); ex.append((np.nanmean(f[m]) - np.nanmean(f[ok])) * m.sum())
        return (hit / n, cr / n, sum(ex) / n, n) if n else (np.nan, np.nan, np.nan, 0)
    def line(lab, M):
        h, c, e, n = stats(M); h1, _, e1, _ = stats(M, 52, mid); h2, _, e2, _ = stats(M, mid, T)
        print(f"{lab:58s} {h*100:6.1f} % {c*100:6.1f} % {e*100:+6.1f} pt  ({e1*100:+5.1f} / {e2*100:+5.1f})  {n/(T-H-52):6.1f}")
    print(f"{'':58s} {'P(+40)':>8s} {'P(−25)':>8s} {'excès':>9s}  {'1re / 2e moitié':>16s} {'cas/sem':>7s}")
    for base_lab, B in (('TOUTES LES SOCIÉTÉS', valid), ('CLASSEMENT (12 mois tiers haut + tendance)', RANK), ('🚀 + PENTE FORTE + MARCHÉ NON EUPHORIQUE', COMBO)):
        line(base_lab, B)
        for k, M in X.items():
            if base_lab.startswith('🚀') and k in ('pente forte', 'marché non euphorique', 'marché euphorique'): continue
            line('  + ' + k, B & M)
if __name__ == '__main__':
    run(*load_cat(), '5 ans, catalogue liquide')
    try: run(*load_8y(), '8 ans, sociétés > 500 M€')
    except Exception as e: print('8 ans indisponible', e)
