"""Idées restées sans test sans biais du survivant (28/11/2026, François : « Faire ce qui est pertinent et vérifier que toutes les
idées/méthodes/stratégies ont été testées »).

Univers C de survivant_eodhd.py (12 bourses de l'EEE, sociétés retirées de la cote comprises, liquidité connue à la date). Mesure
commune des événements : écart de rendement à 6 mois avec la société moyenne de la même semaine, une entrée par société et par
semestre, t sur les moyennes de chaque semestre. Portefeuilles : sélection de base (4 🎯 + 1 📣, sans le filtre des comptes),
tranches de 26 semaines, frais 0,3 % par sens, protection −30 % (sim30).

1. Dirigeants (achats publiés, le critère d'origine de l'outil), testés jusqu'ici sur des cours Yahoo de sociétés encore cotées :
   historique long de l'outil (Paris depuis 2021, Stockholm depuis mi-2016), lu comme le calcul du soir (inities_eodhd.js : achats
   volontaires de personnes physiques, 100 000 € au moins par acheteur en 14 jours, déclarés à 30 jours au plus ; toutes les ventes).
   Événements : achat publié, achat du DG ou du DAF, 2 acheteurs ou plus en 14 jours, achat avec une décote d'au moins 25 % sous le
   plus haut d'un an, achat dans la zone du 🎯, passage en vendeurs nets sur 3 mois, vente du DG ou du DAF. Puis la sélection avec
   les points de dirigeants du calcul du soir (ES.rankInsiders : achat +3, DG ou DAF +1, plusieurs acheteurs +1, vendeurs nets −10,
   vente du DG ou du DAF −5, entre −15 et +5) ajoutés à la note, face à la sélection sans. Règle fixée avant : les points (règle
   actuelle) ne sont retirés (proposition) que si la sélection sans fait mieux sur 2016-2020 et sur 2021-2026 avec t ≥ 3.
2. 🐻 ventes à découvert (Paris, positions publiques AMF depuis fin 2012, testé jusqu'ici sur des cours Yahoo) : zone du 🎯 avec
   ou sans position publiée de 0,5 % ou plus ; sélection avec l'écart 🐻 (règle actuelle) face à la sélection sans. Règle fixée
   avant : l'écart n'est retiré (proposition) que si la sélection sans fait mieux sur 2013-2017 et sur 2018-2026 avec t ≥ 3.
3. Les screeners ProRealTime de François, sur cours journaliers EODHD (jamais testés en entier) : Parrish Minimal v2 (mai 2026 :
   OBV lissé en hausse sur 120 séances, cours au-dessus de la moyenne 200 séances, RSI 14 < 70, pas de séance à −3 % sur 5 jours,
   sortie d'une base de 60 séances à 5 % au plus du plus haut de 120 séances sur 1,3 fois le volume moyen, dans les 5 dernières
   séances) ; Wyckoff phase D v1 (juin 2026 : 6 critères sur 7 parmi fourchette de 60 séances < 20 %, Bollinger resserrées à moins
   de la moitié de leur moyenne de 60 séances, OBV en hausse sur 30 séances, au-dessus de la moyenne 200, volume < 1,5 fois la
   moyenne, cours dans les 60-90 % de la fourchette, RSI < 70 ; et cours > 5 €, pas de baisse de 5 % sur 5 séances, ATR < 5 % du
   cours, pas de baisse de 30 % sur 6 mois ; balayage le vendredi) ; points et figures (novembre 2026 : case 2 %, retournement de
   3 cases, double ou triple sommet cassé depuis 15 séances au plus sur 1,2 fois le volume moyen, colonne de X, cours au-dessus de
   la cassure, RSI < 75, au-dessus de la moyenne 50, moyenne 20 au-dessus de la moyenne 50, cours > 1 €). Sociétés liquides à la
   date (≥ 1 M€ par jour sur 26 semaines). Règle fixée avant : un screener « bat la moyenne » s'il fait mieux que la société moyenne
   dans chaque période avec t ≥ 3, et ne serait utile à la sélection que s'il fait mieux que la zone du 🎯 dans chaque période.
4. « Grenouille dans la casserole » (Da, Gurun et Warachka, 2014) : momentum fait de petites hausses régulières plutôt que de
   quelques bonds ; discrétion = signe de la hausse sur 12 mois (sans le dernier) × (part des séances en baisse − part en hausse).
   Zone du 🎯 par tiers ; sélection sans le tiers le plus « discret ». Règle fixée avant : mieux dans chaque période avec t ≥ 3.
5. Screener « Momentum PEA » proposé en octobre 2026 (repère simple) : chaque mois, les 10 plus fortes hausses sur 12 mois (sans le
   dernier) parmi les sociétés liquides au-dessus de leur moyenne 200 séances et à volatilité sur 60 séances < 45 %, revente
   seulement hors des 20 premières ou sous la moyenne 200 : face à la sélection.
6. Portefeuille concentré « 2 à 3 lignes » (méthode de François avant l'outil) : 3 lignes à la fois (puis 5 et 10), les premières de
   la sélection dès qu'une place se libère, gardées 26 semaines, protection −30 %. Règle fixée avant : mieux que les tranches dans
   chaque période avec t ≥ 3.
Lancé par « Recherche (à la demande) » (script survivant_restes.py), environ 30 minutes, environ 8 300 appels EODHD (cours
hebdomadaires puis journaliers). Cours en mémoire seulement ; fichier temporaire des dirigeants effacé aussitôt ; la clé n'est jamais
affichée.
"""
import bisect
import concurrent.futures as cf
import gc
import json
import os
import subprocess
import tempfile
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

