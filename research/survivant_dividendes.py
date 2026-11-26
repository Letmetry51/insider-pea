"""Dividendes et sélection, sans biais du survivant (26/11/2026, François : « Est-ce qu'il y aurait d'autres idées? Approche?
Méthode? Autre? », puis la liste : « 1. Les dividendes »).

Littérature : à l'annonce, suppression −7,0 % et premier dividende +3,4 % en trois jours, puis dérive dans le même sens l'année
suivante, plus nette après une suppression (Michaely, Thaler et Womack, 1995, États-Unis) ; moins net au Royaume-Uni.

Univers C de survivant_eodhd.py (12 bourses de l'EEE, sociétés retirées de la cote comprises, liquidité ≥ 1 M€ par jour connue à
la date, 2001-2026), dividendes EODHD (« div », montants ajustés des divisions), chaque versement daté de la semaine de son
détachement (montant annoncé avant : rien de connu trop tôt). Événements, règle fixée avant le calcul :
  hausse : versements des 350 derniers jours ≥ +10 % face aux 365 jours d'avant, même nombre de versements des deux côtés ;
  baisse : ≤ −25 %, même règle ; suppression : rien depuis 450 jours après au moins un versement par an les deux années d'avant ;
  premier dividende ou reprise : versement après 2 ans sans rien, société cotée depuis 2 ans au moins.
1. Écart à 6 mois avec la moyenne des sociétés investissables, par événement et par période (t sur les mois), toutes sociétés et
   dans la zone du 🎯 (paliers de la sélection, 12 mois après l'événement).
2. Sélection simulée (4 🎯 + 1 📣, 6 mois, frais 0,3 % par sens, protection −30 %) face à la règle actuelle : sans les sociétés
   qui ont supprimé ou baissé leur dividende dans les 12 derniers mois ; priorité aux hausses des 12 derniers mois (même poids
   qu'un 📣) ; les deux ; pour information, seulement des sociétés qui ont versé un dividende dans les 2 dernières années.
Une variante ne remplace la règle actuelle que si elle fait mieux dans chacune des périodes 2001-2008, 2009-2017 et 2018-2026,
avec t ≥ 3 (blocs de 26 semaines) ; sinon, résultat documenté. Lancé par « Recherche (à la demande) » (script
survivant_dividendes.py), environ 25 minutes, 8 500 appels EODHD. Cours et dividendes restent en mémoire ; la clé n'est jamais
affichée.
"""
import concurrent.futures as cf
import gc
import time
from datetime import date

import numpy as np

import survivant_eodhd as SE

log = SE.log
LIQ = SE.LIQ
UP, DOWN = .10, -.25


def dividends(cols):
    """{i: [(jour, montant)]} : versements de chaque société (montant ajusté des divisions, > 0), du plus ancien au plus récent."""
    out, errs = {}, {}

    def one(i):
        x, err = SE.get('div/' + cols[i], **{'from': '1990-01-01'})
        return i, x, err
    with cf.ThreadPoolExecutor(8) as pool:
        for i, x, err in pool.map(one, range(len(cols))):
            if err:
                errs[err] = errs.get(err, 0) + 1
                continue
            v = []
            for d in x or []:
                try:
                    a, dd = float(d.get('value') or 0), date.fromisoformat(str(d.get('date'))[:10])
                except (TypeError, ValueError):
                    continue
                if a > 0:
                    v.append((dd, a, d.get('currency')))
            out[i] = sorted(v)
    log(f"  dividendes : {sum(1 for v in out.values() if v)} sociétés avec au moins un versement, {sum(len(v) for v in out.values())} "
        f"versements ; erreurs {errs or 'aucune'}")
    return out


