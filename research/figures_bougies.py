"""Figures de chandeliers japonais (marteau, avalement, étoile du matin, trois soldats blancs…) et croisements des moyennes 50 et 200
séances, sur les cours journaliers Yahoo (ouverture, plus haut, plus bas, clôture) des sociétés de l'étude longue (≥ 1 M€ échangé
par jour, éligibles au PEA). Lancé par « Recherche (à la demande) » (script figures_bougies.py), environ 15 minutes.

1. Journalier, 2000-2026 : achat à l'ouverture du lendemain de la figure, écart avec la moyenne des sociétés sur 5, 20, 60 et 125
   séances ; même contexte sans la figure (baisse de 5 % ou plus sur 10 séances avant une figure de retournement haussier, hausse de
   5 % ou plus avant une figure baissière) pour isoler ce que la bougie ajoute ; t regroupé par mois ; trois périodes.
2. Hebdomadaire : les mêmes figures sur les bougies de la semaine.
3. Pour l'étude locale (6 et 12 mois, croisement avec 🎯 et 📣) : un masque par société et par semaine (vendredi), compressé et
   imprimé en base64 entre les lignes « FIGURES-DEBUT » et « FIGURES-FIN ».
"""
import base64
import glob
import io
import json
import time

import numpy as np
import pandas as pd


def log(*a):
    print(*a, flush=True)


def universe():
    uni = json.load(open('../data/sectors/universe.json'))['items']
    sec = {k: v.get('sector') or '?' for k, v in uni.items()}
    for f in glob.glob('../data/societes/*.json'):
        for k, x in json.load(open(f))['items'].items():
            if (x.get('turnoverEur') or 0) >= 1e6 and x.get('pea') is not False:
                sec.setdefault(k, x.get('sector') or '?')
    return sec


def download(tick):
    import yfinance as yf
    F = {k: [] for k in ('Open', 'High', 'Low', 'Close', 'Volume')}
    tick = sorted(tick)
    for i in range(0, len(tick), 50):
        b = tick[i:i + 50]
        df = None
        for a in range(3):
            try:
                df = yf.download(b, period='max', interval='1d', auto_adjust=True, progress=False, threads=True, group_by='column')
                break
            except Exception as e:
                log('lot', i, str(e)[:80])
                time.sleep(5)
        if df is None or df.empty:
            continue
        for k in F:
            if isinstance(df.columns, pd.MultiIndex):
                F[k].append(df[k])
            else:
                F[k].append(df[[k]].rename(columns={k: b[0]}))
        time.sleep(1)
    out = {}
    for k, v in F.items():
        X = pd.concat(v, axis=1)
        X = X.loc[:, ~X.columns.duplicated()]
        X.index = pd.to_datetime(X.index).tz_localize(None).normalize()
        out[k] = X.sort_index()
    cols = sorted(set.intersection(*(set(x.columns) for x in out.values())))
    idx = out['Close'].index
    return {k: x.reindex(index=idx, columns=cols) for k, x in out.items()}


def shift(A, k):
    o = np.full_like(A, np.nan)
    if k > 0:
        o[:, k:] = A[:, :-k]
    elif k < 0:
        o[:, :k] = A[:, -k:]
    else:
        o[:] = A
    return o


def sma(A, k):
    n_, T_ = A.shape
    c = np.cumsum(np.nan_to_num(A).astype(np.float64), 1)
    n = np.cumsum(np.isfinite(A), 1)
    o = np.full_like(A, np.nan)
    s = c[:, k - 1:] - np.concatenate([np.zeros((n_, 1)), c[:, :-k]], 1)
    m = n[:, k - 1:] - np.concatenate([np.zeros((n_, 1)), n[:, :-k]], 1)
    o[:, k - 1:] = np.where(m >= k, s / k, np.nan)
    return o


