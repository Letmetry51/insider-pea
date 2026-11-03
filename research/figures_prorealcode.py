"""Figures de la bibliothèque ProRealCode pas encore testées (03/11/2026), sur les cours journaliers et hebdomadaires Yahoo (ouverture,
plus haut, plus bas, clôture, volume) des sociétés de l'étude longue. Lancé par « Recherche (à la demande) » (script
figures_prorealcode.py), environ 5 minutes. Même mesure que figures_bougies.py (dont il reprend les fonctions).

Figures (codes de la bibliothèque : « Trend reversal and continuation patterns » d'après Bulkowski, « Chartist Figures detector »,
« 3 Line Strike », « Three rising methods », « PopGun », « #TheStrat », « Wide Range Body and Hidden Gap bars », « SlingShot »,
« Same Candle Run », « 3 Weeks Consolidation », « Flat Base Consolidation ») :
- retournement haussier : trois lignes (three-line strike), trois intérieures et trois extérieures haussières, pince (tweezers),
  bébé abandonné, faux décrochage (slingshot : nouveau plus bas de 20 barres en séance, clôture au-dessus de l'ancien plus bas) ;
- continuation et cassure : méthode ascendante, PopGun (barre intérieure puis barre extérieure verte), barre intérieure puis
  cassure (2-1-2), extérieure, intérieure, cassure (3-1-2), grande barre (WRB) avec ou sans volume, gap caché après une WRB ;
- baissières : trois lignes baissières, deux noires en gap, méthode descendante, 6 bougies rouges d'affilée ;
- hebdomadaires seulement : 3 semaines serrées (plus hauts qui baissent, plus bas qui montent) et leur cassure, base plate
  (5 semaines dans 15 %, moyenne 10 semaines à plus de 10 % au-dessus de la 40, cours au-dessus de la 10) et sa cassure.
Contrôles : même contexte sans la figure (baisse d'avant pour un retournement, barre qui clôture au-dessus du plus haut précédent
pour une cassure). Masque par société et par semaine imprimé en base64 entre FIGURES-DEBUT et FIGURES-FIN (étude locale à 6 mois).
"""
import base64
import io
import time

import numpy as np
import pandas as pd

import figures_bougies as FB

log, shift, sma, dedup = FB.log, FB.shift, FB.sma, FB.dedup


def rmin(A, k):
    o = np.full_like(A, np.nan)
    for j in range(k - 1, A.shape[1]):
        o[:, j] = np.nanmin(A[:, j - k + 1:j + 1], 1)
    return o


def rmax(A, k):
    o = np.full_like(A, np.nan)
    for j in range(k - 1, A.shape[1]):
        o[:, j] = np.nanmax(A[:, j - k + 1:j + 1], 1)
    return o


