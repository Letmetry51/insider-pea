"""Les secteurs en tendance aux États-Unis annoncent-ils la hausse des mêmes secteurs en Europe ? (26/11/2026, François : « Est-ce
qu'il serait pertinent de faire un "follow the smartmoney" aux usa des plus grands influenceurs financier, de déterminer des secteurs
en tendance pour ensuite faire une reco d'achat en Europe ? L'idée serait d'anticiper des mouvements de hausse à venir »).

Cœur testable de l'idée : un secteur qui monte d'abord aux États-Unis (là où l'argent « averti » se placerait le premier) monte-t-il
ensuite en Europe, au-delà de ce que la force du secteur en Europe montre déjà ? Force de chaque secteur américain chaque semaine :
fonds sectoriels SPDR (XLK, XLI, XLF, XLV, XLY, XLP, XLE, XLB, XLU ; XLRE et XLC quand ils existent, iShares IYR et IYZ avant), sur
4, 13 et 26 semaines face au S&P 500 (SPY), cours ajustés des dividendes (Yahoo), clôture américaine de la veille (la clôture du
vendredi tombe après celle de l'Europe : rien de connu trop tôt). Secteurs européens : sociétés de backtest/_long.py (secteurs
Yahoo, mêmes noms que les fonds : sociétés encore cotées, biais du survivant), règles de backtest/_selection_sim2.py.

1. Avance des États-Unis : 4, 13 et 26 semaines suivantes des secteurs européens face à la moyenne des sociétés, selon la force du
   même secteur aux États-Unis (3 plus forts moins 3 plus faibles) ; puis ce que la force américaine ajoute à la force européenne
   du secteur (régression des deux, semaine par semaine, sur des semaines espacées de la durée suivie : coefficient moyen et t).
2. Sélection simulée 1998-2026 (4 🎯 + 1 📣, 26 semaines, frais 0,3 % par sens ; copie de cycle_secteurs.py) : secteurs forts aux
   États-Unis d'abord ; 🎯 sans les secteurs faibles aux États-Unis ; 🎯 seulement dans les secteurs forts aux États-Unis ; avec la
   force sur 13 et 26 semaines (comme l'onglet Secteurs) et sur 4 semaines (anticiper). Pour information : liste des 4 mieux
   notées des 3 secteurs les plus forts aux États-Unis.

Règle fixée avant le calcul (méthode de l'outil) : une variante ne remplace la règle actuelle que si elle fait mieux dans chacune
des périodes 1998-2008, 2009-2017 et 2018-2026, avec t ≥ 3 ; sinon, résultat documenté (research/README.md et aide).
Lancé par « Recherche (à la demande) » (script us_secteurs.py), environ 6 minutes.
"""
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

import cycle_secteurs as CS
import figures_bougies as FB
import proba as PB

log = FB.log
ERAS3 = CS.ERAS3
FONDS = {'Technology': ['XLK'], 'Industrials': ['XLI'], 'Financial Services': ['XLF'], 'Healthcare': ['XLV'],
         'Consumer Cyclical': ['XLY'], 'Consumer Defensive': ['XLP'], 'Energy': ['XLE'], 'Basic Materials': ['XLB'],
         'Utilities': ['XLU'], 'Real Estate': ['XLRE', 'IYR'], 'Communication Services': ['XLC', 'IYZ']}


def us_prices(dates):
    """Clôture ajustée de chaque fonds la veille de chaque date de la grille hebdomadaire (NaN avant sa création)."""
    import yfinance as yf
    tick = sorted({t for v in FONDS.values() for t in v} | {'SPY'})
    raw = yf.download(tick, start='1998-01-01', auto_adjust=True, progress=False, threads=True)['Close']
    raw = raw.dropna(how='all').sort_index()
    idx = pd.DatetimeIndex([pd.Timestamp(date.fromisoformat(d) - timedelta(days=1)) for d in dates])
    out = raw.reindex(raw.index.union(idx)).ffill().reindex(idx)
    out.index = list(dates)
    first = {t: str(raw[t].first_valid_index().date()) if raw[t].first_valid_index() is not None else None for t in tick}
    log("fonds américains : " + ', '.join(f"{t} {first[t]}" for t in tick))
    return out


