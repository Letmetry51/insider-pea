"""Signaux entourés par François sur le graphique journalier d'Euronext (18/11/2026, « faire un backtest pour vérifier si ce
screener est optimal ») : supertrend adaptatif (ML_adaptative_supertrend) qui passe haussier, volume cumulé (OBV) au plus haut,
oscillateur qui remonte au-dessus de sa moyenne depuis une zone basse, force relative (PRC_Relative Strength Rank 20 140 0 10)
qui repasse au-dessus de 0. Screener : signaux-entoures.txt (ProScreener), quatre signaux apparus dans les 15 dernières séances,
3 au moins par défaut.

Mêmes calculs que le screener, séance par séance, sur les séances de cotation de chaque société :
- supertrend adaptatif (PRC_Machine Learning Adaptive SuperTrend) : ATR 10 de Wilder, volatilité des 100 dernières séances rangée
  en 3 classes par K-means (centroïdes de départ à 75, 50 et 25 % de l'écart entre plus bas et plus haut, 20 tours au plus,
  arrêt sous 0,00001), bandes à 3 fois la volatilité de la classe la plus proche autour du milieu de séance ; passage haussier
  quand le sens passe de 1 à -1 ;
- OBV au-dessus de son plus haut des 20 séances précédentes ;
- RSI 14 de Wilder qui passe au-dessus de sa moyenne 9 séances, RSI de 40 ou moins dans les 10 dernières séances (« Mon
  indicateur(2) » est inconnu : RSI supposé) ;
- force relative : (2 × cours − moyenne 20 − moyenne 140) / (2 × ATR 10) qui passe au-dessus de 0 ;
- liquidité : 1 M échangé par jour au moins (moyenne de 63 séances, devise de cotation) ; 161 séances d'historique.

Mesure de hausse_tot5.py / prorealcode_nouveautes.py : cours journaliers Yahoo des sociétés de l'étude longue (survivantes :
biais du survivant, mêmes sociétés pour la référence), achat à l'ouverture du lendemain du premier jour où le screener retient
la société, écart avec la moyenne des sociétés à 1, 3, 6 et 12 mois, une entrée par société et par semestre, t regroupé par
mois, trois périodes 2000-2008 / 2009-2017 / 2018-2026. Comparaison : la zone du 🎯 (en tendance, +60 à +200 % sur 12 mois) sur
les mêmes cours.

Règle fixée avant le calcul : le screener n'est « bon » que s'il bat la moyenne des sociétés à 6 mois dans chacune des trois
périodes avec t ≥ 3 ; il ne peut remplacer ou compléter le 🎯 que s'il fait mieux que la zone du 🎯 dans chaque période.
Lancé par « Recherche (à la demande) » (script signaux_entoures.py), environ 15 minutes.
"""
import time

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3
from hausse_tot5 import stats4

log, shift, dedup, roll = FB.log, FB.shift, FB.dedup, HT.roll


def ewm_wilder(x, n):
    """Lissage de Wilder (1/n), comme AverageTrueRange et RSI de ProRealTime ; les écarts de départ s'effacent en 50 séances."""
    return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().values