def patterns(O, H, L, C, V, dn_thr, ctx_len, weekly=False):
    """Figures sur des barres (lignes = sociétés). Contexte de baisse : variation sur ctx_len barres avant la première barre."""
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (L <= np.minimum(O, C)) & \
            (H >= np.maximum(O, C)) & (np.nan_to_num(V) > 0)
        body, rng = np.abs(C - O), H - L
        avgB = shift(sma(np.where(ok, body, np.nan), 10), 1)
        ret = C / shift(C, ctx_len) - 1
        S = {k: dict(O=shift(O, k), H=shift(H, k), L=shift(L, k), C=shift(C, k), B=shift(body, k), R=shift(rng, k),
                     ok=shift(ok.astype(np.float32), k) == 1, avgB=shift(avgB, k)) for k in (1, 2, 3, 4)}
        red, grn = C < O, C > O
        for k in S:
            S[k]['red'] = S[k]['C'] < S[k]['O']
            S[k]['grn'] = S[k]['C'] > S[k]['O']
        dn = {k: shift(ret, k) <= dn_thr for k in (1, 2, 3, 4)}
        s1, s2, s3, s4 = S[1], S[2], S[3], S[4]
        R = {}
        R['trois lignes haussières'] = ok & s1['ok'] & s2['ok'] & s3['ok'] & s1['red'] & s2['red'] & s3['red'] & \
            (s2['L'] < s3['L']) & (s1['L'] < s2['L']) & (s2['O'] < s3['O']) & (s1['O'] < s2['O']) & grn & (O <= s1['C']) & (C > s3['O'])
        R['trois intérieures haussières'] = ok & s1['ok'] & s2['ok'] & s2['red'] & (s2['B'] >= s2['avgB']) & s1['grn'] & \
            (s1['O'] > s2['C']) & (s1['C'] < s2['O']) & grn & (C > s2['O']) & dn[3]
        R['trois extérieures haussières'] = ok & s1['ok'] & s2['ok'] & s2['red'] & s1['grn'] & (s1['O'] <= s2['C']) & \
            (s1['C'] >= s2['O']) & (s1['B'] > s2['B']) & grn & (C > s1['C']) & dn[3]
        R['pince (tweezers)'] = ok & s1['ok'] & s1['red'] & grn & (np.abs(L - s1['L']) <= .001 * C) & dn[2]
        R['bébé abandonné'] = ok & s1['ok'] & s2['ok'] & s2['red'] & (s1['H'] < s2['L']) & (s1['H'] < L) & \
            (s1['B'] <= .5 * s1['R']) & grn & dn[3]
        LL20 = shift(rmin(np.where(ok, L, np.nan), 20), 1)
        R['faux décrochage (slingshot)'] = ok & (L < LL20) & (C > LL20) & grn
        R['méthode ascendante'] = ok & s1['ok'] & s2['ok'] & s3['ok'] & s4['ok'] & s4['grn'] & (s4['B'] >= 1.5 * s4['avgB']) & \
            (s1['B'] <= .5 * s4['B']) & (s2['B'] <= .5 * s4['B']) & (s3['B'] <= .5 * s4['B']) & \
            (np.maximum(np.maximum(s1['H'], s2['H']), s3['H']) <= s4['H']) & \
            (np.minimum(np.minimum(s1['L'], s2['L']), s3['L']) >= s4['L']) & (s1['C'] <= s3['C']) & grn & (C > s4['C']) & (body >= avgB)
        inside1 = s1['ok'] & s2['ok'] & (s2['H'] > s1['H']) & (s2['L'] < s1['L'])
        R['PopGun haussier'] = ok & inside1 & (H > s1['H']) & (L < s1['L']) & grn
        R['intérieure puis cassure (2-1-2)'] = ok & inside1 & (C > s1['H']) & ~(L < s1['L'])
        outside2 = s3['ok'] & (s2['H'] > s3['H']) & (s2['L'] < s3['L'])
        R['extérieure, intérieure, cassure (3-1-2)'] = ok & outside2 & inside1 & (C > s1['H']) & ~(L < s1['L'])
        maxB10 = shift(rmax(np.where(ok, body, np.nan), 10), 1)
        WRB = ok & grn & (body >= 2 * avgB) & (body > maxB10) & ((C - L) >= .75 * rng)
        R['grande barre (WRB)'] = WRB
        volm = shift(sma(np.where(ok, V, np.nan), 52 if weekly else 50), 1)
        R['grande barre sur volume ×2'] = WRB & (V >= 2 * volm)
        R['gap caché après une WRB'] = ok & (shift(WRB.astype(np.float32), 1) == 1) & (L > s2['H'])
        R['trois lignes baissières'] = ok & s1['ok'] & s2['ok'] & s3['ok'] & s1['grn'] & s2['grn'] & s3['grn'] & \
            (s2['H'] > s3['H']) & (s1['H'] > s2['H']) & (s2['O'] > s3['O']) & (s1['O'] > s2['O']) & red & (O >= s1['C']) & (C < s3['O'])
        R['deux noires en gap'] = ok & s1['ok'] & s1['red'] & red & (H < s1['L'])
        R['méthode descendante'] = ok & s1['ok'] & s2['ok'] & s3['ok'] & s4['ok'] & s4['red'] & (s4['B'] >= 1.5 * s4['avgB']) & \
            (s1['B'] <= .5 * s4['B']) & (s2['B'] <= .5 * s4['B']) & (s3['B'] <= .5 * s4['B']) & \
            (np.maximum(np.maximum(s1['H'], s2['H']), s3['H']) <= s4['H']) & \
            (np.minimum(np.minimum(s1['L'], s2['L']), s3['L']) >= s4['L']) & (s1['C'] >= s3['C']) & red & (C < s4['C']) & (body >= avgB)
        r6 = red.copy()
        for k in range(1, 6):
            r6 &= shift(red.astype(np.float32), k) == 1
        R['6 rouges d\'affilée'] = r6
        if weekly:
            c3 = ok & s1['ok'] & s2['ok'] & (s2['H'] >= s1['H']) & (s1['H'] >= H) & (s2['L'] <= s1['L']) & (s1['L'] <= L)
            R['3 semaines serrées'] = c3
            R['3 semaines serrées puis cassure'] = ok & (shift(c3.astype(np.float32), 1) == 1) & (C > s1['H'])
            m10, m40 = sma(C, 10), sma(C, 40)
            hh5, ll5 = rmax(np.where(ok, H, np.nan), 5), rmin(np.where(ok, L, np.nan), 5)
            flat = ok & (hh5 / ll5 - 1 <= .15) & (m10 / m40 - 1 > .10) & (C > m10)
            R['base plate'] = flat
            R['base plate puis cassure'] = ok & (shift(flat.astype(np.float32), 1) == 1) & (C > shift(hh5, 1))
        ctl = {'retournement': ok & dn[1], 'cassure': ok & grn & (C > s1['H']), 'plus bas 20': ok & (L < LL20)}
    return R, ctl, ok


