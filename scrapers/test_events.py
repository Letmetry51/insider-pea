"""Tests de la collecte des événements Yahoo (scrapers/events.py) avec un faux yfinance : jeton refusé (401 Invalid Crumb, cas des
soirs du 03 au 12/11/2026), jeton retrouvé après attente, refus en cours de collecte ; fiches de la veille gardées, compteurs du
contrôle du soir (section « données financières »)."""
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yfinance  # noqa: E402
import events  # noqa: E402
import yahoo  # noqa: E402

events.time.sleep = lambda s: None  # même module time que yahoo : aucune attente réelle
ok = fail = 0
REFUS = 'HTTP Error 401: {"finance":{"result":null,"error":{"code":"Unauthorized","description":"Invalid Crumb"}}}'
MODE = {"info": "ok", "calls": 0, "refuse_after": None}


class FakeTicker:
    def __init__(self, ticker):
        self.ticker = ticker
        self.eps_trend = None
        self.earnings_estimate = None
        self.revenue_estimate = None

    def get_earnings_dates(self, limit=12):
        idx = pd.DatetimeIndex(["2027-02-10", "2026-10-28"])
        return pd.DataFrame({"EPS Estimate": [1.0, 0.9], "Reported EPS": [None, 1.1]}, index=idx)

    def get_news(self, count=25, tab="news"):
        return []

    def get_shares_full(self, start=None):
        return None

    @property
    def info(self):
        MODE["calls"] += 1
        refuse = MODE["info"] == "refus" or (MODE["refuse_after"] is not None and MODE["calls"] > MODE["refuse_after"])
        if refuse:
            raise Exception(REFUS)
        return {"longName": self.ticker, "marketCap": 2e9, "trailingPE": 12.5, "sector": "Industrials", "currentPrice": 10.0}


yfinance.Ticker = FakeTicker


def run(n=40, mode="ok", refuse_after=None):
    """Collecte sur n titres dans un dossier de données temporaire ; renvoie (items, compteurs de la section)."""
    d = Path(tempfile.mkdtemp())
    (d / "tickers.json").write_text(json.dumps({f"FR{k:010d}": {"ticker": f"T{k}.PA"} for k in range(n)}))
    events.DATA = d
    yahoo.DIAG = d / "diagnostics" / "yahoo.json"
    yahoo.STATS.clear()
    MODE.update(info=mode, calls=0, refuse_after=refuse_after)
    os.environ["EVENTS_THREADS"] = "1"
    os.environ["EVENTS_MINUTES"] = "0"
    assert events.main() == 0
    items = json.loads((d / "events.json").read_text())["items"]
    diag = json.loads(yahoo.DIAG.read_text())["sections"][events.INFO]
    return items, diag


def case(name):
    def deco(fn):
        global ok, fail
        try:
            fn(); ok += 1; print("OK  ", name)
        except Exception as e:
            fail += 1; print("ÉCHEC", name, "→", e)
        return fn
    return deco


@case("Jeton valable : fiches lues, compteurs complets")
def _():
    items, diag = run(40)
    assert len(items) == 40 and all(v["fund"] and v["fund"]["trailingPE"] == 12.5 for v in items.values())
    assert diag["requested"] == 40 and diag["received"] == 40 and diag["missing"] == 0, diag


@case("Jeton refusé toute la soirée : aucune fiche demandée, résultats gardés, compteur à 0 sur 40 (alerte du contrôle)")
def _():
    items, diag = run(40, mode="refus")
    assert len(items) == 40 and all(v["fund"] is None for v in items.values())
    assert all(v["earnings"] and v["nextEarnings"] == "2027-02-10" for v in items.values()), "dates de résultats perdues"
    assert MODE["calls"] == 5, f"fiches demandées malgré le refus : {MODE['calls']} (5 essais du témoin attendus)"
    assert diag["requested"] == 40 and diag["received"] == 0 and diag["missing"] == 40, diag


@case("Jeton empoisonné (réponse « Too Many Requests » gardée par yfinance) : repéré et remis à zéro")
def _():
    from yfinance.data import YfData
    YfData()._crumb = "Too Many Requests"
    assert yahoo.crumb_poisoned()
    assert yahoo.ensure_crumb(info=lambda: {"longName": "SAP SE"}) and YfData()._crumb is None
    YfData()._crumb = "aB3dEf.Gh1/"
    assert not yahoo.crumb_poisoned()
    YfData()._crumb = None


@case("Témoin refusé deux fois puis servi : jeton retrouvé après attente")
def _():
    n = {"k": 0}
    def flaky():
        n["k"] += 1
        if n["k"] <= 2:
            raise Exception(REFUS)
        return {"longName": "SAP SE"}
    assert yahoo.ensure_crumb(info=flaky) and n["k"] == 3


@case("Refus en cours de collecte : contrôle du jeton, puis fiches de la veille pour la suite (pas 600 refus)")
def _():
    items, diag = run(120, refuse_after=31)  # témoin + 30 fiches lues, puis refus
    assert diag["received"] == 30 and diag["requested"] == 120, diag
    assert MODE["calls"] < 31 + 30 + 3 + 5, f"trop de fiches demandées après le refus : {MODE['calls']}"
    assert sum(1 for v in items.values() if v["fund"]) == 30 and len(items) == 120


print(f"\n{ok} réussis, {fail} échoués")
sys.exit(1 if fail else 0)
