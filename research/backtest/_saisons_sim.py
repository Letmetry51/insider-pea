"""Calendrier de rotation saisonnière de l'ancien outil « PEA Dashboard — Rotation Saisonnière v9 » (05/11/2026) : mois favorables et
défavorables par secteur (Tech / Industrie / Santé : défavorables décembre à février, favorables mai à juillet ; Distribution / Luxe et
Énergie : favorables octobre à décembre ; Défensif (Santé, Services publics) : favorables décembre à février), prudence en août et
septembre, et la règle « septembre-octobre exposition minimale, novembre-janvier forte conviction ». Sur les clôtures hebdomadaires
1998-2026 : rendement de chaque secteur face à la moyenne selon le mois, puis portefeuille simulé de la sélection (4 🎯 + 1 📣) avec
achats suspendus certains mois ou secteurs écartés selon le calendrier."""
import numpy as np
exec(open('_volatilite_sim.py').read().split("\nif __name__ == '__main__':")[0])

month = np.array([int(str(d)[5:7]) for d in dates])
CAL = {  # secteur Yahoo → mois favorables (+1) et défavorables (−1) du calendrier
    'Technology': ({5, 6, 7}, {12, 1, 2}), 'Industrials': ({5, 6, 7}, {12, 1, 2}), 'Healthcare': ({5, 6, 7, 12, 1, 2}, set()),
    'Consumer Cyclical': ({10, 11, 12}, set()), 'Energy': ({10, 11, 12}, set()), 'Utilities': ({12, 1, 2}, set()),
    'Consumer Defensive': ({12, 1, 2}, set()),
}


def sector_months():
    """Écart mensuel moyen de chaque secteur avec la moyenne des sociétés, mois favorables / autres / défavorables (1998-2026)"""
    print("\n=== 1. Le calendrier se vérifie-t-il ? écart mensuel moyen du secteur avec la moyenne des sociétés (points de %)")
    # rendement sur 4 semaines à partir de chaque semaine de début de mois
    starts = [t for t in range(t1997, T - 5) if month[t] != month[t - 1]]
    for sec, (good, bad) in CAL.items():
        m = secs == sec
        cells = {'favorables': [], 'défavorables': [], 'autres': []}
        for t in starts:
            g = np.prod(1 + retw[:, t + 1:t + 5], axis=1) - 1
            ok = okn[:, t] & np.isfinite(g)
            if ok.sum() < 50 or (ok & m).sum() < 5:
                continue
            e = np.nanmean(g[ok & m]) - np.nanmean(g[ok])
            mo = month[t + 1] if t + 1 < T else month[t]
            k = 'favorables' if mo in good else 'défavorables' if mo in bad else 'autres'
            cells[k].append(e)
        out = []
        for k, v in cells.items():
            if len(v) >= 10:
                v = np.array(v)
                out.append(f"{k} {v.mean() * 100:+5.2f} (t {v.mean() / (v.std(ddof=1) / np.sqrt(len(v))):4.1f}, {len(v)} mois)")
        print(f"  {sec:20s} " + " · ".join(out))


def sel_without_bad(t):
    """sélection de la semaine sans les sociétés d'un secteur dans ses mois défavorables (remplacées par les suivantes)"""
    s = pick(t, n=8, reserve=1, bondCap=2)
    mo = month[t]
    keep = [i for i in s if mo not in CAL.get(str(secs[i]), (set(), set()))[1]]
    return keep[:5]


def sel_good_first(t):
    """sociétés d'un secteur dans ses mois favorables d'abord"""
    s = pick(t, n=10, reserve=1, bondCap=2)
    mo = month[t]
    good = [i for i in s if mo in CAL.get(str(secs[i]), (set(), set()))[0]]
    rest = [i for i in s if i not in good]
    return (good + rest)[:5]


if __name__ == '__main__':
    print(f"{N} sociétés, {dates[t1997]} → {dates[-1]}")
    sector_months()
    print("\n=== 2. Achats suspendus certains mois (tranche de la semaine en liquidités à 0 %), écart avec la règle actuelle")
    B = sim_w(lambda t: 1.0)
    stats(B, "règle actuelle (achat chaque semaine)")
    for lab, months in (("pas d'achat en août et septembre (prudence estivale)", {8, 9}), ("pas d'achat en septembre et octobre", {9, 10}),
                        ("achats de novembre à avril seulement (« Sell in May »)", {5, 6, 7, 8, 9, 10})):
        stats(sim_w(lambda t, M=months: 0.0 if month[t] in M else 1.0), lab, B)
    stats(sim_w(lambda t: 1.0 if month[t] in (11, 12, 1) else .5), "demi-tranches hors novembre-janvier (forte conviction l'hiver)", B)
    print("\n=== 3. Secteurs selon le calendrier (5 lignes chaque semaine, mêmes règles)")
    globals()['SEL'] = {t: sel_without_bad(t) for t in range(t1997, T - 1)}
    stats(sim_w(lambda t: 1.0), "sans les secteurs dans leurs mois défavorables", B)
    globals()['SEL'] = {t: sel_good_first(t) for t in range(t1997, T - 1)}
    stats(sim_w(lambda t: 1.0), "secteurs dans leurs mois favorables d'abord", B)
