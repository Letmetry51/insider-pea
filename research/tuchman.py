"""Peter Tuchman (17/11/2026, François : « S'inspirer de la méthode de Peter Tuchman pour améliorer l'outil »).

Tuchman, courtier au parquet du NYSE, donne des principes plus qu'une méthode (entretien Opto Sessions, CMC Markets) : le trading
est une affaire de probabilités, prendre ses gains quand on les a, ne pas attendre des pertes inacceptables, l'espoir n'est pas
une stratégie, éviter le FOMO, et « après trois pertes de suite, on éteint la machine ». Déjà testés ici : prise de bénéfices
partielle (−2,9 à −5,8 points par an), stop remonté au prix d'entrée (−1,6 à −4,0), stops fixes et suiveurs (_sorties.py),
FOMO (−4,9), RSI et moyennes (indicateurs du plan d'entrée). Restent deux pistes, testées ici :

1. « Trois pertes de suite, on éteint la machine » : portefeuille simulé 1998-2026 de backtest/_selection_sim.py, lignes suivies
   une à une comme backtest/_gestion_sim.py (4 🎯 + 1 📣 par semaine gardés 26 semaines, protection −30 %, frais 0,3 % par sens,
   liquidités à 0 %, ordres à la clôture de la semaine). Principale : le portefeuille a baissé 3 semaines de suite → pas d'achat
   cette semaine. Variantes : pause de 4 semaines ; tranche vendue la semaine d'avant (achats d'une semaine gardés 6 mois) en perte
   pour la 3e fois de suite ; au moins 3 lignes vendues à perte la semaine d'avant. Pour information : la règle actuelle investie à
   la même part que la pause principale (le reste en liquidités), et le résultat des tranches qu'elle aurait sautées.
2. Le montage technique qu'on lui attribue en ligne (forex.in.rs, sans source de sa main) : moyennes exponentielles 9, 15 et 30
   au-dessus de la 200, cours au-dessus de la 200 ; entrée sur un repli dont le plus bas touche la moyenne 9 (ou la 15), clôture
   au-dessus de la 15, RSI 14 entre 50 et 70. Cours journaliers Yahoo 2000-2026. Test décisif : pour chaque 🎯 au feu vert du
   vendredi (12 mois +60 à +200 %, tendance, au-dessus de la moyenne 50 jours ; une entrée par société et par semestre), achat à
   l'ouverture du lundi, ou attente du premier jour du montage dans les 4 semaines (achat à l'ouverture suivante ; sans montage,
   achat au bout de 4 semaines) ; même date de fin (6 mois après le lundi), écart de rendement attendre − acheter. Pour
   information : écart avec la moyenne des sociétés à 1, 3, 6 et 12 mois du montage, seul ou dans le 🎯 (comme hausse_tot5.py).

Règles fixées avant le calcul : (1) adoptée seulement si elle bat la règle actuelle sur 1998-2008, 2009-2017 et 2018-2026 avec
t ≥ 3 (blocs de 6 mois) ; (2) attendre le repli n'est proposé que s'il fait mieux que l'achat du lundi dans chacune des périodes
2000-2008, 2009-2017 et 2018-2026 avec t ≥ 3 (regroupé par mois) ; sinon documentées (research/README.md, aide de la page).

Lancé par « Recherche (à la demande) » (script tuchman.py), environ 15 minutes.
"""
import os
import runpy
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3
from hausse_tot5 import stats4

log, shift, roll, dedup = FB.log, FB.shift, HT.roll, FB.dedup
PERIODS = ((2000, 2009), (2009, 2018), (2018, 2027))

