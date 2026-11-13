"""Place 📣 de la sélection et cassure de canal naissant (13/11/2026, François : « faire ce qui est pertinent et nécessaire », après
cassure_canal.py). Par événement, le canal naissant cassé avant le 🎯, en tendance, sur 3 fois le volume fait +13,4 points à 6 mois
et bat le 📣 bond du jour dans chaque période ; reste à voir si la sélection du lundi y gagne.

Portefeuille simulé 1998-2026 de backtest/_selection_sim.py (règles de ES.pickN sans les comptes ni la liquidité, 5 lignes chaque
semaine gardées 6 mois, frais 0,3 % par sens), comme pour la décision de la place 📣 (_selection_sim9.py). Masque hebdomadaire :
une séance au moins dans la semaine avec la cassure d'un canal naissant (règle de cassure_canal.py), avant le 🎯, en tendance, sur
3 fois le volume moyen de 50 séances (1,5 et 2 fois pour la robustesse), calculé sur les cours journaliers.
Variante principale (fixée avant le calcul) : la place 📣 prend aussi une société dont le canal naissant a cassé dans les 3 dernières
semaines (mêmes filtres que le 📣 : tendance, hors tiers le plus faible, hors ⚡, 2 par secteur, même ordre). Adoptée seulement si
elle bat la règle actuelle sur chacune des périodes 1998-2008, 2009-2017 et 2018-2026. Variantes : canal d'abord dans la place,
canal seul dans la place, volume 1,5 et 2 fois.

Étapes : cours journaliers Yahoo (masque), cours hebdomadaires Yahoo de backtest/_long.py (long.npz), puis la chaîne
_selection_sim7.py. Lancé par « Recherche (à la demande) » (script place_canal.py), environ 15 minutes.
"""
import os
import runpy
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT

log, shift, roll = FB.log, FB.shift, HT.roll
SLOPE_MIN, SLOPE_MAX = np.log(1.15) / 250, np.log(2.5) / 250
L1, L3, L5 = np.log(1.01), np.log(1.03), np.log(1.05)


def nascent(N, T, ok, pl, ph, Lb, LC, lH, lL):
    """Cassures par le haut de canaux naissants (même règle que cassure_canal.py, réglage de base)."""
    out = np.zeros((N, T), bool)
    for i in range(N):
        PL, PH = np.flatnonzero(pl[i]), np.flatnonzero(ph[i])
        if PL.size < 2 or PH.size < 1:
            continue
        prev, busy = None, -1
        for k in PL:
            k = int(k)
            if prev is None:
                prev = k
                continue
            if k - prev < 15:
                if Lb[i, k] < Lb[i, prev]:
                    prev = k
                continue
            k1, k2 = prev, k
            prev = k
            td = k2 + 5
            if td >= T - 2 or td < 260 or td <= busy or not Lb[i, k2] > Lb[i, k1]:
                continue
            sl = (lL[i, k2] - lL[i, k1]) / (k2 - k1)
            if not (SLOPE_MIN <= sl <= SLOPE_MAX):
                continue
            mid = PH[(PH > k1) & (PH < k2)]
            if not mid.size:
                continue
            lo0 = lL[i, k1]
            hi0 = float(np.max(lH[i, mid] - sl * (mid - k1)))
            if not (.15 <= np.exp(hi0 - lo0) - 1 <= .5):
                continue
            seg = np.arange(k1, k2 + 1)
            if np.nanmin(LC[i, seg] - (lo0 + sl * (seg - k1))) < -L3:
                continue
            us = np.arange(td + 1, min(T, td + 251))
            base = lo0 + sl * (us - k1)
            x = LC[i, us]
            dn = np.flatnonzero(x < base - L5)
            up = np.flatnonzero(x > base + (hi0 - lo0) + L1)
            jd = dn[0] if dn.size else 10 ** 9
            ju = up[0] if up.size else 10 ** 9
            if ju < jd and ju < 10 ** 9:
                out[i, us[ju]] = True
                busy = int(us[ju])
            elif jd < 10 ** 9:
                busy = int(us[jd])
    return out


def daily_masks():
    """Masques hebdomadaires (vendredi) des cassures de canal naissant avant le 🎯, en tendance, par seuil de volume."""
    t0 = time.time()
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates, cols = D['Close'].index, list(D['Close'].columns)
    N, T = C.shape
    log(f"cours journaliers : {N} sociétés, {T} séances en {time.time() - t0:.0f} s")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0) & (C > 0)
        Hb, Lb = np.minimum(H, C * 1.5), np.maximum(L, C / 1.5)
        hmax = pd.DataFrame(Hb.T).rolling(11, center=True, min_periods=11).max().values.T
        lmin = pd.DataFrame(Lb.T).rolling(11, center=True, min_periods=11).min().values.T
        ph, pl = ok & (Hb >= hmax), ok & (Lb <= lmin)
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = ok & (C > m200) & (m50 > m200)
        mom = shift(C, 21) / shift(C, 252) - 1
        early = ok & (mom > -.2) & (mom < .6)
        LC = np.where(ok, np.log(np.where(C > 0, C, np.nan)), np.nan).astype(np.float64)
        lH, lL = np.log(Hb).astype(np.float64), np.log(Lb).astype(np.float64)
    NAI = nascent(N, T, ok, pl, ph, Lb, LC, lH, lL)
    out = {}
    for vm in (1.5, 2, 3):
        M = NAI & early & trend & (vx >= vm)
        out[vm] = pd.DataFrame(M.T, index=dates, columns=cols).resample('W-FRI').max()
        log(f"canal naissant cassé, avant le 🎯, en tendance, volume ≥ {vm} : {int(M.sum())} séances, "
            f"{int(out[vm].values.sum())} semaines")
    return out


