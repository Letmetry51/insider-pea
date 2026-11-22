"""Trois vérifications sans biais du survivant (22/11/2026, François : « Faire ce qui est pertinent », abonnement EODHD).

Univers de survivant_eodhd.py (12 bourses, sociétés disparues comprises, liquidité connue à la date), seuil du 🎯 en direct
(3 M€ échangés par jour), 2001-2026, protection −30 %, frais 0,3 % par sens. Une société disparue est vendue à son dernier cours.
1. Un vrai portefeuille de 10, 15 ou 20 lignes : chaque semaine, les lignes arrivées à 6 mois ou à −30 % sont vendues et les places
   libres reprises dans l'ordre de la sélection de la semaine (4 🎯 + 1 📣), à part égale du portefeuille ; liquidités sinon.
   Départ en janvier 2001, puis départs décalés de 4 en 4 semaines : rendement sur 5 et 10 ans, part des départs qui battent la
   société moyenne et le fonds iShares STOXX Europe 600 (EXSA, dividendes compris) ; et la part de chance dans le choix des
   sociétés : 100 portefeuilles qui piochent au hasard parmi les 10 meilleures sociétés de chaque semaine.
2. Auto-surveillance : modèle du 📒 suivi réel (ES.EDGE_MODEL, proba.py : +4 points à 6 mois, écarts types selon le nombre de
   semaines mûres, fausses alertes) recalculé sur ces données (10 sociétés par semaine), comparé aux chiffres en service.
3. Alertes du soir « 📣 Bond du jour » : chiffres des emails (research/bond_jour_seuil.py, sociétés d'aujourd'hui : +9 points à
   6 mois à 5 fois le volume ou plus, +6 entre 4 et 5 fois, +8 au plus haut de l'année, +11 au-delà de +60 % du plus bas d'un an,
   acheté le lendemain plutôt que le lundi +1 point) refaits sur les cours journaliers EODHD, sociétés disparues comprises (dernier
   cours gardé 130 séances), bonds retenus seulement si la société est assez liquide ce jour-là (1 M€, puis 3 M€ comme l'alerte).
Les cours restent en mémoire (rien dans research/out) ; la clé n'est jamais affichée. Lancé par « Recherche (à la demande) »
(script survivant_portefeuille.py), environ 15 minutes, 8 300 appels EODHD.
"""
import concurrent.futures as cf
import gc
import json
import time
import warnings

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
import proba as PB
import survivant_eodhd as SE
from bond_jour_seuil import per6, weekly_bond

log = SE.log
# ES.EDGE_MODEL en service au 22/11/2026 (euro_signal/core.js), pour la comparaison
LIVE = dict(W=(1, 2, 3, 4, 6, 8, 13, 17, 26, 39, 52, 78, 104), mu6=.04, mu3=.0219,
            sd6=(.1472, .1404, .1366, .1338, .1292, .1256, .1168, .111, .0986, .0849, .0743, .0569, .0457),
            sd3=(.1063, .1008, .097, .0939, .0888, .0846, .0743, .0678, .056, .0474, .0408, .0306, .0241))


def book(retw, S, nmax, t0, t1, hold=26, stop=.30, cost=.003):
    """Portefeuille de nmax lignes au plus, des semaines t0 à t1 : rendements hebdomadaires, frais compris. S[t] : sociétés de
    la semaine, dans l'ordre ; une ligne vendue après hold semaines ou à −30 % de son prix d'achat (clôture de la semaine)."""
    cash, pos, R, prev = 1.0, [], [], 1.0
    for t in range(t0, t1):
        keep = []
        for p in pos:
            if t - p[1] >= hold or p[3] <= 1 - stop:
                cash += p[2] * (1 - cost)
            else:
                keep.append(p)
        pos = keep
        if len(pos) < nmax:
            held = {p[0] for p in pos}
            tot = cash + sum(p[2] for p in pos)
            for i in S.get(t, []):
                if len(pos) >= nmax or cash <= 1e-9:
                    break
                if i in held:
                    continue
                amt = min(cash, tot / nmax)
                cash -= amt
                pos.append([i, t, amt * (1 - cost), 1.0])
                held.add(i)
        for p in pos:
            r = retw[p[0], t + 1]
            p[2] *= 1 + r
            p[3] *= 1 + r
        v = cash + sum(p[2] for p in pos)
        R.append(v / prev - 1)
        prev = v
    return np.array(R)


def ann(R):
    return (np.prod(1 + R) ** (52 / len(R)) - 1) * 100


