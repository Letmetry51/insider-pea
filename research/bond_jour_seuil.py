"""Bond du jour à 4 fois le volume (14/11/2026, question de François avec la fiche de Corbion, cours et volumes entourés :
« Pouvoir détecter ce type de moment »).

Corbion (CRBN.AS) : base de 10 mois entre 17 et 20,6 €, sortie en septembre sans gros volume, nouveaux plus hauts d'un an mi-octobre
sur des volumes ordinaires, puis le 27/10 une séance à +8,2 % sur environ 4,3 fois le volume moyen des 50 séances précédentes, en
tendance, au plus haut de l'année. L'outil l'a vue par le 📣 de la semaine (email 📣 Démarrage le 30/10, place 📣 de la sélection
envoyée le 03/11 à 27,56 €) ; l'alerte du soir « 📣 Bond du jour » (depuis le 04/11 : +8 % sur 5 fois le volume, en tendance) l'aurait
manquée de peu. La sortie de base de septembre ne prévoit rien (sortie_base.py, 10/11/2026 : −0,3 point à 6 mois, 1 463 cas).

Règle fixée avant le calcul :
- alerte actuelle (ES.dayBondInfo) : clôture à +8 % ou plus sur la veille, volume d'au moins 5 fois la moyenne des 50 séances
  précédentes (40 connues au moins), cours au-dessus de sa moyenne 200 séances et la 50 au-dessus de la 200 ;
- variante principale : la même à 4 fois le volume ;
- adoptée pour l'alerte du soir seulement (la sélection du lundi n'en tire rien : _selection_sim9.py, 04/11/2026) si les alertes
  ajoutées (entre 4 et 5 fois le volume) font mieux à 6 mois que le 🎯 au feu vert (même mesure, chaque vendredi) dans chacune des
  trois périodes, et si le nombre d'alertes ne fait pas plus que doubler.
Variantes pour information : 3 fois au plus haut de l'année, 4 fois ou 3 fois au plus haut de l'année, 3 fois.
Mesure (comme hausse_tot5.py) : achat à l'ouverture du lendemain, écart avec la moyenne des sociétés à 1, 3, 6 et 12 mois, une
entrée par société et par semestre, t regroupé par mois, périodes 2000-2008 / 2009-2017 / 2018-2026. Références : alerte actuelle,
📣 de la semaine acheté le lundi (règle de hausse_tot3.py), 🎯 au feu vert chaque vendredi. Aussi : alertes par an (une par société
sur 30 jours), part qui font ensuite un 📣 de la semaine, achat le lendemain ou le lundi pour les mêmes sociétés, Corbion le 27/10/2026.

Cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant). Lancé par « Recherche (à la demande) »
(script bond_jour_seuil.py), environ 3 minutes.
"""
import glob
import json
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3
from hausse_tot5 import stats4

log, shift, roll, dedup = FB.log, FB.shift, HT.roll, FB.dedup
PERIODS = ((2000, 2009), (2009, 2018), (2018, 2027))


def per6(M, X, yrs):
    """Écart moyen à 6 mois : ensemble, par période (nan sous 20 cas), nombre de cas."""
    ii, tt = np.where(M & np.isfinite(X))
    e = X[ii, tt]
    pp = []
    for a, b in PERIODS:
        m = (yrs[tt] >= a) & (yrs[tt] < b)
        pp.append(float(e[m].mean()) if m.sum() >= 20 else np.nan)
    return (float(e.mean()) if len(e) else np.nan), pp, len(e)


def fmt(v):
    return '   ·  ' if not np.isfinite(v) else f"{v * 100:+5.1f}"


