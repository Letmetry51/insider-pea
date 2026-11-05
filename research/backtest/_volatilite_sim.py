"""Volatilité implicite et sélection (05/11/2026, livre « Les secrets du trading sur la volatilité ») : le niveau du VIX ou du VSTOXX,
son retour à la moyenne et la structure par terme (VIX3M / VIX) disent-ils quand acheter la sélection, ou combien ? Portefeuille
simulé 1998-2026 de _selection_sim.py (4 🎯 + 1 📣, tranches hebdomadaires gardées 6 mois, frais 0,3 % par sens, liquidités à 0 %).
Données : research/volatilite.py (Yahoo, clôtures du vendredi ; le VSTOXX n'est pas servi par Yahoo). Section 4 : comparaison avec
l'alerte « krach du momentum » (marché équipondéré −20 % sur un an, fin à −15 %), liquidités rémunérées à 2 %."""
import numpy as np
exec(open('_selection_sim2.py').read().split('print("Écart avec')[0])

zv = np.load('volatilite.npz', allow_pickle=True)
vd = {str(d): j for j, d in enumerate(zv['dates'])}


def series(k):
    o = np.full(T, np.nan)
    if k not in zv.files:
        return o
    x = zv[k]
    for t, d in enumerate(dates):
        j = vd.get(str(d))
        if j is not None:
            o[t] = x[j]
    return o


VIX, VIX3, V2 = series('vix'), series('vix3m'), series('v2tx')
if np.isfinite(series('vxv')).sum() > np.isfinite(VIX3).sum():
    VIX3 = series('vxv')
VR = VIX3 / VIX                                         # au-dessus de 1 : contango (confiance) ; en dessous : tension
vix4 = np.array([np.nanmean(VIX[max(0, t - 3):t + 1]) for t in range(T)])
rv13 = np.array([np.nanstd(mkw[max(0, t - 12):t + 1]) * np.sqrt(52) if t >= 12 else np.nan for t in range(T)])   # vol. réalisée du marché
KW = dict(n=5, reserve=1, bondCap=2)
SEL = {t: pick(t, **KW) for t in range(t1997, T - 1)}


def blocks2(d, a0=0):
    out = []
    for el, a, b in ERAS:
        x = d[max(a, t1997 + a0) - t1997:min(b, T - 1) - t1997]
        if len(x) < 60:
            out.append(f"{el}   ·  ")
            continue
        blk = np.array([x[k:k + 26].sum() for k in range(0, len(x) - 25, 26)])
        t_ = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk))) if len(blk) > 3 else np.nan
        out.append(f"{el} {x.mean() * 52 * 100:+5.1f} (t {t_:4.1f})")
    return " · ".join(out)


def sim_w(wfun, a=t1997, b=T, hold=26, cost=.003, invvol=False):
    """Tranche de la semaine t investie à wfun(t) (0 à 1), le reste en liquidités à 0 % ; pondération égale ou inverse de la
    volatilité sur un an de chaque ligne."""
    tr, R = [], []
    for t in range(a, min(b, T - 1)):
        s = np.array(SEL.get(t, []), dtype=int)
        w = wfun(t)
        if len(s) and w > 0:
            if invvol:
                iv = 1 / np.clip(np.nan_to_num(v52[s, t], nan=.4), .15, 2)
                ww = iv / iv.sum() * w
            else:
                ww = np.ones(len(s)) / len(s) * w
            tr.append([t, s, ww, w])
        tr = [x for x in tr if t - x[0] < hold]
        r = 0.0
        for x in tr:
            rr = retw[x[1], t + 1]
            r += (x[2] * rr).sum() - cost * 2 / hold * x[3]
            x[2] = x[2] * (1 + rr)
        R.append(r / hold)
    return np.array(R)


def stats(R, lab, base=None, a0=0):
    R = R[a0:]
    eq = np.cumprod(1 + R)
    c = eq[-1] ** (52 / len(R)) - 1
    vol = R.std() * np.sqrt(52)
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    y12 = (eq[52:] / eq[:-52] - 1).min()
    s = f"  {lab:58s} {c * 100:+5.1f} %/an · volatilité {vol * 100:4.1f} % · pire baisse {dd * 100:+4.0f} % · pire 12 mois {y12 * 100:+4.0f} %"
    print(s)
    if base is not None:
        print(f"      écart : {blocks2(R - base[a0:], a0)}")


