"""💎 Valeur sur 25 ans, émissions d'actions pour le 🎯 et 📣 bond avec ou sans résultats, sans biais du survivant (27/11/2026,
François : « Comme j'ai encore les deux abonnements, est-ce qu'il y a encore d'autres choses à tester? », après « TOUT faire ce que
tu proposes »).

Univers C de survivant_eodhd.py (12 bourses de l'EEE, sociétés retirées de la cote comprises, liquidité connue à la date,
2001-2026) et comptes annuels EODHD (comme survivant_comptes.py, plus les dates de dépôt et les dates de publication des résultats).

1. 💎 Valeur. Testé jusqu'ici sur 2 ans seulement (backtest/valeur.py, comptes Yahoo, mai 2024 - avril 2026 : +5,1 points à
   6 mois, t 1,7, « fragile ») ; dosage conseillé 70 % 🎯 / 30 % 💎 fondé sur les facteurs européens de Kenneth French, pas sur
   nos sélections. Règle rejouée chaque semaine comme ES.pickValue : sociétés liquides (≥ 1 M€ par jour) à cours / fonds propres
   positif ; tiers le moins cher ; F-score ≥ 7 ; ni dernier exercice en perte, ni zone de détresse d'Altman, ni comptes en
   dégradation ; hausse sur 12 mois ≥ −40 % ; volatilité < 80 % ; pas de semaine à ×2,5 ou −65 % sur un an ; banques et
   assurances exclues (pas de F-score) ; meilleur F-score puis cours / fonds propres le plus bas, 2 par secteur, 10 lignes.
   Cours / fonds propres : clôture brute × actions du dernier bilan connu (corrigées des divisions survenues depuis, repérées par
   les sauts du rapport clôture brute / clôture ajustée) / capitaux propres convertis dans la devise de cotation. Non rejoués :
   ⚡ (saut du jour) et 🐻 (ventes à découvert), sans historique.
   Mesures : écart à 6 mois des 10 💎 avec la société moyenne et part des chutes de 25 % ; portefeuille (tranches de 26 semaines,
   frais 0,3 % par sens, protection −30 % comme le 🎯) face à la société moyenne ; mélange 70 / 30 face au 🎯 seul (sélection en
   direct, filtre des comptes compris) : rendement par période et pire baisse. Contrôles : cours / fonds propres et F-score de la
   dernière semaine face à ceux du calcul du soir ; délai réel de dépôt des comptes, et variante où les comptes ne sont connus
   qu'à la date de dépôt quand elle dépasse 120 jours.
   Règles fixées avant le calcul : le 💎 tient si son portefeuille bat la société moyenne dans chacune des 3 périodes ; il serait
   démenti (proposition à François de le retirer) s'il fait moins bien dans chacune avec t ≤ −3 ; sinon pas tranché. Le dosage
   70 / 30 ne changerait (proposition) que si le 🎯 seul fait mieux dans chacune des 3 périodes avec t ≥ 3 sans pire baisse plus
   forte.
2. Émissions d'actions pour le 🎯 (McLean, Pontiff et Watanabe, 2009 : les sociétés qui émettent des actions font moins bien
   ensuite, dans 41 pays). Variation du nombre d'actions entre les deux derniers bilans connus (divisions corrigées). Zone du 🎯 :
   écart à 6 mois par groupe (≥ +10 %, +2 à +10 %, −2 à +2 %, ≤ −2 %). Sélection en direct sans les sociétés à +10 % ou plus.
   Règle fixée avant : retenue (proposition) seulement si elle bat la sélection en direct dans chacune des 3 périodes avec t ≥ 3.
3. 📣 bond avec ou sans résultats (Chan, 2003 : après une forte variation, le cours continue quand elle accompagne une nouvelle,
   revient en arrière sans nouvelle). Dates de publication EODHD (Earnings::History, reportDate). Bond du 📣 (hausse ≥ 8 % sur la
   semaine avec 3 fois le volume, ou 2 fois au plus haut de l'année) la semaine d'une publication (ou la suivante pour une
   publication un vendredi) contre bond sans publication, parmi les sociétés suivies (une publication connue à moins de 200
   jours). Place 📣 réservée aux bonds de résultats, ou aux bonds sans résultats. Règle fixée avant : une variante ne remplace le
   📣 en direct que si elle fait mieux dans chacune des 3 périodes avec t ≥ 3 et si les dates couvrent au moins la moitié des
   sociétés investissables dans chaque période.
Lancé par « Recherche (à la demande) » (script survivant_valeur.py), environ 30 minutes, environ 27 000 appels EODHD (10 par
société pour les comptes). Cours et comptes restent en mémoire (fichiers temporaires pour les calculs en JavaScript, effacés
aussitôt) ; la clé n'est jamais affichée.
"""
import concurrent.futures as cf
import gc
import json
import os
import subprocess
import tempfile
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

