"""Pistes pour la revue du 31/01/2027 (22/11/2026, François : « Faire ce qui est pertinent », après la liste des pistes restantes).

1. Filtre « comptes solides » du 🎯. En direct (ES.pickThree), une société n'entre aux paliers 0 et 1 que si ses comptes sont
   solides ; comptes mitigés, pas encore lus, banques et assurances au palier 2 ; comptes en dégradation écartés ; 📣 seulement avec
   des comptes solides. Les tests 1998-2026 ont tous tourné sans ce filtre, faute de comptes anciens. Mesuré ici de mai 2024 à
   mai 2026 (2 exercices connus au moins) avec les comptes Yahoo (data/financials.json, 4 exercices) tels que le calcul du soir les
   aurait lus à chaque date (comptes_dates.js : même verdict, comptes pris 120 jours après la clôture) : écart à 6 mois des
   sociétés de la zone du 🎯 selon leurs comptes ; sélection de 5 lignes avec le filtre, sans, sans les seuls comptes en
   dégradation, ou avec les seuls comptes solides ; portefeuille simulé sur la même période.
2. Délai de lecture des comptes : 120 jours après la clôture (règle actuelle), 90 ou 60 jours.
3. Garder une ancienne 🎯 en consolidation (piste de backtest/_reprise.py : +6,4 points à 6 mois, t 3,6, mais sous la moyenne du
   🎯). À l'échéance des 6 mois, une ligne encore forte (tiers haut sur 12 mois, tendance, +60 à +200 %, pas ⚡) et au-dessus de sa
   moyenne 10 semaines, dont seule la pente est retombée sous +41 %, est gardée 6 mois de plus au lieu d'être vendue ; variante :
   garder toute ligne encore forte, pente comprise. Référence réaliste : la règle actuelle sans vendre puis racheter la même
   semaine une ligne que la sélection reprend (frais évités, mêmes lignes). Portefeuilles simulés de 5 et 10 lignes, 1998-2026.

Règle fixée avant le calcul : (3) ne remplace la règle actuelle que si elle fait mieux dans chacune des périodes 1998-2008,
2009-2017 et 2018-2026, avec t ≥ 3 (blocs de 26 semaines). (1) et (2) ne couvrent que 2 ans : résultat indicatif pour la revue,
sans changement de règle (l'outil exige les 3 périodes).
Lancé par « Recherche (à la demande) » (script revue_pistes.py), environ 10 minutes.
"""
import json
import subprocess
import time

import numpy as np

import cycle_secteurs as CS
import figures_bougies as FB
import proba as PB

log = FB.log
ERAS3 = ('1998-2008', '2009-2017', '2018-2026')
CODES = {'na': 0, 'good': 1, 'mixed': 2, 'bad': 3, 'fin': 4}
NAMES = {1: 'solides', 2: 'mitigés', 3: 'en dégradation', 0: 'pas encore lus', 4: 'banques et assurances'}


def acc_arrays(G):
    """Verdict des comptes de chaque société à chaque semaine, pour 120, 90 et 60 jours de délai (codes de CODES)."""
    r = subprocess.run(['node', 'comptes_dates.js'], capture_output=True, text=True, timeout=900)
    log('  ' + (r.stdout.strip() or r.stderr.strip()[-300:]))
    if r.returncode:
        raise RuntimeError('comptes_dates.js a échoué')
    D = json.load(open('out/comptes_dates.json'))
    cols = [str(c) for c in G['cols']]
    dates = np.array([str(d) for d in G['dates']])
    N, T = len(cols), len(dates)
    A = {L: np.zeros((N, T), np.int8) for L in (120, 90, 60)}
    hit = 0
    for j, c in enumerate(cols):
        x = D.get(c)
        if not x:
            continue
        hit += 1
        for L in A:
            for d, v in x[str(L)]:
                A[L][j, int(np.searchsorted(dates, d, side='left')):] = CODES.get(v, 0)
    return A, hit