def by_regime(lab, X, bins, names):
    """Rendement à 26 semaines du marché et de la tranche achetée la semaine t, selon le régime de la semaine t"""
    print(f"\n  {lab}")
    for (lo, hi), nm in zip(bins, names):
        ts = [t for t in range(t1997, T - 27) if np.isfinite(X[t]) and lo <= X[t] < hi]
        if len(ts) < 10:
            print(f"    {nm:22s} {len(ts):4d} semaines")
            continue
        m26 = np.array([np.prod(1 + mkw[t + 1:t + 27]) - 1 for t in ts])
        s26_ = []
        for t in ts:
            s = SEL.get(t, [])
            if not s:
                continue
            g = np.prod(1 + retw[np.array(s)][:, t + 1:t + 27], axis=1) - 1
            s26_.append(np.nanmean(g))
        s26_ = np.array(s26_)
        yrs_ = sorted({int(str(dates[t])[:4]) for t in ts})
        print(f"    {nm:22s} {len(ts):4d} semaines ({len(yrs_):2d} années) · marché 6 mois {np.mean(m26) * 100:+5.1f} % · sélection {np.nanmean(s26_) * 100:+5.1f} %"
              f" · écart {np.nanmean(s26_) * 100 - np.mean(m26) * 100:+5.1f} · sélection < −20 % : {np.mean(s26_ < -.2) * 100:3.0f} %")


