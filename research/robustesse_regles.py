"""Chaque règle et chaque réglage de la sélection, sans biais du survivant, sur 1991-2026 (23/11/2026, François : « D'autres idées
pendant que j'ai l'abonnement ? … Oui »).

Univers de survivant_eodhd.py (12 bourses, sociétés disparues comprises, liquidité connue à la date), cours EODHD depuis 1988,
seuil du 🎯 en direct (3 M€ par jour à la date). Quatre périodes : 1991-1997 (jamais utilisée pour régler l'outil), 1998-2008,
2009-2017, 2018-2026. Sélection actuelle (4 🎯 + 1 📣 par semaine, gardées 26 semaines, protection −30 %, frais 0,3 % par sens)
face à :
  - chaque règle enlevée une à une (comme survivant_regles.py, qui l'a fait à 1 M€ sur 2001-2026) ;
  - les réglages voisins : 3 ou 8 sociétés par semaine (au lieu de 5), garder 17 ou 39 semaines (au lieu de 26), protection à −20 %,
    −40 % ou aucune (au lieu de −30 %), tous les seuils de hausse 15 % plus bas ou plus hauts (+51 % ou +69 % au lieu de +60 %,
    plafond et second palier de même), hausse mesurée sur 9 ou 15 mois au lieu de 12 (seuils ramenés à la même durée) ;
  - janvier : écart à 6 mois des choix selon le mois d'achat, et sélection sans achat en janvier, ou en décembre et janvier
    (les sociétés en forte baisse rebondissent souvent en janvier, au détriment des stratégies de tendance : Jegadeesh et Titman,
    1993 ; Grundy et Martin, 2001).
Un réglage est sur un « plateau » si ses voisins font à peu près aussi bien ; une variante « bat » la règle actuelle si elle fait
mieux dans chacune des 4 périodes avec t ≥ 3 (blocs de 26 semaines) : seul ce cas serait proposé à François. Les cours restent en
mémoire (rien dans research/out) ; la clé n'est jamais affichée. Lancé par « Recherche (à la demande) » (script
robustesse_regles.py), environ 30 minutes, 6 500 appels EODHD.
"""
import gc
import time

import numpy as np

import hors_echantillon as HE   # met SE.START à 1988
import proba as PB
import survivant_eodhd as SE
import survivant_regles as SR

log = SE.log
PER = (('1991-1997', '1991-01-01', '1998-01-01'), ('1998-2008', '1998-01-01', '2009-01-01'), ('2009-2017', '2009-01-01', '2018-01-01'),
       ('2018-2026', '2018-01-01', '2100-01-01'))