def candles(O, H, L, C, V, dn_thr, up_thr, ctx_len):
    """Figures sur des bougies (lignes = sociétés, colonnes = séances ou semaines). Contexte : variation sur ctx_len barres avant
    la figure (avant sa première bougie pour les figures de 2 ou 3 bougies)."""
    ok = np.isfinite(O) & np.isfinite(H) & np.isfinite(L) & np.isfinite(C) & (H > L) & (L <= np.minimum(O, C)) & \
        (H >= np.maximum(O, C)) & (np.nan_to_num(V) > 0)
    body = np.abs(C - O)
    rng = H - L
    up_s = H - np.maximum(O, C)
    lo_s = np.minimum(O, C) - L
    with np.errstate(all='ignore'):
        avgB = shift(sma(np.where(ok, body, np.nan), 10), 1)
        avgR = shift(sma(np.where(ok, rng, np.nan), 10), 1)
        ret = C / shift(C, ctx_len) - 1
    pre1 = shift(ret, 1)            # avant la bougie du jour
    pre2 = shift(ret, 2)            # avant une figure de 2 bougies
    pre3 = shift(ret, 3)            # de 3 bougies
    dn1, up1 = pre1 <= dn_thr, pre1 >= up_thr
    dn2, up2 = pre2 <= dn_thr, pre2 >= up_thr
    dn3, up3 = pre3 <= dn_thr, pre3 >= up_thr
    bull, bear = C > O, C < O
    O1, C1, B1, ok1 = shift(O, 1), shift(C, 1), shift(body, 1), shift(ok.astype(float), 1) == 1
    O2, C2, B2, ok2 = shift(O, 2), shift(C, 2), shift(body, 2), shift(ok.astype(float), 2) == 1
    H1, L1 = shift(H, 1), shift(L, 1)
    big = rng >= .8 * avgR
    hammer_shape = ok & (lo_s >= 2 * body) & (up_s <= .1 * rng) & big
    inv_shape = ok & (up_s >= 2 * body) & (lo_s <= .1 * rng) & big
    with np.errstate(invalid='ignore'):
        R = {
            'marteau': hammer_shape & dn1,
            'pendu': hammer_shape & up1,
            'marteau inversé': inv_shape & dn1,
            'étoile filante': inv_shape & up1,
            'avalement haussier': ok & ok1 & (C1 < O1) & bull & (O <= C1) & (C >= O1) & (body > B1) & dn2,
            'avalement baissier': ok & ok1 & (C1 > O1) & bear & (O >= C1) & (C <= O1) & (body > B1) & up2,
            'ligne pénétrante': ok & ok1 & (C1 < O1) & (B1 >= shift(avgB, 1)) & (O < C1) & (C > (O1 + C1) / 2) & (C < O1) & dn2,
            'nuage noir': ok & ok1 & (C1 > O1) & (B1 >= shift(avgB, 1)) & (O > C1) & (C < (O1 + C1) / 2) & (C > O1) & up2,
            'étoile du matin': ok & ok1 & ok2 & (C2 < O2) & (B2 >= shift(avgB, 2)) & (B1 <= .3 * B2) & (np.minimum(O1, C1) <= C2) &
            bull & (C > (O2 + C2) / 2) & dn3,
            'étoile du soir': ok & ok1 & ok2 & (C2 > O2) & (B2 >= shift(avgB, 2)) & (B1 <= .3 * B2) & (np.maximum(O1, C1) >= C2) &
            bear & (C < (O2 + C2) / 2) & up3,
            'harami haussier': ok & ok1 & (C1 < O1) & (B1 >= shift(avgB, 1)) & bull & (body <= .5 * B1) & (O > C1) & (C < O1) & dn2,
            'harami baissier': ok & ok1 & (C1 > O1) & (B1 >= shift(avgB, 1)) & bear & (body <= .5 * B1) & (O < C1) & (C > O1) & up2,
            'libellule': ok & (body <= .1 * rng) & (up_s <= .1 * rng) & (lo_s >= .6 * rng) & big & dn1,
            'pierre tombale': ok & (body <= .1 * rng) & (lo_s <= .1 * rng) & (up_s >= .6 * rng) & big & up1,
        }
        ws, bc = [], []
        for k in range(3):
            Ok, Ck, Bk, okk = shift(O, k), shift(C, k), shift(body, k), shift(ok.astype(float), k) == 1
            Hk, Lk = shift(H, k), shift(L, k)
            Cp, Op = shift(C, k + 1), shift(O, k + 1)
            ws.append(okk & (Ck > Ok) & (Ck > Cp) & (Ok >= np.minimum(Op, Cp)) & (Ok <= np.maximum(Op, Cp)) &
                      (Hk - Ck <= .25 * (Hk - Lk)) & (Bk >= .5 * shift(avgB, k)))
            bc.append(okk & (Ck < Ok) & (Ck < Cp) & (Ok >= np.minimum(Op, Cp)) & (Ok <= np.maximum(Op, Cp)) &
                      (Ck - Lk <= .25 * (Hk - Lk)) & (Bk >= .5 * shift(avgB, k)))
        R['trois soldats blancs'] = ws[0] & ws[1] & ws[2]
        R['trois corbeaux noirs'] = bc[0] & bc[1] & bc[2]
        clv = np.where(ok, (C - L) / np.where(rng > 0, rng, np.nan), np.nan)
    ctx = {'baisse': dn1, 'hausse': up1}
    return R, ok, clv, ctx, (H1, L1)


BULL = ['marteau', 'marteau inversé', 'avalement haussier', 'ligne pénétrante', 'étoile du matin', 'harami haussier', 'libellule',
        'trois soldats blancs']
