"""Détecter le départ plus tôt (04/11/2026) : signaux journaliers contre le 📣 de la semaine, sur les cours journaliers Yahoo (ouverture,
plus haut, plus bas, clôture, volume) des sociétés de l'étude longue, 2000-2026. Lancé par « Recherche (à la demande) » (script
hausse_tot.py), environ 4 minutes.

Signaux du jour (achat à l'ouverture du lendemain) :
- bond du jour : séance à +5 % ou plus sur 3 fois le volume moyen de 50 séances, clôture dans la moitié haute de la séance (variantes :
  +8 %, 5 fois le volume, nouveau plus haut d'un an sur 2 fois le volume, sans condition de tendance) ;
- gap achetable (Kacher et Morales) : ouverture au-dessus du plus haut de la veille d'au moins 0,75 fois la variation moyenne (ATR 40),
  volume ≥ 1,5 fois la moyenne, clôture au-dessus de l'ouverture ; gap de 4 % ou plus sur 3 fois le volume ;
- pocket pivot (Kacher et Morales) : séance de hausse dont le volume dépasse celui de chaque séance de baisse des 10 dernières, cours au
  plus 5 % au-dessus de sa moyenne 10 séances, moyenne 50 séances montante, à moins de 25 % du plus haut de l'année ; variante dans une
  base serrée (20 séances dans 15 %) avant la cassure.
Tendance : cours au-dessus de la moyenne 200 séances, 50 au-dessus de 200. Référence : le 📣 de la semaine (semaine à +8 % sur 3 fois le
volume moyen de l'année, ou 2 fois au plus haut de l'année, en tendance), acheté à l'ouverture qui suit la clôture du vendredi.
Mesure : écart avec la moyenne des sociétés de l'ouverture du lendemain à 5, 20, 60, 125 et 250 séances, une entrée par société et par
semestre, t regroupé par mois, trois périodes ; avance sur le 📣 de la semaine et part de la hausse prise avant lui.
"""
import time

import numpy as np
import pandas as pd

import figures_bougies as FB

log, shift, sma, dedup = FB.log, FB.shift, FB.sma, FB.dedup


def roll(A, k, how, minp=None):
    df = pd.DataFrame(A.T)
    r = df.rolling(k, min_periods=minp or k)
    return (r.max() if how == 'max' else r.min() if how == 'min' else r.mean()).values.T.astype(np.float32)


def stats(lab, M, EX, RAW, months, yrs):
    out, per = [], ''
    for h, X in EX.items():
        ii, tt = np.where(M & np.isfinite(X))
        if len(ii) < 40:
            out.append(f"{h} j : trop peu ({len(ii)})")
            continue
        e = X[ii, tt]
        g = pd.Series(e).groupby(months[tt]).mean()
        tv = g.mean() / (g.std(ddof=1) / np.sqrt(len(g))) if len(g) > 10 else np.nan
        out.append(f"{h} j {e.mean() * 100:+5.1f} (t {tv:4.1f})")
        if h == 125:
            r = RAW[ii, tt]
            big, crash, beat = np.mean(r >= .5) * 100, np.mean(r <= -.25) * 100, np.mean(e > 0) * 100
            pp = []
            for a, b in ((2000, 2009), (2009, 2018), (2018, 2027)):
                m = (yrs[tt] >= a) & (yrs[tt] < b)
                pp.append(f"{e[m].mean() * 100:+5.1f}" if m.sum() >= 25 else "  ·  ")
            per = f" | 6 mois : bat la moyenne {beat:3.0f} %, ≥ +50 % {big:4.1f} %, chutes {crash:4.1f} % [{' / '.join(pp)}]"
    log(f"  {lab:58s} {int(M.sum()):6d} cas | " + " · ".join(out) + per)


