"""Compléments de survivant_pratique.py (22/11/2026) : le seuil de liquidité du 🎯 (3 M€ par jour en direct) face à 0,5, 1 et
10 M€, avec le t de chaque écart (blocs de 26 semaines) ; achat le lundi mesuré de façon robuste (lignes aux cours d'ouverture
aberrants écartées : écart de plus de 30 % entre la clôture du vendredi et l'ouverture du lundi ; médiane et moyenne écrêtée).
Règle fixée avant : un autre seuil ne remplace 3 M€ que s'il fait mieux dans chacune des 3 périodes avec t ≥ 3.
Lancé par « Recherche (à la demande) » (script survivant_liquidite.py), environ 15 minutes, 7 300 appels EODHD.
"""
import concurrent.futures as cf
import gc
import time

import numpy as np

import survivant_eodhd as SE
import survivant_pratique as SP

log = SE.log
SE.LIQ = 5e5


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00 = (
        D[k] for k in ('P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00'))
    G = SE.chain(P, V, dates, cols, secs, liq >= 5e5)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn0 = G['okn'].copy()
    SELS, R = {}, {}
    for L in (5e5, 1e6, 3e6, 1e7):
        G['okn'] = okn0 & (liq >= L)
        SELS[L] = {t: G['pick'](t, n=5, reserve=1, bondCap=2) for t in range(t2001, T - 1)}
        R[L] = SP.sim_stop(G, SELS[L])
    ref = R[3e6]

    def ann(x):
        return (np.prod(1 + x) ** (52 / len(x)) - 1) * 100
    log("\n1. Seuil de liquidité face aux 3 M€ du 🎯 en direct (protection −30 %, frais 0,3 % par sens)")
    log(f"  ≥ 3 M€ (règle actuelle) : {ann(ref):+.1f} %/an")
    for L in (5e5, 1e6, 1e7):
        d = R[L] - ref
        sg = [d[a - t2001:b - t2001].mean() * 5200 for el, a, b in ERAS]
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        v = ' → BAT LA RÈGLE ACTUELLE' if all(x > 0 for x in sg) and tv >= 3 else ' → pas retenu'
        log(f"  ≥ {L / 1e6:4.1f} M€ : {ann(R[L]):+.1f} %/an · écart " + ' · '.join(f"{el} {x:+5.1f}" for (el, a, b), x in zip(ERAS, sg))
            + f" pts/an (t {tv:4.1f}){v}")

    log("\n2. Achat le lundi, mesure robuste (lignes aux cours d'ouverture aberrants écartées)")
    picked = sorted({i for L in (1e6, 3e6) for s in SELS[L].values() for i in s})
    daily = {}

    def one(i):
        x, err = SE.get(f"eod/{cols[i]}", **{'from': '2000-06-01'})
        return i, x
    with cf.ThreadPoolExecutor(8) as pool:
        for i, x in pool.map(one, picked):
            if not x:
                continue
            d = np.array([b['date'] for b in x], dtype='datetime64[D]')
            c = np.array([float(b.get('close') or 'nan') for b in x])
            a = np.array([float(b.get('adjusted_close') or 'nan') for b in x])
            o = np.array([float(b.get('open') or 'nan') for b in x])
            k = np.where((c > 0) & (a > 0) & (o > 0))[0]
            daily[i] = (d[k], a[k], o[k] * a[k] / c[k])
    fri = np.array([np.datetime64(x) for x in dates], dtype='datetime64[D]')
    for L in (1e6, 3e6):
        X, bad = [], 0
        for t in range(t2001, T - 27):
            for i in SELS[L].get(t, []):
                if i not in daily:
                    continue
                d, a, o = daily[i]
                k0 = np.searchsorted(d, fri[t], side='right')
                k1 = np.searchsorted(d, fri[t + 26], side='right')
                if k0 == 0 or k0 >= len(d) or k1 == 0 or k1 >= len(d) or (d[k0] - fri[t]).astype(int) > 4:
                    continue
                g0, g1 = o[k0] / a[k0 - 1] - 1, o[k1] / a[k1 - 1] - 1
                if abs(g0) > .3 or abs(g1) > .3:
                    bad += 1
                    continue
                X.append((a[k1 - 1] / a[k0 - 1] - 1, o[k1] / o[k0] - 1, a[k1] / a[k0] - 1, g0))
        X = np.array(X)
        for j, lab in ((1, "à l'ouverture du lundi"), (2, "à la clôture du lundi")):
            dlt = X[:, j] - X[:, 0]
            lo, hi = np.percentile(dlt, [1, 99])
            tm = np.clip(dlt, lo, hi)
            log(f"  ≥ {L / 1e6:.0f} M€, {len(X)} lignes ({bad} écartées) : achat et vente {lab} au lieu de la clôture du vendredi : "
                f"médiane {np.median(dlt) * 100:+.2f} point, moyenne écrêtée {tm.mean() * 100:+.2f} (écart-type {tm.std() * 100:.1f})")
        log(f"    écart clôture du vendredi → ouverture du lundi à l'achat : médiane {np.median(X[:, 3]) * 100:+.2f} %, moyenne "
            f"{X[:, 3].mean() * 100:+.2f} %")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
