"""Allers-retours dans un canal haussier, croisés avec le momentum de l'outil (question de François du 13/11/2026 : « croiser
cette stratégie de support et résistance dans les actions qui viennent de passer en momentum achat ou dans un canal haussier »).

La fourchette plate d'allers_retours.py ne peut pas croiser le momentum : une société du 🎯 a pris au moins 60 % en un an, sa
fourchette d'un an fait donc plus de 50 % de large et sort de la règle. Le croisement se fait par un canal qui monte : support et
résistance sont deux droites parallèles qui suivent la tendance.

Canal (règle fixée avant le calcul, seuls cours connus à chaque date) : droite des moindres carrés du logarithme des clôtures des
250 dernières séances, pente d'au moins +15 %/an ; ligne basse et ligne haute parallèles à cette droite, par la clôture la plus basse
et la plus haute de la période ; canal large de 15 à 50 % ; ligne basse touchée au moins 2 fois (points bas à 3 % près, séparés
d'au moins 15 séances), ligne haute aussi ; au moins 3 demi-cycles (passages du quart bas au quart haut du canal, ou l'inverse).
Aller-retour : achat à l'ouverture du lendemain d'une séance en hausse qui clôture dans les 15 % du bas du canal ; revente à la
ligne haute −2 % (prolongée chaque jour selon la pente) dès que le plus haut du jour l'atteint, ordre à cours limité ; arrêt si une
clôture passe 5 % sous la ligne basse prolongée (vente à l'ouverture suivante) ; sinon vente au bout de 125 séances. Frais : 0,6 %
l'aller-retour. Un seul aller-retour à la fois par action.

Croisements : canal seul ; canal et tendance (cours au-dessus de la moyenne 200 séances, moyenne 50 au-dessus de la 200) ; canal
et zone du 🎯 (momentum achat : tendance, +60 à +200 % sur 12 mois sans le dernier mois) ; canal et entrée dans le 🎯 depuis moins
de 20 séances (« vient de passer en momentum achat »). Variante : canal de 6 mois. Contrôle : même aller-retour acheté au milieu
du canal. Références : le 🎯 au feu vert (au-dessus de la moyenne 50 séances) gardé 125 séances, comme l'outil, et l'entrée récente
dans le 🎯 gardée 125 séances. Pour chaque aller-retour, la même entrée gardée 125 séances dit si la revente à la ligne haute
fait mieux que de garder. Mesure : écart avec la moyenne des sociétés sur les mêmes séances, t regroupé par mois, trois périodes.

Cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant). Lancé par « Recherche (à la demande) »
(script canal_haussier.py), environ 5 minutes.
"""
import glob
import json
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
from allers_retours import summary

log, shift, roll, dedup = FB.log, FB.shift, HT.roll, FB.dedup
COST = .006
SLOPE_MIN = np.log(1.15) / 250       # pente d'au moins +15 %/an
L3 = np.log(1.03)


def rolling_line(LC, W):
    """Droite des moindres carrés de LC (log des clôtures, NaN hors séance) sur les W dernières séances : ordonnée, pente,
    écart-type des résidus (float64 : les moyennes de x² se soustraient)."""
    T = LC.shape[1]
    fin = np.isfinite(LC)
    X = np.where(fin, np.arange(T, dtype=np.float64)[None, :], np.nan)

    def r(A):
        return pd.DataFrame(A.T).rolling(W, min_periods=int(W * .9)).mean().values.T

    mx, my = r(X), r(LC)
    vx = r(X * X) - mx * mx
    cxy = r(X * LC) - mx * my
    b = cxy / vx
    a = my - b * mx
    vy = r(LC * LC) - my * my
    s = np.sqrt(np.maximum(vy - b * cxy, 0))
    return a, b, s