import revue_pistes as RP
import shorts as SHM
import survivant_eodhd as SE
import survivant_valeur as SV

log = SE.log
PF_BOX, PF_REV = np.log(1.02), 3
CO_FROM = {'FR': '2021-02-01', 'SE': '2016-08-01'}  # couverture de l'historique long des dirigeants (AMF, FI)


def insider_rows():
    """Lecture des dirigeants par inities_eodhd.js (fichier temporaire effacé aussitôt)."""
    fd, pout = tempfile.mkstemp(suffix='.json', dir='.')
    os.close(fd)
    try:
        r = subprocess.run(['node', 'inities_eodhd.js', pout], capture_output=True, text=True, timeout=1200)
        log('  ' + (r.stdout.strip() or r.stderr.strip()[-300:]))
        if r.returncode:
            raise RuntimeError('inities_eodhd.js a échoué')
        return json.load(open(pout))
    finally:
        if os.path.exists(pout):
            os.remove(pout)


def cluster_count(buys):
    """Acheteurs distincts au plus dans une fenêtre glissante de 14 jours (ES.clusterInfo)."""
    pts = sorted((b[1], b[4]) for b in buys if b[4])
    best = 0
    for k in range(len(pts)):
        end = (date.fromisoformat(pts[k][0][:10]) + timedelta(days=13)).isoformat()
        best = max(best, len({p[1] for p in pts[k:] if p[0] <= end}))
    return best


def insider_weeks(DI, isin, dates, T):
    """Points de dirigeants du calcul du soir chaque vendredi (fenêtre de 3 mois par date de publication) et événements."""
    N = len(isin)
    PTS = np.zeros((N, T), np.int8)
    EV = {k: np.zeros((N, T), bool) for k in ('buy', 'ceo', 'multi', 'net', 'ceosale')}
    COV = np.zeros((N, T), bool)
    fr = [date.fromisoformat(d) for d in dates]
    for i, code in enumerate(isin):
        cc = code[:2]
        if cc not in CO_FROM:
            continue
        t0 = int(np.searchsorted(dates, CO_FROM[cc]))
        COV[i, t0:] = True
        rows = DI.get(code)
        if not rows:
            continue
        rows = sorted(rows, key=lambda r: r[0][:10])
        av = [r[0][:10] for r in rows]
        prev_net = False
        for t in range(t0, T):
            lo, hi = (fr[t] - timedelta(days=91)).isoformat(), fr[t].isoformat()
            wk0 = (fr[t] - timedelta(days=7)).isoformat()
            win = rows[bisect.bisect_right(av, lo):bisect.bisect_right(av, hi)]
            if not win:
                prev_net = False
                continue
            buys = [r for r in win if r[2] == 'a']
            sells = [r for r in win if r[2] == 'v']
            ceo = any(b[3] for b in buys)
            multi = cluster_count(buys) >= 2 if len(buys) > 1 else False
            be = sum(b[5] or 0 for b in buys)
            se = sum(s[5] or 0 for s in sells)
            net = se > be and se > 0
            csale = any(s[3] for s in sells)
            p = (3 if buys else 0) + (1 if ceo else 0) + (1 if multi else 0) - (10 if net else 0) - (5 if csale else 0)
            PTS[i, t] = max(-15, min(5, p))
            new = [r for r in win if r[0][:10] > wk0]
            EV['buy'][i, t] = any(r[2] == 'a' for r in new)
            EV['ceo'][i, t] = any(r[2] == 'a' and r[3] for r in new)
            EV['multi'][i, t] = multi and EV['buy'][i, t]
            EV['net'][i, t] = net and not prev_net
            EV['ceosale'][i, t] = any(r[2] == 'v' and r[3] for r in new)
            prev_net = net
    return PTS, EV, COV


