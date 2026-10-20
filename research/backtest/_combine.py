"""Tout croiser à la fois : un modèle statistique (arbres de décision boostés) apprend sur 1997-2012 quelles combinaisons
d'éléments précèdent une forte hausse (+50 % ou plus en 6 mois), puis il est jugé sur 2013-2026, années jamais vues.
Question : départage-t-il les sociétés 🎯 mieux que les règles actuelles, et trouve-t-il des forts gagnants hors 🎯 ?
Résultat (20/10/2026) : dans le 🎯, tiers favorable +9,7 à +10,3 points contre +4,9 à +5,1 (deux réglages), fortes hausses 18 %
contre 7 %, chutes 8 % contre 7 %, même écart sur 2013-2019 et 2020-2026, mais t 1,9 (seuil 3) ; seul, pas mieux que le 🎯
(t 0) avec deux fois plus de chutes ; la variable qui compte le plus est la volatilité (fortes hausses et fortes baisses).
  python _combine.py       (après _vix.py, _vol.py, _highs.py, _moment.py : long.npz, v52.npy, ep.npy) ; VAR=b python _combine.py"""
import time
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
t_start = time.time()
exec(open('_vix.py').read().split("def expq")[0])  # P, mom, mp, trend, s26, fut, valid, ret, mk, m10, m40, sma, yr, dates
fin = np.isfinite
z = np.load('long.npz', allow_pickle=True); VO = z['V'].astype(float); SEC = z['sec']
def roll(A, k):  # moyenne glissante sur k semaines, au moins 80 % de valeurs
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(fin(A), 1)
    o[:, k:] = (c[:, k:] - c[:, :-k]) / k
    cnt = np.zeros_like(A); cnt[:, k:] = n[:, k:] - n[:, :-k]; o[cnt < .8 * k] = np.nan; return o
def back(k):
    o = np.full_like(P, np.nan); o[:, k:] = P[:, k:] / P[:, :-k] - 1; return o
r4, r13, r26 = back(4), back(13), back(26)
v52 = np.load('v52.npy').astype(float); ep = np.load('ep.npy').astype(float)
vx = roll(VO, 10) / roll(VO, 52)
ext10, ext40 = P / m10 - 1, P / m40 - 1
hi = np.full_like(P, np.nan)
for t in range(52, T): hi[:, t] = P[:, t] / np.nanmax(P[:, t-51:t+1], 1)
L = np.log(P); x = np.arange(26) - 12.5; R2 = np.full_like(P, np.nan)
for t in range(25, T):
    y = L[:, t-25:t+1]; ym = y.mean(1, keepdims=True); b = ((y - ym) * x).sum(1) / (x * x).sum()
    res = y - ym - b[:, None] * x; R2[:, t] = 1 - (res ** 2).sum(1) / ((y - ym) ** 2).sum(1)
MAX = np.full_like(P, np.nan)
for t in range(13, T): MAX[:, t] = np.nanmax(ret[:, t-12:t+1], 1)
pos = np.where(fin(ret), (ret > 0).astype(float), np.nan); neg = np.where(fin(ret), (ret < 0).astype(float), np.nan)
ID = np.sign(mom) * (roll(neg, 48) - roll(pos, 48))  # « grenouille » (petits pas réguliers = bas)
BETA = np.full_like(P, np.nan)
for t in range(52, T):
    R1 = ret[:, t-51:t+1]; M = mk[t-51:t+1]; Mc = M - np.nanmean(M); Rc = R1 - np.nanmean(R1, 1, keepdims=True)
    BETA[:, t] = np.nansum(Rc * Mc, 1) / np.nansum(Mc ** 2)
g = np.where(ret > 0, ret, 0); l_ = np.where(ret < 0, -ret, 0)
rsi = 100 - 100 / (1 + roll(g, 14) / np.where(roll(l_, 14) > 0, roll(l_, 14), np.nan))
size = np.log(np.maximum(roll(P * VO, 52), 1))  # montant échangé (taille et liquidité)
# marché : hausse sur un an, au-dessus de sa moyenne 40 semaines, agitation
cm = np.cumprod(1 + np.nan_to_num(mk)); m52 = np.full(T, np.nan); m52[52:] = cm[52:] / cm[:-52] - 1
mtr = np.full(T, np.nan); mtr[40:] = [cm[t] / cm[t-39:t+1].mean() - 1 for t in range(40, T)]
mvol = np.array([np.nanstd(mk[t-12:t+1]) * np.sqrt(52) if t >= 12 else np.nan for t in range(T)])
# secteur : rang de la hausse moyenne de son secteur
secm = np.full_like(P, np.nan); secs = [s for s in set(SEC.tolist()) if s]
for t in range(T):
    ok = valid[:, t]
    if ok.sum() < 30: continue
    vals = {s: np.nanmean(mom[ok & (SEC == s), t]) for s in secs if (ok & (SEC == s)).sum() >= 3}
    if len(vals) < 4: continue
    order = sorted(vals, key=vals.get); rk = {s: i / (len(order) - 1) for i, s in enumerate(order)}
    for s, r in rk.items(): secm[ok & (SEC == s), t] = r
