"""Facteurs des comptes restés sans test, sur 25 ans sans biais du survivant (28/11/2026, François : « Faire ce qui est pertinent
et vérifier que toutes les idées/méthodes/stratégies ont été testées »).

Inventaire du 28/11/2026 : des experts de l'ancien Comité IA (OAD Bourse), seul Piotroski était testé (💎 et « comptes solides ») ;
le nombre de Graham, la formule magique de Greenblatt et le score d'Altman (seulement dans la règle du 💎) ne l'étaient pas, ni le
score de Beneish que la page affiche en point d'alerte (🔍), ni la zone de détresse d'Altman qu'elle affiche (🧯) pour le 🎯, ni les
trois anomalies comptables les plus étudiées : rentabilité brute (Novy-Marx, 2013), croissance de l'actif (Cooper, Gulen et Schill,
2008), régularisations (Sloan, 1996). Univers C de survivant_eodhd.py (12 bourses de l'EEE, sociétés retirées de la cote comprises,
liquidité connue à la date, 2001-2026), comptes annuels EODHD lus 120 jours après la clôture par le calcul du soir
(ES.accountsAnalysis, facteurs_dates_eodhd.js), capitalisation à la date (actions du dernier bilan lu, divisions corrigées, comme
survivant_valeur.py).

Facteurs, exercice lu à la date (et le précédent s'il le suit de 300 à 430 jours) :
- zone d'Altman Z'' et profil Beneish (M > −1,78) tels que la page les affiche ;
- rentabilité brute : marge brute / actif total ; croissance de l'actif : actif / actif précédent − 1 ; régularisations : (résultat
  net − flux d'exploitation) / actif moyen ;
- formule magique (Greenblatt, 2005) : rendement EBIT / valeur d'entreprise (capitalisation + dette − trésorerie) et rentabilité du
  capital (EBIT / (besoin en fonds de roulement hors trésorerie + immobilisations corporelles)), rangs additionnés ;
- nombre de Graham : capitalisation / √(22,5 × résultat net × fonds propres) (< 1 : cours sous le nombre de Graham).
Banques, assurances, foncières et services aux collectivités hors formule magique et rentabilité brute (comme Greenblatt).

1. Zone du 🎯 : écart à 6 mois avec la société moyenne, par groupe (tiers calculés chaque semaine parmi les sociétés
   investissables), une semaine sur 4, par période.
2. Filtres de la sélection en direct (filtre des comptes compris, protection −30 %) : sans la zone de détresse d'Altman ; sans le
   profil Beneish ; sans le tiers le moins rentable ; sans le tiers à la plus forte croissance de l'actif ; sans le tiers aux plus
   fortes régularisations. Règle fixée avant : un filtre n'est proposé à François que s'il bat la sélection en direct dans chacune
   des 3 périodes avec t ≥ 3.
3. Stratégies à part, comme le 💎 (10 lignes, 2 par secteur, sociétés liquides, ni ⚡ ni saut de cours dans l'année, tranches de
   26 semaines, frais 0,3 % par sens, protection −30 %) : formule magique ; nombre de Graham (cours sous le nombre, les moins chers
   d'abord) ; valeur rentable (Novy-Marx : rang de la rentabilité brute + rang du cours / fonds propres). Règle fixée avant : une
   stratégie tient si elle bat la société moyenne dans chaque période ; elle ne remplacerait le 💎 (proposition) que si elle le bat
   dans chaque période avec t ≥ 3.
4. Cœur indiciel (conseil d'octobre 2026, « indice + satellite ») : 70 % ou 50 % dans la société moyenne (équipondérée, dividendes
   compris, sans frais), le reste dans la sélection en direct : rendement et pire baisse.
Penman (bénéfice résiduel) n'est pas testable : il demande les prévisions des analystes, sans historique.
Lancé par « Recherche (à la demande) » (script survivant_facteurs.py), environ 35 minutes, environ 27 000 appels EODHD (10 par
société pour les comptes). Cours et comptes restent en mémoire (fichiers temporaires pour le calcul en JavaScript, effacés
aussitôt) ; la clé n'est jamais affichée.
"""
import gc
import json
import os
import subprocess
import tempfile
import time
from datetime import date

import numpy as np

import revue_pistes as RP
import survivant_eodhd as SE
import survivant_valeur as SV