import cycle_secteurs as CS
import revue_pistes as RP
import survivant_comptes as SC
import survivant_eodhd as SE

log = SE.log
FLT = SC.FLT + ',Earnings::History'
STALE = 548
RD_GAP = []  # (publication − clôture de la période), jours, pour le contrôle des dates


def to_years(x):
    """Exercices comme survivant_comptes.to_years, avec la date de dépôt la plus précoce des trois états (« filed »)."""
    years, cur = SC.to_years(x)
    eq2 = {}
    for d, e in SC.section(x, 'Balance_Sheet').items():
        if isinstance(e, dict) and len(str(d)) >= 10 and SC.num(e.get('totalStockholderEquity')) is not None:
            eq2[str(d)[:10]] = SC.num(e.get('totalStockholderEquity'))
    filed = {}
    for st in SC.MAP:
        for d, e in SC.section(x, st).items():
            if isinstance(e, dict) and len(str(d)) >= 10:
                f = str(e.get('filing_date') or '')[:10]
                if len(f) == 10 and f > str(d)[:10]:
                    k = str(d)[:10]
                    filed[k] = min(filed.get(k, f), f)
    for y in years:
        if y['date'] in filed:
            y['filed'] = filed[y['date']]
        if y['date'] in eq2:
            y['equity2'] = eq2[y['date']]
    return years, cur


def report_dates(x):
    """Dates de publication passées (Earnings::History, reportDate), au moins 5 jours après la clôture de la période."""
    h = x.get('Earnings::History')
    if h is None and isinstance(x.get('Earnings'), dict):
        h = x['Earnings'].get('History')
    out = set()
    if isinstance(h, dict):
        for k, e in h.items():
            if not isinstance(e, dict):
                continue
            d, p = str(e.get('reportDate') or '')[:10], str(e.get('date') or k or '')[:10]
            if len(d) != 10 or d[:2] not in ('19', '20') or d > time.strftime('%Y-%m-%d'):
                continue
            try:
                gap = (date.fromisoformat(d) - date.fromisoformat(p)).days if len(p) == 10 else None
            except ValueError:
                gap = None
            if gap is not None:
                RD_GAP.append(gap)
                if gap < 5:
                    continue
            out.add(d)
    return sorted(out)


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
            rd = report_dates(x)
            if years or rd:
                out[i] = {'years': years, 'currency': cur, 'sector': x.get('General::Sector') or '',
                          'industry': x.get('General::Industry') or '', 'rd': rd}
            if n % 500 == 499:
                log(f"  comptes : {n + 1} sociétés en {time.time() - t0:.0f} s")
    log(f"  comptes : {sum(1 for v in out.values() if v['years'])} sociétés sur {len(cols)} avec des exercices, "
        f"{sum(len(v['years']) for v in out.values())} exercices ; dates de résultats pour {sum(1 for v in out.values() if v['rd'])} "
        f"sociétés ({sum(len(v['rd']) for v in out.values())} publications), en {time.time() - t0:.0f} s ; erreurs {errs or 'aucune'}")
    return out


def value_dates(F, cols, secs, dates, T, mode):
    """Par semaine : verdict (codes de revue_pistes), F-score (−1 inconnu), écarté par les comptes (perte, détresse, dégradation),
    indice dans F[i]['years'] de l'exercice lu (−1 aucun) ; valeur_dates_eodhd.js, fichiers temporaires effacés aussitôt."""
    inp = {cols[i]: {'years': f['years'], 'currency': f.get('currency'), 'industry': f.get('industry') or '',
                     'sector': f"{secs[i] if not str(secs[i]).startswith('?') else ''} {f.get('sector') or ''}".strip()}
           for i, f in F.items() if f['years']}
    fd, pin = tempfile.mkstemp(suffix='.json', dir='.')
    os.close(fd)
    pout = pin + '.out'
    try:
        with open(pin, 'w') as fh:
            json.dump(inp, fh)
        r = subprocess.run(['node', 'valeur_dates_eodhd.js', pin, pout, mode], capture_output=True, text=True, timeout=2400)
        log('  ' + (r.stdout.strip() or r.stderr.strip()[-300:]))
        if r.returncode:
            raise RuntimeError('valeur_dates_eodhd.js a échoué')
        Dv = json.load(open(pout))
    finally:
        for p in (pin, pout):
            if os.path.exists(p):
                os.remove(p)
    N = len(cols)
    A = np.zeros((N, T), np.int8)
    F9 = np.full((N, T), -1, np.int8)
    BAD = np.zeros((N, T), bool)
    YI = np.full((N, T), -1, np.int16)
    dd = np.array(dates)
    ix = {c: i for i, c in enumerate(cols)}
    for c, pts in Dv.items():
        i = ix[c]
        yd = {y['date']: k for k, y in enumerate(F[i]['years'])}
        for k, (d, key, f9, loss, alt, _fin, ld) in enumerate(pts):
            a = int(np.searchsorted(dd, d, side='left'))
            b = int(np.searchsorted(dd, pts[k + 1][0], side='left')) if k + 1 < len(pts) else T
            if a >= b:
                continue
            A[i, a:b] = RP.CODES.get(key, 0)
            F9[i, a:b] = f9 if f9 is not None else -1
            BAD[i, a:b] = bool(loss) or alt == 'distress' or key == 'bad'
            YI[i, a:b] = yd.get(ld, -1)
    return A, F9, BAD, YI


