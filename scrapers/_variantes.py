"""Variantes de pondération de la partie « cours » de la note, testées sur deux échantillons (5 ans toutes sociétés, 8 ans > 500 M€)."""
import json, glob, math, statistics as st, collections, bisect, sys, os
import numpy as np
def load_cat():
    ser = {}; dates = None
    for f in glob.glob('data/societes/*.json'):
        s = json.load(open(f)); dates = s['wDates']
        for k, x in s['items'].items():
            w = x.get('w') or []
            if len(w) == len(dates): ser[k] = [v if v else np.nan for v in w]
    return dates, ser
def load_8y():
    import pandas as pd
    W = pd.read_csv('data/sectors/weekly.csv.gz', index_col=0, parse_dates=True, compression='gzip').sort_index()
    uni = json.load(open('data/sectors/universe.json'))['items']
    cols = [c for c in W.columns if c in uni and W[c].notna().sum() >= 120]
    return [str(d.date()) for d in W.index], {c: list(W[c].values) for c in cols}
V = {'actuel 30/20/15/10': (30, 20, 15, 10), 'proposé 45/10/15/5': (45, 10, 15, 5), '50/10/15/0': (50, 10, 15, 0),
     '60/0/15/0': (60, 0, 15, 0), 'force seule 75/0/0/0': (75, 0, 0, 0), '45/10/10/10': (45, 10, 10, 10)}
def run(dates, ser, label):
    n = len(dates); H = {'3m': 13, '6m': 26}; obs = collections.defaultdict(list)
    for k, p in ser.items():
        p = np.array(p, dtype=float)
        for t in range(56, n - 1):
            c = p[t]
            if not (c > 0 and p[t-4] > 0 and p[t-52] > 0): continue
            win = p[t-51:t+1]; win = win[win > 0]
            if len(win) < 45: continue
            m10 = np.nanmean(p[t-9:t+1]); m40 = np.nanmean(p[t-39:t+1])
            r = p[t-25:t+1] / p[t-26:t] - 1; r = r[np.isfinite(r)]
            fw = {h: max(-.6, min(1.5, p[t+L] / c - 1)) for h, L in H.items() if t + L < n and p[t+L] > 0}
            obs[t].append((p[t-4] / p[t-52] - 1, c / win.max(), 1 if (m10 > m40 and c > m40) else (1/3 if c > m40 else 0), np.std(r) if len(r) > 15 else np.nan, fw))
    res = {v: {h: [] for h in H} for v in V}
    halves = {v: {h: [[], []] for h in H} for v in V}
    T = sorted(obs); mid = T[len(T) // 2]
    for t in T:
        a = obs[t]
        if len(a) < 100: continue
        ms = sorted(x[0] for x in a); vs = sorted(x[3] for x in a if np.isfinite(x[3]))
        feats = []
        for x in a:
            mp = bisect.bisect_left(ms, x[0]) / len(ms); vp = bisect.bisect_left(vs, x[3]) / len(vs) if np.isfinite(x[3]) else .5
            hp = max(0, min(1, (x[1] - .6) / .4)); cp = 1 if vp < 1/3 else .5 if vp < 2/3 else 0
            feats.append((mp, hp, x[2], cp, x[4]))
        for v, (wm, wh, wt, wc) in V.items():
            sc = [wm * f[0] + wh * f[1] + wt * f[2] + wc * f[3] for f in feats]
            cut = sorted(sc)[int(len(sc) * .8)]
            for h in H:
                al = [f[4][h] for f in feats if h in f[4]]
                if len(al) < 100: continue
                m = np.mean(al); g = [f[4][h] - m for f, s in zip(feats, sc) if s >= cut and h in f[4]]
                if g:
                    res[v][h].append(np.mean(g)); halves[v][h][0 if t < mid else 1].append(np.mean(g))
    print('==', label, n, 'semaines', len(ser), 'sociétés')
    for v in V:
        line = f'{v:22}'
        for h, L in H.items():
            d = res[v][h]; md = np.mean(d); t_ = md / (np.std(d) / math.sqrt(len(d))) / math.sqrt(L)
            line += f' | {h} {100*md:+5.2f} t{t_:+.1f} [1re moitié {100*np.mean(halves[v][h][0]):+.1f} / 2e {100*np.mean(halves[v][h][1]):+.1f}]'
        print(line)
run(*load_cat(), '5 ans, toutes sociétés cotées')
if os.path.exists('data/sectors/weekly.csv.gz'): run(*load_8y(), '8 ans, plus de 500 M€')
