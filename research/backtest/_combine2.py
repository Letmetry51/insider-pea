"""Améliorer l'apprentissage du modèle « tout croiser » sans tricher avec les années de test.

Variantes décidées à l'avance (20/10/2026), choisies sur 1997-2012 seulement : apprentissage 1997-2006, validation 2007-2012
(26 semaines d'écart). La variante retenue est ensuite jugée une seule fois sur 2013-2026, années jamais vues.
  A  référence : cible « +50 % en 6 mois », toutes les sociétés, éléments bruts (premier test)
  B  éléments classés semaine par semaine (rang parmi les sociétés : moins sensible aux époques agitées ou calmes)
  C  B + cible relative : faire partie des 10 % meilleures de la semaine sur 6 mois (et non +50 %, qui dépend du marché)
  D  C + sans chute en route : jamais −25 % pendant les 6 mois
  E  D, appris seulement sur les sociétés en tendance (tiers haut sur 12 mois, tendance de fond) : comme le 🎯
Puis, avec la variante retenue : réapprentissage chaque année sur tout le passé (comme en usage réel), moyenne de 5 modèles.
Jugement pratique : chaque semaine, choisir 5 sociétés 🎯 avec le modèle ou avec la priorité actuelle (volumes, 2 par secteur).
Résultat (20/10/2026) : C retenue en validation (écart +4,4, les autres de 0 à +1,6) ; sur 2013-2026, tiers favorable +9,2 points contre
+4,7 (réappris chaque année), fortes hausses 17 % contre 6 %, chutes 7,8 % contre 6,5 %, t 2,6 (2,4 sans réapprentissage) ;
mais pour les 5 sociétés de la semaine, +9,4 points contre +9,6 avec la priorité aux volumes (t 0,3) : rien de plus en pratique.
  python _combine2.py      (après _combine.py : mêmes données)"""
import time
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
t_start = time.time()
src = open('_combine.py').read()
exec(src[src.index('import time'):src.index('big = fut >= .5')])  # mêmes 24 éléments que le premier test (F, names, …)
t0 = int(np.argmax(valid.sum(0) > 30)); t07, t13 = int(np.searchsorted(yr, 2007)), int(np.searchsorted(yr, 2013)); TE = T - 26
# cibles
big = fut >= .5
exr = np.full_like(P, np.nan)  # rang du rendement à 6 mois dans la semaine
for t in range(T - 26):
    ok = valid[:, t] & fin(fut[:, t])
    if ok.sum() > 30: exr[ok, t] = fut[ok, t].argsort().argsort() / (ok.sum() - 1)
mdd = np.full_like(P, np.nan)  # pire point des 6 mois suivants
for t in range(T - 26): mdd[:, t] = np.nanmin(P[:, t+1:t+27], 1) / P[:, t] - 1
top = exr >= .9
clean = top & (mdd > -.25)
MARKET = {'marché 1 an', 'marché / moy. 40 sem.', 'agitation du marché', 'mois'}
RK = {}
def ranked(k):  # rang de l'élément parmi les sociétés de la semaine (les éléments de marché restent bruts)
    if k in MARKET: return np.asarray(F[k])
    if k not in RK:
        A = np.asarray(F[k]); o = np.full_like(P, np.nan)
        for t in range(T):
            ok = valid[:, t] & fin(A[:, t])
            if ok.sum() > 30: o[ok, t] = A[ok, t].argsort().argsort() / (ok.sum() - 1)
        RK[k] = o
    return RK[k]
CAND = valid & (mp >= 2/3) & trend
RULE = valid & (mp >= 2/3) & trend & (s26 >= .41) & (mom >= .6) & (mom <= 2) & ~(v52 >= .8) & ~(ext10 < 0)
VAR = {'A': dict(rank=False, y=big, pop=valid), 'B': dict(rank=True, y=big, pop=valid), 'C': dict(rank=True, y=top, pop=valid),
       'D': dict(rank=True, y=clean, pop=valid), 'E': dict(rank=True, y=clean, pop=CAND)}
def feats(cfg, I, Tt):
    return np.stack([(ranked(k) if cfg['rank'] else np.asarray(F[k]))[I, Tt] for k in names], 1).astype('float32')
def fit(cfg, a, b, seed=7, step=4):
    I, Tt = np.nonzero(cfg['pop'][:, a:b:step]); Tt = Tt * step + a
    y = cfg['y'][I, Tt]
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=.04, max_depth=4, min_samples_leaf=300, l2_regularization=1.0,
                                       early_stopping=True, validation_fraction=.15, random_state=seed)
    return m.fit(feats(cfg, I, Tt), y)
def score(models, cfg, a, b, S=None):
    S = np.full_like(P, np.nan) if S is None else S
    for t in range(a, b):
        ok = np.where(valid[:, t])[0]
        if len(ok):
            X = feats(cfg, ok, np.full(len(ok), t)); S[ok, t] = np.mean([m.predict_proba(X)[:, 1] for m in models], 0)
    return S
def stats(M, a, b, step=1):
    ex, n, bg, cr = [], 0, 0, 0
    for t in range(a, b, step):
        ok = valid[:, t]; m = M[:, t] & ok
        if ok.sum() < 30 or not m.any(): continue
        f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
        ex.append(np.nanmean(f[m]) - np.nanmean(f[ok])); n += m.sum(); bg += big[m, t].sum(); cr += (fut[m, t] <= -.25).sum()
    return (np.mean(ex) * 100 if ex else np.nan), bg / max(n, 1) * 100, cr / max(n, 1) * 100, n
