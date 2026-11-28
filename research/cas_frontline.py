"""Le cas Frontline et l'anatomie des grandes hausses, sans biais du survivant (28/11/2026).

François : « Analyser le cas de frontline et d'autres actions de ce type pour détecter encore plus tôt le moment d'achat et profiter
au maximum des 117 % de hausse puis améliorer notre modèle ». Frontline (FRO.OL, pétrolier) : +117 % de hausse sur 12 mois (sans le
dernier mois) le 27/11/2026, sélectionnée en direct en semaine 45 puis 48 (en attente ⏸️).

1. Frontline semaine par semaine, avec les règles de l'outil rejouées sur les cours EODHD (univers C de survivant_eodhd.py) : hausse
   sur 12 mois, pente sur 6 mois, palier du 🎯 (0 fort, 1 assoupli, 2 comptes non solides en direct), rang parmi les candidates,
   sélection (règle de base sans le filtre des comptes, et en direct avec lui), bond 📣, raison quand elle est hors du 🎯.
2. Ses voisines (pétroliers, armateurs, pétrolières de l'univers) : creux, sommet, première entrée dans le 🎯, première sélection,
   part de la hausse déjà faite à ce moment.
3. Anatomie des grandes hausses 2001-2026 (toutes les sociétés, disparues comprises) : cours doublé en un an au plus depuis un plus
   bas d'un an ; part de la hausse faite (en logarithme) à la première sélection, délai, résultat à 6 mois de la première
   sélection, part jamais sélectionnée avant le sommet ; par période. Descriptif : une règle d'entrée plus précoce se juge ensuite
   sur toutes les sociétés, pas sur les seules gagnantes.
Lancé par « Recherche (à la demande) » (script cas_frontline.py), environ 25 minutes, environ 27 000 appels EODHD (comptes pour le
filtre en direct). Cours et comptes en mémoire ; la clé n'est jamais affichée.
"""
import gc
import time

import numpy as np
import pandas as pd

import revue_pistes as RP
import survivant_comptes as SC
import survivant_eodhd as SE

log = SE.log
PEERS = ['FRO.OL', 'OET.OL', 'CMBTO.OL', 'CMBT.BR', 'HAUTO.OL', 'WAWI.OL', 'EQNR.OL', 'VAR.OL', 'OKEA.OL', 'AKRBP.OL', 'DNO.OL',
         'BNOR.OL', 'REP.MC']


