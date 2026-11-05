"""Volatilité implicite (05/11/2026, livre « Les secrets du trading sur la volatilité ») : séries hebdomadaires (clôture du vendredi)
du VIX (S&P 500, 30 jours), du VIX 3 mois (VIX3M, anciennement VXV), du VSTOXX (Euro Stoxx 50, 30 jours) et des indices, pour
tester dans le portefeuille simulé de la sélection (research/backtest) : niveau de peur, retour à la moyenne, structure par terme
(VIX3M / VIX : au-dessus de 1, marché confiant ; en dessous, tension). Imprimé en base64 entre FIGURES-DEBUT et FIGURES-FIN
(python backtest/_bougies_masque.py journal.log volatilite.npz). Lancé par « Recherche (à la demande) » (script volatilite.py),
environ 1 minute."""
import base64
import io
import time

import numpy as np
import pandas as pd
import yfinance as yf

TICK = {'vix': '^VIX', 'vix3m': '^VIX3M', 'vxv': '^VXV', 'v2tx': '^V2TX', 'sx5e': '^STOXX50E', 'stoxx': '^STOXX', 'gspc': '^GSPC',
        'fchi': '^FCHI'}


def log(*a):
    print(*a, flush=True)


def main():
    t0 = time.time()
    S = {}
    for k, sym in TICK.items():
        for a in range(3):
            try:
                df = yf.download(sym, period='max', interval='1d', auto_adjust=False, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                log(k, 'erreur', str(e)[:80])
                df = None
                time.sleep(3)
        if df is None or df.empty:
            log(f"{k:6s} {sym:10s} : rien")
            continue
        c = df['Close']
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        c = c.dropna()
        c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
        S[k] = c
        log(f"{k:6s} {sym:10s} : {len(c)} séances, {c.index[0].date()} → {c.index[-1].date()}, dernier {c.iloc[-1]:.2f}")
    W = pd.DataFrame({k: v.resample('W-FRI').last() for k, v in S.items()})
    W = W[W.index >= '1990-01-01']
    log(f"hebdomadaire : {len(W)} semaines, {W.index[0].date()} → {W.index[-1].date()}")
    for k in W.columns:
        s = W[k].dropna()
        if len(s):
            log(f"  {k:6s} {len(s)} semaines depuis {s.index[0].date()} ; médiane {s.median():.2f}, 10 % {s.quantile(.1):.2f}, 90 % {s.quantile(.9):.2f}")
    buf = io.BytesIO()
    np.savez_compressed(buf, dates=np.array([str(d.date()) for d in W.index]), **{k: W[k].values.astype('float64') for k in W.columns})
    s = base64.b64encode(buf.getvalue()).decode()
    log(f"fichier : {len(s)} caractères en base64")
    print("FIGURES-DEBUT", flush=True)
    for i in range(0, len(s), 8000):
        print("B64:" + s[i:i + 8000], flush=True)
    print("FIGURES-FIN", flush=True)
    log(f"terminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
