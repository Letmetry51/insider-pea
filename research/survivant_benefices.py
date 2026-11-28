"""Bénéfices et cassures restés sans test, sur 25 ans sans biais du survivant (suite de l'inventaire du 28/11/2026, François :
« Faire ce qui est pertinent et vérifier que toutes les idées/méthodes/stratégies ont été testées »).

Univers C de survivant_eodhd.py, comptes annuels EODHD lus 120 jours après la clôture (comme survivant_facteurs.py), publications
trimestrielles ou semestrielles d'EODHD (Earnings::History : date de publication, bénéfice par action publié et attendu).

1. Dérive après résultats (Bernard et Thomas, 1989), testée jusqu'ici sur Yahoo 2020-2026 seulement : surprise = (bénéfice par
   action publié − attendu) / |attendu|, la dernière publiée depuis 13 semaines au plus. Zone du 🎯 par tiers de surprise ;
   sélection en direct sans le tiers des plus mauvaises surprises.
2. CANSLIM d'O'Neil, lettres C et A : C = bénéfice par action de la dernière période publiée en hausse d'au moins 25 % sur la même
   période un an plus tôt (les deux positifs) ; A = résultat net annuel en hausse chaque année sur 3 exercices et d'au moins 25 % par
   an (résultat net plutôt que par action : les nombres d'actions d'EODHD sont recalculés après coup). Zone du 🎯 avec ou sans ;
   sélection en direct sans les sociétés dont C et A, quand ils sont connus, sont faux.
3. PEG de Lynch : (capitalisation / résultat net) / croissance annuelle du résultat net sur 3 exercices en %, croissance de 10 à
   50 % par an. Zone du 🎯 selon PEG < 1 ; stratégie à part comme le 💎 (10 lignes, 2 par secteur, PEG le plus bas, sous 1).
4. Cassure en points et figures (screener de François, novembre 2026 : case 2 %, retournement de 3 cases, double ou triple sommet
   cassé depuis 15 séances au plus sur 1,2 fois le volume moyen, colonne de X, cours au-dessus de la cassure, RSI < 75, au-dessus de
   la moyenne 50, moyenne 20 au-dessus de la moyenne 50 ; cours journaliers EODHD) mise en priorité dans l'ordre de la sélection,
   juste après 🔊 et 📣 : piste du 28/11/2026 (+3,3 points à 6 mois dans la zone du 🎯 contre +1,9 pour la zone, mieux dans chaque
   période ; survivant_restes.py).
Règles fixées avant : un filtre (1, 2) n'est proposé à François que s'il bat la sélection en direct dans chacune des 3 périodes avec
t ≥ 3 ; la priorité (4), que si elle bat la sélection de base dans chacune des 3 périodes avec t ≥ 3 ; le PEG ne remplacerait le 💎
que s'il le bat dans chaque période avec t ≥ 3.
Lancé par « Recherche (à la demande) » (script survivant_benefices.py), environ 25 minutes, environ 29 000 appels EODHD (10 par
société pour les comptes, puis cours journaliers). Cours et comptes en mémoire seulement (fichiers temporaires du calcul en JavaScript
effacés aussitôt) ; la clé n'est jamais affichée.
"""
import concurrent.futures as cf
import gc
import time
from datetime import date

import numpy as np

import revue_pistes as RP
import survivant_comptes as SC
import survivant_eodhd as SE
import survivant_facteurs as SF
import survivant_restes as SR
import survivant_valeur as SV

log = SE.log


def earnings_hist(x):
    """Publications passées : (fin de période, date de publication, bénéfice par action publié, attendu)."""
    h = x.get('Earnings::History')
    if h is None and isinstance(x.get('Earnings'), dict):
        h = x['Earnings'].get('History')
    out, today = [], time.strftime('%Y-%m-%d')
    if isinstance(h, dict):
        for k, e in h.items():
            if not isinstance(e, dict):
                continue
            d, p = str(e.get('reportDate') or '')[:10], str(e.get('date') or k or '')[:10]
            if len(d) != 10 or len(p) != 10 or d[:2] not in ('19', '20') or d > today:
                continue
            try:
                gap = (date.fromisoformat(d) - date.fromisoformat(p)).days
            except ValueError:
                continue
            if 5 <= gap <= 200:
                out.append((p, d, SC.num(e.get('epsActual')), SC.num(e.get('epsEstimate'))))
    return sorted(out)


