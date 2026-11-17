"""Modèle de probabilité de la méthode (17/11/2026, François : « existe-t-il un modèle mathématique ou de probabilité ? sinon, tu es
mathématicien, probabiliste et statisticien, améliorer l'outil »).

L'outil choisit par des règles validées sur l'historique ; ses probabilités sont des fréquences passées (« 2 fois sur 3 en hausse à 6
mois »). Il manquait : la loi des résultats du portefeuille sur plusieurs années, ce que le 📒 suivi réel peut prouver et quand, une
auto-surveillance dont le taux de fausses alertes est connu, et des chances à 6 mois propres à chaque société. Données : cours
hebdomadaires Yahoo de backtest/_long.py (sociétés encore cotées : biais du survivant), règles de backtest/_selection_sim.py.

1. Portefeuille simulé 1998-2026 (4 🎯 + 1 📣 par semaine gardés 26 semaines, protection −30 %, frais 0,3 % par sens, lignes suivies
   une à une comme backtest/_gestion_sim.py) face à la société moyenne (moyenne équipondérée des sociétés de l'étude, chaque
   semaine) : écart hebdomadaire, volatilité de l'écart, autocorrélation, rapport d'information ; fenêtres glissantes de 1, 3 et 5 ans
   (battre la société moyenne, perdre de l'argent), chiffres bruts puis prudents (écart ramené à +8 points par an, chiffre prudent
   de l'aide : +4 points tous les 6 mois) ; années de suivi réel pour que l'écart atteigne t = 2.
2. 📒 suivi réel rejoué : chaque semaine les 10 sociétés du suivi (8 🎯 + 2 📣, ES.pickN n = 10), résultat à 3 et 6 mois face à la
   société moyenne. Pour un suivi qui commence n'importe quelle semaine : écart type de la moyenne après W semaines mûres (marché,
   chevauchement des fenêtres et sociétés reprises d'une semaine à l'autre compris).
3. Auto-surveillance (build.mjs, 6g) rejouée sur ces suivis, contrôle chaque semaine pendant 3 ans. Règle actuelle : alerte si à 6
   mois la moyenne des lignes fait moins que l'indice (au moins 30 lignes), si à 3 mois elle fait moins de −5 points (au moins 30
   lignes), ou si un signal (🔊, 📣, ⏸️, place 📣) donne un écart de sens contraire à 6 mois (au moins 30 lignes de chaque côté).
   Règle proposée : probabilité a posteriori que l'avantage ait disparu, deux hypothèses à égalité au départ (avantage prudent
   contre avantage nul), loi normale de la moyenne avec l'écart type mesuré en 2 sur les deux autres périodes (6 mois, 3 mois, et
   écart avec / sans de chaque signal) ; alerte au-delà d'un seuil choisi sur les deux autres périodes : le plus bas de 80, 90, 95,
   97,5, 99 et 99,5 % qui y donne au plus 10 % de fausses alertes en 3 ans. Scénarios : avantage tel qu'en 1998-2026 ; avantage
   intact au niveau prudent (écart des lignes ramené à +4 points à 6 mois dans chaque période, signaux tels quels) ; avantage
   disparu (écart ramené à 0, écart des signaux ramené à 0) ; avantage négatif (−4 points).
   Règle fixée avant le calcul : la règle proposée remplace l'actuelle si, pour les suivis commencés dans chacune des périodes
   1998-2008, 2009-2017 et 2018-2023, elle donne moins de fausses alertes en 3 ans (avantage prudent) et des alertes plus sûres
   (part des alertes justifiées, à 50/50 entre avantage prudent et avantage disparu).
4. Chances à 6 mois de chaque société (hausse, +20 % ou mieux, −25 % ou pire), régression logistique sur la volatilité d'un an, la
   hausse sur 12 mois et 🔊, apprise sur deux périodes et jugée sur la troisième. Règle fixée avant le calcul : affichée seulement
   pour les chances dont le score de Brier bat la fréquence d'ensemble (celle de l'aide) dans chacune des trois périodes.

Lancé par « Recherche (à la demande) » (script proba.py), environ 5 minutes.
"""
import json
import os
import runpy
import time

import numpy as np

import figures_bougies as FB
from hausse_tot5 import logit_fit

