"""Chaque règle de la sélection revérifiée sans biais du survivant (22/11/2026, suite de survivant_eodhd.py, François : « Faire ce
qui est pertinent »).

Univers C de survivant_eodhd.py : toutes les actions ordinaires de l'EEE de 12 bourses (EODHD), sociétés retirées de la cote
comprises, liquidité connue à la date (≥ 1 M€ par jour), 2001-2026. Sélection actuelle (4 🎯 + 1 📣 chaque semaine, mêmes calculs
que backtest/_selection_sim.py) face à elle-même sans une règle à la fois :
  sans 🔊 (priorité aux volumes en hausse) ; sans 📣 dans l'ordre et le repêchage ; sans la place 📣 (5 🎯) ; sans ⚡ (cours très
  volatils admis) ; sans ⏸️ (moyenne 10 semaines ignorée) ; sans la pente du canal (tendance seule) ; sans plafond par secteur ;
et face au momentum simple (5 plus fortes hausses sur 12 mois, en tendance, sans autre règle). Portefeuille simulé, 6 mois,
frais 0,3 % par sens, sans et avec la protection −30 %.

Une règle « aide » si la sélection actuelle fait mieux que la variante sans elle dans chacune des 3 périodes ; « nuit » si la
variante fait mieux dans chacune des 3 périodes avec t ≥ 3 (blocs de 26 semaines) : seul ce cas justifierait de proposer un
changement à François ; sinon « pas tranché ». Lancé par « Recherche (à la demande) » (script survivant_regles.py), environ
20 minutes, 6 300 appels EODHD. Les cours restent en mémoire ; la clé n'est jamais affichée.
"""
import gc
import time

import numpy as np

import cycle_secteurs as CS
import survivant_eodhd as SE

log = SE.log
LIQ = SE.LIQ


def make_pick(G, hot_pri=True, bump_pri=True, promo_on=True, wait_ord=True, vol_excl=True, slope=True, plain=False, perSec=2,
              reserve=1, n=5, bondCap=2):
    """pick() de backtest/_selection_sim.py, chaque règle débrayable ; les valeurs par défaut redonnent la sélection actuelle."""
    okn, mpn, v52, mom, trend, s26 = (G[k] for k in ('okn', 'mpn', 'v52', 'mom', 'trend', 's26'))
    bp8, wait, dem, hot, note, secs, N = (G[k] for k in ('bp8', 'wait', 'dem', 'hot', 'note', 'secs', 'N'))

    def take(q, out, seen, m, cap):
        for i in q:
            if len(out) >= m:
                break
            if i in out or seen.get(secs[i], 0) >= cap:
                continue
            seen[secs[i]] = seen.get(secs[i], 0) + 1
            out.append(i)

    def pick(t):
        ok = okn[:, t] & ~(mpn[:, t] < 1 / 3) & (mom[:, t] <= 2)
        if vol_excl:
            ok = ok & ~(v52[:, t] >= .8)
        if plain:
            idx = np.where(ok & trend[:, t] & (mom[:, t] >= .3))[0]
            q = idx[np.argsort(-np.nan_to_num(mom[idx, t]))].tolist()
            out, seen = [], {}
            for cap in (perSec, perSec + 1):
                take(q, out, seen, n, cap)
            return out
        strong = trend[:, t] & (s26[:, t] >= .41) if slope else trend[:, t]
        mid = trend[:, t] & (s26[:, t] >= .14) if slope else trend[:, t]
        bump = bp8[:, t]
        t0 = ok & strong & (mom[:, t] >= .6)
        t1 = ok & mid & (mom[:, t] >= .3) & ~t0
        promo = (t1 & bump & (~wait[:, t] if wait_ord else True)) if promo_on else np.zeros(N, bool)
        tier0, tier1 = t0 | promo, t1 & ~promo
        pri = (2 * hot[:, t] if hot_pri else 0) + (bump if bump_pri else 0)
        pri = pri if np.ndim(pri) else np.zeros(N)

        def order(M):
            idx = np.where(M)[0]
            keys = (-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t] if wait_ord else np.zeros(len(idx)),
                    -pri[idx])
            return idx[np.lexsort(keys)]
        out, seen = [], {}
        q = order(tier0).tolist() + order(tier1).tolist()
        for cap in (perSec, perSec + 1):
            take(q, out, seen, n - reserve, cap)
        if reserve:
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
    t0 = time.time()
    G = SE.chain(P, V, dates, cols, secs, liq >= LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    G['mkw'] = mk = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    M = mk[t2001 + 1:T]
    log(f"\nUnivers C : {len(cols)} sociétés, calcul en {time.time() - t0:.0f} s")
    SEL0 = G['SEL']
    base = make_pick(G)
    same = all(base(t) == list(SEL0[t]) for t in range(t2001, T - 1, 13))
    log(f"copie de la sélection identique à l'originale : {same}")

    def run(f):
        S = {t: f(t) for t in range(t2001, T - 1)}
        R0 = CS.weekly_slots(G, lambda t: S.get(t, []))
        G['SEL'] = S
        R1 = G['sim30']()
        G['SEL'] = SEL0
        return R0, R1

    def cagr(R):
        return ' · '.join(f"{el} {(np.prod(1 + R[a - t2001:b - t2001]) ** (52 / (b - a)) - 1) * 100:+.1f}" for el, a, b in ERAS)

    def cmp(R, ref):
        d = R - ref
        cells, sg = [], []
        for el, a, b in ERAS:
            x = d[a - t2001:b - t2001].mean() * 5200
            cells.append(f"{el} {x:+5.1f}")
            sg.append(x)
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        return cells, sg, tv

    ref0, ref1 = run(lambda t: list(SEL0.get(t, [])))
    an = lambda R: (np.prod(1 + R) ** (52 / len(R)) - 1) * 100  # noqa: E731
    log(f"  règle actuelle : sans protection {an(ref0):+.1f} %/an ({cagr(ref0)}) ; protection −30 % {an(ref1):+.1f} %/an ({cagr(ref1)}) ; "
        f"société moyenne {an(M):+.1f} %/an ({cagr(M)})")
    VAR = [('sans 🔊 (volumes en hausse)', dict(hot_pri=False)),
           ('sans 📣 dans l\'ordre et le repêchage', dict(bump_pri=False, promo_on=False)),
           ('sans la place 📣 (5 🎯)', dict(reserve=0)),
           ('sans ⚡ (cours très volatils admis)', dict(vol_excl=False)),
           ('sans ⏸️ (moyenne 10 semaines ignorée)', dict(wait_ord=False)),
           ('sans la pente du canal (tendance seule)', dict(slope=False)),
           ('sans plafond par secteur', dict(perSec=99)),
           ('momentum simple (5 plus fortes hausses en tendance)', dict(plain=True))]
    log("\nÉcart de la variante avec la règle actuelle, points par an (2001-2008 · 2009-2017 · 2018-2026), protection −30 % comprise ; "
        "entre crochets : sans protection")
    for lab, kw in VAR:
        R0, R1 = run(make_pick(G, **kw))
        c1, s1, t1 = cmp(R1, ref1)
        c0, s0, t0_ = cmp(R0, ref0)
        if all(x < 0 for x in s1):
            v = 'la règle aide (actuelle meilleure dans chaque période)'
        elif all(x > 0 for x in s1) and t1 >= 3:
            v = 'LA RÈGLE NUIT : à proposer à François'
        else:
            v = 'pas tranché'
        log(f"  {lab:52s} {an(R1):+5.1f} %/an · {' · '.join(c1)} (t {t1:4.1f}) [{' · '.join(c0)}, t {t0_:4.1f}] → {v}")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