def dd(R):
    eq = np.cumprod(1 + R)
    return (eq / np.maximum.accumulate(eq) - 1).min() * 100


def fl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def tmonth(M, X, months):
    """t de l'écart moyen, regroupé par mois (cas qui se chevauchent)"""
    ii, tt = np.where(M & np.isfinite(X))
    if len(ii) < 40:
        return np.nan
    g = pd.Series(X[ii, tt]).groupby(months[tt]).mean()
    return float(g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))) if len(g) > 10 else np.nan


def portfolio(G, dates, T, t2001, ERAS):
    retw, mk, S = G['retw'], G['mkw'], G['SEL']
    x, err = SE.get('eod/EXSA.XETRA', period='w', **{'from': '2000-01-01'})
    etf = np.full(T, np.nan)
    if x:
        s = pd.Series({SE.friday(b['date']): fl(b.get('adjusted_close')) for b in x}).sort_index()
        s = s[~s.index.duplicated()]
        etf = s[s > 0].reindex(pd.DatetimeIndex(pd.to_datetime(dates))).ffill().values
    else:
        log(f"  fonds EXSA : {err}")
    er = np.full(T, np.nan)
    er[:-1] = etf[1:] / etf[:-1] - 1
    log("\n1. Portefeuille de 10, 15 ou 20 lignes (places libres reprises dans l'ordre de la sélection de la semaine)")
    M = mk[t2001 + 1:T]
    log(f"  société moyenne (3 M€) : {ann(M):+.1f} %/an, pire baisse {dd(M):.0f} %")
    fe0 = np.isfinite(er[t2001:T - 1])
    if fe0.any():
        a0 = int(np.argmax(fe0)) + t2001
        log(f"  fonds STOXX Europe 600 (EXSA) depuis {dates[a0][:7]} : {ann(er[a0:T - 1]):+.1f} %/an, pire baisse {dd(er[a0:T - 1]):.0f} %")
    Rref = G['sim30']()
    log(f"  référence de l'étude (26 tranches de 5 lignes, sim30) : {ann(Rref):+.1f} %/an, pire baisse {dd(Rref):.0f} % · " +
        ' · '.join(f"{el} {ann(Rref[a - t2001:b - t2001]):+.1f}" for el, a, b in ERAS))
    for n in (10, 15, 20):
        R = book(retw, S, n, t2001, T - 1)
        per = ' · '.join(f"{el} {ann(R[a - t2001:b - t2001]):+.1f} (marché {ann(M[a - t2001:b - t2001]):+.1f})" for el, a, b in ERAS)
        log(f"  {n} lignes, départ janvier 2001 : {ann(R):+.1f} %/an, pire baisse {dd(R):.0f} % · {per}")
        for yrs_ in (5, 10):
            h = 52 * yrs_
            res = []
            for s0 in range(t2001, T - 1 - h, 4):
                Rs = book(retw, S, n, s0, s0 + h)
                e = er[s0:s0 + h]
                res.append((ann(Rs), ann(mk[s0 + 1:s0 + h + 1]), ann(e) if np.isfinite(e).all() else np.nan, dd(Rs)))
            A = np.array(res)
            fe = np.isfinite(A[:, 2])
            vs_etf = f"{np.mean(A[fe, 0] > A[fe, 2]) * 100:.0f} % ({int(fe.sum())} départs avec le fonds)" if fe.any() else '·'
            log(f"    sur {yrs_} ans, {len(A)} départs (2001 à {dates[T - 1 - h][:4]}) : médiane {np.median(A[:, 0]):+.1f} %/an, de "
                f"{np.percentile(A[:, 0], 5):+.1f} à {np.percentile(A[:, 0], 95):+.1f} (5 % et 95 % des départs), pire {A[:, 0].min():+.1f} ; "
                f"bat la société moyenne {np.mean(A[:, 0] > A[:, 1]) * 100:.0f} % des fois (écart médian "
                f"{np.median(A[:, 0] - A[:, 1]):+.1f} points), le fonds {vs_etf} ; pire baisse médiane {np.median(A[:, 3]):.0f} %")
    # part de chance : sociétés piochées au hasard parmi les 10 meilleures de chaque semaine (même nombre de lignes)
    rng = np.random.default_rng(2026)
    S10 = {t: list(v) for t, v in G['SEL10'].items() if t >= t2001}
    for n in (10, 20):
        base = ann(book(retw, S, n, t2001, T - 1))
        mc = []
        for _ in range(100):
            Sr = {t: list(rng.permutation(v)) for t, v in S10.items()}
            mc.append(ann(book(retw, Sr, n, t2001, T - 1)))
        mc = np.array(mc)
        log(f"  {n} lignes piochées au hasard parmi les 10 meilleures de chaque semaine (100 tirages) : médiane {np.median(mc):+.1f} %/an, "
            f"de {np.percentile(mc, 5):+.1f} à {np.percentile(mc, 95):+.1f} (5 % et 95 % des tirages) ; dans l'ordre de l'outil "
            f"{base:+.1f} ; société moyenne {ann(M):+.1f} : la battent {np.mean(mc > ann(M)) * 100:.0f} % des tirages")