def make_pick(G):
    """Copie de pick() (backtest/_selection_sim.py, comme cycle_secteurs.make_pick), avec les comptes en plus (mode)."""
    okn, mpn, v52, mom, trend, s26 = (G[k] for k in ('okn', 'mpn', 'v52', 'mom', 'trend', 's26'))
    bp8, wait, dem, hot, note, secs, N = (G[k] for k in ('bp8', 'wait', 'dem', 'hot', 'note', 'secs', 'N'))

    def pick(t, A=None, mode=None, n=5, reserve=1, bondCap=2, perSec=2):
        a = A[:, t] if A is not None else np.zeros(N, np.int8)
        good, bad = a == 1, a == 3
        ok = okn[:, t] & ~(mpn[:, t] < 1 / 3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
        strong = trend[:, t] & (s26[:, t] >= .41)
        mid = trend[:, t] & (s26[:, t] >= .14)
        bump = bp8[:, t]
        t0 = ok & strong & (mom[:, t] >= .6)
        t1 = ok & mid & (mom[:, t] >= .3) & ~t0
        promo = t1 & bump & ~wait[:, t]
        tier0, tier1, tier2 = t0 | promo, t1 & ~promo, np.zeros(N, bool)
        if mode == 'live':  # ES.pickThree : solides aux paliers 0 et 1, mitigés / pas lus / banques au palier 2, dégradation écartée
            tier2 = (tier0 | tier1) & ~good & ~bad
            tier0, tier1 = tier0 & good, tier1 & good
        elif mode == 'sans_mauvais':
            tier0, tier1 = tier0 & ~bad, tier1 & ~bad
        elif mode == 'solides_seuls':
            tier0, tier1 = tier0 & good, tier1 & good
        pri = 2 * hot[:, t] + bump

        def order(M):
            idx = np.where(M)[0]
            keys = (-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t], -pri[idx])
            return idx[np.lexsort(keys)]
        out, seen = [], {}
        q = order(tier0).tolist() + order(tier1).tolist() + order(tier2).tolist()
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
            if mode in ('live', 'solides_seuls'):
                dm = dm & good
            elif mode == 'sans_mauvais':
                dm = dm & ~bad
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


def slots(G, base, a, b, n=5, hold=26, cost=.003, keep=None):
    """Tranches de 26 semaines (comme cycle_secteurs.weekly_slots) de la semaine a à b. À l'échéance d'une tranche, les lignes
    pour lesquelles keep(i, t) est vrai passent dans la nouvelle tranche sans frais ; la sélection complète les places.
    Renvoie (rendements hebdomadaires, nombre moyen de lignes achetées par semaine)."""
    retw = G['retw']
    sleeves, R, bought = [], [], []
    for t in range(a, b):
        exp = [x for x in sleeves if t - x[0] >= hold]
        sleeves = [x for x in sleeves if t - x[0] < hold]
        pk = list(base(t))
        kept = []
        if keep is not None:
            for x in exp:
                for i in x[1]:
                    if i not in kept and keep(int(i), t, pk):
                        kept.append(int(i))
        kept = kept[:n]
        new = [i for i in pk if i not in kept][:n - len(kept)]
        s = np.array(kept + new, dtype=int)
        sleeves.append([t, s, np.ones(len(s)) / n])
        r = 0.0
        for x in sleeves:
            if len(x[1]):
                rr = retw[x[1], t + 1]
                r += (x[2] * rr).sum()
                x[2] = x[2] * (1 + rr)
        R.append(r / hold - cost * 2 * (len(new) / n) / hold)
        bought.append(len(new))
    return np.array(R), float(np.mean(bought))


def nw_t(d, L=26):
    """Moyenne et t de Newey-West (L retards) d'une série hebdomadaire."""
    d = d[np.isfinite(d)]
    u = d - d.mean()
    s = (u * u).sum()
    for k in range(1, L + 1):
        s += 2 * (1 - k / (L + 1)) * (u[k:] * u[:-k]).sum()
    return d.mean(), d.mean() / np.sqrt(s / len(d) ** 2)


