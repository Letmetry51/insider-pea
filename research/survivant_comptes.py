"""Filtre « comptes solides » du 🎯 et points d'alerte des comptes sur 25 ans, sans biais du survivant (26/11/2026 : François a pris
un mois de la formule « Fundamentals » d'EODHD : « C'est fait, j'ai pris l'abonnement donc TOUT faire ce que tu proposes »).

Jusqu'ici, le filtre n'était mesuré que sur 2 ans (revue_pistes.py, comptes Yahoo, mai 2024 - mai 2026 : rien de prouvé, sens
contraire société par société) ; tous les tests 1998-2026 tournaient sans lui. Ici : univers C de survivant_eodhd.py (12 bourses
de l'EEE, sociétés retirées de la cote comprises, liquidité connue à la date, 2001-2026) et comptes annuels EODHD de chaque société
(compte de résultat, bilan, flux de trésorerie), rangés comme ceux de financials.py et lus comme le calcul du soir
(comptes_dates_eodhd.js : ES.accountsAnalysis, 120 jours après la clôture, « pas lus » au-delà de 18 mois). Limite : EODHD donne
les comptes tels que publiés en dernier (retraitements éventuels) et moins de sociétés disparues avant 2013 (couverture affichée).

1. Couverture : part des sociétés investissables avec des comptes lus, chaque année, cotées et disparues.
2. Zone du 🎯 : écart à 6 mois avec la moyenne des sociétés investissables selon le verdict (solides, mitigés, en dégradation,
   pas lus, banques et assurances), par période ; et selon les points d'alerte calculés par scrapers/comptes_ia.alertes (dette
   nette au-delà de 4 fois l'EBITDA, intérêts couverts moins de 2 fois, capitaux propres négatifs, dilution, chiffre d'affaires
   −20 %, perte plus lourde, trésorerie de moins d'un an de déficit).
3. Sélection simulée (4 🎯 + 1 📣, 6 mois, frais 0,3 % par sens, protection −30 %) : sans aucun filtre (comme tous les tests
   jusqu'ici) ; filtre en direct (ES.pickThree : solides aux paliers 0 et 1, mitigés, pas lus, banques au palier 2, dégradation
   écartée, 📣 seulement solides) ; sans les seuls comptes en dégradation ; seulement des comptes solides ; sans point d'alerte.
Règle fixée avant le calcul : le filtre en direct est gardé s'il fait mieux que l'absence de filtre dans chaque période ; il ne
serait retiré (proposition à François) que si l'absence de filtre fait mieux dans chacune des périodes 2001-2008, 2009-2017 et
2018-2026 avec t ≥ 3 ; une autre variante ne le remplace qu'à la même condition ; sinon, résultat documenté. Lancé par
« Recherche (à la demande) » (script survivant_comptes.py), environ 35 minutes, environ 27 000 appels EODHD (10 par société pour
les comptes). Cours et comptes restent en mémoire (un fichier temporaire pour le calcul des verdicts, effacé aussitôt) ; la clé
n'est jamais affichée.
"""
import concurrent.futures as cf
import gc
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

import revue_pistes as RP
import survivant_eodhd as SE

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scrapers'))
import comptes_ia as CI  # noqa: E402

log = SE.log
LIQ = SE.LIQ
FLT = ('General::Sector,General::Industry,Financials::Income_Statement::yearly,Financials::Balance_Sheet::yearly,'
       'Financials::Cash_Flow::yearly')
