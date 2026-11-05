"""Règles de l'ancien « Comité IA » (outil-comite-ia.html, 05/11/2026) sur le portefeuille simulé de la sélection (4 🎯 + 1 📣,
tranches hebdomadaires gardées 6 mois, frais 0,3 % par sens, liquidités à 0 %), clôtures hebdomadaires 1998-2026 :
1. « FOMO » : écarter une société déjà montée de +30 % en 1 à 3 mois ;
2. gestion de ligne : stop remonté au prix d'entrée une fois +10 % atteint, vente d'un tiers si l'objectif est atteint en avance
   (dans les 3 mois), face à la règle actuelle (6 mois, protection à −30 %) ;
3. momentum relatif au secteur (et momentum du secteur) parmi les sociétés choisies."""
import numpy as np
exec(open('_volatilite_sim.py').read().split("\nif __name__ == '__main__':")[0])

H = 26
r4b = P / shift(P, 4) - 1
r8b = P / shift(P, 8) - 1
r13b = P / shift(P, 13) - 1
L = np.cumsum(np.log1p(retw), axis=1)
fut = np.full((N, T), np.nan)
fut[:, :T - H] = np.exp(L[:, H:] - L[:, :T - H]) - 1          # rendement des 26 semaines qui suivent la semaine t
LM = np.cumsum(np.log1p(mkw))
mk26 = np.full(T, np.nan)
mk26[:T - H] = np.exp(LM[H:] - LM[:T - H]) - 1
BASE_SEL = dict(SEL)


def lines_of(sel):
    out = []
    for t in range(t1997, T - H):
        for pos, i in enumerate(sel.get(t, [])):
            out.append((t, i, pos))
    return np.array(out, dtype=int).reshape(-1, 3)


def group(lab, LN, m):
    """écart moyen à 6 mois avec le marché (points), t (moyennes hebdomadaires, recouvrement de 26 semaines), chutes ≤ −25 %"""
    x = LN[m]
    if len(x) < 30:
        print(f"    {lab:46s} {len(x):5d} lignes")
        return
    ex = fut[x[:, 1], x[:, 0]] - mk26[x[:, 0]]
    wk = {}
    for (t, _, _), e in zip(x, ex):
        wk.setdefault(t, []).append(e)
    w = np.array([np.mean(v) for v in wk.values()])
    tt = w.mean() / (w.std(ddof=1) / np.sqrt(len(w))) / np.sqrt(H) if len(w) > 3 else np.nan
    cr = np.mean(fut[x[:, 1], x[:, 0]] <= -.25) * 100
    per = []
    for el, a, b in ERAS[:3]:
        mm = (x[:, 0] >= a) & (x[:, 0] < b)
        per.append(f"{el} {np.mean(ex[mm]) * 100:+5.1f}" if mm.sum() >= 20 else f"{el}   ·")
    print(f"    {lab:46s} {len(x):5d} lignes · {np.mean(ex) * 100:+5.1f} pts (t {tt:4.1f}) · chutes {cr:4.1f} % · " + " · ".join(per))


def build(no_target=None, no_bond=None):
    """sélection de chaque semaine sans les sociétés de no_target dans le 🎯 et de no_bond à la place 📣"""
    g = globals()
    tr0, de0 = g['trend'], g['dem']
    if no_target is not None:
        g['trend'] = tr0 & ~no_target
    if no_bond is not None:
        g['dem'] = de0 & ~no_bond
    try:
        return {t: pick(t, **KW) for t in range(t1997, T - 1)}
    finally:
        g['trend'], g['dem'] = tr0, de0


def run_sel(sel, lab, base):
    g = globals()
    old = g['SEL']
    g['SEL'] = sel
    try:
        R = sim_w(lambda t: 1.0)
    finally:
        g['SEL'] = old
    stats(R, lab, base)
    return R