def main():
    t0 = time.time()
    G = PB.load()
    t1997, T, ERAS, retw, okn, SEL, N = (G[k] for k in ('t1997', 'T', 'ERAS', 'retw', 'okn', 'SEL', 'N'))
    dates = np.array([str(d) for d in G['dates']])
    log(f"données prêtes en {time.time() - t0:.0f} s")
    pick = make_pick(G)
    same = all(pick(t) == list(SEL[t]) for t in range(t1997, T - 1, 13))
    log(f"copie de la sélection identique à l'originale : {same}")

    # forward 26 semaines, écrêté comme les autres études
    with np.errstate(all='ignore'):
        Lr = np.log1p(np.where(np.isfinite(retw), retw, 0.0))
        C = np.concatenate([np.zeros((N, 1)), np.cumsum(Lr, 1)], 1)

    def fw(t):
        return np.clip(np.expm1(C[:, t + 27] - C[:, t + 1]), -.95, 5)

    # ------------------------------------------------------------------ 1 et 2. comptes
    try:
        A, hit = acc_arrays(G)
    except Exception as e:  # Node ou données absents : les sections 1 et 2 sont sautées, la 3 continue
        log(f"comptes indisponibles ({type(e).__name__} {e}) : sections 1 et 2 sautées")
        A = None
    if A is not None:
        w0 = int(np.searchsorted(dates, '2024-05-01'))
        w1 = T - 27
        log(f"\n1. Comptes solides et 🎯, départs du {dates[w0]} au {dates[w1 - 1]} ({w1 - w0} semaines, comptes lus pour {hit} "
            f"des {N} sociétés)")
        A120 = A[120]
        cnt = {k: 0 for k in NAMES}
        for t in range(w0, w1):
            for i in SEL.get(t, []):
                cnt[int(A120[i, t])] += 1
        tot = sum(cnt.values())
        log("  comptes des sociétés choisies par la règle sans les comptes : " +
            ' · '.join(f"{NAMES[k]} {cnt[k] / tot * 100:.0f} %" for k in (1, 2, 3, 0, 4)))
        # a. zone du 🎯 (paliers 0 et 1 sans les comptes) : écart à 6 mois selon les comptes, une moyenne par semaine
        okn_, mpn, v52, mom, trend, s26 = (G[k] for k in ('okn', 'mpn', 'v52', 'mom', 'trend', 's26'))
        rows = {k: [] for k in NAMES}
        dgood, dbad = [], []
        for t in range(w0, w1):
            ok = okn_[:, t] & ~(mpn[:, t] < 1 / 3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
            Z = ok & trend[:, t] & (s26[:, t] >= .14) & (mom[:, t] >= .3)
            f = fw(t)
            m = np.nanmean(f[okn_[:, t]])
            a = A120[:, t]
            for k in NAMES:
                s = Z & (a == k)
                rows[k].append(np.nanmean(f[s]) - m if s.sum() >= 3 else np.nan)
            g, ng = Z & (a == 1), Z & (a != 1)
            dgood.append(np.nanmean(f[g]) - np.nanmean(f[ng]) if g.sum() >= 3 and ng.sum() >= 3 else np.nan)
            b_, nb = Z & (a == 3), Z & (a != 3)
            dbad.append(np.nanmean(f[b_]) - np.nanmean(f[nb]) if b_.sum() >= 3 and nb.sum() >= 3 else np.nan)
        log("  zone du 🎯, écart avec la moyenne des sociétés à 6 mois, selon les comptes :")
        for k in (1, 2, 3, 0, 4):
            x = np.array(rows[k])
            n_ = int(np.isfinite(x).sum())
            log(f"    comptes {NAMES[k]:22s} {np.nanmean(x) * 100:+5.1f} points ({n_} semaines)" if n_ else
                f"    comptes {NAMES[k]:22s} —")
        m_, tv = nw_t(np.array(dgood))
        log(f"    solides − les autres : {m_ * 100:+5.1f} points (t {tv:4.1f})")
        m_, tv = nw_t(np.array(dbad))
        log(f"    en dégradation − les autres : {m_ * 100:+5.1f} points (t {tv:4.1f})")

        # b. sélections de 5 lignes : écart à 6 mois des lignes choisies, et portefeuille simulé
        def e_of(f_pick):
            e = []
            for t in range(w0, w1):
                s = f_pick(t)
                f = fw(t)
                e.append(np.nanmean(f[s]) - np.nanmean(f[okn_[:, t]]) if s else np.nan)
            return np.array(e)
        VAR = [('sans les comptes (tests 1998-2026)', lambda t: list(SEL.get(t, []))),
               ('avec le filtre, comme en direct (120 jours)', lambda t: pick(t, A=A[120], mode='live')),
               ('seulement sans les comptes en dégradation', lambda t: pick(t, A=A[120], mode='sans_mauvais')),
               ('seulement des comptes solides', lambda t: pick(t, A=A[120], mode='solides_seuls')),
               ('avec le filtre, comptes lus à 90 jours', lambda t: pick(t, A=A[90], mode='live')),
               ('avec le filtre, comptes lus à 60 jours', lambda t: pick(t, A=A[60], mode='live'))]
        E = {lab: e_of(f) for lab, f in VAR}
        live = E[VAR[1][0]]
        yrs = [('mai-déc. 2024', '2024-05-01', '2025-01-01'), ('2025', '2025-01-01', '2026-01-01'), ('janv.-mai 2026', '2026-01-01', '2027-01-01')]
        ww = dates[w0:w1]
        log("\n  sélection de 5 lignes chaque semaine, écart des lignes choisies à 6 mois (différence avec le filtre actuel, t de "
            "Newey-West)")
        for lab, _ in VAR:
            e = E[lab]
            cells = ' · '.join(f"{y} {np.nanmean(e[(ww >= a) & (ww < b)]) * 100:+5.1f}" for y, a, b in yrs)
            if lab == VAR[1][0]:
                log(f"    {lab:46s} {np.nanmean(e) * 100:+5.1f} · {cells}")
            else:
                m_, tv = nw_t(e - live)
                log(f"    {lab:46s} {np.nanmean(e) * 100:+5.1f} ({m_ * 100:+5.1f}, t {tv:4.1f}) · {cells}")
        log(f"\n  portefeuille simulé sur la même période ({dates[w0]} → {dates[T - 2]}, 5 lignes, 26 semaines, frais compris)")
        Rl, _ = slots(G, VAR[1][1], w0, T - 1)
        for lab, f in VAR:
            R, nb = slots(G, f, w0, T - 1)
            ann = (np.prod(1 + R) ** (52 / len(R)) - 1) * 100
            if lab == VAR[1][0]:
                log(f"    {lab:46s} {ann:+6.1f} %/an")
            else:
                m_, tv = nw_t(R - Rl)
                log(f"    {lab:46s} {ann:+6.1f} %/an (écart {m_ * 5200:+5.1f} pts/an, t {tv:4.1f})")

    # ------------------------------------------------------------------ 3. garder une ancienne 🎯 en consolidation
    okn_, mpn, v52, mom, trend, s26, P, m10 = (G[k] for k in ('okn', 'mpn', 'v52', 'mom', 'trend', 's26', 'P', 'm10'))
    with np.errstate(invalid='ignore'):
        strongx = okn_ & (mpn >= 2 / 3) & trend & (mom >= .6) & (mom <= 2) & ~(v52 >= .8) & (P >= m10)
        flat = strongx & (s26 < .41)
    K = {'reprise': lambda i, t, pk: i in pk,
         'consolidation': lambda i, t, pk: i in pk or bool(flat[i, t]),
         'forte': lambda i, t, pk: i in pk or bool(strongx[i, t])}
    eras = [(el, a, min(b, T - 1)) for el, a, b in ERAS if el in ERAS3]

    def cagr(R):
        out = []
        for el, a, b in eras:
            x = R[a - t1997:b - t1997]
            out.append(f"{el} {(np.prod(1 + x) ** (52 / len(x)) - 1) * 100:+.1f}")
        eq = np.cumprod(1 + R)
        dd = (eq / np.maximum.accumulate(eq) - 1).min()
        return f"{(eq[-1] ** (52 / len(R)) - 1) * 100:+.1f} %/an (pire baisse {dd * 100:.0f} %) · " + ' · '.join(out)

    def vs(lab, R, ref, verdict=True):
        d = R - ref
        out, ok_all = [], True
        for el, a, b in eras:
            x = d[a - t1997:b - t1997]
            out.append(f"{el} {x.mean() * 52 * 100:+5.1f}")
            ok_all &= x.mean() > 0
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        v = (' → BAT LA RÉFÉRENCE' if ok_all and tv >= 3 else ' → rejetée') if verdict else ''
        return f"écart : {' · '.join(out)} pts/an, t {tv:4.1f}{v}"

    log("\n3. Garder une ancienne 🎯 en consolidation (portefeuille simulé 1998-2026, frais 0,3 % par sens)")
    for n, base in ((5, lambda t: SEL.get(t, [])), (10, lambda t: G['SEL10'].get(t, []))):
        ref, nb0 = slots(G, base, t1997, T - 1, n=n)
        if n == 5:
            log(f"  copie du portefeuille simulé identique à l'original : {np.allclose(ref, CS.weekly_slots(G, base))}")
        log(f"  {n} lignes par semaine :")
        log(f"    {'règle actuelle':56s} {cagr(ref)} · {nb0:.1f} achats par semaine")
        R0, nb = slots(G, base, t1997, T - 1, n=n, keep=K['reprise'])
        log(f"    {'référence : sans revendre une ligne reprise':56s} {cagr(R0)} · {nb:.1f} achats par semaine")
        log(f"    {'':56s} {vs('', R0, ref, verdict=False)} (face à la règle actuelle)")
        for k, lab in (('consolidation', 'garder une ancienne 🎯 en consolidation'), ('forte', 'garder toute ligne encore forte')):
            R, nb = slots(G, base, t1997, T - 1, n=n, keep=K[k])
            log(f"    {lab:56s} {cagr(R)} · {nb:.1f} achats par semaine")
            log(f"    {'':56s} {vs('', R, R0)} (face à la référence)")
        # frais plus élevés (1 % l'aller-retour, courtier ordinaire) : pour information
        r1, _ = slots(G, base, t1997, T - 1, n=n, cost=.005, keep=K['reprise'])
        for k, lab in (('consolidation', 'consolidation, frais 0,5 % par sens'), ('forte', 'ligne encore forte, frais 0,5 % par sens')):
            R, _ = slots(G, base, t1997, T - 1, n=n, cost=.005, keep=K[k])
            log(f"    {lab:56s} {vs('', R, r1, verdict=False)} (face à la référence aux mêmes frais)")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