def weekly_bond(C, Vp, dates, cols):
    """📣 de la semaine (règle de hausse_tot3.py : semaine à +8 % sur 3 fois le volume moyen de 52 semaines, ou 2 fois au plus haut de
    l'année, en tendance) placé à la dernière séance de la semaine, donc acheté à l'ouverture du lundi ; et la dernière séance de la
    semaine de chaque séance."""
    N, T = C.shape
    Cd = pd.DataFrame(C.T, index=dates, columns=cols)
    Vd = pd.DataFrame(Vp.T, index=dates, columns=cols)
    Cw, Vw = Cd.resample('W-FRI').last(), Vd.resample('W-FRI').sum(min_count=1)
    vavg, hiw = Vw.shift(1).rolling(52, min_periods=40).mean(), Cw.shift(1).rolling(52, min_periods=40).max()
    tw = (Cw.rolling(10).mean() > Cw.rolling(40).mean()) & (Cw > Cw.rolling(40).mean())
    BW = ((Cw / Cw.shift(1) - 1 >= .08) & ((Vw >= 3 * vavg) | ((Vw >= 2 * vavg) & (Cw >= hiw))) & tw)
    BWa = BW.reindex(columns=cols).fillna(False).values.T.astype(bool)
    wk = dates.to_period('W-FRI')
    lastday = {}
    for t in range(T):
        lastday[wk[t]] = t
    WB = np.zeros((N, T), bool)
    for j, p in enumerate(pd.PeriodIndex(BW.index, freq='W-FRI')):
        t = lastday.get(p)
        if t is not None:
            WB[:, t] = BWa[:, j]
    endw = np.array([lastday[wk[t]] for t in range(T)])
    return WB, endw


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
    ds = np.array(dates.strftime('%Y-%m-%d'))
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    N, T = C.shape
    log(f"téléchargé en {time.time() - t0:.0f} s : {N} sociétés, {T} séances ({ds[0]} → {ds[-1]})")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (np.nan_to_num(V) > 0) & (C > 0)
        ret1 = C / shift(C, 1) - 1
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = ok & (C > m200) & (m50 > m200)
        newhi = C > shift(roll(C, 252, 'max', 200), 1)
        mom = shift(C, 21) / shift(C, 252) - 1
        feu = trend & (mom >= .6) & (mom <= 2.0) & (C > m50)
        up8 = ok & (ret1 >= .08) & trend
    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r
    X6 = EX[125]
    fri = np.array(dates.day_of_week == 4)
    WB, endw = weekly_bond(C, Vp, dates, cols)
    FEU = feu & fri[None, :]

    R = up8 & (vx >= 5)
    V4 = up8 & (vx >= 4)
    A4 = V4 & ~R
    H3x = up8 & (vx >= 3) & newhi
    V3 = up8 & (vx >= 3)
    rules = [
        ('alerte actuelle : +8 % sur 5 fois le volume, en tendance', R),
        ('variante principale : +8 % sur 4 fois le volume', V4),
        ('  alertes ajoutées (4 à 5 fois) : décision', A4),
        ("  … ajoutées au plus haut de l'année", A4 & newhi),
        ("  … ajoutées sous le plus haut de l'année", A4 & ~newhi),
        ("3 fois au plus haut de l'année, ou 5 fois", H3x | R),
        ("  alertes ajoutées (3 à 5 fois au plus haut)", H3x & ~R),
        ("4 fois, ou 3 fois au plus haut de l'année", V4 | H3x),
        ('  alertes ajoutées', (V4 | H3x) & ~R),
        ('3 fois', V3),
        ('  alertes ajoutées (3 à 5 fois)', V3 & ~R),
    ]
    log("\n=== Références (achat à l'ouverture du lendemain, une entrée par société et par semestre)")
    stats4("🎯 au feu vert, chaque vendredi", dedup(FEU, 125), EX, RAW, months, yrs)
    stats4("📣 de la semaine, acheté le lundi", dedup(WB, 125), EX, RAW, months, yrs)
    log("\n=== Bond du jour selon le volume")
    for lab, M in rules:
        stats4(lab, dedup(M, 125), EX, RAW, months, yrs)

    full = (yrs >= 2009) & (yrs <= 2025)
    nyears = max(1, len(set(yrs[full].tolist())))
    log("\n=== Alertes par an (une par société sur 30 jours), 2009-2025, sociétés de l'étude")
    cnt = {}
    for lab, M in rules:
        if lab.startswith('  '):
            continue
        cnt[lab] = float(dedup(M, 21)[:, full].sum()) / nyears
        log(f"  {lab:60s} {cnt[lab]:6.1f} par an")
    ratio = cnt[rules[1][0]] / max(cnt[rules[0][0]], 1e-9)

    log("\n=== Pour les mêmes sociétés : 📣 de la semaine ensuite, achat le lendemain ou le lundi qui suit la semaine (6 mois)")
    for lab, M in (('alerte actuelle (5 fois)', R), ('alertes ajoutées (4 à 5 fois)', A4),
                   ("alertes ajoutées (3 à 5 fois au plus haut)", H3x & ~R)):
        ii, tt = np.where(dedup(M, 125) & (yrs[None, :] >= 2000))
        keep = endw[tt] + 130 < T
        ii, tt = ii[keep], tt[keep]
        if len(ii) < 30:
            log(f"  {lab:46s} trop peu de cas ({len(ii)})")
            continue
        e = endw[tt]
        became = WB[ii, e]
        en, em = X6[ii, tt], X6[ii, e]
        m = np.isfinite(en) & np.isfinite(em)
        mb = m & became
        log(f"  {lab:46s} {len(ii):5d} cas ; {became.mean() * 100:3.0f} % font un 📣 de la semaine ; achat le lendemain "
            f"{np.mean(en[m]) * 100:+.1f}, le lundi {np.mean(em[m]) * 100:+.1f} (écart {np.mean(en[m] - em[m]) * 100:+.1f}) ; "
            f"semaine finie en 📣 : {np.mean(en[mb] - em[mb]) * 100 if mb.sum() else float('nan'):+.1f} ; sans 📣 : "
            f"{np.mean(en[m & ~became]) * 100 if (m & ~became).sum() else float('nan'):+.1f}")

    a_all, a_pp, a_n = per6(dedup(A4, 125), X6, yrs)
    f_all, f_pp, _ = per6(dedup(FEU, 125), X6, yrs)
    w_all, w_pp, _ = per6(dedup(WB, 125), X6, yrs)
    r_all, r_pp, _ = per6(dedup(R, 125), X6, yrs)
    beats = all(np.isfinite(a) and np.isfinite(f) and a > f for a, f in zip(a_pp, f_pp))
    verdict = 'ADOPTÉE' if beats and ratio <= 2 else 'REJETÉE'
    log(f"\nDÉCISION (règle fixée avant le calcul) : alertes ajoutées (4 à 5 fois, {a_n} cas) {fmt(a_all)} "
        f"[{' / '.join(fmt(x) for x in a_pp)}] contre 🎯 au feu vert {fmt(f_all)} [{' / '.join(fmt(x) for x in f_pp)}] ; "
        f"pour mémoire alerte actuelle {fmt(r_all)} [{' / '.join(fmt(x) for x in r_pp)}], 📣 de la semaine {fmt(w_all)} "
        f"[{' / '.join(fmt(x) for x in w_pp)}] ; alertes ×{ratio:.2f} → variante principale {verdict}")

    if 'CRBN.AS' in cols:
        i = cols.index('CRBN.AS')
        log("\n=== Corbion (CRBN.AS)")
        for d0 in ('2026-10-20', '2026-10-21', '2026-10-26', '2026-10-27', '2026-10-30'):
            ts = np.flatnonzero(ds == d0)
            if not ts.size:
                continue
            t = int(ts[0])
            yn = lambda b: 'oui' if b else 'non'  # noqa: E731
            log(f"  {d0} : clôture {C[i, t]:.2f}, séance {ret1[i, t] * 100:+.1f} %, volume ×{vx[i, t]:.1f}, tendance {yn(trend[i, t])}, "
                f"plus haut d'un an {yn(newhi[i, t])} ; alerte actuelle {yn(R[i, t])}, 4 fois {yn(V4[i, t])}, 3 fois au plus haut "
                f"{yn(H3x[i, t])} ; 📣 de la semaine {yn(WB[i, endw[t]])}")

    cnt_ok = ok.sum(0)
    tl = T - 1
    now_paris = pd.Timestamp.now(tz='Europe/Paris')
    if dates[tl].date() >= now_paris.date() and now_paris.hour < 18:   # séance du jour pas encore close
        tl -= 1
    while tl > T - 10 and cnt_ok[tl] < .6 * cnt_ok[T - 10:].max():
        tl -= 1
    a0 = max(0, tl - 19)
    log(f"\n=== Bonds des 20 dernières séances (jusqu'au {ds[tl]}) : 4 fois le volume, ou 3 fois au plus haut de l'année")
    log("BOND;symbole;nom;date;hausse;volume;plus_haut_an;alerte_actuelle;cours_du_jour;cours_actuel")
    ii, tt = np.where((V4 | H3x | R)[:, a0:tl + 1])
    last = {}
    for i, t in zip(ii, tt + a0):
        last[i] = t
    for i, t in sorted(last.items(), key=lambda x: (-x[1], -float(vx[x[0], x[1]]))):
        log(";".join(str(v) for v in ('BOND', cols[i], names.get(cols[i], cols[i]), ds[t], f"{ret1[i, t] * 100:+.1f} %",
                                       f"×{vx[i, t]:.1f}", 'oui' if newhi[i, t] else 'non', 'oui' if R[i, t] else 'non',
                                       f"{C[i, t]:.2f}", f"{C[i, tl]:.2f}")))
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