mon = np.array([int(d[5:7]) for d in dates], dtype=float)
F = {'hausse 12 mois (rang)': mp, 'hausse 12 mois': mom, 'pente 6 mois': s26, 'régularité (R²)': R2, 'volatilité 1 an': v52,
     'volumes ×': vx, 'nouveaux plus hauts': ep, 'écart moy. 10 sem.': ext10, 'écart moy. 40 sem.': ext40, 'distance au plus haut': hi,
     'hausse 1 mois': r4, 'hausse 3 mois': r13, 'hausse 6 mois': r26, 'plus forte semaine (3 mois)': MAX, 'grenouille': ID,
     'bêta': BETA, 'RSI 14 sem.': rsi, 'taille (échanges)': size, 'tendance de fond': trend.astype(float),
     'secteur (rang)': secm, 'marché 1 an': np.broadcast_to(m52, P.shape), 'marché / moy. 40 sem.': np.broadcast_to(mtr, P.shape),
     'agitation du marché': np.broadcast_to(mvol, P.shape), 'mois': np.broadcast_to(mon, P.shape)}
names = list(F)
print(f'variables calculées en {time.time() - t_start:.0f} s')
big = fut >= .5
t13 = int(np.searchsorted(yr, 2013)); t0 = int(np.argmax(valid.sum(0) > 30))
def rows(ts):
    idx = [(i, t) for t in ts for i in np.where(valid[:, t])[0]]
    I = np.array([a for a, _ in idx]); Tt = np.array([b for _, b in idx])
    X = np.stack([np.asarray(F[k])[I, Tt] for k in names], 1).astype('float32')
    return X, big[I, Tt], I, Tt
tr = list(range(t0 + 52, t13 - 26, 4))  # apprentissage 1997-2012, une semaine sur 4, sans chevauchement avec le test
X, y, _, _ = rows(tr)
print('apprentissage :', X.shape, 'part des fortes hausses %.1f %%' % (y.mean() * 100))
import os  # VAR=b : réglage plus prudent (contrôle de robustesse)
VAR = os.environ.get('VAR', 'a')
clf = HistGradientBoostingClassifier(max_iter=400 if VAR == 'a' else 250, learning_rate=.04 if VAR == 'a' else .03, max_depth=4 if VAR == 'a' else 3, min_samples_leaf=300 if VAR == 'a' else 800, l2_regularization=1.0 if VAR == 'a' else 3.0,
                                     early_stopping=True, validation_fraction=.15, random_state=7 if VAR == 'a' else 11)
clf.fit(X, y)
# score sur toutes les semaines 2013-2026 (jamais vues)
S = np.full_like(P, np.nan)
for t in range(t13, T - 26):
    ok = np.where(valid[:, t])[0]
    if len(ok): S[ok, t] = clf.predict_proba(np.stack([np.asarray(F[k])[ok, t] for k in names], 1).astype('float32'))[:, 1]
te = fin(S); print('AUC 2013-2026 (toutes les sociétés) : modèle %.3f · hausse 12 mois seule %.3f · volatilité seule %.3f' % (
    roc_auc_score(big[te], S[te]), roc_auc_score(big[te], np.nan_to_num(mom[te])), roc_auc_score(big[te], np.nan_to_num(v52[te]))))
# règles actuelles (🎯 : chiffres_cles.py)
RULE = valid & (mp >= 2/3) & trend & (s26 >= .41) & (mom >= .6) & (mom <= 2) & ~(v52 >= .8) & ~(ext10 < 0)
def stats(M, a=t13, b=T - 26, step=1):
    ex, n, bg, cr, bl = [], 0, 0, 0, []
    for t in range(a, b, step):
        ok = valid[:, t]; m = M[:, t] & ok
        if ok.sum() < 30 or not m.any(): continue
        f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
        e = np.nanmean(f[m]) - np.nanmean(f[ok]); ex.append(e); n += m.sum(); bg += big[m, t].sum(); cr += (fut[m, t] <= -.25).sum()
    return np.mean(ex) * 100 if ex else np.nan, bg / max(n, 1) * 100, cr / max(n, 1) * 100, n