def watchdog(G):
    log("\n2. Modèle de l'auto-surveillance (proba.py) recalculé sans biais du survivant, seuil 3 M€, 10 sociétés par semaine")
    cap, orig = [], PB.log

    def tee(*a):
        cap.append(' '.join(str(x) for x in a))
        orig(*a)
    PB.log = tee
    try:
        PB.part2_3(G, PB.lines(G))
    except Exception as e:  # le reste de l'étude continue
        log(f"  calcul impossible : {type(e).__name__}")
    finally:
        PB.log = orig
    par = next((json.loads(s[len('PARAMÈTRES '):]) for s in cap if s.startswith('PARAMÈTRES ')), None)
    if not par:
        return
    log("\n  Comparaison avec ES.EDGE_MODEL en service (écart type de la moyenne selon les semaines mûres, sans biais / en service) :")
    for h in (6, 3):
        cells, ratios = [], []
        for W, s in zip(LIVE['W'], LIVE[f'sd{h}']):
            v = par[f'sd{h}'].get(str(W))
            if v:
                cells.append(f"W {W} : {v * 100:.1f} / {s * 100:.1f}")
                ratios.append(v / s)
        if ratios:
            log(f"    à {h} mois : " + ', '.join(cells) + f" ; rapport moyen {np.mean(ratios):.2f} (de {min(ratios):.2f} à {max(ratios):.2f})")
    log("    écart moyen des lignes à 6 mois par période : " + ' · '.join(f"{k} {v * 100:+.1f}" for k, v in par['hist6'].items()) +
        f" (avantage prudent retenu : {LIVE['mu6'] * 100:+.0f} points)")
    for k, v in (par.get('signals') or {}).items():
        log(f"    signal {k} : écart avec / sans {v['gap'] * 100:+.1f} points")


