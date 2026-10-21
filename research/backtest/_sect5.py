"""Filtre « secteur en tendance ou émergent » sur les 5 sociétés 🎯 de la semaine (question du 21/10/2026).

Secteurs : définitions de l'onglet Secteurs (scrapers/sectors.py, groupes par industrie), reconstituées semaine par semaine
avec les seuls cours connus à la date (comme _emerg.py). 🌱 émergent : au moins max(5, groupes/6) places gagnées en 8 semaines
et plus fort que le marché sur 3 mois ; 📈 en tendance : 20 % premiers, plus fort que le marché sur 6 mois, moitié des sociétés
au-dessus de leur moyenne 40 semaines.
Sélection de la semaine comme aujourd'hui (ES.pickThree) : règles 🎯 (+ pente moyenne ou +30 à +60 % repêchées par un 📣),
🔊 volumes en hausse puis 📣 bond d'abord, 2 sociétés par secteur, 5 au plus. Variantes décidées à l'avance :
  B  seulement les sociétés d'un secteur en tendance ou émergent (filtre strict : parfois moins de 5, parfois aucune)
  C  secteurs en tendance ou émergents d'abord, puis les autres pour compléter à 5
  D  en tendance seulement (strict)      E  émergent seulement (strict)
  F  contrôle ajouté après coup : le secteur comme simple départage, après 🔊 et 📣
Mesure commune : écart de rendement à 6 mois avec la société moyenne de la même semaine (moyenne des semaines où la sélection
n'est pas vide), part des fortes hausses (≥ +50 %) et des chutes (≤ −25 %) ; 1997-2012 et 2013-2026 ;
t sur des périodes de 6 mois sans chevauchement (deux séries décalées de 3 mois, n/2 indépendantes).
Résultat (21/10/2026) : rien de plus, et même moins bien. Dans le 🎯, secteur en tendance ou émergent +6,1 points (1997-2012)
et +6,5 (2013-2026) contre +10,5 et +7,1 pour les autres secteurs. Les 5 sociétés de la semaine : aujourd'hui +11,0 et +10,5 ;
filtre strict (B) +7,2 et +8,5 (t −0,2 et −1,0), fortes hausses 15 % contre 19 % sur 2013-2026, aucune société 37 % des
semaines avant 2013 (15 % aujourd'hui) ; ces secteurs d'abord (C) +10,3 et +9,0 ; en tendance seul +5,7 et +8,6 ; émergent seul +8,4 et +7,4.
Moins bien sur 2013-2019 comme sur 2020-2026 ; même conclusion en départageant par la pente plutôt que par les volumes.
Comme simple départage (F) : +11,4 et +10,6, mêmes sociétés à 89 % : aucun effet.
  python _sect5.py   (après _vix.py et _combine.py : long.npz, v52.npy, ep.npy ; data/sectors/ du site)"""
import collections
import json
import time
import warnings
import numpy as np
warnings.filterwarnings('ignore')
t_start = time.time()
src = open('_combine.py').read()
exec(src[src.index('import time'):src.index('big = fut >= .5')])  # P, valid, mp, trend, s26, mom, v52, ext10, vx, hi, SEC, fut…
big = fut >= .5
t0 = int(np.argmax(valid.sum(0) > 30)); t13, t20 = int(np.searchsorted(yr, 2013)), int(np.searchsorted(yr, 2020)); TE = T - 26
# 1. secteurs (industries), comme l'onglet Secteurs
DATA = '../../data/sectors/'
cols = [str(c) for c in z['cols']]
ind = {}
for f_ in ('catalog.json', 'universe.json'):
    for s_, it in json.load(open(DATA + f_))['items'].items():
        if it.get('industry'): ind[s_] = it['industry']