def events(divs, dates, P, T):
    """Masques N × T des événements (vrais la semaine où ils deviennent connus) et listes (i, t, type)."""
    N = P.shape[0]
    D = np.array([date.fromisoformat(d) for d in dates])
    week = lambda d: int(np.searchsorted(D, d))  # noqa: E731  (vendredi de la semaine du détachement, ou d'après)
    first = np.array([np.argmax(np.isfinite(p)) if np.isfinite(p).any() else T for p in P])
    ev = {k: np.zeros((N, T), bool) for k in ('hausse', 'baisse', 'suppression', 'premier')}
    paid = np.zeros((N, T), bool)  # au moins un versement dans les 2 années précédentes
    lst = []
    for i, v in divs.items():
        if not v:
            continue
        days = [d for d, _, _ in v]
        for k, (d, a, cur) in enumerate(v):
            t = week(d)
            if t >= T:
                continue
            paid[i, t:min(T, week(date.fromordinal(d.toordinal() + 730)) + 1)] = True
            A = [x for x in v if 0 <= (d - x[0]).days < 350]
            B = [x for x in v if 350 <= (d - x[0]).days < 715]
            if A and B and len(A) == len(B) and len({x[2] for x in A + B}) == 1:
                g = sum(x[1] for x in A) / sum(x[1] for x in B) - 1
                if g >= UP:
                    ev['hausse'][i, t] = True
                    lst.append((i, t, 'hausse'))
                elif g <= DOWN:
                    ev['baisse'][i, t] = True
                    lst.append((i, t, 'baisse'))
            prev = [x for x in days[:k] if 0 < (d - x).days <= 730]
            if not prev and first[i] < T and (d - D[min(first[i], T - 1)]).days >= 730:
                ev['premier'][i, t] = True
                lst.append((i, t, 'premier'))
        # suppression : rien pendant 450 jours après le dernier versement, qui suivait au moins un versement par an les 2 années d'avant
        for k, d in enumerate(days):
            nxt = days[k + 1] if k + 1 < len(days) else None
            if nxt is not None and (nxt - d).days <= 450:
                continue
            y1 = [x for x in days[:k + 1] if 0 <= (d - x).days < 365]
            y2 = [x for x in days[:k + 1] if 365 <= (d - x).days < 730]
            if not y1 or not y2:
                continue
            t = week(date.fromordinal(d.toordinal() + 450))
            if t < T and np.isfinite(P[i, t]):
                ev['suppression'][i, t] = True
                lst.append((i, t, 'suppression'))
    return ev, paid, lst


def within(ev, weeks=52):
    """Vrai pendant les `weeks` semaines qui suivent l'événement (semaine de l'événement comprise)."""
    out = np.zeros_like(ev)
    for i, t in zip(*np.where(ev)):
        out[i, t:t + weeks] = True
    return out


