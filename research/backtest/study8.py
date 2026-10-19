"""Étude sur 8 ans (cours et volumes hebdomadaires du module secteurs) : tendance, volume, départs de tendance, psychologie."""
import math, statistics as st, collections, bisect, json, sys
import numpy as np, pandas as pd
W = pd.read_csv('../../data/sectors/weekly.csv.gz', index_col=0, parse_dates=True, compression='gzip').sort_index()
V = pd.read_csv('../../data/sectors/weekly_volume.csv.gz', index_col=0, parse_dates=True, compression='gzip').sort_index()
uni = json.load(open('../../data/sectors/universe.json'))['items']
cols = [c for c in W.columns if c in uni and c in V.columns and W[c].notna().sum() >= 120]
W, V = W[cols], V[cols].reindex(W.index)
dates = list(W.index); n = len(dates); H = {'3 mois': 13, '6 mois': 26}
print('sociétés', len(cols), 'semaines', n, dates[0].date(), dates[-1].date())
P = W.values; Q = V.values
obs = collections.defaultdict(list)
for j in range(len(cols)):
    p = P[:, j]; q = Q[:, j]
    for t in range(60, n - 1):
        c = p[t]
        if not (c > 0) or not (p[t-4] > 0) or not (p[t-52] > 0) or not (p[t-13] > 0): continue
        win = p[t-51:t+1]; win = win[win > 0]
        if len(win) < 45: continue
        w40 = p[t-39:t+1]; w10 = p[t-9:t+1]; w30 = p[t-29:t+1]; w40b = p[t-47:t-7]; w10b = p[t-17:t-7]
        if min(len(w40[w40 > 0]), len(w10[w10 > 0])) < 8: continue
        m10, m30, m40 = np.nanmean(w10), np.nanmean(w30), np.nanmean(w40); m40b = np.nanmean(w40b); m10b = np.nanmean(w10b)
        hi, lo = win.max(), win.min()
        r = p[t-12:t+1] / p[t-13:t] - 1; vv = q[t-12:t+1]
        up = np.nansum(vv[r > 0]); dn = np.nansum(vv[r < 0])
        acc = up / dn if dn > 0 else None
        v4 = np.nanmean(q[t-3:t+1]); v52 = np.nanmean(q[t-51:t+1])
        surge = v52 > 0 and v4 / v52 > 1.5 and p[t] / p[t-4] > 1
        fw = {h: max(-.6, min(1.5, p[t+L] / c - 1)) for h, L in H.items() if t + L < n and p[t+L] > 0}
        tmpl = c > m30 and c > m40 and m30 > m40 and m40 > np.nanmean(p[t-43:t-3]) and m10 > m30 and c > m10 and c >= 1.3 * lo and c >= 0.75 * hi
        obs[t].append(dict(mom=p[t-4]/p[t-52]-1, r3=c/p[t-13]-1, ratio=c/hi, trend=m10 > m40 and c > m40, cross=m10 > m40 and m10b <= m40b,
                           acc=acc, surge=surge, tmpl=tmpl, nearlow=c <= 1.15 * lo, fw=fw))
breadth = {}
for t, v in obs.items():
    ms = sorted(x['mom'] for x in v); rs = sorted(x['r3'] for x in v); ac = sorted(x['acc'] for x in v if x['acc'] is not None)
    for x in v:
        x['mp'] = bisect.bisect_left(ms, x['mom']) / len(ms); x['rp'] = bisect.bisect_left(rs, x['r3']) / len(rs)
        x['ap'] = bisect.bisect_left(ac, x['acc']) / len(ac) if x['acc'] is not None and ac else None
        x['px'] = 30 * x['mp'] + 20 * max(0, min(1, (x['ratio'] - .6) / .4)) + (15 if x['trend'] else 0)
    cut = sorted(x['px'] for x in v)[int(len(v) * .8)]
    for x in v: x['top'] = x['px'] >= cut
    breadth[t] = sum(1 for x in v if x['trend']) / len(v)
