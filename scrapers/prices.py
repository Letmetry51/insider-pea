"""
Euro Signal — cours quotidiens via Yahoo Finance (yfinance), exécuté par GitHub Actions.

- Univers : tous les émetteurs dont data/latest.json contient une déclaration portant sur des actions.
- Ticker : correspondance manuelle de run.py, sinon recherche Yahoo par ISIN (préférence Euronext Paris),
  mise en cache dans data/tickers.json (un échec est réessayé après 7 jours).
- Historique : 2 ans quotidiens. Yahoo fournit des cours déjà ajustés des divisions d'actions ; on les
  remet en cours bruts et on transmet la liste des divisions, pour que le moteur ajuste lui-même
  le prix payé par les dirigeants.
- Écrit data/prices.json (non versionné : régénéré à chaque exécution).
"""
import json
import math
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LATEST = DATA / "latest.json"
TICKERS = DATA / "tickers.json"
OUT = DATA / "prices.json"
BENCH = "^FCHI"  # CAC 40, indice de référence de l'étude d'événements
MARKET = "^STOXX"  # STOXX Europe 600 : force relative et tendance du marché européen
EU_SUFFIXES = (".PA", ".AS", ".BR", ".MI", ".MC", ".DE", ".LS", ".IR", ".VI", ".HE")
EU_ALL = EU_SUFFIXES + (".F", ".HM", ".SG", ".DU", ".MU", ".BE", ".HA")  # bourses régionales allemandes en dernier recours
HOME = {"FR": ".PA", "DE": ".DE", "IT": ".MI", "ES": ".MC", "NL": ".AS", "BE": ".BR", "PT": ".LS", "IE": ".IR", "AT": ".VI", "FI": ".HE", "LU": ".PA"}
UA = {"User-Agent": "Mozilla/5.0 (euro-signal personal)"}


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def manual_map():
    try:
        sys.path.insert(0, str(ROOT))
        from run import ISIN_TO_TICKER  # correspondances déjà vérifiées dans insider-pea
        return dict(ISIN_TO_TICKER)
    except Exception:
        return {}


def search_yahoo(isin):
    quotes = []
    try:
        quotes = yf.Search(isin, max_results=8).quotes or []
    except Exception:
        try:
            r = requests.get("https://query2.finance.yahoo.com/v1/finance/search", params={"q": isin, "quotesCount": 8, "newsCount": 0}, headers=UA, timeout=20)
            quotes = r.json().get("quotes", []) if r.ok else []
        except Exception:
            quotes = []
    eq = [q for q in quotes if q.get("quoteType") == "EQUITY" and q.get("symbol")]
    if not eq:
        return None
    home = HOME.get(isin[:2], ".PA")
    # Cotation du pays d'origine d'abord (prix déclarés en euros), puis grandes places européennes, puis le reste
    eq.sort(key=lambda q: (not q["symbol"].endswith(home), not q["symbol"].endswith(EU_SUFFIXES), not q["symbol"].endswith(EU_ALL)))
    q = eq[0]
    return {"ticker": q["symbol"], "exchange": q.get("exchDisp") or q.get("exchange"), "name": q.get("longname") or q.get("shortname")}


def resolve(isin, cache, manual, today):
    if isin in manual and manual[isin]:
        return {"ticker": manual[isin], "method": "correspondance insider-pea"}
    c = cache.get(isin)
    if c and c.get("ticker") and not (not str(c["ticker"]).endswith(EU_SUFFIXES) and not c.get("checkedHome")):
        return c
    if c and c.get("ticker"):  # cotation hors grandes places européennes : une nouvelle recherche, une seule fois
        found = search_yahoo(isin) or c
        found.update({"checkedHome": today.isoformat(), "method": found.get("method") or "recherche Yahoo par ISIN"})
        cache[isin] = found
        time.sleep(0.3)
        return found
    if c and not c.get("ticker") and c.get("triedAt", "") > (today - timedelta(days=7)).isoformat():
        return None
    found = search_yahoo(isin)
    if found:
        found.update({"method": "recherche Yahoo par ISIN", "resolvedAt": today.isoformat()})
        cache[isin] = found
        time.sleep(0.3)
        return found
    cache[isin] = {"ticker": None, "triedAt": today.isoformat()}
    return None


