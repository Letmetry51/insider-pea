"""Protection à −30 % posée chez le courtier (ordre stop) ou appliquée à la clôture, sur 25 ans sans biais du survivant (28/11/2026).

François a choisi la « version mixte » (« Version 2 ») : l'email du lundi donne des ordres prêts à copier, et les protections à
−30 % sont posées chez le courtier pour se déclencher seules. Or la règle testée jusqu'ici (proba.SIM, sim30) vend à la clôture
de la semaine quand la ligne est à −30 % ou pire depuis l'achat, et l'alerte du soir (euro_signal/positions.py) part sur la
clôture du jour (vente le lendemain à l'ouverture). Un ordre stop, lui, se déclenche en séance, dès qu'un cours touche le seuil,
et s'exécute au seuil ou plus bas si le cours ouvre en dessous. Ce test mesure l'écart, à entrées identiques.

Univers C de survivant_eodhd.py (12 bourses de l'EEE, sociétés retirées de la cote comprises, liquidité connue à la date) ;
sélection de base de la simulation (4 🎯 + 1 📣 par semaine, sans le filtre des comptes, qui demande les comptes EODHD et ne change
pas la question) ; tranches de 26 semaines, lignes égales, frais 0,3 % par sens, comme sim30. Cours journaliers EODHD (ouverture,
plus bas, clôture, ajustés des dividendes et divisions par le rapport clôture ajustée / clôture) pour chaque société choisie au
moins une fois. Quatre façons de sortir d'une ligne avant 6 mois :
  a. clôture de la semaine à −30 % ou pire : vente à cette clôture (règle testée, sim30) ;
  b. clôture du jour à −30 % ou pire : vente le lendemain à l'ouverture (alerte du soir d'aujourd'hui) ;
  c. ordre stop à 70 % du prix d'achat : déclenché dès qu'un plus bas du jour le touche, vendu au seuil, ou à l'ouverture si elle
     est déjà en dessous (version mixte) ; c bis : mêmes règles en ignorant les plus bas suspects (sous 80 % du plus petit de
     l'ouverture et de la clôture du jour, souvent une erreur de cours) ;
  d. sans protection (pour comparer).
Contrôle : la règle a recalculée ici face à sim30 sur les cours hebdomadaires.
Règle fixée avant le calcul : l'ordre stop est déconseillé s'il fait moins bien que la règle a dans chacune des 3 périodes, avec
plus d'un point par an d'écart au total et t ≤ −2 ; sinon, il peut remplacer l'alerte du soir.
Lancé par « Recherche (à la demande) » (script survivant_stop.py), environ 25 minutes, environ 7 000 appels EODHD. Cours en
mémoire seulement ; la clé n'est jamais affichée.
"""
import concurrent.futures as cf
import gc
import time

import numpy as np

import survivant_eodhd as SE

log = SE.log
HOLD, COST, STOP = 26, .003, .70


def daily(sym):
    """Cours journaliers ajustés (dates, ouverture, plus bas, clôture) ; None si indisponibles."""
    x, err = SE.get(f'eod/{sym}', period='d', **{'from': '2000-01-01'})
    if err or not isinstance(x, list) or len(x) < 30:
        return None
    d, o, lo, c = [], [], [], []
    for b in x:
        try:
            cl, ac = float(b['close']), float(b['adjusted_close'])
            op, lw = float(b.get('open') or cl), float(b.get('low') or cl)
        except (KeyError, TypeError, ValueError):
            continue
        if not (cl > 0 and ac > 0):
            continue
        f = ac / cl
        d.append(str(b['date'])[:10])
        o.append(op * f if op > 0 else ac)
        lo.append(lw * f if lw > 0 else ac)
        c.append(ac)
    if len(d) < 30:
        return None
    o, c = np.array(o), np.array(c)
    return np.array(d, dtype='datetime64[D]'), o, np.minimum(np.minimum(np.array(lo), o), c), c


