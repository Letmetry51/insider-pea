"""Rebonds sur support sur fort volume, comptés (question de François du 13/11/2026 : « mettre la sélection d'actions qui ont fait
1 ou 2 ou 3 rebonds sur support avec forte hausse du volume et anticiper la hausse »).

Règle fixée avant le calcul, seuls cours connus à chaque date :
- creux : point bas encadré de 5 séances de chaque côté (plus bas du jour borné à la clôture / 1,5), connu 5 séances après ;
- sur support : un creux antérieur, 15 à 250 séances plus tôt, à 3 % près du même niveau (double ou triple creux) ;
- rebond sur fort volume : 5 séances après le creux, clôture au moins 5 % au-dessus du creux, et une séance au moins, du creux à
  ces 5 séances, à 2 fois le volume moyen des 50 séances précédentes ou plus ;
- nombre de rebonds : rebonds sur fort volume au même niveau (à 3 % près) dans les 250 dernières séances, celui du jour compris :
  1, 2, 3 ou plus. Signal principal : au moins 2 rebonds sur fort volume.
Achat à l'ouverture du lendemain de la 5e séance. Contrôles : rebond sur support sans fort volume, rebond sur fort volume hors
support, tous les rebonds de 5 %. Contextes : en tendance (moyennes 50 et 200 séances), hors tendance, avant le 🎯, dans le 🎯.
Mesure (comme hausse_tot5.py) : écart avec la moyenne des sociétés à 1, 3, 6 et 12 mois, une entrée par société et par semestre,
t regroupé par mois, trois périodes 2000-2008 / 2009-2017 / 2018-2026 ; références de l'outil : 🎯 au feu vert, 📣 bond du jour.
« Anticiper la hausse » : part des cas qui font un nouveau plus haut d'un an dans les 6 mois.

Cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant). Lancé par « Recherche (à la demande) »
(script rebonds_support.py), environ 3 minutes.
"""
import glob
import json
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3
from hausse_tot5 import stats4

