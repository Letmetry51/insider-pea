"""Supports et résistances tels que la page les dessine (question de François du 13/11/2026 : « améliorer la méthode avec les
supports et résistances pour détecter plus tôt le moment avant les hausses »).

Le test du 26/10/2026 (`backtest/_indic.py`) prenait des niveaux grossiers (plus bas de 13 semaines, plus haut de 52 semaines,
cours hebdomadaires). Ici, les niveaux sont ceux de `ES.supportResistance` (euro_signal/core.js), recalculés chaque jour avec les
seuls cours connus : points hauts et bas encadrés de 5 séances de chaque côté (plus haut et plus bas du jour bornés à ×1,5 la
clôture), regroupés à moins de max(1,2 ATR de 14 séances, 1,5 % du cours), sur 250 séances, un niveau comptant à partir de 2
contacts. Un point haut n'est connu que 5 séances après (il faut les 5 séances suivantes pour le voir).

Même mesure que hausse_tot5.py : cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant, mêmes
sociétés pour la référence), achat à l'ouverture du lendemain, écart avec la moyenne des sociétés à 1, 3, 6 et 12 mois, une
entrée par société et par semestre, t regroupé par mois, trois périodes 2000-2008 / 2009-2017 / 2018-2026. Lancé par
« Recherche (à la demande) » (script supports_resistances.py), environ 10 minutes.

Questions (règles fixées avant le calcul) :
1. Position chaque vendredi dans le 🎯 au feu vert (ce que l'outil propose d'acheter) et parmi les sociétés pas encore 🎯 en
   tendance : à moins de 3 % au-dessus d'un support, à moins de 3 % sous une résistance, aucune résistance au-dessus (ciel dégagé),
   entre les deux.
2. Rebond sur support : vendredi précédent à moins de 3 % au-dessus d'un support, cours de la semaine en hausse de 3 % ou plus.
3. Cassure de résistance : clôture qui franchit une résistance touchée au moins 2 fois (de plus d'un quart d'ATR), sur au moins
   1,5 fois le volume moyen de 50 séances, nouveau plus haut de 20 séances ; avant le 🎯, dans le 🎯, partout.
"""
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3
from hausse_tot5 import stats4

log, shift, dedup, roll = FB.log, FB.shift, FB.dedup, HT.roll


def levels_at(kk, pp, t, close, tol):
    """Niveaux (touchés 2 fois ou plus) à la séance t : points connus (indice ≤ t - 5) des 250 dernières séances.
    → (support le plus proche sous le cours, résistance la plus proche au-dessus), None si aucun."""
    lo = np.searchsorted(kk, t - 249)
    hi = np.searchsorted(kk, t - 5, side='right')
    if hi - lo < 2:
        return None, None
    p = np.sort(pp[lo:hi])
    sup = res = None
    s, n = p[0], 1
    groups = []
    for x in p[1:]:
        if x - s / n <= tol:
            s += x
            n += 1
        else:
            groups.append((s / n, n))
            s, n = x, 1
    groups.append((s / n, n))
    for g, n in groups:
        if n < 2:
            continue
        if g < close - tol / 3:
            sup = g if sup is None or g > sup else sup
        elif g > close + tol / 3:
            res = g if res is None or g < res else res
    return sup, res


