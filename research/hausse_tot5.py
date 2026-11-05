"""Bond près du point bas (05/11/2026) : garder le 📣 bond du jour (séance à +8 % ou plus sur au moins 5 fois le volume moyen de
50 séances, en tendance, clôture dans la moitié haute) et y ajouter un bond qui part près du plus bas (exemples : Qiagen au
printemps 2026, Husqvarna en octobre 2026, Corbion en août 2026) ; puis un modèle prédictif simple (régression logistique) sur
tous les bonds, entraîné sur les années passées et vérifié sur des années qu'il n'a pas vues.

Mesure : écart avec la moyenne des sociétés, de l'ouverture du lendemain à 1, 3, 6 et 12 mois, une entrée par société et par
semestre, t regroupé par mois, trois périodes, part des gains de 50 % ou plus et des chutes de 25 % ou plus. Cours journaliers
Yahoo des sociétés de l'étude longue (survivantes : biais du survivant, mêmes sociétés pour la référence). Lancé par
« Recherche (à la demande) » (script hausse_tot5.py), environ 6 minutes."""
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3

log, shift, dedup, roll = FB.log, FB.shift, FB.dedup, HT.roll


def stats4(lab, M, EX, RAW, months, yrs):
    """Une ligne : nombre de cas, écart à 1, 3, 6 et 12 mois (t à 6 mois), trois périodes, gros gains et chutes à 6 mois."""
    out = []
    n6 = 0
    lab_h = {21: ' 1 m', 63: ' 3 m', 125: ' 6 m', 250: '12 m'}
    for h in (21, 63, 125, 250):
        X = EX[h]
        ii, tt = np.where(M & np.isfinite(X))
        if len(ii) < 30:
            out.append(f"{lab_h[h]}   ·  ")
            continue
        e = X[ii, tt]
        if h == 125:
            n6 = len(ii)
            g = pd.Series(e).groupby(months[tt]).mean()
            tv = g.mean() / (g.std(ddof=1) / np.sqrt(len(g))) if len(g) > 10 else np.nan
            pp = []
            for a, b in ((2000, 2009), (2009, 2018), (2018, 2027)):
                m = (yrs[tt] >= a) & (yrs[tt] < b)
                pp.append(f"{e[m].mean() * 100:+5.1f}" if m.sum() >= 20 else "  ·  ")
            r = RAW[ii, tt]
            out.append(f"6 m {e.mean() * 100:+5.1f} (t {tv:4.1f}) [{' / '.join(pp)}] ≥+50 % {np.mean(r >= .5) * 100:4.1f} % chutes {np.mean(r <= -.25) * 100:4.1f} %")
        else:
            out.append(f"{lab_h[h]} {e.mean() * 100:+5.1f}")
    log(f"  {lab:60s} {n6:5d} | " + " · ".join(out))


def logit_fit(X, y, l2=1.0, iters=30):
    """Régression logistique (Newton, pénalité L2 sauf constante) : coefficients."""
    n, k = X.shape
    w = np.zeros(k)
    P = np.eye(k) * l2
    P[0, 0] = 0
    for _ in range(iters):
        z = np.clip(X @ w, -30, 30)
        p = 1 / (1 + np.exp(-z))
        g = X.T @ (p - y) + P @ w
        Hs = (X * (p * (1 - p))[:, None]).T @ X + P
        step = np.linalg.solve(Hs, g)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return w