log = SE.log
XSECT = ('financial', 'bank', 'insurance', 'real estate', 'reit', 'utilit', 'banque', 'assurance', 'immobili', 'fonci',
         'services aux collectivit')
ALTZ = {'safe': 1, 'grey': 2, 'distress': 3}


def dates_plus(F, cols, secs, dates, T):
    """Comme survivant_valeur.value_dates (mode lag120), plus la zone d'Altman et le profil Beneish de la page."""
    inp = {cols[i]: {'years': f['years'], 'currency': f.get('currency'), 'industry': f.get('industry') or '',
                     'sector': f"{secs[i] if not str(secs[i]).startswith('?') else ''} {f.get('sector') or ''}".strip()}
           for i, f in F.items() if f['years']}
    fd, pin = tempfile.mkstemp(suffix='.json', dir='.')
    os.close(fd)
    pout = pin + '.out'
    try:
        with open(pin, 'w') as fh:
            json.dump(inp, fh)
        r = subprocess.run(['node', 'facteurs_dates_eodhd.js', pin, pout], capture_output=True, text=True, timeout=2400)
        log('  ' + (r.stdout.strip() or r.stderr.strip()[-300:]))
        if r.returncode:
            raise RuntimeError('facteurs_dates_eodhd.js a échoué')
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
    ALT = np.zeros((N, T), np.int8)
    BEN = np.full((N, T), -1, np.int8)
    dd = np.array(dates)
    ix = {c: i for i, c in enumerate(cols)}
    for c, pts in Dv.items():
        i = ix[c]
        yd = {y['date']: k for k, y in enumerate(F[i]['years'])}
        for k, (d, key, f9, loss, alt, _fin, ld, ben) in enumerate(pts):
            a = int(np.searchsorted(dd, d, side='left'))
            b = int(np.searchsorted(dd, pts[k + 1][0], side='left')) if k + 1 < len(pts) else T
            if a >= b:
                continue
            A[i, a:b] = RP.CODES.get(key, 0)
            F9[i, a:b] = f9 if f9 is not None else -1
            BAD[i, a:b] = bool(loss) or alt == 'distress' or key == 'bad'
            YI[i, a:b] = yd.get(ld, -1)
            ALT[i, a:b] = ALTZ.get(alt, 0)
            BEN[i, a:b] = ben
    return A, F9, BAD, YI, ALT, BEN


def gap_days(y1, y0):
    try:
        return (date.fromisoformat(y1['date']) - date.fromisoformat(y0['date'])).days
    except (KeyError, TypeError, ValueError):
        return None


def factor_matrices(F, YI, C, SH, cur_t, FX, secs, N, T):
    """Facteurs de chaque semaine d'après l'exercice lu (et le précédent) ; valeurs hors des bornes plausibles : inconnues."""
    GPA, AGR, ACC, ROC, EY, GR = (np.full((N, T), np.nan, np.float32) for _ in range(6))
    XF = np.zeros(N, bool)
    for i, f in F.items():
        sect = f"{secs[i]} {f.get('sector') or ''} {f.get('industry') or ''}".lower()
        XF[i] = any(w in sect for w in XSECT)
        ys = f['years']
        yi = YI[i]
        qc = cur_t[i]
        rc = (f.get('currency') or '').upper() or qc
        k = FX[qc] / FX[rc] if qc in FX and rc in FX else None
        for j in np.unique(yi[yi >= 0]):
            j = int(j)
            y = ys[j]
            m = yi == j
            p = ys[j - 1] if j >= 1 else None
            if p is not None and not 300 <= (gap_days(y, p) or 0) <= 430:
                p = None
            ta, gp, ni, cfo = (y.get(x) for x in ('totalAssets', 'grossProfit', 'netIncome', 'cfo'))
            pta = p.get('totalAssets') if p else None
            if ta and ta > 0 and gp is not None and -1 <= gp / ta <= 3:
                GPA[i, m] = gp / ta
            if ta and ta > 0 and pta and pta > 0 and -.9 <= ta / pta - 1 <= 10:
                AGR[i, m] = ta / pta - 1
            if ta and ta > 0 and pta and pta > 0 and ni is not None and cfo is not None:
                acc = (ni - cfo) / ((ta + pta) / 2)
                if -1 <= acc <= 1:
                    ACC[i, m] = acc
            ebit = y.get('ebit') if y.get('ebit') is not None else y.get('operatingIncome')
            ca, cl, cash, debt, ltd, ppe = (y.get(x) for x in ('currentAssets', 'currentLiabilities', 'cash', 'totalDebt',
                                                                'longTermDebt', 'ppe'))
            if ebit is not None and ca is not None and cl is not None and ppe is not None:
                std = debt - ltd if debt is not None and ltd is not None and debt >= ltd else 0.0
                cap = max(ca - (cash or 0.0) - (cl - std), 0.0) + ppe
                if cap > 0 and -5 <= ebit / cap <= 5:
                    ROC[i, m] = ebit / cap
            if k is None:
                continue
            kk = k[m]
            with np.errstate(invalid='ignore', divide='ignore'):
                mc = C[i, m].astype(float) * SH[i, m]
                if ebit is not None and debt is not None and cash is not None:
                    ev = mc + (debt - cash) * kk
                    ey = np.where(ev > 0, ebit * kk / ev, np.nan)
                    EY[i, m] = np.where(np.abs(ey) <= 1, ey, np.nan)
                E = SV.equity_of(y)
                if ni is not None and ni > 0 and E is not None and E > 0:
                    gr = mc / (kk * np.sqrt(22.5 * ni * E))
                    GR[i, m] = np.where((gr > .01) & (gr < 100), gr, np.nan)
    return GPA, AGR, ACC, ROC, EY, GR, XF