log = FB.log
ERAS3 = ('1998-2008', '2009-2017', '2018-2026')
WGRID = (1, 2, 3, 4, 6, 8, 13, 17, 26, 39, 52, 78, 104)
PRUDENT6 = .04          # +4 points à 6 mois face à la société moyenne (aide, « ⚖️ Fiabilité des chiffres »)
SIGNALS = (('hot', '🔊', 1), ('bp', '📣 bond', 1), ('wait', '⏸️', -1), ('bd', 'place 📣', 1))

SIM = '''
SEL = {t: pick(t, n=5, reserve=1, bondCap=2) for t in range(t1997, T - 1)}
SEL10 = {t: pick(t, n=10, reserve=2, bondCap=2) for t in range(t1997, T - 1)}


def sim30(hold=26, cost=.003):
    """Lignes suivies une à une (sim_pm(stop30=True) de _gestion_sim.py) : rendement hebdomadaire du portefeuille."""
    tr, R = [], []
    for t in range(t1997, T - 1):
        s = np.array(SEL.get(t, []), dtype=int)
        r = 0.0
        if len(s):
            k = len(s)
            tr.append(dict(t0=t, i=s, px=np.ones(k), q=np.ones(k) / k))
            r -= cost
        keep = []
        for x in tr:
            px1 = x['px'] * (1 + retw[x['i'], t + 1])
            pnl = x['q'] * (px1 - x['px'])
            hit = (x['q'] > 0) & (px1 <= .70)
            if hit.any():
                r -= (x['q'][hit] * px1[hit] * cost).sum()
                x['q'][hit] = 0.0
            r += pnl.sum()
            x['px'] = px1
            if t - x['t0'] + 1 >= hold:
                r -= (x['q'] * x['px']).sum() * cost
            else:
                keep.append(x)
        tr = keep
        R.append(r / hold)
    return np.array(R)
'''


def load():
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
        log(f"cours hebdomadaires : {len(wcols)} sociétés, {len(W.index)} semaines, {cut} séries coupées")
        G = {'__name__': 'selection_sim'}
        exec(compile(open('_selection_sim2.py').read().split('print("Écart avec')[0], '_selection_sim2.py', 'exec'), G)
        exec(compile(SIM, 'proba.SIM', 'exec'), G)
    finally:
        os.chdir('..')
    return G


def era_of(G, t):
    for el, a, b in G['ERAS']:
        if el in ERAS3 and a <= t < b:
            return el
    return None


def pct(x, d=0):
    return f"{x * 100:+.{d}f}".replace('.', ',')