def simk(G, S, t0, hold=26, stop=.30, cost=.003):
    """sim30 de proba.py (tranches suivies ligne à ligne), avec la durée et le seuil de protection en paramètres"""
    retw, T = G['retw'], G['T']
    tr, R = [], []
    for t in range(t0, T - 1):
        s = np.array(S.get(t, []), dtype=int)
        r = 0.0
        if len(s):
            k = len(s)
            tr.append(dict(t0=t, i=s, px=np.ones(k), q=np.ones(k) / k))
            r -= cost
        keep = []
        for x in tr:
            px1 = x['px'] * (1 + retw[x['i'], t + 1])
            r += (x['q'] * (px1 - x['px'])).sum()
            if stop is not None:
                hit = (x['q'] > 0) & (px1 <= 1 - stop)
                if hit.any():
                    r -= (x['q'][hit] * px1[hit] * cost).sum()
                    x['q'][hit] = 0.0
            x['px'] = px1
            if t - x['t0'] + 1 >= hold:
                r -= (x['q'] * x['px']).sum() * cost
            else:
                keep.append(x)
        tr = keep
        R.append(r / hold)
    return np.array(R)


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t00 = (D[k] for k in ('P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't00'))
    del D
    gc.collect()
    t1 = time.time()
    G = HE.base_chain(P, V, dates, cols, secs)
    del V
    gc.collect()
    t_start = int(np.searchsorted(dates, '1990-01-01'))
    G['okn'] = G['okn'] & (liq >= 3e6)
    G['t1997'] = t_start
    exec(compile(PB.SIM, 'proba.SIM', 'exec'), G)
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    mk = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 20 else np.nan for t in range(T)])
    G['mkw'] = np.nan_to_num(mk)
    M = mk[t_start + 1:T]
    tt = np.arange(t_start, T - 1)
    pm = [((tt >= np.searchsorted(dates, a)) & (tt < np.searchsorted(dates, b))) for _, a, b in PER]
    log(f"\nCalculs prêts en {time.time() - t1:.0f} s : {len(cols)} sociétés ; investissables à 3 M€ (médiane par période) : " +
        ' · '.join(f"{lab} {int(np.median([okn[:, t].sum() for t in tt[m]]))}" for (lab, _, _), m in zip(PER, pm)))

    def ann(R):
        R = R[np.isfinite(R)]
        return (np.prod(1 + R) ** (52 / len(R)) - 1) * 100 if len(R) >= 26 else np.nan

    def sel(**kw):
        f = SR.make_pick(G, **kw)
        return {t: f(t) for t in range(t_start, T - 1)}
    S0 = sel()
    same = all(S0[t] == list(G['SEL'].get(t, [])) for t in range(t_start, T - 1, 13))
    R_ref = simk(G, S0, t_start)
    log(f"copie de la sélection identique à l'originale : {same}")
    log("  règle actuelle : " + ' · '.join(f"{lab} {ann(R_ref[m]):+.1f} %/an (société moyenne {ann(M[m]):+.1f})" for (lab, _, _), m in zip(PER, pm)))

    def cmp(R):
        d = R - R_ref
        x = [d[m].mean() * 5200 for m in pm]
        blk = np.array([d[k:k + 26].sum() for k in range(int(np.argmax(pm[0])), len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk))) if blk.std(ddof=1) > 0 else 0.0
        if all(v < 0 for v in x):
            v = "la règle actuelle fait mieux dans chaque période"
        elif all(v > 0 for v in x) and tv >= 3:
            v = "LA VARIANTE BAT LA RÈGLE : à proposer à François"
        elif all(v > 0 for v in x):
            v = "variante meilleure partout, mais t < 3 : pas tranché"
        else:
            v = "pas tranché"
        return ' · '.join(f"{lab} {v_:+5.1f}" for (lab, _, _), v_ in zip(PER, x)), tv, v

    def line(lab, R):
        c, tv, v = cmp(R)
        log(f"  {lab:50s} {ann(R[np.any(pm, 0)]):+5.1f} %/an · écart {c} (t {tv:4.1f}) → {v}")
    log("\n1. Chaque règle enlevée (écart avec la règle actuelle, points par an, protection −30 % comprise)")
    VAR = [('sans 🔊 (volumes en hausse)', dict(hot_pri=False)),
           ("sans 📣 dans l'ordre et le repêchage", dict(bump_pri=False, promo_on=False)),
           ('sans la place 📣 (5 🎯)', dict(reserve=0)),
           ('sans ⚡ (cours très volatils admis)', dict(vol_excl=False)),
           ('sans ⏸️ (moyenne 10 semaines ignorée)', dict(wait_ord=False)),
           ('sans la pente du canal (tendance seule)', dict(slope=False)),
           ('sans plafond par secteur', dict(perSec=99)),
           ('momentum simple (5 plus fortes hausses en tendance)', dict(plain=True))]
    for lab, kw in VAR:
        line(lab, simk(G, sel(**kw), t_start))
    log("\n2. Réglages voisins (plateau ou pic ?)")
    line('3 sociétés par semaine (au lieu de 5)', simk(G, sel(n=3, reserve=1), t_start))
    line('8 sociétés par semaine', simk(G, sel(n=8, reserve=2), t_start))
    for h in (17, 39):
        line(f'garder {h} semaines (au lieu de 26)', simk(G, S0, t_start, hold=h))
    for st in (.20, .40, None):
        line(f"protection à −{int(st * 100)} %" if st else 'sans protection', simk(G, S0, t_start, stop=st))
    mom0 = G['mom'].copy()
    for k, lab in ((1 / .85, 'seuils de hausse 15 % plus bas (+51 % au lieu de +60 %)'), (1 / 1.15, 'seuils de hausse 15 % plus hauts (+69 %)')):
        G['mom'] = mom0 * k
        line(lab, simk(G, sel(), t_start))
    Pp = G['P']
    with np.errstate(all='ignore'):
        chk = Pp[:, 48:-4] / Pp[:, :-52] - 1
    ref_ = mom0[:, 52:]
    mm = np.isfinite(chk) & np.isfinite(ref_)
    log(f"  (définition de la hausse sur 12 mois retrouvée à partir des cours : {bool(mm.any() and np.allclose(chk[mm], ref_[mm], rtol=1e-4, atol=1e-6))})")
    for w, lab in ((39, 'hausse mesurée sur 9 mois (au lieu de 12)'), (65, 'hausse mesurée sur 15 mois')):
        m_ = np.full_like(mom0, np.nan)
        with np.errstate(all='ignore'):
            m_[:, w:] = (Pp[:, w - 4:-4] / Pp[:, :-w] - 1) * (48 / (w - 4))
        G['mom'] = m_
        line(lab, simk(G, sel(), t_start))
    G['mom'] = mom0
    log("\n3. Janvier")
    Lr = np.log1p(retw)
    Cc = np.concatenate([np.zeros((Lr.shape[0], 1)), np.cumsum(Lr, 1)], 1)
    mon = np.array([int(d[5:7]) for d in dates])
    yr = np.array([int(d[:4]) for d in dates])
    ex = {m_: [] for m_ in range(1, 13)}
    for t in range(t_start, T - 27):
        s = S0.get(t) or []
        if s and okn[:, t].sum() > 20 and yr[t] >= 1991:
            fw = np.clip(np.expm1(Cc[:, t + 27] - Cc[:, t + 1]), -1, 5)
            ex[mon[t]].append(np.mean(fw[s]) - np.mean(fw[okn[:, t]]))
    log("  écart à 6 mois des choix avec la société moyenne, selon le mois d'achat (1991-2026, points) : " +
        ' · '.join(f"{'jfmamjjasond'[m_ - 1]} {np.mean(v) * 100:+.1f}" for m_, v in ex.items() if v))
    del Lr, Cc
    for lab, months in (('sans achat en janvier', {1}), ('sans achat en décembre ni janvier', {12, 1})):
        line(lab, simk(G, {t: ([] if mon[t] in months else v) for t, v in S0.items()}, t_start))
    u, err = SE.get('user')
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
