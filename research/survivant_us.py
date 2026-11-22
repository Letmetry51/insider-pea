"""Contrôle sur les États-Unis sans biais du survivant (22/11/2026, François : « Oui le faire »).

L'aide de l'outil cite un contrôle sur ≈ 1 500 sociétés du S&P 1500 (Yahoo, sociétés d'aujourd'hui) : +3,6 points à 6 mois sur
1997-2026, +2,5 sur 2013-2026 (t 1,0). Ici, toutes les actions ordinaires des bourses américaines (NYSE, Nasdaq, NYSE American,
NYSE Arca, Cboe BZX) chez EODHD, cotées ou retirées de la cote (un code de société disparue repris par une société cotée est
écarté : impossible de séparer les deux), cours hebdomadaires ajustés depuis 1998. Investissables à chaque date : les 1 500 plus
échangées (moyenne des 26 semaines précédentes, en dollars), cours d'au moins 5 $, taille proche du S&P 1500. Mêmes règles et mêmes
calculs que l'Europe (sans plafond par secteur : secteurs inconnus), portefeuille simulé 2001-2026, protection −30 %, frais 0,3 %
par sens, face à la moyenne des sociétés investissables et au S&P 500 (SPY, dividendes réinvestis).
  A. sociétés encore cotées, 1 500 plus échangées aujourd'hui (comme le contrôle Yahoo) ;
  B. sociétés encore cotées, 1 500 plus échangées à la date ;
  C. toutes, disparues comprises, 1 500 plus échangées à la date : le chiffre honnête.
Les cours restent en mémoire ; la clé n'est jamais affichée. Lancé par « Recherche (à la demande) » (script survivant_us.py),
environ 45 minutes, 25 000 appels EODHD environ.
"""
import gc
import re
import time

import numpy as np
import pandas as pd

import cycle_litterature as CL
import cycle_secteurs as CS
import survivant_eodhd as SE
import survivant_pratique as SP

log = SE.log
US_EX = {'NYSE', 'NASDAQ', 'NYSE MKT', 'NYSE AMERICAN', 'AMEX', 'NYSE ARCA', 'BATS', 'CBOE BZX'}
JUNK = re.compile(r'\b(rights?|warrants?|units?|etf|etn|fund|notes?|preferred|depositary|adrs?|ads)\b', re.I)
TOP = 1500


def universe():
    out, stat = [], {}
    act = set()
    for dl in (0, 1):
        y, err = SE.get('exchange-symbol-list/US', **({'delisted': 1} if dl else {}))
        if err:
            log(f"  liste {'retirées' if dl else 'cotées'} : {err}")
        n = 0
        for r in y or []:
            name, code = str(r.get('Name') or ''), str(r.get('Code') or '')
            if (r.get('Type') != 'Common Stock' or str(r.get('Exchange') or '').upper() not in US_EX or r.get('Currency') not in ('USD', None)
                    or JUNK.search(name) or not code):
                continue
            if dl and code in act:
                stat['repris'] = stat.get('repris', 0) + 1
                continue
            if not dl:
                act.add(code)
            out.append(dict(sym=f"{code}.US", code=code, dl=dl))
            n += 1
        stat[dl] = n
    log(f"  actions ordinaires américaines retenues : {stat.get(0, 0)} cotées, {stat.get(1, 0)} retirées de la cote "
        f"({stat.get('repris', 0)} codes repris par une société cotée écartés)")
    return out


