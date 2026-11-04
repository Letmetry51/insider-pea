"""Suite de hausse_tot2.py (04/11/2026) : le « bond du jour » (séance à +8 % ou plus sur 5 fois le volume moyen de 50 séances, en
tendance, clôture dans la moitié haute de la séance) fait mieux que le 📣 de la semaine. Solidité des réglages (hausse, volume, tendance,
clôture), et comparaison à égalité : pour les mêmes sociétés, achat le lendemain du bond ou le lundi qui suit la semaine. Lancé par
« Recherche (à la demande) » (script hausse_tot3.py), environ 4 minutes."""
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT

log, shift, dedup, roll = FB.log, FB.shift, FB.dedup, HT.roll


def excess(C, O, yrs, h, start_shift=1):
    """écart avec la moyenne des sociétés, de l'ouverture de t + start_shift à la clôture de t + h"""
    with np.errstate(all='ignore'):
        r = shift(C, -h) / shift(O, -start_shift) - 1
    r = np.where((r > -.9) & (r < 5), r, np.nan).astype(np.float32)
    mu = np.nanmean(r, 0)
    mu[np.isfinite(r).sum(0) < 30] = np.nan
    e = r - mu[None, :]
    e[:, yrs < 2000] = np.nan
    return e, r


def line(lab, M, E, R, months, yrs):
    ii, tt = np.where(M & np.isfinite(E))
    if len(ii) < 40:
        log(f"  {lab:52s} trop peu ({len(ii)})")
        return
    e = E[ii, tt]
    g = pd.Series(e).groupby(months[tt]).mean()
    tv = g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))
    pp = []
    for a, b in ((2000, 2009), (2009, 2018), (2018, 2027)):
        m = (yrs[tt] >= a) & (yrs[tt] < b)
        pp.append(f"{e[m].mean() * 100:+5.1f}" if m.sum() >= 25 else "  ·  ")
    r = R[ii, tt]
    log(f"  {lab:52s} {len(ii):5d} cas · 6 mois {e.mean() * 100:+5.1f} (t {tv:4.1f}) [{' / '.join(pp)}] · ≥ +50 % {np.mean(r >= .5) * 100:4.1f} %"
        f" · chutes {np.mean(r <= -.25) * 100:4.1f} %")


