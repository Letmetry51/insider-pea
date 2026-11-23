"""La méthode hors échantillon dans le temps : 1991-1997, sans biais du survivant (23/11/2026 ; François, 22/11/2026 : « Oui faire ce
qui est pertinent », test 3 de la liste « Comment exploiter davantage les données disponibles avec l'abonnement ? »).

Les règles du 🎯 / 📣 ont été réglées sur 1997-2026 : les années d'avant n'ont jamais servi, c'est le meilleur contrôle contre le
surapprentissage. Univers de survivant_eodhd.py (12 bourses, sociétés disparues comprises, liquidité connue à la date), cours
hebdomadaires EODHD depuis 1988 ; d'abord, ce que les données contiennent avant 1998 (sociétés avec cours, avec volumes, assez
liquides). Mêmes règles et mêmes calculs (sélection de 5 sociétés par semaine gardées 6 mois, protection −30 %, frais 0,3 % par
sens) face à la société moyenne investissable, à 3 M€ par jour à la date (seuil en direct), puis 1 M€ et 0,5 M€ (variantes : en
1991-1997 les échanges étaient bien plus faibles). Aussi : l'alerte « krach du momentum » (moyenne des sociétés à −20 % sur
52 semaines, fin au-dessus de −15 %) et la pause des achats pendant l'alerte, sur les sociétés elles-mêmes, dans chaque période.
Les cours restent en mémoire (rien dans research/out) ; la clé n'est jamais affichée. Lancé par « Recherche (à la demande) »
(script hors_echantillon.py), environ 25 minutes, 6 500 appels EODHD.
"""
import gc
import os
import time

import numpy as np

import proba as PB
import survivant_eodhd as SE

log = SE.log
SE.START = '1988-01-01'
SE.LIQ = 5e5      # garder les sociétés liquides à 0,5 M€ par jour à un moment (variante la plus large)
PERIODS = (('1991-1994', '1991-01-01', '1995-01-01'), ('1995-1997', '1995-01-01', '1998-01-01'), ('1991-1997', '1991-01-01', '1998-01-01'),
           ('1998-2008', '1998-01-01', '2009-01-01'), ('2009-2017', '2009-01-01', '2018-01-01'), ('2018-2026', '2018-01-01', '2100-01-01'))


def base_chain(P, V, dates, cols, secs):
    """Calculs de backtest/_selection_sim2.py une fois (sans le filtre de liquidité, appliqué ensuite à chaque variante)."""
    os.chdir('backtest')
    try:
        np.savez_compressed('long.npz', P=P.astype('float32'), V=V.astype('float32'), dates=np.array(dates), cols=np.array(cols),
                            sec=np.array(secs))
        G = {'__name__': 'selection_sim'}
        exec(compile(open('_selection_sim2.py').read().split('print("Écart avec')[0], '_selection_sim2.py', 'exec'), G)
    finally:
        if os.path.exists('long.npz'):
            os.remove('long.npz')
        os.chdir('..')
    return G