def main():
    t0 = time.time()
    names = {}
    for f in glob.glob('../data/societes/*.json'):
        for k, x in json.load(open(f))['items'].items():
            names[k] = x.get('name') or k
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates = D['Close'].index
    cols = list(D['Close'].columns)
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    N, T = C.shape
    log(f"téléchargé en {time.time() - t0:.0f} s : {N} sociétés, {T} séances")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0) & (C > 0)
        C1 = shift(C, 1)
        Hb, Lb = np.minimum(H, C * 1.5), np.maximum(L, C / 1.5)
        hmax = pd.DataFrame(Hb.T).rolling(11, center=True, min_periods=11).max().values.T
        lmin = pd.DataFrame(Lb.T).rolling(11, center=True, min_periods=11).min().values.T
        ph, pl = ok & (Hb >= hmax), ok & (Lb <= lmin)
        r1 = np.where(ok, C / C1 - 1, np.nan)
        mret = np.nanmean(np.where(np.abs(r1) < .5, r1, np.nan), 0)
        mret[np.isfinite(r1).sum(0) < 30] = np.nan
        M = np.exp(np.nancumsum(np.log1p(np.nan_to_num(mret))))   # moyenne des sociétés (indice équipondéré)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = ok & (C > m200) & (m50 > m200)
        mom = shift(C, 21) / shift(C, 252) - 1
        zone = trend & (mom >= .6) & (mom <= 2.0)                  # zone du 🎯 (momentum achat)
        feu = zone & (C > m50)                                     # au feu vert
        zprev = np.zeros_like(zone)
        zprev[:, 1:] = zone[:, :-1]
        new_in = zone & ~zprev
        recent = (roll(new_in.astype(np.float32), 20, 'max', 1) > 0) & zone   # entrée dans le 🎯 depuis moins de 20 séances
        LC = np.where(ok, np.log(np.where(C > 0, C, np.nan)), np.nan).astype(np.float64)
        lHb, lLb = np.log(Hb).astype(np.float64), np.log(Lb).astype(np.float64)
    t1 = time.time()
    A_, B_, cand = {}, {}, {}
    tt = np.arange(T, dtype=np.float64)[None, :]
    for W in (125, 250):
        a, b, s = rolling_line(LC, W)
        with np.errstate(all='ignore'):
            e = LC - (a + b * tt)
            pre = ok & (C > C1) & (b >= SLOPE_MIN)
            cand[W, False] = pre & (e <= -.5 * s)                 # bas du canal (filtre large, la règle exacte suit)
            cand[W, True] = pre & (np.abs(e) <= 1.0 * s)           # milieu du canal (contrôle)
        A_[W], B_[W] = a, b
        del s, e, pre
    log(f"droites de tendance calculées en {time.time() - t1:.0f} s")
    any_cand = np.zeros_like(ok)
    for m in cand.values():
        any_cand |= m
    cnt = ok.sum(0)
    tl = T - 1
    while tl > T - 10 and cnt[tl] < .6 * cnt[T - 10:].max():
        tl -= 1

    def groups(k):
        return 0 if not k.size else 1 + int(np.sum(np.diff(k) >= 15))

    def channel(i, t, W, pl_i, ph_i):
        """Canal des W dernières séances à t : (ordonnée, pente, ligne basse, ligne haute, largeur, position, contacts bas,
        contacts haut, demi-cycles), None si trop de trous."""
        a, b = A_[W][i, t], B_[W][i, t]
        s0 = max(0, t - W + 1)
        e = LC[i, s0:t + 1] - (a + b * np.arange(s0, t + 1))
        e = e[np.isfinite(e)]
        if e.size < W * .9 or not np.isfinite(LC[i, t]):
            return None
        lo, hi = float(e.min()), float(e.max())
        if hi - lo <= 0:
            return None
        p = (e - lo) / (hi - lo)
        z = np.where(p <= .25, -1, np.where(p >= .75, 1, 0))
        z = z[z != 0]
        half = int(np.sum(z[1:] != z[:-1]))
        kl = pl_i[(pl_i >= s0) & (pl_i <= t - 5)]
        kh = ph_i[(ph_i >= s0) & (ph_i <= t - 5)]
        nf = groups(kl[lLb[i, kl] - (a + b * kl) <= lo + L3])
        nc = groups(kh[lHb[i, kh] - (a + b * kh) >= hi - L3])
        pos = (float(LC[i, t] - (a + b * t)) - lo) / (hi - lo)
        return a, b, lo, hi, np.exp(hi - lo) - 1, pos, nf, nc, half

    RULE = "canal haussier d'un an (pente ≥ +15 %/an, largeur 15 à 50 %, 2 contacts, 3 demi-cycles)"
    base = dict(W=250, mid=False, f=None)
    variants = {
        RULE: base,
        '… et en tendance (moyennes 50 et 200 séances)': {**base, 'f': 'trend'},
        '… et dans la zone du 🎯 (momentum achat)': {**base, 'f': 'zone'},
        '… et entrée dans le 🎯 depuis moins de 20 séances': {**base, 'f': 'recent'},
        'canal de 6 mois (125 séances)': {**base, 'W': 125},
        'contrôle : achat au milieu du canal': {**base, 'mid': True},
    }
    filt = {None: ok, 'trend': trend, 'zone': zone, 'recent': recent}
    trades = {k: [] for k in variants}
    refs = {"🎯 au feu vert gardé 125 séances (ce que fait l'outil)": dedup(feu, 125),
            '🎯 : entrée depuis moins de 20 séances, gardée 125 séances': dedup(recent & (C > m50), 125)}
    rtrades = {k: [] for k in refs}
    now = []
    t2 = time.time()
    calls = 0
    for i in range(N):
        pl_i, ph_i = np.flatnonzero(pl[i]), np.flatnonzero(ph[i])
        # références : achat le lendemain, vente à la clôture 125 séances plus tard
        for name, R in refs.items():
            for t in np.flatnonzero(R[i, 260:T - 6]) + 260:
                buy, u = float(O[i, t + 1]), min(T - 1, t + 126)
                sell = float(C[i, u])
                if buy > 0 and np.isfinite(sell) and sell > 0:
                    net = sell / buy * (1 - COST) - 1
                    rtrades[name].append({'net': net, 'ex': net - (M[u] / M[t] - 1), 'days': u - t, 'how': 'durée',
                                          'prw': None, 'month': int(months[t]), 'year': int(yrs[t])})
        if pl_i.size < 4 or ph_i.size < 4:
            continue
        busy = {k: -1 for k in variants}
        for t in np.flatnonzero(any_cand[i, 260:T - 6]) + 260:
            chans = {}
            for name, v in variants.items():
                if t <= busy[name] or not cand[v['W'], v['mid']][i, t] or not filt[v['f']][i, t]:
                    continue
                if v['W'] not in chans:
                    calls += 1
                    chans[v['W']] = channel(i, t, v['W'], pl_i, ph_i)
                ch = chans[v['W']]
                if ch is None:
                    continue
                a, b, lo, hi, w, pos, nf, nc, half = ch
                if not (.15 <= w <= .5 and nf >= 2 and nc >= 2 and half >= 3):
                    continue
                if not ((.4 <= pos <= .6) if v['mid'] else (pos <= .15)):
                    continue
                buy = float(O[i, t + 1])
                if not buy > 0:
                    continue
                end = min(T - 1, t + 126)
                us = np.arange(t + 1, end + 1)
                tgt = np.exp(a + b * us + hi) * .98
                stp = np.exp(a + b * us + lo) * .95
                ht = np.flatnonzero(Hb[i, t + 1:end + 1] >= tgt)
                hs = np.flatnonzero(C[i, t + 1:end + 1] < stp)
                jt = ht[0] if ht.size else 10 ** 9
                js = hs[0] if hs.size else 10 ** 9
                if jt <= js and jt < 10 ** 9:
                    u = int(us[jt])
                    o_ = float(O[i, u])
                    how, sell = 'objectif', o_ if o_ > tgt[jt] and ok[i, u - 1] else float(tgt[jt])
                elif js < 10 ** 9:
                    u = min(int(us[js]) + 1, T - 1)
                    how, sell = 'arrêt', float(O[i, u]) if np.isfinite(O[i, u]) else float(C[i, us[js]])
                else:
                    u, how, sell = end, 'durée', float(C[i, end])
                if not (sell > 0 and np.isfinite(sell)):
                    continue
                net = sell / buy * (1 - COST) - 1
                hold = float(C[i, end]) / buy * (1 - COST) - 1 if np.isfinite(C[i, end]) and C[i, end] > 0 else None
                trades[name].append({'net': net, 'ex': net - (M[u] / M[t] - 1), 'days': u - t, 'how': how, 'prw': None,
                                     'month': int(months[t]), 'year': int(yrs[t]),
                                     'hex': None if hold is None else hold - (M[end] / M[t] - 1), 'hdays': end - t})
                busy[name] = u
        # sociétés dans un canal haussier à la dernière séance complète
        t = tl
        if ok[i, t] and np.isfinite(B_[250][i, t]) and B_[250][i, t] >= SLOPE_MIN:
            ch = channel(i, t, 250, pl_i, ph_i)
            if ch is not None:
                a, b, lo, hi, w, pos, nf, nc, half = ch
                if .15 <= w <= .5 and nf >= 2 and nc >= 2 and half >= 3:
                    now.append(dict(sym=cols[i], name=names.get(cols[i], cols[i]), c=float(C[i, t]), w=w, pos=pos, nf=nf,
                                    nc=nc, half=half, slope=np.exp(b * 250) - 1, low=float(np.exp(a + b * t + lo)),
                                    high=float(np.exp(a + b * t + hi)), zone=bool(zone[i, t]), recent=bool(recent[i, t]),
                                    trend=bool(trend[i, t])))
    log(f"allers-retours simulés en {time.time() - t2:.0f} s ({calls} canaux calculés)")
    periods = [('2000-2008', 2000, 2008), ('2009-2017', 2009, 2017), ('2018-2026', 2018, 2026)]

    def held(T_):
        h = [x for x in T_ if x.get('hex') is not None]
        if len(h) < 30:
            return ''
        hx = np.array([x['hex'] for x in h]) * 100
        per = []
        for lab, y0, y1 in periods:
            sel = [x['hex'] * 100 for x in h if y0 <= x['year'] <= y1]
            per.append(f"{np.mean(sel):+5.1f}" if len(sel) >= 30 else "  ·  ")
        return f"même entrée gardée 125 séances : écart {hx.mean():+5.1f} [{' / '.join(per)}]"

    log("\n=== Références (ce que fait l'outil)")
    for name in refs:
        summary(name, rtrades[name], periods)
    log("\n=== Allers-retours dans un canal haussier (frais de 0,6 % compris ; écart avec la moyenne des sociétés)")
    for name in variants:
        summary(name, trades[name], periods)
        if trades[name]:
            ex = np.array([x['ex'] for x in trades[name]]) * 100
            days = np.mean([x['days'] for x in trades[name]])
            log(f"  {'':60s}   écart ramené à un an investi ≈ {ex.mean() / max(days, 1) * 252:+5.1f} points ; "
                f"{held(trades[name])}")
    for name in refs:
        ex = np.array([x['ex'] for x in rtrades[name]]) * 100
        if ex.size:
            log(f"  référence {name[:50]} : écart ramené à un an investi ≈ {ex.mean() / 126 * 252:+5.1f} points")
    T_ = trades[RULE]
    if T_:
        a_ = np.array([x['net'] for x in T_])
        log(f"  règle : {len(T_) / 26.9:.0f} allers-retours par an sur toutes les sociétés ; pertes de plus de 10 % : "
            f"{np.mean(a_ <= -.10) * 100:.0f} % ; gains de plus de 10 % : {np.mean(a_ >= .10) * 100:.0f} %")

    log(f"\n=== Sociétés dans un canal haussier ({dates[tl]:%d/%m/%Y}, dernière séance complète, règle) : {len(now)} ; "
        f"dans le 🎯 : {sum(x['zone'] for x in now)} ; entrée récente dans le 🎯 : {sum(x['recent'] for x in now)}")
    log("CANAL;symbole;nom;cours;ligne_basse;ligne_haute;pente_%_an;largeur_%;position_%;contacts_bas;contacts_haut;"
        "demi_cycles;tendance;zone_cible;entree_recente")
    for x in sorted(now, key=lambda x: x['pos']):
        log(";".join(str(v) for v in (
            'CANAL', x['sym'], x['name'], f"{x['c']:.2f}", f"{x['low']:.2f}", f"{x['high']:.2f}", f"{x['slope'] * 100:.0f}",
            f"{x['w'] * 100:.0f}", f"{x['pos'] * 100:.0f}", x['nf'], x['nc'], x['half'], 'oui' if x['trend'] else 'non',
            'oui' if x['zone'] else 'non', 'oui' if x['recent'] else 'non')))
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
