"""Cycle économique et choix des sociétés (22/11/2026, François : « Serait-il pertinent dans opportunités, de recommander des
entreprises qui sont portées par le cycle, si oui, faire ce qui est utile et pertinent et qui augmenter les possibilités des
hausses/gains »).

Phase du cycle recalculée chaque semaine comme ES.cyclePhase (core.js, onglet Secteurs) : force relative de chaque secteur
(moyenne de ses sociétés sur 13 et 26 semaines, face à la moyenne des sociétés), note de chaque phase = force des secteurs qui la
mènent − force de ceux qui la freinent (modèle de rotation de Fidelity et Stovall), phase la mieux notée, seconde phase si l'écart
est sous 0,02 ; secteur « porté », « à contre-cycle » ou neutre comme ES.cycleFit. Données : cours hebdomadaires de
backtest/_long.py (sociétés encore cotées : biais du survivant), secteurs Yahoo, règles de backtest/_selection_sim.py.

1. Le tableau dit-il vrai ? Rendement des 26 semaines suivantes des secteurs portés, neutres et à contre-cycle, face à la moyenne
   des sociétés (t sur des semaines espacées de 26).
2. Sélection simulée 1998-2026 (4 🎯 + 1 📣 par semaine, gardés 26 semaines, frais 0,3 % par sens, 2 par secteur), écart avec la
   règle actuelle : portés d'abord dans chaque palier ; porté compté comme un 📣 dans la priorité ; 🎯 sans les sociétés à
   contre-cycle ; 🎯 et 📣 sans elles ; 🎯 seulement dans les secteurs portés (places vides en liquidités). Pour information : une
   liste « cycle » (les 4 mieux notées des secteurs portés, en tendance, +30 % sur 12 mois au moins).

Règle fixée avant le calcul : une variante ne remplace la règle actuelle que si elle fait mieux dans chacune des périodes 1998-2008,
2009-2017 et 2018-2026, avec t ≥ 3 sur l'ensemble (blocs de 26 semaines) ; sinon, résultat documenté (research/README.md et aide).
Lancé par « Recherche (à la demande) » (script cycle_secteurs.py), environ 5 minutes.
"""
import time

import numpy as np

import figures_bougies as FB
import proba as PB

log = FB.log
ERAS3 = ('1998-2008', '2009-2017', '2018-2026')
CYCLE = [
    dict(key='early', label='Reprise', lead=['Financial Services', 'Consumer Cyclical', 'Real Estate', 'Industrials', 'Technology',
                                            'Basic Materials'],
         lag=['Utilities', 'Healthcare', 'Consumer Defensive', 'Energy', 'Communication Services']),
    dict(key='mid', label='Expansion', lead=['Technology', 'Communication Services', 'Industrials'], lag=['Utilities', 'Basic Materials']),
    dict(key='late', label='Fin de cycle', lead=['Energy', 'Basic Materials', 'Healthcare', 'Consumer Defensive', 'Utilities'],
         lag=['Technology', 'Consumer Cyclical', 'Financial Services', 'Real Estate']),
    dict(key='rec', label='Ralentissement', lead=['Consumer Defensive', 'Healthcare', 'Utilities'],
         lag=['Industrials', 'Technology', 'Basic Materials', 'Real Estate', 'Consumer Cyclical']),
]