MAP = {'Income_Statement': {'revenue': ('totalRevenue',), 'grossProfit': ('grossProfit',), 'operatingIncome': ('operatingIncome',),
                            'netIncome': ('netIncome', 'netIncomeApplicableToCommonShares'), 'ebitda': ('ebitda',),
                            'interestExpense': ('interestExpense',), 'ebit': ('ebit',), 'sga': ('sellingGeneralAdministrative',),
                            'depreciation': ('depreciationAndAmortization',)},
       'Balance_Sheet': {'totalAssets': ('totalAssets',), 'currentAssets': ('totalCurrentAssets',),
                         'currentLiabilities': ('totalCurrentLiabilities',), 'totalDebt': ('shortLongTermDebtTotal',),
                         'longTermDebt': ('longTermDebt', 'longTermDebtTotal'), 'cash': ('cash', 'cashAndEquivalents', 'cashAndShortTermInvestments'),
                         'equity': ('commonStockTotalEquity', 'totalStockholderEquity'), 'shares': ('commonStockSharesOutstanding',),
                         'retainedEarnings': ('retainedEarnings',), 'totalLiabilities': ('totalLiab',), 'receivables': ('netReceivables',),
                         'ppe': ('propertyPlantAndEquipmentNet', 'propertyPlantEquipment')},
       'Cash_Flow': {'cfo': ('totalCashFromOperatingActivities',), 'capex': ('capitalExpenditures',), 'fcf': ('freeCashFlow',)}}
NAMES = RP.NAMES


def num(v):
    try:
        x = float(v)
        return x if x == x and abs(x) != float('inf') else None
    except (TypeError, ValueError):
        return None


def section(x, name):
    """Sous-partie d'une réponse filtrée (clés « Financials::…::yearly ») ou complète (imbriquée)."""
    v = x.get(f'Financials::{name}::yearly')
    if v is None:
        v = (((x.get('Financials') or {}).get(name) or {}).get('yearly')) if isinstance(x.get('Financials'), dict) else None
    return v if isinstance(v, dict) else {}


def to_years(x):
    """Exercices EODHD → postes de financials.py (dépenses d'investissement négatives comme chez Yahoo)."""
    ys = {}
    cur = None
    for st, fields in MAP.items():
        for d, e in section(x, st).items():
            if not isinstance(e, dict) or len(str(d)) < 10:
                continue
            y = ys.setdefault(str(d)[:10], {'date': str(d)[:10]})
            cur = cur or e.get('currency_symbol')
            for k, src in fields.items():
                for s in src:
                    v = num(e.get(s))
                    if v is not None:
                        y[k] = v
                        break
    for y in ys.values():
        if y.get('capex') is not None:
            y['capex'] = -abs(y['capex'])
        if y.get('fcf') is None and y.get('cfo') is not None and y.get('capex') is not None:
            y['fcf'] = y['cfo'] + y['capex']
    return [ys[d] for d in sorted(ys) if len(ys[d]) > 3], cur


def fundamentals(cols):
    out, errs = {}, {}

    def one(i):
        x, err = SE.get('fundamentals/' + cols[i], filter=FLT)
        return i, x, err
    t0 = time.time()
    with cf.ThreadPoolExecutor(8) as pool:
        for n, (i, x, err) in enumerate(pool.map(one, range(len(cols)))):
            if err or not isinstance(x, dict):
                errs[err or 'vide'] = errs.get(err or 'vide', 0) + 1
                continue
            years, cur = to_years(x)
            if years:
                out[i] = {'years': years, 'currency': cur, 'sector': x.get('General::Sector') or '', 'industry': x.get('General::Industry') or ''}
            if n % 500 == 499:
                log(f"  comptes : {n + 1} sociétés en {time.time() - t0:.0f} s")
    log(f"  comptes : {len(out)} sociétés sur {len(cols)} avec des exercices, {sum(len(v['years']) for v in out.values())} exercices, "
        f"en {time.time() - t0:.0f} s ; erreurs {errs or 'aucune'}")
    return out


def verdicts(F, cols, secs, dates, T):
    """A[i, t] (codes de revue_pistes.CODES) par comptes_dates_eodhd.js ; fichiers temporaires effacés aussitôt."""
    inp = {cols[i]: dict(f, sector=f"{secs[i] if not str(secs[i]).startswith('?') else ''} {f['sector']}".strip()) for i, f in F.items()}
    fd, pin = tempfile.mkstemp(suffix='.json', dir='.')
    os.close(fd)
    pout = pin + '.out'
    try:
        with open(pin, 'w') as fh:
            json.dump(inp, fh)
        r = subprocess.run(['node', 'comptes_dates_eodhd.js', pin, pout], capture_output=True, text=True, timeout=1800)
        log('  ' + (r.stdout.strip() or r.stderr.strip()[-300:]))
        if r.returncode:
            raise RuntimeError('comptes_dates_eodhd.js a échoué')
        Dv = json.load(open(pout))
    finally:
        for p in (pin, pout):
            if os.path.exists(p):
                os.remove(p)
    A = np.zeros((len(cols), T), np.int8)
    dd = np.array(dates)
    for i, c in enumerate(cols):
        for d, v in Dv.get(c) or []:
            A[i, int(np.searchsorted(dd, d, side='left')):] = RP.CODES.get(v, 0)
    return A


