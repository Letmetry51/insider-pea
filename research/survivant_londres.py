"""Londres (et la Suisse si elle a assez de sociétés) sans biais du survivant (23/11/2026 ; François, 22/11/2026 : « Oui faire ce qui
est pertinent », test 4 de la liste « Comment exploiter davantage les données disponibles avec l'abonnement ? »).

Les États-Unis n'ont montré aucun avantage une fois les sociétés disparues comprises (survivant_us.py) ; Londres, marché le plus
proche de l'Europe du PEA mais jamais utilisé pour régler l'outil, dit si l'avantage européen se retrouve ailleurs. Toutes les
actions ordinaires de la Bourse de Londres chez EODHD (ISIN GB, JE, GG ou IM, cotées en pence ou en livres), cotées ou retirées de
la cote, sans les fonds, sociétés d'investissement et titres annexes (un code de société disparue repris par une société cotée est
écarté) ; cours hebdomadaires ajustés depuis 1998, liquidité en euros connue à la date. Mêmes règles et mêmes calculs que l'Europe
(secteurs Yahoo des sociétés connues de l'outil), portefeuille simulé 2001-2026, protection −30 %, frais 0,3 % par sens, face à la
société moyenne investissable et au FTSE 100 (iShares ISF, dividendes réinvestis) :
  A. sociétés encore cotées et liquides aujourd'hui (au moins 1 M€ par jour), sans filtre à la date (comme une étude sur les
     sociétés d'aujourd'hui) ;
  B. sociétés encore cotées, au moins 3 M€ par jour à la date ;
  C. toutes, disparues comprises, au moins 3 M€ par jour à la date (seuil du 🎯 en direct) : le chiffre honnête.
Suisse (ISIN CH ou LI, francs suisses) : univers C seulement, s'il compte au moins 80 sociétés investissables en 2010.
Les cours restent en mémoire ; la clé n'est jamais affichée. Lancé par « Recherche (à la demande) » (script survivant_londres.py),
environ 30 minutes, 6 000 appels EODHD.
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
JUNK = re.compile(r'\b(rights?|warrants?|units?|etf|etc|etn|fund|funds|vct|venture capital|investment trust|trust plc|ucits|notes?|bonds?|'
                  r'preference|pref|loan|debentures?|acquisition corp|spac|zdp|c shares?)\b', re.I)
MARKETS = (dict(name='Londres', ex='LSE', isin=('GB', 'JE', 'GG', 'IM'), cur={'GBX': .01, 'GBP': 1.0, 'GBp': .01}, fx='EURGBP.FOREX',
                bench=('FTSE 100 (ISF, dividendes réinvestis)', 'ISF.LSE'), ysuf='L', abc=True),
           dict(name='Suisse', ex='SW', isin=('CH', 'LI'), cur={'CHF': 1.0}, fx='EURCHF.FOREX', bench=('SMI (CSSMI, dividendes réinvestis)', 'CSSMI.SW'),
                ysuf='SW', abc=False))


def universe(m):
    out, stat, act = [], {}, set()
    for dl in (0, 1):
        y, err = SE.get(f"exchange-symbol-list/{m['ex']}", **({'delisted': 1} if dl else {}))
        if err:
            log(f"  liste {'retirées' if dl else 'cotées'} : {err}")
        n = 0
        for r in y or []:
            name, code, isin = str(r.get('Name') or ''), str(r.get('Code') or ''), str(r.get('Isin') or '')
            if (r.get('Type') != 'Common Stock' or r.get('Currency') not in m['cur'] or JUNK.search(name) or not code
                    or isin[:2] not in m['isin']):
                continue
            if dl and code in act:
                stat['repris'] = stat.get('repris', 0) + 1
                continue
            if not dl:
                act.add(code)
            out.append(dict(sym=f"{code}.{m['ex']}", code=code, ex=m['ex'], isin=isin, cur=r.get('Currency'), dl=dl))
            n += 1
        stat[dl] = n
    out.sort(key=lambda r: r['dl'])
    seen, rows = set(), []
    for r in out:
        if r['isin'] in seen:
            continue
        seen.add(r['isin'])
        rows.append(r)
    log(f"  actions ordinaires retenues : {stat.get(0, 0)} cotées, {stat.get(1, 0)} retirées ({stat.get('repris', 0)} codes repris écartés) ; "
        f"{len(rows)} après dédoublonnage par ISIN")
    return rows


def run(m):
    t00 = time.time()
    log(f"\n========== {m['name']} ==========")
    rows = universe(m)
    idx = list(pd.date_range(SE.START, pd.Timestamp.today().normalize() - pd.Timedelta(days=1), freq='W-FRI'))
    P, C, V = SE.download(rows, idx)
    dates = [str(d.date()) for d in idx]
    T = len(idx)
    if m.get('fx'):
        x, err = SE.get(f"eod/{m['fx']}", period='w', **{'from': SE.START})
        s = pd.Series({SE.friday(b['date']): float(b['close']) for b in x or [] if b.get('close')})
        fx = s[~s.index.duplicated()].reindex(idx).ffill().bfill().values if len(s) else np.full(T, np.nan)
        log(f"  change {m['fx']} : {len(s)} semaines" + ('' if len(s) else f" ({err})"))
    else:  # place cotée en euros
        fx = np.ones(T)
    unit = np.array([m['cur'][r['cur']] for r in rows])[:, None]
    tov = np.where(np.isfinite(C) & np.isfinite(V), C * unit * V / 5 / fx[None, :], np.nan)   # en euros par jour
    liq = pd.DataFrame(tov.T).rolling(26, min_periods=13).mean().values.T
    del tov, C
    nspk = SE.despike(P)
    dl = np.array([r['dl'] for r in rows], bool)
    valid = np.isfinite(P).sum(1) >= 104
    ever = np.nanmax(np.where(np.isfinite(liq), liq, 0), 1) >= 1e6
    keep = valid & ever
    ki = np.where(keep)[0]
    rows = [rows[k] for k in ki]
    P, V, liq, dl = P[ki], V[ki], liq[ki], dl[ki]
    cols = [r['sym'] for r in rows]
    SE.YSUF[m['ex']] = m['ysuf']
    secs, hit = SE.sectors(rows)
    last = np.array([np.where(np.isfinite(p))[0].max() for p in P])
    gone = dl & (last < T - 3)
    log(f"  pics isolés retirés : {nspk} ; sociétés liquides à un moment (≥ 1 M€ par jour, 2 ans de cours) : {int((~dl).sum())} cotées, "
        f"{int(dl.sum())} retirées, dont {int(gone.sum())} disparues avant la fin ; secteur connu pour {hit}")
    for y in (2001, 2005, 2010, 2015, 2020, 2025):
        t = int(np.searchsorted(dates, f'{y}-06-01'))
        inv = np.isfinite(P[:, t]) & (np.nan_to_num(liq[:, t]) >= 3e6)
        log(f"  {y} : {int((inv & ~dl).sum())} sociétés à 3 M€ par jour encore cotées aujourd'hui, {int((inv & dl).sum())} disparues depuis")
    t2010 = int(np.searchsorted(dates, '2010-06-01'))
    n2010 = int((np.isfinite(P[:, t2010]) & (np.nan_to_num(liq[:, t2010]) >= 3e6)).sum())
    n2010b = int((np.isfinite(P[:, t2010]) & (np.nan_to_num(liq[:, t2010]) >= 1e6)).sum())
    only1 = False
    if not m['abc'] and n2010 < 80:
        if m.get('lq1') and n2010b >= 80:
            only1 = True
            log(f"  {n2010} sociétés investissables à 3 M€ en 2010, {n2010b} à 1 M€ : test à 1 M€ seulement")
        else:
            log(f"  {n2010} sociétés investissables en 2010 (à 1 M€ : {n2010b}) : trop peu pour la méthode (5 choix par semaine, 2 par "
                f"secteur), test non fait")
            return None
    t2001 = int(np.searchsorted(dates, '2001-01-01'))
    ERAS = [('2001-2008', t2001, int(np.searchsorted(dates, '2009-01-01'))),
            ('2009-2017', int(np.searchsorted(dates, '2009-01-01')), int(np.searchsorted(dates, '2018-01-01'))),
            ('2018-2026', int(np.searchsorted(dates, '2018-01-01')), T - 1)]

    def ann(R):
        return (np.prod(1 + R) ** (52 / len(R)) - 1) * 100

    def per(R):
        return ' · '.join(f"{el} {(np.prod(1 + R[a - t2001:b - t2001]) ** (52 / (b - a)) - 1) * 100:+.1f}" for el, a, b in ERAS)
    lab_b, codes_b = m['bench']
    for code_b in ((codes_b,) if isinstance(codes_b, str) else codes_b):
        x, err = SE.get(f"eod/{code_b}", period='w', **{'from': '2000-01-01'})
        if x:
            lab_b = f"{lab_b} [{code_b}]"
            break
    if x:
        s = pd.Series({SE.friday(b['date']): float(b['adjusted_close']) for b in x if b.get('adjusted_close')}).sort_index()
        s = s[~s.index.duplicated()].reindex(pd.DatetimeIndex(pd.to_datetime(dates))).ffill().values
        bm = s[t2001 + 1:T] / s[t2001:T - 1] - 1
        if np.isfinite(bm).all():
            log(f"  {lab_b} : {ann(bm):+.1f} %/an ({per(bm)})")
        else:
            a0 = int(np.argmax(np.isfinite(bm)))
            log(f"  {lab_b} depuis {dates[t2001 + a0][:7]} : {ann(bm[a0:][np.isfinite(bm[a0:])]):+.1f} %/an")
    else:
        log(f"  {lab_b} : {err}")
    lastliq = np.nan_to_num(liq[:, -1])
    U = [('C. toutes, disparues comprises, ≥ 3 M€ à la date', np.ones(len(cols), bool), liq >= 3e6)]
    if m.get('lq1'):
        U = ([] if only1 else U) + [('C bis. toutes, disparues comprises, ≥ 1 M€ à la date', np.ones(len(cols), bool), liq >= 1e6)]
    if m['abc']:
        U = [("A. cotées et liquides aujourd'hui (≥ 1 M€), sans filtre à la date", ~dl & (lastliq >= 1e6), None),
             ('B. cotées, ≥ 3 M€ à la date', ~dl, liq >= 3e6)] + U
    res = {}
    for lab, sel, mask in U:
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
        ds = ' ; '.join(f"{n_} essais {CL.dsr(q, n_)[4] * 100:.0f} %" for n_ in (10, 100))
        Lr = np.log1p(retw)
        Cc = np.concatenate([np.zeros((Lr.shape[0], 1)), np.cumsum(Lr, 1)], 1)
        ex, tt, ng, n, rg = [], [], 0, 0, []
        gi, li = gone[ii], last[ii]
        for t in range(t2001, T - 27):
            s_ = list(G['SEL'].get(t, []))
            if not s_:
                continue
            fw = np.clip(np.expm1(Cc[:, t + 27] - Cc[:, t + 1]), -1, 5)
            ex.append(np.mean(fw[s_]) - np.mean(fw[okn[:, t]]))
            tt.append(t)
            for i in s_:
                n += 1
                if gi[i] and t < li[i] <= t + 26:
                    ng += 1
                    rg.append(fw[i])
        ex, tt = np.array(ex), np.array(tt)
        pe = ' · '.join(f"{el} {ex[(tt >= a) & (tt < b)].mean() * 100:+.1f}" for el, a, b in ERAS)
        ninv = int(np.median([okn[:, t].sum() for t in range(t2001, T - 1)]))
        log(f"\n  {lab} : {len(ii)} sociétés ({int(gone[ii].sum())} disparues), {ninv} investissables par semaine (médiane), calcul en "
            f"{time.time() - t0:.0f} s")
        log(f"    protection −30 % : {ann(R1):+.1f} %/an ({per(R1)}) contre {ann(M):+.1f} pour la société moyenne ({per(M)}) ; écart t {tv:.1f} ; "
            f"sans protection {ann(R0):+.1f} %/an")
        log(f"    écart des choix à 6 mois {ex.mean() * 100:+.1f} points ({pe}) ; {ng} choix sur {n} disparus dans les 6 mois, "
            f"{np.mean(rg) * 100 if rg else float('nan'):+.0f} % en moyenne ; ratio de Sharpe dégonflé : {ds}")
        res[lab] = (ann(R1), ann(M), [(np.prod(1 + R1[a - t2001:b - t2001]) / np.prod(1 + M[a - t2001:b - t2001])) ** (52 / (b - a)) * 100 - 100
                                      for el, a, b in ERAS])
        del G, Lr, Cc
        gc.collect()
    log(f"\n  Résumé {m['name']} (protection −30 % comprise ; écart par an face à la société moyenne, 2001-2008 / 2009-2017 / 2018-2026)")
    for k, (a, b, pp) in res.items():
        log(f"    {k:66s} {a:+.1f} %/an, société moyenne {b:+.1f}, écart {a - b:+.1f} points ({' / '.join(f'{v:+.1f}' for v in pp)})")
    log(f"  {m['name']} terminé en {time.time() - t00:.0f} s")
    return res


def main():
    if not SE.KEY:
        log("Secret EODHD_API_KEY absent : rien à faire.")
        return
    t00 = time.time()
    u, err = SE.get('user')
    log(f"Formule « {(u or {}).get('subscriptionType')} », {(u or {}).get('apiRequests')} appels utilisés aujourd'hui" if u else f"Compte : {err}")
    for m in MARKETS:
        run(m)
        gc.collect()
    u, err = SE.get('user')
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
