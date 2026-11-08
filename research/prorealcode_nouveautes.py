"""Nouveautés de la bibliothèque ProRealCode (08/11/2026 : codes publiés du 29/10 au 06/11/2026) qui peuvent servir une sélection
hebdomadaire d'actions européennes pour le PEA. La place de marché (market.prorealcode.com) vend surtout des systèmes automatiques
en séance sur indices et devises (DAX, CAC 40 en 15 minutes, Nasdaq en 10 minutes, ouverture asiatique du Forex), des indicateurs
de tendance génériques et des formations : rien d'applicable à un PEA tenu 6 mois. Le reste de la bibliothèque (retournements,
essoufflement, figures, chandeliers, harmoniques, consolidations, squeeze, stops suiveurs type SuperTrend, saisonnalité, humeur
du marché) a déjà été testé : voir research/README.md.

Même mesure que hausse_tot5.py : cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant, mêmes
sociétés pour la référence), achat à l'ouverture du lendemain, écart avec la moyenne des sociétés à 1, 3, 6 et 12 mois, une
entrée par société et par semestre, t regroupé par mois, trois périodes 2000-2008 / 2009-2017 / 2018-2026. Lancé par
« Recherche (à la demande) » (script prorealcode_nouveautes.py), environ 8 minutes.

1. « Participation-Adjusted Momentum » (06/11/2026) : hausse sur 12 mois sans le dernier, chaque séance pondérée par son volume
   relatif. Dans la zone du 🎯 (en tendance, +60 à +200 % sur 12 mois), la part de la hausse faite sur gros volume (momentum pondéré
   moins momentum simple, rang du jour) ajoute-t-elle quelque chose ? Tiers fort contre tiers faible.
2. « Alpha Regime Dashboard » (05/11/2026) : marché en tendance, en transition ou agité (rendement d'efficacité de Kaufman sur 60
   séances de la moyenne des sociétés, tiers de son historique). Les entrées de la zone du 🎯 font-elles mieux que la moyenne des
   sociétés dans un régime plutôt qu'un autre, dans chaque période ?
3. « Monthly Anchored VWAP », « VWAP Range Breakout » (29/10 et 04/11/2026) : prix moyen pondéré par les volumes depuis le bond du
   jour (📣 du jour actuel : +8 % sur 5 fois le volume moyen de 50 séances, clôture dans la moitié haute, en tendance). 20 et 40
   séances après le bond : cours au-dessus ou au-dessous de ce prix moyen, comparé au critère déjà étudié « bond tenu » (cours
   au-dessus de la clôture du bond).
"""
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3
from hausse_tot5 import stats4

log, shift, dedup, roll = FB.log, FB.shift, FB.dedup, HT.roll


def day_rank(X, M):
    """Rang du jour (0 à 1) de X parmi les sociétés où M est vrai."""
    R = pd.DataFrame(np.where(M, X, np.nan).T).rank(axis=1, pct=True).values.T
    return R.astype(np.float32)