BEAR = ['pendu', 'étoile filante', 'avalement baissier', 'nuage noir', 'étoile du soir', 'harami baissier', 'pierre tombale',
        'trois corbeaux noirs']


def dedup(M, k):
    M = M.copy()
    for i in np.where(M.any(1))[0]:
        last = -10 ** 9
        for t in np.where(M[i])[0]:
            if t - last <= k:
                M[i, t] = False
            else:
                last = t
    return M


def study(lab, M, EX, months, yrs, ctl=None, show_per=False):
    """Écart moyen (points de %) et t regroupé par mois ; ctl : même mesure pour le contexte sans figure."""
    out = []
    for h, X in EX.items():
        ii, tt = np.where(M & np.isfinite(X))
        if len(ii) < 50:
            out.append(f"{h:>3d} j : trop peu ({len(ii)})")
            continue
        e = X[ii, tt]
        g = pd.Series(e).groupby(months[tt]).mean()
        tv = g.mean() / (g.std(ddof=1) / np.sqrt(len(g))) if len(g) > 10 else np.nan
        s = f"{h:>3d} j : {e.mean() * 100:+5.2f} (t {tv:4.1f}, bat {np.mean(e > 0) * 100:3.0f} %)"
        if ctl is not None:
            jj, uu = np.where(ctl & np.isfinite(X))
            s += f" vs contexte {X[jj, uu].mean() * 100:+5.2f}"
        if show_per and h in (20, 125):
            per = []
            for a, b in ((2000, 2009), (2009, 2018), (2018, 2027)):
                m = (yrs[tt] >= a) & (yrs[tt] < b)
                per.append(f"{e[m].mean() * 100:+5.2f}" if m.sum() >= 30 else "  ·  ")
            s += " [" + " / ".join(per) + "]"
        out.append(s)
    n = int(M.sum())
    log(f"  {lab:34s} {n:7d} cas | " + " | ".join(out))


