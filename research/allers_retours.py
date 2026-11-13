"""Allers-retours entre support et résistance (question de François du 13/11/2026 : « une action qui oscille de façon cyclique
entre support et résistance, l'idée serait de faire des allers-retours »). Achat près du support d'une action qui oscille dans
une fourchette depuis un an, revente près de la résistance : est-ce que ça rapporte, frais compris, et quelles actions oscillent
ainsi aujourd'hui ?

Niveaux de la page (`ES.supportResistance`, comme supports_resistances.py) recalculés chaque jour avec les seuls cours connus.
Fourchette (règle fixée avant le calcul) : support et résistance touchés chacun au moins 2 fois sur 250 séances, toutes les
clôtures de l'année entre support −5 % et résistance +5 %, largeur (résistance / support − 1) de 15 à 50 %.
Aller-retour : achat à l'ouverture du lendemain d'une séance en hausse qui clôture à moins de 3 % au-dessus du support ; revente
à la résistance −2 % dès que le plus haut du jour l'atteint (ordre à cours limité), arrêt si une clôture passe 5 % sous le
support (fourchette cassée, vente à l'ouverture suivante), sinon vente au bout de 125 séances. Frais : 0,6 % l'aller-retour
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


def levels2(kk, pp, t, close, tol):
    """Support et résistance les plus proches (touchés 2 fois ou plus) à la séance t, avec leurs contacts."""
    lo = np.searchsorted(kk, t - 249)
    hi = np.searchsorted(kk, t - 5, side='right')
    if hi - lo < 4:
        return None
    p = np.sort(pp[lo:hi])
    groups, s, n = [], p[0], 1
    for x in p[1:]:
        if x - s / n <= tol:
            s, n = s + x, n + 1
        else:
            groups.append((s / n, n))
            s, n = x, 1
    groups.append((s / n, n))
    sup = res = None
    for g, n in groups:
        if n < 2:
            continue
        if g < close - tol / 3 and (sup is None or g > sup[0]):
            sup = (g, n)
        elif g > close + tol / 3 and (res is None or g < res[0]):
            res = (g, n)
    return (sup, res) if sup and res else None


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
        tr = np.fmax(Hb - Lb, np.fmax(np.abs(Hb - C1), np.abs(Lb - C1)))
        atr = roll(tr, 14, 'mean', 10)
        tol = np.fmax(atr * 1.2, C * .015)
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
        'règle fixée (largeur 15 à 50 %, 2 contacts)': dict(wmin=.15, touch=2, mid=False),
        'fourchette large (25 à 50 %)': dict(wmin=.25, touch=2, mid=False),
        '3 contacts au moins de chaque côté': dict(wmin=.15, touch=3, mid=False),
        'contrôle : achat au milieu de la fourchette': dict(wmin=.15, touch=2, mid=True),
    }
    trades = {k: [] for k in variants}
    now = []
    with np.errstate(all='ignore'):
        # présélection rapide : cours de l'année dans une fourchette de 12 à 62 %, séance en hausse, cours dans le bas (achat près
        # du support) ou au milieu (contrôle) de la fourchette de l'année ; niveaux exacts calculés seulement ces jours-là
        yr = cmax / cmin - 1
        pos_y = (C - cmin) / (cmax - cmin)
        pre = ok & (yr >= .12) & (yr <= .62) & (C > C1)
        cand_sup, cand_mid = pre & (pos_y <= .6), pre & (pos_y >= .3) & (pos_y <= .7)
    t1 = time.time()
    for i in range(N):
        kk = np.concatenate([np.flatnonzero(ph[i]), np.flatnonzero(pl[i])])
        if kk.size < 6:
            continue
        pp = np.concatenate([Hb[i, ph[i]], Lb[i, pl[i]]]).astype(np.float64)
        order = np.argsort(kk, kind='stable')
        kk, pp = kk[order], pp[order]
        busy = {k: -1 for k in variants}
        for t in np.flatnonzero((cand_sup[i] | cand_mid[i])[260:T - 6]) + 260:
            c = float(C[i, t])
            lv = None
            for name, v in variants.items():
                if t <= busy[name]:
                    continue
                if lv is None:
                    lv = levels2(kk, pp, t, c, float(tol[i, t])) or False
                if not lv:
                    break
                (s, ns), (r, nr) = lv
                width = r / s - 1
                if not (v['wmin'] <= width <= .5 and ns >= v['touch'] and nr >= v['touch']):
                    continue
                if not (cmin[i, t] >= s * .95 and cmax[i, t] <= r * 1.05):
                    continue
                pos = (c - s) / (r - s)
                if v['mid']:
                    if not (cand_mid[i, t] and .4 <= pos <= .6):
                        continue
                elif not (cand_sup[i, t] and c <= s * 1.03):
                    continue
                buy = float(O[i, t + 1])
                if not buy > 0:
                    continue
                target, stop = r * .98, s * .95
                end = min(T - 1, t + 126)
                how, sell, u = 'durée', float(C[i, end]), end
                for u_ in range(t + 1, end + 1):
                    if Hb[i, u_] >= target and u_ > t:
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
        # actions qui oscillent aujourd'hui (règle fixée), où en est le cours
        t = T - 1
        if ok[i, t]:
            lv = levels2(kk, pp, t, float(C[i, t]), float(tol[i, t]))
            if lv:
                (s, ns), (r, nr) = lv
                width = r / s - 1
                if .15 <= width <= .5 and ns >= 2 and nr >= 2 and cmin[i, t] >= s * .95 and cmax[i, t] <= r * 1.05:
                    now.append((cols[i], names.get(cols[i], cols[i]), float(C[i, t]), s, ns, r, nr, width,
                                (float(C[i, t]) - s) / (r - s)))
    log(f"allers-retours simulés en {time.time() - t1:.0f} s")
    log("\n=== Allers-retours (frais de 0,6 % compris ; écart avec la moyenne des sociétés sur les mêmes séances)")
    for name in variants:
        summary(name, trades[name], periods)
    T_ = trades['règle fixée (largeur 15 à 50 %, 2 contacts)']
    if T_:
        a = np.array([t['net'] for t in T_])
        log(f"  règle fixée : {len(T_) / 26.9:.0f} allers-retours par an sur toutes les sociétés ; pertes de plus de 10 % : "
            f"{np.mean(a <= -.10) * 100:.0f} % ; gains de plus de 10 % : {np.mean(a >= .10) * 100:.0f} %")
    log(f"\n=== Actions qui oscillent aujourd'hui ({dates[-1]:%d/%m/%Y}) dans une fourchette d'un an (règle fixée) : {len(now)}")
    for sym, nm, c, s, ns, r, nr, w, pos in sorted(now, key=lambda x: x[8])[:40]:
        log(f"  {sym:10s} {nm[:30]:30s} cours {c:8.2f} | support {s:8.2f} ({ns} contacts) | résistance {r:8.2f} ({nr} contacts)"
            f" | largeur {w * 100:3.0f} % | position {pos * 100:3.0f} %")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
