"""Allers-retours entre support et résistance (question de François du 13/11/2026 : « une action qui oscille de façon cyclique
entre support et résistance, l'idée serait de faire des allers-retours »). Achat près du support d'une action qui oscille dans
une fourchette depuis un an, revente près de la résistance : est-ce que ça rapporte, frais compris, et quelles actions oscillent
ainsi aujourd'hui ?

Fourchette (règle fixée avant le calcul ; les niveaux les plus proches de la page sont trop serrés pour cet usage, d'où la
fourchette de l'année) : plus bas et plus haut des clôtures des 250 dernières séances, largeur de 15 à 50 %, bas touché au moins
2 fois (points bas à moins de 3 % du plus bas, séparés d'au moins 15 séances), haut touché au moins 2 fois (points hauts à moins
de 3 % du plus haut), au moins 3 demi-cycles (passages du quart bas au quart haut de la fourchette, ou l'inverse), seuls cours
connus à chaque date.
Aller-retour : achat à l'ouverture du lendemain d'une séance en hausse qui clôture dans les 15 % du bas de la fourchette ;
revente au haut −2 % dès que le plus haut du jour l'atteint (ordre à cours limité), arrêt si une clôture passe 5 % sous le bas
(fourchette cassée, vente à l'ouverture suivante), sinon vente au bout de 125 séances. Frais : 0,6 % l'aller-retour
(courtage et écart achat-vente d'une valeur moyenne). Un seul aller-retour à la fois par action. Comparaison : la moyenne des
sociétés sur les mêmes séances, et le même aller-retour acheté au milieu de la fourchette (contrôle). Hasard : part des
allers-retours qui touchent l'objectif avant l'arrêt si le cours allait au hasard (marche au hasard sans tendance, mêmes
distances en logarithme : ln(achat / arrêt) / ln(objectif / arrêt)). Variantes (fourchette plus large, plus régulière, de 6
mois, sans arrêt) affichées pour la robustesse, pas pour choisir la meilleure.

Ordre de priorité (question de François du 13/11/2026 : « donner la liste des 67 sociétés dans l'ordre de priorité à tester ») :
les allers-retours de la règle fixée sont découpés selon ce qu'on voit au moment d'acheter (contacts, demi-cycles, largeur,
allers-retours passés sur la même action) pour voir si l'un de ces critères fait de meilleurs candidats ; la liste du jour donne,
pour chaque action, ses allers-retours passés selon la règle (nombre, objectifs atteints, gain moyen) et l'éligibilité au PEA du
catalogue.

Cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant). Lancé par « Recherche (à la demande) »
(script allers_retours.py), environ 2 minutes.
"""
import glob
import json
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT

log, shift, roll = FB.log, FB.shift, HT.roll
COST = .006


def summary(name, T_, periods):
    if not T_:
        log(f"  {name:60s} aucun aller-retour")
        return
    a = np.array([t['net'] for t in T_]) * 100
    ex = np.array([t['ex'] for t in T_]) * 100
    days = np.array([t['days'] for t in T_])
    win = np.mean([t['how'] == 'objectif' for t in T_]) * 100
    stop = np.mean([t['how'] == 'arrêt' for t in T_]) * 100
    fin = [t for t in T_ if t['how'] in ('objectif', 'arrêt') and t['prw'] is not None]
    rw = (f" | finis à l'objectif ou à l'arrêt : objectif {np.mean([t['how'] == 'objectif' for t in fin]) * 100:3.0f} %, "
          f"hasard {np.mean([t['prw'] for t in fin]) * 100:3.0f} %") if len(fin) >= 30 else ""
    mo = pd.Series(ex, index=[t['month'] for t in T_]).groupby(level=0).mean()
    tv = mo.mean() / (mo.std(ddof=1) / np.sqrt(len(mo))) if len(mo) > 2 and mo.std() > 0 else float('nan')
    per = []
    for lab, y0, y1 in periods:
        sel = [t['ex'] * 100 for t in T_ if y0 <= t['year'] <= y1]
        per.append(f"{np.mean(sel):+5.1f}" if len(sel) >= 30 else "  ·  ")
    yearly = np.mean(a) / max(np.mean(days), 1) * 252
    log(f"  {name:60s} {len(a):5d} | net {np.mean(a):+5.1f} % (médiane {np.median(a):+5.1f}) en {np.mean(days):4.0f} séances, "
        f"≈ {yearly:+5.1f} %/an investi | objectif {win:3.0f} %, arrêt {stop:3.0f} % | écart à la moyenne {np.mean(ex):+5.1f} "
        f"(t {tv:4.1f}) [{' / '.join(per)}]{rw}")


