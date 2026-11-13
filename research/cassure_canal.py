"""Cassures par le haut : canal haussier établi, canal naissant, fourchette plate (question de François du 13/11/2026 : « ou
choisir des actions qui cassent le canal haussier par le haut ? faire l'analyse complète »).

Règles fixées avant le calcul, seuls cours connus à chaque date (le canal est celui de la veille, prolongé jusqu'au jour) :
1. Canal haussier établi (comme canal_haussier.py) : droite des moindres carrés du logarithme des clôtures des 250 séances
   jusqu'à la veille, pente d'au moins +15 %/an, lignes parallèles par la clôture la plus basse et la plus haute, canal large de
   15 à 50 %, 2 contacts de chaque côté, 3 demi-cycles. Cassure : clôture 1 % au-dessus de la ligne haute prolongée.
2. Canal naissant (comme canal_naissant.py) : deux creux montants (le second connu 5 séances après lui), ligne basse par les
   creux (pente de +15 à +150 %/an), ligne haute parallèle par le sommet entre eux, canal de 15 à 50 %. Cassure : première clôture
   1 % au-dessus de la ligne haute prolongée, dans les 250 séances, sans clôture 5 % sous la ligne basse avant.
3. Fourchette plate qui oscille (comme allers_retours.py) : clôtures des 250 séances jusqu'à la veille dans 15 à 50 %, bas et haut
   touchés 2 fois, 3 demi-cycles. Cassure : clôture 1 % au-dessus du plus haut de la fourchette (nouveau plus haut d'un an).
Règle principale : cassure d'un canal haussier établi sur au moins 1,5 fois le volume moyen des 50 séances précédentes. Variantes
(sans condition de volume, 3 fois le volume, en tendance, avant le 🎯, dans le 🎯, hors tendance) affichées pour la robustesse.

Mesure (comme hausse_tot5.py) : achat à l'ouverture du lendemain, écart avec la moyenne des sociétés à 1, 3, 6 et 12 mois, une
entrée par société et par semestre, t regroupé par mois, trois périodes 2000-2008 / 2009-2017 / 2018-2026, part des hausses de 50 %
et des chutes de 25 % à 6 mois. Références de l'outil : 🎯 au feu vert, entrée dans la zone du 🎯, 📣 bond du jour, nouveau plus
haut de 20 séances sur 1,5 fois le volume, nouveau plus haut d'un an. Puis : fausses cassures (retour sous la ligne dans les 20
séances), cassure confirmée 20 séances après, temps gagné sur le 🎯, et ce que la cassure ajoute au 🎯 au feu vert chaque vendredi.

Cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant). Lancé par « Recherche (à la demande) »
(script cassure_canal.py), environ 6 minutes.
"""
import glob
import json
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3
from canal_haussier import rolling_line
from hausse_tot5 import stats4

log, shift, roll, dedup = FB.log, FB.shift, HT.roll, FB.dedup
SLOPE_MIN, SLOPE_MAX = np.log(1.15) / 250, np.log(2.5) / 250
L1, L3, L5 = np.log(1.01), np.log(1.03), np.log(1.05)


def groups(k):
    return 0 if not k.size else 1 + int(np.sum(np.diff(k) >= 15))


def halfcycles(p):
    z = np.where(p <= .25, -1, np.where(p >= .75, 1, 0))
    z = z[z != 0]
    return int(np.sum(z[1:] != z[:-1]))


def first_after(M, ii, tt, horizon):
    out = np.full(len(ii), -1)
    for n, (i, t) in enumerate(zip(ii, tt)):
        w = np.flatnonzero(M[i, t + 1:t + 1 + horizon])
        if w.size:
            out[n] = t + 1 + w[0]
    return out


