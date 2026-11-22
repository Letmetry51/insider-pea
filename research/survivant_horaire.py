"""Meilleur moment d'achat et de revente (22/11/2026, François : « quelle heure acheter le lundi ? … recevoir les conseils le
vendredi soir après clôture ? Dimanche ? (pour acheter lundi matin) … quel jour et heure de revente optimal ? »).

Aujourd'hui, le calcul du soir tourne les jours de semaine vers 18 h 40 (17 h 37 UTC) : la sélection part le lundi soir, achat le
mardi. Les simulations décident et achètent à la clôture du vendredi. Mesure sur les cours journaliers EODHD (ouverture et clôture
de chaque séance, ajustées) des sociétés choisies par la règle actuelle au seuil du 🎯 (3 M€ par jour), univers sans biais du
survivant de survivant_eodhd.py (sociétés disparues comprises), 2001-2026 :
1. Retard d'exécution, achat ET vente décalés d'autant (même durée de détention, 26 semaines) : clôture du vendredi (simulations),
   ouverture ou clôture du lundi, du mardi … du vendredi suivant. Écart de rendement sur 6 mois, médiane et moyenne écrêtée à 1 %,
   t de Newey-West par semaine de départ. Réponse à « email le vendredi soir (achat lundi) ou le lundi soir (achat mardi) ».
2. Moment de revente, achat fixé à l'ouverture du lundi : vente à la clôture du vendredi qui précède l'échéance, ou à l'ouverture /
   la clôture de chaque séance de la semaine de l'échéance (la durée change de quelques jours : effet de la hausse moyenne indiqué à part).
3. Écart entre plus haut et plus bas du lundi (ce qu'un mauvais moment de la journée peut coûter ; l'heure exacte demanderait des
   cours intrajournaliers, absents de la formule « Historian »).
Lignes aux ouvertures aberrantes (écart de plus de 30 % avec la clôture précédente) écartées. Règle : renseignement pratique, pas
de règle de la méthode changée. Lancé par « Recherche (à la demande) » (script survivant_horaire.py), environ 15 minutes.
"""
import concurrent.futures as cf
import gc
import time

import numpy as np
import pandas as pd

import survivant_eodhd as SE

log = SE.log
DAYS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi']


