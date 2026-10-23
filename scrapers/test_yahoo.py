"""Tests du lien Yahoo robuste (scrapers/yahoo.py) avec un faux yf.download : erreurs passagères, titres manquants, compteurs."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yahoo  # noqa: E402
import yfinance as yf  # noqa: E402

yahoo.time.sleep = lambda s: None
ok = fail = 0


def case(name):
    def deco(fn):
        global ok, fail
        try:
            fn(); ok += 1; print("OK  ", name)
        except Exception as e:
            fail += 1; print("ÉCHEC", name, "→", e)
        return fn
    return deco


IDX = pd.date_range("2026-01-02", periods=30, freq="W-FRI")


def frame(tickers):
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    return pd.DataFrame(np.ones((len(IDX), len(cols))), index=IDX, columns=cols)


@case("Erreur passagère (401 puis 429) : nouvelles tentatives, rien de perdu")
def _():
    calls = {"n": 0}
    def fake(b, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("401 Unauthorized: Invalid Crumb")
        if calls["n"] == 2:
            raise Exception("429 Too Many Requests")
        return frame(b)
    yf.download = fake; yahoo.STATS.clear()
    fr = yahoo.download(["A.PA", "B.PA"], "t1")
    assert list(fr["Close"].columns) == ["A.PA", "B.PA"] and yahoo.STATS["t1"]["received"] == 2 and yahoo.STATS["t1"]["errors"] == 2, yahoo.STATS


@case("Titres absents d'un lot : récupérés en deuxième passe, les autres comptés manquants")
def _():
    def fake(b, **kw):
        keep = [t for t in b if t != "C.PA" and not (len(b) > 1 and t == "B.PA")]  # B.PA n'arrive que seul ; C.PA jamais
        f = frame(b)
        for t in b:
            if t not in keep:
                f[("Close", t)] = np.nan
        return f
    yf.download = fake; yahoo.STATS.clear()
    fr = yahoo.download(["A.PA", "B.PA", "C.PA"], "t2")
    st = yahoo.STATS["t2"]
    assert fr["Close"]["B.PA"].notna().all() and st["received"] == 2 and st["recovered"] == 1 and st["missing"] == 1, st


@case("Yahoo totalement muet : résultat vide, sans exception")
def _():
    def fake(b, **kw):
        raise Exception("Connection reset")
    yf.download = fake; yahoo.STATS.clear()
    fr = yahoo.download(["A.PA"], "t3")
    assert fr["Close"].empty and yahoo.STATS["t3"]["missing"] == 1


@case("Compteurs : parties des 20 dernières heures gardées (historique du matin, passage de minuit), anciennes effacées")
def _():
    import json, tempfile
    from datetime import datetime, timezone
    keep = yahoo.DIAG
    try:
        yahoo.DIAG = Path(tempfile.mkdtemp()) / "yahoo.json"
        yahoo.DIAG.write_text(json.dumps({"date": "2026-10-22", "at": "2026-10-22T21:40:00+00:00", "sections": {
            "journalier": {"requested": 3829, "received": 3829, "at": "2026-10-22T21:10:00+00:00"},
            "ancien": {"requested": 5, "received": 5, "at": "2026-10-21T21:10:00+00:00"},
            "sans heure": {"requested": 7, "received": 7}}}))
        yahoo.STATS.clear(); yahoo._stat("hebdomadaire", requested=1077, received=1077)
        yahoo.write_diag(now=datetime(2026, 10, 23, 8, 8, tzinfo=timezone.utc))
        d = json.loads(yahoo.DIAG.read_text())
        assert set(d["sections"]) == {"journalier", "sans heure", "hebdomadaire"}, d["sections"].keys()
        assert d["date"] == "2026-10-23" and d["sections"]["hebdomadaire"]["at"].startswith("2026-10-23T08:08")
    finally:
        yahoo.DIAG = keep; yahoo.STATS.clear()


print(f"\n{ok} réussis, {fail} échoués")
sys.exit(1 if fail else 0)