secs = [str(x) for x in z['sec']]
cnt = collections.Counter(ind.get(c) for c in cols)
gname = [(ind.get(c) if ind.get(c) and cnt[ind.get(c)] >= 4 else 'Autres : ' + secs[i]) for i, c in enumerate(cols)]
G = sorted(set(gname)); gi = np.array([G.index(g) for g in gname]); NG = len(G)
mc = np.cumprod(1 + np.nan_to_num(mk))
rs6s = np.full_like(P, np.nan); rs6s[:, 30:] = P[:, 26:T - 4] / P[:, :T - 30] - 1   # 26 semaines, sans les 4 dernières
rs3s = np.full_like(P, np.nan); rs3s[:, 13:] = P[:, 13:] / P[:, :-13] - 1
b6 = np.full(T, np.nan); b6[30:] = mc[26:T - 4] / mc[:T - 30] - 1
b3 = np.full(T, np.nan); b3[13:] = mc[13:] / mc[:-13] - 1
above = np.where(fin(m40), (P > m40).astype(float), np.nan); near = np.where(fin(hi), (hi >= .95).astype(float), np.nan)
gm = {k: np.full((NG, T), np.nan) for k in ('rs6', 'rs3', 'br', 'hi', 'n')}
for g in range(NG):
    M = gi == g
    A = np.where(valid[M], rs6s[M], np.nan)
    gm['n'][g] = fin(A).sum(0)
    gm['rs6'][g] = np.nanmedian(A, 0) - b6
    gm['rs3'][g] = np.nanmedian(np.where(valid[M], rs3s[M], np.nan), 0) - b3
    gm['br'][g] = np.nanmean(np.where(valid[M], above[M], np.nan), 0)
    gm['hi'][g] = np.nanmean(np.where(valid[M], near[M], np.nan), 0)
for k in ('rs6', 'rs3', 'br', 'hi'): gm[k][gm['n'] < 3] = np.nan
def prank(X):
    o = np.full_like(X, np.nan)
    for t in range(T):
        f = fin(X[:, t])
        if f.sum() >= 5: o[f, t] = (X[f, t].argsort().argsort() + 1) / f.sum()
    return o
comp = (prank(gm['rs6']) + prank(gm['rs3']) + prank(gm['br']) + prank(gm['hi'])) / 4
rank = np.full_like(comp, np.nan)
for t in range(T):
    f = fin(comp[:, t])
    if f.sum() >= 5: rank[f, t] = (-comp[f, t]).argsort().argsort() + 1