def tstat(M1, M0, a=t13, b=T - 26):  # écart d'excès par cohorte, une cohorte tous les 6 mois (périodes sans chevauchement)
    blocks = []
    for s0 in range(0, 26, 13):
        for t in range(a + s0, b, 26):
            e1, e0 = stats(M1, t, t + 1)[0], stats(M0, t, t + 1)[0]
            if fin(e1) and fin(e0): blocks.append(e1 - e0)
    blocks = np.array(blocks)
    return blocks.mean() / (blocks.std(ddof=1) / np.sqrt(len(blocks) / 2)) if len(blocks) > 3 else np.nan  # deux séries décalées : n/2 indépendantes
def line(lab, M, a=t13, b=T - 26):
    e, bg, cr, n = stats(M, a, b); print(f'  {lab:52s} excès {e:+5.1f} pts · ≥ +50 % : {bg:4.1f} % · chutes ≤ −25 % : {cr:4.1f} % · {n} cas')
# 1. dans le 🎯 : tiers du score du modèle (seuils de chaque semaine parmi les 🎯)
lo_, mid_, hi_ = np.zeros_like(RULE), np.zeros_like(RULE), np.zeros_like(RULE)
for t in range(t13, T - 26):
    m = RULE[:, t] & fin(S[:, t])
    if m.sum() >= 3:
        q1, q2 = np.nanpercentile(S[m, t], [33.3, 66.7]); lo_[:, t] = m & (S[:, t] < q1); mid_[:, t] = m & (S[:, t] >= q1) & (S[:, t] < q2); hi_[:, t] = m & (S[:, t] >= q2)
print('\n1. Sociétés 🎯 (règles actuelles), 2013-2026, départagées par le modèle')
line('🎯 toutes', RULE); line('  tiers du modèle le plus favorable', hi_); line('  tiers moyen', mid_); line('  tiers le moins favorable', lo_)
for lab, a, b in [('2013-2019', t13, int(np.searchsorted(yr, 2020))), ('2020-2026', int(np.searchsorted(yr, 2020)), T - 26)]:
    e1, e0 = stats(hi_, a, b)[0], stats(lo_, a, b)[0]; print(f'    {lab} : tiers favorable − défavorable {e1 - e0:+5.1f} pts')
print('    t (périodes de 6 mois sans chevauchement) : %.1f' % tstat(hi_, lo_))
# 1b. la même chose avec la seule volatilité (sans modèle) : le modèle fait-il mieux que « prendre les plus agitées » ?
vlo, vmid, vhi = np.zeros_like(RULE), np.zeros_like(RULE), np.zeros_like(RULE)
for t in range(t13, T - 26):
    m = RULE[:, t] & fin(v52[:, t])
    if m.sum() >= 3:
        q1, q2 = np.nanpercentile(v52[m, t], [33.3, 66.7]); vlo[:, t] = m & (v52[:, t] < q1); vmid[:, t] = m & (v52[:, t] >= q1) & (v52[:, t] < q2); vhi[:, t] = m & (v52[:, t] >= q2)
print('\n1b. Sociétés 🎯, 2013-2026, départagées par la seule volatilité sur un an')
line('  tiers le plus agité', vhi); line('  tiers moyen', vmid); line('  tiers le plus calme', vlo)
print('    t (agité − calme) : %.1f' % tstat(vhi, vlo))
# 2. le modèle seul, sans les règles : les 10 et les 30 mieux notés chaque semaine parmi les sociétés liquides
liq = size >= np.nanpercentile(size[valid], 30)
for k in (10, 30):
    top = np.zeros_like(RULE)
    for t in range(t13, T - 26):
        m = valid[:, t] & liq[:, t] & fin(S[:, t])
        if m.sum() > k: top[np.where(m)[0][np.argsort(-S[m, t])[:k]], t] = True
    print(f'\n2. Modèle seul : {k} sociétés liquides les mieux notées chaque semaine')
    line(f'  {k} mieux notées', top)
    print('    t face au 🎯 : %.1f' % tstat(top, RULE))
# 3. ce qui compte pour le modèle (importance par permutation sur 2013-2026, échantillon)
from sklearn.inspection import permutation_importance
rng = np.random.default_rng(1); ts = list(range(t13, T - 26, 8))
Xt, yt, _, _ = rows(ts); sel = rng.choice(len(yt), min(60000, len(yt)), replace=False)
pi = permutation_importance(clf, Xt[sel], yt[sel], scoring='roc_auc', n_repeats=3, random_state=3)
order = np.argsort(-pi.importances_mean)
print('\n3. Ce qui compte pour le modèle (perte d\'AUC si la variable est brouillée, 2013-2026)')
for i in order[:12]: print(f'  {names[i]:30s} {pi.importances_mean[i]:.3f}')
print(f'\ndurée totale {time.time() - t_start:.0f} s')