def alert_mask(F, cols, secs, dates, T):
    """AL[i, t] : point d'alerte calculé (comptes_ia.alertes) sur les exercices connus à la date (120 jours après la clôture),
    jusqu'à l'exercice suivant ou 18 mois sans comptes."""
    AL = np.zeros((len(cols), T), bool)
    dd = np.array(dates)
    for i, f in F.items():
        sec = f"{secs[i]} {f.get('sector') or ''} {f.get('industry') or ''}"
        ys = f['years']
        for k, y in enumerate(ys):
            d0 = date.fromisoformat(y['date']) + timedelta(days=120)
            d1 = date.fromisoformat(ys[k + 1]['date']) + timedelta(days=120) if k + 1 < len(ys) else date.fromisoformat(y['date']) + timedelta(days=549)
            if CI.alertes({'years': ys[:k + 1][-4:], 'currency': f.get('currency')}, sec):
                AL[i, int(np.searchsorted(dd, d0.isoformat())):int(np.searchsorted(dd, d1.isoformat()))] = True
    return AL


def main():
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00, dl = (D[k] for k in ('P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00', 'dl'))
    F = fundamentals(cols)
    A = verdicts(F, cols, secs, dates, T)
    AL = alert_mask(F, cols, secs, dates, T)
    del F
    t0 = time.time()
    G = SE.chain(P, V, dates, cols, secs, liq >= LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    G['mkw'] = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    log(f"\nUnivers C : {len(cols)} sociétés, calcul en {time.time() - t0:.0f} s")

    # 1. couverture
    log("\n1. Sociétés investissables avec des comptes lus (cotées aujourd'hui | disparues depuis)")
    for y in (2001, 2004, 2007, 2010, 2013, 2016, 2019, 2022, 2025):
        t = int(np.searchsorted(dates, f'{y}-06-01'))
        inv = okn[:, t]
        cells = []
        for m in (~dl, dl):
            k = inv & m
            cells.append(f"{int((k & (A[:, t] > 0)).sum())}/{int(k.sum())} ({(k & (A[:, t] > 0)).sum() / max(k.sum(), 1) * 100:.0f} %)")
        log(f"  {y} : {cells[0]:18s} | {cells[1]} ; point d'alerte {int((inv & AL[:, t]).sum())}")

    # 2. zone du 🎯 : écart à 6 mois selon le verdict et les points d'alerte
    L = np.log1p(retw)
    C = np.concatenate([np.zeros((L.shape[0], 1)), np.cumsum(L, 1)], 1)
    mom, trend, s26, mpn, v52 = (G[k] for k in ('mom', 'trend', 's26', 'mpn', 'v52'))
    zone = okn & trend & (s26 >= .14) & (mom >= .3) & (mom <= 2) & ~(mpn < 1 / 3) & ~(v52 >= .8)
    log("\n2. Zone du 🎯 : écart à 6 mois avec la moyenne des sociétés investissables (points, une semaine sur 4 ; t sur les semaines)")

    def era_mean(sel_fn):
        out, allx = {}, []
        for el, a, b in ERAS:
            xs = []
            for t in range(a, min(b, T - 28), 4):
                ok = okn[:, t]
                fw = np.expm1(C[:, t + 27] - C[:, t + 1])
                m = np.nanmean(fw[ok])
                s = zone[:, t] & sel_fn(t)
                if s.sum() >= 3:
                    xs.append(np.nanmean(fw[s]) - m)
            out[el] = (np.mean(xs) * 100 if xs else np.nan, len(xs))
            allx += xs
        x = np.array(allx)
        tv = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else np.nan
        return out, x.mean() * 100 if len(x) else np.nan, tv
    for code in (1, 2, 3, 0, 4):
        o, mu, tv = era_mean(lambda t, c=code: A[:, t] == c)
        log(f"  comptes {NAMES[code]:24s} {mu:+5.1f} (t {tv:4.1f}) · " + ' · '.join(f"{el} {v:+5.1f}" for el, (v, n) in o.items()))
    for lab, fn in (("avec un point d'alerte", lambda t: AL[:, t]), ("sans point d'alerte (comptes lus)", lambda t: ~AL[:, t] & (A[:, t] > 0))):
        o, mu, tv = era_mean(fn)
        log(f"  {lab:32s} {mu:+5.1f} (t {tv:4.1f}) · " + ' · '.join(f"{el} {v:+5.1f}" for el, (v, n) in o.items()))

    # 3. sélection simulée
    SEL0 = G['SEL']
    pick = RP.make_pick(G)
    same = all(pick(t) == list(SEL0[t]) for t in range(t2001, T - 1, 13))
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

    def dd_(R):
        e = np.cumprod(1 + R)
        return (e / np.maximum.accumulate(e) - 1).min() * 100

    def cmp(R, ref):
        d = R - ref
        cells, sg = [], []
        for el, a, b in ERAS:
            x = d[a - t2001:b - t2001].mean() * 5200
            cells.append(f"{el} {x:+5.1f}")
            sg.append(x)
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        return cells, sg, blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
    none_, Snone = run(lambda t: pick(t))
    live, Slive = run(lambda t: pick(t, A=A, mode='live'))
    share = np.bincount([A[i, t] for t, s in Snone.items() for i in s], minlength=5) / max(sum(len(s) for s in Snone.values()), 1) * 100
    log("\n3. Sélection simulée, protection −30 %. Sociétés choisies sans filtre : " + ', '.join(
        f"{NAMES[c]} {share[c]:.0f} %" for c in (1, 2, 3, 0, 4)))
    for lab, R in (("sans filtre (tous les tests jusqu'ici)", none_), ('filtre en direct (ES.pickThree)', live)):
        log(f"  {lab:46s} {an(R):+5.1f} %/an, pire baisse {dd_(R):.0f} % ({cagr(R)})")
    c, sg, tv = cmp(live, none_)
    v = ('le filtre aide (meilleur dans chaque période)' if all(x > 0 for x in sg) else
         'LE FILTRE NUIT : à proposer à François (le retirer)' if all(x < 0 for x in sg) and tv <= -3 else 'pas tranché')
    log(f"  filtre en direct − sans filtre : {' · '.join(c)} pts/an (t {tv:4.1f}) → {v}")
    for lab, kw in (('sans les seuls comptes en dégradation', dict(A=A, mode='sans_mauvais')),
                    ('seulement des comptes solides', dict(A=A, mode='solides_seuls'))):
        R, _ = run(lambda t, k=kw: pick(t, **k))
        c, sg, tv = cmp(R, live)
        v = ' → BAT LE FILTRE EN DIRECT : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → filtre en direct gardé'
        log(f"  {lab:46s} {an(R):+5.1f} %/an, pire baisse {dd_(R):.0f} % · face au filtre en direct {' · '.join(c)} pts/an (t {tv:4.1f}){v}")
    G2 = dict(G, okn=okn & ~AL)  # 🎯 sans les sociétés avec un point d'alerte calculé (filtre en direct en plus)
    pick2 = RP.make_pick(G2)
    R, _ = run(lambda t: pick2(t, A=A, mode='live'))
    c, sg, tv = cmp(R, live)
    v = ' → BAT LE FILTRE EN DIRECT : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejetée'
    lab = "filtre en direct et sans point d'alerte"
    log(f"  {lab:46s} {an(R):+5.1f} %/an, pire baisse {dd_(R):.0f} % · face au filtre en direct {' · '.join(c)} pts/an (t {tv:4.1f}){v}")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