# ---------------------------------------------------------------------------------------------------- 1. portefeuille
def part1(G):
    t1997, T, mkw, yr = G['t1997'], G['T'], G['mkw'], G['yr']
    R = G['sim30']()
    M = mkw[t1997 + 1:T]
    e = R - M
    ty = yr[t1997 + 1:T]
    log("\n=== 1. Portefeuille simulé face à la société moyenne (rendements hebdomadaires)")
    ex_ann = e.mean() * 52
    for lab, m in [('1998-2026', np.ones(len(e), bool))] + [(el, (ty >= int(el[:4])) & (ty <= int(el[-4:]))) for el in ERAS3]:
        x = e[m]
        te = x.std(ddof=1) * np.sqrt(52)
        log(f"  {lab}  écart {pct(x.mean() * 52, 1)} points par an, volatilité de l'écart {x.std(ddof=1) * np.sqrt(52) * 100:.1f} %, "
            f"rapport d'information {x.mean() * 52 / te:.2f} ; portefeuille {pct(np.prod(1 + R[m]) ** (52 / m.sum()) - 1, 1)} %/an, "
            f"société moyenne {pct(np.prod(1 + M[m]) ** (52 / m.sum()) - 1, 1)} %/an")
    ac = [float(np.corrcoef(e[:-k], e[k:])[0, 1]) for k in (1, 2, 4, 13, 26)]
    log("  autocorrélation de l'écart (1, 2, 4, 13, 26 semaines) : " + ', '.join(f"{a:+.2f}" for a in ac))
    # variance de la somme sur 52 semaines, chevauchements compris (Newey-West implicite) : écart type annuel effectif
    cs = np.concatenate([[0], np.cumsum(e)])
    y1 = cs[52:] - cs[:-52]
    sd_eff = y1.std(ddof=1)
    out = {}
    for lab, shift in (('bruts', 0.0), ('prudents', (ex_ann - .08) / 52)):
        Rp = R - shift
        lS, lM = np.concatenate([[0], np.cumsum(np.log1p(Rp))]), np.concatenate([[0], np.cumsum(np.log1p(M))])
        cells = []
        for H in (52, 156, 260):
            gS, gM = np.exp(lS[H:] - lS[:-H]), np.exp(lM[H:] - lM[:-H])
            beat, loss = np.mean(gS > gM), np.mean(gS < 1)
            q = np.percentile(gS - 1, [10, 50, 90])
            out[(lab, H)] = dict(beat=beat, loss=loss, q=q, worst=float((gS - 1).min()), mbeat=np.mean(gM > 1))
            cells.append(f"{H // 52} an{'s' if H > 52 else ''} : bat la société moyenne {beat * 100:.0f} % des fenêtres, perd de "
                         f"l'argent {loss * 100:.0f} % (société moyenne {np.mean(gM < 1) * 100:.0f} %), 10 / 50 / 90 % : "
                         f"{' / '.join(pct(v) for v in q)} %, pire {pct((gS - 1).min())} %")
        ea = (Rp - M).mean() * 52
        yrs2 = (2 * sd_eff / ea) ** 2 if ea > 0 else np.inf
        log(f"  chiffres {lab} (écart {pct(ea, 1)} points par an) :\n    " + "\n    ".join(cells) +
            f"\n    suivi réel nécessaire pour t = 2 : {yrs2:.0f} ans (écart type annuel effectif {sd_eff * 100:.1f} points) ; "
            f"probabilité de faire moins bien que la société moyenne sur 1 an si l'écart est réel : "
            f"{np.mean((y1 - y1.mean() + ea) < 0) * 100:.0f} %")
    return out, ex_ann


# ---------------------------------------------------------------------------------------------------- 2. suivi réel rejoué
def lines(G):
    """Lignes du 📒 (10 par semaine) : semaine, société, rendements à 3 et 6 mois (rendements hebdomadaires écrêtés comme le
    portefeuille), société moyenne aux mêmes dates, drapeaux des signaux, variables des chances."""
    t1997, T, retw, mkw = G['t1997'], G['T'], G['retw'], G['mkw']
    L = np.cumsum(np.log1p(retw), axis=1)
    LM = np.cumsum(np.log1p(mkw))
    hot, bp8, wait, dem = G['hot'], G['bp8'], G['wait'], G['dem']
    rows = []
    for t in range(t1997, T - 27):
        s = G['SEL10'].get(t, [])
        for pos, i in enumerate(s):
            rows.append((t, i, np.exp(L[i, t + 13] - L[i, t]) - 1, np.exp(L[i, t + 26] - L[i, t]) - 1,
                         np.exp(LM[t + 13] - LM[t]) - 1, np.exp(LM[t + 26] - LM[t]) - 1,
                         int(hot[i, t]), int(bp8[i, t]), int(wait[i, t]), int(pos >= 8 and dem[i, t]),
                         G['v52'][i, t], G['mom'][i, t]))
    A = np.array(rows, dtype=float)
    keys = ('t', 'i', 'r3', 'r6', 'm3', 'm6', 'hot', 'bp', 'wait', 'bd', 'v52', 'mom')
    return {k: A[:, j] for j, k in enumerate(keys)}


def prefix(x, T, t):
    """somme par semaine puis somme cumulée (indice t + 1 = jusqu'à la semaine t comprise)"""
    s = np.zeros(T + 1)
    np.add.at(s, t.astype(int) + 1, x)
    return np.cumsum(s)