def phases(G):
    """FIT[i, t] : 1 porté, -1 à contre-cycle, 0 neutre ; PH[t] : phase (clé) ; comme ES.cyclePhase et ES.cycleFit."""
    P, secs, okn = G['P'], G['secs'], G['okn']
    N, T = P.shape
    names = sorted(set(secs) - {'', '?', 'nan'})
    sidx = {s: np.where(secs == s)[0] for s in names}
    FIT = np.zeros((N, T), np.int8)
    PH = np.array([''] * T, dtype=object)
    with np.errstate(all='ignore'):
        for t in range(26, T):
            r3 = P[:, t] / P[:, t - 13] - 1
            r6 = P[:, t] / P[:, t - 26] - 1
            ok = okn[:, t] & np.isfinite(r3) & np.isfinite(r6)
            if ok.sum() < 100:
                continue
            r3 = np.clip(r3, -.9, 3)
            r6 = np.clip(r6, -.9, 5)
            m3, m6 = r3[ok].mean(), r6[ok].mean()
            agg = {}
            for s, ix in sidx.items():
                k = ix[ok[ix]]
                if len(k):
                    a, b = r3[k].mean() - m3, r6[k].mean() - m6
                    agg[s] = (a + b) / 2
            if len(agg) < 8:
                continue

            def score(ph):
                lead = [agg[k] for k in ph['lead'] if k in agg]
                lag = [agg[k] for k in ph['lag'] if k in agg]
                return None if not lead or not lag else np.mean(lead) - np.mean(lag)
            ranked = sorted([(score(ph), j) for j, ph in enumerate(CYCLE) if score(ph) is not None], key=lambda x: -x[0])
            if len(ranked) < 2:
                continue
            ph = CYCLE[ranked[0][1]]
            second = CYCLE[ranked[1][1]] if ranked[0][0] - ranked[1][0] < .02 else None
            PH[t] = ph['key']
            for s in agg:
                rs = agg[s]
                L1, G1 = s in ph['lead'], s in ph['lag']
                if second is None:
                    fit = 1 if L1 else -1 if G1 else 0
                else:
                    L2, G2 = s in second['lead'], s in second['lag']
                    if (L1 and L2) or ((L1 or L2) and rs > 0 and not G1 and not G2):
                        fit = 1
                    elif (G1 and G2) or ((G1 or G2) and rs < 0 and not L1 and not L2):
                        fit = -1
                    else:
                        fit = 0
                FIT[sidx[s], t] = fit
    return FIT, PH


def make_pick(G, FIT):
    """Copie de pick() de _selection_sim.py, avec le cycle en plus (mode)."""
    okn, mpn, v52, mom, trend, s26 = (G[k] for k in ('okn', 'mpn', 'v52', 'mom', 'trend', 's26'))
    bp8, wait, dem, hot, note, secs, N = (G[k] for k in ('bp8', 'wait', 'dem', 'hot', 'note', 'secs', 'N'))

    def pick(t, n=5, reserve=1, bondCap=2, perSec=2, mode=None):
        f = FIT[:, t]
        ok = okn[:, t] & ~(mpn[:, t] < 1 / 3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
        strong = trend[:, t] & (s26[:, t] >= .41)
        mid = trend[:, t] & (s26[:, t] >= .14)
        bump = bp8[:, t]
        t0 = ok & strong & (mom[:, t] >= .6)
        t1 = ok & mid & (mom[:, t] >= .3) & ~t0
        promo = t1 & bump & ~wait[:, t]
        tier0, tier1 = t0 | promo, t1 & ~promo
        if mode in ('sans_contre', 'sans_contre_tout'):
            tier0, tier1 = tier0 & (f >= 0), tier1 & (f >= 0)
        if mode == 'portes_seuls':
            tier0, tier1 = tier0 & (f == 1), tier1 & (f == 1)
        pri = 2 * hot[:, t] + bump + ((f == 1) if mode == 'bonus' else 0)

        def order(M):
            idx = np.where(M)[0]
            keys = (-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t], -pri[idx])
            if mode == 'prio':
                keys = keys + (-f[idx],)
            return idx[np.lexsort(keys)]
        out, seen = [], {}
        q = order(tier0).tolist() + order(tier1).tolist()
        m = n - reserve
        for cap in (perSec, perSec + 1):
            for i in q:
                if len(out) >= m:
                    break
                if i in out or seen.get(secs[i], 0) >= cap:
                    continue
                seen[secs[i]] = seen.get(secs[i], 0) + 1
                out.append(i)
        if reserve:
            dm = ok & dem[:, t] & ~np.isin(np.arange(N), out)
            if mode == 'sans_contre_tout':
                dm = dm & (f >= 0)
            for i in order(dm):
                if len(out) >= n:
                    break
                if seen.get(secs[i], 0) >= bondCap:
                    continue
                seen[secs[i]] = seen.get(secs[i], 0) + 1
                out.append(i)
            for i in q:
                if len(out) >= n:
                    break
                if i not in out and seen.get(secs[i], 0) < perSec + 1:
                    seen[secs[i]] = seen.get(secs[i], 0) + 1
                    out.append(i)
        return out
    return pick


