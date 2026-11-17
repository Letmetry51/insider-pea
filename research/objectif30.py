"""Une seule action, objectif +30 % (17/11/2026, François : « est-ce possible que tu choisisses en autonomie l'action qui réunit le
plus de critères pour une hausse significative avec objectif de +30 % puis envoyer un mail pour l'achat et un autre pour la vente ?
(intégrer garde-fou) »).

Portefeuille simulé 1998-2026, cours hebdomadaires de backtest/_long.py (sociétés encore cotées : biais du survivant), règles de
backtest/_selection_sim.py, ordres à la clôture de la semaine, frais 0,3 % par sens, liquidités à 0 %.

- Règle actuelle (référence) : 4 🎯 + 1 📣 chaque semaine, gardés 26 semaines, protection −30 % (lignes suivies une à une,
  sim30 de proba.py).
- Demande (principale) : une seule action à la fois. Quand le compte est vide, achat de la 1re de la sélection de la semaine
  (ordre de l'outil : 🔊 avec 📣, puis 🔊, puis 📣, feu vert avant attente, puis note). Vente dès que la clôture de la semaine
  atteint +30 % (objectif), ou garde-fous : clôture à −15 % (stop), 26 semaines écoulées (durée maximale).
- Variantes : sans objectif (garder 26 semaines) ; protection −30 % au lieu du stop −15 % ; objectif +50 % ; l'action qui coche le
  plus de critères (pente forte, +60 à +200 % sur 12 mois, 🔊, 📣, feu vert, à moins de 10 % du plus haut, 📣 démarrage ; puis
  note) ; pas d'achat pendant l'alerte krach (marché −20 % sur un an, fin au-dessus de −15 %) ; même règle sur 5 lignes à la fois
  (chaque place libérée reprend la meilleure action pas encore détenue).

Règle fixée avant le calcul : la demande ne remplace la règle actuelle que si elle fait mieux dans chacune des périodes 1998-2008,
2009-2017 et 2018-2026, avec t ≥ 3 (blocs de 6 mois) ; sinon, documentée (research/README.md et aide de la page). Pour information :
effet de l'objectif seul (avec / sans objectif, même action), effet de la concentration (1 ligne contre 5).

Lancé par « Recherche (à la demande) » (script objectif30.py), environ 3 minutes.
"""
import time

import numpy as np

import figures_bougies as FB
import proba as PB

log = FB.log
ERAS3 = ('1998-2008', '2009-2017', '2018-2026')


def slots(G, choose, k=1, target=.30, stop=.15, hold=26, cost=.003, pause=None):
    """k places égales ; une place vide reprend la meilleure action pas encore détenue (choose(t) : liste ordonnée) ; sortie à
    l'objectif, au stop ou au bout de hold semaines, sur les clôtures hebdomadaires. → (rendements hebdomadaires, opérations)."""
    t1997, T, retw = G['t1997'], G['T'], G['retw']
    sv = [dict(v=1.0 / k, pos=None) for _ in range(k)]
    R, trades = [], []
    for t in range(t1997, T - 1):
        V0 = sum(s['v'] for s in sv)
        held = {s['pos']['i'] for s in sv if s['pos']}
        if not (pause is not None and pause(t)):
            cand = [i for i in choose(t) if i not in held]
            for s in sv:
                if s['pos'] is None and cand:
                    i = cand.pop(0)
                    s['pos'] = dict(i=i, t0=t, px=1.0)
                    s['v'] *= 1 - cost
                    held.add(i)
        for s in sv:
            p = s['pos']
            if p is None:
                continue
            g = retw[p['i'], t + 1]
            s['v'] *= 1 + g
            p['px'] *= 1 + g
            why = 'objectif' if p['px'] >= 1 + target else 'stop' if p['px'] <= 1 - stop else 'durée' if t + 1 - p['t0'] >= hold else None
            if why:
                s['v'] *= 1 - cost
                trades.append((p['t0'], t + 1, p['px'] - 1, why))
                s['pos'] = None
        R.append(sum(s['v'] for s in sv) / V0 - 1)
    return np.array(R), trades


