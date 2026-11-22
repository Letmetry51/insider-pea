"""La méthode telle qu'appliquée, sans biais du survivant (22/11/2026, François : « Oui et Faire ce qui est pertinent », abonnement
EODHD « Historian » d'un mois).

Univers de survivant_eodhd.py (toutes les actions ordinaires de l'EEE de 12 bourses, retirées de la cote comprises, liquidité
connue à la date), ici sociétés liquides à 0,5 M€ par jour au moins à un moment. Sélection et calculs de backtest/_selection_sim.py,
portefeuille simulé 2001-2026, protection −30 % comme dans l'outil (sim30 de proba.py), frais 0,3 % par sens.

1. Seuil de liquidité : 0,5, 1, 3 (seuil du 🎯 en direct) ou 10 M€ échangés par jour, connus à la date.
2. Jour d'achat réel : la sélection est envoyée le lundi ; achat (et vente 26 semaines plus tard) à l'ouverture ou à la clôture du
   lundi au lieu de la clôture du vendredi (cours journaliers EODHD des sociétés choisies).
3. Durée de détention (13, 26 ou 52 semaines) et protection (aucune, −20 %, −30 %, −40 %).
4. Points de la revue du 31/01/2027 : protection suspendue pendant une panique générale (thermomètre de l'outil : part des sociétés
   au plus bas de l'année ≥ 20 % et 15 points au-dessus de la médiane passée, fin 10 points sous le seuil) ; dosage selon l'agitation
   de la stratégie (Barroso et Santa-Clara : exposition = médiane passée de l'agitation sur 13 semaines / agitation récente, au plus
   100 %, liquidités sinon ; comparé à la même exposition moyenne en permanence) ; pause des achats pendant l'alerte krach (indice
   équipondéré −20 % sur un an, fin au-dessus de −15 %).
5. Face à un fonds indiciel : iShares STOXX Europe 600 (EXSA, dividendes réinvestis) et autres suivis disponibles chez EODHD.

Règle fixée avant le calcul : une variante ne remplace la règle actuelle que si elle fait mieux dans chacune des périodes 2001-2008,
2009-2017 et 2018-2026, avec t ≥ 3 (blocs de 26 semaines) ; sinon, résultat documenté. Les cours EODHD restent en mémoire.
Lancé par « Recherche (à la demande) » (script survivant_pratique.py), environ 25 minutes, 7 500 appels EODHD.
"""
import concurrent.futures as cf
import gc
import time

import numpy as np
import pandas as pd

import survivant_eodhd as SE

log = SE.log
SE.LIQ = 5e5  # sociétés liquides à 0,5 M€ par jour au moins à un moment (pour tester ce seuil)