def bear_weeks(rows, dates, T):
    """Positions courtes publiques AMF (≥ 0,5 %) en cours chaque vendredi, sociétés de Paris."""
    sp = SHM.amf()
    idx = {}
    for i, r in enumerate(rows):
        if r['ex'] == 'PA' and r.get('isin'):
            idx.setdefault(r['isin'], []).append(i)
    SHP = np.zeros((len(rows), T), np.float32)
    dd = np.array(dates)
    for code, pct, st, en in zip(sp['code'], sp['pct'], sp['start'], sp['end']):
        for i in idx.get(code, []):
            a = int(np.searchsorted(dd, str(st.date()), side='left'))
            b = int(np.searchsorted(dd, str(en.date()), side='left')) if pd.notna(en) else T
            if b > a:
                SHP[i, a:b] += pct
    return SHP, int(np.searchsorted(dd, '2013-01-01'))


def rsi(c, n=14):
    d = np.diff(c, prepend=np.nan)
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().values
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().values
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.where(dn > 0, 100 - 100 / (1 + up / dn), 100.0)


def pf_breakouts(c):
    """Points et figures sur clôtures (case 2 %, retournement de 3 cases) : jour de cassure d'un double / triple sommet, niveau
    cassé, colonne de X en cours."""
    n = len(c)
    dtb, ttb, xcol = np.zeros(n, bool), np.zeros(n, bool), np.zeros(n, bool)
    lvl = np.full(n, np.nan)
    b = np.floor(np.log(c) / PF_BOX).astype(int)
    d, top, bot, b0, xt = 0, b[0], b[0], b[0], []
    for k in range(1, n):
        bk = b[k]
        if d == 0:
            if bk >= b0 + PF_REV:
                d, top = 1, bk
            elif bk <= b0 - PF_REV:
                d, bot = -1, bk
        elif d == 1:
            if bk > top:
                if xt and top <= xt[-1] < bk:
                    dtb[k], lvl[k] = True, np.exp((xt[-1] + 1) * PF_BOX)
                    ttb[k] = len(xt) >= 2 and xt[-2] == xt[-1]
                top = bk
            elif bk <= top - PF_REV:
                xt.append(top)
                d, bot = -1, bk
        else:
            if bk < bot:
                bot = bk
            elif bk >= bot + PF_REV:
                d, top = 1, bk
                if xt and bk > xt[-1]:
                    dtb[k], lvl[k] = True, np.exp((xt[-1] + 1) * PF_BOX)
                    ttb[k] = len(xt) >= 2 and xt[-2] == xt[-1]
        xcol[k] = d == 1
    return dtb, ttb, lvl, xcol