def history(ticker):
    t = yf.Ticker(ticker)
    h = t.history(period="2y", interval="1d", auto_adjust=False, actions=True)
    if h is None or h.empty:
        return None
    currency = None
    try:
        currency = (t.history_metadata or {}).get("currency")
    except Exception:
        pass
    splits = []
    if "Stock Splits" in h.columns:
        for idx, v in h["Stock Splits"].items():
            if v and not math.isnan(v) and v > 0 and v != 1:
                splits.append({"date": idx.strftime("%Y-%m-%d"), "ratio": float(v)})
    rows = []
    for idx, r in h.iterrows():
        c = r.get("Close")
        if c is None or math.isnan(c) or c <= 0:
            continue
        d = idx.strftime("%Y-%m-%d")
        f = 1.0
        for s in splits:
            if s["date"] > d:
                f *= s["ratio"]  # retour au cours brut publié ce jour-là

        def px(x):
            return None if x is None or math.isnan(x) or x <= 0 else round(float(x) * f, 6)

        vol = r.get("Volume")
        rows.append([d, px(r.get("Open")), px(r.get("High")), px(r.get("Low")), px(c), None if vol is None or math.isnan(vol) else round(float(vol) / f)])
    return {"rows": rows, "splits": splits, "currency": currency}


def main():
    today = datetime.utcnow().date()
    latest = load(LATEST, None)
    if not latest:
        print("data/latest.json absent : aucun cours collecté")
        return 0
    isins = set()
    for t in latest.get("transactions", []):
        isin = str(t.get("isin") or "").upper()
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin) and str(t.get("instrument") or "").strip().lower() in ("action", "actions"):
            isins.add(isin)
    # Déclarations hors France (FSMA, AFM) : mêmes besoins de cours
    eu = load(DATA / "insiders-eu.json", {}).get("records", {})
    share_words = {"share", "shares", "aandeel", "aandelen", "aktie", "aktien", "azioni", "acciones", "action", "actions", "ordinary shares", ""}
    for r in eu.values():
        isin = str(r.get("isin") or "").upper().replace(" ", "")
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin) and str(r.get("instrument") or "").strip().lower() in share_words:
            isins.add(isin)
    cache = load(TICKERS, {})
    manual = manual_map()
    items, unresolved = {}, []
    print(f"Cours Yahoo : {len(isins)} émetteurs")
    for n, isin in enumerate(sorted(isins), 1):
        info = resolve(isin, cache, manual, today)
        if not info:
            unresolved.append(isin)
            continue
        try:
            h = history(info["ticker"])
        except Exception as e:
            print(f"  [{n}] {isin} {info['ticker']} : erreur {str(e)[:80]}")
            h = None
        if not h:
            unresolved.append(isin)
            continue
        items[isin] = {"ticker": info["ticker"], "exchange": info.get("exchange"), "name": info.get("name"), "currency": h["currency"], "rows": h["rows"], "splits": h["splits"], "method": info.get("method")}
        print(f"  [{n}/{len(isins)}] {isin} {info['ticker']} : {len(h['rows'])} séances")
        time.sleep(0.2)
    bench = None
    try:
        b = history(BENCH)
        if b:
            bench = {"ticker": BENCH, "rows": b["rows"]}
    except Exception as e:
        print("Indice de référence indisponible :", e)
    market = None
    try:
        m = history(MARKET)
        if m:
            market = {"ticker": MARKET, "rows": m["rows"]}
    except Exception as e:
        print("Indice européen indisponible :", e)
    if market is None and bench:
        market = bench  # repli : CAC 40
    OUT.write_text(json.dumps({"generated_at": datetime.utcnow().isoformat(), "items": items, "bench": bench, "market": market, "unresolved": unresolved}), encoding="utf-8")
    TICKERS.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"Cours écrits : {len(items)} titres, {len(unresolved)} sans cours")
    return 0


if __name__ == "__main__":
    sys.exit(main())
