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
sociétés sur les mêmes séances, et le même aller-retour acheté au milieu de la fourchette (contrôle).

Cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant). Lancé par « Recherche (à la demande) »
(script allers_retours.py), environ 5 minutes.
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
    mo = pd.Series(ex, index=[t['month'] for t in T_]).groupby(level=0).mean()
    tv = mo.mean() / (mo.std(ddof=1) / np.sqrt(len(mo))) if len(mo) > 2 and mo.std() > 0 else float('nan')
    per = []
    for lab, y0, y1 in periods:
        sel = [t['ex'] * 100 for t in T_ if y0 <= t['year'] <= y1]
        per.append(f"{np.mean(sel):+5.1f}" if len(sel) >= 30 else "  ·  ")
    yearly = np.mean(a) / max(np.mean(days), 1) * 252
    log(f"  {name:60s} {len(a):5d} | net {np.mean(a):+5.1f} % (médiane {np.median(a):+5.1f}) en {np.mean(days):4.0f} séances, "
        f"≈ {yearly:+5.1f} %/an investi | objectif {win:3.0f} %, arrêt {stop:3.0f} % | écart à la moyenne {np.mean(ex):+5.1f} "
        f"(t {tv:4.1f}) [{' / '.join(per)}]")


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
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0)
        C1 = shift(C, 1)
        Hb, Lb = np.minimum(H, C * 1.5), np.maximum(L, C / 1.5)
        cmax = roll(C, 250, 'max', 225)
        cmin = roll(C, 250, 'min', 225)
        hmax = pd.DataFrame(Hb.T).rolling(11, center=True, min_periods=11).max().values.T
        lmin = pd.DataFrame(Lb.T).rolling(11, center=True, min_periods=11).min().values.T
        ph, pl = ok & (Hb >= hmax), ok & (Lb <= lmin)
        r1 = np.where(ok, C / C1 - 1, np.nan)
        mret = np.nanmean(np.where(np.abs(r1) < .5, r1, np.nan), 0)
        mret[np.isfinite(r1).sum(0) < 30] = np.nan
        M = np.exp(np.nancumsum(np.log1p(np.nan_to_num(mret))))   # moyenne des sociétés (indice équipondéré)
    periods = [('2000-2008', 2000, 2008), ('2009-2017', 2009, 2017), ('2018-2026', 2018, 2026)]
    variants = {
        'règle fixée (largeur 15 à 50 %, 2 contacts, 3 demi-cycles)': dict(wmin=.15, touch=2, swing=3, mid=False),
        'fourchette large (25 à 50 %)': dict(wmin=.25, touch=2, swing=3, mid=False),
        'plus régulière (3 contacts, 5 demi-cycles)': dict(wmin=.15, touch=3, swing=5, mid=False),
        'contrôle : achat au milieu de la fourchette': dict(wmin=.15, touch=2, swing=3, mid=True),
    }
    trades = {k: [] for k in variants}
    now = []
    with np.errstate(all='ignore'):
        yr = cmax / cmin - 1
        pos_y = (C - cmin) / (cmax - cmin)
        pre = ok & (yr >= .15) & (yr <= .5) & (C > C1)
        cand_sup, cand_mid = pre & (pos_y <= .15), pre & (pos_y >= .4) & (pos_y <= .6)

    def band(i, t, pl_i, ph_i):
        """Fourchette de l'année (clôtures) à la séance t : (bas, haut, contacts du bas, contacts du haut, demi-cycles)."""
        lo_, hi_ = float(cmin[i, t]), float(cmax[i, t])
        a = max(0, t - 249)
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
        for t in np.flatnonzero((cand_sup[i] | cand_mid[i])[260:T - 6]) + 260:
            b = None
            for name, v in variants.items():
                if t <= busy[name] or not (cand_mid[i, t] if v['mid'] else cand_sup[i, t]):
                    continue
                if b is None:
                    b = band(i, t, pl_i, ph_i)
                lo_, hi_, nf, nc, half = b
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
                        how, sell, u = 'objectif', max(target, float(O[i, u_])) if O[i, u_] > target else target, u_
                        break
                    if C[i, u_] < stop:
                        u = min(u_ + 1, T - 1)
                        how, sell = 'arrêt', float(O[i, u]) if np.isfinite(O[i, u]) else float(C[i, u_])
                        break
                if not (sell > 0 and np.isfinite(sell)):
                    continue
                net = sell / buy * (1 - COST) - 1
                mk = M[u] / M[t] - 1 if M[t] > 0 else 0.0
                trades[name].append({'net': net, 'ex': net - mk, 'days': u - t, 'how': how,
                                     'month': int(months[t]), 'year': int(yrs[t])})
                busy[name] = u
        # actions qui oscillent aujourd'hui (règle fixée) et où en est leur cours dans la fourchette
        t = T - 1
        if ok[i, t] and .15 <= yr[i, t] <= .5:
            lo_, hi_, nf, nc, half = band(i, t, pl_i, ph_i)
            if nf >= 2 and nc >= 2 and half >= 3:
                now.append((cols[i], names.get(cols[i], cols[i]), float(C[i, t]), lo_, nf, hi_, nc, hi_ / lo_ - 1,
                            (float(C[i, t]) - lo_) / (hi_ - lo_), half))
    log(f"allers-retours simulés en {time.time() - t1:.0f} s")
    log("\n=== Allers-retours (frais de 0,6 % compris ; écart avec la moyenne des sociétés sur les mêmes séances)")
    for name in variants:
        summary(name, trades[name], periods)
    T_ = trades['règle fixée (largeur 15 à 50 %, 2 contacts, 3 demi-cycles)']
    if T_:
        a = np.array([t['net'] for t in T_])
        log(f"  règle fixée : {len(T_) / 26.9:.0f} allers-retours par an sur toutes les sociétés ; pertes de plus de 10 % : "
            f"{np.mean(a <= -.10) * 100:.0f} % ; gains de plus de 10 % : {np.mean(a >= .10) * 100:.0f} %")
    log(f"\n=== Actions qui oscillent aujourd'hui ({dates[-1]:%d/%m/%Y}) dans une fourchette d'un an (règle fixée) : {len(now)}")
    for sym, nm, c, s, ns, r, nr, w, pos, half in sorted(now, key=lambda x: x[8])[:40]:
        log(f"  {sym:10s} {nm[:30]:30s} cours {c:8.2f} | support {s:8.2f} ({ns} contacts) | résistance {r:8.2f} ({nr} contacts)"
            f" | largeur {w * 100:3.0f} % | position {pos * 100:3.0f} % | {half} demi-cycles")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
