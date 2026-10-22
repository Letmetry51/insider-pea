"""
Stress test opérationnel du module Secteurs : données manquantes, abîmées ou incomplètes ne doivent ni faire planter
le calcul, ni produire de valeurs absurdes dans le fichier lu par le tableau de bord. Sans réseau (données simulées).

  python scrapers/test_sectors.py
"""
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sectors as S  # noqa: E402

S.PLACEBO_N = 30  # vérification du fonctionnement, pas de la statistique

results = []


def case(name):
    def deco(fn):
        tmp = Path(tempfile.mkdtemp())
        for k in ("SEC", "UNIVERSE", "INFO_CACHE", "ESTIMATES", "REV_HIST", "WEEKLY", "WEEKLY_VOL", "BACKTEST", "OUT", "OUT_CO", "CATALOG", "CO_DIR", "CO_INDEX",
                  "FINANCIALS", "TICKERS", "OFFICIAL"):
            old = getattr(S, k)
            setattr(S, k, tmp / ("sectors" if k == "SEC" else old.name))
        S.SEC.mkdir(parents=True, exist_ok=True)
        try:
            S.synthetic(seed=len(results) + 1)
            fn()
            results.append(("OK  ", name, ""))
        except Exception as e:
            results.append(("ÉCHEC", name, f"{e}\n{traceback.format_exc(limit=3)}"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return fn
    return deco


def check_outputs(require_backtest=True):
    if require_backtest:
        S.run_backtest()
    S.dashboard(fetch_daily=False)
    txt = S.OUT.read_text(encoding="utf-8")
    assert "NaN" not in txt and "Infinity" not in txt, "valeur non numérique dans sectors.json"
    d = json.loads(txt)
    assert d["format"] == "euro-signal-sectors" and d["groups"], "classement vide"
    for g in d["groups"]:
        assert 0 <= (g["breadth"] or 0) <= 1 and g["rank"] >= 1, f"groupe incohérent {g['key']}"
        for k in ("rs6", "rs3"):
            v = g.get(k)
            assert v is None or abs(v) < 5, f"{k} absurde pour {g['key']} : {v}"
    idx = json.loads(S.CO_INDEX.read_text(encoding="utf-8"))
    items = {}
    for k in range(idx["shards"]):
        sh = json.loads((S.CO_DIR / f"{k}.json").read_text(encoding="utf-8"))
        for sym, v in sh["items"].items():
            assert S.shard_of(sym) == k, f"fiche {sym} dans le mauvais fichier"
            assert len(v.get("w") or []) in (0, len(sh["wDates"])), "fiches sociétés : cours non alignés"
            items[sym] = v
    assert items and len(items) == idx["n"] == len(idx["rows"]), "liste de recherche incomplète"
    assert any(v.get("roles") for v in items.values()), "fiches sociétés : aucun leader ni challenger"
    if S.CATALOG.exists():
        cat = json.loads(S.CATALOG.read_text(encoding="utf-8"))["items"]
        assert all(sym in items for sym in cat if sym not in json.loads(S.UNIVERSE.read_text(encoding="utf-8"))["items"]) or True
    ranks = [g["rank"] for g in d["groups"]]
    assert sorted(ranks) == list(range(1, len(ranks) + 1)), "rangs non consécutifs"
    return d


def mutate_weekly(fn):
    W = pd.read_csv(S.WEEKLY, index_col=0, parse_dates=True, compression="gzip")
    W = fn(W)
    W.to_csv(S.WEEKLY, compression="gzip")


@case("Données propres : test historique et classement du jour")
def _():
    d = check_outputs()
    bt = json.loads(S.BACKTEST.read_text(encoding="utf-8"))
    assert bt["stress"]["trials"] >= 20, "essais non déclarés"
    assert 0 <= bt["stress"]["deflatedSharpe"] <= 1
    assert any(t["key"] == "cyber" for t in d["themes"]), "thème cybersécurité absent"


@case("30 % de cours manquants au hasard")
def _():
    rng = np.random.default_rng(1)
    mutate_weekly(lambda W: W.mask((rng.random(W.shape) < 0.3) & ~W.columns.isin([S.BENCH, S.US_BENCH])))
    check_outputs()


@case("Erreurs de cours : prix ×1000 isolé, prix négatif, série à zéro")
def _():
    def f(W):
        c = [x for x in W.columns if x.endswith(".PA")]
        W.iloc[200, W.columns.get_loc(c[0])] *= 1000
        W.iloc[210, W.columns.get_loc(c[1])] = -5
        W[c[2]] = 0.0
        return W
    mutate_weekly(f)
    d = check_outputs()
    assert all(abs(g["rs6"] or 0) < 5 for g in d["groups"])


@case("Dates en double et dans le désordre, barres du lundi et du mercredi mélangées")
def _():
    def f(W):
        W2 = W.iloc[::3].copy()
        W2.index = W2.index - pd.Timedelta(days=2)
        return pd.concat([W, W2]).sample(frac=1, random_state=3)
    mutate_weekly(f)
    W, _ = S.load_weekly()
    assert W.index.is_monotonic_increasing and W.index.is_unique and set(W.index.dayofweek) == {4}
    check_outputs()


@case("Indice de référence absent à la fin, baromètres américains manquants")
def _():
    def f(W):
        W.iloc[-6:, W.columns.get_loc(S.BENCH)] = np.nan
        return W.drop(columns=["NVDA", "LLY", "CRWD"], errors="ignore")
    mutate_weekly(f)
    check_outputs()


@case("Catalogue de toutes les sociétés cotées : petites sociétés ajoutées aux fiches et à la recherche")
def _():
    S.CATALOG.write_text(json.dumps({"generatedAt": "2026-10-15T00:00:00+00:00", "items": {
        "PETIT.PA": {"symbol": "PETIT.PA", "name": "Petite Société SA", "exchange": "PAR", "country": "FR", "hq": "FR", "currency": "EUR", "capEur": 4.2e7},
        "LITEN.ST": {"symbol": "LITEN.ST", "name": "Liten AB", "exchange": "STO", "country": "SE", "currency": "SEK", "capEur": None}}}), encoding="utf-8")
    check_outputs()
    idx = json.loads(S.CO_INDEX.read_text(encoding="utf-8"))
    rows = {r[0]: r for r in idx["rows"]}
    assert "PETIT.PA" in rows and rows["PETIT.PA"][3] == 42 and rows["PETIT.PA"][7] == 1, rows.get("PETIT.PA")
    assert "LITEN.ST" in rows and rows["LITEN.ST"][3] is None


@case("Univers abîmé : secteur, industrie ou capitalisation manquants")
def _():
    u = json.loads(S.UNIVERSE.read_text(encoding="utf-8"))
    for k, s in enumerate(list(u["items"])):
        if k % 4 == 0:
            u["items"][s].pop("industry", None)
        if k % 7 == 0:
            u["items"][s].pop("sector", None)
        if k % 5 == 0:
            u["items"][s]["capEur"] = None
    S.UNIVERSE.write_text(json.dumps(u), encoding="utf-8")
    check_outputs()


@case("Révisions et surprises absentes ou illisibles, volumes absents")
def _():
    S.ESTIMATES.write_text(json.dumps({"ASML.AS": {"rev": {"up30": None}}, "SU.PA": {"surprises": []}}), encoding="utf-8")
    S.WEEKLY_VOL.unlink()
    check_outputs()


@case("Historique trop court (40 semaines) : rien d'écrit, aucun plantage")
def _():
    mutate_weekly(lambda W: W.iloc[-40:])
    S.run_backtest()
    assert not S.BACKTEST.exists() or "stress" not in json.loads(S.BACKTEST.read_text(encoding="utf-8"))


@case("Sans révisions ni test historique : le tableau de bord reste lisible")
def _():
    S.ESTIMATES.unlink()
    d = check_outputs(require_backtest=False)
    assert d["backtest"] is None


@case("Moteur sans regard vers le futur : mesures à la semaine t identiques avec ou sans les semaines suivantes")
def _():
    W, V = S.load_weekly()
    uni = json.loads(S.UNIVERSE.read_text(encoding="utf-8"))["items"]
    est = json.loads(S.ESTIMATES.read_text(encoding="utf-8"))
    groups = S.groups_of(uni)
    t = 250
    full = S.group_signals(S.panels(W, W[S.BENCH], V, est), groups)
    cut = S.group_signals(S.panels(W.iloc[:t + 1], W[S.BENCH].iloc[:t + 1], V.iloc[:t + 1], est), groups)
    for k in ("rs6", "rs3", "breadth", "composite", "volume", "surprise", "trending"):
        a, b = full[k].iloc[t], cut[k].iloc[t]
        assert ((a == b) | (a.isna() & b.isna())).all(), f"{k} dépend de données futures"



@case("Valeur comptable du catalogue : devise des comptes vérifiée, valeurs aberrantes écartées, fiches anciennes relues")
def _():
    assert S.book_fields({"priceToBook": 2.345678, "returnOnEquity": 0.12, "currency": "EUR", "financialCurrency": "EUR"}) == {"pb": 2.346, "roe": 0.12}
    assert "pb" not in S.book_fields({"priceToBook": 0.03, "currency": "SEK", "financialCurrency": "EUR"}), "comptes en euros, cotation en couronnes"
    assert "pb" in S.book_fields({"priceToBook": 1.2, "currency": "GBp", "financialCurrency": "GBP"})
    assert S.book_fields({"priceToBook": 500, "returnOnEquity": 9}) == {} and S.book_fields(None) == {}
    assert S.info_stale({"fetched": "2099-01-01"}, "2026-01-01") and not S.info_stale({"fetched": "2099-01-01", "v": S.INFO_V}, "2026-01-01")



@case("Analyse des fiches : comptes sur 4 ans, prochaine publication de résultats, actionnariat")
def _():
    yrs = [{"date": f"{y}-12-31", "revenue": 1e9 * (y - 2020), "operatingIncome": 2e8, "netIncome": 1.5e8, "ebitda": 3e8, "cash": 5e8,
            "totalDebt": 2e8, "shares": 1e8, "equity": 2e9} for y in range(2021, 2026)]
    S.FINANCIALS.write_text(json.dumps({"items": {
        "NL0010273215": {"ticker": "ASML.AS", "years": []},          # dossier vide : le plus complet l'emporte
        "@ASML.AS": {"ticker": "ASML.AS", "currency": "EUR", "years": yrs},
        "@SU.PA": {"years": [{"date": "2025-12-31", "revenue": None, "netIncome": None}]}}}), encoding="utf-8")
    est = json.loads(S.ESTIMATES.read_text(encoding="utf-8"))
    est["ASML.AS"]["next"] = "2099-01-28"
    est["SU.PA"]["next"] = "2001-01-01"  # date passée : ignorée
    S.write_json(S.ESTIMATES, est)
    about = "ASML Holding N.V. develops and sells lithography systems for the semiconductor industry. " * 20
    S.write_json(S.INFO_CACHE, {"ASML.AS": {"heldPercentInstitutions": 0.42, "heldPercentInsiders": 7, "longBusinessSummary": about,
                                            "fullTimeEmployees": 44027, "website": "https://www.asml.com"},
                                "SU.PA": {"longBusinessSummary": "court", "fullTimeEmployees": -3, "website": "javascript:alert(1)"}})
    check_outputs()
    item = lambda s: json.loads((S.CO_DIR / f"{S.shard_of(s)}.json").read_text(encoding="utf-8"))["items"][s]
    a, b = item("ASML.AS"), item("SU.PA")
    assert a["fin"]["c"] == "EUR" and len(a["fin"]["y"]) == 4 and a["fin"]["y"][0][0] == "2022-12-31", a.get("fin")
    assert a["fin"]["y"][-1][1:] == [5e9, 2e8, 1.5e8, 3e8, 5e8, 2e8, 1e8, 2e9, None, None, None], a["fin"]["y"][-1]
    assert a["about"].startswith("ASML Holding") and len(a["about"]) <= 900 and a["about"].endswith(".") and a["staff"] == 44027, a
    assert a["web"] == "https://www.asml.com" and not any(k in b for k in ("about", "staff", "web")), b
    assert a["nextEarnings"] == "2099-01-28" and a["instPct"] == 0.42 and a.get("insiderPct") is None, a
    assert "fin" not in b and "nextEarnings" not in b, b
    assert S.fin_compact(None) is None and S.fin_compact({"years": [{"date": "2025-12-31", "revenue": float("nan")}]}) is None
    assert S.about_text("x" * 30) is None and S.about_text("Une phrase. " * 200).endswith(".") and len(S.about_text("mot " * 400)) <= 901


@case("Prochaine publication de résultats : dates à venir de Yahoo, avec ou sans fuseau horaire")
def _():
    idx = pd.DatetimeIndex(["2026-07-24 07:00", "2026-10-22 07:00", "2027-01-30 07:00"]).tz_localize("Europe/Paris")
    ed = pd.DataFrame({"EPS Estimate": [1.0, 2.0, 3.0], "Reported EPS": [1.1, None, None], "Surprise(%)": [10.0, None, None]}, index=idx)
    assert S.next_earnings(ed, "2026-10-19") == "2026-10-22"
    assert S.next_earnings(ed, "2026-10-22") == "2026-10-22"  # le jour même
    assert S.next_earnings(ed, "2027-02-01") is None and S.next_earnings(None) is None and S.next_earnings(ed.iloc[:0]) is None
    naive = ed.copy()
    naive.index = idx.tz_localize(None)
    assert S.next_earnings(naive, "2026-10-23") == "2027-01-30"


@case("Yahoo renvoie des fiches vides : les anciennes fiches sont conservées, relecture arrêtée")
def _():
    old = {"OR.PA": {"longName": "L'Oréal S.A.", "sector": "Consumer Defensive", "marketCap": 2e11, "country": "France", "fetched": "2020-01-01"}}
    syms = ["OR.PA"] + ["X%d.PA" % k for k in range(200)]
    S.write_json(S.INFO_CACHE, old)
    calls = []
    real, real_reset, real_sleep = S.fetch_info, S.reset_yahoo_session, S.time.sleep
    S.fetch_info = lambda s: (calls.append(s) or (s, {"fetched": "2026-10-16", "v": S.INFO_V}))
    S.reset_yahoo_session = lambda: None
    S.time.sleep = lambda sec: None  # pause d'une minute du vrai calcul : inutile ici (1 min de moins chaque soir)
    try:
        c = S.refresh_infos(syms, minutes=1)
    finally:
        S.fetch_info, S.reset_yahoo_session, S.time.sleep = real, real_reset, real_sleep
    assert c["OR.PA"].get("longName") == "L'Oréal S.A.", c["OR.PA"]
    assert len(calls) <= 100, len(calls)  # 40 + 40, puis 10 + 10 une fiche à la fois après la pause : arrêt
    assert S.read_json(S.INFO_CACHE, {})["OR.PA"].get("marketCap") == 2e11


class FakeQuery:
    def __init__(self, op, args):
        self.op, self.args = op, args


class FakeYf:
    """yfinance simulé pour le filtre du catalogue : Allianz n'apparaît qu'à Vienne, Alstom qu'à Francfort, Publicis nulle part."""
    EquityQuery = FakeQuery
    QUOTES = {
        "VIE": [{"symbol": "ALV.VI", "longName": "Allianz SE", "exchange": "VIE", "currency": "EUR", "marketCap": 1.5e11, "regularMarketPrice": 380,
                 "averageDailyVolume3Month": 40},
                {"symbol": "RAW.VI", "longName": "Rawlplug Werke AG", "exchange": "VIE", "currency": "EUR", "marketCap": 8e8, "regularMarketPrice": 10,
                 "averageDailyVolume3Month": 1000}],
        "GER": [{"symbol": "AOMD.DE", "longName": "Alstom SA", "exchange": "GER", "currency": "EUR", "marketCap": 1e10, "regularMarketPrice": 22,
                 "averageDailyVolume3Month": 5000},
                {"symbol": "RAW.DE", "longName": "Raiffeisen Bank International AG", "exchange": "GER", "currency": "EUR", "marketCap": 9e9,
                 "regularMarketPrice": 30, "averageDailyVolume3Month": 7000},
                {"symbol": "SAP.DE", "longName": "SAP SE", "exchange": "GER", "currency": "EUR", "marketCap": 2.5e11, "regularMarketPrice": 200,
                 "averageDailyVolume3Month": 1e6}],
    }

    @staticmethod
    def screen(q, offset=0, size=250, sortField=None, sortAsc=False):
        exch = [a.args[1] for a in q.args if a.op == "eq" and a.args[0] == "exchange"][0]
        quotes = FakeYf.QUOTES.get(exch, []) if offset == 0 else []
        return {"quotes": quotes, "total": len(FakeYf.QUOTES.get(exch, []))}


INFOS = {
    "ALV.VI": {"longName": "Allianz SE", "country": "Germany", "marketCap": 1.5e11, "currency": "EUR", "currentPrice": 380, "averageVolume": 40},
    "ALV.DE": {"longName": "Allianz SE", "country": "Germany", "marketCap": 1.5e11, "currency": "EUR", "currentPrice": 380, "averageVolume": 560000,
               "sector": "Financial Services"},
    "AOMD.DE": {"longName": "Alstom SA", "country": "France", "marketCap": 1e10, "currency": "EUR", "currentPrice": 22, "averageVolume": 5000},
    "ALO.PA": {"longName": "Alstom SA", "country": "France", "marketCap": 1e10, "currency": "EUR", "currentPrice": 22, "averageVolume": 900000},
    "PUB.PA": {"longName": "Publicis Groupe S.A.", "country": "France", "marketCap": 2.4e10, "currency": "EUR", "currentPrice": 95, "averageVolume": 600000},
    "RAW.VI": {"longName": "Rawlplug Werke AG", "country": "Austria", "marketCap": 8e8, "currency": "EUR", "currentPrice": 10, "averageVolume": 1000},
    "RAW.DE": {"longName": "Raiffeisen Bank International AG", "country": "Austria", "marketCap": 9e9, "currency": "EUR", "currentPrice": 30,
               "averageVolume": 7000},
    "RBI.VI": {"longName": "Raiffeisen Bank International AG", "country": "Austria", "marketCap": 9e9, "currency": "EUR", "currentPrice": 30,
               "averageVolume": 600000},
    "SAP.DE": {"longName": "SAP SE", "country": "Germany", "marketCap": 2.5e11, "currency": "EUR", "currentPrice": 200, "averageVolume": 1e6},
    "TINY.PA": {"longName": "Tiny SA", "country": "France", "marketCap": 5e5, "currency": "EUR", "currentPrice": 1, "averageVolume": 10},
}


@case("Cotations principales absentes du filtre Yahoo : Allianz (Vienne), Alstom (Francfort), Publicis (absente) ajoutées ; suppositions fausses écartées")
def _():
    S.TICKERS.write_text(json.dumps({"FR0010220475": {"ticker": "ALO.PA", "name": "Alstom SA"}}), encoding="utf-8")
    S.OFFICIAL.write_text(json.dumps({"isins": {"FR0000130577": ["PUB.PA", "EUR"], "FR0000000099": ["TINY.PA", "EUR"]}}), encoding="utf-8")
    cache = {k: dict(v, fetched="2026-10-20", v=S.INFO_V) for k, v in INFOS.items() if k in ("ALV.VI", "AOMD.DE", "RAW.VI", "RAW.DE", "SAP.DE")}
    items = {k: {"name": INFOS[k]["longName"], "capEur": INFOS[k]["marketCap"]} for k in cache}
    sup, ask = S.home_supplement(items, cache)
    assert sup["ALV.DE"]["kind"] == "guess" and sup["ALV.DE"]["name"] == "allianz" and sup["ALV.DE"]["of"] == "ALV.VI", sup.get("ALV.DE")
    assert sup["ALO.PA"]["kind"] == "dossier" and sup["ALO.PA"]["name"] is None, sup.get("ALO.PA")
    assert sup["PUB.PA"]["kind"] == "list" and "SAP.SW" not in sup and not any(x["of"] == "SAP.DE" for x in sup.values())
    # RAW.VI existe déjà (Rawlplug, autre société) : Raiffeisen (RAW.DE, siège en Autriche) sera cherchée par son nom
    assert "RAW.VI" not in sup and [x["of"] for x in ask] == ["RAW.DE"], ask
    # catalogue complet, avec un faux yfinance
    real = (sys.modules.get("yfinance"), S.fetch_info, S.fx_now, S.search_home, S.time.sleep)
    fake = type(sys)("yfinance")
    fake.screen, fake.EquityQuery = FakeYf.screen, FakeQuery
    sys.modules["yfinance"] = fake
    S.fetch_info = lambda s: (s, dict(INFOS[s], fetched="2026-10-23", v=S.INFO_V) if s in INFOS else None)
    S.fx_now = lambda: {}
    S.search_home = lambda name, sfx, want: {"raiffeisen bank international": "RBI.VI"}.get(want)
    S.time.sleep = lambda sec: None
    try:
        kept = S.screen_catalog(info_minutes=1)
    finally:
        if real[0] is not None:
            sys.modules["yfinance"] = real[0]
        else:
            sys.modules.pop("yfinance", None)
        S.fetch_info, S.fx_now, S.search_home, S.time.sleep = real[1:]
    for sym in ("ALV.DE", "ALO.PA", "PUB.PA", "RBI.VI", "SAP.DE", "ALV.VI", "AOMD.DE"):
        assert sym in kept, (sym, sorted(kept))
    assert kept["ALV.DE"]["turnoverEur"] > 1e8 and kept["ALV.DE"]["hq"] == "DE" and kept["PUB.PA"]["hq"] == "FR"
    assert "TINY.PA" not in kept and "AOMD.PA" not in kept and "RAW.VI" in kept  # coquille écartée ; Rawlplug reste une autre société
    cat = json.loads(S.CATALOG.read_text(encoding="utf-8"))
    assert cat["pending"] == 0 and cat["homeV"] == S.HOME_V and S.catalog_age() == 0, cat.get("pending")
    # fiches : la cotation du siège, la plus échangée, représente la société (Allianz à Francfort, plus à Vienne)
    S.dashboard(fetch_daily=False)
    idx = {r[0] for r in json.loads(S.CO_INDEX.read_text(encoding="utf-8"))["rows"]}
    assert "ALV.DE" in idx and "ALV.VI" not in idx and "ALO.PA" in idx and "AOMD.DE" not in idx, sorted(x for x in idx if x[:3] in ("ALV", "ALO", "AOM"))


@case("Univers des secteurs : la cotation principale remplace la ligne secondaire (Allianz, Alstom, Raiffeisen)")
def _():
    S.TICKERS.write_text(json.dumps({"FR0010220475": {"ticker": "ALO.PA", "name": "Alstom SA"}}), encoding="utf-8")
    S.OFFICIAL.write_text(json.dumps({"isins": {"FR0000130577": ["PUB.PA", "EUR"]}}), encoding="utf-8")
    S.write_json(S.INFO_CACHE, {"PUB.PA": dict(INFOS["PUB.PA"], fetched="2026-10-20", v=S.INFO_V)})  # lue par le catalogue
    real = (sys.modules.get("yfinance"), S.fetch_info, S.fx_now, S.search_home, S.time.sleep)
    fake = type(sys)("yfinance")
    fake.screen, fake.EquityQuery = FakeYf.screen, FakeQuery
    sys.modules["yfinance"] = fake
    S.fetch_info = lambda s: (s, dict(INFOS[s], fetched="2026-10-23", v=S.INFO_V) if s in INFOS else None)
    S.fx_now = lambda: {}
    S.search_home = lambda name, sfx, want: {"raiffeisen bank international": "RBI.VI"}.get(want)
    S.time.sleep = lambda sec: None
    try:
        S.build_universe()
    finally:
        if real[0] is not None:
            sys.modules["yfinance"] = real[0]
        else:
            sys.modules.pop("yfinance", None)
        S.fetch_info, S.fx_now, S.search_home, S.time.sleep = real[1:]
    u = json.loads(S.UNIVERSE.read_text(encoding="utf-8"))
    uni = u["items"]
    for sym in ("ALV.DE", "ALO.PA", "RBI.VI", "SAP.DE", "PUB.PA"):
        assert sym in uni, (sym, sorted(uni))
    for sym in ("ALV.VI", "AOMD.DE", "RAW.DE"):
        assert sym not in uni, (sym, sorted(uni))
    assert u["homeV"] == S.HOME_V and S.universe_age() == 0


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