def daily(cols, liq, dates, T, gone):
    """Cours journaliers EODHD de toutes les sociétés, en mémoire : signaux du bond du jour et rendement à 6 mois de chaque séance."""
    N = len(cols)
    ax = pd.bdate_range('1998-06-01', pd.Timestamp.today().normalize() - pd.Timedelta(days=1)).values.astype('datetime64[D]')
    Td0 = len(ax)
    O, H, L, C, Vd = (np.full((N, Td0), np.nan, np.float32) for _ in range(5))

    def one(k):
        x, err = SE.get(f"eod/{cols[k]}", **{'from': '1998-06-01'})
        if not x:
            return k, None, err
        try:
            df = pd.DataFrame(x)
            d = pd.to_datetime(df['date'], errors='coerce').values.astype('datetime64[D]')
            A = np.column_stack([pd.to_numeric(df[f], errors='coerce').values.astype(float) if f in df else np.full(len(df), np.nan)
                                 for f in ('open', 'high', 'low', 'close', 'adjusted_close', 'volume')])
        except Exception as e:  # réponse au format inattendu : société ignorée, comptée dans les erreurs
            return k, None, type(e).__name__
        return k, (d, A), None
    errs, t1 = {}, time.time()
    with cf.ThreadPoolExecutor(8) as pool:
        for n_, (k, res, err) in enumerate(pool.map(one, range(N))):
            if err:
                errs[err] = errs.get(err, 0) + 1
            if res is not None:
                d, A = res
                j = np.searchsorted(ax, d)
                with np.errstate(invalid='ignore'):
                    m = (j < Td0) & (ax[np.minimum(j, Td0 - 1)] == d) & (A[:, 3] > 0) & (A[:, 4] > 0)
                j, A = j[m], A[m]
                f = A[:, 4] / A[:, 3]
                O[k, j], H[k, j], L[k, j], C[k, j], Vd[k, j] = A[:, 0] * f, A[:, 1] * f, A[:, 2] * f, A[:, 4], A[:, 5]
            if n_ % 500 == 499:
                log(f"  {n_ + 1} séries en {time.time() - t1:.0f} s")
    nspk = SE.despike(C)
    bad = ~np.isfinite(C)
    for A in (O, H, L, Vd):
        A[bad] = np.nan
    has = np.isfinite(C).any(0)
    O, H, L, C, Vd, ax = O[:, has], H[:, has], L[:, has], C[:, has], Vd[:, has], ax[has]
    gc.collect()
    Td = len(ax)
    days = pd.DatetimeIndex(ax)
    log(f"  cours journaliers : {int(np.isfinite(C).any(1).sum())} sociétés sur {N}, {Td} séances ({str(ax[0])} → {str(ax[-1])}), "
        f"en {time.time() - t1:.0f} s ; pics isolés retirés {nspk} ; erreurs {errs or 'aucune'}")
    fr = np.array(dates, dtype='datetime64[D]')
    wk = np.clip(np.searchsorted(fr, ax, side='right') - 1, 0, T - 1)
    Z = dict(Td=Td, days=days, yrs=np.array(days.year), months=np.array(days.year * 100 + days.month),
             fri=np.array(days.day_of_week == 4), LQ=np.nan_to_num(liq[:, wk]).astype(np.float32))  # liquidité connue à la date
    shift, roll = FB.shift, HT.roll
    with np.errstate(all='ignore'), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(Vd) > 0) & (C > 0)
        del H, L
        ret1 = C / shift(C, 1) - 1
        Vp = np.where(Vd > 0, Vd, np.nan).astype(np.float32)
        Z['vx'] = Vd / shift(roll(Vp, 50, 'mean', 40), 1)
        del Vd
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = ok & (C > m200) & (m50 > m200)
        Z['newhi'] = C > shift(roll(C, 252, 'max', 200), 1)
        Z['lo60'] = C / roll(C, 252, 'min', 200) - 1 >= .6
        mom = shift(C, 21) / shift(C, 252) - 1
        Z['feu'] = trend & (mom >= .6) & (mom <= 2.0) & (C > m50)
        Z['up8'] = ok & (ret1 >= .08) & trend
        del ret1, m50, m200, mom, trend, ok
        gc.collect()
        # sortie : clôture 125 séances après l'achat à l'ouverture du lendemain ; une société disparue (ou suspendue) garde son
        # dernier cours 130 séances ; ouvertures aberrantes (hors de 0,5 à 2 fois les clôtures voisines) écartées
        Z['lastd'] = lastd = np.array([np.where(np.isfinite(c))[0].max() if np.isfinite(c).any() else -1 for c in C])
        Cx = pd.DataFrame(C.T).ffill(limit=130).values.T
        O1, C1 = shift(O, -1), shift(C, -1)
        good = (O1 > .5 * C) & (O1 < 2 * C) & (O1 > .5 * C1) & (O1 < 2 * C1)
        rr = shift(Cx, -125) / O1 - 1
        Z['rr'] = np.where(good & (rr < 5), rr, np.nan).astype(np.float32)
        del Cx, O1, C1, good, O, rr
        gc.collect()
    Z['WB'], Z['endw'] = weekly_bond(C, Vp, days, cols)
    Z['gone_d'] = gone & (lastd < Td - 10)
    return Z