def line_paths(Dd, i, t, d64, T):
    """Chemin hebdomadaire de la valeur d'une ligne (1 à l'achat, clôture du vendredi t) selon chaque règle de sortie :
    {règle: (px[0..26], semaine de sortie ou None)} ; None sans cours journaliers à l'achat."""
    if i not in Dd:
        return None
    dd, o, lo, c = Dd[i]
    end = min(t + HOLD, T - 1)
    fri = [int(np.searchsorted(dd, d64[w], side='right')) - 1 for w in range(t, end + 1)]
    if fri[0] < 0:
        return None
    e = c[fri[0]]
    out = {}
    # a. clôture de la semaine
    px = np.array([c[k] / e if k >= 0 else 1.0 for k in fri])
    ex = None
    for w in range(1, len(px)):
        if px[w] <= STOP:
            ex = w
            px[w + 1:] = px[w]
            break
    out['a'] = (px, ex)
    # d. sans protection
    out['d'] = (np.array([c[k] / e if k >= 0 else 1.0 for k in fri]), None)
    a, b = fri[0] + 1, fri[-1] + 1  # séances après l'achat, jusqu'au dernier vendredi
    for rule in ('b', 'c', 'c2'):
        px = out['d'][0].copy()
        ex = None
        if b > a:
            if rule == 'b':
                hit = np.where(c[a:b] <= STOP * e)[0]
                if len(hit):
                    k = a + hit[0] + 1  # vente le lendemain à l'ouverture
                    k = min(k, len(c) - 1)
                    val = (o[k] if k > a + hit[0] else c[k]) / e
            else:
                lw = lo[a:b]
                if rule == 'c2':
                    lw = np.where(lw < .8 * np.minimum(o[a:b], c[a:b]), np.minimum(o[a:b], c[a:b]), lw)
                hit = np.where(lw <= STOP * e)[0]
                if len(hit):
                    k = a + hit[0]
                    val = min(o[k], STOP * e) / e
            if len(hit):
                w = int(np.searchsorted(np.array(fri), k, side='left'))  # semaine où tombe la vente
                w = max(1, min(w, len(px) - 1))
                px[w:] = val
                ex = w
        out[rule] = (px, ex)
    return out


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00, dl, rows = (D[k] for k in (
        'P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00', 'dl', 'rows'))
    N = len(cols)
    t0 = time.time()
    G = SE.chain(P, V, dates, cols, secs, liq >= SE.LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    mkw = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    SEL = G['SEL']
    R_sim = G['sim30']()
    d64 = np.array(dates, dtype='datetime64[D]')
    log(f"\nUnivers C : {N} sociétés, sélection calculée en {time.time() - t0:.0f} s")
    picked = sorted({int(i) for t in range(t2001, T - 1) for i in SEL.get(t, [])})
    log(f"sociétés choisies au moins une fois depuis 2001 : {len(picked)}")
    Dd, miss = {}, 0
    t1 = time.time()
    with cf.ThreadPoolExecutor(8) as pool:
        for i, x in zip(picked, pool.map(lambda i: daily(rows[i]['sym']), picked)):
            if x is None:
                miss += 1
            else:
                Dd[i] = x
    log(f"cours journaliers : {len(Dd)} sociétés en {time.time() - t1:.0f} s ; indisponibles : {miss}")

    RULES = ('a', 'b', 'c', 'c2', 'd')
    NAMES = {'a': 'a. clôture de la semaine (règle testée)', 'b': 'b. clôture du jour, vente le lendemain',
             'c': 'c. ordre stop chez le courtier', 'c2': 'c bis. ordre stop, plus bas suspects ignorés', 'd': 'd. sans protection'}
    R = {r: np.zeros(T - 1 - t2001) for r in RULES}
    nlines, nexit, nfall = 0, {r: 0 for r in RULES}, 0
    wh = []  # lignes vendues par l'ordre stop mais pas par la règle a : valeur à 6 mois sans vente, et valeur de vente
    for t in range(t2001, T - 1):
        s = list(SEL.get(t, []))
        if not s:
            continue
        k = len(s)
        q = 1.0 / k
        for r in RULES:
            R[r][t - t2001] -= COST
        for i in s:
            paths = line_paths(Dd, i, t, d64, T)
            nlines += 1
            if paths is None:  # pas de cours journaliers : même chemin hebdomadaire que sim30 pour toutes les règles
                nfall += 1
                full = np.cumprod(np.concatenate([[1.0], 1 + retw[i, t + 1:min(t + HOLD, T - 1) + 1]]))
                px = full.copy()
                ex = next((w for w in range(1, len(px)) if px[w] <= STOP), None)
                if ex is not None:
                    px[ex + 1:] = px[ex]
                paths = {r: (px, ex) for r in RULES if r != 'd'}
                paths['d'] = (full, None)
            for r in RULES:
                px, ex = paths[r]
                for w in range(1, len(px)):
                    tt = t + w - 1 - t2001  # rendement de la semaine t+w-1 → t+w, compté à la semaine t+w-1 comme sim30
                    if tt >= len(R[r]):
                        break
                    R[r][tt] += q * (px[w] - px[w - 1])
                    if ex is not None and w == ex:
                        R[r][tt] -= q * px[w] * COST
                        break
                    if w == len(px) - 1 and ex is None:
                        R[r][tt] -= q * px[w] * COST
                if ex is not None:
                    nexit[r] += 1
            pa, pc = paths['a'], paths['c']
            if pc[1] is not None and pa[1] is None:
                wh.append((paths['d'][0][-1], pc[0][-1]))
    for r in RULES:
        R[r] /= HOLD

    def seg(x, a, b):
        return x[a - t2001:b - t2001]
    an = lambda x: (np.prod(1 + x) ** (52 / len(x)) - 1) * 100  # noqa: E731

    def dd_(x):
        e = np.cumprod(1 + x)
        return (e / np.maximum.accumulate(e) - 1).min() * 100

    def line(lab, x):
        log(f"  {lab:46s} {an(x):+5.1f} %/an, pire baisse {dd_(x):.0f} % (" +
            ' · '.join(f"{el} {an(seg(x, a, b)):+.1f} / {dd_(seg(x, a, b)):.0f} %" for el, a, b in ERAS) + ')')

    def cmp(x, ref):
        d = x - ref
        sg = [seg(d, a, b).mean() * 5200 for _, a, b in ERAS]
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        with np.errstate(invalid='ignore', divide='ignore'):
            return sg, d.mean() * 5200, blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))

    log("\nPortefeuille simulé (4 🎯 + 1 📣 par semaine, tranches de 26 semaines, frais 0,3 % par sens) : %/an et pire baisse")
    line('contrôle : sim30 (cours hebdomadaires)', R_sim)
    line('société moyenne (sans frais)', mkw[t2001 + 1:T])
    for r in RULES:
        line(NAMES[r], R[r])
    log(f"\nLignes : {nlines} (dont {nfall} sans cours journaliers, chemin hebdomadaire) ; vendues avant 6 mois par la protection : " +
        ' · '.join(f"{r} {nexit[r] / max(nlines, 1) * 100:.1f} %" for r in RULES if r != 'd'))
    if wh:
        w = np.array(wh)
        log(f"Lignes vendues par l'ordre stop mais gardées par la règle a : {len(w)} ; valeur à 6 mois si gardée {np.mean(w[:, 0]):.2f}, "
            f"vendue {np.mean(w[:, 1]):.2f} (1 = prix d'achat) ; remontées au-dessus du prix d'achat à 6 mois : {np.mean(w[:, 0] >= 1) * 100:.0f} %")
    log("\nÉcart avec la règle a (points par an ; t sur des blocs de 26 semaines)")
    verdict = None
    for r in ('b', 'c', 'c2', 'd'):
        sg, tot, tv = cmp(R[r], R['a'])
        log(f"  {NAMES[r]:46s} " + ' · '.join(f"{el} {x:+5.1f}" for (el, _, _), x in zip(ERAS, sg)) + f" ; total {tot:+.1f} (t {tv:4.1f})")
        if r == 'c':
            bad = all(x < 0 for x in sg) and tot < -1 and tv <= -2
            verdict = ("→ L'ORDRE STOP EST DÉCONSEILLÉ : garder l'alerte du soir et vendre à la main" if bad else
                       "→ l'ordre stop chez le courtier peut remplacer l'alerte du soir")
    log(verdict)
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
