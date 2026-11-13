"""Canal haussier repéré dès sa naissance, sur son support, puis allers-retours enchaînés (question de François du 13/11/2026 :
« détecter les actions qui entrent dans un canal haussier en étant sur un support et pouvoir ensuite faire des allers-retours entre
support et résistance »).

Naissance d'un canal (règle fixée avant le calcul, seuls cours connus à chaque date) : deux creux successifs (points bas encadrés de
5 séances de chaque côté ; un point bas à moins de 15 séances du creux précédent le remplace s'il est plus bas, sinon il est
ignoré), le second au moins 15 séances après le premier et plus haut que lui ; ligne basse par ces deux creux, pente de +15 à +150 %/an ; ligne haute parallèle par le plus haut sommet entre les deux ;
canal large de 15 à 50 % ; aucune clôture à plus de 3 % sous la ligne basse entre les deux creux. Le second creux n'est connu que
5 séances après : c'est le jour du repérage, retenu si la clôture est alors dans le quart bas du canal (« sur le support »).
Allers-retours enchaînés sur ces lignes, prolongées chaque jour selon la pente : achat à l'ouverture du lendemain du repérage ;
revente à la ligne haute −2 % dès que le plus haut du jour l'atteint (ordre à cours limité) ; rachat à l'ouverture du lendemain d'une
séance en hausse qui clôture dans les 15 % du bas ; le canal est cassé quand une clôture passe 5 % sous la ligne basse (vente à
l'ouverture suivante) ou 5 % au-dessus de la ligne haute hors position ; au plus 250 séances après le repérage. Frais : 0,6 %
l'aller-retour, argent non placé entre deux allers-retours. Un seul canal à la fois par action.

Comparaisons, sur la même période (du repérage à la fin du canal) : la moyenne des sociétés, et l'action achetée au repérage et
gardée jusqu'à la fin du canal (même vente). Variantes affichées pour la robustesse, pas pour choisir : en tendance au repérage,
« sur le support » plus strict (10 % du bas), dans la zone du 🎯. t regroupé par mois du repérage, trois périodes.

Cours journaliers Yahoo des sociétés de l'étude longue (survivantes : biais du survivant). Lancé par « Recherche (à la demande) »
(script canal_naissant.py), environ 5 minutes.
"""
import glob
import json
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT

log, shift, roll = FB.log, FB.shift, HT.roll
COST = .006
SLOPE_MIN, SLOPE_MAX = np.log(1.15) / 250, np.log(2.5) / 250
L3, L5 = np.log(1.03), np.log(1.05)


def simulate(i, t, k1, s, lo0, hi0, O, Hb, C, C1, lC, ok, T):
    """Allers-retours enchaînés dans le canal repéré à t (achat à l'ouverture de t+1).
    → (multiplicateur du capital, nombre d'allers-retours, séances investies, fin du canal, cassé, 1er à l'objectif, suivants)."""
    buy_px = float(O[i, t + 1])
    end = min(T - 1, t + 250)
    us = np.arange(t + 1, end + 1)
    base = lo0 + s * (us - k1)
    lo_a, hi_a = np.exp(base) * .95, np.exp(base + (hi0 - lo0)) * .98
    brk_hi = np.exp(base + (hi0 - lo0)) * 1.05
    pos_a = (lC[i, us] - base) / (hi0 - lo0)
    up_a = ok[i, us] & (C[i, us] > C1[i, us])
    Hs, Cs, Os = Hb[i, us], C[i, us], O[i, us]
    holding, entry, eq, n, inv, broke, first, u_end, d_in = True, buy_px, 1.0, 0, 0, False, None, end, t + 1
    later = []
    j, J = 0, len(us)
    while j < J:
        u = int(us[j])
        if holding:
            if Hs[j] >= hi_a[j]:
                sell = float(Os[j]) if Os[j] > hi_a[j] and ok[i, u - 1] else float(hi_a[j])
                eq *= sell / entry * (1 - COST)
                n, inv, holding = n + 1, inv + u - d_in, False
                if first is None:
                    first = True
                else:
                    later.append(True)
            elif Cs[j] < lo_a[j]:
                uu = min(u + 1, T - 1)
                sell = float(O[i, uu]) if np.isfinite(O[i, uu]) and O[i, uu] > 0 else float(Cs[j])
                eq *= sell / entry * (1 - COST)
                n, inv, holding, broke, u_end = n + 1, inv + uu - d_in, False, True, uu
                if first is None:
                    first = False
                else:
                    later.append(False)
                break
        else:
            if Cs[j] < lo_a[j]:
                broke, u_end = True, u
                break
            if Cs[j] > brk_hi[j]:
                u_end = u
                break
            if up_a[j] and pos_a[j] <= .15 and j + 1 < J and Os[j + 1] > 0:
                entry, holding, d_in = float(Os[j + 1]), True, u + 1
        j += 1
    if holding:                                       # fin des 250 séances en position : vente à la clôture
        sell = float(C[i, end]) if np.isfinite(C[i, end]) and C[i, end] > 0 else entry
        eq *= sell / entry * (1 - COST)
        n, inv, u_end = n + 1, inv + end - d_in, end
    return eq, n, inv, u_end, broke, first, later