def main():
    t0 = time.time()
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates, cols = D['Close'].index, list(D['Close'].columns)
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    log(f"téléchargé en {time.time() - t0:.0f} s : {len(cols)} sociétés, {len(dates)} séances")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0)
        ret1 = C / shift(C, 1) - 1
        vol50 = shift(roll(np.where(V > 0, V, np.nan).astype(np.float32), 50, 'mean', 40), 1)
        vx = V / vol50
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        clv = (C - L) / (H - L)
        hi252 = shift(roll(C, 252, 'max', 200), 1)
    E6, R6 = excess(C, O, yrs, 125)
    log("\n=== 1. Réglages du bond du jour (6 mois, une entrée par société et par semestre)")
    for r_ in (.06, .08, .10):
        for v_ in (3, 4, 5, 7):
            M = ok & (ret1 >= r_) & (vx >= v_) & (clv >= .5) & trend
            line(f"+{r_ * 100:.0f} % sur {v_} fois le volume", dedup(M, 125), E6, R6, months, yrs)
    base = ok & (ret1 >= .08) & (vx >= 5)
    line("+8 % sur 5 fois, sans condition de tendance", dedup(base & (clv >= .5), 125), E6, R6, months, yrs)
    line("+8 % sur 5 fois, en tendance, clôture quelconque", dedup(base & trend, 125), E6, R6, months, yrs)
    line("+8 % sur 5 fois, en tendance, clôture dans le quart haut", dedup(base & trend & (clv >= .75), 125), E6, R6, months, yrs)
    line("+8 % sur 5 fois, en tendance, au plus haut de l'année", dedup(base & trend & (clv >= .5) & (C >= hi252), 125), E6, R6, months, yrs)
    line("+8 % sur 5 fois, en tendance, sous le plus haut de l'année", dedup(base & trend & (clv >= .5) & (C < hi252), 125), E6, R6, months,
         yrs)
    line("+8 % sur 5 fois, hors tendance", dedup(base & ~trend & (clv >= .5), 125), E6, R6, months, yrs)
    A = dedup(base & trend & (clv >= .5), 125)
    # 2. à égalité : mêmes événements, achat le lendemain ou le lundi qui suit la semaine du bond
    wk = pd.Series(dates, index=dates).dt.to_period('W-FRI')
    wid = pd.factorize(wk)[0]
    last_of = {}
    for t in range(len(dates)):
        last_of[wid[t]] = t
    endw = np.array([last_of[w] for w in wid])
    Cd, Vd = pd.DataFrame(C.T, index=dates, columns=cols), pd.DataFrame(np.where(V > 0, V, np.nan).T, index=dates, columns=cols)
    Cw, Vw = Cd.resample('W-FRI').last(), Vd.resample('W-FRI').sum(min_count=1)
    vavg, hiw = Vw.shift(1).rolling(52, min_periods=40).mean(), Cw.shift(1).rolling(52, min_periods=40).max()
    tw = (Cw.rolling(10).mean() > Cw.rolling(40).mean()) & (Cw > Cw.rolling(40).mean())
    BW = ((Cw / Cw.shift(1) - 1 >= .08) & ((Vw >= 3 * vavg) | ((Vw >= 2 * vavg) & (Cw >= hiw))) & tw).fillna(False)
    wpos = {p: j for j, p in enumerate(pd.PeriodIndex(BW.index, freq='W-FRI'))}
    BWa = BW.reindex(columns=cols).values.T
    ii, tt = np.where(A & (yrs[None, :] >= 2000))
    e_next, e_mon, cap, became, lead = [], [], [], [], []
    for i, t in zip(ii, tt):
        e = endw[t]
        j = wpos.get(wk.iloc[t], -1)
        became.append(bool(BWa[i, j]) if j >= 0 else False)
        lead.append(e - t)
    became = np.array(became, dtype=bool)
    # rendements à 6 mois depuis l'ouverture qui suit la fin de la semaine du bond (le lundi) pour les mêmes sociétés
    Em, _ = excess(C, O, yrs, 125)          # depuis l'ouverture qui suit le jour d'indice : pris à e (fin de semaine) ci-dessous
    O1 = shift(O, -1)
    for i, t in zip(ii, tt):
        e = endw[t]
        a, b = O1[i, t], O1[i, e]
        cap.append(b / a - 1 if np.isfinite(a) and np.isfinite(b) and a > 0 else np.nan)
        e_next.append(E6[i, t])
        e_mon.append(Em[i, e] if e + 126 < len(dates) else np.nan)
    cap, e_next, e_mon = np.array(cap), np.array(e_next), np.array(e_mon)
    ok2 = np.isfinite(e_next) & np.isfinite(e_mon)
    log("\n=== 2. Bond du jour (+8 % sur 5 fois, en tendance) : à égalité, achat le lendemain ou le lundi qui suit la semaine")
    log(f"  {len(ii)} bonds ; {became.mean() * 100:.0f} % font un 📣 de la semaine ; séances jusqu'à la fin de la semaine : médiane {np.median(lead):.0f}")
    log(f"  hausse entre l'achat du lendemain et celui du lundi : moyenne {np.nanmean(cap) * 100:+.1f} %, médiane {np.nanmedian(cap) * 100:+.1f} %"
        f" (devenus 📣 : {np.nanmean(cap[became]) * 100:+.1f} %, les autres : {np.nanmean(cap[~became]) * 100:+.1f} %)")
    log(f"  écart à 6 mois, mêmes sociétés : acheté le lendemain {np.mean(e_next[ok2]) * 100:+.1f}, acheté le lundi {np.mean(e_mon[ok2]) * 100:+.1f}"
        f" (différence {np.mean(e_next[ok2] - e_mon[ok2]) * 100:+.1f}, t {np.mean(e_next[ok2] - e_mon[ok2]) / (np.std(e_next[ok2] - e_mon[ok2], ddof=1) / np.sqrt(ok2.sum())):.1f})")
    for lab, m in (('devenus 📣', became), ('pas devenus 📣', ~became)):
        k = ok2 & m
        log(f"    {lab:16s} {k.sum():5d} : lendemain {np.mean(e_next[k]) * 100:+5.1f}, lundi {np.mean(e_mon[k]) * 100:+5.1f}")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