def main():
    t0 = time.time()
    sec = FB.universe()
    D = FB.download(list(sec))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates, cols = D['Close'].index, list(D['Close'].columns)
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    log(f"téléchargé en {time.time() - t0:.0f} s : {len(cols)} sociétés, {len(dates)} séances ({dates[0].date()} → {dates[-1].date()})")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0)
        C1, H1 = shift(C, 1), shift(H, 1)
        TR = np.fmax(H - L, np.fmax(np.abs(H - C1), np.abs(L - C1)))
        ATR = shift(roll(np.where(ok, TR, np.nan), 40, 'mean', 30), 1)
        Vn = np.where(ok, V, np.nan)
        vol50 = shift(roll(Vn, 50, 'mean', 40), 1)
        ret1 = C / C1 - 1
        m10, m50, m200 = roll(C, 10, 'mean'), roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        hi252 = shift(roll(C, 252, 'max', 200), 1)
        downv = np.where(ok & (C < C1), V, 0).astype(np.float32)
        maxdown10 = shift(roll(downv, 10, 'max'), 1)
        rng20 = shift(roll(np.where(ok, H, np.nan), 20, 'max', 18), 1) / shift(roll(np.where(ok, L, np.nan), 20, 'min', 18), 1) - 1
        upper = (C - L) >= .5 * (H - L)
        S = {
            'bond du jour : +5 % sur 3 fois le volume, en tendance': ok & (ret1 >= .05) & (V >= 3 * vol50) & upper & trend,
            '  … +8 %': ok & (ret1 >= .08) & (V >= 3 * vol50) & upper & trend,
            '  … 5 fois le volume': ok & (ret1 >= .05) & (V >= 5 * vol50) & upper & trend,
            '  … sans condition de tendance': ok & (ret1 >= .05) & (V >= 3 * vol50) & upper,
            'bond du jour au plus haut de l\'année, 2 fois le volume': ok & (ret1 >= .05) & (V >= 2 * vol50) & (C >= hi252) & upper,
            'gap achetable (0,75 ATR, volume ×1,5), en tendance': ok & (O >= H1 + .75 * ATR) & (V >= 1.5 * vol50) & (C >= O) & trend,
            'gap de 4 % ou plus sur 3 fois le volume': ok & (O >= H1 * 1.04) & (V >= 3 * vol50) & (C >= O),
            'pocket pivot, en tendance': ok & (C > C1) & (V > maxdown10) & (C >= m10) & (C <= m10 * 1.05) & (m50 > shift(m50, 5))
            & (C >= .75 * hi252) & trend,
            '  … dans une base serrée, avant la cassure': ok & (C > C1) & (V > maxdown10) & (C >= m10) & (C <= m10 * 1.05)
            & (m50 > shift(m50, 5)) & (C >= .75 * hi252) & trend & (rng20 <= .15) & (C < hi252),
            'contrôle : séance à +2 % en tendance': ok & (ret1 >= .02) & trend,
            'contrôle : un jour quelconque en tendance': ok & trend,
        }
    del C1, H1, TR, downv, rng20, upper
    # 📣 de la semaine, daté du dernier jour de la semaine (acheté à l'ouverture suivante, le lundi)
    Cw = D['Close'].resample('W-FRI').last()
    Vw = D['Volume'].where(D['Volume'] > 0).resample('W-FRI').sum(min_count=1)
    rw = Cw / Cw.shift(1) - 1
    vavg = Vw.shift(1).rolling(52, min_periods=40).mean()
    hiw = Cw.shift(1).rolling(52, min_periods=40).max()
    tw = (Cw.rolling(10).mean() > Cw.rolling(40).mean()) & (Cw > Cw.rolling(40).mean())
    BW = ((rw >= .08) & ((Vw >= 3 * vavg) | ((Vw >= 2 * vavg) & (Cw >= hiw))) & tw).fillna(False)
    lastday = pd.Series(np.arange(len(dates)), index=dates).resample('W-FRI').last()
    BWd = np.zeros(C.shape, dtype=bool)
    for wk, j in lastday.dropna().astype(int).items():
        if wk in BW.index:
            BWd[:, j] = BW.loc[wk].reindex(cols).fillna(False).values
    S['📣 de la semaine (référence, acheté le lundi)'] = BWd
    # rendements de l'ouverture du lendemain
    EX, RAW = {}, None
    O1n = shift(O, -1)
    for h in (5, 20, 60, 125, 250):
        with np.errstate(all='ignore'):
            r = shift(C, -h) / O1n - 1
        r = np.where((r > -.9) & (r < 5), r, np.nan).astype(np.float32)
        mu = np.nanmean(r, 0)
        mu[np.isfinite(r).sum(0) < 30] = np.nan
        EX[h] = r - mu[None, :]
        EX[h][:, yrs < 2000] = np.nan
        if h == 125:
            RAW = r
    log("\n=== 1. Écart avec la moyenne des sociétés (points de %), achat à l'ouverture du lendemain, une entrée par société et par semestre")
    for k, M in S.items():
        stats(k, dedup(M, 125), EX, RAW, months, yrs)
    # 2. avance sur le 📣 de la semaine
    log("\n=== 2. Avance sur le 📣 de la semaine : semaines 📣 précédées d'un signal du jour dans les 10 séances")
    bw_i, bw_t = np.where(BWd & (yrs[None, :] >= 2000))
    Onext = shift(O, -1)
    for k in ('bond du jour : +5 % sur 3 fois le volume, en tendance', '  … sans condition de tendance',
              'gap achetable (0,75 ATR, volume ×1,5), en tendance', 'pocket pivot, en tendance'):
        M = S[k]
        leads, gains = [], []
        for i, t in zip(bw_i, bw_t):
            w = np.where(M[i, max(0, t - 9):t + 1])[0]
            if len(w):
                d = max(0, t - 9) + w[0]
                leads.append(t - d)
                a, b = Onext[i, d], Onext[i, t]
                if np.isfinite(a) and np.isfinite(b) and a > 0:
                    gains.append(b / a - 1)
        n = len(bw_i)
        log(f"  {k:58s} {len(leads) / max(n, 1) * 100:3.0f} % des 📣 ({len(leads)} sur {n}) ; avance médiane {np.median(leads) if leads else np.nan:.0f} séances ;"
            f" hausse prise avant l'achat du lundi : moyenne {np.mean(gains) * 100 if gains else np.nan:+.1f} %, médiane {np.median(gains) * 100 if gains else np.nan:+.1f} %")
    # 3. le signal du jour qui ne devient pas un 📣 (la semaine finit sous +8 %) : que vaut-il ?
    wk_of = pd.Series(np.arange(len(dates)), index=dates).resample('W-FRI').transform('max').values
    log("\n=== 3. Bond du jour selon la fin de la semaine")
    M = S['bond du jour : +5 % sur 3 fois le volume, en tendance']
    became = np.zeros_like(M)
    ii, tt = np.where(M)
    for i, t in zip(ii, tt):
        j = wk_of[t]
        became[i, t] = BWd[i, j]
    stats('bond du jour qui devient un 📣 à la fin de la semaine', dedup(M & became, 125), EX, RAW, months, yrs)
    stats('bond du jour qui ne devient pas un 📣', dedup(M & ~became, 125), EX, RAW, months, yrs)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