def us_strength(U, secs_eu, T, L):
    """S[s][t] : rendement du secteur américain sur L semaines moins celui du S&P 500 (fonds le plus récent quand il existe, sinon
    son prédécesseur : XLRE puis IYR, XLC puis IYZ)."""
    spy = U['SPY'].values.astype(float)
    S = {}
    for s, tk in FONDS.items():
        if s not in secs_eu:
            continue
        x = np.full(T, np.nan)
        for t in range(L, T):
            for k in tk:
                a, b = U[k].values[t], U[k].values[t - L]
                if np.isfinite(a) and np.isfinite(b) and b > 0:
                    x[t] = a / b - spy[t] / spy[t - L]
                    break
        S[s] = x
    return S


def fit_from(S, T, N, sidx, top=3):
    """FIT[i, t] : 1 secteur parmi les 3 plus forts aux États-Unis, -1 parmi les 3 plus faibles, 0 sinon."""
    FIT = np.zeros((N, T), np.int8)
    for t in range(T):
        v = [(S[s][t], s) for s in S if np.isfinite(S[s][t])]
        if len(v) < 8:
            continue
        v.sort()
        for _, s in v[-top:]:
            FIT[sidx[s], t] = 1
        for _, s in v[:top]:
            FIT[sidx[s], t] = -1
    return FIT