def main():
    t00 = time.time()
    if not SE.KEY:
        log("Secret EODHD_API_KEY absent : rien à faire.")
        return
    u, err = SE.get('user')
    log(f"Formule « {(u or {}).get('subscriptionType')} », {(u or {}).get('apiRequests')} appels utilisés aujourd'hui" if u else f"Compte : {err}")
    rows = universe()
    idx = list(pd.date_range('1998-01-02', pd.Timestamp.today().normalize() - pd.Timedelta(days=1), freq='W-FRI'))
    P, C, V = SE.download(rows, idx)
    dates = [str(d.date()) for d in idx]
    T = len(idx)
    tov = np.where(np.isfinite(C) & np.isfinite(V), C * V / 5, np.nan)
    liq = pd.DataFrame(tov.T).rolling(26, min_periods=13).mean().values.T
    del tov
    nspk = SE.despike(P)
    dl = np.array([r['dl'] for r in rows], bool)
    elig = np.isfinite(liq) & np.isfinite(C) & (C >= 5)

    def top_mask(sel):
        """1 500 plus échangées à chaque date parmi sel (cours ≥ 5 $)."""
        M = np.zeros_like(elig)
        for t in range(T):
            ok = np.where(elig[:, t] & sel)[0]
            if len(ok):
                M[ok[np.argsort(-liq[ok, t])[:TOP]], t] = True
        return M
    Mall = top_mask(np.ones(len(rows), bool))
    Mact = top_mask(~dl)
    valid = np.isfinite(P).sum(1) >= 104
    keep = valid & ((Mall.sum(1) >= 13) | (Mact.sum(1) >= 13))  # un trimestre au moins parmi les 1 500
    ki = np.where(keep)[0]
    log(f"  pics isolés retirés : {nspk} ; sociétés parmi les 1 500 plus échangées 13 semaines au moins : {int((keep & ~dl).sum())} cotées, "
        f"{int((keep & dl).sum())} retirées")
    P, C, V, liq, dl, Mall, Mact = P[ki], C[ki], V[ki], liq[ki], dl[ki], Mall[ki], Mact[ki]
    cols = [rows[k]['sym'] for k in ki]
    secs = ['?' + c for c in cols]
    del rows
    gc.collect()
    last = np.array([np.where(np.isfinite(p))[0].max() for p in P])
    gone = dl & (last < T - 3)
    t2001 = int(np.searchsorted(dates, '2001-01-01'))
    ERAS = [('2001-2008', t2001, int(np.searchsorted(dates, '2009-01-01'))),
            ('2009-2017', int(np.searchsorted(dates, '2009-01-01')), int(np.searchsorted(dates, '2018-01-01'))),
            ('2018-2026', int(np.searchsorted(dates, '2018-01-01')), T - 1)]
    # S&P 500 (SPY, dividendes réinvestis)
    x, err = SE.get('eod/SPY.US', period='w', **{'from': '2000-01-01'})
    spy = None
    if x:
        s = pd.Series({SE.friday(b['date']): float(b['adjusted_close']) for b in x}).sort_index()
        s = s[~s.index.duplicated()].reindex(pd.DatetimeIndex(pd.to_datetime(dates))).ffill().values
        spy = s[t2001 + 1:T] / s[t2001:T - 1] - 1

    def ann(R):
        return (np.prod(1 + R) ** (52 / len(R)) - 1) * 100

    def per(R):
        return ' · '.join(f"{el} {(np.prod(1 + R[a - t2001:b - t2001]) ** (52 / (b - a)) - 1) * 100:+.1f}" for el, a, b in ERAS)

    if spy is not None:
        log(f"  S&P 500 (SPY) : {ann(spy):+.1f} %/an ({per(spy)})")
    res = {}
    lastliq = np.nan_to_num(liq[:, -1])
    A = ~dl & np.isin(np.arange(len(cols)), np.where(~dl)[0][np.argsort(-lastliq[~dl])[:TOP]])
    for lab, sel, mask in (("A. cotées, 1 500 plus échangées aujourd'hui", A, None), ('B. cotées, 1 500 plus échangées à la date', ~dl, Mact),
                           ('C. toutes, disparues comprises', np.ones(len(cols), bool), Mall)):
        ii = np.where(sel)[0]
        okm = np.ones((len(ii), T), bool) if mask is None else mask[ii]
        t0 = time.time()
        G = SE.chain(P[ii], V[ii], dates, [cols[i] for i in ii], [secs[i] for i in ii], okm)
        G['t1997'] = t2001
        G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
        okn = G['okn']
        G['mkw'] = mk = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
        M = mk[t2001 + 1:T]
        R0 = CS.weekly_slots(G, lambda t, g=G: g['SEL'].get(t, []))
        R1 = SP.sim_stop(G, G['SEL'])
        d = R1 - M
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        q = np.array([np.prod(1 + R1[k:k + 13]) - np.prod(1 + M[k:k + 13]) for k in range(0, len(R1) - 12, 13)])
        ds = ' ; '.join(f"{n_} essais {CL.dsr(q, n_)[4] * 100:.0f} %" for n_ in (10, 100, 1000))
        # écart des choix à 6 mois et sort des choix qui disparaissent
        Lr = np.log1p(retw)
        Cc = np.concatenate([np.zeros((Lr.shape[0], 1)), np.cumsum(Lr, 1)], 1)
        ex, tt, ng, n, rg = [], [], 0, 0, []
        gi, li = gone[ii], last[ii]
        for t in range(t2001, T - 27):
            s = list(G['SEL'].get(t, []))
            if not s:
                continue
            fw = np.clip(np.expm1(Cc[:, t + 27] - Cc[:, t + 1]), -1, 5)
            ex.append(np.mean(fw[s]) - np.mean(fw[okn[:, t]]))
            tt.append(t)
            for i in s:
                n += 1
                if gi[i] and t < li[i] <= t + 26:
                    ng += 1
                    rg.append(fw[i])
        ex, tt = np.array(ex), np.array(tt)
        pe = ' · '.join(f"{el} {ex[(tt >= a) & (tt < b)].mean() * 100:+.1f}" for el, a, b in ERAS)
        log(f"\n  {lab} : {len(ii)} sociétés ({int(gone[ii].sum())} disparues), calcul en {time.time() - t0:.0f} s")
        log(f"    protection −30 % : {ann(R1):+.1f} %/an ({per(R1)}) contre {ann(M):+.1f} pour la société moyenne ({per(M)}) ; écart t {tv:.1f} ; "
            f"sans protection {ann(R0):+.1f} %/an")
        log(f"    écart des choix à 6 mois {ex.mean() * 100:+.1f} points ({pe}) ; {ng} choix sur {n} disparus dans les 6 mois, "
            f"{np.mean(rg) * 100 if rg else float('nan'):+.0f} % en moyenne ; ratio de Sharpe dégonflé : {ds}")
        res[lab] = (ann(R1), ann(M))
        del G, Lr, Cc
        gc.collect()
    log("\nRésumé (protection −30 % comprise)")
    for k, (a, b) in res.items():
        log(f"  {k:46s} {a:+.1f} %/an, société moyenne {b:+.1f}, écart {a - b:+.1f} points par an")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