def main():
    u, err = SE.get('user')
    used = int((u or {}).get('apiRequests') or 0)
    if str((u or {}).get('apiRequestsDate') or '') != time.strftime('%Y-%m-%d', time.gmtime()):
        used = 0
    if used > 70000:
        log(f"{used} appels EODHD déjà utilisés aujourd'hui : relancer après la remise à zéro du compteur")
        return
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00, dl = (D[k] for k in (
        'P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00', 'dl'))
    N = len(cols)
    F = SC.fundamentals(cols)
    A = SC.verdicts(F, cols, secs, dates, T)
    del F
    gc.collect()
    G = SE.chain(P, V, dates, cols, secs, liq >= SE.LIQ)
    del D, V
    gc.collect()
    okn, mpn, v52, mom, trend, s26, bp8, wait, dem, hot, note = (G[k] for k in (
        'okn', 'mpn', 'v52', 'mom', 'trend', 's26', 'bp8', 'wait', 'dem', 'hot', 'note'))
    Pw = G['P']
    B = G['R0'] | G['R1']
    SEL = G['SEL']
    pick = RP.make_pick(G)
    idx = {c: i for i, c in enumerate(cols)}
    t0 = time.time()
    LIVE = {t: pick(t, A=A, mode='live') for t in range(t2001, T - 1)}
    log(f"\nUnivers C : {N} sociétés ; sélections en direct rejouées en {time.time() - t0:.0f} s")

    def tiers(t, live):
        a = A[:, t] if live else np.zeros(N, np.int8)
        good, bad = a == 1, a == 3
        ok = okn[:, t] & ~(mpn[:, t] < 1 / 3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
        t0_ = ok & trend[:, t] & (s26[:, t] >= .41) & (mom[:, t] >= .6)
        t1_ = ok & trend[:, t] & (s26[:, t] >= .14) & (mom[:, t] >= .3) & ~t0_
        promo = t1_ & bp8[:, t] & ~wait[:, t]
        k0, k1, k2 = t0_ | promo, t1_ & ~promo, np.zeros(N, bool)
        if live:
            k2 = (k0 | k1) & ~good & ~bad
            k0, k1 = k0 & good, k1 & good
        pri = 2 * hot[:, t] + bp8[:, t]

        def order(M):
            ii = np.where(M)[0]
            keys = (-np.nan_to_num(s26[ii, t]), -np.nan_to_num(note[ii, t]), wait[ii, t], -pri[ii])
            return ii[np.lexsort(keys)]
        q = order(k0).tolist() + order(k1).tolist() + order(k2).tolist()
        return k0, k1, k2, q, bad

    ZB = np.zeros((N, T), bool)  # dans le 🎯 (paliers 0-1, règle de base) chaque semaine
    for t in range(t2001, T - 1):
        k0, k1, _, _, _ = tiers(t, False)
        ZB[:, t] = k0 | k1

    def why(t, i):
        if not okn[i, t]:
            return 'non investissable (liquidité ou historique)'
        if mpn[i, t] < 1 / 3:
            return 'tiers le plus faible du momentum'
        if v52[i, t] >= .8:
            return 'volatilité ≥ 80 %'
        if mom[i, t] > 2:
            return 'hausse > +200 %'
        if not trend[i, t]:
            return 'pas en tendance'
        if mom[i, t] < .3:
            return 'hausse sur 12 mois < +30 %'
        if s26[i, t] < .14:
            return 'pente sur 6 mois < +14 %'
        return ''

    def f(v, pc=True):
        return '   —' if v is None or not np.isfinite(v) else (f"{v * 100:+5.0f}" if pc else f"{v:7.1f}")

    # 1. Frontline
    i = idx.get('FRO.OL')
    if i is None:
        log("Frontline (FRO.OL) absente de l'univers C")
    else:
        log("\n1. Frontline (FRO.OL), semaine par semaine (cours ajusté en NOK ; hausse 12 mois sans le dernier mois ; pente 6 mois ; "
            "palier et rang parmi les candidates : base | en direct ; ✔ sélectionnée)")
        a = int(np.searchsorted(dates, '2025-06-01'))
        for t in range(a, T - 1):
            k0, k1, k2, q, bad = tiers(t, False)
            l0, l1, l2, ql, badl = tiers(t, True)
            tb = 0 if k0[i] else 1 if k1[i] else None
            tl = 0 if l0[i] else 1 if l1[i] else 2 if l2[i] else None
            rb = (q.index(i) + 1) if i in q else None
            rl = (ql.index(i) + 1) if i in ql else None
            sb = '✔' if i in SEL.get(t, []) else ' '
            sl = '✔' if i in LIVE.get(t, []) else ' '
            ev = ('📣' if B[i, t] else '  ') + ('⏸️' if wait[i, t] else '  ')
            acc = {1: 'solides', 2: 'mitigés', 3: 'dégradation', 0: 'pas lus', 4: 'banque'}.get(int(A[i, t]), '?')
            log(f"  {dates[t]} {f(Pw[i, t], False)} 12m {f(mom[i, t])} pente {f(s26[i, t])} palier {tb if tb is not None else '-'}|"
                f"{tl if tl is not None else '-'} rang {rb or '-':>4}/{len(q):<4}|{rl or '-':>4}/{len(ql):<4} {sb}{sl} {ev} comptes {acc:11s} {why(t, i)}")

    # 2. voisines
    log("\n2. Voisines : creux (plus bas d'un an), sommet après, première entrée dans le 🎯, première sélection (base | en direct) et part "
        "de la hausse déjà faite (en logarithme)")
    a26 = int(np.searchsorted(dates, '2025-06-01'))
    for c in PEERS:
        i = idx.get(c)
        if i is None:
            log(f"  {c:10s} absente de l'univers C")
            continue
        p = Pw[i, a26:T - 1]
        if not np.isfinite(p).any():
            log(f"  {c:10s} pas de cours")
            continue
        tr = a26 + int(np.nanargmin(p))
        pk = tr + int(np.nanargmax(Pw[i, tr:T - 1]))
        rise = np.log(Pw[i, pk] / Pw[i, tr])
        zone = [t for t in range(tr, T - 1) if ZB[i, t]]
        fb = next((t for t in range(tr, T - 1) if i in SEL.get(t, [])), None)
        fl = next((t for t in range(tr, T - 1) if i in LIVE.get(t, [])), None)

        def done(t):
            return f"{np.log(Pw[i, t] / Pw[i, tr]) / rise * 100:3.0f} %" if t is not None and rise > 0 else '  —'
        log(f"  {c:10s} creux {dates[tr]} → sommet {dates[pk]} ({(np.exp(rise) - 1) * 100:+4.0f} %) ; 🎯 dès {dates[zone[0]] if zone else '—'} "
            f"({done(zone[0]) if zone else '—'}) ; sélection {dates[fb] if fb else '—'} ({done(fb)}) | {dates[fl] if fl else '—'} ({done(fl)})")

    # 3. anatomie des grandes hausses
    log("\n3. Grandes hausses 2001-2026 : cours doublé en 52 semaines au plus depuis un plus bas d'un an, société investissable au creux")
    eps = []
    df = pd.DataFrame(np.asarray(Pw, float).T)
    low52 = df.rolling(53, min_periods=26).min().values.T  # plus bas des 52 semaines passées, semaine comprise
    fmax = df[::-1].rolling(52, min_periods=4).max()[::-1].shift(-1).values.T  # plus haut des 52 semaines suivantes
    with np.errstate(invalid='ignore'):
        cand = (np.asarray(Pw, float) <= low52) & (fmax >= 2 * np.asarray(Pw, float))
    for i in range(N):
        p = np.asarray(Pw[i], float)
        ws = np.where(cand[i, t2001:T - 2])[0] + t2001
        k = 0
        for w in ws:
            if w < k:
                continue
            seg = p[w:min(T - 1, w + 27)]
            if not np.isfinite(seg).any():
                continue
            tr = w + int(np.nanargmin(seg))
            sg2 = p[tr:min(T - 1, tr + 79)]
            pk = tr + int(np.nanargmax(sg2))
            if pk > tr and (okn[i, tr] or okn[i, min(tr + 4, T - 2)]):
                eps.append((i, tr, pk))
            k = pk + 1
    log(f"  {len(eps)} grandes hausses dans {len({e[0] for e in eps})} sociétés")
    for el, a, b in ERAS:
        E = [e for e in eps if a <= e[1] < b]
        if not E:
            continue
        rows = []
        for i, tr, pk in E:
            rise = np.log(Pw[i, pk] / Pw[i, tr])
            fb = next((t for t in range(tr, pk + 1) if i in SEL.get(t, [])), None)
            fl = next((t for t in range(tr, pk + 1) if i in LIVE.get(t, [])), None)
            fz = next((t for t in range(tr, pk + 1) if ZB[i, t]), None)
            fbond = next((t for t in range(tr, pk + 1) if B[i, t]), None)
            r6 = (Pw[i, min(fb + 26, T - 2)] / Pw[i, fb] - 1) if fb is not None else np.nan
            rows.append((rise, fb, fl, fz, fbond, tr, pk, r6, i))
        sel = [r for r in rows if r[1] is not None]
        sell = [r for r in rows if r[2] is not None]

        def frac(r, t):
            return np.log(Pw[r[8], t] / Pw[r[8], r[5]]) / r[0]
        log(f"  {el} : {len(E)} hausses (médiane {np.median([np.exp(r[0]) - 1 for r in rows]) * 100:+.0f} % du creux au sommet, "
            f"{np.median([r[6] - r[5] for r in rows]):.0f} semaines) ; sélectionnées avant le sommet {len(sel) / len(E) * 100:.0f} % (base), "
            f"{len(sell) / len(E) * 100:.0f} % (en direct)")
        if sel:
            log(f"     première sélection (base) : {np.median([r[1] - r[5] for r in sel]):.0f} semaines après le creux, hausse déjà faite "
                f"{np.median([frac(r, r[1]) for r in sel]) * 100:.0f} % (quartiles {np.percentile([frac(r, r[1]) for r in sel], 25) * 100:.0f}-"
                f"{np.percentile([frac(r, r[1]) for r in sel], 75) * 100:.0f} %) ; puis 6 mois : médiane {np.nanmedian([r[7] for r in sel]) * 100:+.0f} %")
        bonds = [r for r in rows if r[4] is not None]
        if bonds:
            log(f"     premier bond 📣 après le creux : {np.median([r[4] - r[5] for r in bonds]):.0f} semaines, hausse déjà faite "
                f"{np.median([frac(r, r[4]) for r in bonds]) * 100:.0f} % ({len(bonds) / len(E) * 100:.0f} % des hausses en ont un)")
        zs = [r for r in rows if r[3] is not None]
        if zs:
            log(f"     première entrée dans le 🎯 (paliers 0-1) : {np.median([r[3] - r[5] for r in zs]):.0f} semaines après le creux, hausse "
                f"déjà faite {np.median([frac(r, r[3]) for r in zs]) * 100:.0f} %")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
