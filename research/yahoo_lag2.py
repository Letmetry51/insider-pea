"""Sonde : le secours « Yahoo titre par titre » de scrapers/backup_prices.py, sur de vrais titres (dernier cours et sa date)."""
import datetime as dt
import sys
sys.path.insert(0, "../scrapers")
import backup_prices as B  # noqa: E402

T = ["SAP.DE", "SIE.DE", "BARC.L", "VOLV-B.ST", "SAN.MC", "ITX.MC", "NOKIA.HE", "NOVO-B.CO", "OMV.VI", "NESN.SW", "MC.PA", "XXXX.DE"]
today = dt.datetime.now(dt.timezone.utc).date().isoformat()
print("Heure (UTC) :", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"))
md = B._yahoo_meta("SAP.DE")
print("  en-tête SAP.DE :", {k: md.get(k) for k in ("regularMarketPrice", "regularMarketTime", "exchangeTimezoneName", "currency", "regularMarketVolume")})
q, st = B.yahoo_quotes(T, today)
for s in T:
    print(f"  {s:10s} {q.get(s)}")
print("  compteurs :", st)