def fundamentals_e(cols):
    out, errs = {}, {}

    def one(i):
        x, err = SE.get('fundamentals/' + cols[i], filter=SV.FLT)
        return i, x, err
    t0 = time.time()
    with cf.ThreadPoolExecutor(8) as pool:
        for n, (i, x, err) in enumerate(pool.map(one, range(len(cols)))):
            if err or not isinstance(x, dict):
                errs[err or 'vide'] = errs.get(err or 'vide', 0) + 1
                continue
            years, cur = SV.to_years(x)
            eh = earnings_hist(x)
            if years or eh:
                out[i] = {'years': years, 'currency': cur, 'sector': x.get('General::Sector') or '',
                          'industry': x.get('General::Industry') or '', 'eh': eh}
            if n % 500 == 499:
                log(f"  comptes : {n + 1} sociétés en {time.time() - t0:.0f} s")
    ne = sum(len(v['eh']) for v in out.values())
    na = sum(1 for v in out.values() for e in v['eh'] if e[2] is not None)
    nb = sum(1 for v in out.values() for e in v['eh'] if e[2] is not None and e[3] is not None)
    log(f"  comptes : {sum(1 for v in out.values() if v['years'])} sociétés sur {len(cols)} avec des exercices ; publications {ne}, "
        f"avec bénéfice par action {na}, avec aussi l'attendu {nb} ; en {time.time() - t0:.0f} s ; erreurs {errs or 'aucune'}")
    return out


def earnings_weeks(F, dates, T, N):
    """Dernière publication connue depuis 13 semaines au plus : surprise et croissance sur un an de la même période."""
    SURP = np.full((N, T), np.nan, np.float32)
    CQG = np.full((N, T), np.nan, np.float32)
    dd = np.array(dates)
    for i, f in F.items():
        eh = sorted(f.get('eh') or [], key=lambda e: e[1])
        if not eh:
            continue
        W = np.searchsorted(dd, [e[1] for e in eh], side='left')
        act = {}
        for p, _, a, _ in eh:
            if a is not None:
                q = date.fromisoformat(p)
                act[(q.year, q.month)] = a
        nxt = T
        ends = [T] * len(eh)
        for k in range(len(eh) - 1, -1, -1):  # prochaine publication d'une autre semaine
            ends[k] = nxt
            if k and W[k - 1] < W[k]:
                nxt = int(W[k])
        for k, (p, d, a, e) in enumerate(eh):
            w = int(W[k])
            if w >= T:
                continue
            b = min(w + 13, ends[k], T)
            if b <= w:
                continue
            if a is not None and e is not None and abs(e) >= .01:
                SURP[i, w:b] = float(np.clip((a - e) / abs(e), -3, 3))
            q = date.fromisoformat(p)
            a0 = next((act[key] for key in ((q.year - 1, q.month), (q.year - 1, q.month - 1), (q.year - 1, q.month + 1)) if key in act), None)
            if a is not None and a > 0 and a0 is not None and a0 > 0:
                CQG[i, w:b] = float(np.clip(a / a0 - 1, -1, 20))
    return SURP, CQG


def annual_growth(F, YI, C, SH, cur_t, FX, N, T):
    """Croissance annuelle du résultat net sur 3 exercices (chaque année en hausse : A d'O'Neil) et PEG de Lynch."""
    G3 = np.full((N, T), np.nan, np.float32)
    UP3 = np.zeros((N, T), bool)
    KN = np.zeros((N, T), bool)
    PEG = np.full((N, T), np.nan, np.float32)
    for i, f in F.items():
        ys = f['years']
        yi = YI[i]
        qc = cur_t[i]
        rc = (f.get('currency') or '').upper() or qc
        k = FX[qc] / FX[rc] if qc in FX and rc in FX else None
        for j in np.unique(yi[yi >= 3]):
            j = int(j)
            seq = ys[j - 3:j + 1]
            gaps = [SF.gap_days(seq[m + 1], seq[m]) for m in range(3)]
            ni = [y.get('netIncome') for y in seq]
            if any(g is None or not 300 <= g <= 430 for g in gaps) or any(x is None for x in ni):
                continue
            m = yi == j
            KN[i, m] = True
            if ni[0] > 0 and ni[3] > 0:
                g = (ni[3] / ni[0]) ** (1 / 3) - 1
                G3[i, m] = g
                UP3[i, m] = ni[1] > ni[0] and ni[2] > ni[1] and ni[3] > ni[2]
                if k is not None and .10 <= g <= .50:
                    with np.errstate(invalid='ignore', divide='ignore'):
                        pe = C[i, m].astype(float) * SH[i, m] / (ni[3] * k[m])
                        PEG[i, m] = np.where((pe > 0) & (pe < 200), pe / (g * 100), np.nan)
    return G3, UP3, KN, PEG