# exécuté dans les variables de backtest/_selection_sim2.py (pick, retw, t1997, T, ERAS)
SIM = '''
SEL = {t: pick(t, n=5, reserve=1, bondCap=2) for t in range(t1997, T - 1)}


def sim_pause(pause=None, weeks=1, hold=26, cost=.003):
    """Comme sim_pm(stop30=True) de _gestion_sim.py ; pause(t, R, last, done) dit s'il faut sauter les achats de la semaine t (R :
    rendements des semaines passées, last : résultats des lignes vendues la semaine d'avant, done : (semaine, résultat) des tranches
    vendues, dans l'ordre) ; weeks : semaines sans achat une fois la pause déclenchée. Renvoie les rendements, le nombre de semaines
    sans achat et le résultat de chaque tranche (semaine d'achat → résultat moyen des lignes, frais compris)."""
    tr, R, last, done, off, skip, tres = [], [], [], [], 0, 0, {}
    for t in range(t1997, T - 1):
        s = np.array(SEL.get(t, []), dtype=int)
        if len(s) and off > 0:
            off -= 1
            skip += 1
            s = s[:0]
        elif len(s) and pause is not None and pause(t, R, last, done):
            off = weeks - 1
            skip += 1
            s = s[:0]
        r = 0.0
        if len(s):
            k = len(s)
            tr.append(dict(t0=t, i=s, px=np.ones(k), q=np.ones(k) / k, res=np.full(k, np.nan)))
            r -= cost
        keep, closed = [], []
        for x in tr:
            age = t - x['t0'] + 1
            px1 = x['px'] * (1 + retw[x['i'], t + 1])
            live = x['q'] > 0
            pnl = x['q'] * (px1 - x['px'])
            hit = live & (px1 <= .70)
            if hit.any():
                r -= (x['q'][hit] * px1[hit] * cost).sum()
                x['res'][hit] = px1[hit] - 1 - 2 * cost
                closed += list(x['res'][hit])
                x['q'][hit] = 0.0
            r += pnl.sum()
            x['px'] = px1
            if age >= hold:
                r -= (x['q'] * x['px']).sum() * cost
                still = x['q'] > 0
                x['res'][still] = x['px'][still] - 1 - 2 * cost
                closed += list(x['res'][still])
                tres[x['t0']] = float(np.mean(x['res']))
                done.append((t, tres[x['t0']]))
            else:
                keep.append(x)
        tr = keep
        last = closed
        R.append(r / hold)
    return np.array(R), skip, tres
'''