def tstat(M1, M0, a, b):
    d = []
    for s0 in (0, 13):
        for t in range(a + s0, b, 26):
            e1, e0 = stats(M1, t, t + 1)[0], stats(M0, t, t + 1)[0]
            if fin(e1) and fin(e0): d.append(e1 - e0)
    d = np.array(d); return d.mean() / (d.std(ddof=1) / np.sqrt(len(d) / 2)) if len(d) > 3 else np.nan
def terciles(S, a, b):
    lo, hi = np.zeros_like(RULE), np.zeros_like(RULE)
    for t in range(a, b):
        m = RULE[:, t] & fin(S[:, t])
        if m.sum() >= 3:
            q1, q2 = np.nanpercentile(S[m, t], [33.3, 66.7]); lo[:, t] = m & (S[:, t] < q1); hi[:, t] = m & (S[:, t] >= q2)
    return hi, lo
def pick5(key, a, b):  # 5 sociétés 🎯 par semaine, 2 par secteur au plus, dans l'ordre de la clé
    M = np.zeros_like(RULE)
    for t in range(a, b):
        c = np.where(RULE[:, t] & fin(key[:, t]))[0]
        n_ = {}
        for i in c[np.argsort(-key[c, t])]:
            s = SEC[i]
            if n_.get(s, 0) >= 2: continue
            n_[s] = n_.get(s, 0) + 1; M[i, t] = True
            if M[:, t].sum() >= 5: break
    return M
def line(lab, M, a, b):
    e, bg, cr, n = stats(M, a, b); print(f'  {lab:46s} excès {e:+5.1f} pts · ≥ +50 % : {bg:4.1f} % · chutes : {cr:4.1f} % · {n} cas')
# 1. choix de la variante sur 1997-2012 seulement
print('1. Validation 2007-2012 (apprentissage 1997-2006) : sociétés 🎯 départagées par chaque variante')
val = {}
for k, cfg in VAR.items():
    m = fit(cfg, t0 + 52, t07 - 26); S = score([m], cfg, t07, t13 - 26); hi, lo = terciles(S, t07, t13 - 26)
    e1, b1, c1, _ = stats(hi, t07, t13 - 26); e0, b0, c0, _ = stats(lo, t07, t13 - 26)
    val[k] = e1 - e0
    print(f'  {k} : tiers favorable {e1:+5.1f} pts ({b1:.0f} % de fortes hausses, {c1:.0f} % de chutes) · défavorable {e0:+5.1f} ({b0:.0f} %, {c0:.0f} %)'
          f' · écart {e1 - e0:+5.1f} · t {tstat(hi, lo, t07, t13 - 26):.1f}')
best = max(val, key=val.get); print(f'  → variante retenue : {best}  ({time.time() - t_start:.0f} s)')
# 2. jugement unique sur 2013-2026 : modèle appris sur 1997-2012 (comme le premier test) et réappris chaque année
cfg = VAR[best]
S_fixed = score([fit(cfg, t0 + 52, t13 - 26, seed=s) for s in (7, 11, 13, 17, 19)], cfg, t13, TE)
S_wf = np.full_like(P, np.nan)
for y_ in range(2013, int(yr[TE - 1]) + 1):
    a, b = int(np.searchsorted(yr, y_)), min(int(np.searchsorted(yr, y_ + 1)), TE)
    if a >= b: continue
    S_wf = score([fit(cfg, t0 + 52, a - 26, seed=s) for s in (7, 11, 13)], cfg, a, b, S_wf)
print(f'\n2. Jugement sur 2013-2026, années jamais vues (variante {best}, {time.time() - t_start:.0f} s)')
line('🎯 toutes', RULE, t13, TE)
for lab, S in [('appris sur 1997-2012, 5 modèles', S_fixed), ('réappris chaque année, 3 modèles', S_wf)]:
    hi, lo = terciles(S, t13, TE)
    print(f'  {lab} :'); line('    tiers favorable', hi, t13, TE); line('    tiers défavorable', lo, t13, TE)
    i20 = int(np.searchsorted(yr, 2020))
    print(f'    écart 2013-2019 {stats(hi, t13, i20)[0] - stats(lo, t13, i20)[0]:+5.1f} · 2020-2026 {stats(hi, i20, TE)[0] - stats(lo, i20, TE)[0]:+5.1f}'
          f' · t {tstat(hi, lo, t13, TE):.1f}')
# 3. usage réel : les 5 sociétés 🎯 de la semaine, choisies par le modèle ou par la priorité actuelle (volumes, 2 par secteur)
print('\n3. Cinq sociétés 🎯 par semaine (2 par secteur au plus), 2013-2026')
cur = pick5(np.where(fin(vx), vx, 0) + 0.0, t13, TE)
mod = pick5(np.where(fin(S_wf), S_wf, -1), t13, TE)
line('priorité actuelle (volumes en hausse)', cur, t13, TE); line('modèle réappris chaque année', mod, t13, TE)
print(f'  t (modèle − priorité actuelle) : {tstat(mod, cur, t13, TE):.1f}')
print(f'\ndurée totale {time.time() - t_start:.0f} s')
