"""Sonde des sources du Bulletin des grains (11/11/2026) : historique du prix physique des orges brassicoles (dates, doublons,
écart avec la variation terre-net) et sources de secours pour le gaz TTF (Yahoo refuse les demandes depuis le 9/11)."""
import csv
import json
import pathlib

import requests

P = pathlib.Path("../data/grain/prive")
rows = list(csv.DictReader((P / "physique_hist.csv").open(encoding="utf-8"))) if (P / "physique_hist.csv").exists() else []
print("physique_hist :", len(rows), "lignes")
for var in ("etincel", "planet"):
    rs = [r for r in rows if r["page"] == "orge_brassicole" and var in (r["titre"] + r["place"]).lower() and "creil" in (r["titre"] + r["place"]).lower()]
    print(f"\n== {var} Creil : {len(rs)} lignes ; 12 dernières :")
    for r in rs[-12:]:
        print("  ", r["date"], r["prix"], "|", r["place"], "|", r["titre"][:70])
four = [r for r in rows if r["page"] == "orge" and "creil" in (r["titre"] + r["place"]).lower()]
print("\n== orge fourragère Creil, 6 dernières :")
for r in four[-6:]:
    print("  ", r["date"], r["prix"], "|", r["titre"][:70])

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
print("\n== gaz TTF")
try:
    import yfinance as yf
    for per in ("5d", "1mo"):
        h = yf.Ticker("TTF=F").history(period=per)
        print(f"  yfinance TTF=F {per} : {len(h)} séances", (h.index[-1].date(), float(h['Close'].iloc[-1])) if len(h) else "")
except Exception as e:  # noqa: BLE001
    print("  yfinance :", str(e)[:150])
for url in ("https://query1.finance.yahoo.com/v8/finance/chart/TTF=F?range=1mo&interval=1d",
            "https://query2.finance.yahoo.com/v8/finance/chart/TTF%3DF?range=5d&interval=1d",
            "https://stooq.com/q/d/l/?s=ttf.f&i=d",
            "https://www.barchart.com/proxies/core-api/v1/historical/get?symbol=TGZ26&fields=tradeTime,closePrice&type=eod&limit=5",
            "https://api.energy-charts.info/price?bzn=DE-LU"):
    try:
        r = requests.get(url, headers=UA, timeout=30)
        print(f"  {url[:70]} : HTTP {r.status_code}, {len(r.text)} car. : {r.text[:160]!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  {url[:70]} : {str(e)[:120]}")