ng = fin(comp).sum(0)
emg = np.zeros((NG, T), bool); trd = np.zeros((NG, T), bool)
for t in range(8, T):
    if ng[t] < 10: continue
    gain = rank[:, t - 8] - rank[:, t]
    emg[:, t] = (np.nan_to_num(gain, nan=-99) >= max(5, ng[t] // 6)) & (np.nan_to_num(gm['rs3'][:, t], nan=-1) > 0)
    k = max(1, round(ng[t] * .2))
    trd[:, t] = (np.nan_to_num(rank[:, t], nan=999) <= k) & (np.nan_to_num(gm['rs6'][:, t], nan=-1) > 0) & (np.nan_to_num(gm['br'][:, t], nan=0) >= .5)
EM, TR = emg[gi], trd[gi]; HOT_S = EM | TR
print(f'groupes (industries) : {NG} · semaines-sociétés en secteur émergent {EM[valid].mean() * 100:.0f} %,'
      f' en tendance {TR[valid].mean() * 100:.0f} %, l\'un ou l\'autre {HOT_S[valid].mean() * 100:.0f} %')
# 2. sélection de la semaine comme aujourd'hui
above10 = ~(ext10 < 0)
RULE = valid & (mp >= 2/3) & trend & (s26 >= .41) & (mom >= .6) & (mom <= 2) & ~(v52 >= .8) & above10
VO2 = np.where(VO > 0, VO, np.nan)
v52b = np.full_like(P, np.nan)
for t in range(52, T): v52b[:, t] = np.nanmean(VO2[:, t - 52:t], 1)
jump = (ret >= .08) & (VO2 >= 3 * v52b)
bump = np.zeros_like(jump)
for t in range(8, T): bump[:, t] = np.any(jump[:, t - 7:t + 1], 1)
T1 = valid & (mp >= 2/3) & trend & (((s26 >= .14) & (s26 < .41) & (mom >= .6) & (mom <= 2)) | ((s26 >= .41) & (mom >= .3) & (mom < .6))) & ~(v52 >= .8) & above10
CAND = RULE | (T1 & bump)
hot = vx >= 1.5
KEY = 2 * hot + bump + np.clip(np.nan_to_num(vx), 0, 50) / 100
SECN = np.array([s or '?' for s in SEC.tolist()])
def pick5(C, K, n=5, per=2):
    M = np.zeros_like(C)
    for t in range(t0, TE):
        c = np.where(C[:, t])[0]
        if not len(c): continue
        seen, k = {}, 0
        for i in c[np.argsort(-K[c, t], kind='stable')]:
            s = SECN[i]
            if seen.get(s, 0) >= per: continue
            seen[s] = seen.get(s, 0) + 1; M[i, t] = True; k += 1
            if k >= n: break
    return M
def stats(M, a, b):
    ex, n, bg, cr, wk, wall = [], 0, 0, 0, 0, 0
    for t in range(a, b):
        ok = valid[:, t]
        if ok.sum() < 30: continue
        wall += 1; m = M[:, t] & ok
        if not m.any(): continue
        f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
        ex.append(np.nanmean(f[m]) - np.nanmean(f[ok])); n += m.sum(); bg += big[m, t].sum(); cr += (fut[m, t] <= -.25).sum(); wk += 1
    return (np.mean(ex) * 100 if ex else np.nan), bg / max(n, 1) * 100, cr / max(n, 1) * 100, n, wk / max(wall, 1) * 100, n / max(wk, 1)
def tstat(M1, M0, a, b):
    d = []
    for s0 in (0, 13):
        for t in range(a + s0, b, 26):
            e1, e0 = stats(M1, t, t + 1)[0], stats(M0, t, t + 1)[0]
            if fin(e1) and fin(e0): d.append(e1 - e0)
    d = np.array(d)
    return (d.mean() / (d.std(ddof=1) / np.sqrt(len(d) / 2)) if len(d) > 3 else np.nan), len(d) // 2
PER = [('1997-2012', t0, t13), ('2013-2026', t13, TE)]
def show(lab, M, ref=None):
    for p, a, b in PER:
        e, bg, cr, n, wk, avg = stats(M, a, b)
        tt = '' if ref is None else ' · t %+.1f (%d périodes)' % tstat(M, ref, a, b)
        print(f'  {lab:44s} {p}  excès {e:+5.1f} pts · ≥ +50 % : {bg:4.1f} % · chutes : {cr:4.1f} % · '
              f'{avg:3.1f} sociétés/sem. · semaines avec au moins une : {wk:3.0f} %{tt}')
print(f'\n1. Toutes les sociétés 🎯 de la semaine (sans limite de 5), selon leur secteur  ({time.time() - t_start:.0f} s)')
show('🎯 toutes', CAND)
show('🎯 secteur en tendance ou émergent', CAND & HOT_S, CAND & ~HOT_S)
show('🎯 autres secteurs', CAND & ~HOT_S)
show('🎯 secteur en tendance', CAND & TR); show('🎯 secteur émergent', CAND & EM)
print('\n2. Les 5 sociétés de la semaine (🔊 puis 📣 d\'abord, 2 par secteur) ; t : écart avec A')
A = pick5(CAND, KEY)
B = pick5(CAND & HOT_S, KEY)
C = pick5(CAND, KEY + 10 * HOT_S)
D = pick5(CAND & TR, KEY)
E = pick5(CAND & EM, KEY)
show('A  aujourd\'hui', A)
show('B  secteur en tendance ou émergent seulement', B, A)
show('C  ces secteurs d\'abord, puis les autres', C, A)
show('D  secteur en tendance seulement', D, A)
show('E  secteur émergent seulement', E, A)
Fd = pick5(CAND, KEY + .5 * HOT_S)
show('F  départage par le secteur, après 🔊 et 📣', Fd, A)
print('\n3. Sous-périodes 2013-2026 (écart avec A, points à 6 mois)')
for lab, M in [('B', B), ('C', C), ('F', Fd)]:
    print(f'  {lab} : ' + ' · '.join(f'{p} {stats(M, a, b)[0] - stats(A, a, b)[0]:+5.1f}'
                                      for p, a, b in [('2013-2019', t13, t20), ('2020-2026', t20, TE)]))
ov = (A & C).sum() / max(A.sum(), 1) * 100
print(f'\n  sociétés communes entre A et C : {ov:.0f} % · durée {time.time() - t_start:.0f} s')