def part1(t0):
    os.chdir('backtest')
    try:
        Lg = runpy.run_path('_long.py', run_name='long_build')
        sec = Lg['universe']()
        W, V = Lg['download'](list(sec))
        W = W.loc['1985':]
        V = V.reindex(index=W.index, columns=W.columns)
        wcols = list(W.columns)
        P, cut = Lg['clean'](W.values.T.astype(float))
        np.savez_compressed('long.npz', P=P.astype('float32'), V=V.values.T.astype('float32'),
                            dates=np.array([str(d.date()) for d in W.index]), cols=np.array(wcols),
                            sec=np.array([sec.get(c, '?') for c in wcols]))
        log(f"cours hebdomadaires : {len(wcols)} sociétés, {len(W.index)} semaines, {cut} séries coupées, en {time.time() - t0:.0f} s")
        G = {'__name__': 'selection_sim'}
        exec(compile(open('_selection_sim2.py').read().split('print("Écart avec')[0], '_selection_sim2.py', 'exec'), G)
        exec(compile(SIM, 'tuchman.SIM', 'exec'), G)
    finally:
        os.chdir('..')
    sim, ERAS, t1997, T, dates = G['sim_pause'], G['ERAS'], G['t1997'], G['T'], G['dates']

    def tstat(x):
        blk = np.array([x[k:k + 26].sum() for k in range(0, len(x) - 25, 26)])
        return blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk))) if len(blk) > 3 else np.nan

    def per(d):
        pp = [(d[a - t1997:min(b, T - 1) - t1997].mean() * 52 * 100, tstat(d[a - t1997:min(b, T - 1) - t1997]))
              for el, a, b in ERAS if el in ('1998-2008', '2009-2017', '2018-2026')]
        return pp, tstat(d)

    def desc(R):
        eq = np.cumprod(1 + R)
        return f"{(eq[-1] ** (52 / len(R)) - 1) * 100:+5.1f} %/an, pire baisse {(eq / np.maximum.accumulate(eq) - 1).min() * 100:+4.0f} %"

    B, _, tres = sim()
    nweeks = sum(1 for t in range(t1997, T - 1) if G['SEL'].get(t))
    log(f"\n=== 1. « Trois pertes de suite, on éteint la machine » ({dates[t1997]} → {dates[-1]}, {nweeks} semaines d'achat)\n"
        f"  règle actuelle (lignes suivies une à une, protection −30 %) : {desc(B)}")
    neg3 = lambda t, R, last, done: len(R) >= 3 and R[-1] < 0 and R[-2] < 0 and R[-3] < 0  # noqa: E731
    variants = [
        ("3 semaines de baisse de suite → pas d'achat (principale)", dict(pause=neg3)),
        ("même chose, pause de 4 semaines", dict(pause=neg3, weeks=4)),
        # la tranche vendue la semaine d'avant est la 3e perte de suite (sans tranche vendue, rien de nouveau : on rachète)
        ("tranche vendue la semaine d'avant : 3e perte de suite → pas d'achat",
         dict(pause=lambda t, R, last, done: len(done) >= 3 and done[-1][0] == t - 1 and max(v for _, v in done[-3:]) < 0)),
        ("3 lignes vendues à perte la semaine d'avant → pas d'achat",
         dict(pause=lambda t, R, last, done: sum(1 for v in last if v < 0) >= 3)),
    ]
    main_ok = False
    for k, (lab, kw) in enumerate(variants):
        Rv, skip, _ = sim(**kw)
        pp, tt = per(Rv - B)
        verdict = ''
        if k == 0:
            main_ok = all(x > 0 for x, _ in pp) and tt >= 3
            verdict = ' → ' + ('BAT LA RÈGLE' if main_ok else 'REJETÉE')
        log(f"  {lab:58s} sans achat {skip / max(nweeks, 1) * 100:4.1f} % des semaines · {desc(Rv)}\n"
            f"      écart : {' · '.join(f'{el} {x:+5.1f} (t {y:4.1f})' for (x, y), el in zip(pp, ('1998-2008', '2009-2017', '2018-2026')))}"
            f" · ensemble t {tt:4.1f}{verdict}")
        if k == 0:
            # à exposition égale : règle actuelle investie à la même part (le reste en liquidités à 0 %)
            f = 1 - skip / max(nweeks, 1)
            pq, tq = per(Rv - f * B)
            log(f"      règle actuelle investie à {f * 100:.0f} % : {desc(f * B)} ; écart de la pause : "
                f"{' · '.join(f'{x:+5.1f} (t {y:4.1f})' for x, y in pq)} · ensemble t {tq:4.1f}")
    # les tranches qu'on n'aurait pas achetées étaient-elles moins bonnes ? (règle actuelle)
    flag = {t1997 + k: bool(k >= 3 and B[k - 1] < 0 and B[k - 2] < 0 and B[k - 3] < 0) for k in range(len(B))}
    a = np.array([v for t, v in tres.items() if flag.get(t)])
    b = np.array([v for t, v in tres.items() if not flag.get(t)])
    if len(a) > 10 and len(b) > 10:
        log(f"  tranches achetées après 3 semaines de baisse : {len(a)}, résultat moyen à 6 mois {a.mean() * 100:+.1f} % "
            f"(en perte {np.mean(a < 0) * 100:.0f} %) ; autres semaines : {len(b)}, {b.mean() * 100:+.1f} % (en perte {np.mean(b < 0) * 100:.0f} %)")
    return main_ok


def wait_pullback(C, O, ev, setup, months, yrs, horizon=126, wait=20):
    """Pour chaque événement (vendredi t) : achat à l'ouverture de la séance suivante, ou au premier jour du montage dans les
    `wait` séances (achat à l'ouverture suivante ; sans montage, achat au bout de `wait` séances) ; même date de fin (clôture
    t + horizon). Renvoie (écart attendre − acheter, montage trouvé, attente en séances, année, mois) par événement."""
    N, T = C.shape
    rows = []
    for i, t in zip(*np.where(ev)):
        end = t + horizon
        if end >= T or t + wait + 1 >= T or yrs[t] < 2000:
            continue
        e0, ce = O[i, t + 1], C[i, end]
        if not (np.isfinite(e0) and e0 > 0 and np.isfinite(ce) and -.9 < ce / e0 - 1 < 5):
            continue
        u = np.flatnonzero(setup[i, t:t + wait + 1])
        j = t + int(u[0]) + 1 if len(u) else t + wait + 1
        e1 = O[i, j]
        if not (np.isfinite(e1) and .5 < e1 / e0 < 2):
            continue
        rows.append((ce / e1 - ce / e0, len(u) > 0, j - t - 1, yrs[t], months[t]))
    return rows


