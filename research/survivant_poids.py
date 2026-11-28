"""Répartition de la sélection selon le potentiel, face aux lignes égales, sur 25 ans sans biais du survivant (28/11/2026).

François : « au lieu de proposer des montants, proposer un pourcentage de répartition pour chaque action proposée avec plus gros
pourcentage pour les actions avec plus gros potentiel de hausse ». La règle actuelle met des lignes égales (4 🎯 + 1 📣 par semaine,
plus 2 💎 dans le dosage 70 / 30). Le potentiel affiché par l'outil est celui des analystes (objectif de cours moyen face au cours) :
sans historique (Yahoo et EODHD ne donnent que l'objectif du jour), il ne peut pas être testé sur 25 ans. Testé ici, à sélections
identiques (univers C, 12 bourses de l'EEE, sociétés retirées de la cote comprises ; sélection de base 4 🎯 + 1 📣 ; tranches de 26
semaines, frais 0,3 % par sens, protection −30 % comme sim30) :
  W0. lignes égales (règle actuelle) ;
  W1. selon le rang de la sélection, l'estimation du potentiel par l'outil : les 4 🎯 à 32 / 24 / 16 / 8 %, la place 📣 à 20 % ;
  W2. selon la force du momentum (hausse sur 12 mois, au moins 10 %), une ligne à 40 % au plus ;
  W3. pour comprendre : à l'inverse du momentum (le potentiel des analystes est le plus faible pour les plus fortes hausses :
      corrélation −0,14 sur 766 sociétés le 27/11/2026, potentiel médian +12 % pour +31 à +51 % sur un an, +26 % pour les baisses).
Contrôle : W0 recalculé ici retrouve sim30. Règle fixée avant le calcul : une répartition remplace les lignes égales seulement si elle
fait mieux dans chacune des 3 périodes avec t ≥ 3. Lancé par « Recherche (à la demande) » (script survivant_poids.py), environ 10
minutes, environ 6 200 appels EODHD. Cours en mémoire seulement ; la clé n'est jamais affichée.
"""
import gc
import time

import numpy as np

import survivant_eodhd as SE

log = SE.log


def sim30w(G, SEL, wfn, hold=26, cost=.003, stop=.70):
    """sim30 (proba.SIM) avec des parts wfn(t, s) au lieu de lignes égales."""
    retw, T, t0 = G['retw'], G['T'], G['t1997']
    tranches, R = [], []
    for t in range(t0, T - 1):
        r = 0.0
        s = list(SEL.get(t, []))
        if s:
            w = wfn(t, s)
            tranches.append([t, [[i, q, 1.0] for i, q in zip(s, w)]])
            r -= cost
        keep = []
        for tr in tranches:
            ts, lines = tr
            for ln in lines:
                i, q, px = ln
                if not q:
                    continue
                px1 = px * (1 + retw[i, t + 1])
                r += q * (px1 - px)
                ln[2] = px1
                if px1 <= stop:
                    r -= q * px1 * cost
                    ln[1] = 0
            if t - ts + 1 >= hold:
                for ln in lines:
                    if ln[1]:
                        r -= ln[1] * ln[2] * cost
            else:
                keep.append(tr)
        tranches = keep
        R.append(r / hold)
    return np.array(R)


def capped(w, cap=.40):
    w = np.asarray(w, float)
    w = w / w.sum()
    for _ in range(10):
        over = w > cap
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        free = ~over
        if not free.any():
            break
        w[free] += excess * w[free] / w[free].sum()
    return list(w / w.sum())


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00 = (D[k] for k in (
        'P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00'))
    t0 = time.time()
    G = SE.chain(P, V, dates, cols, secs, liq >= SE.LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    mkw = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    SEL, mom = G['SEL'], G['mom']
    R_sim = G['sim30']()
    log(f"\nUnivers C : {len(cols)} sociétés, sélection calculée en {time.time() - t0:.0f} s")
    RANK = [.32, .24, .16, .08, .20]

    def w0(t, s):
        return [1 / len(s)] * len(s)

    def w1(t, s):
        w = RANK[:len(s)]
        return list(np.array(w) / sum(w))

    def w2(t, s):
        return capped([max(float(np.nan_to_num(mom[i, t], nan=.1)), .1) for i in s])

    def w3(t, s):
        return capped([1 / max(float(np.nan_to_num(mom[i, t], nan=.1)), .1) for i in s])
    R = {k: sim30w(G, SEL, f) for k, f in (('W0', w0), ('W1', w1), ('W2', w2), ('W3', w3))}
    NAMES = {'W0': 'W0. lignes égales (règle actuelle)', 'W1': 'W1. selon le rang de la sélection',
             'W2': 'W2. selon la force du momentum', 'W3': "W3. à l'inverse du momentum (pour comprendre)"}

    def seg(x, a, b):
        return x[a - t2001:b - t2001]

    def an(x):
        g = np.prod(1 + x)
        return (g ** (52 / len(x)) - 1) * 100 if g > 0 else -100.0

    def dd_(x):
        e = np.cumprod(1 + x)
        return (e / np.maximum.accumulate(e) - 1).min() * 100

    def line(lab, x):
        log(f"  {lab:44s} {an(x):+5.1f} %/an, pire baisse {dd_(x):.0f} % (" +
            ' · '.join(f"{el} {an(seg(x, a, b)):+.1f} / {dd_(seg(x, a, b)):.0f} %" for el, a, b in ERAS) + ')')

    log("\nPortefeuille simulé (4 🎯 + 1 📣 par semaine, tranches de 26 semaines, frais 0,3 % par sens, protection −30 %)")
    line('contrôle : sim30', R_sim)
    line('société moyenne (sans frais)', mkw[t2001 + 1:T])
    for k in R:
        line(NAMES[k], R[k])
    log(f"  contrôle W0 = sim30 : écart maximal {np.abs(R['W0'] - R_sim).max():.2e} par semaine")
    w2s = [w2(t, list(SEL[t])) for t in range(t2001, T - 1, 13) if len(SEL.get(t, [])) == 5]
    log(f"  W2, part de la plus grosse ligne : médiane {np.median([max(w) for w in w2s]) * 100:.0f} %, "
        f"la plus petite {np.median([min(w) for w in w2s]) * 100:.0f} %")
    log("\nÉcart avec les lignes égales (points par an ; t sur des blocs de 26 semaines)")
    for k in ('W1', 'W2', 'W3'):
        d = R[k] - R['W0']
        sg = [seg(d, a, b).mean() * 5200 for _, a, b in ERAS]
        blk = np.array([d[j:j + 26].sum() for j in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        v = ' → MIEUX DANS LES 3 PÉRIODES (t ≥ 3) : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejetée'
        log(f"  {NAMES[k]:44s} " + ' · '.join(f"{el} {x:+5.1f}" for (el, _, _), x in zip(ERAS, sg)) + f" ; total {d.mean() * 5200:+.1f} (t {tv:4.1f}){v}")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