def ml_supertrend(Hh, Ll, Cc, train=100, fact=3.0, iters=20, eps=1e-5):
    """Sens du supertrend adaptatif à chaque séance (1 baissier, -1 haussier), comme signaux-entoures.txt."""
    T = len(Cc)
    C1 = np.concatenate([[Cc[0]], Cc[:-1]])
    tr = np.maximum(Hh - Ll, np.maximum(np.abs(Hh - C1), np.abs(Ll - C1)))
    tr[0] = Hh[0] - Ll[0]
    atr = ewm_wilder(tr, 10)
    s = pd.Series(atr)
    hi = s.rolling(train, min_periods=1).max().values
    lo = s.rolling(train, min_periods=1).min().values
    cH, cM, cL = lo + (hi - lo) * .75, lo + (hi - lo) * .5, lo + (hi - lo) * .25
    if T >= train:
        W = swv(atr, train)                       # ligne j : séances j à j + train - 1
        rows = np.arange(train - 1, T)
        okr = np.isfinite(W).all(1) & (atr[rows] > 0)
        h, m, low = cH[rows].copy(), cM[rows].copy(), cL[rows].copy()
        active = okr.copy()
        for _ in range(iters):
            idx = np.where(active)[0]
            if not len(idx):
                break
            Wa = W[idx]
            dH, dM, dL = np.abs(Wa - h[idx, None]), np.abs(Wa - m[idx, None]), np.abs(Wa - low[idx, None])
            gH = (dH <= dM) & (dH <= dL)
            gM = ~gH & (dM <= dL)
            gL = ~gH & ~gM
            new = []
            for c, g in ((h, gH), (m, gM), (low, gL)):
                n = g.sum(1)
                new.append(np.where(n > 0, (Wa * g).sum(1) / np.maximum(n, 1), c[idx]))
            conv = ((np.abs(new[0] - h[idx]) < eps) & (np.abs(new[1] - m[idx]) < eps) & (np.abs(new[2] - low[idx]) < eps))
            h[idx], m[idx], low[idx] = new
            active[idx[conv]] = False
        cH[rows[okr]], cM[rows[okr]], cL[rows[okr]] = h[okr], m[okr], low[okr]
    d0, d1, d2 = np.abs(atr - cH), np.abs(atr - cM), np.abs(atr - cL)
    vol = np.where((d1 < d0) & (d1 <= d2), cM, cH)
    vol = np.where((d2 < d0) & (d2 < d1), cL, vol)
    mid = (Hh + Ll) / 2
    bu, bl = mid + fact * vol, mid - fact * vol
    sens = np.ones(T, np.int8)
    hp = bp = lp = 0.0
    for t in range(T):
        if t == 0 or hp == 0:
            ha, ba = bu[t], bl[t]
        else:
            ba = bp if (bl[t] <= bp and Cc[t - 1] >= bp) else bl[t]
            ha = hp if (bu[t] >= hp and Cc[t - 1] <= hp) else bu[t]
        if lp == hp:
            d = -1 if Cc[t] > ha else 1
        else:
            d = 1 if Cc[t] < ba else -1
        sens[t] = d
        hp, bp, lp = ha, ba, (ba if d == -1 else ha)
    return sens, atr


def recent(x, w):
    """Vrai si l'évènement a eu lieu dans les w dernières séances (séance du jour comprise)."""
    return pd.Series(x.astype(np.float32)).rolling(w, min_periods=1).max().values > 0


def signals(O, H, L, C, V):
    """Signaux du screener sur les séances de cotation d'une société (tableaux compacts)."""
    T = len(C)
    sens, atr = ml_supertrend(H.astype(np.float64), L.astype(np.float64), C.astype(np.float64))
    bascule = np.zeros(T, bool)
    bascule[1:] = (sens[1:] == -1) & (sens[:-1] == 1)
    obv = np.cumsum(np.concatenate([[0.0], np.sign(np.diff(C)) * V[1:]]))
    obv_hi = pd.Series(obv).rolling(20, min_periods=20).max().shift(1).values
    obv_haut = obv > np.nan_to_num(obv_hi, nan=np.inf)
    dC = np.diff(C, prepend=C[0])
    up, dn = ewm_wilder(np.maximum(dC, 0), 14), ewm_wilder(np.maximum(-dC, 0), 14)
    rsi = np.where(dn > 0, 100 - 100 / (1 + up / np.where(dn > 0, dn, 1)), 100.0)
    rsi[:15] = np.nan
    rsi_m = pd.Series(rsi).rolling(9, min_periods=9).mean().values
    rsi_lo = pd.Series(rsi).rolling(10, min_periods=10).min().values
    with np.errstate(invalid='ignore'):
        croix = np.zeros(T, bool)
        croix[1:] = (rsi[1:] > rsi_m[1:]) & (rsi[:-1] <= rsi_m[:-1]) & (rsi_lo[1:] <= 40)
        m20 = pd.Series(C).rolling(20, min_periods=20).mean().values
        m140 = pd.Series(C).rolling(140, min_periods=140).mean().values
        rsr = np.where(atr > 0, (2 * C - m20 - m140) / (2 * atr), 0.0)
        remonte = np.zeros(T, bool)
        remonte[1:] = (rsr[1:] > 0) & (rsr[:-1] <= 0)
        liq = C * pd.Series(V).rolling(63, min_periods=50).mean().values >= 1e6
    base = liq & (np.arange(T) >= 160)
    out = {'base': base, 'haussier': sens == -1, 'rs_pos': np.nan_to_num(rsr) > 0}
    for w in (10, 15, 20):
        st = recent(bascule, w) & (sens == -1)
        ob = recent(obv_haut, w)
        os_ = recent(croix, w)
        rs = recent(remonte, w) & (np.nan_to_num(rsr) > 0)
        out[w] = (st, ob, os_, rs)
    out['events'] = (bascule, obv_haut, croix, remonte)
    return out