G = {
 'Notre partie cours : 20 % mieux notés': lambda x: x['top'],
 'Trend Template de Minervini': lambda x: x['tmpl'],
 'Les deux': lambda x: x['top'] and x['tmpl'],
 'Accumulation : tiers fort (volume des semaines de hausse)': lambda x: x['ap'] is not None and x['ap'] >= 2/3,
 'Distribution : tiers faible': lambda x: x['ap'] is not None and x['ap'] < 1/3,
 'Notre top 20 % ET accumulation forte': lambda x: x['top'] and x['ap'] is not None and x['ap'] >= 2/3,
 'Notre top 20 % SANS accumulation (tiers faible)': lambda x: x['top'] and x['ap'] is not None and x['ap'] < 1/3,
 'Volume x1,5 sur 4 semaines avec hausse': lambda x: x['surge'],
 'Croisement MM50/MM200 depuis moins de 2 mois': lambda x: x['cross'],
 'Accélération 3 mois sans tendance 12 mois': lambda x: x['rp'] >= 2/3 and x['mp'] < 2/3,
 'À moins de 15 % du plus bas annuel': lambda x: x['nearlow'],
 '40 % ou plus sous le plus haut': lambda x: x['ratio'] <= .6,
}
def run(weeks, label):
    out = []
    for h, L in H.items():
        out.append('== ' + h + ' ' + label)
        for g, f in G.items():
            diffs = []; cnt = 0; beat = 0
            for t in weeks:
                a = [x for x in obs[t] if h in x['fw']]
                if len(a) < 100: continue
                m = sum(x['fw'][h] for x in a) / len(a); s = [x['fw'][h] - m for x in a if f(x)]
                if not s: continue
                diffs.append(sum(s) / len(s)); cnt += len(s); beat += sum(1 for y in s if y > 0)
            if len(diffs) < 8: out.append(f"{g:58} trop peu"); continue
            md = sum(diffs) / len(diffs); sd = st.pstdev(diffs); tt = md / (sd / math.sqrt(len(diffs))) / math.sqrt(L)
            out.append(f"{g:58} {100*md:+5.1f} pts  bat {100*beat/cnt:3.0f}%  t≈{tt:+.1f}  ({cnt}, {len(diffs)} sem.)")
    print('\n'.join(out))
T = sorted(obs)
run(T, 'TOUTE LA PÉRIODE')
mid = dates[T[0]] + (dates[T[-1]] - dates[T[0]]) / 2
run([t for t in T if dates[t] < mid], 'PREMIÈRE MOITIÉ (avant ' + str(mid.date()) + ')')
run([t for t in T if dates[t] >= mid], 'SECONDE MOITIÉ')
bs = sorted(breadth.values()); lo, hi = bs[len(bs) // 3], bs[2 * len(bs) // 3]
print('\nPsychologie : part des sociétés en tendance haussière, tiers', round(lo, 2), round(hi, 2))
for nm, pred in [('pessimiste (peu en tendance)', lambda t: breadth[t] < lo), ('neutre', lambda t: lo <= breadth[t] <= hi), ('euphorique (beaucoup en tendance)', lambda t: breadth[t] > hi)]:
    ws = [t for t in T if pred(t)]
    for h in H:
        r = [np.mean([x['fw'][h] for x in obs[t] if h in x['fw']]) for t in ws if any(h in x['fw'] for x in obs[t])]
        print(f"  marché {nm:35} titre moyen à {h} : {100*np.mean(r):+.1f} % ({len(r)} semaines)")
    G2 = {k: G[k] for k in ['Notre partie cours : 20 % mieux notés']}
    Gs = dict(G); G.clear(); G.update(G2); run(ws, 'marché ' + nm); G.clear(); G.update(Gs)
# série de l'ampleur (pour l'affichage)
print('\nAmpleur (dernières semaines) :', [(str(dates[t].date()), round(breadth[t], 2)) for t in T[-6:]])
