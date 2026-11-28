"""Ordre de la sélection pour prendre les hausses plus tôt, sur 25 ans sans biais du survivant (28/11/2026).

Suite du cas Frontline (cas_frontline.py, demande de François : « détecter encore plus tôt le moment d'achat et profiter au maximum
des 117 % de hausse puis améliorer notre modèle »). Frontline est entrée dans le 🎯 le 28/11/2025, à 27 % de sa hausse (en
logarithme, creux du 27/06/2025, sommet du 09/10/2026, +264 % dividendes compris), et au palier fort dès décembre, mais classée 24e à
123e parmi 120 à 190 candidates pour 4 places : première sélection le 18/09/2026 (91 % de la hausse faite) avec la règle de base, le
12/06/2026 (63 %) en direct, une fois ses comptes devenus solides. Ses voisines pareil (Höegh Autoliners et DNO dans le 🎯 dès 13 %
et 19 % de leur hausse, jamais choisies). Sur 1 115 grandes hausses (cours doublé en un an, 2001-2026), la première sélection vient
à 73-85 % de la hausse. L'obstacle est donc l'ordre des candidates, pas leur repérage. Deux ordres testés, à règles et places
identiques (4 🎯 + 1 📣, paliers, plafond de 2 par secteur, place 📣) :
  O1. nouvelles venues d'abord : dans chaque palier, les sociétés entrées dans le 🎯 depuis 13 semaines au plus (et absentes des 13
      semaines d'avant) passent devant, puis l'ordre actuel (pente sur 6 mois la plus forte) ;
  O2. hausse sur 3 mois : dans chaque palier, classées d'abord par la hausse des 13 dernières semaines (avant la priorité 🔊 / bond,
      l'attente ⏸️, la note et la pente sur 6 mois de l'ordre actuel).
Contrôle : l'ordre actuel recopié ici retrouve la sélection de la simulation. Mesures : portefeuille simulé (tranches de 26
semaines, frais 0,3 % par sens, protection −30 %), part des grandes hausses choisies avant leur sommet et part de la hausse faite à
la première sélection, date de première sélection de Frontline. Règle fixée avant le calcul : un ordre remplace l'actuel seulement
s'il fait mieux dans chacune des 3 périodes avec t ≥ 3 (proposition à François).
Lancé par « Recherche (à la demande) » (script survivant_ordre.py), environ 15 minutes, environ 6 200 appels EODHD.
"""
import gc
import time

import numpy as np
import pandas as pd

import survivant_eodhd as SE