def nw(v, wk, L=26):
    """Moyenne par semaine de départ puis t de Newey-West (L retards)."""
    s = pd.Series(v).groupby(wk).mean().values
    u = s - s.mean()
    g = (u * u).sum() + sum(2 * (1 - k / (L + 1)) * (u[k:] * u[:-k]).sum() for k in range(1, L + 1))
    return s.mean(), s.mean() / np.sqrt(g / len(s) ** 2)


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, t00 = (D[k] for k in ('P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 't00'))
    G = SE.chain(P, V, dates, cols, secs, liq >= 3e6)
    del D, V
    gc.collect()
    S = {t: G['pick'](t, n=5, reserve=1, bondCap=2) for t in range(t2001, T - 1)}
    picked = sorted({i for s in S.values() for i in s})
    daily = {}

    def one(i):
        x, err = SE.get(f"eod/{cols[i]}", **{'from': '2000-06-01'})
        return i, x
    t1 = time.time()
    with cf.ThreadPoolExecutor(8) as pool:
        for i, x in pool.map(one, picked):
            if not x:
                continue
            d = np.array([b['date'] for b in x], dtype='datetime64[D]')
            f = lambda k: np.array([float(b.get(k) or 'nan') for b in x])  # noqa: E731
            c, a, o, h, lo = f('close'), f('adjusted_close'), f('open'), f('high'), f('low')
            k = np.where((c > 0) & (a > 0) & (o > 0) & (h > 0) & (lo > 0))[0]
            r = a[k] / c[k]
            daily[i] = (d[k], a[k], o[k] * r, h[k] * r, lo[k] * r)
    log(f"\ncours journaliers : {len(daily)} des {len(picked)} sociétés choisies (seuil 3 M€), en {time.time() - t1:.0f} s")
    fri = np.array([np.datetime64(x) for x in dates], dtype='datetime64[D]')

    # prix d'entrée et de sortie : 0 = clôture du vendredi, puis (jour 1..5, ouverture / clôture) de la semaine qui suit
    def legs(i, f):
        d, a, o, h, lo = daily[i]
        k = np.searchsorted(d, f, side='right')
        if k == 0 or k + 5 > len(d) or (d[k] - f).astype(int) > 4 or (d[k + 4] - f).astype(int) > 11:
            return None
        if np.any(np.abs(o[k:k + 5] / np.concatenate([[a[k - 1]], a[k:k + 4]]) - 1) > .3):
            return None
        px = {'F': a[k - 1]}
        for j in range(5):
            px[(j + 1, 'o')], px[(j + 1, 'c')] = o[k + j], a[k + j]
        px['rng'] = (h[k] - lo[k]) / o[k]
        return px
    rows, wk = [], []
    for t in range(t2001, T - 27):
        for i in S.get(t, []):
            if i not in daily:
                continue
            e, x = legs(i, fri[t]), legs(i, fri[t + 26])
            if e is None or x is None:
                continue
            rows.append((e, x))
            wk.append(t)
    wk = np.array(wk)
    log(f"lignes mesurées : {len(rows)} (achats de {len(set(wk))} semaines)")
    keys = [(j, oc) for j in range(1, 6) for oc in ('o', 'c')]
    lab = {(j, oc): f"{'ouverture' if oc == 'o' else 'clôture'} du {DAYS[j - 1]}" for j, oc in keys}

    def stat(v):
        lo_, hi_ = np.percentile(v, [1, 99])
        m, tv = nw(np.clip(v, lo_, hi_), wk)
        return f"médiane {np.median(v) * 100:+.2f}, moyenne écrêtée {m * 100:+.2f} point (t {tv:4.1f})"

    r0 = np.array([x['F'] / e['F'] - 1 for e, x in rows])
    log(f"\n1. Achat et vente décalés d'autant (26 semaines) ; référence : clôture du vendredi, 6 mois {np.mean(r0) * 100:+.1f} % en moyenne, "
        f"médiane {np.median(r0) * 100:+.1f} %. Écart avec la référence :")
    R = {}
    for k in keys:
        R[k] = np.array([x[k] / e[k] - 1 for e, x in rows])
        log(f"  {lab[k]:24s} {stat(R[k] - r0)}")
    log(f"  → email du lundi soir, achat à l'ouverture du mardi, face à un email du vendredi soir, achat à l'ouverture du lundi : "
        f"{stat(R[(2, 'o')] - R[(1, 'o')])}")

    log("\n2. Revente, achat à l'ouverture du lundi ; référence : vente à l'ouverture du lundi de la semaine 26. Écart :")
    base = np.array([x[(1, 'o')] / e[(1, 'o')] - 1 for e, x in rows])
    vf = np.array([x['F'] / e[(1, 'o')] - 1 for e, x in rows])
    log(f"  {'clôture du vendredi qui précède':38s} {stat(vf - base)}")
    for k in keys:
        if k == (1, 'o'):
            continue
        v = np.array([x[k] / e[(1, 'o')] - 1 for e, x in rows])
        log(f"  {lab[k] + ' (semaine 26)':38s} {stat(v - base)}")
    drift = np.median(base) / 126 * 100
    log(f"  (hausse moyenne de ces lignes : environ {drift:+.3f} point par séance de détention en plus)")

    rng = np.array([e['rng'] for e, _ in rows])
    log(f"\n3. Écart entre plus haut et plus bas du lundi (en % de l'ouverture) : médiane {np.median(rng) * 100:.1f} %, un lundi sur quatre "
        f"au-delà de {np.percentile(rng, 75) * 100:.1f} %")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