def main():
    t0 = time.time()
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates = D['Close'].index
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    N, T = C.shape
    log(f"téléchargé en {time.time() - t0:.0f} s : {N} sociétés, {T} séances")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H >= L) & (np.nan_to_num(V) > 0) & (C > 0)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        mom = shift(C, 21) / shift(C, 252) - 1
        liq_all = roll(np.where(ok, C * V, np.nan).astype(np.float32), 63, 'mean', 50) >= 1e6
        zone = ok & trend & (mom >= .6) & (mom <= 2.0) & liq_all

    keys = ['st', 'obv', 'osc', 'rs']
    M = {}

    def put(name, i, idx, x):
        if name not in M:
            M[name] = np.zeros((N, T), bool)
        M[name][i, idx] = x

    n_ev = np.zeros(4)
    t1 = time.time()
    for i in range(N):
        idx = np.where(ok[i])[0]
        if len(idx) < 300:
            continue
        S = signals(O[i, idx], H[i, idx], L[i, idx], C[i, idx], V[i, idx])
        b = S['base']
        for k, e in enumerate(S['events']):
            n_ev[k] += (e & b).sum()
        for w in (10, 15, 20):
            sig = S[w]
            n = sum(x.astype(int) for x in sig)
            put(f'n4_{w}', i, idx, b & (n == 4))
            put(f'n3_{w}', i, idx, b & (n >= 3))
            if w == 15:
                for k, nm in enumerate(keys):
                    put(nm, i, idx, b & sig[k])
                    others = [sig[j] for j in range(4) if j != k]
                    put(f'sans_{nm}', i, idx, b & others[0] & others[1] & others[2])
        if i % 100 == 0:
            log(f"  {i}/{N} sociétés, {time.time() - t1:.0f} s")
    log(f"signaux calculés en {time.time() - t1:.0f} s ; évènements (liquides, historique suffisant) : bascule haussière du "
        f"supertrend {int(n_ev[0])}, OBV au plus haut {int(n_ev[1])}, RSI qui remonte {int(n_ev[2])}, force relative > 0 {int(n_ev[3])}")

    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r

    def S4(lab, X):
        stats4(lab, dedup(X, 125), EX, RAW, months, yrs)

    log("\nÉcart avec la moyenne des sociétés (points de %), achat le lendemain du premier jour retenu, une entrée par semestre")
    log("=== Référence")
    S4("zone du 🎯 (tendance, +60 à +200 % sur 12 mois), 1 M/jour", zone)
    log("=== Le screener (15 séances)")
    S4("SCREENER : les 4 signaux (15 = 8 + 4 + 2 + 1)", M['n4_15'])
    S4("SCREENER : 3 signaux au moins (réglage par défaut)", M['n3_15'])
    log("=== Fenêtre")
    for w in (10, 20):
        S4(f"les 4 signaux en {w} séances", M[f'n4_{w}'])
        S4(f"3 signaux au moins en {w} séances", M[f'n3_{w}'])
    log("=== Chaque signal seul (15 séances), puis les trois autres sans lui")
    lab = {'st': 'supertrend adaptatif haussier', 'obv': 'OBV au plus haut de 20 séances', 'osc': 'RSI qui remonte depuis 40',
           'rs': 'force relative au-dessus de 0'}
    for nm in keys:
        S4(f"{lab[nm]} seul", M[nm])
    for nm in keys:
        S4(f"les trois autres, sans {lab[nm]}", M[f'sans_{nm}'])
    log("=== Avec le 🎯 : les signaux améliorent-ils le moment d'entrée dans la zone ?")
    S4("zone du 🎯 ET les 4 signaux", zone & M['n4_15'])
    S4("zone du 🎯 ET 3 signaux au moins", zone & M['n3_15'])
    S4("zone du 🎯 SANS 3 signaux", zone & ~M['n3_15'])
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
