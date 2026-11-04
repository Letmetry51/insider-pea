"""Suite de hausse_tot.py (04/11/2026) : le 📣 repéré en cours de semaine. Chaque soir, semaine en cours comparée à la moyenne de
l'année avec un volume ramené au nombre de séances écoulées (2 séances : 2/5 du volume d'une semaine) : hausse depuis la clôture du
vendredi précédent ≥ +8 % sur 3 fois ce volume (ou 2 fois au plus haut de l'année), en tendance la semaine d'avant. Comparé au 📣 de la
semaine acheté le lundi : écart à 6 et 12 mois, avance, hausse prise en plus, et faux départs (semaine finie sans 📣). Variantes du bond
du jour : +8 % sur 5 fois le volume, bond confirmé le lendemain (clôture qui tient), deux séances cumulées. Lancé par « Recherche (à la
demande) » (script hausse_tot2.py), environ 4 minutes."""
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT

log, shift, dedup, roll, stats = FB.log, FB.shift, FB.dedup, HT.roll, HT.stats


def main():
    t0 = time.time()
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates, cols = D['Close'].index, list(D['Close'].columns)
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    nT = len(dates)
    log(f"téléchargé en {time.time() - t0:.0f} s : {len(cols)} sociétés, {nT} séances")
    # semaine de chaque séance, rang de la séance dans sa semaine, dernière séance de la semaine précédente
    wk = pd.Series(dates, index=dates).dt.to_period('W-FRI')
    wid = pd.factorize(wk)[0]
    first = np.r_[True, wid[1:] != wid[:-1]]
    rank = np.zeros(nT, dtype=int)
    for t in range(1, nT):
        rank[t] = 0 if first[t] else rank[t - 1] + 1
    prev_last = np.full(nT, -1)
    last_of = {}
    for t in range(nT):
        last_of[wid[t]] = t
    for t in range(nT):
        prev_last[t] = last_of.get(wid[t] - 1, -1)
    # volumes et clôtures hebdomadaires de référence (52 semaines précédentes)
    Vd = pd.DataFrame(np.where(V > 0, V, np.nan).T, index=dates, columns=cols)
    Cd = pd.DataFrame(C.T, index=dates, columns=cols)
    Vw = Vd.resample('W-FRI').sum(min_count=1)
    Cw = Cd.resample('W-FRI').last()
    vavg = Vw.shift(1).rolling(52, min_periods=40).mean()
    hiw = Cw.shift(1).rolling(52, min_periods=40).max()
    tw = (Cw.rolling(10).mean() > Cw.rolling(40).mean()) & (Cw > Cw.rolling(40).mean())
    rw = Cw / Cw.shift(1) - 1
    BW = ((rw >= .08) & ((Vw >= 3 * vavg) | ((Vw >= 2 * vavg) & (Cw >= hiw))) & tw).fillna(False)
    wlab = Vw.index
    wpos = {p: j for j, p in enumerate(pd.PeriodIndex(wlab, freq='W-FRI'))}
    widx = np.array([wpos.get(p, -1) for p in wk.values])            # semaine (ligne des tableaux hebdomadaires) de chaque séance
    # cumul de la semaine en cours, chaque soir
    Vn = np.nan_to_num(np.where(V > 0, V, 0)).astype(np.float64)
    vwtd = np.zeros_like(Vn)
    for t in range(nT):
        vwtd[:, t] = Vn[:, t] + (vwtd[:, t - 1] if not first[t] else 0)
    vavg_a, hiw_a, tw_a, BW_a = (x.reindex(columns=cols).values.T for x in (vavg, hiw, tw.astype(float), BW.astype(float)))
    prevC = np.where(prev_last >= 0, C[:, np.clip(prev_last, 0, None)], np.nan)
    with np.errstate(all='ignore'):
        retw = C / prevC - 1
        frac = (rank + 1) / 5.0
        va = np.where(widx >= 0, vavg_a[:, np.clip(widx, 0, None)], np.nan)
        hi = np.where(widx >= 0, hiw_a[:, np.clip(widx, 0, None)], np.nan)
        trp = np.where(widx >= 1, tw_a[:, np.clip(widx - 1, 0, None)], np.nan) == 1     # tendance de la semaine d'avant
        cond = (retw >= .08) & ((vwtd >= 3 * va * frac) | ((vwtd >= 2 * va * frac) & (C >= hi))) & trp
    # première séance de la semaine où la condition est remplie
    MID = np.zeros_like(cond)
    seen = np.zeros(len(cols), dtype=bool)
    for t in range(nT):
        if first[t]:
            seen[:] = False
        MID[:, t] = cond[:, t] & ~seen
        seen |= cond[:, t]
    # 📣 de la semaine, daté du dernier jour de la semaine (achat le lundi)
    is_last = np.r_[wid[1:] != wid[:-1], True]
    BWd = np.zeros_like(cond)
    for t in np.where(is_last)[0]:
        if widx[t] >= 0:
            BWd[:, t] = BW_a[:, widx[t]] == 1
    # variantes du bond du jour
    with np.errstate(all='ignore'):
        C1 = shift(C, 1)
        ret1 = C / C1 - 1
        vol50 = shift(roll(np.where(V > 0, V, np.nan).astype(np.float32), 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        upper = (C - L) >= .5 * (H - L)
        B8 = (ret1 >= .08) & (V >= 3 * vol50) & upper & trend
        B85 = (ret1 >= .08) & (V >= 5 * vol50) & upper & trend
        B5 = (ret1 >= .05) & (V >= 3 * vol50) & upper & trend
        conf = lambda M: (shift(M.astype(np.float32), 1) == 1) & (C >= C1)            # noqa: E731 (la clôture du lendemain tient)
        r2 = C / shift(C, 2) - 1
        v2 = V + shift(V, 1)
        B2j = (r2 >= .08) & (v2 >= 6 * vol50) & trend & ~(shift(B5.astype(np.float32), 1) == 1)
    S = {
        '📣 de la semaine (référence, acheté le lundi)': BWd,
        '📣 repéré en cours de semaine (volume ramené aux séances écoulées)': MID,
        'bond du jour +8 % sur 3 fois le volume': B8,
        'bond du jour +8 % sur 5 fois le volume': B85,
        'bond du jour +5 %, confirmé le lendemain (clôture qui tient)': conf(B5),
        'bond du jour +8 %, confirmé le lendemain': conf(B8),
        'deux séances : +8 % sur 3 fois le volume de 2 jours': B2j,
    }
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
    log("\n=== 2. 📣 repéré en cours de semaine : jour de la semaine, avance et hausse prise avant l'achat du lundi")
    ii, tt = np.where(MID & (yrs[None, :] >= 2000))
    days = np.bincount(rank[tt], minlength=5)
    log("  séance où il est repéré (lundi … vendredi) : " + ", ".join(f"{d}" for d in days))
    Onext = shift(O, -1)
    endw = np.array([last_of[w] for w in wid])
    became, gains, leads = [], [], []
    for i, t in zip(ii, tt):
        e = endw[t]
        b = BWd[i, e]
        became.append(b)
        if b and e > t:
            a, c = Onext[i, t], Onext[i, e]
            if np.isfinite(a) and np.isfinite(c) and a > 0:
                gains.append(c / a - 1)
                leads.append(e - t)
    became = np.array(became)
    log(f"  {len(ii)} repérages ; {became.mean() * 100:.0f} % finissent la semaine en 📣 ; parmi eux, repérés avant le vendredi : {len(gains)},"
        f" avance médiane {np.median(leads):.0f} séances, hausse prise avant l'achat du lundi : moyenne {np.mean(gains) * 100:+.1f} %,"
        f" médiane {np.median(gains) * 100:+.1f} %")
    nb = int((BWd & (yrs[None, :] >= 2000)).sum())
    log(f"  📣 de la semaine sur la même période : {nb} ; repérés avant le vendredi : {len(gains) / max(nb, 1) * 100:.0f} %")
    FS = np.zeros_like(MID)
    FS[ii[~became], tt[~became]] = True
    TS = np.zeros_like(MID)
    TS[ii[became], tt[became]] = True
    log("\n=== 3. Faux départs : repéré en cours de semaine, mais la semaine finit sans 📣")
    stats('repéré en cours de semaine, semaine finie en 📣', dedup(TS, 125), EX, RAW, months, yrs)
    stats('repéré en cours de semaine, semaine finie sans 📣 (faux départ)', dedup(FS, 125), EX, RAW, months, yrs)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