log, shift, roll, dedup = FB.log, FB.shift, HT.roll, FB.dedup


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
        ret1 = C / C1 - 1
        Lb = np.maximum(L, C / 1.5)
        lmin = pd.DataFrame(Lb.T).rolling(11, center=True, min_periods=11).min().values.T
        pl = ok & (Lb <= lmin)
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = ok & (C > m200) & (m50 > m200)
        mom = shift(C, 21) / shift(C, 252) - 1
        zone = trend & (mom >= .6) & (mom <= 2.0)
        feu = zone & (C > m50)
        early = ok & (mom > -.2) & (mom < .6)
        clv = (C - L) / (H - L)
        dbond = ok & (ret1 >= .08) & (vx >= 5) & (clv >= .5) & trend
        cmax = roll(C, 250, 'max', 225)
    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r
    cnt = ok.sum(0)
    tl = T - 1
    now_paris = pd.Timestamp.now(tz='Europe/Paris')
    if dates[tl].date() >= now_paris.date() and now_paris.hour < 18:   # séance du jour pas encore close
        tl -= 1
    while tl > T - 10 and cnt[tl] < .6 * cnt[T - 10:].max():
        tl -= 1

    t1 = time.time()
    E = {k: np.zeros((N, T), bool) for k in ('n1', 'n2', 'n3', 'weak', 'nosup', 'all')}
    NREB = np.zeros((N, T), np.int8)
    for i in range(N):
        PL = np.flatnonzero(pl[i])
        strong_lows = []                   # rebonds sur fort volume passés : (creux, niveau)
        for k in PL:
            k = int(k)
            t = k + 5
            if t >= T - 1:
                break
            low = float(Lb[i, k])
            if not (low > 0 and ok[i, t]):
                continue
            reb = C[i, t] >= low * 1.05
            vmax = np.nanmax(vx[i, k:t + 1]) if np.isfinite(vx[i, k:t + 1]).any() else np.nan
            strong = bool(reb and vmax >= 2)
            prev = PL[(PL >= k - 250) & (PL <= k - 15)]
            at_sup = bool(prev.size and np.any(np.abs(Lb[i, prev] / low - 1) <= .03))
            if strong:
                n = 1 + sum(1 for kk, lv in strong_lows if k - 250 <= kk <= k - 15 and abs(lv / low - 1) <= .03)
                strong_lows.append((k, low))
            if t < 260:
                continue
            if reb:
                E['all'][i, t] = True
            if at_sup and reb and not strong:
                E['weak'][i, t] = True
            if strong and not at_sup:
                E['nosup'][i, t] = True
            if strong and at_sup:
                E['n1' if n == 1 else 'n2' if n == 2 else 'n3'][i, t] = True
                NREB[i, t] = min(n, 9)
    log(f"rebonds repérés en {time.time() - t1:.0f} s : sur support et fort volume {int(E['n1'].sum() + E['n2'].sum() + E['n3'].sum())}"
        f" (1 : {int(E['n1'].sum())}, 2 : {int(E['n2'].sum())}, 3 ou plus : {int(E['n3'].sum())}) ; sans fort volume "
        f"{int(E['weak'].sum())} ; hors support {int(E['nosup'].sum())} ; tous les rebonds de 5 % {int(E['all'].sum())}")

    def hi_share(M):
        ii, tt_ = np.where(dedup(M, 125))
        keep = (tt_ + 126 < T) & (yrs[tt_] >= 2000)
        ii, tt_ = ii[keep], tt_[keep]
        if len(ii) < 30:
            return ''
        hit = [np.nanmax(C[i, t + 1:t + 126]) > cmax[i, t] for i, t in zip(ii, tt_)]
        return f"nouveau plus haut d'un an dans les 6 mois : {np.mean(hit) * 100:.0f} % ({len(ii)} cas)"

    log("\n=== Références de l'outil (même mesure)")
    stats4("tous les jours, sociétés en tendance", dedup(trend, 125), EX, RAW, months, yrs)
    stats4("🎯 au feu vert (ce que l'outil propose d'acheter)", dedup(feu, 125), EX, RAW, months, yrs)
    stats4("📣 bond du jour (+8 % sur 5 fois le volume, en tendance)", dedup(dbond, 125), EX, RAW, months, yrs)
    n2p = E['n2'] | E['n3']
    sup_strong = E['n1'] | n2p
    blocks = [
        ('1 rebond sur fort volume', E['n1']),
        ('2 rebonds sur fort volume', E['n2']),
        ('3 rebonds ou plus sur fort volume', E['n3']),
        ('au moins 2 rebonds sur fort volume (signal principal)', n2p),
    ]
    log("\n=== Rebonds sur support sur fort volume, selon leur nombre")
    for lab, M in blocks:
        stats4(lab, dedup(M, 125), EX, RAW, months, yrs)
        log(f"  {'':60s} {hi_share(M)}")
    log("\n=== Contextes (au moins 2 rebonds sur fort volume, puis un seul)")
    for lab, M in (('au moins 2 rebonds', n2p), ('1 rebond', E['n1'])):
        stats4(f"{lab}, en tendance", dedup(M & trend, 125), EX, RAW, months, yrs)
        stats4(f"{lab}, hors tendance", dedup(M & ~trend, 125), EX, RAW, months, yrs)
        stats4(f"{lab}, avant le 🎯 (−20 à +60 % sur 12 mois)", dedup(M & early, 125), EX, RAW, months, yrs)
        stats4(f"{lab}, avant le 🎯, en tendance", dedup(M & early & trend, 125), EX, RAW, months, yrs)
        stats4(f"{lab}, dans la zone du 🎯", dedup(M & zone, 125), EX, RAW, months, yrs)
    log("\n=== Contrôles")
    stats4("rebond sur support sans fort volume", dedup(E['weak'], 125), EX, RAW, months, yrs)
    log(f"  {'':60s} {hi_share(E['weak'])}")
    stats4("rebond sur fort volume hors support", dedup(E['nosup'], 125), EX, RAW, months, yrs)
    log(f"  {'':60s} {hi_share(E['nosup'])}")
    stats4("tous les rebonds de 5 % après un creux", dedup(E['all'], 125), EX, RAW, months, yrs)
    log(f"  {'':60s} {hi_share(E['all'])}")
    stats4("rebond sur support sur fort volume, tous", dedup(sup_strong, 125), EX, RAW, months, yrs)
    log(f"  {'':60s} {hi_share(sup_strong)}")
    log("\n=== Au rythme du lundi : chaque vendredi, rebond sur support sur fort volume dans les 20 séances")
    fri = np.array(dates.day_of_week == 4)
    r20 = roll(sup_strong.astype(np.float32), 20, 'max', 1) > 0
    r20b = roll(n2p.astype(np.float32), 20, 'max', 1) > 0
    stats4("🎯 au feu vert, tous les vendredis", dedup(feu & fri[None, :], 125), EX, RAW, months, yrs)
    stats4("  … avec un rebond sur support sur fort volume", dedup(feu & fri[None, :] & r20, 125), EX, RAW, months, yrs)
    stats4("  … avec au moins 2 rebonds", dedup(feu & fri[None, :] & r20b, 125), EX, RAW, months, yrs)
    stats4("en tendance avant le 🎯, avec au moins 2 rebonds", dedup(trend & early & fri[None, :] & r20b, 125), EX, RAW, months,
           yrs)

    log(f"\n=== Rebonds sur support sur fort volume des 20 dernières séances (jusqu'au {dates[tl]:%d/%m/%Y})")
    log("REBOND;symbole;nom;date;rebonds;cours_du_jour;cours_actuel;tendance;zone_cible;avant_cible")
    ii, tt_ = np.where(sup_strong[:, max(0, tl - 19):tl + 1])
    last = {}
    for i, t in zip(ii, tt_ + max(0, tl - 19)):
        last[i] = t
    for i, t in sorted(last.items(), key=lambda x: (-int(NREB[x[0], x[1]]), x[1])):
        log(";".join(str(v) for v in ('REBOND', cols[i], names.get(cols[i], cols[i]), dates[t].date(), int(NREB[i, t]),
                                       f"{C[i, t]:.2f}", f"{C[i, tl]:.2f}", 'oui' if trend[i, t] else 'non',
                                       'oui' if zone[i, t] else 'non', 'oui' if early[i, t] else 'non')))
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