def main():
    t0 = time.time()
    sec = universe()
    log('univers', len(sec), 'symboles')
    D = download(list(sec))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates = D['Close'].index
    cols = list(D['Close'].columns)
    log(f"téléchargé en {time.time() - t0:.0f} s : {len(cols)} sociétés, {len(dates)} séances ({dates[0].date()} → {dates[-1].date()})")
    # qualité : séances avec vraie bougie (plus haut > plus bas), par année
    yrs = np.array(dates.year)
    real = np.isfinite(O) & (H > L)
    for y in (1995, 2000, 2005, 2010, 2015, 2020, 2025):
        m = yrs == y
        if m.any():
            log(f"  {y} : {real[:, m].sum() / max(np.isfinite(C[:, m]).sum(), 1) * 100:3.0f} % des séances avec une vraie bougie")
    # rendements de l'ouverture du lendemain à la clôture de t+h, écart avec la moyenne des sociétés
    EX = {}
    O1n = shift(O, -1)
    for h in (5, 20, 60, 125):
        with np.errstate(all='ignore'):
            r = shift(C, -h) / O1n - 1
        r = np.where((r > -.7) & (r < 2), r, np.nan)
        mu = np.nanmean(r, 0)
        cnt = np.isfinite(r).sum(0)
        mu[cnt < 30] = np.nan
        EX[h] = r - mu[None, :]
    months = np.array(dates.year * 100 + dates.month)
    keep = yrs >= 2000
    for h in EX:
        EX[h][:, ~keep] = np.nan
    R, ok, clv, ctx, _ = candles(O, H, L, C, V, -.05, .05, 10)
    with np.errstate(all='ignore'):
        m50, m200 = sma(C, 50), sma(C, 200)
        R['golden cross 50/200'] = (m50 > m200) & (shift(m50, 1) <= shift(m200, 1))
        R['death cross 50/200'] = (m50 < m200) & (shift(m50, 1) >= shift(m200, 1))
        upT = (C > m200)
    log("\n=== 1. Journalier (2000-2026) : écart avec la moyenne des sociétés en points de %, achat à l'ouverture du lendemain")
    log("     [périodes 2000-08 / 2009-17 / 2018-26 à 20 et 125 séances] ; contexte = même tendance avant, sans la figure")
    for k in BULL + BEAR + ['golden cross 50/200', 'death cross 50/200']:
        M = dedup(R[k], 10)
        c = ctx['baisse'] if k in BULL and k != 'trois soldats blancs' else ctx['hausse'] if k in BEAR and k != 'trois corbeaux noirs' else None
        study(k, M, EX, months, yrs, ctl=(c & ok) if c is not None else None, show_per=True)
    log("\n  — en tendance de fond haussière (au-dessus de la moyenne 200 séances), repli de 5 % ou plus sur 10 séances")
    for k in ('marteau', 'avalement haussier', 'étoile du matin', 'ligne pénétrante', 'harami haussier', 'libellule'):
        study(k + ' sur repli', dedup(R[k] & upT, 10), EX, months, yrs, ctl=ctx['baisse'] & upT & ok, show_per=True)
    # hebdomadaire
    Dw = {'Open': D['Open'].resample('W-FRI').first(), 'High': D['High'].resample('W-FRI').max(),
          'Low': D['Low'].resample('W-FRI').min(), 'Close': D['Close'].resample('W-FRI').last(),
          'Volume': D['Volume'].resample('W-FRI').sum(min_count=1)}
    wdates = Dw['Close'].index
    Ow, Hw, Lw, Cw, Vw = (Dw[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    Rw, okw, clvw, ctxw, _ = candles(Ow, Hw, Lw, Cw, Vw, -.08, .08, 4)
    EXw = {}
    for h in (4, 13, 26):
        with np.errstate(all='ignore'):
            r = shift(Cw, -h) / Cw - 1
        r = np.where((r > -.8) & (r < 3), r, np.nan)
        mu = np.nanmean(r, 0)
        mu[np.isfinite(r).sum(0) < 30] = np.nan
        EXw[h] = r - mu[None, :]
        EXw[h][:, np.array(wdates.year) < 2000] = np.nan
    log("\n=== 2. Hebdomadaire (2000-2026) : bougies de la semaine, mesure depuis la clôture du vendredi, à 4, 13 et 26 semaines")
    wm = np.array(wdates.year * 100 + wdates.month)
    wy = np.array(wdates.year)
    for k in BULL + BEAR:
        c = ctxw['baisse'] if k in BULL and k != 'trois soldats blancs' else ctxw['hausse'] if k in BEAR and k != 'trois corbeaux noirs' else None
        M = dedup(Rw[k], 4)
        out = []
        for h, X in EXw.items():
            ii, tt = np.where(M & np.isfinite(X))
            if len(ii) < 50:
                out.append(f"{h:>2d} sem. : trop peu")
                continue
            e = X[ii, tt]
            g = pd.Series(e).groupby(wm[tt]).mean()
            tv = g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))
            s = f"{h:>2d} sem. : {e.mean() * 100:+5.2f} (t {tv:4.1f})"
            if c is not None:
                jj, uu = np.where(c & okw & np.isfinite(X))
                s += f" vs {X[jj, uu].mean() * 100:+5.2f}"
            if h == 26:
                per = []
                for a, b in ((2000, 2009), (2009, 2018), (2018, 2027)):
                    m = (wy[tt] >= a) & (wy[tt] < b)
                    per.append(f"{e[m].mean() * 100:+5.2f}" if m.sum() >= 30 else "  ·  ")
                s += " [" + " / ".join(per) + "]"
            out.append(s)
        log(f"  {k:24s} {int(M.sum()):6d} cas | " + " | ".join(out))
    # masque par société et par semaine pour l'étude locale
    bits = np.zeros(Cw.shape, dtype=np.uint32)
    for b, k in enumerate(BULL + BEAR):
        bits |= (Rw[k].astype(np.uint32) << b)
    dk = ['marteau', 'avalement haussier', 'étoile du matin', 'ligne pénétrante', 'trois soldats blancs', 'harami haussier',
          'marteau inversé', 'libellule', 'étoile filante', 'avalement baissier', 'étoile du soir', 'trois corbeaux noirs']
    Dd = pd.DataFrame(index=dates)
    for b, k in enumerate(dk):
        wkly = pd.DataFrame(R[k].T, index=dates, columns=cols).resample('W-FRI').max().reindex(wdates).fillna(False).values.T
        bits |= (wkly.astype(np.uint32) << (16 + b))
    q = np.clip((np.nan_to_num(clvw) * 4).astype(int), 0, 3).astype(np.uint32)
    bits |= (q << 28)
    bits |= (okw.astype(np.uint32) << 30)
    gcw = pd.DataFrame(R['golden cross 50/200'].T, index=dates, columns=cols).resample('W-FRI').max().reindex(wdates).fillna(False).values.T
    bits |= (gcw.astype(np.uint32) << 31)
    del Dd
    buf = io.BytesIO()
    np.savez_compressed(buf, bits=bits, cols=np.array(cols), dates=np.array([str(d.date()) for d in wdates]),
                        names=np.array(BULL + BEAR), dnames=np.array(dk))
    s = base64.b64encode(buf.getvalue()).decode()
    log(f"\nmasque : {bits.shape}, {len(s)} caractères en base64")
    print("FIGURES-DEBUT", flush=True)
    for i in range(0, len(s), 8000):
        print("B64:" + s[i:i + 8000], flush=True)
    print("FIGURES-FIN", flush=True)
    log(f"terminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