def make_pick_pf(G, PF):
    """Copie de la sélection de base (comme survivant_ordre.py) ; avec use_pf, cassure en points et figures juste après 🔊 / 📣."""
    okn, mpn, v52, mom, trend, s26, bp8, wait, dem, hot, note, N = (G[k] for k in (
        'okn', 'mpn', 'v52', 'mom', 'trend', 's26', 'bp8', 'wait', 'dem', 'hot', 'note', 'N'))
    secs_ = G['secs']

    def pick(t, use_pf=False, n=5, reserve=1, bondCap=2, perSec=2):
        ok = okn[:, t] & ~(mpn[:, t] < 1 / 3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
        t0_ = ok & trend[:, t] & (s26[:, t] >= .41) & (mom[:, t] >= .6)
        t1_ = ok & trend[:, t] & (s26[:, t] >= .14) & (mom[:, t] >= .3) & ~t0_
        promo = t1_ & bp8[:, t] & ~wait[:, t]
        k0, k1 = t0_ | promo, t1_ & ~promo
        pri = 2 * hot[:, t] + bp8[:, t]
        pf = PF[:, t] if use_pf else np.zeros(N, bool)

        def order(M):
            idx = np.where(M)[0]
            return idx[np.lexsort((-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t], ~pf[idx], -pri[idx]))]
        out, seen = [], {}
        q = order(k0).tolist() + order(k1).tolist()
        m = n - reserve
        for cap in (perSec, perSec + 1):
            for i in q:
                if len(out) >= m:
                    break
                if i in out or seen.get(secs_[i], 0) >= cap:
                    continue
                seen[secs_[i]] = seen.get(secs_[i], 0) + 1
                out.append(i)
        if reserve:
            dm = ok & dem[:, t] & ~np.isin(np.arange(N), out)
            for i in order(dm):
                if len(out) >= n:
                    break
                if seen.get(secs_[i], 0) >= bondCap:
                    continue
                seen[secs_[i]] = seen.get(secs_[i], 0) + 1
                out.append(int(i))
            for i in q:
                if len(out) >= n:
                    break
                if i not in out and seen.get(secs_[i], 0) < perSec + 1:
                    seen[secs_[i]] = seen.get(secs_[i], 0) + 1
                    out.append(i)
        return [int(i) for i in out]
    return pick