def split_jumps(P, C):
    """Facteur cumulé des divisions et regroupements : sauts du rapport clôture brute / clôture ajustée (au-delà de ×1,5 ou ÷1,5
    d'une semaine à l'autre ; les dividendes ne le font bouger que de quelques %)."""
    N, T = P.shape
    J = np.ones((N, T))
    nj = 0
    for i in range(N):
        s = C[i].astype(float) / P[i].astype(float)
        ok = np.where(np.isfinite(s) & (s > 0))[0]
        if len(ok) < 2:
            continue
        q = s[ok[1:]] / s[ok[:-1]]
        for k in np.where((q > 1.5) | (q < 1 / 1.5))[0]:
            J[i, ok[k + 1]:] *= q[k]
            nj += 1
    return J, nj


def split_votes(F, J, dates):
    """Autour de chaque division repérée, les bilans donnent-ils le nombre d'actions tel que publié (saut du même facteur) ou
    recalculé après coup (pas de saut) ? Renvoie [tel que publié, recalculé]."""
    votes = [0, 0]
    for i, f in F.items():
        ys = [y for y in f['years'] if y.get('shares')]
        if len(ys) < 2:
            continue
        for w in np.where(np.diff(J[i]) != 0)[0] + 1:
            q = J[i, w] / J[i, w - 1]
            y0 = [y for y in ys if y['date'] < dates[w]]
            y1 = [y for y in ys if y['date'] >= dates[w]]
            if not y0 or not y1 or (date.fromisoformat(y1[0]['date']) - date.fromisoformat(y0[-1]['date'])).days > 460:
                continue
            r = y1[0]['shares'] / y0[-1]['shares']
            if r > 0:
                votes[0 if abs(np.log(r) + np.log(q)) < abs(np.log(r)) else 1] += 1
    return votes


def fx_table(curs, dates):
    """Devise pour 1 € chaque semaine (EODHD, EUR…FOREX) ; devise sans cours : absente."""
    idx = [pd.Timestamp(d) for d in dates]
    out = {'EUR': np.ones(len(dates))}
    miss = []
    for c in sorted(c for c in curs if c and c != 'EUR' and c.isalpha() and len(c) == 3):
        x, err = SE.get(f'eod/EUR{c}.FOREX', period='w', **{'from': SE.START})
        s = pd.Series({SE.friday(b['date']): float(b['close']) for b in x or [] if b.get('close')})
        s = s[s > 0] if len(s) else s
        if len(s) >= 100:
            out[c] = s.reindex(idx).ffill().bfill().values
        else:
            miss.append(c)
    log(f"  change : {len(out) - 1} devises ({', '.join(sorted(out))}) ; sans cours : {', '.join(miss) or 'aucune'}")
    return out


def pb_matrix(F, YI, C, J, cur_t, FX, dates, field='equity'):
    """Cours / fonds propres chaque semaine : clôture brute × actions du bilan lu (corrigées des divisions depuis la clôture) /
    capitaux propres convertis dans la devise de cotation ; capitaux propres négatifs ou valeur hors de 0,02 à 200 : inconnu."""
    N, T = C.shape
    PB = np.full((N, T), np.nan, np.float32)
    odd = 0
    for i, f in F.items():
        ys = f['years']
        qc = cur_t[i]
        rc = (f.get('currency') or '').upper() or qc
        if rc not in FX or qc not in FX:
            continue
        k = FX[qc] / FX[rc]
        yi = YI[i]
        for j in np.unique(yi[yi >= 0]):
            y = ys[int(j)]
            E, S = y.get(field, y.get('equity')), y.get('shares')
            if E is None or S is None or not S > 0 or not E > 0:
                continue
            tb = min(int(np.searchsorted(dates, y['date'])), T - 1)
            m = yi == j
            pb = C[i, m] * (S * J[i, tb] / J[i, m]) / (E * k[m])
            bad = ~((pb > .02) & (pb < 200))
            odd += int((bad & np.isfinite(pb)).sum())
            PB[i, m] = np.where(bad, np.nan, pb)
    return PB, odd


