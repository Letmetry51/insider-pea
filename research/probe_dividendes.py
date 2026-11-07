"""
Sonde temporaire (relecture du 07/11/2026, retirée avant fusion) : téléchargement journalier des fiches avec dividendes
(scrapers/sectors.py daily_series, actions=True) comparé au téléchargement actuel sans dividendes.

  python probe_dividendes.py   (GitHub Actions, workflow research.yml)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scrapers"))
import sectors as S  # noqa: E402
import yahoo  # noqa: E402

T = ["TTE.PA", "SAN.PA", "BNP.PA", "OR.PA", "MC.PA", "AI.PA", "ENEL.MI", "ISP.MI", "SAP.DE", "ALV.DE", "BAS.DE", "ASML.AS",
     "INGA.AS", "IBE.MC", "SAN.MC", "NOVO-B.CO", "EQNR.OL", "WAWI.OL", "FRO.OL", "VOLV-B.ST", "NESTE.HE", "KBC.BR", "GALP.LS",
     "OMV.VI", "DEC.PA", "ALO.PA", "RBI.VI", "STLAM.MI", "MT.AS", "HEI.DE"]

X, V, DIV = S.daily_series(T)
F0 = yahoo.download(T, "sans dividendes", period="1y", interval="1d", fields=("Close", "Volume"))
X0 = F0["Close"].where(F0["Close"] > 0)
print("avec dividendes :", X.shape, "dernière séance", X.index[-1].date() if len(X) else None)
print("sans dividendes :", X0.shape, "dernière séance", X0.index[-1].date() if len(X0) else None)
print("colonnes Dividends :", list(DIV.columns)[:5], "…", DIV.shape)
common = [c for c in X.columns if c in X0.columns]
idx = X.index.intersection(X0.index)
a, b = X.loc[idx, common], X0.loc[idx, common]
diff = ((a - b).abs() / b).max().max()
print("écart relatif maximal des clôtures (mêmes dates) :", diff)
only_new = X.index.difference(X0.index)
only_old = X0.index.difference(X.index)
print("dates en plus avec dividendes :", [d.date() for d in only_new][:10], "; en moins :", [d.date() for d in only_old][:10])
empty = int(X.isna().all(axis=1).sum())
print("lignes sans aucun cours gardées :", empty)
R = yahoo.download(T, "brut avec dividendes", period="1y", interval="1d", fields=("Close", "Volume", "Dividends"), actions=True)
raw_empty = R["Close"].isna().all(axis=1)
print("lignes sans aucun cours ajoutées par yfinance (avant filtrage) :", [d.date() for d in R["Close"].index[raw_empty]])
for s in T:
    dv = S.daily_dividends(DIV, s, X.index[0].strftime("%Y-%m-%d")) if s in X.columns else None
    last = X[s].dropna().index[-1].date() if s in X.columns and X[s].notna().any() else None
    print(f"  {s:10s} dernière clôture {last}  dividendes {dv}")
vol = S.daily_volumes(V, "TTE.PA", X.index)
print("volumes TTE.PA (5 dernières) :", vol[-5:] if vol else None)
print("NaN dans les volumes alignés :", int(np.isnan(V.reindex(X.index).values.astype(float)).sum()) if not V.empty else None,
      "sur", V.size if not V.empty else 0, ";", pd.__version__)