def part2_3(G, D):
    T, t1997 = G['T'], G['t1997']
    t = D['t'].astype(int)
    era = np.array([era_of(G, x) or '' for x in range(T)])
    e3, e6 = D['r3'] - D['m3'], D['r6'] - D['m6']
    mu6 = {el: e6[era[t] == el].mean() for el in ERAS3}
    mu3 = {el: e3[era[t] == el].mean() for el in ERAS3}
    g6 = {}
    for k, _, _ in SIGNALS:
        y = D[k] == 1
        g6[k] = {}
        for el in ERAS3:
            a_, b_ = (era[t] == el) & y, (era[t] == el) & ~y
            g6[k][el] = float(D['r6'][a_].mean() - D['r6'][b_].mean()) if a_.sum() >= 30 and b_.sum() >= 30 else 0.0
    log("\n=== 2. 📒 suivi réel rejoué (10 lignes par semaine, face à la société moyenne)")
    log("  écart moyen des lignes à 6 mois : " + ' · '.join(f"{el} {pct(mu6[el], 1)}" for el in ERAS3) +
        " ; à 3 mois : " + ' · '.join(f"{el} {pct(mu3[el], 1)}" for el in ERAS3))
    for k, lab, want in SIGNALS:
        log(f"  {lab:9s} écart avec / sans à 6 mois : " + ' · '.join(f"{el} {pct(g6[k][el], 1)}" for el in ERAS3) +
            f" ({int(D[k].sum())} lignes avec)")
    D_max = 156
    starts = np.arange(t1997, T - 27 - D_max)
    s_era = era[starts]
    dd = np.arange(D_max + 1)

    def path_sum(x, h):
        """somme de x sur les lignes des semaines mûres (résultat à h semaines connu) à chaque contrôle d = 0..D_max après le
        départ s, et nombre de semaines mûres : tableaux (départs × contrôles)"""
        PX = prefix(x, T, t)
        last = starts[:, None] + dd[None, :] - h
        ok = last >= starts[:, None]
        lastc = np.where(ok, last, starts[:, None] - 1)
        return PX[lastc + 1] - PX[starts[:, None]], np.where(ok, last - starts[:, None] + 1, 0)

    one = np.ones(len(t))
    N6, W6 = path_sum(one, 26)
    N3, W3 = path_sum(one, 13)
    # écart type de la moyenne après W semaines mûres, par période de départ (autour de la moyenne de la période)
    sdW = {6: {}, 3: {}}
    for h, x, mu, NN in ((6, e6, mu6, N6), (3, e3, mu3, N3)):
        hh = 26 if h == 6 else 13
        S, _ = path_sum(x, hh)
        with np.errstate(all='ignore'):
            m = S / NN
        for el in ERAS3:
            se = s_era == el
            for W in WGRID:
                col = W + hh - 1
                if col <= D_max:
                    sdW[h].setdefault(el, {})[W] = float(np.nanstd(m[se, col] - mu[el]))
    sdg = {k: {} for k, _, _ in SIGNALS}
    for k, _, _ in SIGNALS:
        y = (D[k] == 1).astype(float)
        ny, _ = path_sum(y, 26)
        sy, _ = path_sum(y * D['r6'], 26)
        nn, sn = N6 - ny, path_sum((1 - y) * D['r6'], 26)[0]
        with np.errstate(all='ignore'):
            gap = sy / ny - sn / nn
        for el in ERAS3:
            se = s_era == el
            for W in WGRID:
                col = W + 25
                if col > D_max:
                    continue
                v = gap[se, col]
                okv = (ny[se, col] >= 5) & (nn[se, col] >= 5)
                sdg[k].setdefault(el, {})[W] = float(np.nanstd(v[okv] - g6[k][el])) if okv.sum() > 20 else np.nan

    def sd_other(tab, el, W):
        v = [tab[o][W] for o in ERAS3 if o != el and W in tab.get(o, {}) and np.isfinite(tab[o][W])]
        return float(np.mean(v)) if v else np.nan

    def sd_all(tab, W):
        v = [tab[o][W] for o in ERAS3 if W in tab.get(o, {}) and np.isfinite(tab[o][W])]
        return float(np.mean(v)) if v else np.nan

    log("  écart type de la moyenne à 6 mois après W semaines mûres (points) : " +
        ', '.join(f"W {W} : {sd_all(sdW[6], W) * 100:.1f}" for W in WGRID if np.isfinite(sd_all(sdW[6], W))))
    log("  à 3 mois : " + ', '.join(f"W {W} : {sd_all(sdW[3], W) * 100:.1f}" for W in WGRID if np.isfinite(sd_all(sdW[3], W))))
    g_all = {k: float(np.mean([g6[k][el] for el in ERAS3])) for k, _, _ in SIGNALS}
    kap = PRUDENT6 / np.mean([mu6[el] for el in ERAS3])
    mu1_6, mu1_3 = PRUDENT6, kap * float(np.mean([mu3[el] for el in ERAS3]))
    for W in (13, 26, 52, 104):
        s = sd_all(sdW[6], W)
        if np.isfinite(s):
            log(f"  après {W} semaines mûres : un avantage prudent de {pct(mu1_6)} points à 6 mois pèse {mu1_6 / s:.1f} écart type")

    # ------------------------------------------------------------------ 3. auto-surveillance rejouée
    log("\n=== 3. Auto-surveillance rejouée (contrôle chaque semaine, 3 ans de suivi)")
    QGRID = (.8, .9, .95, .975, .99, .995)

    def sd_table(tab, el, wmax):
        return np.array([np.nan] + [interp(tab, el, W, sd_other) for W in range(1, wmax + 1)])

    def post0(m, s, mu1):
        """probabilité a posteriori de « avantage nul » contre « avantage mu1 », à égalité au départ (loi normale)"""
        with np.errstate(all='ignore'):
            z = np.clip((mu1 ** 2 - 2 * m * mu1) / (2 * s ** 2), -50, 50)
        p = 1 / (1 + np.exp(-z))
        return np.where(np.isfinite(p), p, 0.0)

    def first_time(A):
        return np.where(A.any(1), A.argmax(1), 10 ** 6)

    FT, P0 = {}, {}
    for scen in ('historique', 'intact', 'disparu', 'négatif'):
        if scen == 'historique':
            d6, d3 = np.zeros(len(t)), np.zeros(len(t))
        else:
            target = {'intact': mu1_6, 'disparu': 0.0, 'négatif': -mu1_6}[scen]
            d6 = np.array([mu6[era[x]] - target if era[x] else 0.0 for x in t])
            d3 = np.array([mu3[era[x]] - target * mu1_3 / mu1_6 if era[x] else 0.0 for x in t])
        S6, _ = path_sum(e6 - d6, 26)
        S3, _ = path_sum(e3 - d3, 13)
        with np.errstate(all='ignore'):
            m6, m3 = S6 / N6, S3 / N3
        cur = ((N6 >= 30) & (m6 < 0)) | ((N3 >= 30) & (m3 < -.05))
        ptot = np.zeros(cur.shape)
        for el in ERAS3:
            se = s_era == el
            for m, w, mu1, h in ((m6, W6, mu1_6, 6), (m3, W3, mu1_3, 3)):
                s = sd_table(sdW[h], el, int(w.max()))[w[se]]
                ptot[se] = np.maximum(ptot[se], np.where(w[se] >= 1, post0(m[se], s, mu1), 0.0))
        cur_sig, psig = np.zeros_like(cur), np.zeros(cur.shape)
        r6 = D['r6'] - d6
        for k, _, want in SIGNALS:
            y = (D[k] == 1).astype(float)
            gk = np.array([g6[k][era[x]] if era[x] else 0.0 for x in t])
            rk = r6 - y * gk if scen in ('disparu', 'négatif') else r6
            ny, _ = path_sum(y, 26)
            sy, _ = path_sum(y * rk, 26)
            sn, _ = path_sum((1 - y) * rk, 26)
            nn = N6 - ny
            with np.errstate(all='ignore'):
                gap = sy / ny - sn / nn
            both = (ny >= 30) & (nn >= 30)
            cur_sig |= both & ((gap <= 0) if want > 0 else (gap >= 0))
            for el in ERAS3:
                se = s_era == el
                s = sd_table(sdg[k], el, int(W6.max()))[W6[se]]
                psig[se] = np.maximum(psig[se], np.where(both[se], post0(gap[se], s, g_all[k]), 0.0))
        FT[(scen, 'actuelle')] = first_time(cur | cur_sig)
        FT[(scen, 'actuelle sans les signaux')] = first_time(cur)
        P0[scen] = (ptot, psig)

    def rates(first, se):
        return [float(np.mean(first[se] <= 52 * yy)) for yy in (1, 2, 3)]

    def new_first(scen, q, sig=True):
        ptot, psig = P0[scen]
        return first_time((ptot >= q) | ((psig >= q) if sig else False))

    # seuil choisi sur les deux autres périodes : le plus bas qui y donne au plus 10 % de fausses alertes en 3 ans (chacune)
    qsel = {}
    for el in ERAS3:
        ok_q = [q for q in QGRID if all(rates(new_first('intact', q), s_era == o)[2] <= .10 for o in ERAS3 if o != el)]
        qsel[el] = ok_q[0] if ok_q else QGRID[-1]
    q_all = ([q for q in QGRID if all(rates(new_first('intact', q), s_era == o)[2] <= .10 for o in ERAS3)] or [QGRID[-1]])[0]
    log("  seuil de probabilité choisi sur les deux autres périodes : " + ' · '.join(f"{el} {qsel[el] * 100:g} %" for el in ERAS3) +
        f" ; sur les trois : {q_all * 100:g} %")
    log("  fausses alertes du seuil selon la période de départ (avantage intact, 3 ans) : " + ' ; '.join(
        f"{q * 100:g} % → " + '/'.join(f"{rates(new_first('intact', q), s_era == el)[2] * 100:.0f}" for el in ERAS3) for q in QGRID))
    names = (('historique', "fausses alertes, avantage tel qu'en 1998-2026"), ('intact', 'fausses alertes, avantage prudent (+4 points)'),
             ('disparu', 'alertes justes, avantage disparu'), ('négatif', 'alertes justes, avantage négatif (−4 points)'))
    tab = {}
    for lab in ('actuelle', 'actuelle sans les signaux', 'proposée', 'proposée sans les signaux'):
        log(f"  règle {lab} (part des suivis alertés en 1 / 2 / 3 ans) :")
        for scen, nm in names:
            cells = []
            for el in ERAS3:
                se = s_era == el
                f = FT[(scen, lab)] if lab.startswith('actuelle') else new_first(scen, qsel[el], sig=not lab.endswith('signaux'))
                tab[(scen, lab, el)] = rates(f, se)
                cells.append(f"{el} {' / '.join(f'{v * 100:.0f}' for v in tab[(scen, lab, el)])} %")
            log(f"    {nm:48s} " + ' · '.join(cells))
    ok = True
    for el in ERAS3:
        fa_c, fa_n = tab[('intact', 'actuelle', el)][2], tab[('intact', 'proposée', el)][2]
        de_c, de_n = tab[('disparu', 'actuelle', el)][2], tab[('disparu', 'proposée', el)][2]
        ppv_c = de_c / (de_c + fa_c) if de_c + fa_c > 0 else np.nan
        ppv_n = de_n / (de_n + fa_n) if de_n + fa_n > 0 else np.nan
        log(f"  {el} : fausses alertes en 3 ans {fa_c * 100:.0f} % → {fa_n * 100:.0f} % ; alertes justifiées "
            f"{ppv_c * 100 if np.isfinite(ppv_c) else float('nan'):.0f} % → {ppv_n * 100 if np.isfinite(ppv_n) else float('nan'):.0f} %")
        ok &= bool(fa_n < fa_c and np.isfinite(ppv_n) and (not np.isfinite(ppv_c) or ppv_n > ppv_c))
    log(f"\nDÉCISION 3 (règle fixée avant le calcul) : auto-surveillance par probabilité a posteriori → "
        f"{'ADOPTÉE' if ok else 'REJETÉE'} (seuil {q_all * 100:g} %)")
    params = dict(q=q_all, mu6=round(mu1_6, 4), mu3=round(mu1_3, 4), hist6={el: round(mu6[el], 4) for el in ERAS3},
                  sd6={W: round(sd_all(sdW[6], W), 4) for W in WGRID if np.isfinite(sd_all(sdW[6], W))},
                  sd3={W: round(sd_all(sdW[3], W), 4) for W in WGRID if np.isfinite(sd_all(sdW[3], W))},
                  signals={k: dict(gap=round(g_all[k], 4),
                                   sd={W: round(sd_all(sdg[k], W), 4) for W in WGRID if np.isfinite(sd_all(sdg[k], W))})
                           for k, _, _ in SIGNALS})
    log("PARAMÈTRES " + json.dumps(params, ensure_ascii=False))
    return ok