REV = ['trois lignes haussières', 'trois intérieures haussières', 'trois extérieures haussières', 'pince (tweezers)', 'bébé abandonné']
BRK = ['méthode ascendante', 'PopGun haussier', 'intérieure puis cassure (2-1-2)', 'extérieure, intérieure, cassure (3-1-2)',
       'grande barre (WRB)', 'grande barre sur volume ×2', 'gap caché après une WRB']
BRKW = ['3 semaines serrées puis cassure', 'base plate puis cassure']


def ctl_of(k, ctl):
    return ctl['retournement'] if k in REV else ctl['cassure'] if k in BRK + BRKW else ctl['plus bas 20'] if 'slingshot' in k else None


def study_w(lab, M, EX, wm, wy, ctl=None):
    out = []
    for h, X in EX.items():
        ii, tt = np.where(M & np.isfinite(X))
        if len(ii) < 50:
            out.append(f"{h:>2d} sem. : trop peu ({len(ii)})")
            continue
        e = X[ii, tt]
        g = pd.Series(e).groupby(wm[tt]).mean()
        tv = g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))
        s = f"{h:>2d} sem. : {e.mean() * 100:+5.2f} (t {tv:4.1f})"
        if ctl is not None:
            jj, uu = np.where(ctl & ~M & np.isfinite(X))
            s += f" vs {X[jj, uu].mean() * 100:+5.2f}"
        if h == 26:
            per = []
            for a, b in ((2000, 2009), (2009, 2018), (2018, 2027)):
                m = (wy[tt] >= a) & (wy[tt] < b)
                per.append(f"{e[m].mean() * 100:+5.2f}" if m.sum() >= 30 else "  ·  ")
            s += " [" + " / ".join(per) + "]"
        out.append(s)
    log(f"  {lab:40s} {int(M.sum()):6d} cas | " + " | ".join(out))


