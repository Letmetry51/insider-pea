"""Historique maximal (Yahoo, period=max, hebdomadaire) : mêmes tests que sur 5 et 8 ans, par grande période."""
import json, glob, time, sys, numpy as np, pandas as pd
def log(*a): print(*a, flush=True)
def universe():
    uni = json.load(open('../../data/sectors/universe.json'))['items']
    sec = {k: v.get('sector') or '?' for k, v in uni.items()}
    for f in glob.glob('../../data/societes/*.json'):
        for k, x in json.load(open(f))['items'].items():
            if (x.get('turnoverEur') or 0) >= 1e6 and x.get('pea') is not False: sec.setdefault(k, x.get('sector') or '?')
    return sec
def download(tick):
    import yfinance as yf
    C, V = [], []
    tick = sorted(tick)
    for i in range(0, len(tick), 60):
        b = tick[i:i+60]; df = None
        for a in range(3):
            try: df = yf.download(b, period='max', interval='1wk', auto_adjust=True, progress=False, threads=True, group_by='column'); break
            except Exception as e: log('lot', i, str(e)[:80]); time.sleep(5)
        if df is None or df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): C.append(df['Close']); V.append(df['Volume'])
        else: C.append(df[['Close']].rename(columns={'Close': b[0]})); V.append(df[['Volume']].rename(columns={'Volume': b[0]}))
        time.sleep(1)
    def tidy(F):
        X = pd.concat(F, axis=1); X = X.loc[:, ~X.columns.duplicated()]
        X.index = pd.to_datetime(X.index).tz_localize(None).normalize(); return X.sort_index()
    return tidy(C).resample('W-FRI').last(), tidy(V).resample('W-FRI').sum(min_count=1)
def clean(P):
    """Coupe chaque série après son dernier saut anormal (regroupement mal ajusté) : on ne garde que la partie fiable."""
    P = np.where(P > 0, P, np.nan); cut = 0
    for i in range(P.shape[0]):
        p = P[i]; ok = np.where(np.isfinite(p))[0]
        if len(ok) < 2: continue
        q = p[ok[1:]] / p[ok[:-1]]; bad = np.where((q > 2.5) | (q < 0.35))[0]
        if len(bad): P[i, :ok[bad[-1] + 1]] = np.nan; cut += 1
    return P, cut
def main():
    sec = universe(); log('univers', len(sec), 'symboles')
    t0 = time.time(); W, V = download(list(sec)); log('téléchargé en', int(time.time() - t0), 's :', W.shape)
    W = W.loc['1985':]; V = V.reindex(index=W.index, columns=W.columns)
    first = W.apply(lambda c: c.first_valid_index())
    log('début des séries : ' + ', '.join(f"avant {y} : {(first < pd.Timestamp(str(y))).sum()}" for y in (1995, 2000, 2005, 2010)))
    dates = [str(d.date()) for d in W.index]; cols = list(W.columns)
    P, cut = clean(W.values.T.astype(float)); VO = V.values.T.astype(float)
    log('séries coupées après un saut anormal :', cut)
    np.savez_compressed('long.npz', P=P.astype('float32'), V=VO.astype('float32'), dates=np.array(dates), cols=np.array(cols), sec=np.array([sec.get(c, '?') for c in cols]))
    analyse(dates, P, VO, np.array([sec.get(c, '?') for c in cols]))