def daily_signals(bars, Pw_i, fri, fx_i):
    """Signaux journaliers d'une société ramenés au dernier jour de chaque semaine : Parrish, Wyckoff, points et figures (double ou
    triple sommet), triple sommet seul, discrétion (grenouille), volatilité sur 60 séances. Jours aberrants (clôture à plus de 25 %
    de la clôture hebdomadaire nettoyée) écartés."""
    T = len(fri)
    out = {k: np.zeros(T, bool) for k in ('par', 'wyk', 'pf', 'pf3')}
    fid, v60 = np.full(T, np.nan, np.float32), np.full(T, np.nan, np.float32)
    rec = []
    for x in bars or []:
        try:
            c, a = float(x.get('close') or 'nan'), float(x.get('adjusted_close') or 'nan')
            h, lo, v = float(x.get('high') or 'nan'), float(x.get('low') or 'nan'), float(x.get('volume') or 0)
        except (TypeError, ValueError):
            continue
        if c > 0 and a > 0 and h > 0 and lo > 0:
            rec.append((x['date'], a, h * a / c, lo * a / c, v, c))
    if len(rec) < 300:
        return out, fid, v60, 0
    day = np.array([np.datetime64(r[0], 'D').astype(int) for r in rec])
    wk = np.searchsorted(fri, day, side='left')
    arr = np.array([r[1:] for r in rec], float)
    ok = wk < T
    with np.errstate(invalid='ignore', divide='ignore'):
        ref = np.where(ok, Pw_i[np.minimum(wk, T - 1)], np.nan)
        dev = np.abs(np.log(arr[:, 0] / ref))
    keep = ok & ~(dev > np.log(1.25))
    nbad = int((ok & (dev > np.log(1.25))).sum())
    day, wk, arr = day[keep], wk[keep], arr[keep]
    if len(day) < 300:
        return out, fid, v60, nbad
    c, h, lo, v, raw = (arr[:, k] for k in range(5))
    S = pd.Series(c)
    sma = lambda x, n: pd.Series(x).rolling(n).mean().values  # noqa: E731
    ma20, ma50, ma200 = sma(c, 20), sma(c, 50), sma(c, 200)
    vma20 = sma(v, 20)
    r_ = S.pct_change().values
    obv = np.cumsum(np.nan_to_num(np.sign(np.diff(c, prepend=c[0]))) * v)
    sobv = pd.Series(obv).ewm(span=20, adjust=False).mean().values
    rs = rsi(c)
    eur = raw / fx_i[np.minimum(wk, T - 1)]
    with np.errstate(invalid='ignore', divide='ignore'):
        # Parrish Minimal v2
        acc = sobv > np.roll(sobv, 120)
        acc[:120] = False
        minr5 = pd.Series(r_).rolling(5).min().values
        hs = pd.Series(h).shift(5)
        res60, hi120 = hs.rolling(60).max().values, hs.rolling(120).max().values
        brk = (c > res60) & (v >= 1.3 * np.roll(vma20, 1))
        brk5 = pd.Series(brk.astype(float)).rolling(5).max().values > 0
        par = acc & (c > ma200) & (rs < 70) & (minr5 > -.03) & (res60 >= .95 * hi120) & brk5 & (c > res60)
        # Wyckoff phase D v1
        hh60, ll60 = pd.Series(h).rolling(60).max().values, pd.Series(lo).rolling(60).min().values
        bbw = 4 * S.rolling(20).std(ddof=0).values / ma20 * 100
        bbm = pd.Series(bbw).rolling(60).mean().values
        obv30 = obv > np.roll(obv, 30)
        obv30[:30] = False
        pos = (c - ll60) / (hh60 - ll60) * 100
        prev = np.roll(c, 1)
        prev[0] = np.nan
        tr = np.nanmax(np.vstack([h - lo, np.abs(h - prev), np.abs(lo - prev)]), 0)
        atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
        sc = (((hh60 - ll60) / ll60 * 100 < 20).astype(int) + (bbw < .5 * bbm) + obv30 + (c > ma200) + (v / vma20 < 1.5)
              + ((pos >= 60) & (pos <= 90)) + (rs < 70))
        ch5 = c / np.roll(c, 5) - 1
        ch120 = c / np.roll(c, 120) - 1
        wyk = (sc >= 6) & (ch5 > -.05) & (atr / c < .05) & (eur > 5) & (ch120 > -.30)
        wyk[:200] = False
        # points et figures
        dtb, ttb, lvl, xcol = pf_breakouts(c)
        bk_ok = (dtb & (v > 1.2 * np.roll(vma20, 1)))
        last_k = pd.Series(np.where(bk_ok, np.arange(len(c)), np.nan)).ffill().values
        last_t = pd.Series(np.where(bk_ok & ttb, np.arange(len(c)), np.nan)).ffill().values
        lv = pd.Series(np.where(bk_ok, lvl, np.nan)).ffill().values
        lv3 = pd.Series(np.where(bk_ok & ttb, lvl, np.nan)).ffill().values
        k_ = np.arange(len(c))
        base = xcol & (rs < 75) & (c > ma50) & (ma20 > ma50) & (eur > 1)
        pf = base & (k_ - last_k <= 15) & (c > lv)
        pf3 = base & (k_ - last_t <= 15) & (c > lv3)
        # grenouille dans la casserole et volatilité sur 60 séances
        pos_, neg_ = (r_ > 0).astype(float), (r_ < 0).astype(float)
        npos = pd.Series(pos_).rolling(231).sum().shift(21).values
        nneg = pd.Series(neg_).rolling(231).sum().shift(21).values
        pret = S.shift(21).values / S.shift(252).values - 1
        fip = np.sign(pret) * (nneg - npos) / 231
        vol60 = pd.Series(r_).rolling(60).std().values * np.sqrt(252)
    # dernier jour de chaque semaine
    u, first_rev = np.unique(wk[::-1], return_index=True)
    last = len(wk) - 1 - first_rev
    for nm, sig in (('par', par), ('wyk', wyk), ('pf', pf), ('pf3', pf3)):
        out[nm][u] = np.nan_to_num(sig[last]).astype(bool)
    fid[u] = fip[last]
    v60[u] = vol60[last]
    return out, fid, v60, nbad