def issuance(F, YI, J, dates, T):
    """Variation du nombre d'actions entre les deux derniers bilans connus (exercices consécutifs, divisions corrigées)."""
    N = YI.shape[0]
    DS = np.full((N, T), np.nan, np.float32)
    for i, f in F.items():
        ys = f['years']
        yi = YI[i]
        for j in np.unique(yi[yi >= 1]):
            y1, y0 = ys[int(j)], ys[int(j) - 1]
            S1, S0 = y1.get('shares'), y0.get('shares')
            if not (S1 and S0 and S1 > 0 and S0 > 0):
                continue
            gap = (date.fromisoformat(y1['date']) - date.fromisoformat(y0['date'])).days
            if not 300 <= gap <= 430:
                continue
            t1, t0 = (min(int(np.searchsorted(dates, y['date'])), T - 1) for y in (y1, y0))
            ds = S1 / (S0 * J[i, t0] / J[i, t1]) - 1
            if -.9 < ds < 10:
                DS[i, yi == j] = ds
    return DS


def results_weeks(F, dates, T, N):
    """RESW : semaine d'une publication (et la suivante pour un vendredi) ; COV : publication connue à moins de 200 jours."""
    RESW, COV = np.zeros((N, T), bool), np.zeros((N, T), bool)
    for i, f in F.items():
        for d in f.get('rd') or []:
            dd = date.fromisoformat(d)
            w = int(np.searchsorted(dates, d, side='left'))
            if w < T:
                RESW[i, w] = True
                if dd.weekday() == 4 and w + 1 < T:
                    RESW[i, w + 1] = True
            a = int(np.searchsorted(dates, (dd - timedelta(days=200)).isoformat()))
            b = int(np.searchsorted(dates, (dd + timedelta(days=200)).isoformat()))
            COV[i, a:b] = True
    return RESW, COV