def main():
    u, err = SE.get('user')
    used = int((u or {}).get('apiRequests') or 0)
    if str((u or {}).get('apiRequestsDate') or '') != time.strftime('%Y-%m-%d', time.gmtime()):
        used = 0
    if used > 68000:  # ce test en prend environ 29 000, limite 100 000 par jour
        log(f"{used} appels EODHD déjà utilisés aujourd'hui : relancer après la remise à zéro du compteur")
        return
    D = SE.prepare()
    if D is None:
        return
    P, C, V, liq, cols, secs, dates, T, t2001, ERAS, t00, dl, rows = (D[k] for k in (
        'P', 'C', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00', 'dl', 'rows'))
    N = len(cols)
    F = fundamentals_e(cols)
    J, nj, nr = SV.split_jumps(P, C)
    A, F9, BAD, YI, ALT, BEN = SF.dates_plus(F, cols, secs, dates, T)
    jumps = {md: SV.mcap_jumps(C, SV.shares_matrix(F, YI, J, C, dates, T, md)[0]) for md in ('now', 'pub')}
    default = 'now' if jumps['now'] <= jumps['pub'] else 'pub'
    SH, choice = SV.shares_matrix(F, YI, J, C, dates, T, 'auto', default)
    cur_t = [r['cur'] for r in rows]
    FX = SV.fx_table({c for c in cur_t} | {(f.get('currency') or '').upper() for f in F.values()}, dates)
    PB, odd = SV.pb_matrix(F, YI, C, SH, cur_t, FX)
    SURP, CQG = earnings_weeks(F, dates, T, N)
    G3, UP3, KN3, PEG = annual_growth(F, YI, C, SH, cur_t, FX, N, T)
    del SH, choice, J, F, C, ALT, BEN
    gc.collect()

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
    Cc = np.concatenate([np.zeros((N, 1)), np.cumsum(np.log1p(retw), 1)], 1)
    secs_a = np.array([str(s) for s in secs])
    zone = okn & trend & (s26 >= .14) & (mom >= .3) & (mom <= 2) & ~(mpn < 1 / 3) & ~(v52 >= .8)
    log(f"\nUnivers C : {N} sociétés")

    log("\n0. Couverture : part des sociétés investissables avec une surprise publiée depuis 13 semaines, une croissance sur un an de "
        "la dernière période, 3 exercices consécutifs, un PEG")
    for y in (2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023, 2026):
        t = min(int(np.searchsorted(dates, f'{y}-06-01')), T - 2)
        inv = okn[:, t]
        cl = [f"{(inv & m[:, t]).sum() / max(inv.sum(), 1) * 100:.0f} %" for m in (np.isfinite(SURP), np.isfinite(CQG), KN3, np.isfinite(PEG))]
        log(f"  {y} : surprise {cl[0]} · période sur un an {cl[1]} · 3 exercices {cl[2]} · PEG {cl[3]}")

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
        log(f"  {lab:46s} {mu:+5.1f} (t {tv:4.1f}) · " + ' · '.join(f"{el} {v:+5.1f}" for el, v in o.items()))

    SEL0 = G['SEL']

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
    pick = RP.make_pick(G)
    S_live = {t: pick(t, A=A, mode='live') for t in range(t2001, T - 1)}
    R_live = run(S_live)
    R0 = run(SEL0)

    log("\n1-3. Zone du 🎯 : écart à 6 mois avec la société moyenne (points ; une semaine sur 4 ; t sur des blocs de 26 semaines)")
    groups_line('toute la zone', np.ones_like(zone))
    Q = np.full((N, T), -1, np.int8)
    for t in range(T):
        k = okn[:, t] & np.isfinite(SURP[:, t])
        if k.sum() >= 30:
            a, b = np.nanpercentile(SURP[k, t], [100 / 3, 200 / 3])
            Q[k, t] = np.where(SURP[k, t] <= a, 0, np.where(SURP[k, t] <= b, 1, 2))
    for lab, q in (('surprise : tiers des plus mauvaises', 0), ('surprise : tiers du milieu', 1), ('surprise : tiers des meilleures', 2),
                   ('pas de publication depuis 13 semaines', -1)):
        groups_line(lab, Q == q)
    with np.errstate(invalid='ignore'):
        Cq = CQG >= .25
        Aa = UP3 & (G3 >= .25)
        groups_line('C : dernière période +25 % ou plus sur un an', Cq)
        groups_line('C : moins', np.isfinite(CQG) & ~Cq)
        groups_line('A : résultat en hausse 3 ans, +25 %/an ou plus', Aa)
        groups_line('A : non', KN3 & ~Aa)
        groups_line('C et A', Cq & Aa)
        groups_line('PEG de Lynch < 1', PEG < 1)
        groups_line('PEG ≥ 1', PEG >= 1)
        groups_line('PEG inconnu (croissance hors de 10-50 %, perte)', ~np.isfinite(PEG))

    log("\n1-2. Sélection en direct (filtre des comptes, protection −30 %) et filtres des bénéfices")
    line('société moyenne (sans frais)', Rm)
    line('sélection en direct', R_live)
    with np.errstate(invalid='ignore'):
        canslim_out = (np.isfinite(CQG) | KN3) & ~Cq & ~Aa
    for lab, mask in (('sans le tiers des plus mauvaises surprises', Q == 0), ('sans les sociétés ni C ni A (CANSLIM)', canslim_out)):
        share = np.mean([np.mean(mask[s, t]) for t, s in S_live.items() if len(s)]) * 100
        pk = RP.make_pick(dict(G, okn=okn & ~mask))
        R = run({t: pk(t, A=A, mode='live') for t in range(t2001, T - 1)})
        line(lab, R)
        sg, tv = cmp(R, R_live)
        v = ' → BAT LA SÉLECTION EN DIRECT : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejeté'
        log(f"    − en direct : {cells(sg)} pts/an (t {tv:4.1f}) ; lignes concernées dans la sélection en direct {share:.1f} %{v}")
    del Q
    gc.collect()

    log("\n3. PEG de Lynch, stratégie à part (10 lignes, 2 par secteur, PEG le plus bas sous 1), face au 💎")

    def top(pool, order, n=10, per_sec=2):
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

    def peg_pick(t):
        with np.errstate(invalid='ignore'):
            return top(okn[:, t] & (PEG[:, t] < 1) & ~(v52[:, t] >= .8) & ~jump1y[:, t], PEG[:, t])

    def value_picks(t, n=10, per_sec=2):
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
    S_peg = {t: peg_pick(t) for t in range(t2001, T - 1)}
    R_val = run({t: value_picks(t) for t in range(t2001, T - 1)})
    R_peg = run(S_peg)
    log(f"  lignes par semaine (médiane) {np.median([len(S_peg[t]) for t in range(t2001, T - 1)]):.0f}")
    line('💎 (référence)', R_val)
    line('PEG de Lynch', R_peg)
    sg, tv = cmp(R_peg, Rm)
    v1 = 'tient (mieux que la société moyenne dans chaque période)' if all(x > 0 for x in sg) else 'ne tient pas'
    sg2, tv2 = cmp(R_peg, R_val)
    v2 = 'BAT LE 💎 : à proposer à François' if all(x > 0 for x in sg2) and tv2 >= 3 else 'ne remplace pas le 💎'
    log(f"    − société moyenne : {cells(sg)} pts/an (t {tv:4.1f}) → {v1} ; − 💎 : {cells(sg2)} (t {tv2:4.1f}) → {v2}")
    log("\n4. Cassure en points et figures en priorité dans la sélection de base (cours journaliers)")
    fri = np.array([np.datetime64(d, 'D').astype(int) for d in dates])
    PF = np.zeros((N, T), bool)
    t0, errs = time.time(), {}

    def one(i):
        x, e = SE.get(f"eod/{cols[i]}", **{'from': SE.START})
        return i, x, e
    with cf.ThreadPoolExecutor(8) as pool:
        for n, (i, x, e) in enumerate(pool.map(one, range(N))):
            if e:
                errs[e] = errs.get(e, 0) + 1
                continue
            try:
                o, _, _, _ = SR.daily_signals(x, Pw[i], fri, FX.get(rows[i]['cur'], np.ones(T)))
                PF[i] = o['pf']
            except Exception as ex:
                errs[type(ex).__name__] = errs.get(type(ex).__name__, 0) + 1
    PF &= okn
    log(f"  cours journaliers : {N} sociétés en {time.time() - t0:.0f} s ; erreurs {errs or 'aucune'} ; semaines-sociétés en cassure "
        f"{int(PF.sum())}, dans la zone du 🎯 {int((PF & zone).sum())}")
    pk = make_pick_pf(G, PF)
    same = np.mean([pk(t) == list(SEL0[t]) for t in range(t2001, T - 1)]) * 100
    log(f"  copie de la sélection de base identique : {same:.1f} % des semaines")
    S_pf = {t: pk(t, use_pf=True) for t in range(t2001, T - 1)}
    diff = np.mean([S_pf[t] != list(SEL0[t]) for t in range(t2001, T - 1)]) * 100
    R_pf = run(S_pf)
    line('sélection de base', R0)
    line('cassure en points et figures en priorité', R_pf)
    sg, tv = cmp(R_pf, R0)
    v = ' → BAT LA SÉLECTION : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejeté'
    log(f"    − sélection : {cells(sg)} pts/an (t {tv:4.1f}) ; semaines différentes {diff:.0f} %{v}")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