def main():
    t0 = time.time()
    G = PB.load()
    t1997, T, ERAS = G['t1997'], G['T'], G['ERAS']
    SEL = G['SEL']
    log(f"données prêtes en {time.time() - t0:.0f} s")
    A = G['sim30']()

    # l'action qui coche le plus de critères (parmi les sociétés des deux paliers du 🎯), puis la note
    okn, mpn, v52, mom, trend, s26, hot, bp8, wait, dem, note = (G[k] for k in (
        'okn', 'mpn', 'v52', 'mom', 'trend', 's26', 'hot', 'bp8', 'wait', 'dem', 'note'))
    ratio = G['ratio']

    def maxcrit(t):
        ok = okn[:, t] & ~(mpn[:, t] < 1 / 3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2) & trend[:, t] & (s26[:, t] >= .14) & (mom[:, t] >= .3)
        idx = np.where(ok)[0]
        if not len(idx):
            return []
        c = ((s26[idx, t] >= .41).astype(int) + ((mom[idx, t] >= .6) & (mom[idx, t] <= 2)) + hot[idx, t] + bp8[idx, t]
             + ~wait[idx, t] + (np.nan_to_num(ratio[idx, t]) >= .9) + dem[idx, t])
        o = np.lexsort((-np.nan_to_num(note[idx, t]), -c))
        return idx[o].tolist()

    LM = np.concatenate([[0], np.cumsum(np.log1p(G['mkw']))])
    crash, on = np.zeros(T, bool), False
    for t in range(52, T):
        m52 = np.exp(LM[t + 1] - LM[t + 1 - 52]) - 1
        on = m52 <= -.20 if not on else m52 <= -.15
        crash[t] = on
    top = lambda t: list(SEL.get(t, []))  # noqa: E731

    def stats(R, tr=None):
        eq = np.cumprod(1 + R)
        cagr = eq[-1] ** (52 / len(R)) - 1
        dd = (eq / np.maximum.accumulate(eq) - 1).min()
        s = f"{cagr * 100:+6.1f} %/an, pire baisse {dd * 100:+4.0f} %"
        if tr:
            g = np.array([x[2] for x in tr])
            w = [x[3] for x in tr]
            s += (f" · {len(tr)} ventes, objectif {w.count('objectif') / len(tr) * 100:.0f} %, stop {w.count('stop') / len(tr) * 100:.0f} %, "
                  f"durée {w.count('durée') / len(tr) * 100:.0f} %, gain moyen {g.mean() * 100:+.1f} %, en perte {np.mean(g < 0) * 100:.0f} %, "
                  f"{np.mean([x[1] - x[0] for x in tr]):.0f} semaines en moyenne")
        return s

    def per(d):
        out = []
        for el, a, b in ERAS:
            if el not in ERAS3:
                continue
            x = d[a - t1997:min(b, T - 1) - t1997]
            blk = np.array([x[k:k + 26].sum() for k in range(0, len(x) - 25, 26)])
            out.append((x.mean() * 52 * 100, blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))))
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        return out, blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))

    def cagr_era(R):
        cells = []
        for el, a, b in ERAS:
            if el in ERAS3:
                x = R[a - t1997:min(b, T - 1) - t1997]
                cells.append(f"{el} {(np.prod(1 + x) ** (52 / len(x)) - 1) * 100:+.1f}")
        return ' · '.join(cells)

    log(f"\nRègle actuelle (4 🎯 + 1 📣 par semaine, 26 semaines, protection −30 %) : {stats(A)}\n  par période (%/an) : {cagr_era(A)}")
    variants = [
        ('DEMANDE : 1 action, objectif +30 %, stop −15 %, 26 semaines au plus', dict(choose=top)),
        ('même action, sans objectif (26 semaines, stop −15 %)', dict(choose=top, target=9e9)),
        ('même action, objectif +30 %, protection −30 %', dict(choose=top, stop=.30)),
        ('même action, sans objectif, protection −30 % (règles de la méthode)', dict(choose=top, target=9e9, stop=.30)),
        ('même action, objectif +50 %, stop −15 %', dict(choose=top, target=.50)),
        ("l'action qui coche le plus de critères, objectif +30 %, stop −15 %", dict(choose=maxcrit)),
        ('demande, sans achat pendant l’alerte krach', dict(choose=top, pause=lambda t: crash[t])),
        ('demande sur 5 lignes à la fois', dict(choose=top, k=5)),
        ('5 lignes à la fois, sans objectif, protection −30 %', dict(choose=top, k=5, target=9e9, stop=.30)),
    ]
    res = {}
    for k, (lab, kw) in enumerate(variants):
        R, tr = slots(G, **kw)
        res[lab] = R
        pp, tt = per(R - A)
        verdict = ''
        if k == 0:
            ok = all(x > 0 for x, _ in pp) and tt >= 3
            verdict = ' → ' + ('BAT LA RÈGLE ACTUELLE' if ok else 'REJETÉE')
        log(f"\n{lab}\n  {stats(R, tr)}\n  par période (%/an) : {cagr_era(R)}\n  écart avec la règle actuelle : "
            f"{' · '.join(f'{el} {x:+.1f} (t {y:.1f})' for el, (x, y) in zip(ERAS3, pp))} points par an, ensemble t {tt:.1f}{verdict}")
    d = res[variants[0][0]] - res[variants[1][0]]
    pp, tt = per(d)
    log("\nEffet de l'objectif +30 % seul (même action, stop −15 %) : " +
        ' · '.join(f'{el} {x:+.1f} (t {y:.1f})' for el, (x, y) in zip(ERAS3, pp)) + f" points par an, ensemble t {tt:.1f}")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
