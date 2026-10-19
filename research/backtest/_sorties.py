"""Fiabilité : règles de sortie, filtre de marché et saisonnalité des secteurs (5 ans catalogue, 8 ans > 500 M€)."""
import json, glob, numpy as np, sys, collections
sys.path.insert(0, 'scrapers')
from _audit import load_cat, load_8y
def prep(dates, meta, P):
    P = np.where(P > 0, P, np.nan)
    jr = P[:, 1:] / P[:, :-1]; bad = (np.nanmax(jr, 1) > 2.5) | (np.nanmin(jr, 1) < 0.35)
    return [d for d in dates], [m for m, b in zip(meta, bad) if not b], P[~bad]
def sorties(dates, meta, P, label):
    N, T = P.shape; L = np.log(P)
    print(f"\n=== {label} : {N} sociétés, {T} semaines {dates[0]} → {dates[-1]}")
    def sma(k):
        o = np.full_like(P, np.nan)
        for t in range(k-1, T): o[:, t] = np.nanmean(P[:, t-k+1:t+1], 1)
        return o
    m10, m40 = sma(10), sma(40); trend = (m10 > m40) & (P > m40)
    mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
    hi = np.full_like(P, np.nan)
    for t in range(51, T): hi[:, t] = np.nanmax(P[:, t-51:t+1], 1)
    ratio = P / hi
    x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)
    for t in range(25, T):
        y = L[:, t-25:t+1]; ym = np.nanmean(y, 1, keepdims=True); s26[:, t] = np.exp(np.nansum((y-ym)*x, 1) / (x*x).sum() * 26) - 1
    ret = np.full_like(P, np.nan); ret[:, 1:] = P[:, 1:] / P[:, :-1] - 1
    vol = np.full_like(P, np.nan)
    for t in range(26, T): vol[:, t] = np.nanstd(ret[:, t-25:t+1], 1)
    valid = np.isfinite(mom) & np.isfinite(P)
    mp = np.full_like(P, np.nan)
    for t in range(T):
        ok = valid[:, t]
        if ok.sum() > 30: mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
    up = np.array([np.nanmean(trend[valid[:, t], t]) if valid[:, t].sum() > 30 else np.nan for t in range(T)])
    c1, c2 = np.nanpercentile(up[np.isfinite(up)], [33.3, 66.7]); reg = np.where(up < c1, 0, np.where(up < c2, 1, 2))
    mkt = np.array([np.nanmean(ret[valid[:, t-1] if t else valid[:, 0], t]) if t else 0 for t in range(T)]); mkt = np.nan_to_num(mkt); mcum = np.cumprod(1 + mkt)
    score = 50 * mp + 10 * np.clip((ratio - 0.6) / 0.4, 0, 1) + np.where(trend, 15, np.where(P > m40, 5, 0))
    elig = valid & (mp >= 1/3)
    def picks(extra=None, k=5):
        out = np.zeros_like(valid)
        for t in range(52, T):
            sc = np.where(elig[:, t] & (extra[:, t] if extra is not None else True), score[:, t], -1)
            idx = np.argsort(-sc)[:k]; idx = idx[sc[idx] > 0]; out[idx, t] = True
        return out
    def trades(sel, rule, mfilter=None):
        R = []
        held = {}
        for t in range(52, T - 1):
            if mfilter is not None and not mfilter(t): continue
            for i in np.where(sel[:, t] & ~sel[:, t-1])[0]:
                if i in held and held[i] > t: continue
                p0 = P[i, t]; top = p0; e = None
                for u in range(t + 1, min(T, t + 53)):
                    pu = P[i, u]
                    if not np.isfinite(pu): break
                    top = max(top, pu); h = u - t
                    if rule == 'h13' and h >= 13: e = u
                    elif rule == 'h26' and h >= 26: e = u
                    elif rule == 'h52' and h >= 52: e = u
                    elif rule == 'mm40' and (pu < m40[i, u] or h >= 52): e = u
                    elif rule == 'tr15' and (pu < 0.85 * top or h >= 52): e = u
                    elif rule == 'tr20' and (pu < 0.80 * top or h >= 52): e = u
                    elif rule == 'tr25' and (pu < 0.75 * top or h >= 52): e = u
                    elif rule == 'atr3' and (pu < top * (1 - 3 * vol[i, t]) or h >= 52): e = u
                    elif rule == 'rank' and ((mp[i, u] < 0.5 if np.isfinite(mp[i, u]) else True) or h >= 52): e = u
                    elif rule == 'stop15h26' and (pu < 0.85 * p0 or h >= 26): e = u
                    if e: break
                if not e: continue
                r = P[i, e] / p0 - 1; bm = mcum[e] / mcum[t] - 1
                R.append((r, r - bm, e - t)); held[i] = e
        A = np.array(R)
        if not len(A): return None
        return dict(n=len(A), win=(A[:, 0] > 0).mean(), beat=(A[:, 1] > 0).mean(), avg=A[:, 0].mean(), med=np.median(A[:, 0]), ex=A[:, 1].mean(), wk=A[:, 2].mean(),
                    p10=np.percentile(A[:, 0], 10), perwk=np.log1p(np.clip(A[:, 0], -0.99, None)).sum() / A[:, 2].sum() * 52)
    base = picks(); strong = picks(trend & (s26 >= 0.41))
    print(f"{'stratégie (5 premières du classement, entrée à leur arrivée)':66s} {'trades':>6s} {'gagnants':>8s} {'> marché':>8s} {'moyen':>7s} {'médian':>7s} {'pire 10 %':>9s} {'durée':>6s} {'rythme/an':>9s}")
    rules = [('h13', 'garder 3 mois'), ('h26', 'garder 6 mois'), ('h52', 'garder 1 an'), ('mm40', 'vendre sous la MM40 (200 séances)'), ('tr15', 'stop suiveur −15 % du plus haut'),
             ('tr20', 'stop suiveur −20 %'), ('tr25', 'stop suiveur −25 %'), ('atr3', 'stop suiveur 3 × volatilité (type SuperTrend)'), ('rank', 'vendre quand il sort de la moitié haute (12 mois)'), ('stop15h26', '6 mois avec stop fixe −15 %')]
    def show(lab, st):
        if st: print(f"{lab:66s} {st['n']:6d} {st['win']*100:7.0f} % {st['beat']*100:7.0f} % {st['avg']*100:+6.1f} % {st['med']*100:+6.1f} % {st['p10']*100:+8.1f} % {st['wk']:5.0f} s {st['perwk']*100:+8.1f} %")
    for r, lab in rules: show(lab, trades(base, r))
    print('— filtre de marché (sortie : stop suiveur −20 %) —')
    show('entrer seulement si marché non euphorique', trades(base, 'tr20', lambda t: reg[t] <= 1))
    show('entrer seulement si marché euphorique', trades(base, 'tr20', lambda t: reg[t] == 2))
    show('entrer seulement si l\'ampleur monte (vs 4 sem.)', trades(base, 'tr20', lambda t: up[t] > up[t-4]))
    show('entrer seulement si l\'ampleur baisse', trades(base, 'tr20', lambda t: up[t] <= up[t-4]))
    show('entrer seulement si marché au-dessus de sa MM40', trades(base, 'tr20', lambda t: mcum[t] > np.mean(mcum[t-39:t+1])))
    print('— 5 premières parmi les pentes fortes —')
    for r, lab in (('h26', 'garder 6 mois'), ('tr20', 'stop suiveur −20 %'), ('mm40', 'vendre sous la MM40')): show(lab, trades(strong, r))
    return dict(dates=dates, meta=meta, P=P)
