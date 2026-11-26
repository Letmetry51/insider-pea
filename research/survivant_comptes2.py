"""Suite de survivant_comptes.py (26/11/2026) : le filtre « comptes solides » faisait mieux que l'absence de filtre sur 2001-2008
(+3,2 points par an) et 2009-2017 (+0,9), moins bien sur 2018-2026 (−6,5). Or avant 2016, EODHD a surtout les comptes des sociétés
encore cotées (18 à 44 % des sociétés disparues ont des comptes, 81 à 100 % des cotées) : « comptes pas lus » voulait alors souvent
dire « société qui va disparaître », et le filtre, qui les met au palier 2, en profitait sans rien savoir de leurs comptes. Deux
contrôles à couverture égale, règle de décision inchangée (le filtre n'est retiré que si l'absence de filtre fait mieux dans chacune
des 3 périodes avec t ≥ 3) :
  1. comptes pas lus comptés comme solides : le filtre ne joue plus que sur les verdicts (mitigés et banques au palier 2,
     dégradation écartée, 📣 seulement solides ou pas lus) ;
  2. univers réduit, chaque semaine, aux sociétés dont les comptes sont lus à la date : sélection avec et sans filtre.
Lancé par « Recherche (à la demande) » (script survivant_comptes2.py), environ 15 minutes, mêmes appels EODHD que
survivant_comptes.py. Cours et comptes restent en mémoire.
"""
import gc
import time

import numpy as np

import revue_pistes as RP
import survivant_comptes as SC
import survivant_eodhd as SE

log = SE.log


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00 = (D[k] for k in ('P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00'))
    F = SC.fundamentals(cols)
    A = SC.verdicts(F, cols, secs, dates, T)
    del F
    G = SE.chain(P, V, dates, cols, secs, liq >= SE.LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    G['mkw'] = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    SEL0 = G['SEL']
    t0 = time.time()

    def run(Gx, f):
        """Sélection de f (qui peut venir d'un univers réduit, Gx) jouée par sim30, qui lit SEL dans G (son espace d'exécution)."""
        S = {t: f(t) for t in range(t2001, T - 1)}
        G['SEL'] = S
        R = G['sim30']()
        G['SEL'] = SEL0
        return R

    def cagr(R):
        return ' · '.join(f"{el} {(np.prod(1 + R[a - t2001:b - t2001]) ** (52 / (b - a)) - 1) * 100:+.1f}" for el, a, b in ERAS)
    an = lambda R: (np.prod(1 + R) ** (52 / len(R)) - 1) * 100  # noqa: E731

    def cmp(R, ref):
        d = R - ref
        cells, sg = [], []
        for el, a, b in ERAS:
            x = d[a - t2001:b - t2001].mean() * 5200
            cells.append(f"{el} {x:+5.1f}")
            sg.append(x)
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        return cells, sg, blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))

    def verdict(sg, tv):
        return ('le filtre aide (meilleur dans chaque période)' if all(x > 0 for x in sg) else
                'LE FILTRE NUIT : à proposer à François (le retirer)' if all(x < 0 for x in sg) and tv <= -3 else 'pas tranché')
    pick = RP.make_pick(G)
    none_ = run(G, lambda t: pick(t))
    live = run(G, lambda t: pick(t, A=A, mode='live'))
    A1 = A.copy()
    A1[A1 == 0] = 1
    live_na = run(G, lambda t: pick(t, A=A1, mode='live'))
    log(f"\nSans filtre {an(none_):+.1f} %/an ({cagr(none_)}) ; filtre en direct {an(live):+.1f} %/an ({cagr(live)})")
    c, sg, tv = cmp(live_na, none_)
    log(f"1. Pas lus comptés comme solides : {an(live_na):+.1f} %/an ({cagr(live_na)}) ; face à l'absence de filtre "
        f"{' · '.join(c)} pts/an (t {tv:4.1f}) → {verdict(sg, tv)}")
    G2 = dict(G, okn=okn & (A > 0))
    pick2 = RP.make_pick(G2)
    n2 = run(G2, lambda t: pick2(t))
    l2 = run(G2, lambda t: pick2(t, A=A, mode='live'))
    c, sg, tv = cmp(l2, n2)
    log(f"2. Sociétés aux comptes lus seulement : sans filtre {an(n2):+.1f} %/an ({cagr(n2)}) ; filtre {an(l2):+.1f} %/an ({cagr(l2)}) ; "
        f"filtre − sans filtre {' · '.join(c)} pts/an (t {tv:4.1f}) → {verdict(sg, tv)}")
    log(f"\nterminé en {time.time() - t00:.0f} s (simulations {time.time() - t0:.0f} s) ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