def part2(t0):
    D = FB.download(list(FB.universe()))
    O, H, L, C = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close'))
    dates = D['Close'].index
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    N, T = C.shape
    log(f"\n=== 2. Montage attribué à Tuchman (cours journaliers : {N} sociétés, {T} séances, {time.time() - t0:.0f} s)")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (C > 0)
        Cd = pd.DataFrame(np.where(ok, C, np.nan).T)
        E = {n: Cd.ewm(span=n, adjust=False, min_periods=n).mean().values.T for n in (9, 15, 30, 200)}
        dlt = Cd.diff()
        up = dlt.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        dn = (-dlt.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rsi = (100 - 100 / (1 + up / dn)).values.T
        upt = ok & (C > E[200]) & (E[9] > E[200]) & (E[15] > E[200]) & (E[30] > E[200])
        pull = upt & (L <= E[9]) & (C > E[15])
        setup = pull & (rsi >= 50) & (rsi <= 70)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = ok & (C > m200) & (m50 > m200)
        mom = shift(C, 21) / shift(C, 252) - 1
        zone = trend & (mom >= .6) & (mom <= 2.0)
        feu = zone & (C > m50)
        fri = np.array(dates.day_of_week == 4)
    EX, RAW = {}, None
    for h in (21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        EX[h] = e
        if h == 125:
            RAW = r
    FEU = dedup(feu & fri[None, :], 125)
    log("  écart avec la moyenne des sociétés, achat à l'ouverture du lendemain, une entrée par société et par semestre :")
    for lab, M in (('en tendance (moyennes 9, 15, 30 au-dessus de la 200)', upt),
                   ('montage complet (repli sur la 9, RSI 50-70)', setup),
                   ('repli sur la 9, RSI au-dessus de 70', pull & (rsi > 70)),
                   ('🎯 au feu vert, chaque vendredi (référence)', feu & fri[None, :]),
                   ('🎯 et montage complet', zone & setup),
                   ('🎯 sans repli, RSI au-dessus de 70', zone & ~pull & (rsi > 70))):
        stats4(lab, dedup(M, 125), EX, RAW, months, yrs)

    rows = wait_pullback(C, O, FEU, setup, months, yrs)
    if len(rows) < 60:
        log(f"  attente du repli : trop peu d'événements ({len(rows)})")
        return False
    d = np.array([x[0] for x in rows])
    found = np.array([x[1] for x in rows])
    lag = np.array([x[2] for x in rows])
    yy = np.array([x[3] for x in rows])
    mm = np.array([x[4] for x in rows])
    g = pd.Series(d).groupby(mm).mean()
    tv = g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))
    pp = [d[(yy >= a) & (yy < b)].mean() if ((yy >= a) & (yy < b)).sum() >= 20 else np.nan for a, b in PERIODS]
    log(f"\n  🎯 au feu vert du vendredi ({len(d)} cas) : montage dans les 4 semaines {found.mean() * 100:.0f} % des cas "
        f"(au bout de {np.median(lag[found]):.0f} séances en médiane)\n"
        f"  attendre le repli plutôt qu'acheter le lundi, même date de fin : {d.mean() * 100:+.1f} points (t {tv:.1f}) "
        f"[{' / '.join(f'{x * 100:+.1f}' for x in pp)}] ; quand le montage arrive {d[found].mean() * 100:+.1f}, "
        f"sinon {d[~found].mean() * 100 if (~found).any() else float('nan'):+.1f}")
    ok2 = all(np.isfinite(x) and x > 0 for x in pp) and tv >= 3
    log(f"\nDÉCISION 2 (règle fixée avant le calcul) : attendre le repli → {'à proposer à François' if ok2 else 'REJETÉ'}")
    return ok2


def main():
    t0 = time.time()
    ok1 = part1(t0)
    log(f"\nDÉCISION 1 (règle fixée avant le calcul) : pause après 3 semaines de baisse → {'à proposer à François' if ok1 else 'REJETÉE'}")
    part2(t0)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
