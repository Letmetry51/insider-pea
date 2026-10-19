"""Secteur émergent (définition de l'onglet Secteurs, par industrie) × volumes en hausse (🔊) : anticipe-t-il les hausses ? 1997-2026."""
import numpy as np, json, collections
src = open('_timing4.py').read(); exec(src.split("print('référence')")[0])
cols = [str(c) for c in z['cols']]
cat = json.load(open('../../data/sectors/catalog.json'))['items']; uni = json.load(open('../../data/sectors/universe.json'))['items']
ind = {}
for srcd in (cat, uni):
    for s_, it in srcd.items():
        if it.get('industry'): ind[s_] = it['industry']
secs = [str(x) for x in z['sec']]
cnt = collections.Counter(ind.get(c) for c in cols)
gname = [(ind.get(c) if ind.get(c) and cnt[ind.get(c)] >= 4 else 'Autres : ' + secs[i]) for i, c in enumerate(cols)]
G = sorted(set(gname)); gi = np.array([G.index(g) for g in gname]); NG = len(G)
mc = np.cumprod(1 + np.nan_to_num(mk))
def lagr(k, lag=0):
    o = np.full_like(P, np.nan); o[:, k:] = P[:, k - lag:T - lag] / P[:, :T - k] - 1 if lag == 0 else np.nan
    if lag: o[:, k:] = P[:, k - lag:T - lag] / P[:, :T - k] - 1
    return o
rs6s = lagr(30, 4); rs3s = lagr(13)
b6 = np.full(T, np.nan); b6[30:] = mc[26:T - 4] / mc[:T - 30] - 1
b3 = np.full(T, np.nan); b3[13:] = mc[13:] / mc[:-13] - 1
above = np.where(np.isfinite(m40), (P > m40).astype(float), np.nan); near = np.where(np.isfinite(ratio), (ratio >= .95).astype(float), np.nan)
ok = valid
gm = {k: np.full((NG, T), np.nan) for k in ('rs6', 'rs3', 'br', 'hi', 'n')}
for g in range(NG):
    M = gi == g
    A = np.where(ok[M], rs6s[M], np.nan); n = np.isfinite(A).sum(0)
    with np.errstate(all='ignore'):
        gm['rs6'][g] = np.nanmedian(A, 0) - b6; gm['rs3'][g] = np.nanmedian(np.where(ok[M], rs3s[M], np.nan), 0) - b3
        gm['br'][g] = np.nanmean(np.where(ok[M], above[M], np.nan), 0); gm['hi'][g] = np.nanmean(np.where(ok[M], near[M], np.nan), 0)
    gm['n'][g] = n
for k in ('rs6', 'rs3', 'br', 'hi'): gm[k][gm['n'] < 3] = np.nan
def prank(X):
    o = np.full_like(X, np.nan)
    for t in range(T):
        f = np.isfinite(X[:, t])
        if f.sum() >= 5: o[f, t] = (X[f, t].argsort().argsort() + 1) / f.sum()
    return o
comp = (prank(gm['rs6']) + prank(gm['rs3']) + prank(gm['br']) + prank(gm['hi'])) / 4
rank = np.full_like(comp, np.nan)
for t in range(T):
    f = np.isfinite(comp[:, t])
    if f.sum() >= 5: rank[f, t] = (-comp[f, t]).argsort().argsort() + 1
ng = np.isfinite(comp).sum(0)
emg = np.zeros((NG, T), bool); trd = np.zeros((NG, T), bool)
for t in range(8, T):
    if ng[t] < 10: continue
    gain = rank[:, t - 8] - rank[:, t]
    emg[:, t] = np.nan_to_num(gain, nan=-99) >= max(5, ng[t] // 6)
    emg[:, t] &= np.nan_to_num(gm['rs3'][:, t], nan=-1) > 0
    k = max(1, round(ng[t] * .2))
    trd[:, t] = (np.nan_to_num(rank[:, t], nan=999) <= k) & (np.nan_to_num(gm['rs6'][:, t], nan=-1) > 0) & (np.nan_to_num(gm['br'][:, t], nan=0) >= .5)
E_ = emg[gi]; TR = trd[gi] & ~E_
print('groupes :', NG, '· part des semaines-sociétés en secteur émergent : %.0f %%' % (E_[valid].mean() * 100), '· en tendance : %.0f %%' % (TR[valid].mean() * 100))
hot = vx >= 1.5
Q = Qs
def row4(lab, M):
    r = st(M); per = '  '.join(f"{l} {st(M, x, y)[0]:+5.1f}" for l, x, y in E3)
    print(f"  {lab:50s} {r[0]:+6.1f} pts  chutes {r[1]:4.1f} %  n={int(M.sum()):7d} | {per}")
print('\n== Toutes les sociétés (écart à 6 mois contre la moyenne)')
row4('secteur émergent', valid & E_); row4('secteur en tendance (pas émergent)', valid & TR); row4('autres secteurs', valid & ~E_ & ~TR)
row4('🔊 volumes, secteur émergent', valid & hot & E_); row4('🔊 volumes, autres secteurs', valid & hot & ~E_)
print('\n== Anticiper : pas encore dans le 🎯, 🔊 volumes en hausse, cours en tendance')
pre = valid & ~Qs & hot & trend
row4('🔊 + tendance, secteur émergent', pre & E_); row4('🔊 + tendance, secteur en tendance', pre & TR); row4('🔊 + tendance, autres secteurs', pre & ~E_ & ~TR)
print('\n== Dans le 🎯 (au-dessus de la moyenne 10 semaines)')
row4('🎯 référence', Qs); row4('🎯 secteur émergent', Qs & E_); row4('🎯 secteur en tendance', Qs & TR); row4('🎯 autres secteurs', Qs & ~E_ & ~TR)
row4('🎯 🔊 + secteur émergent', Qs & hot & E_); row4('🎯 🔊, autres secteurs', Qs & hot & ~E_)