def main():
    D = SE.prepare()
    if D is None:
        return
    P, C, V, liq, dl, cols, secs, dates, T, t00, gone = (D[k] for k in ('P', 'C', 'V', 'liq', 'dl', 'cols', 'secs', 'dates', 'T', 't00', 'gone'))
    rows = D['rows']
    del D
    gc.collect()
    ex = np.array([r['ex'] for r in rows])
    # ------------------------------------------------------------------ ce que contiennent les données avant 1998
    log("\nDonnées avant 1998 (premier vendredi de juin ; sociétés avec cours / avec volume / liquides à 0,5, 1 et 3 M€ par jour) :")
    for y in range(1988, 2001):
        t = int(np.searchsorted(dates, f'{y}-06-01'))
        if t >= T:
            continue
        hp = np.isfinite(P[:, t])
        hv = hp & (np.nan_to_num(V[:, t]) > 0)
        lq = np.nan_to_num(liq[:, t])
        top = ', '.join(f"{e} {int((hp & (ex == e)).sum())}" for e in sorted(set(ex[hp]), key=lambda e: -int((hp & (ex == e)).sum()))[:5])
        log(f"  {y} : {int(hp.sum())} / {int(hv.sum())} / {int((lq >= 5e5).sum())}, {int((lq >= 1e6).sum())}, {int((lq >= 3e6).sum())} "
            f"(dont disparues depuis : {int((hp & dl).sum())}) ; par bourse : {top}")
    t_start = int(np.searchsorted(dates, '1990-01-01'))
    G0 = base_chain(P, V, dates, cols, secs)
    base_okn = G0['okn'].copy()
    retw = np.clip(np.nan_to_num(G0['r1']), -.95, 3.0)
    yrs = np.array([int(d[:4]) for d in dates])

    def ann(R):
        R = R[np.isfinite(R)]
        return (np.prod(1 + R) ** (52 / len(R)) - 1) * 100 if len(R) >= 26 else np.nan

    def mdd(R):
        eq = np.cumprod(1 + np.nan_to_num(R))
        return (eq / np.maximum.accumulate(eq) - 1).min() * 100
    for Lq in (3e6, 1e6, 5e5):
        t0 = time.time()
        G = G0
        G['okn'] = base_okn & (liq >= Lq)
        G['t1997'] = t_start
        exec(compile(PB.SIM, 'proba.SIM', 'exec'), G)
        G['retw'] = retw
        okn = G['okn']
        mk = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 20 else np.nan for t in range(T)])
        G['mkw'] = np.nan_to_num(mk)
        R = G['sim30']()                     # semaines t_start → T−1 (rendement de t à t+1)
        M = mk[t_start + 1:T]
        tt = np.arange(t_start, T - 1)
        # alerte krach sur la moyenne des sociétés investissables ; pause : pas de nouvelle tranche pendant l'alerte
        I = np.cumprod(1 + np.nan_to_num(mk))
        m52 = np.full(T, np.nan)
        m52[52:] = (I[52:] / I[:-52] - 1) * 100
        on, st = np.zeros(T, bool), False
        for t in range(T):
            if np.isfinite(m52[t]):
                st = (m52[t] <= -15) if st else (m52[t] <= -20)
            on[t] = st
        S0 = G['SEL']
        G['SEL'] = {t: ([] if on[t] else v) for t, v in S0.items()}
        Rp = G['sim30']()
        G['SEL'] = S0
        # écart à 6 mois des choix de chaque semaine face à la société moyenne (cohortes de 26 semaines sans chevauchement)
        Lr = np.log1p(retw)
        Cc = np.concatenate([np.zeros((Lr.shape[0], 1)), np.cumsum(Lr, 1)], 1)
        ex6, et = [], []
        for t in range(t_start, T - 27):
            s = list(S0.get(t, []))
            if s and okn[:, t].sum() > 20:
                fw = np.clip(np.expm1(Cc[:, t + 27] - Cc[:, t + 1]), -1, 5)
                ex6.append(np.mean(fw[s]) - np.mean(fw[okn[:, t]]))
                et.append(t)
        ex6, et = np.array(ex6), np.array(et)
        del Lr, Cc
        log(f"\nSeuil {Lq / 1e6:g} M€ par jour à la date (calcul en {time.time() - t0:.0f} s) :")
        for lab, a, b in PERIODS:
            m = (tt >= np.searchsorted(dates, a)) & (tt < np.searchsorted(dates, b))
            if m.sum() < 26:
                continue
            ninv = int(np.median([okn[:, t].sum() for t in tt[m]]))
            wk = int(sum(1 for t in tt[m] if S0.get(t)))
            e6 = ex6[(et >= np.searchsorted(dates, a)) & (et < np.searchsorted(dates, b))]
            coh = e6[::26]
            tv = coh.mean() / (coh.std(ddof=1) / np.sqrt(len(coh))) if len(coh) > 2 and coh.std(ddof=1) > 0 else np.nan
            al = on[tt[m]].mean() * 100
            log(f"  {lab} : 🎯 {ann(R[m]):+.1f} %/an (pire baisse {mdd(R[m]):.0f} %), société moyenne {ann(M[m]):+.1f} ({mdd(M[m]):.0f} %), "
                f"écart {ann(R[m]) - ann(M[m]):+.1f} points ; choix à 6 mois {np.nanmean(e6) * 100:+.1f} points (t {tv:.1f}, {len(coh)} "
                f"cohortes) ; {ninv} sociétés investissables, sélection {wk} semaines sur {int(m.sum())} ; alerte krach {al:.0f} % du temps, "
                f"pause {ann(Rp[m]):+.1f} %/an (pire baisse {mdd(Rp[m]):.0f} %)")
        yl = ' · '.join(f"{y} {ann(R[yrs[tt] == y]) - ann(M[yrs[tt] == y]):+.0f}" for y in range(1990, 1999) if (yrs[tt] == y).sum() >= 26)
        log(f"  écart par année (points) : {yl}")
        eps = []
        for t in range(1, T):
            if on[t] and not on[t - 1]:
                u = t
                while u + 1 < T and on[u + 1]:
                    u += 1
                eps.append(f"{dates[t]} → {dates[min(u + 1, T - 1)]}")
        log(f"  alertes krach (moyenne des sociétés) : {len(eps)} — " + ' ; '.join(eps[:12]))
        del S0
        gc.collect()
    u, err = SE.get('user')
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