def main():
    u, err = SE.get('user')
    used = int((u or {}).get('apiRequests') or 0)
    if str((u or {}).get('apiRequestsDate') or '') != time.strftime('%Y-%m-%d', time.gmtime()):
        used = 0  # compteur d'un autre jour : il repart à zéro au premier appel compté (constaté le 27/11/2026)
    if used > 70000:  # ce test en prend environ 27 000 (10 par société pour les comptes), limite 100 000 par jour
        log(f"{used} appels EODHD déjà utilisés aujourd'hui : relancer après la remise à zéro du compteur")
        return
    D = SE.prepare()
    if D is None:
        return
    P, C, V, liq, cols, secs, dates, T, t2001, ERAS, t00, dl, rows = (D[k] for k in (
        'P', 'C', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00', 'dl', 'rows'))
    N = len(cols)
    F = fundamentals(cols)

    # contrôles des données : dépôt des comptes, dates de publication, divisions
    lag = np.array([(date.fromisoformat(y['filed']) - date.fromisoformat(y['date'])).days
                    for f in F.values() for y in f['years'] if y.get('filed')])
    ny = sum(len(f['years']) for f in F.values())
    if len(lag):
        log(f"  date de dépôt connue pour {len(lag)} exercices sur {ny} ; délai médian {np.median(lag):.0f} jours ; "
            f"au-delà de 120 jours : {np.mean(lag > 120) * 100:.0f} % ; au-delà de 180 jours : {np.mean(lag > 180) * 100:.0f} %")
    if RD_GAP:
        g = np.array(RD_GAP)
        log(f"  publications : délai médian après la clôture de la période {np.median(g):.0f} jours ; moins de 5 jours (écartées) "
            f"{np.mean(g < 5) * 100:.0f} % ; 10 à 120 jours {np.mean((g >= 10) & (g <= 120)) * 100:.0f} %")
    J, nj = split_jumps(P, C)
    votes = split_votes(F, J, dates)
    log(f"  divisions ou regroupements repérés : {nj}, dans {int((J[:, -1] != 1).sum())} séries ; nombre d'actions des bilans "
        f"autour d'une division : tel que publié {votes[0]} fois, recalculé après coup {votes[1]} fois")
    if nj < 20:
        log("  attention : presque aucune division repérée sur 25 ans : la clôture « brute » d'EODHD serait déjà ajustée des divisions")
    if votes[1] > votes[0]:
        J = np.ones_like(J)  # bilans déjà recalculés : pas de correction
        log("  → nombre d'actions des bilans pris tel quel")
    else:
        log("  → nombre d'actions corrigé des divisions survenues depuis la clôture")
    A, F9, BAD, YI = value_dates(F, cols, secs, dates, T, 'lag120')
    A0 = SC.verdicts(F, cols, secs, dates, T)
    log(f"  verdicts identiques à ceux de survivant_comptes.py : {np.mean(A == A0) * 100:.2f} % des cases")
    del A0
    cur_t = [r['cur'] for r in rows]
    FX = fx_table({c for c in cur_t} | {(f.get('currency') or '').upper() for f in F.values()}, dates)
    try:
        site = json.load(open('../data/euro-signal.json'))
        live_rows = {r.get('sym'): r for r in (site.get('rank') or {}).get('rows') or [] if r.get('sym')}
        v10 = [x.get('sym') for x in (site.get('rank') or {}).get('value10') or [] if isinstance(x, dict)]
        del site
    except (OSError, ValueError):
        live_rows, v10 = {}, []
    ysym = [f"{r['code']}.{SE.YSUF.get(r['ex'], r['ex'])}" for r in rows]
    tl = T - 1

    def check_pb(PBm):
        rp = []
        for i in range(N):
            r = live_rows.get(ysym[i])
            if r and not dl[i] and r.get('pb') and r['pb'] > 0 and np.isfinite(PBm[i, tl]):
                rp.append(PBm[i, tl] / r['pb'])
        return np.array(rp)
    best = None
    for field in ('equity', 'equity2'):
        PBm, odd = pb_matrix(F, YI, C, J, cur_t, FX, dates, field)
        rp = check_pb(PBm)
        err_ = np.median(np.abs(np.log(rp))) if len(rp) else np.inf
        log(f"  cours / fonds propres ({'capitaux propres du calcul des comptes' if field == 'equity' else 'totalStockholderEquity'}) : "
            f"{len(rp)} sociétés face au calcul du soir, rapport médian {np.median(rp) if len(rp) else np.nan:.2f}, à ±25 % "
            f"{np.mean(np.abs(rp - 1) <= .25) * 100 if len(rp) else 0:.0f} % ; hors de 0,02 à 200 (écartés) : {odd} semaines")
        if best is None or err_ < best[0]:
            best = (err_, field, PBm)
    _, EQF, PB = best
    del best, PBm
    log(f"  → capitaux propres retenus : {EQF}")
    DS = issuance(F, YI, J, dates, T)
    _, F9d, BADd, YId = value_dates(F, cols, secs, dates, T, 'depot')
    PBd, _ = pb_matrix(F, YId, C, J, cur_t, FX, dates, EQF)
    del YId, J
    RESW, COV = results_weeks(F, dates, T, N)
    del F, C
    gc.collect()

    t0 = time.time()
    G = SE.chain(P, V, dates, cols, secs, liq >= SE.LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    G['mkw'] = mkw = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    mom, trend, s26, mpn, v52, Pw = (G[k] for k in ('mom', 'trend', 's26', 'mpn', 'v52', 'P'))
    q1 = Pw / np.concatenate([np.full((N, 1), np.nan), Pw[:, :-1]], 1)
    jump1y = G['ago_any']((q1 > 2.5) | (q1 < .35), 53)
    log(f"\nUnivers C : {N} sociétés, calcul en {time.time() - t0:.0f} s")
    L = np.log1p(retw)
    Cc = np.concatenate([np.zeros((N, 1)), np.cumsum(L, 1)], 1)
    secs_a = np.array([str(s) for s in secs])

    def fwd(t):
        return np.expm1(Cc[:, t + 27] - Cc[:, t + 1])

    def value_picks(t, pbm=PB, f9m=F9, badm=BAD, cheap=True, fmin=7, n=10, per_sec=2):
        pb = pbm[:, t]
        base = okn[:, t] & np.isfinite(pb) & (pb > 0)
        if base.sum() < 30:
            return []
        cut = np.sort(pb[base])[int(base.sum()) // 3]
        f9 = f9m[:, t]
        pool = base & (f9 >= max(fmin, 0)) & ~badm[:, t] & ~(mom[:, t] < -.4) & ~(v52[:, t] >= .8) & ~jump1y[:, t]
        if cheap:
            pool &= pb <= cut
        idx = np.where(pool)[0]
        idx = idx[np.lexsort((pb[idx], -f9[idx]))]
        out, seen = [], {}
        for i in idx:
            if len(out) >= n:
                break
            s = secs_a[i]
            if seen.get(s, 0) >= per_sec:
                continue
            seen[s] = seen.get(s, 0) + 1
            out.append(int(i))
        return out

    def picks_measure(S):
        """Écart à 6 mois avec la société moyenne (une semaine sur 4), t sur des départs espacés de 26 semaines, part des chutes."""
        res, allx, x26, cr, crm = {}, [], [], [], []
        for el, a, b in ERAS:
            xs = []
            for t in range(a, min(b, T - 28)):
                s = S.get(t) or []
                if len(s) < 3:
                    continue
                fw = fwd(t)
                ok = okn[:, t]
                m = np.nanmean(fw[ok])
                e = np.nanmean(fw[s]) - m
                if (t - t2001) % 26 == 0:
                    x26.append(e)
                if (t - t2001) % 4:
                    continue
                xs.append(e)
                cr.append(np.mean(fw[s] <= -.25))
                crm.append(np.nanmean(fw[ok] <= -.25))
            res[el] = np.mean(xs) * 100 if xs else np.nan
            allx += xs
        x26 = np.array(x26)
        tv = x26.mean() / (x26.std(ddof=1) / np.sqrt(len(x26))) if len(x26) > 2 else np.nan
        return res, np.mean(allx) * 100 if allx else np.nan, tv, np.mean(cr) * 100 if cr else np.nan, np.mean(crm) * 100 if crm else np.nan

    def fmt_measure(lab, S):
        res, mu, tv, cr, crm = picks_measure(S)
        log(f"  {lab:44s} {mu:+5.1f} (t {tv:4.1f}) · " + ' · '.join(f"{el} {v:+5.1f}" for el, v in res.items()) +
            f" ; chutes de 25 % à 6 mois : {cr:.0f} % (société moyenne {crm:.0f} %)")
        return res

    SEL0 = G['SEL']
    pick = RP.make_pick(G)
    same = all(pick(t) == list(SEL0[t]) for t in range(t2001, T - 1, 13))
    log(f"copie de la sélection identique à l'originale : {same}")

    def run(S):
        G['SEL'] = S
        R1 = G['sim30']()
        G['SEL'] = SEL0
        return R1

    def seg(R, a, b):
        return R[a - t2001:b - t2001]
    an = lambda R: (np.prod(1 + R) ** (52 / len(R)) - 1) * 100  # noqa: E731

    def dd_(R):
        e = np.cumprod(1 + R)
        return (e / np.maximum.accumulate(e) - 1).min() * 100

    def line(lab, R):
        log(f"  {lab:44s} {an(R):+5.1f} %/an, pire baisse {dd_(R):.0f} % (" +
            ' · '.join(f"{el} {an(seg(R, a, b)):+.1f} / {dd_(seg(R, a, b)):.0f} %" for el, a, b in ERAS) + ')')

    def cmp(R, ref):
        d = R - ref
        sg = [seg(d, a, b).mean() * 5200 for _, a, b in ERAS]
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        with np.errstate(invalid='ignore', divide='ignore'):
            return sg, blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))

    def cells(sg):
        return ' · '.join(f"{el} {x:+5.1f}" for (el, _, _), x in zip(ERAS, sg))

    Rm = mkw[t2001 + 1:T]
    S_live = {t: pick(t, A=A, mode='live') for t in range(t2001, T - 1)}
    R_live = run(S_live)

    # 1. 💎 Valeur
    log("\n0. Contrôle face au calcul du soir (dernière semaine, sociétés cotées présentes des deux côtés)")
    f9eq, f9n = 0, 0
    for i in range(N):
        r = live_rows.get(ysym[i])
        if r and not dl[i] and r.get('f9') is not None and F9[i, tl] >= 0:
            f9n += 1
            f9eq += abs(int(F9[i, tl]) - int(r['f9'])) <= 1
    rp = check_pb(PB)
    if len(rp):
        log(f"  cours / fonds propres : {len(rp)} sociétés ; rapport médian notre calcul / calcul du soir {np.median(rp):.2f} ; "
            f"à ±25 % : {np.mean(np.abs(rp - 1) <= .25) * 100:.0f} % ; à ±50 % : {np.mean(np.abs(rp - 1) <= .5) * 100:.0f} %")
    if f9n:
        log(f"  F-score : {f9n} sociétés ; à un point près : {f9eq / f9n * 100:.0f} %")
    last_pk = value_picks(tl)
    log(f"  💎 de la dernière semaine ({len(last_pk)}) : {', '.join(ysym[i] for i in last_pk)} ; en commun avec les 10 💎 du calcul "
        f"du soir : {len(set(ysym[i] for i in last_pk) & set(v10))}")

    log("\n1. 💎 Valeur. Couverture : sociétés investissables avec un cours / fonds propres (cotées aujourd'hui | disparues depuis), "
        "candidates 💎 et lignes par semaine (médianes)")
    S_val = {t: value_picks(t) for t in range(t2001, T - 1)}
    for y in (2001, 2004, 2007, 2010, 2013, 2016, 2019, 2022, 2025):
        t = int(np.searchsorted(dates, f'{y}-06-01'))
        inv = okn[:, t]
        cl = []
        for m in (~dl, dl):
            k = inv & m
            cl.append(f"{int((k & np.isfinite(PB[:, t])).sum())}/{int(k.sum())} ({(k & np.isfinite(PB[:, t])).sum() / max(k.sum(), 1) * 100:.0f} %)")
        ws = range(t, min(t + 52, T - 1))
        log(f"  {y} : {cl[0]:18s} | {cl[1]:16s} ; lignes {np.median([len(S_val.get(w, [])) for w in ws]):.0f}")
    log("  Écart à 6 mois avec la société moyenne (points, une semaine sur 4 ; t sur des départs espacés de 26 semaines)")
    fmt_measure('💎 (règle du calcul du soir)', S_val)
    fmt_measure('pour comprendre : tiers le moins cher seul', {t: value_picks(t, fmin=0) for t in range(t2001, T - 1)})
    fmt_measure('pour comprendre : F-score ≥ 7 seul', {t: value_picks(t, cheap=False) for t in range(t2001, T - 1)})
    S_vd = {t: value_picks(t, pbm=PBd, f9m=F9d, badm=BADd) for t in range(t2001, T - 1)}
    fmt_measure('contrôle : comptes connus à la date de dépôt', S_vd)
    del PBd, F9d, BADd
    gc.collect()
    R_val = run(S_val)
    R_vnp = CS.weekly_slots(G, lambda t: S_val.get(t, []), n=10)
    R_v5 = CS.weekly_slots(G, lambda t: S_val.get(t, []), n=10, cost=.005)
    R_vd = run(S_vd)
    log("  Portefeuilles (tranches de 26 semaines, frais 0,3 % par sens) : %/an et pire baisse, par période")
    line('société moyenne (sans frais)', Rm)
    line('💎, protection −30 %', R_val)
    line('💎, sans protection (10 places)', R_vnp)
    line('💎, sans protection, frais 0,5 % par sens', R_v5)
    line('💎, comptes connus à la date de dépôt', R_vd)
    sg, tv = cmp(R_val, Rm)
    v = ('le 💎 TIENT (meilleur que la société moyenne dans chaque période)' if all(x > 0 for x in sg) else
         'LE 💎 EST DÉMENTI : à proposer à François (le retirer)' if all(x < 0 for x in sg) and tv <= -3 else 'pas tranché')
    log(f"  💎 − société moyenne : {cells(sg)} pts/an (t {tv:4.1f}) → {v}")
    sg, tv = cmp(R_vd, Rm)
    log(f"  contrôle, comptes à la date de dépôt − société moyenne : {cells(sg)} pts/an (t {tv:4.1f})")
    R_mix = .7 * R_live + .3 * R_val
    log("  Dosage (le 🎯 : sélection en direct, filtre des comptes compris, protection −30 %)")
    line('🎯 seul', R_live)
    line('70 % 🎯 + 30 % 💎 (dosage conseillé)', R_mix)
    line('50 % 🎯 + 50 % 💎 (pour comprendre)', .5 * R_live + .5 * R_val)
    cor = np.corrcoef(R_live, R_val)[0, 1]
    sg, tv = cmp(R_live, R_mix)
    worse_dd = dd_(R_live) < dd_(R_mix)
    v = ('LE 🎯 SEUL FAIT MIEUX : à proposer à François (dosage)' if all(x > 0 for x in sg) and tv >= 3 and not worse_dd
         else 'dosage 70 / 30 gardé')
    log(f"  🎯 seul − 70 / 30 : {cells(sg)} pts/an (t {tv:4.1f}) ; pire baisse {dd_(R_live):.0f} % contre {dd_(R_mix):.0f} % ; "
        f"corrélation hebdomadaire 🎯 / 💎 {cor:.2f} → {v}")
    del PB
    gc.collect()

    # 2. émissions d'actions
    zone = okn & trend & (s26 >= .14) & (mom >= .3) & (mom <= 2) & ~(mpn < 1 / 3) & ~(v52 >= .8)
    log("\n2. Émissions d'actions. Zone du 🎯 : écart à 6 mois avec la société moyenne selon la variation du nombre d'actions "
        "sur le dernier exercice connu (une semaine sur 4)")
    known = np.isfinite(DS)
    for y in (2004, 2010, 2016, 2022):
        t = int(np.searchsorted(dates, f'{y}-06-01'))
        log(f"  {y} : variation connue pour {int((zone[:, t] & known[:, t]).sum())} des {int(zone[:, t].sum())} sociétés de la zone")

    def era_mean(mask):
        out, allx = {}, []
        for el, a, b in ERAS:
            xs = []
            for t in range(a, min(b, T - 28), 4):
                s = zone[:, t] & mask[:, t]
                if s.sum() >= 3:
                    fw = fwd(t)
                    xs.append(np.nanmean(fw[s]) - np.nanmean(fw[okn[:, t]]))
            out[el] = np.mean(xs) * 100 if xs else np.nan
            allx += xs
        x = np.array(allx)
        return out, x.mean() * 100 if len(x) else np.nan, len(x)
    with np.errstate(invalid='ignore'):
        groups = (('+10 % ou plus', DS >= .10), ('+2 à +10 %', (DS >= .02) & (DS < .10)), ('−2 à +2 %', np.abs(DS) < .02),
                  ('−2 % ou moins (rachats)', DS <= -.02), ('inconnue', ~known))
    for lab, m in groups:
        o, mu, n = era_mean(m)
        log(f"  {lab:28s} {mu:+5.1f} · " + ' · '.join(f"{el} {v:+5.1f}" for el, v in o.items()))
    big = np.nan_to_num(DS) >= .10
    share = np.mean([np.mean(big[s, t]) for t, s in S_live.items() if len(s)]) * 100
    G2 = dict(G, okn=okn & ~big)
    pick2 = RP.make_pick(G2)
    R2 = run({t: pick2(t, A=A, mode='live') for t in range(t2001, T - 1)})
    log(f"  lignes de la sélection en direct à +10 % d'actions ou plus : {share:.1f} %")
    line('sélection en direct', R_live)
    line('sans les sociétés à +10 % d\'actions ou plus', R2)
    sg, tv = cmp(R2, R_live)
    v = ' → BAT LA SÉLECTION EN DIRECT : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejetée'
    log(f"  sans les émetteurs − en direct : {cells(sg)} pts/an (t {tv:4.1f}){v}")
    del DS, big, G2
    gc.collect()

    # 3. 📣 bond avec ou sans résultats
    log("\n3. 📣 bond avec ou sans résultats. Sociétés investissables suivies (une publication connue à moins de 200 jours)")
    cov_ok = {}
    for el, a, b in ERAS:
        ts = range(a, b, 13)
        cov_ok[el] = np.mean([(okn[:, t] & COV[:, t]).sum() / max(okn[:, t].sum(), 1) for t in ts]) * 100
    for y in (2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023, 2026):
        t = min(int(np.searchsorted(dates, f'{y}-06-01')), T - 1)
        inv = okn[:, t]
        cl = [f"{int((inv & m & COV[:, t]).sum())}/{int((inv & m).sum())}" for m in (~dl, dl)]
        log(f"  {y} : {cl[0]:9s} | {cl[1]}")
    log("  moyenne par période : " + ' · '.join(f"{el} {v:.0f} %" for el, v in cov_ok.items()))
    B = G['R0'] | G['R1']
    cond = trend & okn & (mpn >= 1 / 3) & ~(v52 >= .8)
    first = B & ~G['ago_any'](np.concatenate([np.zeros((N, 1), bool), B[:, :-1]], 1), 8)  # premier bond en 8 semaines
    EV = first & cond & COV
    for lab, m in (('bond la semaine des résultats', EV & RESW), ('bond sans résultats', EV & ~RESW)):
        out, allx, blk = {}, [], {}
        for el, a, b in ERAS:
            xs = []
            for t in range(a, min(b, T - 28)):
                s = np.where(m[:, t])[0]
                if not len(s):
                    continue
                fw = fwd(t)
                e = fw[s] - np.nanmean(fw[okn[:, t]])
                e = e[np.isfinite(e)]
                xs += list(e)
                blk.setdefault((t - t2001) // 26, []).extend(e)
            out[el] = (np.mean(xs) * 100 if xs else np.nan, len(xs))
            allx += xs
        bm = np.array([np.mean(v) for v in blk.values() if len(v)])
        tv = bm.mean() / (bm.std(ddof=1) / np.sqrt(len(bm))) if len(bm) > 2 else np.nan
        log(f"  {lab:30s} {np.mean(allx) * 100 if allx else np.nan:+5.1f} (t {tv:4.1f}, {len(allx)} bonds) · " +
            ' · '.join(f"{el} {v:+5.1f} ({n})" for el, (v, n) in out.items()))
    aa = G['ago_any']
    dem_res = aa(B & RESW, 4) & cond
    dem_nores = aa(B & ~RESW & COV, 4) & cond
    pick_r = RP.make_pick(dict(G, dem=dem_res))
    R3a = run({t: pick_r(t, A=A, mode='live') for t in range(t2001, T - 1)})
    pick_n = RP.make_pick(dict(G, dem=dem_nores))
    R3b = run({t: pick_n(t, A=A, mode='live') for t in range(t2001, T - 1)})
    line('sélection en direct', R_live)
    line('📣 réservé aux bonds de résultats', R3a)
    line('📣 réservé aux bonds sans résultats', R3b)
    enough = all(v >= 50 for v in cov_ok.values())
    for lab, R in (('bonds de résultats', R3a), ('bonds sans résultats', R3b)):
        sg, tv = cmp(R, R_live)
        v = (' → BAT LE 📣 EN DIRECT : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 and enough else
             ' → rejetée' if enough else ' → dates trop rares sur une période : pas testable sur les 3 périodes')
        log(f"  {lab} − en direct : {cells(sg)} pts/an (t {tv:4.1f}){v}")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