def main():
    t0 = time.time()
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates = D['Close'].index
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
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        mom = shift(C, 21) / shift(C, 252) - 1
        zone = ok & trend & (mom >= .6) & (mom <= 2.0)            # zone du 🎯
        feu = zone & (C > m50)                                     # au feu vert (au-dessus de la moyenne 10 semaines ≈ 50 séances)
        early = ok & trend & (mom > -.2) & (mom < .6)              # en tendance, pas encore 🎯
        hmax = pd.DataFrame(Hb.T).rolling(11, center=True, min_periods=11).max().values.T
        lmin = pd.DataFrame(Lb.T).rolling(11, center=True, min_periods=11).min().values.T
        ph = ok & (Hb >= hmax)
        pl = ok & (Lb <= lmin)
        hi20 = shift(roll(Hb, 20, 'max', 18), 1)
    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r

    fri = np.array(dates.day_of_week == 4)
    near_s, near_r, clear, mid = (np.zeros((N, T), bool) for _ in range(4))
    brk = np.zeros((N, T), bool)
    cand = ok & (vx >= 1.5) & (C > C1) & (C > hi20)
    t1 = time.time()
    for i in range(N):
        kk = np.concatenate([np.flatnonzero(ph[i]), np.flatnonzero(pl[i])])
        if kk.size < 4:
            continue
        pp = np.concatenate([Hb[i, ph[i]], Lb[i, pl[i]]])
        order = np.argsort(kk, kind='stable')
        kk, pp = kk[order], pp[order].astype(np.float64)
        for t in np.flatnonzero(fri & (feu[i] | early[i])):
            sup, res = levels_at(kk, pp, t, float(C[i, t]), float(tol[i, t]))
            c = float(C[i, t])
            if sup is not None and c - sup <= .03 * c:
                near_s[i, t] = True
            if res is not None and res - c <= .03 * c:
                near_r[i, t] = True
            if res is None:
                clear[i, t] = True
            if not near_s[i, t] and not near_r[i, t] and res is not None:
                mid[i, t] = True
        for t in np.flatnonzero(cand[i]):
            _, res = levels_at(kk, pp, t - 1, float(C1[i, t]), float(tol[i, t - 1]))
            if res is not None and C[i, t] > res + .25 * atr[i, t] and C1[i, t] <= res + .25 * atr[i, t]:
                brk[i, t] = True
    log(f"niveaux calculés en {time.time() - t1:.0f} s")
    # rebond : vendredi précédent près d'un support, semaine en hausse de 3 % ou plus (achat le lundi suivant)
    w_prev = np.zeros((N, T), bool)
    fidx = np.flatnonzero(fri)
    reb = np.zeros((N, T), bool)
    for a, b in zip(fidx[:-1], fidx[1:]):
        w_prev[:, b] = near_s[:, a]
        reb[:, b] = near_s[:, a] & (C[:, b] >= C[:, a] * 1.03) & ok[:, b]

    for name, ctx in (("🎯 au feu vert (ce que l'outil propose d'acheter)", feu), ("en tendance, pas encore 🎯", early)):
        log(f"\n=== 1. Position chaque vendredi : {name}")
        base = ctx & fri[None, :]
        stats4("tous les vendredis", dedup(base, 125), EX, RAW, months, yrs)
        stats4("  à moins de 3 % au-dessus d'un support", dedup(base & near_s, 125), EX, RAW, months, yrs)
        stats4("  à moins de 3 % sous une résistance", dedup(base & near_r, 125), EX, RAW, months, yrs)
        stats4("  aucune résistance au-dessus (ciel dégagé)", dedup(base & clear, 125), EX, RAW, months, yrs)
        stats4("  entre les deux", dedup(base & mid, 125), EX, RAW, months, yrs)
        log(f"=== 2. Rebond sur support (semaine à +3 % après un vendredi près d'un support) : {name}")
        stats4("  rebond confirmé", dedup(ctx & reb, 125), EX, RAW, months, yrs)
        stats4("  près du support sans rebond la semaine suivante", dedup(ctx & w_prev & ~reb & fri[None, :], 125), EX, RAW,
               months, yrs)

    log("\n=== 3. Cassure d'une résistance touchée au moins 2 fois, sur 1,5 fois le volume, nouveau plus haut de 20 séances")
    stats4("partout", dedup(brk, 125), EX, RAW, months, yrs)
    stats4("  avant le 🎯 (en tendance, −20 à +60 % sur 12 mois)", dedup(brk & early, 125), EX, RAW, months, yrs)
    stats4("  avant le 🎯, hors tendance (−20 à +60 %)", dedup(brk & ~trend & (mom > -.2) & (mom < .6), 125), EX, RAW,
           months, yrs)
    stats4("  dans le 🎯", dedup(brk & zone, 125), EX, RAW, months, yrs)
    stats4("  sur 3 fois le volume ou plus", dedup(brk & (vx >= 3), 125), EX, RAW, months, yrs)
    log("références : nouveau plus haut de 20 séances sur 1,5 fois le volume (sans résistance)")
    stats4("  partout", dedup(cand, 125), EX, RAW, months, yrs)
    stats4("  avant le 🎯 (en tendance)", dedup(cand & early, 125), EX, RAW, months, yrs)

    log("\n=== 4. Dans le 🎯 : la résistance compte-t-elle, ou seulement le nouveau plus haut sur volume ? (contrôles)")
    with np.errstate(all='ignore'):
        up20 = ok & (C > hi20) & (C > C1)
        clv = (C - L) / (H - L)
        dbond = ok & (C / C1 - 1 >= .08) & (vx >= 5) & (clv >= .5) & trend
    stats4("🎯 : cassure d'une résistance sur 1,5 fois le volume (rappel)", dedup(brk & zone, 125), EX, RAW, months, yrs)
    stats4("🎯 : nouveau plus haut de 20 séances sur 1,5 fois le volume", dedup(cand & zone, 125), EX, RAW, months, yrs)
    stats4("🎯 : … sans résistance franchie ce jour-là", dedup(cand & zone & ~brk, 125), EX, RAW, months, yrs)
    stats4("🎯 : nouveau plus haut de 20 séances, volume quelconque", dedup(up20 & zone, 125), EX, RAW, months, yrs)
    stats4("🎯 : … sur moins de 1,5 fois le volume", dedup(up20 & zone & ~(vx >= 1.5), 125), EX, RAW, months, yrs)
    stats4("🎯 : bond du jour (+8 % sur 5 fois le volume)", dedup(dbond & zone, 125), EX, RAW, months, yrs)
    log("  chaque vendredi au feu vert (rythme de la sélection du lundi) :")
    rb10 = roll(brk.astype(np.float32), 10, 'max', 1) > 0
    rc10 = roll(cand.astype(np.float32), 10, 'max', 1) > 0
    base = feu & fri[None, :]
    stats4("    cassure de résistance dans les 10 dernières séances", dedup(base & rb10, 125), EX, RAW, months, yrs)
    stats4("    plus haut de 20 séances sur volume dans les 10 séances, sans résistance", dedup(base & rc10 & ~rb10, 125),
           EX, RAW, months, yrs)
    stats4("    ni l'un ni l'autre", dedup(base & ~rc10, 125), EX, RAW, months, yrs)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