def main():
    t0 = time.time()
    names = {}
    for f in glob.glob('../data/societes/*.json'):
        for k, x in json.load(open(f))['items'].items():
            names[k] = x.get('name') or k
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates = D['Close'].index
    cols = list(D['Close'].columns)
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    N, T = C.shape
    log(f"téléchargé en {time.time() - t0:.0f} s : {N} sociétés, {T} séances")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0) & (C > 0)
        C1 = shift(C, 1)
        ret1 = C / C1 - 1
        Hb, Lb = np.minimum(H, C * 1.5), np.maximum(L, C / 1.5)
        hmax = pd.DataFrame(Hb.T).rolling(11, center=True, min_periods=11).max().values.T
        lmin = pd.DataFrame(Lb.T).rolling(11, center=True, min_periods=11).min().values.T
        ph, pl = ok & (Hb >= hmax), ok & (Lb <= lmin)
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = ok & (C > m200) & (m50 > m200)
        mom = shift(C, 21) / shift(C, 252) - 1
        zone = trend & (mom >= .6) & (mom <= 2.0)                  # zone du 🎯
        feu = zone & (C > m50)                                     # au feu vert
        early = ok & (mom > -.2) & (mom < .6)                      # pas encore 🎯
        clv = (C - L) / (H - L)
        dbond = ok & (ret1 >= .08) & (vx >= 5) & (clv >= .5) & trend   # 📣 bond du jour
        hi20 = shift(roll(Hb, 20, 'max', 18), 1)
        cand20 = ok & (vx >= 1.5) & (C > C1) & (C > hi20)          # nouveau plus haut de 20 séances sur volume
        cmax, cmin = roll(C, 250, 'max', 225), roll(C, 250, 'min', 225)
        cmax1, cmin1 = shift(cmax, 1), shift(cmin, 1)
        new_hi = ok & (C > cmax1)                                  # nouveau plus haut d'un an (clôtures)
        LC = np.where(ok, np.log(np.where(C > 0, C, np.nan)), np.nan).astype(np.float64)
        lH, lL = np.log(Hb).astype(np.float64), np.log(Lb).astype(np.float64)
    zprev = np.zeros_like(zone)
    zprev[:, 1:] = zone[:, :-1]
    zone_in = zone & ~zprev
    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r
    cnt = ok.sum(0)
    tl = T - 1
    now_paris = pd.Timestamp.now(tz='Europe/Paris')
    if dates[tl].date() >= now_paris.date() and now_paris.hour < 18:   # séance du jour pas encore close
        tl -= 1
    while tl > T - 10 and cnt[tl] < .6 * cnt[T - 10:].max():
        tl -= 1

    # 1. canal haussier établi : canal de la veille, cassure par le haut le jour même
    t1 = time.time()
    a, b, s = rolling_line(LC, 250)
    with np.errstate(all='ignore'):
        a1, b1, s1 = shift(a, 1), shift(b, 1), shift(s, 1)
        tt = np.arange(T, dtype=np.float64)[None, :]
        e_up = LC - (a1 + b1 * tt)
        pre = ok & (C > C1) & (b1 >= SLOPE_MIN) & (e_up >= 1.0 * s1)
    del a, b, s
    EST = np.zeros((N, T), bool)
    est_line = {}                      # (i, t) → (ordonnée, pente, ligne haute) du canal cassé
    for i in range(N):
        pl_i, ph_i = np.flatnonzero(pl[i]), np.flatnonzero(ph[i])
        if pl_i.size < 4 or ph_i.size < 4:
            continue
        for t in np.flatnonzero(pre[i, 260:]) + 260:
            tc = t - 1
            aa, bb = a1[i, t], b1[i, t]
            s0 = tc - 249
            e = LC[i, s0:tc + 1] - (aa + bb * np.arange(s0, tc + 1))
            e = e[np.isfinite(e)]
            if e.size < 225:
                continue
            lo, hi = float(e.min()), float(e.max())
            w = np.exp(hi - lo) - 1
            if not (.15 <= w <= .5) or LC[i, t] - (aa + bb * t) < hi + L1:
                continue
            if halfcycles((e - lo) / (hi - lo)) < 3:
                continue
            kl = pl_i[(pl_i >= s0) & (pl_i <= tc - 5)]
            kh = ph_i[(ph_i >= s0) & (ph_i <= tc - 5)]
            if groups(kl[lL[i, kl] - (aa + bb * kl) <= lo + L3]) < 2 or groups(kh[lH[i, kh] - (aa + bb * kh) >= hi - L3]) < 2:
                continue
            EST[i, t] = True
            est_line[i, t] = (aa, bb, hi)
    del a1, b1, s1, e_up, pre
    log(f"cassures de canaux établis : {EST.sum()} jours en {time.time() - t1:.0f} s")

    # 2. canal naissant (deux creux montants), première cassure par le haut avant toute cassure par le bas
    t1 = time.time()
    NAI = np.zeros((N, T), bool)
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
                NAI[i, us[ju]] = True
                busy = int(us[ju])
            elif jd < 10 ** 9:
                busy = int(us[jd])
    log(f"cassures de canaux naissants : {NAI.sum()} jours en {time.time() - t1:.0f} s")

    # 3. fourchette plate qui oscille, cassée par le haut (nouveau plus haut d'un an de 1 %)
    t1 = time.time()
    with np.errstate(all='ignore'):
        yr1 = cmax1 / cmin1 - 1
        pre = ok & (C > cmax1 * 1.01) & (yr1 >= .15) & (yr1 <= .5)
    RNG = np.zeros((N, T), bool)
    for i in range(N):
        pl_i, ph_i = np.flatnonzero(pl[i]), np.flatnonzero(ph[i])
        if pl_i.size < 4 or ph_i.size < 4:
            continue
        for t in np.flatnonzero(pre[i, 260:]) + 260:
            tc = t - 1
            lo_, hi_ = float(cmin1[i, t]), float(cmax1[i, t])
            s0 = tc - 249
            seg = C[i, s0:tc + 1]
            seg = seg[np.isfinite(seg)]
            if halfcycles((seg - lo_) / (hi_ - lo_)) < 3:
                continue
            kl = pl_i[(pl_i >= s0) & (pl_i <= tc - 5)]
            kh = ph_i[(ph_i >= s0) & (ph_i <= tc - 5)]
            if groups(kl[Lb[i, kl] <= lo_ * 1.03]) < 2 or groups(kh[Hb[i, kh] >= hi_ * .97]) < 2:
                continue
            RNG[i, t] = True
    log(f"cassures de fourchettes plates : {RNG.sum()} jours en {time.time() - t1:.0f} s")

    def block(title, E):
        log(f"\n=== {title}")
        stats4("toutes", dedup(E, 125), EX, RAW, months, yrs)
        stats4("  sur 1,5 fois le volume ou plus", dedup(E & (vx >= 1.5), 125), EX, RAW, months, yrs)
        stats4("  sur 3 fois le volume ou plus", dedup(E & (vx >= 3), 125), EX, RAW, months, yrs)
        stats4("  sur moins de 1,5 fois le volume", dedup(E & ~(vx >= 1.5), 125), EX, RAW, months, yrs)
        stats4("  en tendance (moyennes 50 et 200 séances)", dedup(E & trend, 125), EX, RAW, months, yrs)
        stats4("  hors tendance", dedup(E & ~trend, 125), EX, RAW, months, yrs)
        stats4("  avant le 🎯 (−20 à +60 % sur 12 mois)", dedup(E & early, 125), EX, RAW, months, yrs)
        stats4("  avant le 🎯, en tendance, sur 1,5 fois le volume", dedup(E & early & trend & (vx >= 1.5), 125), EX, RAW,
               months, yrs)
        stats4("  dans la zone du 🎯", dedup(E & zone, 125), EX, RAW, months, yrs)
        stats4("  dans la zone du 🎯, sur 1,5 fois le volume", dedup(E & zone & (vx >= 1.5), 125), EX, RAW, months, yrs)

    log("\n=== Références de l'outil (même mesure)")
    stats4("tous les jours, sociétés en tendance", dedup(trend, 125), EX, RAW, months, yrs)
    stats4("🎯 au feu vert (ce que l'outil propose d'acheter)", dedup(feu, 125), EX, RAW, months, yrs)
    stats4("entrée dans la zone du 🎯", dedup(zone_in, 125), EX, RAW, months, yrs)
    stats4("📣 bond du jour (+8 % sur 5 fois le volume, en tendance)", dedup(dbond, 125), EX, RAW, months, yrs)
    stats4("nouveau plus haut de 20 séances sur 1,5 fois le volume", dedup(cand20, 125), EX, RAW, months, yrs)
    stats4("  … avant le 🎯, en tendance", dedup(cand20 & early & trend, 125), EX, RAW, months, yrs)
    stats4("nouveau plus haut d'un an (clôtures)", dedup(new_hi, 125), EX, RAW, months, yrs)
    stats4("  … avant le 🎯, en tendance, sur 1,5 fois le volume", dedup(new_hi & early & trend & (vx >= 1.5), 125), EX, RAW,
           months, yrs)
    block("1. Cassure par le haut d'un canal haussier établi (règle principale : sur 1,5 fois le volume)", EST)
    block("2. Cassure par le haut d'un canal haussier naissant (deux creux montants)", NAI)
    block("3. Cassure par le haut d'une fourchette plate qui oscille (nouveau plus haut d'un an)", RNG)

    log("\n=== 4. Fausses cassures (canal établi) : retour sous la ligne haute prolongée dans les 20 séances")
    back = np.zeros((N, T), bool)
    conf = np.zeros((N, T), bool)          # cassure tenue 20 séances : achat le lendemain de la 20e séance
    for (i, t), (aa, bb, hi) in est_line.items():
        if t + 20 >= T:
            continue
        us = np.arange(t + 1, t + 21)
        fell = np.nanmin(LC[i, us] - (aa + bb * us)) < hi
        if fell:
            back[i, t] = True
        elif t + 21 < T:
            conf[i, t + 20] = True
    ii, tt_ = np.where(EST & (vx >= 1.5))
    known = [(i, t) for i, t in zip(ii, tt_) if t + 20 < T]
    if known:
        log(f"  règle principale : {np.mean([back[i, t] for i, t in known]) * 100:.0f} % des cassures repassent sous la ligne dans les "
            f"20 séances ({len(known)} cassures)")
    stats4("cassure tenue 20 séances, achat ensuite (règle principale)", dedup(conf & np.roll(EST & (vx >= 1.5), 20, 1), 125),
           EX, RAW, months, yrs)
    stats4("cassure tenue 20 séances, achat ensuite (toutes)", dedup(conf, 125), EX, RAW, months, yrs)
    stats4("  … dans la zone du 🎯", dedup(conf & zone, 125), EX, RAW, months, yrs)

    log("\n=== 5. Temps gagné sur le 🎯 (cassures avant le 🎯, en tendance, 6 mois après)")
    for name, E in (("canal établi", EST), ("canal naissant", NAI), ("fourchette plate", RNG)):
        ii, tt_ = np.where(dedup(E & early & trend, 125))
        keep = tt_ + 1 < T
        ii, tt_ = ii[keep], tt_[keep]
        if not len(ii):
            continue
        u = first_after(zone_in, ii, tt_, 125)
        hit = u >= 0
        if not hit.any():
            log(f"  {name} : {len(ii)} cassures, aucune n'entre dans le 🎯 dans les 6 mois")
            continue
        lag = (u - tt_)[hit]
        gain = np.array([(O[i, min(x + 1, T - 1)] / O[i, t + 1] - 1) * 100 for i, t, x in zip(ii[hit], tt_[hit], u[hit])])
        gain = gain[np.isfinite(gain)]
        log(f"  {name} : {len(ii)} cassures, {hit.mean() * 100:.0f} % entrent dans le 🎯 dans les 6 mois, {np.median(lag):.0f} "
            f"séances après (médiane) ; hausse faite entre les deux achats : médiane {np.median(gain):+.1f} %, moyenne "
            f"{gain.mean():+.1f} %")

    log("\n=== 6. Ce que la cassure ajoute au 🎯 au feu vert (chaque vendredi, rythme de la sélection du lundi)")
    fri = np.array(dates.day_of_week == 4)
    anyb = EST | NAI | RNG
    rb10 = roll(anyb.astype(np.float32), 10, 'max', 1) > 0
    re10 = roll(EST.astype(np.float32), 10, 'max', 1) > 0
    rc10 = roll(cand20.astype(np.float32), 10, 'max', 1) > 0
    base = feu & fri[None, :]
    stats4("🎯 au feu vert, tous les vendredis", dedup(base, 125), EX, RAW, months, yrs)
    stats4("  cassure de canal ou de fourchette dans les 10 séances", dedup(base & rb10, 125), EX, RAW, months, yrs)
    stats4("  cassure d'un canal établi dans les 10 séances", dedup(base & re10, 125), EX, RAW, months, yrs)
    stats4("  plus haut de 20 séances sur volume, sans cassure de canal", dedup(base & rc10 & ~rb10, 125), EX, RAW, months, yrs)
    stats4("  ni l'un ni l'autre", dedup(base & ~rc10 & ~rb10, 125), EX, RAW, months, yrs)

    log("\n=== 7. Canal naissant cassé avant le 🎯, en tendance, sur 1,5 fois le volume : le canal ou la séance ?")
    nv = NAI & early & trend & (vx >= 1.5)
    ctl = cand20 & early & trend          # même séance sans canal : plus haut de 20 séances sur 1,5 fois le volume, avant le 🎯
    with np.errstate(all='ignore'):
        b20 = roll(dbond.astype(np.float32), 20, 'max', 1) > 0
        d0, d3, d8 = ret1 < .03, (ret1 >= .03) & (ret1 < .08), ret1 >= .08
    stats4("canal naissant cassé (rappel)", dedup(nv, 125), EX, RAW, months, yrs)
    stats4("  … le jour d'un 📣 bond du jour", dedup(nv & dbond, 125), EX, RAW, months, yrs)
    stats4("  … sans 📣 bond du jour dans les 20 séances", dedup(nv & ~b20, 125), EX, RAW, months, yrs)
    stats4("  … séance à moins de +3 %", dedup(nv & d0, 125), EX, RAW, months, yrs)
    stats4("  … séance de +3 à +8 %", dedup(nv & d3, 125), EX, RAW, months, yrs)
    stats4("  … séance à +8 % ou plus", dedup(nv & d8, 125), EX, RAW, months, yrs)
    stats4("  … de 1,5 à 3 fois le volume", dedup(nv & (vx < 3), 125), EX, RAW, months, yrs)
    stats4("  … 3 fois le volume ou plus", dedup(nv & (vx >= 3), 125), EX, RAW, months, yrs)
    log("  contrôle sans canal : plus haut de 20 séances sur 1,5 fois le volume, avant le 🎯, en tendance")
    stats4("  contrôle, séance à moins de +3 %", dedup(ctl & d0, 125), EX, RAW, months, yrs)
    stats4("  contrôle, séance de +3 à +8 %", dedup(ctl & d3, 125), EX, RAW, months, yrs)
    stats4("  contrôle, séance à +8 % ou plus", dedup(ctl & d8, 125), EX, RAW, months, yrs)
    stats4("  contrôle, 3 fois le volume ou plus", dedup(ctl & (vx >= 3), 125), EX, RAW, months, yrs)
    stats4("  contrôle, sans 📣 bond du jour dans les 20 séances", dedup(ctl & ~b20, 125), EX, RAW, months, yrs)
    stats4("  contrôle, au-dessus du plus haut d'un an", dedup(ctl & new_hi, 125), EX, RAW, months, yrs)
    stats4("  canal naissant cassé, au-dessus du plus haut d'un an", dedup(nv & new_hi, 125), EX, RAW, months, yrs)
    stats4("  canal naissant cassé, sous le plus haut d'un an", dedup(nv & ~new_hi, 125), EX, RAW, months, yrs)
    ii, tt_ = np.where(dedup(nv, 125))
    log(f"  {len(ii)} cassures en {len(set(yrs[tt_]))} ans, soit {len(ii) / 26.9:.0f} par an ; depuis 2024 : "
        f"{np.sum(yrs[tt_] >= 2024)}")

    log(f"\n=== Cassures par le haut des 10 dernières séances (jusqu'au {dates[tl]:%d/%m/%Y})")
    log("CASSURE;symbole;nom;date;type;cours_du_jour;cours_actuel;volume_x;tendance;zone_cible;avant_cible")
    rows = []
    for name, E in (("canal établi", EST), ("canal naissant", NAI), ("fourchette plate", RNG)):
        ii, tt_ = np.where(E[:, max(0, tl - 9):tl + 1])
        for i, t in zip(ii, tt_ + max(0, tl - 9)):
            rows.append((cols[i], names.get(cols[i], cols[i]), str(dates[t].date()), name, float(C[i, t]), float(C[i, tl]),
                         float(vx[i, t]) if np.isfinite(vx[i, t]) else float('nan'), bool(trend[i, t]), bool(zone[i, t]),
                         bool(early[i, t])))
    last = {}
    for r in sorted(rows, key=lambda r: r[2]):       # une ligne par société et type : la cassure la plus récente
        last[r[0], r[3]] = r
    for r in sorted(last.values(), key=lambda r: (r[2], r[0])):
        log(";".join(str(v) for v in ('CASSURE', r[0], r[1], r[2], r[3], f"{r[4]:.2f}", f"{r[5]:.2f}", f"{r[6]:.1f}",
                                       'oui' if r[7] else 'non', 'oui' if r[8] else 'non', 'oui' if r[9] else 'non')))
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