log = SE.log


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00 = (D[k] for k in (
        'P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00'))
    N = len(cols)
    G = SE.chain(P, V, dates, cols, secs, liq >= SE.LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn, mpn, v52, mom, trend, s26, bp8, wait, dem, hot, note = (G[k] for k in (
        'okn', 'mpn', 'v52', 'mom', 'trend', 's26', 'bp8', 'wait', 'dem', 'hot', 'note'))
    secs_ = G['secs']
    Pw = np.asarray(G['P'], float)
    mkw = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    with np.errstate(invalid='ignore', divide='ignore'):
        s13 = Pw / np.concatenate([np.full((N, 13), np.nan), Pw[:, :-13]], 1) - 1

    def tiers(t):
        ok = okn[:, t] & ~(mpn[:, t] < 1 / 3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
        t0_ = ok & trend[:, t] & (s26[:, t] >= .41) & (mom[:, t] >= .6)
        t1_ = ok & trend[:, t] & (s26[:, t] >= .14) & (mom[:, t] >= .3) & ~t0_
        promo = t1_ & bp8[:, t] & ~wait[:, t]
        return t0_ | promo, t1_ & ~promo, ok
    ZB = np.zeros((N, T), bool)
    for t in range(T - 1):
        k0, k1, _ = tiers(t)
        ZB[:, t] = k0 | k1
    cz = np.concatenate([np.zeros((N, 1), int), np.cumsum(ZB, 1)], 1)  # semaines dans le 🎯 cumulées

    def fresh(t):
        """Entrée dans le 🎯 depuis 13 semaines au plus, absente des 13 semaines d'avant."""
        a, b = max(0, t - 12), max(0, t - 25)
        return ZB[:, t] & (cz[:, a] - cz[:, b] == 0)

    def make_pick(variant):
        def pick(t, n=5, reserve=1, bondCap=2, perSec=2):
            k0, k1, ok = tiers(t)
            pri = 2 * hot[:, t] + bp8[:, t]
            fr = fresh(t) if variant == 'O1' else np.zeros(N, bool)

            def order(M):
                idx = np.where(M)[0]
                # np.lexsort : la dernière clé est la principale ; ordre actuel = priorité 🔊 / bond, puis pas en attente, puis note,
                # puis pente sur 6 mois ; O1 met les nouvelles venues devant ; O2 classe d'abord par la hausse sur 13 semaines
                keys = (-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t], -pri[idx], ~fr[idx])
                if variant == 'O2':
                    keys = keys + (-np.nan_to_num(s13[idx, t]),)
                return idx[np.lexsort(keys)]
            out, seen = [], {}
            q = order(k0).tolist() + order(k1).tolist()
            m = n - reserve
            for cap in (perSec, perSec + 1):
                for i in q:
                    if len(out) >= m:
                        break
                    if i in out or seen.get(secs_[i], 0) >= cap:
                        continue
                    seen[secs_[i]] = seen.get(secs_[i], 0) + 1
                    out.append(i)
            if reserve:
                dm = ok & dem[:, t] & ~np.isin(np.arange(N), out)
                for i in order(dm):
                    if len(out) >= n:
                        break
                    if seen.get(secs_[i], 0) >= bondCap:
                        continue
                    seen[secs_[i]] = seen.get(secs_[i], 0) + 1
                    out.append(int(i))
                for i in q:  # place 📣 sans candidate : suite de l'ordre (comme pick)
                    if len(out) >= n:
                        break
                    if i not in out and seen.get(secs_[i], 0) < perSec + 1:
                        seen[secs_[i]] = seen.get(secs_[i], 0) + 1
                        out.append(i)
            return [int(i) for i in out]
        return pick
    SEL0 = G['SEL']
    S = {}
    t0 = time.time()
    for v in ('actuel', 'O1', 'O2'):
        pk = make_pick(v)
        S[v] = {t: pk(t) for t in range(t2001, T - 1)}
    same = np.mean([S['actuel'][t] == list(SEL0.get(t, [])) for t in range(t2001, T - 1)]) * 100
    log(f"\nUnivers C : {N} sociétés ; ordres calculés en {time.time() - t0:.0f} s ; ordre actuel recopié identique à la sélection de "
        f"la simulation : {same:.1f} % des semaines")
    R = {}
    for v in S:
        G['SEL'] = S[v]
        R[v] = G['sim30']()
    G['SEL'] = SEL0
    NAMES = {'actuel': 'ordre actuel', 'O1': 'O1. nouvelles venues d\'abord', 'O2': 'O2. hausse sur 3 mois d\'abord'}

    def seg(x, a, b):
        return x[a - t2001:b - t2001]

    def an(x):
        g = np.prod(1 + x)
        return (g ** (52 / len(x)) - 1) * 100 if g > 0 else -100.0

    def dd_(x):
        e = np.cumprod(1 + x)
        return (e / np.maximum.accumulate(e) - 1).min() * 100

    def line(lab, x):
        log(f"  {lab:40s} {an(x):+5.1f} %/an, pire baisse {dd_(x):.0f} % (" +
            ' · '.join(f"{el} {an(seg(x, a, b)):+.1f} / {dd_(seg(x, a, b)):.0f} %" for el, a, b in ERAS) + ')')
    log("\nPortefeuille simulé (4 🎯 + 1 📣 par semaine, tranches de 26 semaines, frais 0,3 % par sens, protection −30 %)")
    line('société moyenne (sans frais)', mkw[t2001 + 1:T])
    for v in R:
        line(NAMES[v], R[v])
    log("Écart avec l'ordre actuel (points par an ; t sur des blocs de 26 semaines)")
    for v in ('O1', 'O2'):
        d = R[v] - R['actuel']
        sg = [seg(d, a, b).mean() * 5200 for _, a, b in ERAS]
        blk = np.array([d[j:j + 26].sum() for j in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        vd = ' → MIEUX DANS LES 3 PÉRIODES (t ≥ 3) : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejeté'
        log(f"  {NAMES[v]:40s} " + ' · '.join(f"{el} {x:+5.1f}" for (el, _, _), x in zip(ERAS, sg)) + f" ; total {d.mean() * 5200:+.1f} (t {tv:4.1f}){vd}")
    olap = {v: np.mean([len(set(S[v][t]) & set(S['actuel'][t])) / max(len(S['actuel'][t]), 1) for t in range(t2001, T - 1)]) * 100 for v in ('O1', 'O2')}
    log("  sociétés en commun avec l'ordre actuel chaque semaine : " + ' · '.join(f"{NAMES[v]} {x:.0f} %" for v, x in olap.items()))

    # grandes hausses : choisies plus tôt ?
    df = pd.DataFrame(Pw.T)
    low52 = df.rolling(53, min_periods=26).min().values.T
    fmax = df[::-1].rolling(52, min_periods=4).max()[::-1].shift(-1).values.T
    with np.errstate(invalid='ignore'):
        cand = (Pw <= low52) & (fmax >= 2 * Pw)
    eps = []
    for i in range(N):
        p = Pw[i]
        k = 0
        for w in np.where(cand[i, t2001:T - 2])[0] + t2001:
            if w < k:
                continue
            sgm = p[w:min(T - 1, w + 27)]
            if not np.isfinite(sgm).any():
                continue
            tr = w + int(np.nanargmin(sgm))
            pk = tr + int(np.nanargmax(p[tr:min(T - 1, tr + 79)]))
            if pk > tr and (okn[i, tr] or okn[i, min(tr + 4, T - 2)]):
                eps.append((i, tr, pk))
            k = pk + 1
    log(f"\nGrandes hausses (cours doublé en un an depuis un plus bas d'un an) : {len(eps)} ; choisies avant le sommet, part de la hausse "
        "faite à la première sélection (médiane) et 6 mois après la première sélection (médiane)")
    for el, a, b in ERAS:
        E = [e for e in eps if a <= e[1] < b]
        cells = []
        for v in S:
            fr_, r6 = [], []
            for i, tr, pk in E:
                fs = next((t for t in range(tr, min(pk + 1, T - 1)) if i in S[v].get(t, [])), None)
                if fs is None:
                    continue
                rise = np.log(Pw[i, pk] / Pw[i, tr])
                fr_.append(np.log(Pw[i, fs] / Pw[i, tr]) / rise)
                r6.append(Pw[i, min(fs + 26, T - 2)] / Pw[i, fs] - 1)
            cells.append(f"{NAMES[v].split(' (')[0]} {len(fr_) / max(len(E), 1) * 100:.0f} % choisies, à {np.median(fr_) * 100 if fr_ else np.nan:.0f} % "
                         f"de la hausse, puis {np.nanmedian(r6) * 100 if r6 else np.nan:+.0f} %")
        log(f"  {el} ({len(E)}) : " + ' ; '.join(cells))
    i = {c: k for k, c in enumerate(cols)}.get('FRO.OL')
    if i is not None:
        log("Frontline, première sélection depuis son entrée dans le 🎯 (28/11/2025) : " + ' ; '.join(
            f"{NAMES[v].split(' (')[0]} {next((dates[t] for t in range(int(np.searchsorted(dates, '2025-11-28')), T - 1) if i in S[v].get(t, [])), '—')}"
            for v in S))
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