def main():
    t0 = time.time()
    G = PB.load()
    t1997, T, ERAS, retw, okn, secs, N = (G[k] for k in ('t1997', 'T', 'ERAS', 'retw', 'okn', 'secs', 'N'))
    dates = G['dates']
    names = sorted(set(secs) - {'', '?', 'nan'})
    log(f"données prêtes en {time.time() - t0:.0f} s ; secteurs européens : " + ', '.join(
        f"{s} {int((secs == s).sum())}" for s in names))
    sidx = {s: np.where(secs == s)[0] for s in names}
    U = us_prices(dates)
    with np.errstate(all='ignore'):
        Lr = np.log1p(np.where(np.isfinite(retw), retw, 0.0))
        C = np.concatenate([np.zeros((Lr.shape[0], 1)), np.cumsum(Lr, 1)], 1)

    def eu_sector(t, H):
        """Rendement des H semaines suivantes de chaque secteur européen face à la moyenne des sociétés (sociétés présentes à t)."""
        ok = okn[:, t]
        fw = np.clip(np.expm1(C[:, t + H + 1] - C[:, t + 1]), -.95, 5)
        m = np.nanmean(fw[ok])
        out = {}
        for s, ix in sidx.items():
            k = ix[ok[ix] & np.isfinite(fw[ix])]
            if len(k) >= 5:
                out[s] = np.nanmean(fw[k]) - m
        return out

    def eu_strength(t, L):
        ok = okn[:, t]
        with np.errstate(all='ignore'):
            r = np.clip(np.expm1(C[:, t + 1] - C[:, t + 1 - L]), -.9, 5)
        m = np.nanmean(r[ok])
        out = {}
        for s, ix in sidx.items():
            k = ix[ok[ix] & np.isfinite(r[ix])]
            if len(k) >= 5:
                out[s] = np.nanmean(r[k]) - m
        return out

    def era_of(t):
        for el, a, b in ERAS:
            if el in ERAS3 and a <= t < b:
                return el
        return None

    def tstat(x):
        x = np.asarray([v for v in x if np.isfinite(v)])
        return (x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else np.nan, x

    # 1. Avance des États-Unis
    log("\n1. Secteurs européens dans les semaines suivantes selon la force du même secteur aux États-Unis "
        "(3 plus forts − 3 plus faibles, points de %, semaines espacées de la durée suivie)")
    SL = {L: us_strength(U, names, T, L) for L in (4, 13, 26)}
    start = next(t for t in range(t1997, T) if sum(np.isfinite(SL[26][s][t]) for s in SL[26]) >= 9)
    log(f"  première semaine avec 9 secteurs américains : {dates[start]}")
    for L in (4, 13, 26):
        for H in (4, 13, 26):
            diffs, fm, per = [], [], {el: [] for el in ERAS3}
            for t in range(max(start, L + 1), T - H - 1, H):
                fwd = eu_sector(t, H)
                us = {s: SL[L][s][t] for s in SL[L] if np.isfinite(SL[L][s][t]) and s in fwd}
                if len(us) < 8:
                    continue
                order = sorted(us, key=lambda s: us[s])
                d = np.mean([fwd[s] for s in order[-3:]]) - np.mean([fwd[s] for s in order[:3]])
                diffs.append(d)
                el = era_of(t)
                if el:
                    per[el].append(d)
                eu = eu_strength(t, L)
                ks = [s for s in us if s in eu]
                if len(ks) >= 8:
                    zu = np.array([us[s] for s in ks])
                    ze = np.array([eu[s] for s in ks])
                    y = np.array([fwd[s] for s in ks])
                    zu, ze = (zu - zu.mean()) / (zu.std() or 1), (ze - ze.mean()) / (ze.std() or 1)
                    X = np.column_stack([np.ones(len(ks)), zu, ze])
                    b = np.linalg.lstsq(X, y, rcond=None)[0]
                    fm.append((b[1], b[2]))
            tv, x = tstat(diffs)
            fm = np.array(fm) if fm else np.full((1, 2), np.nan)
            tu, _ = tstat(fm[:, 0])
            te, _ = tstat(fm[:, 1])
            log(f"  force sur {L:2d} sem., {H:2d} semaines suivantes : {x.mean() * 100:+5.1f} (t {tv:4.1f}) · "
                + ' · '.join(f"{el} {np.mean(per[el]) * 100:+5.1f}" for el in ERAS3 if per[el])
                + f" | à force européenne égale : États-Unis {fm[:, 0].mean() * 100:+4.1f} (t {tu:4.1f}), "
                  f"Europe {fm[:, 1].mean() * 100:+4.1f} (t {te:4.1f}) par écart-type")

    # 2. Sélection simulée
    SEL = G['SEL']
    ref = CS.weekly_slots(G, lambda t: SEL.get(t, []))

    def cagr_era(R):
        out = []
        for el, a, b in ERAS:
            if el in ERAS3:
                x = R[a - t1997:min(b, T - 1) - t1997]
                out.append(f"{el} {(np.prod(1 + x) ** (52 / len(x)) - 1) * 100:+.1f}")
        eq = np.cumprod(1 + R)
        dd = (eq / np.maximum.accumulate(eq) - 1).min()
        return f"{(eq[-1] ** (52 / len(R)) - 1) * 100:+.1f} %/an (pire baisse {dd * 100:.0f} %) · " + ' · '.join(out)

    def vs_ref(lab, R, verdict=True):
        dd = R - ref
        out, ok_all = [], True
        for el, a, b in ERAS:
            if el not in ERAS3:
                continue
            x = dd[a - t1997:min(b, T - 1) - t1997]
            out.append(f"{el} {x.mean() * 52 * 100:+5.1f}")
            ok_all &= x.mean() > 0
        blk = np.array([dd[k:k + 26].sum() for k in range(0, len(dd) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        v = (' → BAT LA RÈGLE ACTUELLE' if ok_all and tv >= 3 else ' → rejetée') if verdict else ''
        log(f"  {lab:58s} {cagr_era(R)}\n  {'':58s} écart : {' · '.join(out)} pts/an, t {tv:4.1f}{v}")

    log(f"\n2. Sélection simulée (4 🎯 + 1 📣, 26 semaines, frais compris), secteurs américains connus dès {dates[start]}")
    log(f"  {'règle actuelle':58s} {cagr_era(ref)}")
    note, trend, mom, v52 = (G[k] for k in ('note', 'trend', 'mom', 'v52'))
    for lab_L, S in (('13 et 26 semaines', {s: (SL[13][s] + SL[26][s]) / 2 for s in SL[13]}), ('4 semaines', SL[4])):
        FIT = fit_from(S, T, N, sidx)
        fits = [FIT[i, t] for t, s in SEL.items() if t >= start for i in s]
        log(f"\n  force américaine sur {lab_L} : sociétés de la règle actuelle dans un secteur fort aux États-Unis "
            f"{np.mean(np.array(fits) == 1) * 100:.0f} %, faible {np.mean(np.array(fits) == -1) * 100:.0f} %")
        pick = CS.make_pick(G, FIT)
        for mode, lab in (('prio', 'secteurs forts aux États-Unis d\'abord'),
                          ('sans_contre', '🎯 sans les secteurs faibles aux États-Unis'),
                          ('portes_seuls', '🎯 seulement dans les secteurs forts aux États-Unis')):
            vs_ref(lab + ' (' + lab_L + ')', CS.weekly_slots(G, lambda t, m=mode: pick(t, mode=m)))

        def us_list(t, F=FIT):
            M = okn[:, t] & trend[:, t] & (mom[:, t] >= .3) & (mom[:, t] <= 2) & ~(v52[:, t] >= .8) & (F[:, t] == 1)
            idx = np.where(M)[0]
            return idx[np.argsort(-np.nan_to_num(note[idx, t]))][:4].tolist()
        vs_ref("liste « États-Unis » (4 mieux notées des 3 secteurs forts)", CS.weekly_slots(G, us_list, n=4), verdict=False)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
