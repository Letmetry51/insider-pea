"""Vérification réseau des corrections du 15/11/2026 (audit) : jeton Yahoo empoisonné repéré et remis à zéro (scrapers/yahoo.py,
ensure_crumb), ETF de secours du STOXX Europe 600 (scrapers/prices.py, fill_market). Lancé par « Recherche (à la demande) »
(script verif_yahoo_jeton.py), moins d'une minute."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
import yfinance as yf  # noqa: E402
from yfinance.data import YfData  # noqa: E402
import yahoo  # noqa: E402
import prices as P  # noqa: E402

print("yfinance", yf.__version__)
inf = yf.Ticker("SAP.DE").info or {}
print("fiche SAP.DE :", bool(inf.get("longName")), "jeton valable :", not yahoo.crumb_poisoned(), "longueur", len(str(YfData()._crumb)))
YfData()._crumb = "Too Many Requests"  # ce que yfinance 1.8 garde après un getcrumb limité (HTTP 429)
print("jeton empoisonné repéré :", yahoo.crumb_poisoned())
try:
    yf.Ticker("EVK.DE").info
    print("fiche avec le jeton empoisonné : servie (yfinance a renouvelé le jeton seul)")
except Exception as e:
    print("fiche avec le jeton empoisonné : refusée →", str(e)[:120])
YfData()._crumb = "Too Many Requests"
print("ensure_crumb :", yahoo.ensure_crumb(waits=(0, 10)), "jeton après :", str(YfData()._crumb)[:4] + "…")
m = P.history("^STOXX")
print("^STOXX : dernière séance", m["rows"][-1][0] if m else None)
for pt in P.MARKET_PROXIES:
    p = P.history(pt, period="1mo")
    rows = (p or {}).get("rows") or []
    print(pt, ":", len(rows), "séances, dernière", rows[-1][0] if rows else None, "devise", (p or {}).get("currency"))
    if m and rows:
        cut = dict(m, rows=m["rows"][:-1])
        f = P.fill_market(cut, rows, m["rows"][-1][0])
        if f is not cut:
            est, real = f["rows"][-1][4], m["rows"][-1][4]
            print(f"  séance {f['filled'][-1]} estimée {est:.2f} contre {real:.2f} publiée ({(est / real - 1) * 100:+.2f} %)")