def auc(score, y):
    o = np.argsort(score)
    r = np.empty(len(score))
    r[o] = np.arange(1, len(score) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else np.nan


def main():
    t0 = time.time()
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates, cols = D['Close'].index, list(D['Close'].columns)
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    log(f"téléchargé en {time.time() - t0:.0f} s : {len(cols)} sociétés, {len(dates)} séances")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0)
        C1 = shift(C, 1)
        ret1 = C / C1 - 1
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        clv = (C - L) / (H - L)
        lo252, hi252 = roll(C, 252, 'min', 200), roll(C, 252, 'max', 200)
        lo60 = roll(C, 60, 'min', 50)
        dlo = C / lo252 - 1                       # distance au plus bas d'un an (clôture du jour du bond)
        dlo60 = C / lo60 - 1                      # distance au plus bas de 3 mois
        ddn = 1 - C / hi252                       # baisse depuis le plus haut d'un an
        mom = shift(C, 21) / shift(C, 252) - 1    # 12 mois sans le dernier
        r20 = C1 / shift(C, 21) - 1               # 20 séances avant le bond
        lr = np.log(C / C1)
        vol60 = roll(np.where(ok, lr, np.nan).astype(np.float32) ** 2, 60, 'mean', 40) ** .5 * np.sqrt(252)
        gap = O / C1 - 1
        crash10 = roll(((ret1 <= -.08) & (vx >= 3)).astype(np.float32), 10, 'max', 1) > 0   # chute de -8 % sur gros volume, 10 séances
    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r
    base = ok & (ret1 >= .08) & (vx >= 5) & (clv >= .5)
    log("\n=== 1. Bond du jour (+8 % sur 5 fois le volume, clôture dans la moitié haute) selon la distance au plus bas d'un an")
    stats4("règle actuelle : en tendance (MM200 et MM50 > MM200)", dedup(base & trend, 125), EX, RAW, months, yrs)
    stats4("hors tendance", dedup(base & ~trend, 125), EX, RAW, months, yrs)
    for a, b in ((0, .05), (.05, .1), (.1, .2), (.2, .35), (.35, .6), (.6, 1), (1, 99)):
        stats4(f"  à +{a * 100:.0f} à +{b * 100:.0f} % du plus bas d'un an (toutes tendances)", dedup(base & (dlo >= a) & (dlo < b), 125), EX, RAW,
               months, yrs)
    for a, b in ((0, .1), (.1, .2), (.2, .35), (.35, .6), (.6, 99)):
        stats4(f"  en tendance, à +{a * 100:.0f} à +{b * 100:.0f} % du plus bas", dedup(base & trend & (dlo >= a) & (dlo < b), 125), EX, RAW, months, yrs)
    log("\n=== 2. Bond près du point bas : variantes (hors de la règle actuelle)")
    near = ~trend
    for X in (.1, .2, .3):
        stats4(f"+8 % ×5, à moins de {X * 100:.0f} % du plus bas d'un an", dedup(base & near & (dlo <= X), 125), EX, RAW, months, yrs)
        stats4("  … après une baisse de 30 % ou plus", dedup(base & near & (dlo <= X) & (ddn >= .3), 125), EX, RAW, months, yrs)
    stats4("+8 % ×5, à moins de 10 % du plus bas de 3 mois", dedup(base & near & (dlo60 <= .1), 125), EX, RAW, months, yrs)
    b53 = ok & (ret1 >= .05) & (vx >= 3) & (clv >= .5)
    stats4("+5 % ×3, à moins de 10 % du plus bas d'un an", dedup(b53 & near & (dlo <= .1), 125), EX, RAW, months, yrs)
    stats4("+5 % ×3, à moins de 10 % du plus bas, après -30 %", dedup(b53 & near & (dlo <= .1) & (ddn >= .3), 125), EX, RAW, months, yrs)
    stats4("chute ≤ -8 % sur gros volume puis rebond +5 % ×2 (10 séances)", dedup(ok & (ret1 >= .05) & (vx >= 2) & (clv >= .5) & crash10 & (dlo <= .15), 125),
           EX, RAW, months, yrs)
    stats4("contrôle : un jour quelconque à moins de 10 % du plus bas", dedup(ok & (dlo <= .1), 125), EX, RAW, months, yrs)
    stats4("contrôle : un jour quelconque en tendance", dedup(ok & trend, 125), EX, RAW, months, yrs)
    # rebond qui tient : 10 séances après le bond près du plus bas, la clôture est au-dessus de celle du bond (achat 10 séances plus tard)
    with np.errstate(all='ignore'):
        held = shift((base & near & (dlo <= .2)).astype(np.float32), 10) == 1
        held &= C >= shift(C, 10)
    stats4("bond à moins de 20 % du plus bas, tenu 10 séances (achat après)", dedup(held, 125), EX, RAW, months, yrs)

    log("\n=== 3. Modèle prédictif (régression logistique) sur tous les bonds (+5 % sur 3 fois le volume, toutes tendances)")
    EV = dedup(b53, 63) & (yrs[None, :] >= 2000) & np.isfinite(EX[125])
    ii, tt = np.where(EV)
    with np.errstate(all='ignore'):
        mk = np.nanmean(np.where(np.isfinite(C / m200), (C > m200).astype(np.float32), np.nan), 0)   # part des sociétés au-dessus de MM200
        feats = {
            'hausse du jour': np.clip(ret1, 0, .5),
            'volume (log)': np.log(np.clip(vx, 1, 100)),
            'distance au plus bas (log)': np.log1p(np.clip(dlo, 0, 5)),
            'baisse depuis le plus haut': np.clip(ddn, 0, .95),
            'cours / MM200': np.clip(C / m200 - 1, -.8, 2),
            'MM50 / MM200': np.clip(m50 / m200 - 1, -.8, 1.5),
            'momentum 12-1 mois': np.clip(mom, -.95, 5),
            '20 séances avant': np.clip(r20, -.6, 1.5),
            'volatilité 60 j': np.clip(vol60, 0, 2.5),
            'clôture dans la séance': np.clip(clv, 0, 1),
            'écart à l\'ouverture': np.clip(gap, -.3, .5),
            'marché au-dessus de MM200': np.broadcast_to(mk[None, :], C.shape),
        }
    names = list(feats)
    Xall = np.column_stack([feats[k][ii, tt] for k in names]).astype(np.float64)
    good = np.isfinite(Xall).all(1)
    ii, tt, Xall = ii[good], tt[good], Xall[good]
    e6 = EX[125][ii, tt]
    y = (e6 > 0).astype(float)
    ey = yrs[tt]
    log(f"  {len(ii)} bonds (une entrée par société et par trimestre, 2000-2026), {y.mean() * 100:.0f} % battent la moyenne à 6 mois")
    mu, sd = Xall[ey < 2014].mean(0), Xall[ey < 2014].std(0) + 1e-9
    Z = np.column_stack([np.ones(len(Xall)), (Xall - mu) / sd])
    tr, te = ey < 2014, ey >= 2014
    w = logit_fit(Z[tr], y[tr], l2=5.0)
    log("  coefficients (variables centrées réduites, 2000-2013) :")
    for k, c in sorted(zip(names, w[1:]), key=lambda x: -abs(x[1])):
        log(f"    {k:30s} {c:+.3f}")
    s_te = Z[te] @ w
    log(f"  AUC hors échantillon (2014-2026, {te.sum()} bonds) : {auc(s_te, y[te]):.3f} (0,5 = hasard)")
    # marche en avant : modèle réentraîné chaque année sur les années précédentes, appliqué à l'année suivante
    pred = np.full(len(ii), np.nan)
    for Y in range(2008, 2027):
        a, b = ey < Y, ey == Y
        if b.sum() and a.sum() > 1000:
            mu2, sd2 = Xall[a].mean(0), Xall[a].std(0) + 1e-9
            Za = np.column_stack([np.ones(a.sum()), (Xall[a] - mu2) / sd2])
            Zb = np.column_stack([np.ones(b.sum()), (Xall[b] - mu2) / sd2])
            wa = logit_fit(Za, y[a], l2=5.0)
            pred[b] = 1 / (1 + np.exp(-(Zb @ wa)))
    m = np.isfinite(pred)
    log(f"  marche en avant 2008-2026 : AUC {auc(pred[m], y[m]):.3f} sur {m.sum()} bonds")
    if m.sum() < 100:
        log("  trop peu de bonds pour la marche en avant")
        return
    q = pd.qcut(pred[m], 5, labels=False, duplicates='drop')
    for k in range(5):
        sel = q == k
        log(f"    quintile {k + 1} (probabilité {pred[m][sel].min():.2f}-{pred[m][sel].max():.2f}) : {sel.sum():5d} bonds, écart à 6 mois "
            f"{np.nanmean(e6[m][sel]) * 100:+5.1f}, battent la moyenne {y[m][sel].mean() * 100:3.0f} %")
    # sélection du modèle (quintile haut) contre la règle actuelle, mêmes années (2008-2026)
    top = np.zeros_like(EV)
    cut = np.nanquantile(pred[m], .8)
    sel = m & (pred >= cut)
    top[ii[sel], tt[sel]] = True
    yr08 = (yrs[None, :] >= 2008)
    stats4("modèle : quintile haut (2008-2026, prédit sans voir l'année)", dedup(top, 125), EX, RAW, months, yrs)
    stats4("  … dont hors de la règle actuelle (hors tendance)", dedup(top & ~trend, 125), EX, RAW, months, yrs)
    stats4("règle actuelle sur 2008-2026", dedup(base & trend & yr08, 125), EX, RAW, months, yrs)
    # effet de la distance au plus bas, autres variables égales : probabilité prédite en faisant varier seulement cette variable
    j = names.index('distance au plus bas (log)')
    zz = Z.copy()
    for v in (0, .05, .1, .2, .35, .6, 1, 2):
        zz[:, 1 + j] = (np.log1p(v) - mu[j]) / sd[j]
        log(f"    distance au plus bas +{v * 100:3.0f} % : probabilité moyenne {np.mean(1 / (1 + np.exp(-(zz @ w)))) * 100:4.1f} %")
    # les trois exemples
    log("\n=== 4. Les trois exemples (séances à +4 % ou plus en 2026)")
    for sym in ('QIA.DE', 'HUSQ-B.ST', 'CRBN.AS'):
        if sym not in cols:
            log(f"  {sym} absent")
            continue
        i = cols.index(sym)
        for t in np.where((yrs == 2026) & (np.nan_to_num(ret1[i]) >= .04))[0]:
            row = np.array([feats[k][i, t] for k in names], dtype=np.float64)
            p = 1 / (1 + np.exp(-(np.r_[1, (row - mu) / sd] @ w))) if np.isfinite(row).all() else np.nan
            log(f"  {sym:10s} {dates[t].date()} {ret1[i, t] * 100:+5.1f} % vol ×{vx[i, t]:4.1f} | plus bas d'un an +{dlo[i, t] * 100:3.0f} % | "
                f"{'en tendance' if trend[i, t] else 'hors tendance'} | règle actuelle {'oui' if base[i, t] and trend[i, t] else 'non'} | "
                f"modèle {p * 100:4.0f} %")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