def sim_stop(G, S, stop=.30, hold=26, cost=.003, suspend=None, buy=None):
    """sim30 de proba.SIM (lignes suivies une à une, vente à la protection ou après hold semaines) avec la protection en paramètre ;
    suspend[t] vrai : pas de vente à la protection cette semaine-là ; buy[t] faux : pas d'achat cette semaine-là."""
    t1997, T, retw = G['t1997'], G['T'], G['retw']
    tr, R = [], []
    for t in range(t1997, T - 1):
        s = np.array(S.get(t, []), dtype=int) if (buy is None or buy[t]) else np.array([], int)
        r = 0.0
        if len(s):
            k = len(s)
            tr.append(dict(t0=t, i=s, px=np.ones(k), q=np.ones(k) / k))
            r -= cost
        keep = []
        for x in tr:
            px1 = x['px'] * (1 + retw[x['i'], t + 1])
            pnl = x['q'] * (px1 - x['px'])
            if stop is not None and not (suspend is not None and suspend[t]):
                hit = (x['q'] > 0) & (px1 <= 1 - stop)
                if hit.any():
                    r -= (x['q'][hit] * px1[hit] * cost).sum()
                    x['q'][hit] = 0.0
            r += pnl.sum()
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
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00 = (
        D[k] for k in ('P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00'))
    t0 = time.time()
    G = SE.chain(P, V, dates, cols, secs, liq >= 5e5)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn0 = G['okn'].copy()
    log(f"\nUnivers : {len(cols)} sociétés liquides à 0,5 M€ par jour à un moment, calcul en {time.time() - t0:.0f} s")

    def market(okn):
        return np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])

    def ann(R):
        return (np.prod(1 + R) ** (52 / len(R)) - 1) * 100

    def per(R):
        return ' · '.join(f"{el} {(np.prod(1 + R[a - t2001:b - t2001]) ** (52 / (b - a)) - 1) * 100:+.1f}" for el, a, b in ERAS)

    def dd(R):
        eq = np.cumprod(1 + R)
        return (eq / np.maximum.accumulate(eq) - 1).min() * 100

    def cmp(R, ref):
        d = R - ref
        sg = [d[a - t2001:b - t2001].mean() * 5200 for el, a, b in ERAS]
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk))) if blk.std() > 0 else 0.0
        v = ' → BAT LA RÈGLE ACTUELLE' if all(x > 0 for x in sg) and tv >= 3 else ''
        return ' · '.join(f"{el} {x:+5.1f}" for (el, a, b), x in zip(ERAS, sg)) + f" pts/an (t {tv:4.1f}){v}"

    # ------------------------------------------------------------------ 1. seuil de liquidité
    log("\n1. Seuil de liquidité (échanges moyens des 26 semaines précédentes, connus à la date)")
    SELS, MK = {}, {}
    for L in (5e5, 1e6, 3e6, 1e7):
        G['okn'] = okn0 & (liq >= L)
        SELS[L] = {t: G['pick'](t, n=5, reserve=1, bondCap=2) for t in range(t2001, T - 1)}
        MK[L] = market(G['okn'])
    G['okn'] = okn0 & (liq >= 1e6)
    G['mkw'] = MK[1e6]
    M1 = MK[1e6][t2001 + 1:T]
    for L in (5e5, 1e6, 3e6, 1e7):
        R = sim_stop(G, SELS[L])
        n_inv = [int((okn0[:, t] & (liq[:, t] >= L)).sum()) for t in (t2001, int(np.searchsorted(dates, '2010-06-01')), T - 2)]
        log(f"  ≥ {L / 1e6:4.1f} M€ : {ann(R):+5.1f} %/an ({per(R)}), pire baisse {dd(R):.0f} % ; société moyenne de ce seuil "
            f"{ann(MK[L][t2001 + 1:T]):+5.1f} %/an ; sociétés investissables 2001 / 2010 / 2026 : {n_inv}")
    log(f"  société moyenne à 1 M€ (référence des autres études) : {ann(M1):+5.1f} %/an ({per(M1)})")

    # ------------------------------------------------------------------ 2. jour d'achat réel (cours journaliers)
    log("\n2. Jour d'achat réel : sélection du vendredi soir achetée le lundi (cours journaliers des sociétés choisies)")
    picked = sorted({i for L in (1e6, 3e6) for s in SELS[L].values() for i in s})
    daily = {}

    def one(i):
        x, err = SE.get(f"eod/{cols[i]}", **{'from': '2000-06-01'})
        return i, x, err
    t1 = time.time()
    with cf.ThreadPoolExecutor(8) as pool:
        for i, x, err in pool.map(one, picked):
            if not x:
                continue
            d = np.array([b['date'] for b in x], dtype='datetime64[D]')
            c = np.array([float(b.get('close') or 'nan') for b in x])
            a = np.array([float(b.get('adjusted_close') or 'nan') for b in x])
            o = np.array([float(b.get('open') or 'nan') for b in x])
            k = np.where((c > 0) & (a > 0) & (o > 0))[0]
            daily[i] = (d[k], a[k], o[k] * a[k] / c[k])
    log(f"  cours journaliers : {len(daily)} des {len(picked)} sociétés choisies, en {time.time() - t1:.0f} s")
    fri = np.array([np.datetime64(x) for x in dates], dtype='datetime64[D]')
    for L in (1e6, 3e6):
        rows_ = []
        for t in range(t2001, T - 27):
            for i in SELS[L].get(t, []):
                if i not in daily:
                    continue
                d, a, o = daily[i]
                k0 = np.searchsorted(d, fri[t], side='right')  # premier jour après le vendredi
                k1 = np.searchsorted(d, fri[t + 26], side='right')
                if k0 == 0 or k0 >= len(d) or k1 == 0 or k1 >= len(d) or (d[k0] - fri[t]).astype(int) > 4:
                    continue
                f0, f1 = a[k0 - 1], a[k1 - 1]
                rows_.append((t, f1 / f0 - 1, o[k1] / o[k0] - 1, a[k1] / a[k0] - 1, o[k0] / f0 - 1))
        if not rows_:
            continue
        X = np.array(rows_)
        wk = X[:, 0].astype(int)

        def nw(v):
            # moyenne par semaine de départ, puis t de Newey-West (26 retards)
            s = pd.Series(v).groupby(wk).mean().values
            u = s - s.mean()
            g = (u * u).sum() + sum(2 * (1 - k / 27) * (u[k:] * u[:-k]).sum() for k in range(1, 27))
            return s.mean(), s.mean() / np.sqrt(g / len(s) ** 2)
        m_o, t_o = nw(X[:, 2] - X[:, 1])
        m_c, t_c = nw(X[:, 3] - X[:, 1])
        m_g, t_g = nw(X[:, 4])
        log(f"  ≥ {L / 1e6:.0f} M€, {len(X)} lignes : 6 mois du vendredi au vendredi {X[:, 1].mean() * 100:+.1f} % ; du lundi ouverture au lundi "
            f"ouverture {X[:, 2].mean() * 100:+.1f} % (écart {m_o * 100:+.2f} point, t {t_o:.1f}) ; du lundi clôture au lundi clôture "
            f"{X[:, 3].mean() * 100:+.1f} % (écart {m_c * 100:+.2f}, t {t_c:.1f}) ; écart moyen vendredi clôture → lundi ouverture à "
            f"l'achat {m_g * 100:+.2f} % (t {t_g:.1f})")

    # ------------------------------------------------------------------ 3 et 4, pour les seuils 1 M€ (études) et 3 M€ (direct)
    for L in (1e6, 3e6):
        G['okn'] = okn0 & (liq >= L)
        G['mkw'] = mk = MK[L]
        S = SELS[L]
        ref = sim_stop(G, S)
        if L == 1e6:
            G['SEL'] = S
            log(f"\n  contrôle : protection −30 % recalculée identique à sim30 : {np.allclose(ref, G['sim30']())}")
        log(f"\n3. Durée de détention et protection, seuil {L / 1e6:.0f} M€ : règle actuelle (26 semaines, −30 %) {ann(ref):+.1f} %/an "
            f"({per(ref)}), pire baisse {dd(ref):.0f} %")
        for h in (13, 26, 52):
            for st in (None, .20, .30, .40):
                if h == 26 and st == .30:
                    continue
                R = sim_stop(G, S, stop=st, hold=h)
                lab = f"{h} semaines, " + ('sans protection' if st is None else f"protection −{int(st * 100)} %")
                log(f"  {lab:34s} {ann(R):+5.1f} %/an, pire baisse {dd(R):4.0f} % · écart {cmp(R, ref)}")
        log(f"\n4. Points de la revue du 31/01/2027, seuil {L / 1e6:.0f} M€")
        # a. protection suspendue pendant une panique générale
        okn, Pp, lo52 = G['okn'], G['P'], G['lo52']
        with np.errstate(invalid='ignore'):
            share = np.array([np.mean(Pp[okn[:, t], t] <= lo52[okn[:, t], t] * 1.0000001) * 100 if okn[:, t].sum() > 30 else np.nan
                              for t in range(T)])
        pan = np.zeros(T, bool)
        on = False
        for t in range(T):
            h_ = share[:t][np.isfinite(share[:t])]
            if len(h_) < 104 or not np.isfinite(share[t]):
                continue
            cut = max(20.0, np.median(h_) + 15.0)
            on = share[t] > cut - 10 if on else share[t] >= cut
            pan[t] = on
        log(f"  semaines de panique générale (2001-2026) : {int(pan[t2001:].sum())} ; part médiane des sociétés au plus bas de l'année "
            f"{np.nanmedian(share[t2001:]):.0f} %")
        R = sim_stop(G, S, suspend=pan)
        log(f"  {'protection suspendue pendant une panique':44s} {ann(R):+5.1f} %/an, pire baisse {dd(R):4.0f} % · écart {cmp(R, ref)}")
        # b. dosage selon l'agitation de la stratégie
        sig = pd.Series(ref).rolling(13, min_periods=13).std().values * np.sqrt(52)
        tgt = np.array([np.nanmedian(sig[:k]) if k > 104 else np.nan for k in range(len(sig))])
        w = np.clip(tgt / sig, 0, 1)
        w = np.where(np.isfinite(w), w, 1.0)
        wl = np.concatenate([[1.0], w[:-1]])  # exposition décidée la semaine précédente
        Rd = wl * ref
        Rc = wl.mean() * ref
        log(f"  {'dosage selon l agitation (exposition moyenne ' + str(int(wl.mean() * 100)) + ' %)':44s} {ann(Rd):+5.1f} %/an, pire baisse "
            f"{dd(Rd):4.0f} % · écart {cmp(Rd, ref)}")
        log(f"  {'  … même exposition moyenne en permanence':44s} {ann(Rc):+5.1f} %/an, pire baisse {dd(Rc):4.0f} % · dosage face à elle : "
            f"{cmp(Rd, Rc)}")
        # c. pause des achats pendant l'alerte krach
        idx = np.cumprod(1 + mk)
        m52 = np.full(T, np.nan)
        m52[52:] = idx[52:] / idx[:-52] - 1
        al = np.zeros(T, bool)
        on = False
        for t in range(T):
            if np.isfinite(m52[t]):
                on = m52[t] < -.15 if on else m52[t] <= -.20
            al[t] = on
        R = sim_stop(G, S, buy=~al)
        log(f"  {'pause des achats pendant l alerte krach (' + str(int(al[t2001:].sum())) + ' sem.)':44s} {ann(R):+5.1f} %/an, pire baisse "
            f"{dd(R):4.0f} % · écart {cmp(R, ref)}")

    # ------------------------------------------------------------------ 5. face à un fonds indiciel
    log("\n5. Face à un fonds indiciel (cours ajustés des dividendes, hebdomadaires)")
    G['okn'] = okn0 & (liq >= 3e6)
    G['mkw'] = MK[3e6]
    R3 = sim_stop(G, SELS[3e6])
    fr = pd.DatetimeIndex(pd.to_datetime(dates))
    for sym, lab in (('EXSA.XETRA', 'iShares STOXX Europe 600'), ('MEUD.PA', 'Amundi STOXX Europe 600'),
                     ('CW8.PA', 'Amundi MSCI World, éligible au PEA'), ('PCEU.PA', 'Amundi PEA MSCI Europe'),
                     ('SXXP.INDX', 'indice STOXX Europe 600, sans dividendes')):
        x, err = SE.get(f"eod/{sym}", period='w', **{'from': '2000-01-01'})
        if not x:
            log(f"  {sym} : {err or 'vide'}")
            continue
        s = pd.Series({SE.friday(b['date']): float(b.get('adjusted_close') or b.get('close')) for b in x}).sort_index()
        s = s[~s.index.duplicated()].reindex(fr).ffill()
        v = s.values
        k0 = int(np.argmax(np.isfinite(v)))
        a = max(k0, t2001)
        er = v[a + 1:T] / v[a:T - 1] - 1
        er = np.nan_to_num(er)
        rm = R3[a - t2001:]
        log(f"  {lab:40s} depuis le {dates[a]} : {ann(er):+5.1f} %/an, pire baisse {dd(er):.0f} % ; méthode (3 M€, protection) sur la "
            f"même période {ann(rm):+5.1f} %/an, pire baisse {dd(rm):.0f} %")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