def main():
    t0 = time.time()
    masks = daily_masks()
    os.chdir('backtest')
    Lg = runpy.run_path('_long.py', run_name='long_build')
    sec = Lg['universe']()
    W, V = Lg['download'](list(sec))
    W = W.loc['1985':]
    V = V.reindex(index=W.index, columns=W.columns)
    wdates = [str(d.date()) for d in W.index]
    wcols = list(W.columns)
    P, cut = Lg['clean'](W.values.T.astype(float))
    np.savez_compressed('long.npz', P=P.astype('float32'), V=V.values.T.astype('float32'), dates=np.array(wdates),
                        cols=np.array(wcols), sec=np.array([sec.get(c, '?') for c in wcols]))
    log(f"cours hebdomadaires : {len(wcols)} sociétés, {len(wdates)} semaines ({wdates[0]} → {wdates[-1]}), "
        f"{cut} séries coupées, en {time.time() - t0:.0f} s depuis le début")
    G = {'__name__': 'selection_sim'}
    code = open('_selection_sim7.py').read().split("\nif __name__ == '__main__':")[0]
    exec(compile(code, '_selection_sim7.py', 'exec'), G)
    gN, gT = G['P'].shape
    gcols = [str(c) for c in G['z']['cols']]
    gdates = [str(d) for d in G['dates']]
    CN = {}
    for vm, Wm in masks.items():
        Wm.index = [str(d.date()) for d in Wm.index]
        A = Wm.reindex(index=gdates, columns=gcols).fillna(False).values.T.astype(bool)
        CN[vm] = A
    log(f"masques alignés : {sum(c in masks[3].columns for c in gcols)} sociétés communes sur {gN}, "
        f"{int(CN[3].sum())} semaines-sociétés (volume ≥ 3)")
    ago_any, weekly, pick, pick2, blocks, ev = (G[k] for k in ('ago_any', 'weekly', 'pick', 'pick2', 'blocks', 'ev'))
    trend, okn, mpn, v52, valid, Q = (G[k] for k in ('trend', 'okn', 'mpn', 'v52', 'valid', 'Q'))
    R0, R1, t1997 = G['R0'], G['R1'], G['t1997']
    okd = trend & okn & (mpn >= 1 / 3) & ~(v52 >= .8)
    base_dem = G['dem'].copy()
    base_fb8 = G['FB8'].copy()

    log("\n=== Par événement, cadre hebdomadaire (écart avec la moyenne des sociétés, 6 mois)")
    okb = valid & ~(v52 >= .8)
    ev('📣 de la semaine en tendance, hors 🎯 (référence)', okb & (R0 | R1) & trend & ~Q, 26)
    for vm in (1.5, 2, 3):
        ev(f'canal naissant cassé, volume ≥ {vm}, hors 🎯 (semaine)', okb & CN[vm] & ~Q, 26)
    ev('canal naissant cassé, volume ≥ 3, sans 📣 la même semaine', okb & CN[3] & ~(R0 | R1) & ~Q, 26)

    def run_with(dmask=None, first=None):
        G['dem'] = base_dem if dmask is None else dmask
        G['FB8'] = base_fb8 if first is None else first
        if first is None:
            return weekly(lambda t: pick(t, n=5, reserve=1, bondCap=2), t1997, gT)
        return weekly(lambda t: pick2(t, fb_slot=True), t1997, gT)

    A0 = run_with()
    A2 = weekly(lambda t: pick2(t, fb_slot=False), t1997, gT)
    log(f"\nRègle actuelle (4 🎯 + 1 📣) : {A0.mean() * 52 * 100:+.1f} % par an avant marché ; copie de contrôle : "
        f"{A2.mean() * 52 * 100:+.1f} %")
    log("Écart avec la règle actuelle (rendement hebdomadaire annualisé, t sur blocs de 6 mois) :")
    c3 = ago_any(CN[3], 4) & okd
    variants = [
        ('📣 ou canal naissant cassé (volume ≥ 3) dans les 3 semaines — principale', dict(dmask=base_dem | c3)),
        ('canal naissant cassé d\'abord dans la place 📣', dict(dmask=base_dem | c3, first=c3)),
        ('canal naissant cassé seul dans la place 📣', dict(dmask=c3)),
        ('📣 ou canal naissant cassé (volume ≥ 2)', dict(dmask=base_dem | (ago_any(CN[2], 4) & okd))),
        ('📣 ou canal naissant cassé (volume ≥ 1,5)', dict(dmask=base_dem | (ago_any(CN[1.5], 4) & okd))),
    ]
    for lab, kw in variants:
        B = run_with(**kw)
        log(f"  {lab:74s} {blocks(B - A0)}")
    G['dem'], G['FB8'] = base_dem, base_fb8
    elig = okn & ~(mpn < 1 / 3) & ~(v52 >= .8)
    wk = np.arange(gT) >= t1997
    has_dem = ((base_dem & elig).any(0))[wk].mean() * 100
    has_c3 = ((c3 & elig).any(0))[wk].mean() * 100
    only_c3 = ((c3 & elig).any(0) & ~(base_dem & elig).any(0))[wk].mean() * 100
    log(f"semaines avec un candidat 📣 : {has_dem:.0f} % ; avec un canal naissant cassé (volume ≥ 3) : {has_c3:.0f} % ; "
        f"canal sans 📣 cette semaine-là : {only_c3:.0f} %")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