def sim_pm(stop30=False, be=None, third=None, third_by=13, fill='close', rate=0.0, hold=26, cost=.003, info=None):
    """Lignes suivies une à une. be : stop remonté au prix d'entrée une fois la clôture à +be ; third : vente d'un tiers si la
    clôture atteint +third dans les third_by premières semaines ; stop30 : protection à −30 %. fill 'close' : ordres exécutés à la
    clôture de la semaine ; 'niveau' : exactement au niveau du stop ou de l'objectif (sans écart d'ouverture). Les ventes vont en
    liquidités rémunérées à rate jusqu'à la fin de la tranche ; achat de la tranche au poids 1, frais à chaque vente."""
    tr, R = [], []
    cnt = dict(lines=0, be=0, s30=0, third=0, after_be=[], after_s30=[])
    for t in range(t1997, T - 1):
        s = np.array(SEL.get(t, []), dtype=int)
        r = 0.0
        if len(s):
            k = len(s)
            tr.append(dict(t0=t, i=s, px=np.ones(k), q=np.ones(k) / k, armed=np.zeros(k, bool), sold=np.zeros(k, bool), cash=0.0))
            r -= cost
            cnt['lines'] += k
        keep = []
        for x in tr:
            age = t - x['t0'] + 1                       # semaines écoulées à la clôture t + 1
            rr = retw[x['i'], t + 1]
            px1 = x['px'] * (1 + rr)
            live = x['q'] > 0
            r += x['cash'] * rate / 52
            pnl = x['q'] * (px1 - x['px'])
            exit_px = np.full(len(px1), np.nan)
            if stop30:
                hit = live & (px1 <= .70)
                exit_px[hit] = px1[hit] if fill == 'close' else np.minimum(.70, x['px'][hit])
                for j in np.where(hit)[0]:
                    cnt['s30'] += 1
                    if t + 1 + (hold - age) < T:
                        cnt['after_s30'].append(np.exp(L[x['i'][j], min(T - 1, x['t0'] + hold)] - L[x['i'][j], t + 1]) - 1)
            if be is not None:
                hit = live & x['armed'] & (px1 <= 1.0) & ~np.isfinite(exit_px)
                exit_px[hit] = px1[hit] if fill == 'close' else np.minimum(1.0, x['px'][hit])
                for j in np.where(hit)[0]:
                    cnt['be'] += 1
                    if t + 1 + (hold - age) < T:
                        cnt['after_be'].append(np.exp(L[x['i'][j], min(T - 1, x['t0'] + hold)] - L[x['i'][j], t + 1]) - 1)
                x['armed'] |= live & (px1 >= 1 + be)
            ex = np.isfinite(exit_px)
            if ex.any():
                pnl[ex] = x['q'][ex] * (exit_px[ex] - x['px'][ex])
                val = x['q'][ex] * exit_px[ex]
                x['cash'] += (val * (1 - cost)).sum()
                r -= (val * cost).sum()
                x['q'][ex] = 0.0
            if third is not None:
                hit = live & ~ex & ~x['sold'] & (age <= third_by) & (px1 >= 1 + third)
                if hit.any():
                    p_s = px1[hit] if fill == 'close' else np.maximum(1 + third, x['px'][hit])   # tiers vendu à ce prix
                    pnl[hit] = x['q'][hit] / 3 * (p_s - x['px'][hit]) + x['q'][hit] * 2 / 3 * (px1[hit] - x['px'][hit])
                    val = x['q'][hit] / 3 * p_s
                    x['cash'] += (val * (1 - cost)).sum()
                    r -= (val * cost).sum()
                    x['q'][hit] *= 2 / 3
                    x['sold'][hit] = True
                    cnt['third'] += int(hit.sum())
            r += pnl.sum()
            x['px'] = px1
            if age >= hold:
                val = (x['q'] * x['px']).sum()
                r -= val * cost
            else:
                keep.append(x)
        tr = keep
        R.append(r / hold)
    if info is not None:
        info.update(cnt)
    return np.array(R)


def sec_strength():
    """momentum médian (12 mois sauf le dernier) du secteur de chaque société, et rang du secteur parmi les secteurs, chaque semaine"""
    smed = np.full((N, T), np.nan)
    srank = np.full((N, T), np.nan)
    us = [s for s in np.unique(secs) if s and s != 'nan']
    for t in range(t1997, T - 1):
        ok = okn[:, t] & np.isfinite(mom[:, t])
        meds = {}
        for s in us:
            m = ok & (secs == s)
            if m.sum() >= 8:
                meds[s] = np.median(mom[m, t])
        if len(meds) < 4:
            continue
        order = sorted(meds, key=meds.get)
        rk = {s: k / (len(order) - 1) for k, s in enumerate(order)}
        for s, v in meds.items():
            m = secs == s
            smed[m, t] = v
            srank[m, t] = rk[s]
    return smed, srank


