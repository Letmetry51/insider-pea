"""
Euro Signal — événements des sociétés via Yahoo Finance (exécuté par GitHub Actions, après prices.py).

Pour chaque titre dont le ticker est connu (data/tickers.json) :
  - publications de résultats : BPA publié et consensus (estimation figée à la publication) ;
  - communiqués de l'émetteur (onglet « press releases ») : titre, date, diffuseur, lien ;
  - tendance du BPA annuel estimé (actuel / il y a 30 jours) : révisions des analystes.
L'interprétation (rachat, perspectives, surprise) est faite par le moteur Euro Signal (core.js), testé.
Écrit data/events.json (régénéré à chaque exécution ; l'historique est conservé par build.mjs).
"""
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def num(v):
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return None


def press_items(t):
    out = []
    for tab in ("press releases", "news"):
        try:
            items = t.get_news(count=25, tab=tab) or []
        except Exception:
            items = []
        for it in items:
            c = it.get("content", it) or {}
            title = c.get("title")
            when = c.get("pubDate") or c.get("displayTime") or it.get("providerPublishTime")
            if isinstance(when, (int, float)):
                when = datetime.fromtimestamp(when, timezone.utc).isoformat()
            prov = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else it.get("publisher")
            url = ((c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else None) or ((c.get("clickThroughUrl") or {}).get("url") if isinstance(c.get("clickThroughUrl"), dict) else None) or it.get("link")
            if title and when:
                out.append({"title": title, "date": str(when)[:10], "provider": prov, "url": url, "tab": tab})
        if out and tab == "press releases":
            break  # les communiqués de l'émetteur suffisent quand ils existent
    return out


FUND_KEYS = {"totalDebt": "totalDebt", "totalCash": "totalCash", "ebitda": "ebitda", "freeCashflow": "freeCashflow",
             "operatingCashflow": "operatingCashflow", "profitMargins": "profitMargins", "returnOnEquity": "returnOnEquity",
             "currentRatio": "currentRatio", "debtToEquity": "debtToEquity", "marketCap": "marketCap",
             # multiples de valorisation : comparaison aux sociétés du même secteur (décote par rapport aux pairs)
             "forwardPE": "forwardPE", "trailingPE": "trailingPE", "evToEbitda": "enterpriseToEbitda", "priceToBook": "priceToBook",
             # taille : position concurrentielle (leader / challenger) parmi les sociétés suivies
             "revenue": "totalRevenue"}


def fundamentals(t):
    """Dernières données financières publiées (Yahoo). Non historisées : jamais utilisées pour la validation."""
    try:
        inf = t.info or {}
    except Exception:
        return None
    out = {k: num(inf.get(src)) for k, src in FUND_KEYS.items()}
    if all(v is None for v in out.values()):
        return None
    out.update({"sector": inf.get("sector"), "industry": inf.get("industry"), "currency": inf.get("financialCurrency"),
                "asOf": datetime.now(timezone.utc).date().isoformat()})
    return out


def main():
    try:
        tickers = json.loads((DATA / "tickers.json").read_text(encoding="utf-8"))
    except Exception:
        print("data/tickers.json absent : aucun événement collecté")
        return 0
    items, errors = {}, 0
    pairs = [(isin, v["ticker"]) for isin, v in tickers.items() if v.get("ticker")]
    try:
        prices = json.loads((DATA / "prices.json").read_text(encoding="utf-8")).get("items", {})
        pairs = [(i, prices[i]["ticker"]) for i in prices] or pairs  # mêmes tickers que les cours
    except Exception:
        pass
    print(f"Événements Yahoo : {len(pairs)} titres")
    for n, (isin, ticker) in enumerate(pairs, 1):
        t = yf.Ticker(ticker)
        rec = {"ticker": ticker, "earnings": [], "press": [], "epsTrend": None, "fund": None, "nextEarnings": None}
        try:
            ed = t.get_earnings_dates(limit=12)
            if ed is not None and not ed.empty:
                for idx, row in ed.iterrows():
                    rec["earnings"].append({"date": idx.strftime("%Y-%m-%d"), "epsEstimate": num(row.get("EPS Estimate")), "epsActual": num(row.get("Reported EPS"))})
                today_s = datetime.now(timezone.utc).date().isoformat()
                fut = sorted(e["date"] for e in rec["earnings"] if e["date"] > today_s)
                rec["nextEarnings"] = fut[0] if fut else None
        except Exception:
            errors += 1
        try:
            rec["press"] = press_items(t)
        except Exception:
            errors += 1
        try:
            tr = t.eps_trend
            if tr is not None and not tr.empty and "0y" in tr.index:
                rec["epsTrend"] = {"current": num(tr.loc["0y"].get("current")), "d30": num(tr.loc["0y"].get("30daysAgo"))}
        except Exception:
            pass
        rec["fund"] = fundamentals(t)
        items[isin] = rec
        time.sleep(0.4)
        if n % 20 == 0:
            print(f"  {n}/{len(pairs)}")
    (DATA / "events.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "items": items, "errors": errors}, ensure_ascii=False), encoding="utf-8")
    withE = sum(1 for v in items.values() if v["earnings"])
    withP = sum(1 for v in items.values() if v["press"])
    withF = sum(1 for v in items.values() if v.get("fund"))
    print(f"Données financières : {withF} titres ; prochaines publications connues : {sum(1 for v in items.values() if v.get('nextEarnings'))}")
    print(f"Événements écrits : {len(items)} titres, {withE} avec résultats, {withP} avec communiqués, {errors} erreur(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