def stats(name, R, periods):
    """R : liste de canaux {ex, hex, ret, n, inv, days, broke, month, year, first}."""
    if len(R) < 30:
        log(f"  {name:62s} trop peu de canaux ({len(R)})")
        return
    ex = np.array([r['ex'] for r in R]) * 100
    hx = np.array([r['hex'] for r in R]) * 100
    ret = np.array([r['ret'] for r in R]) * 100
    mo = pd.Series(ex, index=[r['month'] for r in R]).groupby(level=0).mean()
    tv = mo.mean() / (mo.std(ddof=1) / np.sqrt(len(mo))) if len(mo) > 2 and mo.std() > 0 else float('nan')
    mo2 = pd.Series(ex - hx, index=[r['month'] for r in R]).groupby(level=0).mean()
    tv2 = mo2.mean() / (mo2.std(ddof=1) / np.sqrt(len(mo2))) if len(mo2) > 2 and mo2.std() > 0 else float('nan')
    per, per2 = [], []
    for lab, y0, y1 in periods:
        sel = [r for r in R if y0 <= r['year'] <= y1]
        per.append(f"{np.mean([r['ex'] for r in sel]) * 100:+5.1f}" if len(sel) >= 30 else "  ·  ")
        per2.append(f"{np.mean([r['ex'] - r['hex'] for r in sel]) * 100:+5.1f}" if len(sel) >= 30 else "  ·  ")
    n = np.array([r['n'] for r in R])
    first = [r['first'] for r in R if r['first'] is not None]
    log(f"  {name:62s} {len(R):5d} canaux | allers-retours enchaînés {np.mean(ret):+5.1f} % (médiane {np.median(ret):+5.1f}), "
        f"{n.mean():.1f} allers-retours en {np.mean([r['days'] for r in R]):.0f} séances (investi {np.mean([r['inv'] for r in R]):.0f}) "
        f"| canal cassé {np.mean([r['broke'] for r in R]) * 100:3.0f} % | 1er aller-retour à l'objectif "
        f"{np.mean(first) * 100:3.0f} % | écart à la moyenne {np.mean(ex):+5.1f} (t {tv:4.1f}) [{' / '.join(per)}] | "
        f"gardée jusqu'à la fin du canal {np.mean(hx):+5.1f} | allers-retours moins garder {np.mean(ex - hx):+5.1f} "
        f"(t {tv2:4.1f}) [{' / '.join(per2)}]")


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
        Hb, Lb = np.minimum(H, C * 1.5), np.maximum(L, C / 1.5)
        hmax = pd.DataFrame(Hb.T).rolling(11, center=True, min_periods=11).max().values.T
        lmin = pd.DataFrame(Lb.T).rolling(11, center=True, min_periods=11).min().values.T
        ph, pl = ok & (Hb >= hmax), ok & (Lb <= lmin)
        r1 = np.where(ok, C / C1 - 1, np.nan)
        mret = np.nanmean(np.where(np.abs(r1) < .5, r1, np.nan), 0)
        mret[np.isfinite(r1).sum(0) < 30] = np.nan
        M = np.exp(np.nancumsum(np.log1p(np.nan_to_num(mret))))   # moyenne des sociétés (indice équipondéré)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = ok & (C > m200) & (m50 > m200)
        mom = shift(C, 21) / shift(C, 252) - 1
        zone = trend & (mom >= .6) & (mom <= 2.0)
        lC, lH, lL = (np.log(X).astype(np.float64) for X in (C, Hb, Lb))
    cnt = ok.sum(0)
    tl = T - 1
    now_paris = pd.Timestamp.now(tz='Europe/Paris')
    if dates[tl].date() >= now_paris.date() and now_paris.hour < 18:   # séance du jour pas encore close
        tl -= 1
    while tl > T - 10 and cnt[tl] < .6 * cnt[T - 10:].max():
        tl -= 1

    variants = {
        "règle fixée (2 creux montants, pente +15 à +150 %/an, largeur 15 à 50 %, quart bas)": dict(pos=.25, f=None),
        '… en tendance au repérage (moyennes 50 et 200 séances)': dict(pos=.25, f='trend'),
        '… « sur le support » plus strict (10 % du bas)': dict(pos=.10, f=None),
        '… dans la zone du 🎯 au repérage': dict(pos=.25, f='zone'),
    }
    filt = {None: ok, 'trend': trend, 'zone': zone}
    res = {k: [] for k in variants}
    later = {k: [] for k in variants}       # allers-retours après le premier : objectif atteint ou non
    now = []
    t1 = time.time()
    for i in range(N):
        PL = np.flatnonzero(pl[i])
        PH = np.flatnonzero(ph[i])
        if PL.size < 2 or PH.size < 1:
            continue
        busy = {k: -1 for k in variants}
        seen_now = None
        prev = None
        for k in PL:
            k = int(k)
            if prev is None:
                prev = k
                continue
            if k - prev < 15:                            # même creux : le plus bas l'emporte (connu à k + 5)
                if Lb[i, k] < Lb[i, prev]:
                    prev = k
                continue
            k1, k2 = prev, k
            prev = k
            t = k2 + 5                                   # le second creux n'est connu que 5 séances après
            if t >= T - 2 or t < 260 or not ok[i, t] or not Lb[i, k2] > Lb[i, k1]:
                continue
            s = (lL[i, k2] - lL[i, k1]) / (k2 - k1)
            if not (SLOPE_MIN <= s <= SLOPE_MAX):
                continue
            mid = PH[(PH > k1) & (PH < k2)]
            if not mid.size:
                continue
            lo0 = lL[i, k1]
            hi0 = float(np.max(lH[i, mid] - s * (mid - k1)))
            w = np.exp(hi0 - lo0) - 1
            if not (.15 <= w <= .5):
                continue
            seg = np.arange(k1, k2 + 1)
            e = lC[i, seg] - (lo0 + s * (seg - k1))
            if np.nanmin(e) < -L3:
                continue
            pos_t = (lC[i, t] - (lo0 + s * (t - k1))) / (hi0 - lo0)
            if pos_t < -L5 / (hi0 - lo0):                # déjà cassé au repérage
                continue
            if tl - 20 <= t <= tl and pos_t <= .25 and ok[i, tl]:
                ln_lo = lo0 + s * (np.arange(t, tl + 1) - k1)
                path = lC[i, t:tl + 1]
                if np.nanmin(path - ln_lo) >= -L5 and np.nanmax(path - ln_lo - (hi0 - lo0)) <= L5:
                    lo_now = np.exp(lo0 + s * (tl - k1))
                    seen_now = dict(sym=cols[i], name=names.get(cols[i], cols[i]), c=float(C[i, tl]), low=float(lo_now),
                                    high=float(lo_now * np.exp(hi0 - lo0)), slope=np.exp(s * 250) - 1, w=w,
                                    pos=(lC[i, tl] - (lo0 + s * (tl - k1))) / (hi0 - lo0), seen=str(dates[t].date()),
                                    zone=bool(zone[i, tl]), trend=bool(trend[i, tl]))
            sim = None
            for name, v in variants.items():
                if t <= busy[name] or pos_t > v['pos'] or not filt[v['f']][i, t] or not O[i, t + 1] > 0:
                    continue
                if sim is None:
                    sim = simulate(i, t, k1, s, lo0, hi0, O, Hb, C, C1, lC, ok, T)
                eq, n, inv, u_end, broke, first, lt = sim
                mk = M[u_end] / M[t] - 1
                hs = float(C[i, u_end]) if np.isfinite(C[i, u_end]) and C[i, u_end] > 0 else float(O[i, t + 1])
                hold = hs / float(O[i, t + 1]) * (1 - COST) - 1
                res[name].append({'ex': eq - 1 - mk, 'hex': hold - mk, 'ret': eq - 1, 'n': n, 'inv': inv, 'days': u_end - t,
                                  'broke': broke, 'month': int(months[t]), 'year': int(yrs[t]), 'first': first})
                later[name].extend(lt)
                busy[name] = u_end
        if seen_now:
            now.append(seen_now)
    log(f"canaux suivis en {time.time() - t1:.0f} s")
    periods = [('2000-2008', 2000, 2008), ('2009-2017', 2009, 2017), ('2018-2026', 2018, 2026)]
    log("\n=== Canal haussier repéré à sa naissance, sur son support, allers-retours enchaînés (frais de 0,6 % compris ; "
        "écart avec la moyenne des sociétés du repérage à la fin du canal)")
    for name in variants:
        stats(name, res[name], periods)
        lt = later[name]
        if lt:
            log(f"  {'':62s} allers-retours suivants (après le premier) : {len(lt)}, objectif atteint {np.mean(lt) * 100:.0f} %")
    log(f"\n=== Canaux haussiers repérés sur leur support dans les 20 dernières séances, encore intacts au "
        f"{dates[tl]:%d/%m/%Y} : {len(now)}")
    log("NAISSANT;symbole;nom;repéré_le;cours;ligne_basse;ligne_haute;pente_%_an;largeur_%;position_%;tendance;zone_cible")
    for x in sorted(now, key=lambda x: x['pos']):
        log(";".join(str(v) for v in (
            'NAISSANT', x['sym'], x['name'], x['seen'], f"{x['c']:.2f}", f"{x['low']:.2f}", f"{x['high']:.2f}",
            f"{x['slope'] * 100:.0f}", f"{x['w'] * 100:.0f}", f"{x['pos'] * 100:.0f}", 'oui' if x['trend'] else 'non',
            'oui' if x['zone'] else 'non')))
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