def analyse(dates, P, VO, sec):
    N, T = P.shape; L = np.log(P)
    yr = np.array([int(d[:4]) for d in dates])
    def sma(A, k):
        o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(np.isfinite(A), 1)
        o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
        cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan; return o
    m10, m40 = sma(P, 10), sma(P, 40); trend = (m10 > m40) & (P > m40)
    mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
    hi = np.full_like(P, np.nan)
    for t in range(51, T): hi[:, t] = np.nanmax(P[:, t-51:t+1], 1) if True else 0
    ratio = P / hi; rl = np.full_like(P, np.nan); rl[:, 26:] = ratio[:, :-26]
    x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)
    for t in range(25, T):
        y = L[:, t-25:t+1]; ym = y.mean(1, keepdims=True); s26[:, t] = np.exp(((y - ym) * x).sum(1) / (x * x).sum() * 26) - 1
    H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
    valid = np.isfinite(mom) & np.isfinite(fut) & np.isfinite(s26) & np.isfinite(rl)
    mp = np.full_like(P, np.nan)
    for t in range(T):
        ok = valid[:, t]
        if ok.sum() > 30: mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
    nval = valid.sum(0)
    up = np.array([np.nanmean(trend[valid[:, t], t]) if nval[t] > 30 else np.nan for t in range(T)])
    c1, c2 = np.nanpercentile(up, [33.3, 66.7]); reg = np.where(up < c1, 0, np.where(up < c2, 1, 2))[None, :]
    brk0 = valid & (ratio >= 0.999) & (rl < 0.75); brk = np.zeros_like(brk0)
    for t in range(T): brk[:, t] = np.any(brk0[:, max(0, t-3):t+1], 1)
    v10, v52 = sma(VO, 10), sma(VO, 52)
    r4 = np.full_like(P, np.nan); r4[:, 4:] = P[:, 4:] / P[:, :-4] - 1
    volsurge = (v10 > 2 * v52) & (r4 > 0)
    t52 = int(np.argmax(nval > 30))
    eras = [('tout l\'historique', t52, T), ('jusqu\'à 2008 (bulle internet, krach 2008)', t52, int(np.searchsorted(yr, 2009))),
            ('2009–2017', int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))), ('2018–2026', int(np.searchsorted(yr, 2018)), T)]
    log(f"\n=== {N} sociétés, {dates[t52]} → {dates[-1]} ; sociétés testables par semaine : {int(nval[t52])} au début, {int(nval[-30])} à la fin")
    log('ATTENTION : seules les sociétés encore cotées aujourd\'hui sont présentes (biais de survie, plus fort sur les années anciennes).')
    def st(M, a, b):
        win = hit = cr = n = 0; ex = []
        for t in range(a, min(b, T - H)):
            ok = valid[:, t]; m = M[:, t] & ok
            if ok.sum() < 30 or not m.any(): continue
            f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
            win += (fut[m, t] > 0).sum(); hit += (fut[m, t] >= 0.4).sum(); cr += (fut[m, t] <= -0.25).sum(); n += m.sum(); ex.append(np.nanmean(f[m]) - np.nanmean(f[ok]))
        if not n: return None
        ex = np.array(ex); return (ex.mean(), ex.mean() / ex.std() * np.sqrt(len(ex)) / np.sqrt(H) if ex.std() > 0 else 0, win / n, hit / n, cr / n, n)
    G = [('classement (12 mois tiers haut + tendance)', valid & (mp >= 2/3) & trend),
         ('  + pente forte (≥ +40 %/6 mois)', valid & (mp >= 2/3) & trend & (s26 >= 0.41)),
         ('  + pente moyenne ou légère', valid & (mp >= 2/3) & trend & (s26 < 0.41)),
         ('pente forte (en tendance)', valid & trend & (s26 >= 0.41)), ('pente moyenne', valid & trend & (s26 >= 0.14) & (s26 < 0.41)), ('pente légère', valid & trend & (s26 < 0.14)),
         ('déjà +30 à +60 % (en tendance)', valid & trend & (mom >= .3) & (mom < .6)), ('déjà +60 à +100 %', valid & trend & (mom >= .6) & (mom < 1)),
         ('déjà +100 à +200 %', valid & trend & (mom >= 1) & (mom < 2)), ('déjà plus de +200 %', valid & trend & (mom >= 2)),
         ('🚀 sortie de base seule', brk), ('🚀 + pente forte + marché non euphorique', brk & trend & (s26 >= 0.41) & (reg <= 1)),
         ('les 3 filtres du bouton 🎯 (sans les comptes)', valid & (mp >= 2/3) & trend & (s26 >= 0.41) & (mom >= .6) & (mom <= 2)),
         ('volume ×2 sur 10 sem. avec hausse (non utilisé)', valid & volsurge), ('  volume ×2 + classement', valid & volsurge & (mp >= 2/3) & trend),
         ('au creux (12 mois négatif, sous MM40) : écarté', valid & (mom < 0) & (P < m40))]
    for lab, a, b in eras:
        log(f"\n--- {lab} ({dates[a][:4]}–{dates[min(b, T) - 1][:4]}) ---")
        log(f"{'groupe':52s} {'excès 6 m':>10s} {'t':>5s} {'gagne':>6s} {'≥+40 %':>7s} {'≤−25 %':>7s}")
        r0 = st(valid, a, b)
        if not r0: log('pas de données sur cette période'); continue
        log(f"{'toutes les sociétés':52s} {'':>10s} {'':>5s} {r0[2]*100:5.0f}% {r0[3]*100:6.1f}% {r0[4]*100:6.1f}%")
        for g, M in G:
            r = st(M, a, b)
            if r: log(f"{g:52s} {r[0]*100:+8.1f}pt {r[1]:5.1f} {r[2]*100:5.0f}% {r[3]*100:6.1f}% {r[4]*100:6.1f}%")
    # sorties
    score = 50 * mp + 10 * np.clip((ratio - 0.6) / 0.4, 0, 1) + np.where(trend, 15, np.where(P > m40, 5, 0)); elig = valid & (mp >= 1/3)
    sel = np.zeros_like(valid)
    for t in range(t52, T):
        sc = np.where(elig[:, t], score[:, t], -1); idx = np.argsort(-sc)[:5]; idx = idx[sc[idx] > 0]; sel[idx, t] = True
    ret = np.full_like(P, np.nan); ret[:, 1:] = P[:, 1:] / P[:, :-1] - 1
    mk = np.array([np.nanmean(ret[valid[:, t - 1], t]) if t and valid[:, t - 1].sum() > 30 else 0 for t in range(T)]); mcum = np.cumprod(1 + np.nan_to_num(mk))
    def trades(rule, a, b):
        R = []; held = {}
        for t in range(max(a, t52 + 1), min(b, T - 1)):
            for i in np.where(sel[:, t] & ~sel[:, t-1])[0]:
                if held.get(i, 0) > t: continue
                p0 = P[i, t]; top = p0; e = None
                for u in range(t + 1, min(T, t + 53)):
                    pu = P[i, u]
                    if not np.isfinite(pu): break
                    top = max(top, pu); h = u - t
                    if (rule == 'h26' and h >= 26) or (rule == 'h52' and h >= 52) or (rule == 's30' and (pu < .7 * p0 or h >= 26)) or (rule == 's15' and (pu < .85 * p0 or h >= 26)) \
                       or (rule == 'tr20' and (pu < .8 * top or h >= 52)) or (rule == 'mm40' and (pu < m40[i, u] or h >= 52)): e = u; break
                if not e: continue
                r = P[i, e] / p0 - 1; R.append((r, r - (mcum[e] / mcum[t] - 1), e - t)); held[i] = e
        A = np.array(R); return A
    rules = [('h26', 'garder 6 mois'), ('s30', '6 mois, protection −30 %'), ('h52', 'garder 1 an'), ('s15', '6 mois, stop −15 %'), ('tr20', 'stop suiveur −20 %'), ('mm40', 'vendre sous la MM40')]
    for lab, a, b in eras:
        log(f"\n--- sorties, 5 premières du classement : {lab} ---")
        log(f"{'règle':30s} {'trades':>6s} {'gagnants':>8s} {'> marché':>8s} {'moyen':>7s} {'pire 10 %':>9s} {'rythme/an':>9s}")
        for r, rl_ in rules:
            A = trades(r, a, b)
            if not len(A): continue
            log(f"{rl_:30s} {len(A):6d} {(A[:,0]>0).mean()*100:7.0f}% {(A[:,1]>0).mean()*100:7.0f}% {A[:,0].mean()*100:+6.1f}% {np.percentile(A[:,0],10)*100:+8.1f}% {np.log1p(np.clip(A[:,0],-.99,None)).sum()/A[:,2].sum()*52*100:+8.1f}%")
if __name__ == '__main__':
    main()