def measure(Z, lab, lq):
    """Écart à 6 mois des alertes parmi les cas permis par lq (sociétés × séances), face à la moyenne de ces mêmes cas ; renvoie
    {règle : (écart moyen, écarts par période, nombre de cas)}."""
    rr, yrs, months, Td, WB, endw, lastd, gone_d = (Z[k] for k in ('rr', 'yrs', 'months', 'Td', 'WB', 'endw', 'lastd', 'gone_d'))
    up8, vx, newhi, lo60 = Z['up8'], Z['vx'], Z['newhi'], Z['lo60']
    with np.errstate(all='ignore'), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        z = np.where(lq, rr, np.nan)
        mu = np.nanmean(z, 0)
        mu[np.isfinite(z).sum(0) < 30] = np.nan
        del z
        X6 = rr - mu[None, :]
    X6[:, yrs < 2000] = np.nan
    R5, V4 = up8 & (vx >= 5) & lq, up8 & (vx >= 4) & lq
    A4 = V4 & ~R5
    rules = [('🎯 au feu vert, chaque vendredi', Z['feu'] & Z['fri'][None, :] & lq), ('📣 de la semaine, acheté le lundi', WB & lq),
             ('bond à 5 fois le volume ou plus', R5), ('bond entre 4 et 5 fois', A4),
             ("  … entre 4 et 5 fois, au plus haut de l'année", A4 & newhi), ("  … entre 4 et 5 fois, sous le plus haut", A4 & ~newhi),
             ('toutes les alertes (4 fois ou plus)', V4), ("  … à +60 % ou plus du plus bas d'un an", V4 & lo60),
             ("  … à moins de +60 % du plus bas", V4 & ~lo60)]
    log(f"\n  {lab} : écart à 6 mois avec la moyenne des mêmes sociétés, achat à l'ouverture du lendemain, une entrée par société et "
        f"par semestre ; en tout [2000-2008 / 2009-2017 / 2018-2026] (t regroupé par mois)")
    out = {}
    for lab_, Mk in rules:
        Md = FB.dedup(Mk, 125)
        a, pp, n_ = per6(Md, X6, yrs)
        out[lab_] = (a, pp, n_)
        ii, tt = np.where(Md & np.isfinite(X6))
        dis = gone_d[ii] & (lastd[ii] <= tt + 125)
        dtxt = f", dont {int(dis.sum())} disparues dans les 6 mois ({np.mean(rr[ii[dis], tt[dis]]) * 100:+.0f} % en moyenne)" if dis.any() else ''
        log(f"    {lab_:46s} {a * 100:+5.1f} points [{' / '.join('  ·  ' if not np.isfinite(v) else f'{v * 100:+5.1f}' for v in pp)}] "
            f"(t {tmonth(Md, X6, months):.1f}), {n_} cas{dtxt}")
    log("    acheté le lendemain plutôt que le lundi qui suit la semaine du bond (mêmes sociétés, 6 mois) :")
    for lab_, Mk in (('5 fois ou plus', R5), ('entre 4 et 5 fois', A4)):
        ii, tt = np.where(FB.dedup(Mk, 125) & (yrs[None, :] >= 2000))
        k_ = endw[tt] + 130 < Td
        ii, tt = ii[k_], tt[k_]
        if len(ii) < 30:
            log(f"      {lab_:18s} trop peu de cas ({len(ii)})")
            continue
        e = endw[tt]
        became = WB[ii, e]
        en, em = X6[ii, tt], X6[ii, e]
        m = np.isfinite(en) & np.isfinite(em)
        mb, mn = m & became, m & ~became
        log(f"      {lab_:18s} {int(m.sum())} cas ; {became[m].mean() * 100:.0f} % finissent la semaine en 📣 ; lendemain "
            f"{np.mean(en[m]) * 100:+.1f}, lundi {np.mean(em[m]) * 100:+.1f} (écart {np.mean(en[m] - em[m]) * 100:+.1f}) ; semaine finie "
            f"en 📣 : écart {np.mean(en[mb] - em[mb]) * 100 if mb.any() else float('nan'):+.1f} ; sans 📣 : "
            f"{np.mean(en[mn]) * 100 if mn.any() else float('nan'):+.1f} points à 6 mois")
    del X6
    gc.collect()
    return out


EMAILS = ("\n  Chiffres des emails jusqu'au 22/11/2026 (sociétés d'aujourd'hui, 2000-2026) : +9 points à 5 fois ou plus ; +6 entre 4 et 5 fois (+8 au plus haut "
          "de l'année, +5,5 en dessous) ; +11 au-delà de +60 % du plus bas d'un an, +6 à +7 en dessous ; lendemain plutôt que lundi +1 "
          "point (+3 quand la semaine finit en 📣) ; 4 sur 10 (5 fois) et 2 sur 3 (4 à 5 fois) ne finissent pas la semaine en 📣 ; "
          "🎯 au feu vert +4,5, 📣 de la semaine +7,1")


def bonds(cols, liq, dates, T, gone):
    log("\n3. Alertes « 📣 Bond du jour » sur cours journaliers, sociétés disparues comprises")
    Z = daily(cols, liq, dates, T, gone)
    for Lq in (1e6, 3e6):
        measure(Z, f"liquidité à la date ≥ {Lq / 1e6:.0f} M€", Z['LQ'] >= Lq)
    log(EMAILS)


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00, gone = (
        D[k] for k in ('P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00', 'gone'))
    del D
    G = SE.chain(P, V, dates, cols, secs, liq >= 3e6)
    del P, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    G['mkw'] = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    log(f"\nCalculs prêts en {time.time() - t00:.0f} s ({SE.calls[0]} appels) : {len(cols)} sociétés, {int(gone.sum())} disparues")
    portfolio(G, dates, T, t2001, ERAS)
    watchdog(G)
    del G, retw, okn
    gc.collect()
    bonds(cols, liq, dates, T, gone)
    u, err = SE.get('user')
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