def main():
    u, err = SE.get('user')
    used = int((u or {}).get('apiRequests') or 0)
    if str((u or {}).get('apiRequestsDate') or '') != time.strftime('%Y-%m-%d', time.gmtime()):
        used = 0
    if used > 90000:  # ce test en prend environ 8 300, limite 100 000 par jour
        log(f"{used} appels EODHD déjà utilisés aujourd'hui : relancer après la remise à zéro du compteur")
        return
    D = SE.prepare()
    if D is None:
        return
    P, V, liq, cols, secs, dates, T, t2001, ERAS, t00, dl, rows = (D[k] for k in (
        'P', 'V', 'liq', 'cols', 'secs', 'dates', 'T', 't2001', 'ERAS', 't00', 'dl', 'rows'))
    N = len(cols)
    G = SE.chain(P, V, dates, cols, secs, liq >= SE.LIQ)
    del D, V
    gc.collect()
    G['t1997'] = t2001
    G['retw'] = retw = np.clip(np.nan_to_num(G['r1']), -.95, 3.0)
    okn = G['okn']
    G['mkw'] = mkw = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
    mom, trend, s26, mpn, v52, Pw, m40 = (G[k] for k in ('mom', 'trend', 's26', 'mpn', 'v52', 'P', 'm40'))
    zone = okn & trend & (s26 >= .14) & (mom >= .3) & (mom <= 2) & ~(mpn < 1 / 3) & ~(v52 >= .8)
    Cc = np.concatenate([np.zeros((N, 1)), np.cumsum(np.log1p(retw), 1)], 1)
    M = np.full(T, np.nan)
    for t in range(T - 28):
        fw = np.expm1(Cc[:, t + 27] - Cc[:, t + 1])
        M[t] = np.nanmean(fw[okn[:, t]]) if okn[:, t].sum() > 30 else np.nan
    isin = [r.get('isin') or '' for r in rows]
    dd = np.array(dates)
    log(f"\nUnivers C : {N} sociétés ; {T} semaines")

    def ex6(i, t):
        return np.expm1(Cc[i, t + 27] - Cc[i, t + 1]) - M[t]

    def events(mask, a=None, b=None):
        a = t2001 if a is None else a
        b = T - 28 if b is None else min(b, T - 28)
        ev = []
        for i in np.where(mask[:, a:b].any(1))[0]:
            last = -1
            for t in np.where(mask[i, a:b])[0] + a:
                sem = (t - t2001) // 26
                if sem != last and okn[i, t]:
                    ev.append((int(i), int(t)))
                    last = sem
        return ev

    def ev_line(lab, ev, spans):
        means, cells, allx, blk = [], [], [], {}
        for el, a, b in spans:
            xs = []
            for i, t in ev:
                if a <= t < b:
                    x = ex6(i, t)
                    if np.isfinite(x):
                        xs.append(x)
                        blk.setdefault((t - t2001) // 26, []).append(x)
            means.append(np.mean(xs) * 100 if xs else np.nan)
            cells.append(f"{el} {means[-1]:+5.1f} ({len(xs)})")
            allx += xs
        bm = np.array([np.mean(v) for v in blk.values()])
        tv = bm.mean() / (bm.std(ddof=1) / np.sqrt(len(bm))) if len(bm) > 2 else np.nan
        gone = np.mean([dl[i] for i, _ in ev]) * 100 if ev else np.nan
        log(f"  {lab:46s} {np.mean(allx) * 100 if allx else np.nan:+5.1f} (t {tv:4.1f}, {len(allx)} cas, {gone:.0f} % de sociétés "
            f"disparues depuis) · " + ' · '.join(cells))
        return means, tv

    SEL0 = G['SEL']

    def run(S):
        G['SEL'] = S
        R1 = G['sim30']()
        G['SEL'] = SEL0
        return R1

    def seg(R, a, b):
        return R[a - t2001:b - t2001]
    an = lambda R: (np.prod(1 + R) ** (52 / len(R)) - 1) * 100 if len(R) else np.nan  # noqa: E731

    def dd_(R):
        e = np.cumprod(1 + R)
        return (e / np.maximum.accumulate(e) - 1).min() * 100

    def line(lab, R, spans=ERAS):
        Rt = seg(R, spans[0][1], spans[-1][2]) if spans is not ERAS else R
        log(f"  {lab:46s} {an(Rt):+5.1f} %/an, pire baisse {dd_(Rt):.0f} % (" +
            ' · '.join(f"{el} {an(seg(R, a, b)):+.1f} / {dd_(seg(R, a, b)):.0f} %" for el, a, b in spans) + ')')

    def cmp(R, ref, spans=ERAS):
        d = R - ref
        sg = [seg(d, a, b).mean() * 5200 for _, a, b in spans]
        a0, b0 = spans[0][1] - t2001, spans[-1][2] - t2001
        x = d[a0:b0]
        blk = np.array([x[k:k + 26].sum() for k in range(0, len(x) - 25, 26)])
        with np.errstate(invalid='ignore', divide='ignore'):
            return sg, blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))

    def cells(sg, spans=ERAS):
        return ' · '.join(f"{el} {x:+5.1f}" for (el, _, _), x in zip(spans, sg))

    R0 = run(SEL0)
    Rm = mkw[t2001 + 1:T]
    pick = RP.make_pick(G)
    log(f"copie de la sélection identique à l'originale : {all(pick(t) == list(SEL0[t]) for t in range(t2001, T - 1, 13))}")

    # 1. dirigeants
    try:
        log("\n1. Dirigeants, sans biais du survivant (historique long de l'outil, cours EODHD des sociétés disparues comprises)")
        DI = insider_rows()
        PTS, EV, COV = insider_weeks(DI, isin, dates, T)
        del DI
        tS, t21 = int(np.searchsorted(dd, CO_FROM['SE'])), int(np.searchsorted(dd, '2021-01-01'))
        SP = [('2016-2020', tS, t21), ('2021-2026', t21, T - 1)]
        cov = COV & okn
        log(f"  sociétés investissables couvertes : {int(cov[:, t21].sum())} en 2021, {int(cov[:, T - 2].sum())} aujourd'hui ; "
            f"semaines avec des points de dirigeants non nuls : {int(((PTS != 0) & cov).sum())} sur {int(cov.sum())}")
        hi52 = pd.DataFrame(Pw.T).rolling(52, min_periods=26).max().values.T
        with np.errstate(invalid='ignore'):
            disc = Pw <= .75 * hi52
        log("  Écart à 6 mois avec la société moyenne (points ; cas ; part de sociétés disparues) · par période")
        ev_line('zone du 🎯 (sociétés couvertes, repère)', events(zone & cov, tS), SP)
        for lab, m in (('achat publié', EV['buy']), ('achat du DG ou du DAF', EV['ceo']), ('2 acheteurs ou plus en 14 jours', EV['multi']),
                       ('achat avec une décote ≥ 25 %', EV['buy'] & disc), ('achat dans la zone du 🎯', EV['buy'] & zone),
                       ('passage en vendeurs nets sur 3 mois', EV['net']), ('vente du DG ou du DAF', EV['ceosale'])):
            ev_line(lab, events(m & cov, tS), SP)
        G2 = dict(G, note=G['note'] + PTS.astype(float))
        pk = RP.make_pick(G2)
        S_ins = {t: pk(t) for t in range(t2001, T - 1)}
        diff = np.mean([S_ins[t] != list(SEL0[t]) for t in range(tS, T - 1)]) * 100
        R_ins = run(S_ins)
        log(f"  sélection avec les points de dirigeants dans la note (règle actuelle du calcul du soir) : semaines différentes "
            f"{diff:.0f} % sur 2016-2026")
        line('sélection avec les points (règle actuelle)', R_ins, SP)
        line('sélection sans', R0, SP)
        sg, tv = cmp(R0, R_ins, SP)
        v = ' → SANS FAIT MIEUX : retrait à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → points gardés'
        log(f"    sans − avec : {cells(sg, SP)} pts/an (t {tv:4.1f}){v}")
        del PTS, EV, COV, G2, pk, S_ins
        gc.collect()
    except Exception as e:  # une partie qui échoue n'empêche pas les autres
        log(f"  dirigeants : échec ({type(e).__name__} : {str(e)[:200]})")

    # 2. 🐻
    try:
        log("\n2. 🐻 ventes à découvert (Paris, positions publiques AMF), sans biais du survivant")
        SHP, t13 = bear_weeks(rows, dates, T)
        t18 = int(np.searchsorted(dd, '2018-01-01'))
        SP2 = [('2013-2017', t13, t18), ('2018-2026', t18, T - 1)]
        par = np.array([r['ex'] == 'PA' for r in rows])[:, None]
        bear = SHP >= .5
        z = zone & par
        log(f"  sociétés de Paris investissables avec une position publiée ≥ 0,5 % : {int((bear & okn)[:, t18].sum())} en 2018, "
            f"{int((bear & okn)[:, T - 2].sum())} aujourd'hui")
        ev_line('zone du 🎯 à Paris, sans position publiée', events(z & ~bear, t13), SP2)
        ev_line('zone du 🎯 à Paris, avec (🐻)', events(z & bear, t13), SP2)
        ev_line('toutes les sociétés de Paris avec 🐻', events(okn & par & bear, t13), SP2)
        pkb = RP.make_pick(dict(G, okn=okn & ~(par & bear)))
        R_b = run({t: pkb(t) for t in range(t2001, T - 1)})
        line('sélection avec l\'écart 🐻 (règle actuelle)', R_b, SP2)
        line('sélection sans', R0, SP2)
        sg, tv = cmp(R0, R_b, SP2)
        v = ' → SANS FAIT MIEUX : retrait à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → écart 🐻 gardé'
        log(f"    sans − avec : {cells(sg, SP2)} pts/an (t {tv:4.1f}){v}")
        del SHP, bear, pkb
        gc.collect()
    except Exception as e:
        log(f"  🐻 : échec ({type(e).__name__} : {str(e)[:200]})")

    # 3 à 5 : cours journaliers
    fri = np.array([np.datetime64(d, 'D').astype(int) for d in dates])
    FXd = SV.fx_table({r['cur'] for r in rows}, dates)
    SIG = {k: np.zeros((N, T), bool) for k in ('par', 'wyk', 'pf', 'pf3')}
    FIP = np.full((N, T), np.nan, np.float32)
    VOL60 = np.full((N, T), np.nan, np.float32)
    t0 = time.time()
    nbad, errs = 0, {}

    def one(i):
        x, e = SE.get(f"eod/{cols[i]}", **{'from': SE.START})
        return i, x, e
    with cf.ThreadPoolExecutor(8) as pool:
        for n, (i, x, e) in enumerate(pool.map(one, range(N))):
            if e:
                errs[e] = errs.get(e, 0) + 1
                continue
            try:
                o, f, v6, nb = daily_signals(x, Pw[i], fri, FXd.get(rows[i]['cur'], np.ones(T)))
            except Exception as ex:
                errs[type(ex).__name__] = errs.get(type(ex).__name__, 0) + 1
                continue
            nbad += nb
            for k in SIG:
                SIG[k][i] = o[k]
            FIP[i], VOL60[i] = f, v6
            if n % 500 == 499:
                log(f"  cours journaliers : {n + 1} sociétés en {time.time() - t0:.0f} s")
    log(f"  cours journaliers : {N} sociétés en {time.time() - t0:.0f} s ; jours aberrants écartés {nbad} ; erreurs {errs or 'aucune'}")
    for k in SIG:
        SIG[k] &= okn

    try:
        log("\n3. Screeners ProRealTime de François, sur cours journaliers (sociétés liquides à la date). Écart à 6 mois avec la "
            "société moyenne (points ; cas ; part de sociétés disparues) · par période")
        sg_z, _ = ev_line('zone du 🎯 (repère)', events(zone), ERAS)
        for lab, k in (('Parrish Minimal v2', 'par'), ('Wyckoff phase D v1', 'wyk'), ('points et figures (double ou triple sommet)', 'pf'),
                       ('points et figures, triple sommet seulement', 'pf3')):
            sg, tv = ev_line(lab, events(SIG[k]), ERAS)
            beat = all(x > 0 for x in sg) and tv >= 3
            vs_z = all(x > y for x, y in zip(sg, sg_z))
            log(f"    → {'bat la moyenne dans chaque période (t ≥ 3)' if beat else 'ne bat pas la moyenne dans chaque période avec t ≥ 3'} ; "
                f"{'mieux que la zone du 🎯 dans chaque période' if vs_z else 'pas mieux que la zone du 🎯 dans chaque période'}")
            ev_line(f"  {lab}, dans la zone du 🎯", events(SIG[k] & zone), ERAS)
            log(f"    semaines-sociétés signalées : {int(SIG[k].sum())} ; par an en médiane {np.median([SIG[k][:, a:b].sum() / ((b - a) / 52) for _, a, b in ERAS]):.0f}")
    except Exception as e:
        log(f"  screeners : échec ({type(e).__name__} : {str(e)[:200]})")

    try:
        log("\n4. Grenouille dans la casserole (discrétion du momentum, cours journaliers) : zone du 🎯 par tiers de discrétion")
        Q = np.full((N, T), -1, np.int8)
        for t in range(T):
            k = okn[:, t] & np.isfinite(FIP[:, t])
            if k.sum() >= 30:
                a, b = np.nanpercentile(FIP[k, t], [100 / 3, 200 / 3])
                Q[k, t] = np.where(FIP[k, t] <= a, 0, np.where(FIP[k, t] <= b, 1, 2))
        for lab, q in (('hausse régulière (tiers bas)', 0), ('tiers du milieu', 1), ('hausse par bonds (tiers haut)', 2)):
            ev_line(lab, events(zone & (Q == q)), ERAS)
        pkf = RP.make_pick(dict(G, okn=okn & ~(Q == 2)))
        R_f = run({t: pkf(t) for t in range(t2001, T - 1)})
        line('sélection de base', R0)
        line('sans le tiers le plus discret', R_f)
        sg, tv = cmp(R_f, R0)
        v = ' → BAT LA SÉLECTION : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejeté'
        log(f"    − sélection : {cells(sg)} pts/an (t {tv:4.1f}){v}")
    except Exception as e:
        log(f"  grenouille : échec ({type(e).__name__} : {str(e)[:200]})")

    def slots_sim(n, pick_fn, hold=None, stop=None, every=1, keep_fn=None, cost=.003):
        """n places : achats dans l'ordre de pick_fn(t) quand une place est libre (toutes les `every` semaines), revente après
        `hold` semaines, à −30 % (stop) ou quand keep_fn(t, i) est faux ; liquidités à 0 %."""
        held, R = [None] * n, []
        val = np.full(n, 1.0 / n)
        for t in range(t2001, T - 1):
            if (t - t2001) % every == 0:
                order = list(pick_fn(t))
                if keep_fn is not None:
                    for s in range(n):
                        if held[s] is not None and not keep_fn(t, held[s][0]):
                            val[s] *= 1 - cost
                            held[s] = None
                cur = {h[0] for h in held if h is not None}
                for i in order:
                    if None not in held:
                        break
                    if i in cur:
                        continue
                    s = held.index(None)
                    held[s] = [i, t, 1.0]
                    val[s] *= 1 - cost
                    cur.add(i)
            v0 = val.sum()
            for s in range(n):
                if held[s] is None:
                    continue
                r = retw[held[s][0], t + 1]
                val[s] *= 1 + r
                held[s][2] *= 1 + r
                if (stop is not None and held[s][2] <= stop) or (hold is not None and t + 1 - held[s][1] >= hold):
                    val[s] *= 1 - cost
                    held[s] = None
            R.append(val.sum() / v0 - 1)
        return np.array(R)

    try:
        log("\n5. Screener « Momentum PEA » d'octobre 2026 (repère simple, revu chaque mois)")
        rk = {}

        def mom_pick(t):
            k = okn[:, t] & (Pw[:, t] > m40[:, t]) & (VOL60[:, t] < .45) & (mom[:, t] > 0)
            idx = np.where(k)[0]
            idx = idx[np.argsort(-mom[idx, t])]
            rk[t] = {int(i): r for r, i in enumerate(idx)}
            return [int(i) for i in idx]

        def mom_keep(t, i):
            return rk.get(t, {}).get(i, 99) < 20
        R_mp = slots_sim(10, mom_pick, every=4, keep_fn=mom_keep)
        line('société moyenne (sans frais)', Rm)
        line('« Momentum PEA » (10 lignes, revue mensuelle)', R_mp)
        line('sélection de base (tranches, protection −30 %)', R0)
        sg, tv = cmp(R0, R_mp)
        log(f"    sélection − « Momentum PEA » : {cells(sg)} pts/an (t {tv:4.1f})")
    except Exception as e:
        log(f"  Momentum PEA : échec ({type(e).__name__} : {str(e)[:200]})")

    try:
        log("\n6. Portefeuille concentré : n lignes à la fois, les premières de la sélection dès qu'une place se libère, gardées 26 "
            "semaines, protection −30 %")
        line('tranches de 26 semaines (règle actuelle)', R0)
        for n in (3, 5, 10):
            R = slots_sim(n, lambda t: SEL0.get(t, []), hold=26, stop=.70)
            line(f"{n} lignes à la fois", R)
            sg, tv = cmp(R, R0)
            v = ' → BAT LES TRANCHES : à proposer à François' if all(x > 0 for x in sg) and tv >= 3 else ' → rejeté'
            log(f"    − tranches : {cells(sg)} pts/an (t {tv:4.1f}){v}")
    except Exception as e:
        log(f"  portefeuille concentré : échec ({type(e).__name__} : {str(e)[:200]})")
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels")


if __name__ == '__main__':
    main()