def main():
    t0 = time.time()
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates = D['Close'].index
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    N, T = C.shape
    log(f"téléchargé en {time.time() - t0:.0f} s : {N} sociétés, {T} séances")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0)
        C1 = shift(C, 1)
        ret1 = C / C1 - 1
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        clv = (C - L) / (H - L)
        mom = shift(C, 21) / shift(C, 252) - 1
        lr = np.where(ok, np.log(C / C1), np.nan).astype(np.float32)
        lr = np.where(np.abs(lr) < np.log(2.5), lr, np.nan).astype(np.float32)   # sauts non ajustés écartés
        zone = ok & trend & (mom >= .6) & (mom <= 2.0)
    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r

    log("\n=== 1. Momentum ajusté de la participation (« Participation-Adjusted Momentum ») dans la zone du 🎯")
    with np.errstate(all='ignore'):
        rv = np.clip(Vp / roll(Vp, 252, 'mean', 200), 0, 5).astype(np.float32)   # volume relatif à sa moyenne d'un an, plafonné à 5
        w_mean = roll(np.where(np.isfinite(lr), lr * rv, np.nan).astype(np.float32), 231, 'mean', 180)
        v_mean = roll(np.where(np.isfinite(lr), rv, np.nan).astype(np.float32), 231, 'mean', 180)
        s_mean = roll(lr, 231, 'mean', 180)
        # même échelle que le momentum simple : rendement moyen pondéré × 231 séances, sur t-252 à t-21
        spread = shift((w_mean / v_mean - s_mean) * 231, 21)
    R = day_rank(spread, zone & np.isfinite(spread))
    stats4("zone du 🎯 : toutes les entrées", dedup(zone, 125), EX, RAW, months, yrs)
    stats4("  hausse faite sur gros volume (tiers fort)", dedup(zone & (R >= 2 / 3), 125), EX, RAW, months, yrs)
    stats4("  tiers du milieu", dedup(zone & (R > 1 / 3) & (R < 2 / 3), 125), EX, RAW, months, yrs)
    stats4("  hausse faite sur petit volume (tiers faible)", dedup(zone & (R <= 1 / 3), 125), EX, RAW, months, yrs)
    with np.errstate(all='ignore'):
        Rm = day_rank(mom, zone & np.isfinite(mom))
    stats4("  contrôle : momentum simple, tiers fort de la zone", dedup(zone & (Rm >= 2 / 3), 125), EX, RAW, months, yrs)
    stats4("  momentum fort ET hausse sur gros volume", dedup(zone & (Rm >= 2 / 3) & (R >= 2 / 3), 125), EX, RAW, months, yrs)
    stats4("  momentum fort ET hausse sur petit volume", dedup(zone & (Rm >= 2 / 3) & (R <= 1 / 3), 125), EX, RAW, months, yrs)

    log("\n=== 2. Régime du marché (« Alpha Regime Dashboard ») : tendance, transition ou agité")
    with np.errstate(all='ignore'):
        mret = np.nanmean(np.where(np.isfinite(ret1) & (np.abs(ret1) < .5), ret1, np.nan), 0)
        mret[np.isfinite(ret1).sum(0) < 30] = np.nan
        M = np.exp(np.nancumsum(np.log1p(np.nan_to_num(mret))))
        dM = np.abs(np.diff(M, prepend=M[0]))
        path = pd.Series(dM).rolling(60, min_periods=55).sum().values
        er = np.abs(M - shift(M[None, :], 60)[0]) / path
        up = M > shift(M[None, :], 60)[0]
        valid = np.isfinite(er) & (yrs >= 2000)
        lo, hi = np.nanquantile(er[valid], [1 / 3, 2 / 3])
    log(f"  rendement d'efficacité sur 60 séances : tiers à {lo:.2f} et {hi:.2f}")
    regimes = {
        'tendance haussière': valid & (er >= hi) & up,
        'tendance baissière': valid & (er >= hi) & ~up,
        'transition': valid & (er > lo) & (er < hi),
        'agité': valid & (er <= lo),
    }
    for name, g in regimes.items():
        log(f"  {name} : {g.sum()} séances ({g[yrs >= 2000].mean() * 100:.0f} %)")
    for name, g in regimes.items():
        stats4(f"zone du 🎯, marché en {name}", dedup(zone & g[None, :], 125), EX, RAW, months, yrs)

    log("\n=== 3. Prix moyen pondéré par les volumes depuis le 📣 bond du jour (« Anchored VWAP »)")
    with np.errstate(all='ignore'):
        bond = dedup(ok & (ret1 >= .08) & (vx >= 5) & (clv >= .5) & trend, 125)
        tp = np.where(ok, (H + L + C) / 3, np.nan)
        pv = np.nancumsum(np.nan_to_num(tp * V), 1)
        vv = np.nancumsum(np.nan_to_num(np.where(ok, V, 0)), 1)
    ii, tt = np.where(bond)
    log(f"  {len(ii)} bonds du jour en tendance")
    stats4("bond du jour (achat le lendemain, référence)", bond, EX, RAW, months, yrs)
    for k in (20, 40):
        A = {key: np.zeros_like(bond) for key in ('tous', 'dessus', 'dessous', 'tenu', 'perdu', 'dessus_perdu', 'dessous_tenu')}
        for i, t in zip(ii, tt):
            u = t + k
            if u >= T or not np.isfinite(C[i, u]):
                continue
            base_pv = pv[i, t - 1] if t > 0 else 0.0
            base_vv = vv[i, t - 1] if t > 0 else 0.0
            vol = vv[i, u] - base_vv
            if not vol > 0:
                continue
            vwap = (pv[i, u] - base_pv) / vol
            above, held = C[i, u] > vwap, C[i, u] > C[i, t]
            A['tous'][i, u] = True
            A['dessus' if above else 'dessous'][i, u] = True
            A['tenu' if held else 'perdu'][i, u] = True
            if above and not held:
                A['dessus_perdu'][i, u] = True
            if held and not above:
                A['dessous_tenu'][i, u] = True
        log(f"  — {k} séances après le bond (achat le lendemain)")
        stats4(f"    tous les bonds, {k} séances après", A['tous'], EX, RAW, months, yrs)
        stats4("    cours au-dessus du prix moyen depuis le bond", A['dessus'], EX, RAW, months, yrs)
        stats4("    cours au-dessous du prix moyen depuis le bond", A['dessous'], EX, RAW, months, yrs)
        stats4("    bond tenu (au-dessus de la clôture du bond)", A['tenu'], EX, RAW, months, yrs)
        stats4("    bond perdu", A['perdu'], EX, RAW, months, yrs)
        stats4("    au-dessus du prix moyen mais bond perdu", A['dessus_perdu'], EX, RAW, months, yrs)
        stats4("    bond tenu mais au-dessous du prix moyen", A['dessous_tenu'], EX, RAW, months, yrs)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
