"""
Recherche ponctuelle (05/11/2026, ancien outil « Squeeze Hunter ») : une société très vendue à découvert qui bondit sur gros volume
(rachats forcés des vendeurs, « short squeeze ») continue-t-elle de monter ? Et faut-il lever, pour le 📣, l'écart 🐻 des sociétés
parisiennes vendues à découvert à 0,5 % ou plus ? Mêmes données que shorts.py (positions courtes publiques de l'AMF depuis 2012 et
de la FCA), cours et volumes hebdomadaires Yahoo de Paris et Londres, 2013-2026. Résultat : écart de performance à 1, 3 et 6 mois
avec la société moyenne de la même semaine, achat à la clôture de la semaine du bond. Ne modifie pas le tableau de bord.
Lancé par « Recherche (à la demande) » (script squeeze.py), 15 à 30 minutes.
"""
import glob
import json

import numpy as np
import pandas as pd

import shorts as SH

log = SH.log


def main():
    S = pd.concat([SH.amf(), SH.fca()], ignore_index=True)
    S = S[S['code'].str.match(r'^[A-Z]{2}[A-Z0-9]{9}\d$')]
    m = SH.resolve(sorted(S['code'].unique()), SH.OUT / 'isin_yahoo.json')
    S['sym'] = S['code'].map(m)
    log('ISIN résolus :', S.drop_duplicates('code')['sym'].notna().sum(), '/', S['code'].nunique())
    uni = set()
    for f in glob.glob(str(SH.ROOT / 'data' / 'societes' / '*.json')):
        for k, x in json.load(open(f))['items'].items():
            if k.endswith(('.PA', '.L')) and (x.get('turnoverEur') or 0) >= 1e6:
                uni.add(k)
    uni |= set(S['sym'].dropna())
    uni = sorted(uni)
    log('titres à télécharger :', len(uni))
    import yahoo
    fr = yahoo.download(uni, 'research', start='2011-06-01', interval='1wk', fields=('Close', 'Volume'))
    W = fr['Close'].resample('W-FRI').last().loc['2011-06-01':]
    W = W.loc[:, W.notna().sum() >= 104]
    VV = fr['Volume'].resample('W-FRI').last().reindex(index=W.index, columns=W.columns)
    dates = W.index
    cols = list(W.columns)
    T, N = len(dates), len(cols)
    log('cours :', W.shape)
    P = W.values.T.astype(float)
    P = np.where(P > 0, P, np.nan)
    V = VV.values.T.astype(float)
    V = np.where(V > 0, V, np.nan)
    for i in range(N):                     # coupe après un saut anormal (comme les autres tests)
        p = P[i]
        ok = np.where(np.isfinite(p))[0]
        if len(ok) < 2:
            continue
        q = p[ok[1:]] / p[ok[:-1]]
        bad = np.where((q > 2.5) | (q < 0.35))[0]
        if len(bad):
            P[i, :ok[bad[-1] + 1]] = np.nan
    SI = np.zeros((N, T))
    idx = {c: k for k, c in enumerate(cols)}
    for r in S.dropna(subset=['sym']).itertuples():
        k = idx.get(r.sym)
        if k is None:
            continue
        a = np.searchsorted(dates.values, np.datetime64(r.start))
        b = T if pd.isna(r.end) else np.searchsorted(dates.values, np.datetime64(r.end))
        if b > a:
            SI[k, a:b] += r.pct
    lon = np.array([c.endswith('.L') for c in cols])

    def sma(A, k):
        o = np.full_like(A, np.nan)
        c = np.nancumsum(np.nan_to_num(A), 1)
        n = np.cumsum(np.isfinite(A), 1)
        o[:, k - 1:] = (c[:, k - 1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
        cnt = n[:, k - 1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1)
        o[:, k - 1:][cnt < k] = np.nan
        return o

    def shift(A, k):
        o = np.full_like(A, np.nan)
        o[:, k:] = A[:, :-k]
        return o
    m10, m40 = sma(P, 10), sma(P, 40)
    trend = (m10 > m40) & (P > m40)
    mom = np.full_like(P, np.nan)
    mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
    r1 = P / shift(P, 1) - 1
    vy = V / shift(sma(V, 52), 1)
    hi52 = np.full_like(P, np.nan)
    for t in range(51, T):
        hi52[:, t] = np.nanmax(P[:, t - 51:t + 1], axis=1)
    hi52p = shift(hi52, 1)
    bond = (r1 >= .08) & (vy >= 3)                                    # 📣 : semaine à +8 % sur 3 fois le volume habituel
    bond_h = (r1 >= .08) & (vy >= 2) & (P >= hi52p)                   # ou 2 fois au plus haut de l'année
    valid = np.isfinite(mom) & np.isfinite(P)
    mp = np.full_like(P, np.nan)
    for t in range(T):
        ok = valid[:, t]
        if ok.sum() > 30:
            mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
    d4 = np.zeros_like(SI)
    d4[:, 4:] = SI[:, 4:] - SI[:, :-4]
    t0 = int(np.searchsorted(dates.values, np.datetime64('2013-01-01')))
    yr = dates.year.values
    FUT = {}
    for H in (4, 13, 26):
        f = np.full_like(P, np.nan)
        f[:, :-H] = P[:, H:] / P[:, :-H] - 1
        FUT[H] = f

    def st(M, H, a=t0, b=T):
        fut = FUT[H]
        ex, n, cr, win = [], 0, 0, 0
        for t in range(max(a, t0), min(b, T - H)):
            ok = valid[:, t] & np.isfinite(fut[:, t])
            mm = M[:, t] & ok
            if ok.sum() < 30 or not mm.any():
                continue
            f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
            ex.append(np.nanmean(f[mm]) - np.nanmean(f[ok]))
            n += mm.sum()
            cr += (fut[mm, t] <= -.25).sum()
            win += (fut[mm, t] > 0).sum()
        if not ex:
            return None
        ex = np.array(ex)
        tt = ex.mean() / ex.std() * np.sqrt(len(ex)) / np.sqrt(H) if len(ex) > 2 and ex.std() > 0 else 0
        return ex.mean() * 100, tt, cr / n * 100, win / n * 100, n
    P1 = [('2013-2019', t0, int(np.searchsorted(yr, 2020))), ('2020-2026', int(np.searchsorted(yr, 2020)), T)]
    lines = []

    def show(lab, M):
        out = []
        for H in (4, 13, 26):
            r = st(M, H)
            out.append('—' if not r else f"{r[0]:+5.1f} (t {r[1]:4.1f})")
        r = st(M, 26)
        if not r:
            lines.append(f'{lab:60s} —')
            return
        per = '  '.join(f"{p}: {'—' if st(M, 26, a, b) is None else '%+.1f' % st(M, 26, a, b)[0]}" for p, a, b in P1)
        lines.append(f"{lab:60s} 1 mois {out[0]} · 3 mois {out[1]} · 6 mois {out[2]} · chutes {r[2]:4.1f} % · n={r[4]:5d} | {per}")
    lines.append(f"Sociétés : {N} (Londres {lon.sum()}, Paris {(~lon).sum()}), semaines {dates[t0].date()} → {dates[-1].date()} ;"
                 f" bonds 📣 (+8 % sur 3 fois le volume) : {int((bond & valid)[:, t0:].sum())}, dont sur une société vendue à découvert"
                 f" (0,5 % ou plus) : {int((bond & valid & (SI > 0))[:, t0:].sum())}")
    lines.append("Écart avec la société moyenne de la même semaine (points de %), achat à la clôture de la semaine du bond")
    dem = (bond | bond_h) & trend & (mp >= 1 / 3)                      # 📣 démarrage : bond en tendance, hors tiers faible
    for zone, Z in [('Paris + Londres', np.ones(N, bool)), ('Paris', ~lon), ('Londres', lon)]:
        Zb = Z[:, None]
        lines.append(f"\n=== {zone} ===")
        for lab, M in [('toutes les sociétés', valid),
                       ('vendues à découvert à 2 % ou plus (sans bond)', valid & (SI >= 2) & ~bond),
                       ('bond 📣 (toutes)', valid & bond),
                       ('  … sans position publiée', valid & bond & (SI == 0)),
                       ('  … vendue à découvert 0,5 à 2 %', valid & bond & (SI > 0) & (SI < 2)),
                       ('  … vendue à découvert 2 % ou plus', valid & bond & (SI >= 2)),
                       ('  … vendue à découvert 5 % ou plus', valid & bond & (SI >= 5)),
                       ('  … vendeurs qui rachètent (−0,5 pt ou plus sur 4 semaines)', valid & bond & (SI > 0) & (d4 <= -.5)),
                       ('📣 démarrage (bond en tendance, hors tiers faible)', valid & dem),
                       ('  … sans position publiée', valid & dem & (SI == 0)),
                       ('  … vendue à découvert 0,5 % ou plus (écartée 🐻 à Paris)', valid & dem & (SI > 0)),
                       ('  … vendue à découvert 2 % ou plus', valid & dem & (SI >= 2))]:
            show(lab, M & Zb)
    rep = '\n'.join(lines)
    log('\n' + rep)
    (SH.OUT / 'rapport_squeeze.txt').write_text('Ventes à découvert dans le sens « squeeze » — écart avec la société moyenne\n' + rep + '\n')


if __name__ == '__main__':
    main()