if __name__ == '__main__':
    LN = lines_of(BASE_SEL)
    t_, i_, pos_ = LN[:, 0], LN[:, 1], LN[:, 2]
    print(f"{N} sociétés, {dates[t1997]} → {dates[-1]} ; {len(LN)} lignes achetées (sélection de 5 chaque semaine)")
    isb = dem[i_, t_] & (pos_ == 4)
    print(f"  5e place occupée par un 📣 : {np.mean(isb[pos_ == 4]) * 100:.0f} % des semaines")

    print("\n=== 1. « FOMO » : société déjà montée de +30 % en 1 à 3 mois au moment de l'achat")
    o4, o8, o13 = r4b[i_, t_] > .3, r8b[i_, t_] > .3, r13b[i_, t_] > .3
    oany = o4 | o8 | o13
    for lab, m in (("🎯 (places 1 à 4)", ~isb), ("📣 (5e place)", isb)):
        print(f"  {lab} : +30 % en 1 mois {np.mean(o4[m]) * 100:.0f} %, en 3 mois {np.mean(o13[m]) * 100:.0f} %,"
              f" en 1 à 3 mois {np.mean(oany[m]) * 100:.0f} % des lignes")
        group("toutes", LN, m)
        group("+30 % ou plus en 1 à 3 mois", LN, m & oany)
        group("  dont +30 % ou plus en 1 mois", LN, m & o4)
        group("+50 % ou plus en 3 mois", LN, m & (r13b[i_, t_] > .5))
        group("moins de +30 % sur 1, 2 et 3 mois", LN, m & ~oany)
    print("\n  Portefeuille : sociétés « FOMO » écartées (remplacées par les suivantes), écart avec la règle actuelle")
    B = sim_w(lambda t: 1.0)
    stats(B, "règle actuelle")
    OV = (r4b > .3) | (r8b > .3) | (r13b > .3)
    run_sel(build(no_target=OV), "+30 % en 1 à 3 mois écartées du 🎯", B)
    run_sel(build(no_target=r4b > .3), "+30 % en 1 mois écartées du 🎯", B)
    run_sel(build(no_target=r13b > .5), "+50 % en 3 mois écartées du 🎯", B)
    run_sel(build(no_bond=OV), "+30 % en 1 à 3 mois écartées du 📣", B)
    run_sel(build(no_target=OV, no_bond=OV), "+30 % en 1 à 3 mois écartées partout", B)

    print("\n=== 2. Gestion de ligne (lignes suivies une à une ; ordres à la clôture de la semaine, liquidités à 0 %)")
    print(f"  contrôle : règle actuelle par tranche (sim_w) {np.mean(B) * 52 * 100:+.2f} pts/an ; par ligne :")
    inf0 = {}
    B0 = sim_pm(info=inf0)
    stats(B0, "6 mois, sans protection")
    inf = {}
    B30 = sim_pm(stop30=True, info=inf)
    stats(B30, "6 mois, protection à −30 % (règle actuelle)", B0)
    a30 = np.array(inf['after_s30'])
    print(f"      {inf['s30'] / inf['lines'] * 100:.1f} % des lignes touchent −30 % ; ensuite, jusqu'aux 6 mois : moyenne {np.mean(a30) * 100:+.0f} %,"
          f" encore −10 % ou pire {np.mean(a30 <= -.1) * 100:.0f} %, +10 % ou mieux {np.mean(a30 >= .1) * 100:.0f} %")
    BASE = B30
    for lab, kw in (("stop au prix d'entrée une fois +10 % atteint", dict(be=.10)),
                    ("stop au prix d'entrée une fois +20 % atteint", dict(be=.20)),
                    ("vente d'un tiers à +20 % dans les 3 mois", dict(third=.20)),
                    ("vente d'un tiers à +15 % dans les 3 mois", dict(third=.15)),
                    ("vente d'un tiers à +30 % dans les 3 mois", dict(third=.30)),
                    ("Comité : stop à l'entrée après +10 % et tiers à +20 % en 3 mois", dict(be=.10, third=.20))):
        inf = {}
        R = sim_pm(stop30=True, info=inf, **kw)
        stats(R, lab, BASE)
        msg = []
        if inf['be']:
            ab = np.array(inf['after_be'])
            msg.append(f"stop à l'entrée touché par {inf['be'] / inf['lines'] * 100:.0f} % des lignes ; ensuite, jusqu'aux 6 mois : moyenne "
                       f"{np.mean(ab) * 100:+.1f} %, reparties à +10 % ou mieux {np.mean(ab >= .1) * 100:.0f} %, −10 % ou pire {np.mean(ab <= -.1) * 100:.0f} %")
        if inf['third']:
            msg.append(f"tiers vendu sur {inf['third'] / inf['lines'] * 100:.0f} % des lignes")
        for m_ in msg:
            print("      " + m_)
    print("\n  Sensibilité : ordres exécutés exactement au niveau (stop au prix d'entrée, objectif) et liquidités à 2 %")
    BASEn = sim_pm(stop30=True, fill='niveau', rate=.02)
    stats(BASEn, "6 mois, protection à −30 % (au niveau, liquidités 2 %)")
    for lab, kw in (("stop au prix d'entrée une fois +10 % atteint", dict(be=.10)),
                    ("vente d'un tiers à +20 % dans les 3 mois", dict(third=.20)),
                    ("Comité : les deux", dict(be=.10, third=.20))):
        stats(sim_pm(stop30=True, fill='niveau', rate=.02, **kw), lab, BASEn)

    print("\n=== 3. Momentum relatif au secteur parmi les sociétés choisies (momentum 12 mois sauf le dernier)")
    smed, srank = sec_strength()
    rel = mom[i_, t_] - smed[i_, t_]
    sr = srank[i_, t_]
    okr = np.isfinite(rel) & np.isfinite(sr)
    q1, q2 = np.nanpercentile(rel[okr], [100 / 3, 200 / 3])
    print(f"  écart avec le momentum médian du secteur : tiers à {q1 * 100:+.0f} et {q2 * 100:+.0f} points")
    group("toutes (secteur connu)", LN, okr)
    group("tiers le plus faible face au secteur", LN, okr & (rel <= q1))
    group("tiers du milieu", LN, okr & (rel > q1) & (rel <= q2))
    group("tiers le plus fort face au secteur", LN, okr & (rel > q2))
    group("secteur dans le tiers faible des secteurs", LN, okr & (sr <= 1 / 3))
    group("secteur dans le tiers du milieu", LN, okr & (sr > 1 / 3) & (sr <= 2 / 3))
    group("secteur dans le tiers fort des secteurs", LN, okr & (sr > 2 / 3))
