"""Sonde : à quelle heure Yahoo a-t-il la clôture de la veille pour chaque place ? Dernières séances (journalier) de quelques titres."""
import datetime as dt
import yfinance as yf

T = ["SAP.DE", "SIE.DE", "BARC.L", "SHEL.L", "VOLV-B.ST", "ERIC-B.ST", "SAN.MC", "ITX.MC", "NOKIA.HE", "NOVO-B.CO",
     "OMV.VI", "NESN.SW", "MC.PA", "TTE.PA", "ASML.AS", "ENI.MI", "EQNR.OL", "^STOXX"]
print("Heure de la sonde (UTC) :", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"))
X = yf.download(T, period="7d", interval="1d", auto_adjust=True, progress=False, threads=True, group_by="column")
C = X["Close"]
for t in T:
    s = C[t].dropna() if t in C else None
    last = ", ".join(f"{d.date()} {v:.2f}" for d, v in s.tail(3).items()) if s is not None and len(s) else "rien"
    print(f"  download {t:10s} {last}")
for t in ("SAP.DE", "SAN.MC", "VOLV-B.ST", "MC.PA"):
    h = yf.Ticker(t).history(period="7d", interval="1d", auto_adjust=True)
    print(f"  history  {t:10s}", ", ".join(f"{d.date()} {v:.2f}" for d, v in h["Close"].tail(3).items()))
    fi = yf.Ticker(t).fast_info
    try:
        print(f"           prix {fi['lastPrice']:.2f}, clôture précédente {fi['previousClose']:.2f}")
    except Exception as e:
        print("           fast_info :", type(e).__name__)