def interp(tab, el, W, sd_other):
    """écart type pour W semaines mûres (interpolation log-log entre les points de WGRID), mesuré sur les deux autres périodes"""
    ws = [w for w in WGRID if np.isfinite(sd_other(tab, el, w))]
    if not ws:
        return np.nan
    if W <= ws[0]:
        return sd_other(tab, el, ws[0])
    if W >= ws[-1]:
        return sd_other(tab, el, ws[-1]) * np.sqrt(ws[-1] / W)
    for a, b in zip(ws, ws[1:]):
        if a <= W <= b:
            ya, yb = np.log(sd_other(tab, el, a)), np.log(sd_other(tab, el, b))
            return float(np.exp(ya + (yb - ya) * (np.log(W) - np.log(a)) / (np.log(b) - np.log(a))))
    return np.nan


# ---------------------------------------------------------------------------------------------------- 4. chances par société
def part4(G, D):
    T = G['T']
    t = D['t'].astype(int)
    era = np.array([era_of(G, x) or '' for x in range(T)])[t]
    ok = np.isfinite(D['v52']) & (D['v52'] > 0) & np.isfinite(D['mom'])
    X = np.column_stack([np.ones(len(t)), np.log(np.clip(D['v52'], .1, 2)), np.clip(D['mom'], -.5, 3), D['hot']])
    log("\n=== 4. Chances à 6 mois de chaque société (apprises sur deux périodes, jugées sur la troisième)")
    events = (('hausse', D['r6'] > 0), ('+20 % ou mieux', D['r6'] >= .2), ('−25 % ou pire', D['r6'] <= -.25))
    verdict = {}
    for lab, yv in events:
        y = yv.astype(float)
        cells, good = [], True
        for el in ERAS3:
            te, tr = ok & (era == el), ok & (era != el) & (era != '')
            mu, sd = X[tr, 1:].mean(0), X[tr, 1:].std(0)
            Xs = X.copy()
            Xs[:, 1:] = (X[:, 1:] - mu) / sd
            w = logit_fit(Xs[tr], y[tr], l2=1.0)
            p = 1 / (1 + np.exp(-np.clip(Xs[te] @ w, -30, 30)))
            base = y[tr].mean()
            bs, b0 = np.mean((p - y[te]) ** 2), np.mean((base - y[te]) ** 2)
            bss = 1 - bs / b0
            q10, q90 = np.percentile(p, [10, 90])
            hi, lo = p >= q90, p <= q10
            cells.append(f"{el} : score de Brier {bss * 100:+.1f} % ; prévu 10 % / 90 % des sociétés {q10 * 100:.0f} / {q90 * 100:.0f} %, "
                         f"observé dans ces groupes {y[te][lo].mean() * 100:.0f} / {y[te][hi].mean() * 100:.0f} % (fréquence "
                         f"d'ensemble {base * 100:.0f} %, observée {y[te].mean() * 100:.0f} %)")
            good &= bss > 0
        verdict[lab] = good
        log(f"  {lab} :\n    " + "\n    ".join(cells) + f"\n    → {'affichable' if good else 'pas mieux que la fréquence d’ensemble'}")
    wfull = {}
    for lab, yv in events:
        tr = ok & (era != '')
        mu, sd = X[tr, 1:].mean(0), X[tr, 1:].std(0)
        Xs = X.copy()
        Xs[:, 1:] = (X[:, 1:] - mu) / sd
        w = logit_fit(Xs[tr], yv.astype(float)[tr], l2=1.0)
        wfull[lab] = dict(w=[round(float(v), 4) for v in w], mu=[round(float(v), 4) for v in mu], sd=[round(float(v), 4) for v in sd])
    log("COEFFICIENTS " + json.dumps(wfull, ensure_ascii=False))
    log(f"\nDÉCISION 4 (règle fixée avant le calcul) : chances par société affichables pour : "
        f"{', '.join(k for k, v in verdict.items() if v) or 'aucune'}")
    return verdict


def main():
    t0 = time.time()
    G = load()
    log(f"données prêtes en {time.time() - t0:.0f} s")
    part1(G)
    D = lines(G)
    log(f"\n📒 rejoué : {len(D['t'])} lignes, {len(set(D['t'].astype(int)))} semaines")
    part2_3(G, D)
    part4(G, D)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
