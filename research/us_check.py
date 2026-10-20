"""Contrôle indépendant : les règles 🎯 d'Euro Signal, sans aucun réglage, sur les actions américaines.

Univers : sociétés actuelles du S&P 500, du S&P 400 et du S&P 600 (≈ 1 500, listes Wikipedia), cours hebdomadaires Yahoo
ajustés des divisions et des dividendes, depuis 1985. Même calcul que pour l'Europe : le script chiffres_cles.py est lancé
tel quel sur ces cours (mêmes seuils, même mesure : écart à 6 mois avec la société moyenne de la même semaine).

Limite, comme pour l'Europe : seules les sociétés encore cotées (et ici présentes dans un indice) sont dans l'historique.

  python us_check.py            (GitHub Actions : workflow « Recherche (à la demande) », script us_check.py)
Résultats : out/us.npz (cours), out/us_check.txt (rapport).
"""
import io
import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
LISTS = {
    "S&P 500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "S&P 400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "S&P 600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
}


def log(*a):
    print(*a, flush=True)


def universe():
    syms = set()
    for name, url in LISTS.items():
        try:
            html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Euro Signal, recherche)"}, timeout=60).text
            for t in pd.read_html(io.StringIO(html)):
                col = next((c for c in t.columns if str(c).strip().lower() in ("symbol", "ticker", "ticker symbol")), None)
                if col is None:
                    continue
                s = {str(x).strip().replace(".", "-") for x in t[col] if isinstance(x, str) and 0 < len(x.strip()) <= 6}
                log(f"{name} : {len(s)} sociétés")
                syms |= s
                break
        except Exception as e:  # une liste manquante ne bloque pas les autres
            log(f"{name} : liste indisponible ({str(e)[:120]})")
    return sorted(syms)


def download(tick):
    """Même téléchargement que backtest/_long.py (Europe) : lots de 60, hebdomadaire, cours ajustés."""
    import yfinance as yf

    C, V = [], []
    for i in range(0, len(tick), 60):
        b = tick[i:i + 60]
        df = None
        for a in range(3):
            try:
                df = yf.download(b, period="max", interval="1wk", auto_adjust=True, progress=False, threads=True,
                                 group_by="column")
                break
            except Exception as e:
                log("lot", i, str(e)[:80])
                time.sleep(5)
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            C.append(df["Close"])
            V.append(df["Volume"])
        else:
            C.append(df[["Close"]].rename(columns={"Close": b[0]}))
            V.append(df[["Volume"]].rename(columns={"Volume": b[0]}))
        time.sleep(1)

    def tidy(F):
        X = pd.concat(F, axis=1)
        X = X.loc[:, ~X.columns.duplicated()]
        X.index = pd.to_datetime(X.index).tz_localize(None).normalize()
        return X.sort_index()

    return tidy(C).resample("W-FRI").last(), tidy(V).resample("W-FRI").sum(min_count=1)


def clean(P):
    """Comme pour l'Europe : chaque série est coupée avant son dernier saut anormal (×2,5 ou ÷2,9 en une semaine)."""
    P = np.where(P > 0, P, np.nan)
    cut = 0
    for i in range(P.shape[0]):
        p = P[i]
        ok = np.where(np.isfinite(p))[0]
        if len(ok) < 2:
            continue
        q = p[ok[1:]] / p[ok[:-1]]
        bad = np.where((q > 2.5) | (q < 0.35))[0]
        if len(bad):
            P[i, :ok[bad[-1] + 1]] = np.nan
            cut += 1
    return P, cut


def main():
    tick = universe()
    if len(tick) < 300:
        log("Univers trop petit : arrêt")
        return 1
    t0 = time.time()
    W, V = download(tick)
    log("téléchargé en", int(time.time() - t0), "s :", W.shape)
    W = W.loc["1985":]
    V = V.reindex(index=W.index, columns=W.columns)
    first = W.apply(lambda c: c.first_valid_index())
    log("début des séries : " + ", ".join(f"avant {y} : {(first < pd.Timestamp(str(y))).sum()}" for y in (1990, 1997, 2005, 2013)))
    P, cut = clean(W.values.T.astype(float))
    log("séries coupées après un saut anormal :", cut)
    npz = os.path.join(OUT, "us.npz")
    np.savez_compressed(npz, P=P.astype("float32"), V=V.values.T.astype("float32"),
                        dates=np.array([str(d.date()) for d in W.index]), cols=np.array(list(W.columns)))
    rep = subprocess.run([sys.executable, os.path.join(HERE, "chiffres_cles.py"), npz], capture_output=True, text=True)
    txt = "Règles 🎯 d'Euro Signal, sans réglage, sur les actions américaines (S&P 1500 actuel)\n\n" + rep.stdout + rep.stderr[-2000:]
    open(os.path.join(OUT, "us_check.txt"), "w").write(txt)
    log("\n" + txt)
    return rep.returncode


if __name__ == "__main__":
    sys.exit(main())