def main():
    t0 = time.time()
    sec = FB.universe()
    log('univers', len(sec), 'symboles')
    D = FB.download(list(sec))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates, cols = D['Close'].index, list(D['Close'].columns)
    yrs = np.array(dates.year)
    log(f"téléchargé en {time.time() - t0:.0f} s : {len(cols)} sociétés, {len(dates)} séances ({dates[0].date()} → {dates[-1].date()})")
    EX = {}
    O1n = shift(O, -1)
    for h in (5, 20, 60, 125):
        with np.errstate(all='ignore'):
            r = shift(C, -h) / O1n - 1
        r = np.where((r > -.7) & (r < 2), r, np.nan)
        mu = np.nanmean(r, 0)
        mu[np.isfinite(r).sum(0) < 30] = np.nan
        EX[h] = (r - mu[None, :]).astype(np.float32)
        EX[h][:, yrs < 2000] = np.nan
    del O1n
    months = np.array(dates.year * 100 + dates.month)
    R, ctl, ok = patterns(O, H, L, C, V, -.05, 10)
    with np.errstate(all='ignore'):
        m50, m200 = sma(C, 50), sma(C, 200)
        upT = (C > m200) & (m50 > m200)
    log("\n=== 1. Journalier (2000-2026) : écart avec la moyenne des sociétés en points de %, achat à l'ouverture du lendemain")
    log("     [2000-08 / 2009-17 / 2018-26 à 20 et 125 séances] ; « vs contexte » : même situation sans la figure")
    for k, M in R.items():
        FB.study(k, dedup(M, 10), EX, months, yrs, ctl=(lambda c: (c & ~M) if c is not None else None)(ctl_of(k, ctl)), show_per=True)
    log("\n  — en tendance haussière (cours au-dessus de la moyenne 200 séances, 50 au-dessus de 200)")
    for k in REV + BRK + ['faux décrochage (slingshot)']:
        c = ctl_of(k, ctl)
        FB.study(k + ' en tendance', dedup(R[k] & upT, 10), EX, months, yrs, ctl=(c & upT & ~R[k]) if c is not None else None,
                 show_per=True)
    names_d = list(R.keys())
    wk = {}
    for k in names_d:
        wk[k] = pd.DataFrame(R[k].T, index=dates, columns=cols).resample('W-FRI').max().fillna(False).values.T.astype(bool)
    del R, EX, O, H, L, C, V, m50, m200, upT
    # hebdomadaire
    Dw = {'Open': D['Open'].resample('W-FRI').first(), 'High': D['High'].resample('W-FRI').max(),
          'Low': D['Low'].resample('W-FRI').min(), 'Close': D['Close'].resample('W-FRI').last(),
          'Volume': D['Volume'].resample('W-FRI').sum(min_count=1)}
    wdates = Dw['Close'].index
    Ow, Hw, Lw, Cw, Vw = (Dw[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    Rw, ctlw, okw = patterns(Ow, Hw, Lw, Cw, Vw, -.08, 4, weekly=True)
    EXw = {}
    for h in (4, 13, 26):
        with np.errstate(all='ignore'):
            r = shift(Cw, -h) / Cw - 1
        r = np.where((r > -.8) & (r < 3), r, np.nan)
        mu = np.nanmean(r, 0)
        mu[np.isfinite(r).sum(0) < 30] = np.nan
        EXw[h] = r - mu[None, :]
        EXw[h][:, np.array(wdates.year) < 2000] = np.nan
    wm, wy = np.array(wdates.year * 100 + wdates.month), np.array(wdates.year)
    log("\n=== 2. Hebdomadaire (2000-2026) : barres de la semaine, mesure depuis la clôture du vendredi, à 4, 13 et 26 semaines")
    for k, M in Rw.items():
        study_w(k, dedup(M, 4), EXw, wm, wy, ctl=ctl_of(k, ctlw))
    m10w, m40w = sma(Cw, 10), sma(Cw, 40)
    trw = (m10w > m40w) & (Cw > m40w)
    log("\n  — en tendance (moyenne 10 semaines au-dessus de la 40, cours au-dessus de la 40)")
    for k in REV + BRK + ['faux décrochage (slingshot)', '3 semaines serrées'] + BRKW:
        c = ctl_of(k, ctlw)
        study_w(k + ' en tendance', dedup(Rw[k] & trw, 4), EXw, wm, wy, ctl=(c & trw) if c is not None else None)
    # masque (64 bits) : figures journalières (une au moins dans la semaine) d'abord, puis hebdomadaires
    bits = np.zeros(Cw.shape, dtype=np.uint64)
    for b, k in enumerate(names_d):
        m = wk[k]
        bits[:, :m.shape[1]] |= (m[:, :bits.shape[1]].astype(np.uint64) << np.uint64(b))
    names_w = list(Rw.keys())
    for b, k in enumerate(names_w):
        bits |= (Rw[k].astype(np.uint64) << np.uint64(len(names_d) + b))
    buf = io.BytesIO()
    np.savez_compressed(buf, bits=bits, cols=np.array(cols), dates=np.array([str(d.date()) for d in wdates]),
                        dnames=np.array(names_d), wnames=np.array([k + ' (sem.)' for k in names_w]))
    s = base64.b64encode(buf.getvalue()).decode()
    log(f"\nmasque : {bits.shape}, {len(names_d)} figures journalières et {len(names_w)} hebdomadaires, {len(s)} caractères en base64")
    print("FIGURES-DEBUT", flush=True)
    for i in range(0, len(s), 8000):
        print("B64:" + s[i:i + 8000], flush=True)
    print("FIGURES-FIN", flush=True)
    log(f"terminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