def make_pick(G, excl=None, bonus=None, only=None):
    """survivant_regles.make_pick (règle actuelle), avec une exclusion, une priorité (poids d'un 📣) ou un filtre en plus."""
    okn, mpn, v52, mom, trend, s26 = (G[k] for k in ('okn', 'mpn', 'v52', 'mom', 'trend', 's26'))
    bp8, wait, dem, hot, note, secs, N = (G[k] for k in ('bp8', 'wait', 'dem', 'hot', 'note', 'secs', 'N'))
    perSec, reserve, n, bondCap = 2, 1, 5, 2

    def take(q, out, seen, m, cap):
        for i in q:
            if len(out) >= m:
                break
            if i in out or seen.get(secs[i], 0) >= cap:
                continue
            seen[secs[i]] = seen.get(secs[i], 0) + 1
            out.append(i)

    def pick(t):
        ok = okn[:, t] & ~(mpn[:, t] < 1 / 3) & (mom[:, t] <= 2) & ~(v52[:, t] >= .8)
        if excl is not None:
            ok = ok & ~excl[:, t]
        if only is not None:
            ok = ok & only[:, t]
        strong, mid, bump = trend[:, t] & (s26[:, t] >= .41), trend[:, t] & (s26[:, t] >= .14), bp8[:, t]
        t0 = ok & strong & (mom[:, t] >= .6)
        t1 = ok & mid & (mom[:, t] >= .3) & ~t0
        promo = t1 & bump & ~wait[:, t]
        tier0, tier1 = t0 | promo, t1 & ~promo
        pri = 2 * hot[:, t] + bump + (bonus[:, t] if bonus is not None else 0)

        def order(M):
            idx = np.where(M)[0]
            return idx[np.lexsort((-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t], -pri[idx]))]
        out, seen = [], {}
        q = order(tier0).tolist() + order(tier1).tolist()
        for cap in (perSec, perSec + 1):
            take(q, out, seen, n - reserve, cap)
        dm = ok & dem[:, t] & ~np.isin(np.arange(N), out)
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


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00 = (D[k] for k in ('P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00'))
    divs = dividends(cols)
    ev, paid, lst = events(divs, dates, P, T)
    del divs
    t0 = time.time()
    G = SE.chain(P, V, dates, cols, secs, liq >= LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    G['mkw'] = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    log(f"\nUnivers C : {len(cols)} sociétés, calcul en {time.time() - t0:.0f} s")
    n_ev = {k: int(v[:, t2001:].sum()) for k, v in ev.items()}
    log("événements 2001-2026 : " + ', '.join(f"{k} {n}" for k, n in n_ev.items()))

    # 1. écart à 6 mois avec la moyenne des sociétés investissables
    L = np.log1p(retw)
    C = np.concatenate([np.zeros((L.shape[0], 1)), np.cumsum(L, 1)], 1)
    mom, trend, s26, mpn, v52 = (G[k] for k in ('mom', 'trend', 's26', 'mpn', 'v52'))
    zone = okn & trend & (s26 >= .14) & (mom >= .3) & (mom <= 2) & ~(mpn < 1 / 3) & ~(v52 >= .8)  # paliers du 🎯
    mean26 = {}

    def fwd(i, t):
        if t + 27 > C.shape[1] - 1:
            return np.nan
        if t not in mean26:
            ok = okn[:, t]
            mean26[t] = np.nanmean(np.expm1(C[ok, t + 27] - C[ok, t + 1]))
        return np.expm1(C[i, t + 27] - C[i, t + 1]) - mean26[t]

    def era(t):
        return next((el for el, a, b in ERAS if a <= t < b), None)
    log("\n1. Écart à 6 mois avec la moyenne des sociétés investissables (points de %, t sur les mois ; nombre d'événements)")
    for kind in ('suppression', 'baisse', 'hausse', 'premier'):
        for lab, M in (('toutes', okn), ('zone du 🎯', zone)):
            rows = [(t, fwd(i, t)) for i, t, k in lst if k == kind and t >= t2001 and M[i, t]]
            rows = [(t, x) for t, x in rows if np.isfinite(x)]
            if len(rows) < 10:
                log(f"  {kind:12s} {lab:10s} : {len(rows)} événement(s), trop peu")
                continue
            months = {}
            for t, x in rows:
                months.setdefault(dates[t][:7], []).append(x)
            mm = np.array([np.mean(v) for v in months.values()])
            tv = mm.mean() / (mm.std(ddof=1) / np.sqrt(len(mm))) if len(mm) > 2 else np.nan
            per = ' · '.join(f"{el} {np.mean([x for t, x in rows if era(t) == el]) * 100:+5.1f} ({sum(1 for t, _ in rows if era(t) == el)})"
                             for el, _, _ in ERAS if any(era(t) == el for t, _ in rows))
            log(f"  {kind:12s} {lab:10s} : {np.mean([x for _, x in rows]) * 100:+5.1f} (t {tv:4.1f}, {len(rows)}) · {per}")

    # 2. sélection simulée
    SEL0 = G['SEL']
    same = all(make_pick(G)(t) == list(SEL0[t]) for t in range(t2001, T - 1, 13))
    log(f"\ncopie de la sélection identique à l'originale : {same}")

    def run(f):
        S = {t: f(t) for t in range(t2001, T - 1)}
        G['SEL'] = S
        R1 = G['sim30']()
        G['SEL'] = SEL0
        return R1, S

    def cagr(R):
        return ' · '.join(f"{el} {(np.prod(1 + R[a - t2001:b - t2001]) ** (52 / (b - a)) - 1) * 100:+.1f}" for el, a, b in ERAS)

    an = lambda R: (np.prod(1 + R) ** (52 / len(R)) - 1) * 100  # noqa: E731
    ref, Sref = run(lambda t: list(SEL0.get(t, [])))
    eq = np.cumprod(1 + ref)
    log(f"\n2. Sélection simulée, protection −30 % : règle actuelle {an(ref):+.1f} %/an ({cagr(ref)}), pire baisse "
        f"{(eq / np.maximum.accumulate(eq) - 1).min() * 100:.0f} %")
    cut12 = within(ev['suppression'] | ev['baisse'])
    up12 = within(ev['hausse'])
    share = {k: np.mean([M[i, t] for t, s in Sref.items() for i in s]) * 100 for k, M in
             (('suppression ou baisse dans les 12 mois', cut12), ('hausse dans les 12 mois', up12), ('versement dans les 2 ans', paid))}
    log("  sociétés choisies par la règle actuelle : " + ', '.join(f"{k} {v:.1f} %" for k, v in share.items()))
    for lab, kw, verdict in (('sans suppression ni baisse dans les 12 mois', dict(excl=cut12), True),
                             ('hausse des 12 mois en priorité (poids d\'un 📣)', dict(bonus=up12.astype(int)), True),
                             ('les deux', dict(excl=cut12, bonus=up12.astype(int)), True),
                             ('seulement des sociétés qui versent un dividende', dict(only=paid), False)):
        R, _ = run(make_pick(G, **kw))
        d = R - ref
        cells, sg = [], []
        for el, a, b in ERAS:
            x = d[a - t2001:b - t2001].mean() * 5200
            cells.append(f"{el} {x:+5.1f}")
            sg.append(x)
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        e2 = np.cumprod(1 + R)
        v = ('' if not verdict else ' → BAT LA RÈGLE ACTUELLE : à proposer à François' if all(x > 0 for x in sg) and tv >= 3
             else ' → rejetée')
        log(f"  {lab:50s} {an(R):+5.1f} %/an, pire baisse {(e2 / np.maximum.accumulate(e2) - 1).min() * 100:.0f} % · écart "
            f"{' · '.join(cells)} pts/an (t {tv:4.1f}){v}")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
