"""Indicateurs de contexte de l'ancien outil « Rotation PEA » (05/11/2026) : écart de crédit Baa − Aaa (Moody's, FRED), écart Baa − taux
à 10 ans (FRED), pétrole Brent (FRED), CAPE de Shiller (données de R. Shiller), taux à 10 ans américain. Séries hebdomadaires
(vendredi) imprimées en base64 entre FIGURES-DEBUT et FIGURES-FIN (python backtest/_bougies_masque.py journal.log macro.npz), pour le
portefeuille simulé de la sélection. Lancé par « Recherche (à la demande) » (script macro_regime.py), environ 1 minute."""
import base64
import io
import time

import numpy as np
import pandas as pd
import requests

FRED = {'baa': 'BAA', 'aaa': 'AAA', 'baa10y': 'BAA10Y', 'brent': 'DCOILBRENTEU', 'dgs10': 'DGS10', 'hy': 'BAMLH0A0HYM2'}
UA = {'User-Agent': 'Mozilla/5.0 (recherche Euro Signal)'}


def log(*a):
    print(*a, flush=True)


def fred(code):
    r = requests.get('https://fred.stlouisfed.org/graph/fredgraph.csv', params={'id': code}, headers=UA, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ['date', 'v']
    df['date'] = pd.to_datetime(df['date'])
    df['v'] = pd.to_numeric(df['v'], errors='coerce')
    return df.dropna().set_index('date')['v']


def shiller_cape():
    r = requests.get('http://www.econ.yale.edu/~shiller/data/ie_data.xls', headers=UA, timeout=90)
    r.raise_for_status()
    x = pd.read_excel(io.BytesIO(r.content), sheet_name='Data', skiprows=7)
    x = x[['Date', 'CAPE']].dropna()
    d = x['Date'].astype(float)
    yr = d.astype(int)
    mo = ((d - yr) * 100).round().astype(int).clip(1, 12)
    idx = pd.to_datetime(dict(year=yr, month=mo, day=1)) + pd.offsets.MonthEnd(0)
    return pd.Series(pd.to_numeric(x['CAPE'], errors='coerce').values, index=idx).dropna()


def main():
    t0 = time.time()
    S = {}
    for k, code in FRED.items():
        try:
            s = fred(code)
            S[k] = s
            log(f"{k:7s} {code:13s} : {len(s)} valeurs, {s.index[0].date()} → {s.index[-1].date()}, dernier {s.iloc[-1]:.2f}")
        except Exception as e:  # noqa: BLE001
            log(f"{k:7s} {code:13s} : échec {type(e).__name__} {str(e)[:80]}")
    try:
        c = shiller_cape()
        S['cape'] = c
        log(f"cape    Shiller       : {len(c)} valeurs, {c.index[0].date()} → {c.index[-1].date()}, dernier {c.iloc[-1]:.1f}")
    except Exception as e:  # noqa: BLE001
        log(f"cape    Shiller       : échec {type(e).__name__} {str(e)[:120]}")
    # hebdomadaire (vendredi) : dernière valeur connue (séries mensuelles reportées jusqu'à la publication suivante)
    idx = pd.date_range('1985-01-04', pd.Timestamp.today(), freq='W-FRI')
    W = pd.DataFrame({k: v.sort_index().reindex(v.index.union(idx)).ffill().reindex(idx) for k, v in S.items()})
    for k in W.columns:
        s = W[k].dropna()
        log(f"  {k:7s} {len(s)} semaines ; médiane {s.median():.2f}, 10 % {s.quantile(.1):.2f}, 90 % {s.quantile(.9):.2f}")
    buf = io.BytesIO()
    np.savez_compressed(buf, dates=np.array([str(d.date()) for d in W.index]), **{k: W[k].values.astype('float64') for k in W.columns})
    s = base64.b64encode(buf.getvalue()).decode()
    print("FIGURES-DEBUT", flush=True)
    for i in range(0, len(s), 8000):
        print("B64:" + s[i:i + 8000], flush=True)
    print("FIGURES-FIN", flush=True)
    log(f"terminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
