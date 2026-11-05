"""Portefeuille « miroir Buffett » en PEA (05/11/2026, fichier backtest-miroir-buffett-pea.html de l'ancien outil Rotation PEA) :
vérification sur les cours réels (Yahoo, dividendes réinvestis) des chiffres annoncés : corrélations sectorielles US → Europe,
rendements à 3 ans des achats de Buffett et de leur « miroir » européen, simulation de 25 000 € depuis 2008. Lancé par « Recherche
(à la demande) » (script miroir_buffett.py), environ 1 minute."""
import time

import numpy as np
import pandas as pd
import yfinance as yf

US = ['KO', 'AXP', 'BAC', 'CVX', 'OXY', 'CB', 'KHC', 'GS', 'GE', 'GOOGL', 'MCO', 'BRK-B', 'AAPL', '^GSPC']
EU = ['BN.PA', 'BNP.PA', 'TTE.PA', 'CS.PA', 'SIE.DE', 'SAP.DE', 'ENX.PA', '^FCHI', '^STOXX50E']
FX = ['EURUSD=X']


def log(*a):
    print(*a, flush=True)


def main():
    t0 = time.time()
    px = {}
    for s in US + EU + FX:
        for a in range(3):
            try:
                df = yf.download(s, period='max', interval='1d', auto_adjust=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                log(s, 'erreur', str(e)[:60])
                df = None
                time.sleep(3)
        if df is None or df.empty:
            log(f"{s:10s} rien")
            continue
        c = df['Close']
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        c = c.dropna()
        c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
        px[s] = c
        log(f"{s:10s} {c.index[0].date()} → {c.index[-1].date()}")
    P = pd.DataFrame(px).sort_index().ffill()
    eur = 1 / P['EURUSD=X'] if 'EURUSD=X' in P else None   # dollars → euros

    log("\n=== 1. Corrélations des rendements mensuels (annoncé : énergie 0,82 / 0,78 / 0,75, banques 0,71 / 0,68 / 0,65, assurance 0,63 / 0,62 / 0,60,"
        " consommation 0,58 / 0,57 / 0,55, logiciel — / 0,52 / 0,45)")
    M = P.resample('ME').last().pct_change()
    pairs = [('énergie', 'CVX', 'TTE.PA'), ('banques', 'BAC', 'BNP.PA'), ('assurance', 'CB', 'CS.PA'), ('consommation', 'KO', 'BN.PA'),
             ('logiciel', 'GOOGL', 'SAP.DE'), ('« péage financier »', 'MCO', 'ENX.PA'), ('contrôle : marchés', '^GSPC', '^STOXX50E'),
             ('contrôle : énergie / marché EU', 'CVX', '^STOXX50E')]
    for lab, a, b in pairs:
        if a not in M or b not in M:
            log(f"  {lab:32s} données absentes")
            continue
        out = []
        for yrs in (50, 20, 10):
            m = M[[a, b]].dropna()
            m = m[m.index >= m.index[-1] - pd.DateOffset(years=yrs)]
            out.append(f"{yrs} ans {m[a].corr(m[b]):.2f} ({len(m)} mois depuis {m.index[0].year})" if len(m) > 24 else f"{yrs} ans ·")
        log(f"  {lab:32s} {a:6s} / {b:9s} : " + " · ".join(out))

    log("\n=== 2. Rendement à 3 ans, dividendes réinvestis, des achats annoncés et de leur miroir (annoncé entre parenthèses)")
    cases = [('1988-12-30', 'KO', 'BN.PA', '+196 / +145'), ('1994-12-30', 'AXP', 'BNP.PA', '+280 / +190'), ('2002-12-31', 'KO', 'BN.PA', '+45 / +38'),
             ('2008-10-31', 'GS', 'BNP.PA', '+312 / +185 (avec GE et Siemens)'), ('2008-10-31', 'GE', 'SIE.DE', ''),
             ('2011-08-31', 'BAC', 'BNP.PA', '+180 / +120'), ('2015-07-06', 'KHC', 'BN.PA', '−30 / +15'), ('2020-06-30', 'CVX', 'TTE.PA', '+240 / +195'),
             ('2022-03-31', 'OXY', 'TTE.PA', '+85 / +72'), ('2023-09-29', 'CB', 'CS.PA', '+45 / +52')]

    def ret(s, d0, years=3, in_eur=False):
        if s not in P:
            return None
        x = P[s]
        if in_eur and eur is not None:
            x = x * eur
        x = x.dropna()
        d0 = pd.Timestamp(d0)
        if x.index[0] > d0:
            return None
        a = x[x.index <= d0].iloc[-1]
        e = min(d0 + pd.DateOffset(years=years), x.index[-1])
        b = x[x.index <= e].iloc[-1]
        return (b / a - 1) * 100, e.date()
    for d0, us, eu, claim in cases:
        r1, r2 = ret(us, d0), ret(eu, d0)
        r1e = ret(us, d0, in_eur=True)
        mk = ret('^STOXX50E', d0) or ret('^FCHI', d0)
        f = lambda r: f"{r[0]:+5.0f} %" if r else "pas de cours"   # noqa: E731
        log(f"  {d0} {us:5s} {f(r1)} (en euros {f(r1e)}) · miroir {eu:7s} {f(r2)} · marché européen (prix) {f(mk)}"
            f"{' · annoncé ' + claim if claim else ''}{' · jusqu’au ' + str(r1[1]) if r1 else ''}")

    log("\n=== 3. 25 000 investis début 2008 (annoncé : Buffett 215 000 $ soit +760 %, 12,8 %/an ; miroir PEA 145 000 €, +480 %, 10,2 %/an)")
    d0 = pd.Timestamp('2008-01-02')
    for s, lab in (('BRK-B', 'Berkshire (dollars)'), ('^GSPC', 'S&P 500 (prix, dollars)'), ('^FCHI', 'CAC 40 (prix)'), ('^STOXX50E', 'Euro Stoxx 50 (prix)')):
        r = ret(s, d0, years=30)
        if r:
            yrs = (pd.Timestamp(r[1]) - d0).days / 365.25
            log(f"  {lab:28s} {r[0]:+6.0f} % · {((1 + r[0] / 100) ** (1 / yrs) - 1) * 100:+5.1f} %/an")
    W = {'TTE.PA': .25, 'BNP.PA': .20, 'BN.PA': .20, 'CS.PA': .15, 'SAP.DE': .10, 'ENX.PA': .10}
    X = P[list(W)].loc[d0:].ffill()
    R = X.pct_change().fillna(0)
    # rééquilibrage annuel ; Euronext cotée depuis 2014 : sa part va aux 5 autres avant
    eq, val = [], 1.0
    w = None
    for i, dt in enumerate(R.index):
        if w is None or (i and dt.year != R.index[i - 1].year):
            av = {k: v for k, v in W.items() if np.isfinite(X[k].loc[dt])}
            tot = sum(av.values())
            w = {k: v / tot for k, v in av.items()}
        r = sum(w[k] * R[k].loc[dt] for k in w)
        val *= 1 + r
        w = {k: w[k] * (1 + R[k].loc[dt]) / (1 + r) for k in w}
        eq.append(val)
    eq = pd.Series(eq, index=R.index)
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    dd = (eq / eq.cummax() - 1).min()
    log(f"  {'miroir PEA (25/20/20/15/10/10)':28s} {(eq.iloc[-1] - 1) * 100:+6.0f} % · {(eq.iloc[-1] ** (1 / yrs) - 1) * 100:+5.1f} %/an · pire baisse {dd * 100:.0f} %"
        f" · 25 000 € → {25000 * eq.iloc[-1]:,.0f} €".replace(',', ' '))
    for y in (2012, 2016, 2020, 2024):
        v = eq[eq.index <= f'{y}-12-31']
        if len(v):
            log(f"    fin {y} : {25000 * v.iloc[-1]:,.0f} € (annoncé fin {y} : {dict([(2012, 42000), (2016, 58000), (2020, 72000), (2024, 125000)])[y]:,} €)".replace(',', ' '))
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