def weekly_slots(G, f, n=5, hold=26, cost=.003):
    """Tranches de 26 semaines, 1/n par ligne (places vides en liquidités) : rendement hebdomadaire du portefeuille."""
    t1997, T, retw = G['t1997'], G['T'], G['retw']
    sleeves, R = [], []
    for t in range(t1997, T - 1):
        s = np.array(f(t), dtype=int)
        sleeves.append([t, s, np.ones(len(s)) / n])
        sleeves = [x for x in sleeves if t - x[0] < hold]
        r = 0.0
        for x in sleeves:
            if len(x[1]):
                rr = retw[x[1], t + 1]
                r += (x[2] * rr).sum()
                x[2] = x[2] * (1 + rr)
        R.append(r / hold - cost * 2 * (len(s) / n) / hold)
    return np.array(R)


def main():
    t0 = time.time()
    G = PB.load()
    t1997, T, ERAS = G['t1997'], G['T'], G['ERAS']
    retw, okn = G['retw'], G['okn']
    log(f"données prêtes en {time.time() - t0:.0f} s")
    FIT, PH = phases(G)
    log(f"phases calculées en {time.time() - t0:.0f} s")

    # 0. Phases dans le temps
    labels = {c['key']: c['label'] for c in CYCLE}
    for el, a, b in ERAS:
        if el not in ERAS3:
            continue
        ph = [p for p in PH[a:min(b, T - 1)] if p]
        log(f"  {el} : " + ', '.join(f"{labels[k]} {ph.count(k) / max(len(ph), 1) * 100:.0f} %" for k in labels))

    # 1. Le tableau dit-il vrai ? rendement des 26 semaines suivantes par place dans le cycle
    log("\n1. Rendement des 26 semaines suivantes face à la moyenne des sociétés (points de %, semaines espacées de 26)")
    with np.errstate(all='ignore'):
        L = np.log1p(np.where(np.isfinite(retw), retw, 0.0))
        C = np.concatenate([np.zeros((L.shape[0], 1)), np.cumsum(L, 1)], 1)
    rows = {1: [], 0: [], -1: []}
    tsamp = []
    for t in range(t1997, T - 27, 26):
        ok = okn[:, t]
        fw = np.expm1(C[:, t + 27] - C[:, t + 1])
        fw = np.clip(fw, -.95, 5)
        m = np.nanmean(fw[ok])
        tsamp.append(t)
        for k in rows:
            sel = ok & (FIT[:, t] == k)
            rows[k].append(np.nanmean(fw[sel]) - m if sel.sum() >= 10 else np.nan)
    tsamp = np.array(tsamp)
    for k, lab in ((1, 'secteurs portés'), (0, 'secteurs neutres'), (-1, 'secteurs à contre-cycle')):
        x = np.array(rows[k])
        cells = []
        for el, a, b in ERAS:
            if el in ERAS3:
                y = x[(tsamp >= a) & (tsamp < b)]
                y = y[np.isfinite(y)]
                cells.append(f"{el} {y.mean() * 100:+5.1f}")
        y = x[np.isfinite(x)]
        tv = y.mean() / (y.std(ddof=1) / np.sqrt(len(y)))
        log(f"  {lab:26s} {y.mean() * 100:+5.1f} (t {tv:4.1f}) · " + ' · '.join(cells))
    d = np.array(rows[1]) - np.array(rows[-1])
    y = d[np.isfinite(d)]
    cells = []
    for el, a, b in ERAS:
        if el in ERAS3:
            z = d[(tsamp >= a) & (tsamp < b)]
            z = z[np.isfinite(z)]
            cells.append(f"{el} {z.mean() * 100:+5.1f}")
    log(f"  {'portés − à contre-cycle':26s} {y.mean() * 100:+5.1f} (t {y.mean() / (y.std(ddof=1) / np.sqrt(len(y))):4.1f}) · "
        + ' · '.join(cells))

    # parts des 🎯 et 📣 actuels dans chaque place du cycle
    SEL = G['SEL']
    fits = [FIT[i, t] for t, s in SEL.items() for i in s]
    log(f"\nsociétés choisies par la règle actuelle : portées {np.mean(np.array(fits) == 1) * 100:.0f} %, neutres "
        f"{np.mean(np.array(fits) == 0) * 100:.0f} %, à contre-cycle {np.mean(np.array(fits) == -1) * 100:.0f} %")

    # 2. Sélection simulée
    pick = make_pick(G, FIT)
    same = all(pick(t) == list(SEL[t]) for t in range(t1997, T - 1, 13))
    log(f"copie de la règle actuelle identique à l'originale : {same}")
    ref = weekly_slots(G, lambda t: SEL.get(t, []))

    def cagr_era(R):
        out = []
        for el, a, b in ERAS:
            if el in ERAS3:
                x = R[a - t1997:min(b, T - 1) - t1997]
                out.append(f"{el} {(np.prod(1 + x) ** (52 / len(x)) - 1) * 100:+.1f}")
        eq = np.cumprod(1 + R)
        dd = (eq / np.maximum.accumulate(eq) - 1).min()
        return f"{(eq[-1] ** (52 / len(R)) - 1) * 100:+.1f} %/an (pire baisse {dd * 100:.0f} %) · " + ' · '.join(out)

    def vs_ref(lab, R, verdict=True):
        dd = R - ref
        out, ok_all = [], True
        for el, a, b in ERAS:
            if el not in ERAS3:
                continue
            x = dd[a - t1997:min(b, T - 1) - t1997]
            out.append(f"{el} {x.mean() * 52 * 100:+5.1f}")
            ok_all &= x.mean() > 0
        blk = np.array([dd[k:k + 26].sum() for k in range(0, len(dd) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        v = (' → BAT LA RÈGLE ACTUELLE' if ok_all and tv >= 3 else ' → rejetée') if verdict else ''
        log(f"  {lab:52s} {cagr_era(R)}\n  {'':52s} écart : {' · '.join(out)} pts/an, t {tv:4.1f}{v}")

    log("\n2. Sélection simulée (4 🎯 + 1 📣, 26 semaines, frais compris)")
    log(f"  {'règle actuelle':52s} {cagr_era(ref)}")
    for mode, lab in (('prio', 'secteurs portés d\'abord dans chaque palier'),
                      ('bonus', 'porté compté comme un 📣 dans la priorité'),
                      ('sans_contre', '🎯 sans les sociétés à contre-cycle'),
                      ('sans_contre_tout', '🎯 et 📣 sans les sociétés à contre-cycle'),
                      ('portes_seuls', '🎯 seulement dans les secteurs portés')):
        R = weekly_slots(G, lambda t, m=mode: pick(t, mode=m))
        vs_ref(lab, R)

    # liste « cycle » pour information : les 4 mieux notées des secteurs portés, en tendance, +30 % sur 12 mois au moins
    note, trend, mom, v52, mpn = (G[k] for k in ('note', 'trend', 'mom', 'v52', 'mpn'))

    def cyc_list(t):
        M = okn[:, t] & trend[:, t] & (mom[:, t] >= .3) & (mom[:, t] <= 2) & ~(v52[:, t] >= .8) & (FIT[:, t] == 1)
        idx = np.where(M)[0]
        return idx[np.argsort(-np.nan_to_num(note[idx, t]))][:4].tolist()
    vs_ref("liste « cycle » (4 mieux notées des secteurs portés)", weekly_slots(G, cyc_list, n=4), verdict=False)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