def saison(dates, meta, P, label):
    N, T = P.shape; sec = np.array([m[0] for m in meta])
    mon = np.array([int(d[5:7]) for d in dates]); yr = np.array([int(d[:4]) for d in dates])
    # rendements mensuels : dernière clôture de chaque mois
    ends = [t for t in range(T - 1) if mon[t + 1] != mon[t]] + [T - 1]
    M = []; Mm = []; My = []
    for a, b in zip(ends[:-1], ends[1:]):
        r = P[:, b] / P[:, a] - 1; M.append(r); Mm.append(mon[b]); My.append(yr[b])
    M = np.array(M).T; Mm = np.array(Mm); My = np.array(My)
    mk = np.nanmean(M, 0)
    print(f"\n=== Saisonnalité ({label}) : {len(Mm)} mois, {My.min()}–{My.max()}")
    print('marché (moyenne des sociétés) par mois : ' + '  '.join(f"{m}:{np.mean(mk[Mm==m])*100:+.1f}%({(mk[Mm==m]>0).mean()*100:.0f})" for m in range(1, 13)))
    secs = [s for s in collections.Counter(sec) if (sec == s).sum() >= 15 and s != '?']
    X = {s: np.nanmean(M[sec == s], 0) - mk for s in secs}
    years = sorted(set(My)); half = years[len(years) // 2]
    a1 = []; a2 = []
    for s in secs:
        for m in range(1, 13):
            v1 = X[s][(Mm == m) & (My < half)]; v2 = X[s][(Mm == m) & (My >= half)]
            if len(v1) and len(v2): a1.append(np.mean(v1)); a2.append(np.mean(v2))
    print(f"corrélation de l'excès secteur×mois entre {years[0]}–{half-1} et {half}–{years[-1]} : {np.corrcoef(a1, a2)[0,1]:+.2f} (0 = aucune saisonnalité stable)")
    # stratégie hors échantillon : chaque mois, les 2 secteurs au meilleur historique pour ce mois (années précédentes seulement)
    gains = []; hits = []
    for j in range(len(Mm)):
        prev = {s: X[s][(Mm == Mm[j]) & (My < My[j])] for s in secs}
        prev = {s: v[np.isfinite(v)] for s, v in prev.items()}
        if min(len(v) for v in prev.values()) < 3: continue
        best = sorted(secs, key=lambda s: -np.mean(prev[s]))[:2]; worst = sorted(secs, key=lambda s: np.mean(prev[s]))[:2]
        g = np.mean([X[s][j] for s in best]) - np.mean([X[s][j] for s in worst]); gains.append(g); hits.append(np.mean([X[s][j] for s in best]) > 0)
    g = np.array(gains)
    print(f"hors échantillon : 2 meilleurs secteurs « saisonniers » du mois moins 2 pires : {g.mean()*100:+.2f} pt/mois, t {g.mean()/g.std()*np.sqrt(len(g)):.1f}, {np.mean(hits)*100:.0f} % des mois les meilleurs battent le marché ({len(g)} mois)")
    # les cas les plus réguliers (8 ans) : secteur×mois positifs ou négatifs presque chaque année
    reg = []
    for s in secs:
        for m in range(1, 13):
            v = X[s][Mm == m]; v = v[np.isfinite(v)]
            if len(v) >= 5: reg.append(((v > 0).mean(), np.mean(v), s, m, len(v)))
    reg.sort(key=lambda r: -abs(r[0] - 0.5))
    print('les plus réguliers (part des années au-dessus du marché, excès moyen) : ' + ' ; '.join(f"{r[2]} {r[3]:02d} : {r[0]*100:.0f} % ({r[1]*100:+.1f} pt, {r[4]} ans)" for r in reg[:10]))
    print(f"   attendu par hasard : sur {len(reg)} cases secteur×mois et {reg[0][4]} ans, environ {sum(1 for r in reg if abs(r[0]-0.5)>=0.35)} au-delà de 85 % ou sous 15 % (ici), contre ≈ {len(reg)*2*sum(__import__('math').comb(reg[0][4],k) for k in range(reg[0][4]+1) if k/reg[0][4]>=0.85)/2**reg[0][4]:.0f} au hasard")
if __name__ == '__main__':
    d = prep(*load_cat()); sorties(*d, '5 ans, catalogue liquide'); saison(*d, '5 ans')
    try:
        d = prep(*load_8y()); sorties(*d, '8 ans, sociétés > 500 M€'); saison(*d, '8 ans')
    except Exception as e: print('8 ans indisponible', e)