if __name__ == '__main__':
    have = {k: int(np.isfinite(x[t1997:]).sum()) for k, x in (('VIX', VIX), ('VIX3M', VIX3), ('VSTOXX', V2))}
    print(f"{N} sociétés, {dates[t1997]} → {dates[-1]} ; semaines avec données : {have}")
    print("\n=== 1. Rendement à 6 mois selon le régime de la semaine d'achat (moyenne des semaines)")
    by_regime("VIX (S&P 500, 30 jours)", VIX, [(0, 12), (12, 16), (16, 20), (20, 25), (25, 30), (30, 40), (40, 999)],
              ['< 12', '12-16', '16-20', '20-25', '25-30', '30-40', '≥ 40'])
    by_regime("VSTOXX (Euro Stoxx 50, 30 jours)", V2, [(0, 15), (15, 20), (20, 25), (25, 30), (30, 40), (40, 999)],
              ['< 15', '15-20', '20-25', '25-30', '30-40', '≥ 40'])
    by_regime("Structure par terme VIX3M / VIX (2007-2026)", VR, [(0, .95), (.95, 1), (1, 1.1), (1.1, 1.2), (1.2, 9)],
              ['< 0,95 (forte tension)', '0,95-1 (tension)', '1-1,1', '1,1-1,2', '≥ 1,2 (confiance)'])
    by_regime("VIX sous sa moyenne de 4 semaines, quand il est ≥ 25 (retour à la moyenne)", np.where(VIX >= 25, VIX - vix4, np.nan),
              [(-999, 0), (0, 999)], ['en baisse', 'en hausse'])
    by_regime("Volatilité réalisée du marché (13 semaines, %/an)", rv13 * 100, [(0, 10), (10, 15), (15, 20), (20, 30), (30, 999)],
              ['< 10', '10-15', '15-20', '20-30', '≥ 30'])

    print("\n=== 2. Règles d'achat (tranche de la semaine investie ou non, liquidités à 0 %) : 1998-2026, écart avec la règle actuelle")
    B = sim_w(lambda t: 1.0)
    stats(B, "règle actuelle (toujours investi)")
    rules = [
        ("pas d'achat quand le VIX ≥ 30", lambda t: 0.0 if VIX[t] >= 30 else 1.0),
        ("pas d'achat quand le VIX ≥ 25", lambda t: 0.0 if VIX[t] >= 25 else 1.0),
        ("pas d'achat quand le VSTOXX ≥ 30", lambda t: 0.0 if V2[t] >= 30 else 1.0),
        ("VIX ≥ 25 : achat seulement s'il redescend (4 semaines)", lambda t: 0.0 if (VIX[t] >= 25 and VIX[t] >= vix4[t]) else 1.0),
        ("pas d'achat quand le VIX < 12 (marché trop calme)", lambda t: 0.0 if VIX[t] < 12 else 1.0),
        ("tranche réduite : 20 / VIX (au plus 1)", lambda t: min(1.0, 20 / VIX[t]) if np.isfinite(VIX[t]) else 1.0),
        ("tranche réduite : 18 % / vol. réalisée du marché", lambda t: min(1.0, .18 / rv13[t]) if np.isfinite(rv13[t]) and rv13[t] > 0 else 1.0),
    ]
    for lab, f in rules:
        stats(sim_w(f), lab, B)
    t07 = int(np.searchsorted(dates, '2008-01-01'))
    a0 = t07 - t1997
    print("\n  Structure par terme (VIX3M connu depuis 2007) : 2008-2026")
    stats(B, "règle actuelle (2008-2026)", None, a0)
    for lab, f in [("pas d'achat en tension (VIX3M / VIX < 1)", lambda t: 0.0 if VR[t] < 1 else 1.0),
                   ("pas d'achat en forte tension (VIX3M / VIX < 0,95)", lambda t: 0.0 if VR[t] < .95 else 1.0),
                   ("« Volatility Fusion » : contango, VIX < 25 et en baisse sur 4 semaines", lambda t: 1.0 if (VR[t] >= 1 and VIX[t] < 25 and VIX[t] <= vix4[t]) else 0.0)]:
        stats(sim_w(f), lab, B, a0)

    print("\n=== 3. Taille des lignes : égale (règle actuelle) ou inverse de la volatilité sur un an de chaque société")
    stats(sim_w(lambda t: 1.0, invvol=True), "inverse de la volatilité", B)

    print("\n=== 4. Pause des achats : structure par terme inversée face à l'alerte « krach du momentum » (liquidités à 2 %)")
    m52 = np.full(T, np.nan)
    for t in range(52, T):
        m52[t] = np.prod(1 + mkw[t - 51:t + 1]) - 1
    crash, on = np.zeros(T, dtype=bool), False
    for t in range(T):
        if np.isfinite(m52[t]):
            on = (m52[t] <= -.15) if on else (m52[t] <= -.20)
        crash[t] = on
    tens = np.isfinite(VR) & (VR < 1)

    def run(f, rate=.02):
        R = sim_w(f)
        inv, tr = [], []
        for t in range(t1997, T - 1):
            tr.append(f(t) if SEL.get(t) else 0.0)
            tr = tr[-26:]
            inv.append(sum(tr) / 26)
        return R + (1 - np.array(inv)) * rate / 52, np.mean(inv)
    base, _ = run(lambda t: 1.0)
    for lab, f in (("règle actuelle", lambda t: 1.0), ("pause en krach du momentum (alerte actuelle)", lambda t: 0.0 if crash[t] else 1.0),
                   ("pause en tension (VIX3M / VIX < 1)", lambda t: 0.0 if tens[t] else 1.0),
                   ("demi-tranche en tension", lambda t: .5 if tens[t] else 1.0),
                   ("pause en krach ou en tension", lambda t: 0.0 if (crash[t] or tens[t]) else 1.0),
                   ("pause en tension hors krach", lambda t: 0.0 if (tens[t] and not crash[t]) else 1.0)):
        R, inv = run(f)
        eq = np.cumprod(1 + R)
        c, v = eq[-1] ** (52 / len(R)) - 1, R.std() * np.sqrt(52)
        dd, y12 = (eq / np.maximum.accumulate(eq) - 1).min(), (eq[52:] / eq[:-52] - 1).min()
        print(f"  {lab:46s} investi {inv * 100:3.0f} % · {c * 100:+5.1f} %/an · rendement/volatilité {c / v:4.2f} · pire baisse {dd * 100:+4.0f} %"
              f" · pire 12 mois {y12 * 100:+4.0f} %")
        print(f"      écart : {blocks2(R - base)}")
    R1, _ = run(lambda t: 0.0 if tens[t] else 1.0)
    yy = np.array([int(str(dates[t1997 + i])[:4]) for i in range(len(base))])
    print("  pause en tension, écart par année (points) : " + ", ".join(
        f"{y} {((np.prod(1 + R1[yy == y]) - np.prod(1 + base[yy == y])) * 100):+.0f}" for y in range(2008, 2027)))
