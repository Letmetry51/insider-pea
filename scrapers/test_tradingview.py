"""
Tests hors ligne de TradingView (aucun accès réseau) : lecture des réponses du screener (symboles Yahoo, date de la séance à l'heure
de la bourse, devise, F-score), bourse en panne, fichier du soir ; dernier recours des cours de secours (séance, jour du fichier,
priorité aux autres sources, garde-fous) ; contrôle des F-scores (euro_signal/tv_check.py).

  python scrapers/test_tradingview.py
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "euro_signal"))
import backup_prices as B  # noqa: E402
import tradingview as T  # noqa: E402
import tv_check as C  # noqa: E402

results = []
NOV17 = 1794873600  # 17/11/2026 00:00 UTC : « daily-bar.time » réel (sonde du 17/11/2026)
FY25 = 1767139200  # 31/12/2025


def case(name):
    def deco(fn):
        try:
            fn()
            results.append(("OK  ", name, ""))
        except Exception as e:  # noqa: BLE001
            results.append(("ÉCHEC", name, repr(e)))
        return fn
    return deco


def row(name, close=10.0, cur="EUR", ts=NOV17, f9=7, fy=FY25):
    # ordre de T.COLS : name, close, open, high, low, currency, daily-bar.time, piotroski_f_score_fy, fiscal_period_end_fy
    hi, lo = (close + 1, close - 1) if close else (None, None)
    return {"s": "X:" + name, "d": [name, close, close, hi, lo, cur, ts, f9, fy]}


@case("symboles TradingView → Yahoo (Londres, Nordiques, Xetra)")
def _():
    assert T.yahoo_symbol("BA.", "L") == "BA.L" and T.yahoo_symbol("BT.A", "L") == "BT-A.L"
    assert T.yahoo_symbol("VOLV_B", "ST") == "VOLV-B.ST" and T.yahoo_symbol("NDA_FI", "HE") == "NDA-FI.HE"
    assert T.yahoo_symbol("MAERSK_B", "CO") == "MAERSK-B.CO" and T.yahoo_symbol("drw3", "DE") == "DRW3.DE"
    assert T.yahoo_symbol("", "PA") is None and T.yahoo_symbol("A B", "PA") is None


@case("date de la séance : heure de la bourse, secondes ou millisecondes")
def _():
    assert T.day_of(NOV17, "Europe/Paris") == "2026-11-17" and T.day_of(NOV17 * 1000, "Europe/London") == "2026-11-17"
    assert T.day_of(None, "Europe/Paris") is None and T.day_of(-5, "Europe/Paris") is None and T.day_of(True, "UTC") is None


@case("réponse du screener : clôture, devise GBX → GBp, F-score, lignes incomplètes ignorées")
def _():
    js = {"data": [row("AZN", 13802, "GBX", f9=7), row("BA.", 1200, "GBX", f9=None), row("X", None),
                   row("Y", 5, ts=None), {"s": "bad", "d": [1, 2]}, row("Z", 3, f9=11), row("AZN", 1)]}
    got = T.parse(js, "L", "Europe/London")
    assert set(got) == {"AZN.L", "BA.L", "Z.L"}, got
    assert got["AZN.L"] == ["2026-11-17", 13802.0, 13802.0, 13803.0, 13801.0, "GBp", 7, "2025-12-31"], got["AZN.L"]
    assert got["AZN.L"][1] == 13802.0  # premier gardé (tri par capitalisation)
    assert got["BA.L"][6] is None and got["Z.L"][6] is None  # F-score absent ou hors de 0 à 9


@case("une requête par bourse ; bourse en panne notée sans arrêter les autres")
def _():
    asked = []

    def post(url, b):
        asked.append((url, b["markets"], b["filter"][1]["right"]))
        if "austria" in url:
            raise ConnectionError("refusé")
        return {"data": [row("SAP", 201.5)]} if "germany" in url else {"data": []}
    items, info, errors = T.fetch(post, pause=0)
    assert len(asked) == len(T.PLACES) == 15
    assert ("https://scanner.tradingview.com/germany/scan", ["germany"], "XETR") in asked
    assert set(errors) == {"VI"} and "refusé" in errors["VI"]
    assert items == {"SAP.DE": ["2026-11-17", 201.5, 201.5, 202.5, 200.5, "EUR", 7, "2025-12-31"]}
    assert info["DE"] == {"rows": 1, "session": "2026-11-17"} and info["PA"] == {"rows": 0, "session": None}


@case("fichier du soir : celui de la veille effacé, panne totale sans échec de l'étape")
def _():
    with tempfile.TemporaryDirectory() as d:
        old_data, old_out, old_fetch = T.DATA, T.OUT, T.fetch
        try:
            T.DATA, T.OUT = Path(d), Path(d) / "tradingview.json"
            T.OUT.write_text('{"date": "2026-11-16", "items": {"SAP.DE": ["2026-11-16", 1]}}')

            def boom():
                raise ImportError("requests")
            T.fetch = boom
            assert T.main() == 0
            js = json.loads(T.OUT.read_text())
            assert js["items"] == {} and "ImportError" in js["errors"]["*"]
            T.fetch = lambda: ({"SAP.DE": ["2026-11-17", 201.5, None, None, None, "EUR", 7, None]}, {"DE": {"rows": 1}}, {})
            assert T.main() == 0 and json.loads(T.OUT.read_text())["items"]["SAP.DE"][1] == 201.5
        finally:
            T.DATA, T.OUT, T.fetch = old_data, old_out, old_fetch


def tv_file(d, date, items):
    p = Path(d) / "tradingview.json"
    p.write_text(json.dumps({"date": date, "items": items, "errors": {}}))
    return p


@case("cours de secours : seulement la séance attendue, fichier du jour, devise reprise, volume jamais")
def _():
    with tempfile.TemporaryDirectory() as d:
        p = tv_file(d, "2026-11-17", {"SAP.DE": ["2026-11-17", 201.5, 212.1, 212.9, 200.9, "EUR", 7, None],
                                      "OLD.DE": ["2026-11-13", 9.0, None, None, None, "EUR", None, None],
                                      "BAD.DE": ["2026-11-17", None, None, None, None, "EUR", None, None], "X.DE": "?"})
        q, st = B.tradingview_quotes("2026-11-17", "2026-11-17", p)
        assert set(q) == {"SAP.DE"} and st == {"rows": 4, "session": 1}
        assert q["SAP.DE"] == B.quote("2026-11-17", 201.5, 212.1, 212.9, 200.9, None, "EUR", "TradingView")
        q, st = B.tradingview_quotes("2026-11-17", "2026-11-18", p)  # fichier d'un autre jour : rien
        assert q == {} and "pas d'aujourd'hui" in st["note"]
        q, st = B.tradingview_quotes("2026-11-17", "2026-11-17", Path(d) / "absent.json")
        assert q == {} and st["session"] == 0


def shard(items, dd):
    return {"dDates": list(dd), "wDates": [dd[-1]], "items": items}


@case("cours de secours : case vide complétée, garde-fous (devise, ÷2 ×2), source prioritaire gardée")
def _():
    dd = ["2026-11-13", "2026-11-16", "2026-11-17"]
    items = {"SAP.DE": {"currency": "EUR", "d": [200.0, 205.0, None], "w": [205.0]},
             "LOW.DE": {"currency": "EUR", "d": [10.0, 10.0, None], "w": [10.0]},  # TradingView à 30 : hors fourchette
             "GBP.L": {"currency": "GBp", "d": [1300.0, 1310.0, None], "w": [1310.0]},
             "USD.L": {"currency": "USD", "d": [5.0, 5.0, None], "w": [5.0]},  # devise différente : écartée
             "PA.PA": {"currency": "EUR", "d": [50.0, 51.0, None], "w": [51.0]}}
    with tempfile.TemporaryDirectory() as d:
        p = tv_file(d, "2026-11-17", {"SAP.DE": ["2026-11-17", 201.5, None, None, None, "EUR", 7, None],
                                      "LOW.DE": ["2026-11-17", 30.0, None, None, None, "EUR", None, None],
                                      "GBP.L": ["2026-11-17", 1319.8, None, None, None, "GBp", None, None],
                                      "USD.L": ["2026-11-17", 5.1, None, None, None, "GBp", None, None],
                                      "PA.PA": ["2026-11-17", 99.0, None, None, None, "EUR", None, None]})
        tq, _ = B.tradingview_quotes("2026-11-17", "2026-11-17", p)
    official = {"PA.PA": B.quote("2026-11-17", 51.5, src="Euronext")}
    enx = {**tq, **official}  # même ordre que main() : la liste de la bourse passe devant TradingView
    sh = shard(items, dd)
    st = B.patch_catalogue([sh], enx, lambda s: None, "2026-11-17", "2026-11-17")
    d_ = {k: v["d"][-1] for k, v in sh["items"].items()}
    assert d_ == {"SAP.DE": 201.5, "LOW.DE": None, "GBP.L": 1319.8, "USD.L": None, "PA.PA": 51.5}, d_
    assert st["filled"] == 3 and st["rejected"] == 2 and st["mode"] == "fill"


@case("contrôle des F-scores : écarts comptés, sociétés suivies à vérifier, sans données")
def _():
    rank = {"rows": [{"key": "A", "sym": "A.PA", "name": "Alpha", "f9": 8}, {"key": "SE1", "sym": "B.ST", "name": "Beta", "f9": 7},
                     {"key": "C", "sym": "C.DE", "name": "Gamma", "f9": 4}, {"key": "D", "sym": "D.MI", "name": "Delta", "f9": 6},
                     {"key": "E", "sym": "E.MC", "name": "Eps", "f9": None}, {"key": "F", "sym": "F.L", "name": "Phi", "f9": 9}],
            "selection": {"items": [{"key": "A"}, {"key": "SE1"}]}, "pick10": ["A", "C"], "value10": ["D"]}
    tv = {"A.PA": ["2026-11-17", 1, None, None, None, "EUR", 4, "2025-12-31"],  # sélection, −4 : à vérifier
          "B.ST": ["2026-11-17", 1, None, None, None, "SEK", 6, None],  # −1 : normal
          "C.DE": ["2026-11-17", 1, None, None, None, "EUR", 8, None],  # 10 🎯, +4 : à vérifier
          "D.MI": ["2026-11-17", 1, None, None, None, "EUR", 6, None],  # identique
          "E.MC": ["2026-11-17", 1, None, None, None, "EUR", 5, None],  # pas de F-score Euro Signal : ignoré
          "F.L": ["2026-11-17", 1, None, None, None, "GBp", 3, None]}  # −6 mais hors des listes suivies : compté seulement
    r = C.compare(rank, tv)
    assert (r["compared"], r["same"], r["within1"], r["gaps"], r["watched"]) == (5, 1, 2, 3, 4), r
    assert [(c["sym"], c["list"], c["f9"], c["tv"]) for c in r["check"]] == [("A.PA", "sélection", 8, 4), ("C.DE", "10 🎯", 4, 8)]
    assert r["check"][0]["fy"] == "2025-12-31" and r["meanDiff"] == round((-4 - 1 + 4 + 0 - 6) / 5, 2)
    assert C.compare({}, tv)["compared"] == 0 and C.compare(rank, {})["meanDiff"] is None


if __name__ == "__main__":
    for r in results:
        print(*r)
    bad = [r for r in results if r[0] != "OK  "]
    print(f"\n{len(results) - len(bad)}/{len(results)} tests réussis")
    sys.exit(1 if bad else 0)
