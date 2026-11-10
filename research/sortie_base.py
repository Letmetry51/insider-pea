"""Sortie de base longue, comme Corbion en septembre 2026 (question de François du 10/11/2026 : « détecter plus rapidement le
potentiel des hausses avec des configurations comme Corbion, analyser toutes les sociétés »).

Corbion : 10 mois entre 17 et 20,6 € (écart 22 %), sortie par le haut début septembre sur 2,5 fois le volume (+3,3 % et +3,8 % les
jours de sortie, pas de bond à +8 %), montée régulière jusqu'à 24,5 € fin octobre, puis bond à +8,2 % sur 4,4 fois le volume le 27/10
(📣 Démarrage envoyé le 30/10, place 📣 de la sélection le 02/11, à 27,4 €). Le 🎯 (+60 % sur 12 mois) ne la voit qu'après coup.
Question : une sortie de base longue au plus haut de l'année, avant que la société n'entre dans le 🎯, annonce-t-elle une hausse,
et combien de temps et de hausse fait-elle gagner sur le 🎯, le 📣 et le bond du jour ?

Même mesure que hausse_tot5.py : cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant, mêmes
sociétés pour la référence), achat à l'ouverture du lendemain, écart avec la moyenne des sociétés à 1, 3, 6 et 12 mois, une
entrée par société et par semestre, t regroupé par mois, trois périodes 2000-2008 / 2009-2017 / 2018-2026. Lancé par
« Recherche (à la demande) » (script sortie_base.py), environ 3 minutes.

Sortie de base (règle testée, fixée avant le calcul) : clôture au-dessus du plus haut des L séances précédentes (L = 250 : nouveau
plus haut d'un an), ces L séances tenant dans un écart de R (plus haut / plus bas − 1, R = 25 %), volume du jour au moins V fois la
moyenne des 50 séances précédentes (V = 2), hausse sur 12 mois (sans le dernier mois) entre −20 et +60 % (pas encore 🎯). Variantes
de L, R, V et de la tendance affichées pour la robustesse, pas pour choisir la meilleure.
"""
import time

import numpy as np

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3
from hausse_tot5 import stats4

log, shift, dedup, roll = FB.log, FB.shift, FB.dedup, HT.roll


def first_after(M, ii, tt, horizon):
    """Pour chaque évènement (i, t), première séance u dans ]t, t + horizon] où M est vrai, sinon -1."""
    out = np.full(len(ii), -1)
    for k, (i, t) in enumerate(zip(ii, tt)):
        w = np.flatnonzero(M[i, t + 1:t + 1 + horizon])
        if w.size:
            out[k] = t + 1 + w[0]
    return out


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
        ret1 = C / C1 - 1
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        clv = (C - L) / (H - L)
        mom = shift(C, 21) / shift(C, 252) - 1
        zone = ok & trend & (mom >= .6) & (mom <= 2.0)            # zone du 🎯
        early = (mom > -.2) & (mom < .6)                           # pas encore 🎯
        dbond = ok & (ret1 >= .08) & (vx >= 5) & (clv >= .5) & trend   # 📣 bond du jour actuel
        r5 = C / shift(C, 5) - 1
        v5 = roll(Vp, 5, 'mean', 4) / shift(roll(Vp, 50, 'mean', 40), 5)
        wbond = ok & (r5 >= .08) & (v5 >= 3) & trend               # 📣 de la semaine, approché sur 5 séances glissantes
        hi = {Lb: shift(roll(C, Lb, 'max', int(Lb * .9)), 1) for Lb in (120, 250)}
        lo = {Lb: shift(roll(C, Lb, 'min', int(Lb * .9)), 1) for Lb in (120, 250)}
    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r

    def brk(Lb, R, Vm, tr=None):
        with np.errstate(all='ignore'):
            M = ok & early & (C > hi[Lb]) & (hi[Lb] / lo[Lb] - 1 <= R) & (vx >= Vm)
        return M & trend if tr == 'oui' else (M & ~trend if tr == 'non' else M)

    log("\n=== Références")
    stats4("tous les jours, sociétés pas encore 🎯 (−20 à +60 %)", dedup(ok & early, 125), EX, RAW, months, yrs)
    stats4("nouveau plus haut d'un an, pas encore 🎯 (sans base)", dedup(ok & early & (C > hi[250]), 125), EX, RAW, months, yrs)
    zprev = np.zeros_like(zone)
    zprev[:, 1:] = zone[:, :-1]
    stats4("entrée dans la zone du 🎯", dedup(zone & ~zprev, 125), EX, RAW, months, yrs)
    stats4("📣 bond du jour (+8 % sur 5 fois, en tendance)", dedup(dbond, 125), EX, RAW, months, yrs)
    stats4("📣 de la semaine (5 séances : +8 % sur 3 fois, en tendance)", dedup(wbond, 125), EX, RAW, months, yrs)

    log("\n=== Sortie de base longue (règle fixée : 250 séances dans 25 %, volume 2 fois, pas encore 🎯)")
    main_ev = dedup(brk(250, .25, 2), 125)
    stats4("sortie de base, règle fixée", main_ev, EX, RAW, months, yrs)
    stats4("  … en tendance (moyenne 50 au-dessus de la 200)", dedup(brk(250, .25, 2, 'oui'), 125), EX, RAW, months, yrs)
    stats4("  … hors tendance", dedup(brk(250, .25, 2, 'non'), 125), EX, RAW, months, yrs)
    stats4("  … sans condition de volume", dedup(brk(250, .25, 0), 125), EX, RAW, months, yrs)
    stats4("  … sur 3 fois le volume ou plus", dedup(brk(250, .25, 3), 125), EX, RAW, months, yrs)
    stats4("  … le jour de sortie à +5 % ou plus", dedup(brk(250, .25, 2) & (ret1 >= .05), 125), EX, RAW, months, yrs)

    log("\n=== Robustesse : longueur de la base, écart, volume")
    for Lb in (120, 250):
        for R in (.25, .35, .5):
            for Vm in (0, 2, 3):
                stats4(f"base {Lb} séances, écart ≤ {R * 100:.0f} %, volume ≥ {Vm} fois", dedup(brk(Lb, R, Vm), 125),
                       EX, RAW, months, yrs)

    log("\n=== Temps et hausse gagnés par la règle fixée (6 mois après la sortie)")
    ii, tt = np.where(main_ev)
    keep = tt + 1 < T
    ii, tt = ii[keep], tt[keep]
    log(f"  {len(ii)} sorties de base")
    for name, M in (("zone du 🎯", zone), ("📣 bond du jour", dbond), ("📣 de la semaine", wbond)):
        u = first_after(M, ii, tt, 125)
        hit = u >= 0
        if not hit.any():
            log(f"  {name} : jamais dans les 6 mois")
            continue
        lag = (u - tt)[hit]
        gain = np.array([(O[i, min(x + 1, T - 1)] / O[i, t + 1] - 1) * 100 for i, t, x in zip(ii[hit], tt[hit], u[hit])])
        gain = gain[np.isfinite(gain)]
        log(f"  {name} : {hit.mean() * 100:.0f} % des sorties y arrivent dans les 6 mois, {np.median(lag):.0f} séances après "
            f"(médiane) ; hausse déjà faite entre l'achat le lendemain de la sortie et l'achat à ce signal : médiane "
            f"{np.median(gain):+.1f} %, moyenne {gain.mean():+.1f} %")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