def terciles(X, pool, T):
    """Tiers chaque semaine parmi pool & X connu : 0 bas, 1 milieu, 2 haut, −1 inconnu."""
    Q = np.full(X.shape, -1, np.int8)
    for t in range(T):
        k = pool[:, t] & np.isfinite(X[:, t])
        if k.sum() < 30:
            continue
        a, b = np.nanpercentile(X[k, t], [100 / 3, 200 / 3])
        x = X[:, t]
        Q[k, t] = np.where(x[k] <= a, 0, np.where(x[k] <= b, 1, 2))
    return Q


def main():
    u, err = SE.get('user')
    used = int((u or {}).get('apiRequests') or 0)
    if str((u or {}).get('apiRequestsDate') or '') != time.strftime('%Y-%m-%d', time.gmtime()):
        used = 0  # compteur d'un autre jour : il repart à zéro au premier appel compté
    if used > 70000:  # ce test en prend environ 27 000 (10 par société pour les comptes), limite 100 000 par jour
        log(f"{used} appels EODHD déjà utilisés aujourd'hui : relancer après la remise à zéro du compteur")
        return
    D = SE.prepare()
    if D is None:
        return
    P, C, V, liq, cols, secs, dates, T, t2001, ERAS, t00, dl, rows = (D[k] for k in (
        'P', 'C', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00', 'dl', 'rows'))
    N = len(cols)
    F = SV.fundamentals(cols)
    J, nj, nr = SV.split_jumps(P, C)
    A, F9, BAD, YI, ALT, BEN = dates_plus(F, cols, secs, dates, T)
    jumps = {md: SV.mcap_jumps(C, SV.shares_matrix(F, YI, J, C, dates, T, md)[0]) for md in ('now', 'pub')}
    default = 'now' if jumps['now'] <= jumps['pub'] else 'pub'
    SH, choice = SV.shares_matrix(F, YI, J, C, dates, T, 'auto', default)
    log(f"  divisions repérées : {nr} ; capitalisation qui double ou se divise par deux d'une semaine à l'autre : "
        f"{SV.mcap_jumps(C, SH) * 100:.2f} % des semaines")
    cur_t = [r['cur'] for r in rows]
    FX = SV.fx_table({c for c in cur_t} | {(f.get('currency') or '').upper() for f in F.values()}, dates)
    PB, odd = SV.pb_matrix(F, YI, C, SH, cur_t, FX)
    GPA, AGR, ACC, ROC, EY, GR, XF = factor_matrices(F, YI, C, SH, cur_t, FX, secs, N, T)
    del SH, choice, J, F, C
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
    L = np.log1p(retw)
    Cc = np.concatenate([np.zeros((N, 1)), np.cumsum(L, 1)], 1)
    secs_a = np.array([str(s) for s in secs])
    zone = okn & trend & (s26 >= .14) & (mom >= .3) & (mom <= 2) & ~(mpn < 1 / 3) & ~(v52 >= .8)
    log(f"\nUnivers C : {N} sociétés, calcul en {time.time() - t0:.0f} s")

    # 0. couverture des facteurs
    log("\n0. Couverture : part des sociétés investissables dont le facteur est connu (cotées aujourd'hui et disparues depuis)")
    FAC = (('zone d\'Altman', ALT > 0), ('Beneish', BEN >= 0), ('rentabilité brute', np.isfinite(GPA)),
           ('croissance de l\'actif', np.isfinite(AGR)), ('régularisations', np.isfinite(ACC)),
           ('formule magique', np.isfinite(EY) & np.isfinite(ROC)), ('nombre de Graham', np.isfinite(GR)))
    for y in (2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023, 2026):
        t = min(int(np.searchsorted(dates, f'{y}-06-01')), T - 2)
        inv = okn[:, t]
        log(f"  {y} : " + ' · '.join(f"{lab} {(inv & m[:, t]).sum() / max(inv.sum(), 1) * 100:.0f} %" for lab, m in FAC))
    tl = T - 2
    inv = okn[:, tl]
    log(f"  dernière semaine, sociétés investissables : zone de détresse d'Altman {int((inv & (ALT[:, tl] == 3)).sum())}, grise "
        f"{int((inv & (ALT[:, tl] == 2)).sum())}, sûre {int((inv & (ALT[:, tl] == 1)).sum())} ; profil Beneish {int((inv & (BEN[:, tl] == 1)).sum())} "
        f"sur {int((inv & (BEN[:, tl] >= 0)).sum())} ; cours sous le nombre de Graham {int((inv & (GR[:, tl] < 1)).sum())} sur "
        f"{int((inv & np.isfinite(GR[:, tl])).sum())} ; médianes : rentabilité brute {np.nanmedian(GPA[inv, tl]):.2f}, croissance de "
        f"l'actif {np.nanmedian(AGR[inv, tl]) * 100:+.0f} %, régularisations {np.nanmedian(ACC[inv, tl]) * 100:+.1f} % de l'actif, "
        f"rendement EBIT / VE {np.nanmedian(EY[inv, tl]) * 100:.1f} %, rentabilité du capital {np.nanmedian(ROC[inv, tl]) * 100:.0f} %")

    def fwd(t):
        return np.expm1(Cc[:, t + 27] - Cc[:, t + 1])

    def era_mean(mask):
        out, allx, blk = {}, [], {}
        for el, a, b in ERAS:
            xs = []
            for t in range(a, min(b, T - 28), 4):
                s = zone[:, t] & mask[:, t]
                if s.sum() >= 3:
                    fw = fwd(t)
                    e = np.nanmean(fw[s]) - np.nanmean(fw[okn[:, t]])
                    xs.append(e)
                    blk.setdefault((t - t2001) // 26, []).append(e)
            out[el] = np.mean(xs) * 100 if xs else np.nan
            allx += xs
        bm = np.array([np.mean(v) for v in blk.values()])
        tv = bm.mean() / (bm.std(ddof=1) / np.sqrt(len(bm))) if len(bm) > 2 else np.nan
        return out, np.mean(allx) * 100 if allx else np.nan, tv

    def groups_line(lab, mask):
        o, mu, tv = era_mean(mask)
        log(f"  {lab:40s} {mu:+5.1f} (t {tv:4.1f}) · " + ' · '.join(f"{el} {v:+5.1f}" for el, v in o.items()))

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
        log(f"  {lab:46s} {an(R):+5.1f} %/an, pire baisse {dd_(R):.0f} % (" +
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

    # 1. zone du 🎯 par groupe
    log("\n1. Zone du 🎯 : écart à 6 mois avec la société moyenne selon le facteur (points ; une semaine sur 4 ; t sur des blocs de "
        "26 semaines ; tiers calculés chaque semaine parmi les sociétés investissables)")
    groups_line('toute la zone', np.ones_like(zone))
    for lab, v in (('Altman : zone sûre', 1), ('Altman : zone grise', 2), ('Altman : zone de détresse (🧯 de la page)', 3),
                   ('Altman : inconnu', 0)):
        groups_line(lab, ALT == v)
    for lab, v in (('Beneish : profil signalé (🔍 de la page)', 1), ('Beneish : non signalé', 0), ('Beneish : inconnu', -1)):
        groups_line(lab, BEN == v)
    pool_x = okn & ~XF[:, None]
    TQ = {}
    for nm, X, pool in (('rentabilité brute', GPA, pool_x), ('croissance de l\'actif', AGR, okn), ('régularisations', ACC, okn)):
        Q = terciles(X, pool, T)
        TQ[nm] = Q
        for k, lab in ((0, 'tiers bas'), (1, 'tiers du milieu'), (2, 'tiers haut')):
            groups_line(f"{nm} : {lab}", Q == k)
    # formule magique : rangs du rendement EBIT / VE et de la rentabilité du capital, additionnés
    MF = np.full((N, T), np.nan, np.float32)
    for t in range(T):
        k = pool_x[:, t] & np.isfinite(EY[:, t]) & np.isfinite(ROC[:, t])
        if k.sum() < 30:
            continue
        idx = np.where(k)[0]
        r1 = (-EY[idx, t]).argsort().argsort()
        r2 = (-ROC[idx, t]).argsort().argsort()
        MF[idx, t] = (r1 + r2) / (2 * (len(idx) - 1))  # 0 : meilleure, 1 : moins bonne
    QM = terciles(-MF, pool_x, T)
    for k, lab in ((2, 'tiers le mieux classé'), (1, 'tiers du milieu'), (0, 'tiers le moins bien classé')):
        groups_line(f"formule magique : {lab}", QM == k)
    with np.errstate(invalid='ignore'):
        groups_line('Graham : cours sous le nombre de Graham', GR < 1)
        groups_line('Graham : cours au-dessus', GR >= 1)
    groups_line('Graham : sans nombre (perte ou fonds propres ≤ 0)', ~np.isfinite(GR))

    # 2. filtres de la sélection en direct
    log("\n2. Sélection en direct (4 🎯 + 1 📣, filtre des comptes, protection −30 %) et filtres des facteurs")
    line('société moyenne (sans frais)', Rm)
    line('sélection en direct', R_live)
    FILT = (('sans la zone de détresse d\'Altman', ALT == 3), ('sans le profil Beneish', BEN == 1),
            ('sans le tiers le moins rentable', TQ['rentabilité brute'] == 0),
            ('sans le tiers à la plus forte croissance de l\'actif', TQ['croissance de l\'actif'] == 2),
            ('sans le tiers aux plus fortes régularisations', TQ['régularisations'] == 2))
    for lab, mask in FILT:
        share = np.mean([np.mean(mask[s, t]) for t, s in S_live.items() if len(s)]) * 100
        G2 = dict(G, okn=okn & ~mask)
        pk = RP.make_pick(G2)
        R = run({t: pk(t, A=A, mode='live') for t in range(t2001, T - 1)})
        line(lab, R)
        sg, tv = cmp(R, R_live)
        v = ' → BAT LA SÉLECTION EN DIRECT : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejeté'
        log(f"    − en direct : {cells(sg)} pts/an (t {tv:4.1f}) ; lignes concernées dans la sélection en direct {share:.1f} %{v}")
        del G2, pk
    gc.collect()

    # 3. stratégies à part
    def top(t, pool, order, n=10, per_sec=2):
        idx = np.where(pool)[0]
        idx = idx[np.argsort(order[idx], kind='stable')]
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

    def base_pool(t):
        return okn[:, t] & ~(v52[:, t] >= .8) & ~jump1y[:, t]

    def magic(t):
        return top(t, base_pool(t) & np.isfinite(MF[:, t]) & (EY[:, t] > 0) & (ROC[:, t] > 0), MF[:, t])

    def graham(t):
        with np.errstate(invalid='ignore'):
            return top(t, base_pool(t) & (GR[:, t] < 1), GR[:, t])

    def prof_value(t):
        k = base_pool(t) & ~XF & np.isfinite(GPA[:, t]) & np.isfinite(PB[:, t]) & (PB[:, t] > 0)
        if k.sum() < 30:
            return []
        idx = np.where(k)[0]
        sc = np.full(N, np.inf)
        sc[idx] = (-GPA[idx, t]).argsort().argsort() + PB[idx, t].argsort().argsort()
        return top(t, k, sc)

    def value_picks(t, n=10, per_sec=2):
        """💎 du calcul du soir (copie de survivant_valeur.value_picks)."""
        pb = PB[:, t]
        base = okn[:, t] & np.isfinite(pb) & (pb > 0)
        if base.sum() < 30:
            return []
        cut = np.sort(pb[base])[int(base.sum()) // 3]
        f9 = F9[:, t]
        pool = base & (f9 >= 7) & ~BAD[:, t] & ~(mom[:, t] < -.4) & ~(v52[:, t] >= .8) & ~jump1y[:, t] & (pb <= cut)
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
        res, allx, x26, cr = {}, [], [], []
        for el, a, b in ERAS:
            xs = []
            for t in range(a, min(b, T - 28)):
                s = S.get(t) or []
                if len(s) < 3:
                    continue
                fw = fwd(t)
                e = np.nanmean(fw[s]) - np.nanmean(fw[okn[:, t]])
                if (t - t2001) % 26 == 0:
                    x26.append(e)
                if (t - t2001) % 4:
                    continue
                xs.append(e)
                cr.append(np.mean(fw[s] <= -.25))
            res[el] = np.mean(xs) * 100 if xs else np.nan
            allx += xs
        x26 = np.array(x26)
        tv = x26.mean() / (x26.std(ddof=1) / np.sqrt(len(x26))) if len(x26) > 2 else np.nan
        return res, np.mean(allx) * 100 if allx else np.nan, tv, np.mean(cr) * 100 if cr else np.nan

    log("\n3. Stratégies à part (10 lignes, 2 par secteur). Écart à 6 mois des choix avec la société moyenne (une semaine sur 4 ; "
        "t sur des départs espacés de 26 semaines), puis portefeuilles (tranches de 26 semaines, frais 0,3 % par sens, protection −30 %)")
    STRAT = (('💎 (règle du calcul du soir, référence)', value_picks), ('formule magique (Greenblatt)', magic),
             ('nombre de Graham', graham), ('valeur rentable (Novy-Marx)', prof_value))
    SS = {}
    for lab, fn in STRAT:
        S = {t: fn(t) for t in range(t2001, T - 1)}
        SS[lab] = S
        res, mu, tv, cr = picks_measure(S)
        nl = np.median([len(S[t]) for t in range(t2001, T - 1)])
        log(f"  {lab:44s} {mu:+5.1f} (t {tv:4.1f}) · " + ' · '.join(f"{el} {v:+5.1f}" for el, v in res.items()) +
            f" ; chutes de 25 % à 6 mois : {cr:.0f} % ; lignes par semaine (médiane) {nl:.0f}")
    R_val = run(SS[STRAT[0][0]])
    line(STRAT[0][0], R_val)
    for lab, _ in STRAT[1:]:
        R = run(SS[lab])
        line(lab, R)
        sg, tv = cmp(R, Rm)
        v1 = 'tient (mieux que la société moyenne dans chaque période)' if all(x > 0 for x in sg) else 'ne tient pas'
        sg2, tv2 = cmp(R, R_val)
        v2 = 'BAT LE 💎 : à proposer à François' if all(x > 0 for x in sg2) and tv2 >= 3 else 'ne remplace pas le 💎'
        log(f"    − société moyenne : {cells(sg)} pts/an (t {tv:4.1f}) → {v1} ; − 💎 : {cells(sg2)} (t {tv2:4.1f}) → {v2}")
        cor = np.corrcoef(R, R_live)[0, 1]
        log(f"    corrélation hebdomadaire avec la sélection en direct {cor:.2f}")

    # 4. cœur indiciel
    log("\n4. Cœur indiciel (société moyenne équipondérée, dividendes compris, sans frais) et sélection en direct")
    line('sélection en direct seule', R_live)
    line('30 % sélection + 70 % société moyenne', .3 * R_live + .7 * Rm)
    line('50 % sélection + 50 % société moyenne', .5 * R_live + .5 * Rm)
    line('70 % sélection + 30 % 💎 (dosage de la page)', .7 * R_live + .3 * R_val)
    line('société moyenne seule', Rm)
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