def main():
    t0 = time.time()
    names, cat = {}, {}
    for f in glob.glob('../data/societes/*.json'):
        for k, x in json.load(open(f))['items'].items():
            names[k] = x.get('name') or k
            cat[k] = x
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates = D['Close'].index
    cols = list(D['Close'].columns)
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    N, T = C.shape
    log(f"téléchargé en {time.time() - t0:.0f} s : {N} sociétés, {T} séances")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0)
        C1 = shift(C, 1)
        Hb, Lb = np.minimum(H, C * 1.5), np.maximum(L, C / 1.5)
        cmax = {W: roll(C, W, 'max', int(W * .9)) for W in (125, 250)}
        cmin = {W: roll(C, W, 'min', int(W * .9)) for W in (125, 250)}
        hmax = pd.DataFrame(Hb.T).rolling(11, center=True, min_periods=11).max().values.T
        lmin = pd.DataFrame(Lb.T).rolling(11, center=True, min_periods=11).min().values.T
        ph, pl = ok & (Hb >= hmax), ok & (Lb <= lmin)
        r1 = np.where(ok, C / C1 - 1, np.nan)
        mret = np.nanmean(np.where(np.abs(r1) < .5, r1, np.nan), 0)
        mret[np.isfinite(r1).sum(0) < 30] = np.nan
        M = np.exp(np.nancumsum(np.log1p(np.nan_to_num(mret))))   # moyenne des sociétés (indice équipondéré)
    periods = [('2000-2008', 2000, 2008), ('2009-2017', 2009, 2017), ('2018-2026', 2018, 2026)]
    RULE = 'règle fixée (1 an, largeur 15 à 50 %, 2 contacts, 3 demi-cycles)'
    base = dict(W=250, wmin=.15, touch=2, swing=3, mid=False, stop=True)
    variants = {
        RULE: base,
        'fourchette large (25 à 50 %)': {**base, 'wmin': .25},
        'plus régulière (3 contacts, 5 demi-cycles)': {**base, 'touch': 3, 'swing': 5},
        'fourchette de 6 mois (125 séances)': {**base, 'W': 125},
        'sans arrêt (objectif ou 125 séances)': {**base, 'stop': False},
        'contrôle : achat au milieu de la fourchette': {**base, 'mid': True},
    }
    trades = {k: [] for k in variants}
    now = []
    cand = {}
    with np.errstate(all='ignore'):
        for W in (125, 250):
            yr = cmax[W] / cmin[W] - 1
            pos_y = (C - cmin[W]) / (cmax[W] - cmin[W])
            pre = ok & (yr >= .15) & (yr <= .5) & (C > C1)
            cand[W, False], cand[W, True] = pre & (pos_y <= .15), pre & (pos_y >= .4) & (pos_y <= .6)
        yr = cmax[250] / cmin[250] - 1
    any_cand = np.zeros_like(ok)
    for m in cand.values():
        any_cand |= m
    # dernière séance complète (le jour du calcul peut n'être qu'à moitié coté)
    cnt = ok.sum(0)
    tl = T - 1
    now_paris = pd.Timestamp.now(tz='Europe/Paris')
    if dates[tl].date() >= now_paris.date() and now_paris.hour < 18:   # séance du jour pas encore close
        tl -= 1
    while tl > T - 10 and cnt[tl] < .6 * cnt[T - 10:].max():
        tl -= 1

    def band(i, t, W, pl_i, ph_i):
        """Fourchette des W dernières clôtures à la séance t : (bas, haut, contacts du bas, contacts du haut, demi-cycles)."""
        lo_, hi_ = float(cmin[W][i, t]), float(cmax[W][i, t])
        a = max(0, t - W + 1)
        seg = C[i, a:t + 1]
        seg = seg[np.isfinite(seg)]
        pos = (seg - lo_) / (hi_ - lo_)
        state, half = 0, 0
        for x in pos:
            if x <= .25 and state != -1:
                half += state == 1
                state = -1
            elif x >= .75 and state != 1:
                half += state == -1
                state = 1

        def touches(idx, val, test):
            k = idx[(idx >= a) & (idx <= t - 5)]
            k = k[test(val[k])]
            if not k.size:
                return 0
            return 1 + int(np.sum(np.diff(k) >= 15))
        nf = touches(pl_i, Lb[i], lambda v: v <= lo_ * 1.03)
        nc = touches(ph_i, Hb[i], lambda v: v >= hi_ * .97)
        return lo_, hi_, nf, nc, half

    t1 = time.time()
    for i in range(N):
        pl_i, ph_i = np.flatnonzero(pl[i]), np.flatnonzero(ph[i])
        if pl_i.size < 4 or ph_i.size < 4:
            continue
        busy = {k: -1 for k in variants}
        hist = []   # allers-retours passés de la règle fixée sur cette action : (fin, issue)
        for t in np.flatnonzero(any_cand[i, 260:T - 6]) + 260:
            bands = {}
            for name, v in variants.items():
                if t <= busy[name] or not cand[v['W'], v['mid']][i, t]:
                    continue
                if v['W'] not in bands:
                    bands[v['W']] = band(i, t, v['W'], pl_i, ph_i)
                lo_, hi_, nf, nc, half = bands[v['W']]
                if not (hi_ / lo_ - 1 >= v['wmin'] and nf >= v['touch'] and nc >= v['touch'] and half >= v['swing']):
                    continue
                buy = float(O[i, t + 1])
                if not buy > 0:
                    continue
                target, stop = hi_ * .98, lo_ * .95
                end = min(T - 1, t + 126)
                how, sell, u = 'durée', float(C[i, end]), end
                for u_ in range(t + 1, end + 1):
                    if Hb[i, u_] >= target:
                        # ouverture au-dessus de l'objectif : vendue à l'ouverture, sauf après un trou de cotation (l'ordre à cours
                        # limité aurait été exécuté à l'objectif pendant le trou)
                        o_ = float(O[i, u_])
                        how, sell, u = 'objectif', o_ if o_ > target and ok[i, u_ - 1] else target, u_
                        break
                    if v['stop'] and C[i, u_] < stop:
                        u = min(u_ + 1, T - 1)
                        how, sell = 'arrêt', float(O[i, u]) if np.isfinite(O[i, u]) else float(C[i, u_])
                        break
                if not (sell > 0 and np.isfinite(sell)):
                    continue
                net = sell / buy * (1 - COST) - 1
                mk = M[u] / M[t] - 1 if M[t] > 0 else 0.0
                prw = None
                if v['stop']:
                    prw = float(np.clip(np.log(buy / stop) / np.log(target / stop), 0, 1)) if target > stop else None
                rec_ = {'net': net, 'ex': net - mk, 'days': u - t, 'how': how, 'prw': prw,
                        'month': int(months[t]), 'year': int(yrs[t])}
                if name == RULE:   # ce qu'on voit au moment d'acheter (les allers-retours passés sont finis avant t)
                    p3 = [h for uu, h in hist if uu >= t - 750]
                    rec_.update(i=i, t=t, nmin=min(nf, nc), half=half, width=hi_ / lo_ - 1,
                                p3n=len(p3), p3w=sum(h == 'objectif' for h in p3),
                                pan=len(hist), paw=sum(h == 'objectif' for _, h in hist),
                                open=how == 'durée' and t + 126 > T - 1)
                    hist.append((u, how))
                trades[name].append(rec_)
                busy[name] = u
        # actions qui oscillent aujourd'hui (règle fixée) et où en est leur cours dans la fourchette
        t = tl
        if ok[i, t] and .15 <= yr[i, t] <= .5:
            lo_, hi_, nf, nc, half = band(i, t, 250, pl_i, ph_i)
            if nf >= 2 and nc >= 2 and half >= 3:
                now.append(dict(i=i, sym=cols[i], name=names.get(cols[i], cols[i]), c=float(C[i, t]), lo=lo_, nf=nf, hi=hi_,
                                nc=nc, w=hi_ / lo_ - 1, pos=(float(C[i, t]) - lo_) / (hi_ - lo_), half=half))
    log(f"allers-retours simulés en {time.time() - t1:.0f} s")
    log("\n=== Allers-retours (frais de 0,6 % compris ; écart avec la moyenne des sociétés sur les mêmes séances)")
    for name in variants:
        summary(name, trades[name], periods)
    T_ = trades[RULE]
    if T_:
        a = np.array([t['net'] for t in T_])
        log(f"  règle fixée : {len(T_) / 26.9:.0f} allers-retours par an sur toutes les sociétés ; pertes de plus de 10 % : "
            f"{np.mean(a <= -.10) * 100:.0f} % ; gains de plus de 10 % : {np.mean(a >= .10) * 100:.0f} %")
    log("\n=== Qu'est-ce qui fait un meilleur candidat ? (allers-retours de la règle fixée, découpés selon ce qu'on voit à l'achat)")
    groups = [
        ('contacts : 2 du côté le moins touché', lambda t: t['nmin'] == 2),
        ('contacts : 3 ou plus des deux côtés', lambda t: t['nmin'] >= 3),
        ('3 demi-cycles', lambda t: t['half'] == 3),
        ('4 demi-cycles', lambda t: t['half'] == 4),
        ('5 demi-cycles ou plus', lambda t: t['half'] >= 5),
        ('largeur 15 à 25 %', lambda t: t['width'] < .25),
        ('largeur 25 à 35 %', lambda t: .25 <= t['width'] < .35),
        ('largeur 35 à 50 %', lambda t: t['width'] >= .35),
        ('aucun aller-retour sur cette action dans les 3 ans', lambda t: t['p3n'] == 0),
        ("dans les 3 ans, au moins un objectif atteint", lambda t: t['p3w'] >= 1),
        ("dans les 3 ans, des allers-retours mais aucun objectif", lambda t: t['p3n'] >= 1 and t['p3w'] == 0),
        ("depuis 2000, au moins 2 objectifs atteints", lambda t: t['paw'] >= 2),
        ("depuis 2000, plus d'objectifs que d'échecs", lambda t: t['pan'] >= 2 and 2 * t['paw'] > t['pan']),
    ]
    for gname, f in groups:
        summary(gname, [t for t in T_ if f(t)], periods)

    log(f"\n=== Actions qui oscillent ({dates[tl]:%d/%m/%Y}, dernière séance complète) dans une fourchette d'un an "
        f"(règle fixée) : {len(now)}")
    by_i = {}
    for t_ in T_:
        by_i.setdefault(t_['i'], []).append(t_)
    log("LISTE;symbole;nom;pea;pays;secteur;devise;cours;support;contacts_bas;résistance;contacts_haut;largeur_%;position_%;"
        "demi_cycles;allers_retours;objectifs;arrêts;gain_moyen_%;allers_retours_3_ans;objectifs_3_ans;en_cours;échanges_jour_eur")
    for x in sorted(now, key=lambda x: x['pos']):
        h = [t_ for t_ in by_i.get(x['i'], []) if not t_['open']]
        h3 = [t_ for t_ in h if t_['t'] >= tl - 750]
        op = any(t_['open'] for t_ in by_i.get(x['i'], []))
        k = cat.get(x['sym'], {})
        gm = f"{np.mean([t_['net'] for t_ in h]) * 100:+.1f}" if h else ""
        te = k.get('turnoverEur')
        log(";".join(str(v) for v in (
            'LISTE', x['sym'], x['name'], k.get('pea'), k.get('country') or '', k.get('sector') or '', k.get('currency') or '',
            f"{x['c']:.2f}", f"{x['lo']:.2f}", x['nf'], f"{x['hi']:.2f}", x['nc'], f"{x['w'] * 100:.0f}", f"{x['pos'] * 100:.0f}",
            x['half'], len(h), sum(t_['how'] == 'objectif' for t_ in h), sum(t_['how'] == 'arrêt' for t_ in h), gm, len(h3),
            sum(t_['how'] == 'objectif' for t_ in h3), 'oui' if op else 'non', f"{te:.0f}" if te else '')))
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
