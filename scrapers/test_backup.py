"""
Tests hors ligne de la source de cours de secours (aucun accès réseau) : lecture de la liste Euronext et des réponses
Nasdaq Nordic, complément des fiches sociétés (case vide, nouvelle séance, nouvelle semaine), garde-fous (devise, écart
÷2 ou ×2, cours Yahoo jamais remplacé, dates communes), cours Euro Signal, limites de Nasdaq Nordic.

  python scrapers/test_backup.py
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup_prices as B  # noqa: E402

results = []


def case(name):
    def deco(fn):
        try:
            fn()
            results.append(("OK  ", name, ""))
        except Exception as e:  # noqa: BLE001
            results.append(("ÉCHEC", name, repr(e)))
        return fn
    return deco


HEAD = "Name;ISIN;Symbol;Market;Currency;Open Price;High Price;low Price;last Price;last Trade MIC Time;Time Zone;Volume;Turnover;closing Price;closing Price DateTime"
CSV = "﻿" + "\n".join([
    '"European Equities"',
    '"Exported on 19/10/2026"',
    HEAD,
    "TOTALENERGIES;FR0000120271;TTE;Euronext Paris;EUR;80.10;81.00;79.90;80.53;19/10/2026 17:35;CET;1000000;80530000;80.53;19/10/2026",
    "2020 BULKERS;BMG9156K1018;2020;Oslo Børs;NOK;7.20;8.685;7.20;8.675;19/10/2026 16:19;CET;1170971;9100229.04;8.675;19/10/2026",
    "PETITE;FR0000000001;ALPET;Euronext Growth Paris;EUR;0.85;0.86;0.84;0.85;19/10/2026 17:35;CET;5000;4250;0.85;19/10/2026",
    "DOUBLE;BE0000000002;DUAL;Euronext Brussels, Paris;EUR;10;10.6;9.9;10.5;19/10/2026 17:35;CET;800;8400;10.5;19/10/2026",
    "SANS COURS;FR0000000003;NONE;Euronext Paris;EUR;-;-;-;-;-;CET;-;-;-;-",
    "ANCIENNE;FR0000000004;OLD;Euronext Paris;EUR;2;2;2;2;15/10/2026 10:00;CET;10;20;2.00;15/10/2026",
    "GROS;NL0010273215;ASML;Euronext Amsterdam;EUR;1,480.00;1,500.00;1,470.00;1,496.00;19/10/2026 17:35;CET;500000;748000000;1,496.00;19/10/2026",
])


@case("Liste Euronext : en-tête trouvé, places, séance, nombres, lignes sans clôture ignorées")
def _():
    q = B.parse_euronext(CSV)
    assert q["TTE.PA"]["close"] == 80.53 and q["TTE.PA"]["date"] == "2026-10-19" and q["TTE.PA"]["currency"] == "EUR"
    assert q["TTE.PA"]["open"] == 80.10 and q["TTE.PA"]["volume"] == 1000000
    assert q["2020.OL"]["close"] == 8.675 and q["2020.OL"]["currency"] == "NOK"
    assert q["ALPET.PA"]["close"] == 0.85
    assert q["DUAL.BR"]["close"] == 10.5 and q["DUAL.PA"]["close"] == 10.5  # cotée sur deux places
    assert "NONE.PA" not in q
    assert q["OLD.PA"]["date"] == "2026-10-15"
    assert q["ASML.AS"]["close"] == 1496.0
    assert B.parse_euronext("pas un fichier Euronext") == {}


@case("Dates et nombres : formats Euronext et Nasdaq, valeurs vides ou absurdes")
def _():
    assert B.iso_date("19/10/2026 17:35") == "2026-10-19" and B.iso_date("2026-10-19") == "2026-10-19"
    assert B.iso_date("31/02/2026") is None and B.iso_date("") is None and B.iso_date(None) is None
    assert B.num("24,390.00") == 24390.0 and B.num("8.675") == 8.675 and B.num(12) == 12.0
    assert B.num("-") is None and B.num("0") is None and B.num(None) is None and B.num(True) is None and B.num("abc") is None
    assert B.nordic_symbol("INVE-B.ST") == "INVE B" and B.nordic_symbol("NDA-FI.HE") == "NDA FI" and B.nordic_symbol("NOKIA.HE") == "NOKIA"
    assert B.sig(80.534567) == 80.535


SEARCH = {"data": [{"instruments": [
    {"symbol": "INVE A", "orderbookId": "TX999", "currency": "EUR", "fullName": "Investor A (autre place)"},
    {"symbol": "INVE A", "orderbookId": "TX75", "currency": "SEK", "fullName": "Investor A"},
    {"symbol": "INVE B", "orderbookId": "TX76", "fullName": "Investor B"},
]}, {"instruments": None}]}
CHART = {"data": {"charts": {"rows": [
    {"dateTime": "2026-10-19", "open": "411.70", "high": "414.50", "low": "407.00", "close": "412.60", "totalVolume": "1,234,567"},
    {"dateTime": "2026-10-16", "open": "410.00", "high": "415.00", "low": "409.00", "close": "413.80", "totalVolume": "999"},
    {"dateTime": "pas une date", "close": "1"},
    {"dateTime": "2026-10-15", "close": "-"},
]}}}


@case("Nasdaq Nordic : bon titre (symbole exact, devise attendue), historique trié, réponses abîmées sans erreur")
def _():
    assert B.parse_nordic_search(SEARCH, "INVE A", "SEK") == "TX75"
    assert B.parse_nordic_search(SEARCH, "INVE B", "SEK") == "TX76"  # devise non indiquée : acceptée
    assert B.parse_nordic_search(SEARCH, "ATCO A", "SEK") is None
    for bad in (None, [], {"data": None}, {"data": [None, 3]}, {"data": [{"instruments": [None, "x"]}]}):
        assert B.parse_nordic_search(bad, "INVE A") is None
    rows = B.parse_nordic_chart(CHART)
    assert [q["date"] for q in rows] == ["2026-10-16", "2026-10-19"]
    assert rows[1]["close"] == 412.6 and rows[1]["volume"] == 1234567
    for bad in (None, {}, {"data": None}, {"data": {"charts": None}}, {"data": {"charts": {"rows": "x"}}}):
        assert B.parse_nordic_chart(bad) == []


@case("Séance du soir : date la plus fréquente, au moins 30 titres, jamais dans le futur")
def _():
    qs = [B.quote("2026-10-19", 1)] * 40 + [B.quote("2026-10-15", 1)] * 5 + [B.quote("2026-10-21", 1)] * 50
    assert B.session_of(qs, "2026-10-20") == "2026-10-19"
    assert B.session_of(qs[:20], "2026-10-20") is None
    assert B.session_of([], "2026-10-20") is None


DD = ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"]
WD = ["2026-09-25", "2026-10-02", "2026-10-09", "2026-10-16", "2026-10-19"]


def shard(items, dd=DD, wd=WD):
    return {"format": "euro-signal-sector-companies", "dDates": list(dd), "wDates": list(wd), "items": copy.deepcopy(items)}


def enx_of(**kw):
    return {k.replace("_", "."): B.quote(d, c, currency=cur, src="Euronext") for k, (d, c, cur) in kw.items()}


def no_nordic(sym):
    return None


@case("Fiches, séance déjà dans les dates : seules les cases vides sont complétées, garde-fous appliqués")
def _():
    items = {
        "TTE.PA": {"currency": "EUR", "d": [80, 80.2, 80.4, 80.7, None], "w": [79, 79.5, 80, 80.7, None]},
        "MC.PA": {"currency": "EUR", "d": [395, 396, 397, 397, 390.0], "w": [400, 399, 398, 397, 390.0]},
        "BAD.PA": {"currency": "EUR", "d": [10, 10, 10, 10, None]},
        "USD.OL": {"currency": "NOK", "d": [5, 5, 5, 5, None]},
        "SAP.DE": {"currency": "EUR", "d": [200, 201, 202, 203, None], "w": [199, 200, 201, 203, None]},
    }
    shs = [shard(items)]
    enx = enx_of(TTE_PA=("2026-10-19", 80.53, "EUR"), MC_PA=("2026-10-19", 391.0, "EUR"), BAD_PA=("2026-10-19", 31.0, "EUR"),
                 USD_OL=("2026-10-19", 5.1, "USD"))
    st = B.patch_catalogue(shs, enx, no_nordic, "2026-10-19", "2026-10-19")
    it = shs[0]["items"]
    assert st["mode"] == "fill" and st["needed"] == 4 and st["filled"] == 1 and st["rejected"] == 2, st
    assert it["TTE.PA"]["d"][-1] == 80.53 and it["TTE.PA"]["w"][-1] == 80.53
    assert it["MC.PA"]["d"][-1] == 390.0 and it["MC.PA"]["w"][-1] == 390.0  # cours Yahoo jamais remplacé
    assert it["BAD.PA"]["d"][-1] is None and it["USD.OL"]["d"][-1] is None
    assert it["SAP.DE"]["d"][-1] is None  # Allemagne : pas de source de secours
    assert shs[0]["dDates"] == DD and shs[0]["wDates"] == WD


@case("Fiches, nouvelle séance la même semaine : dates décalées partout, semaine en cours mise à jour")
def _():
    items = {
        "TTE.PA": {"currency": "EUR", "d": [80, 80.2, 80.4, 80.7, 80.5], "w": [79, 79.5, 80, 80.7, 80.5]},
        "SAP.DE": {"currency": "EUR", "d": [200, 201, 202, 203, 204], "w": [199, 200, 201, 203, 204]},
    }
    shs = [shard(items), shard({"ASML.AS": {"currency": "EUR", "d": [1400, 1410, 1420, 1430, 1440], "w": [1, 2, 3, 4, 1440]}})]
    enx = enx_of(TTE_PA=("2026-10-20", 81.0, "EUR"), ASML_AS=("2026-10-20", 1496.0, "EUR"))
    st = B.patch_catalogue(shs, enx, no_nordic, "2026-10-20", "2026-10-20")
    assert st["mode"] == "append" and st["filled"] == 2, st
    for sh in shs:
        assert sh["dDates"] == DD[1:] + ["2026-10-20"] and sh["wDates"] == WD[:-1] + ["2026-10-20"]
    a, b = shs[0]["items"], shs[1]["items"]
    assert a["TTE.PA"]["d"] == [80.2, 80.4, 80.7, 80.5, 81.0] and a["TTE.PA"]["w"][-1] == 81.0
    assert a["SAP.DE"]["d"] == [201, 202, 203, 204, None] and a["SAP.DE"]["w"][-1] == 204  # non couvert : rien d'inventé
    assert b["ASML.AS"]["d"][-1] == 1496.0 and len(b["ASML.AS"]["d"]) == 5


@case("Fiches, nouvelle semaine : cours et volumes hebdomadaires décalés pour toutes les fiches (dates alignées)")
def _():
    dd = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]
    wd = ["2026-09-18", "2026-09-25", "2026-10-02", "2026-10-09", "2026-10-16"]
    items = {
        "TTE.PA": {"currency": "EUR", "d": [80, 80.2, 80.4, 80.7, 80.5], "w": [79, 79.5, 80, 80.7, 80.5], "wv": [1, 2, 3]},
        "SAP.DE": {"currency": "EUR", "d": [200, 201, 202, 203, 204], "w": [199, 200, 201, 203, 204], "wv": [4, 5, 6]},
        "HEBDO.PA": {"currency": "EUR", "w": [5, 5, 5, 5, 5]},  # sans cours journaliers : décalé aussi
    }
    shs = [shard(items, dd, wd)]
    st = B.patch_catalogue(shs, enx_of(TTE_PA=("2026-10-19", 81.0, "EUR")), no_nordic, "2026-10-19", "2026-10-19")
    it = shs[0]["items"]
    assert st["mode"] == "append" and st["filled"] == 1
    assert shs[0]["wDates"] == wd[1:] + ["2026-10-19"] and shs[0]["dDates"] == dd[1:] + ["2026-10-19"]
    assert it["TTE.PA"]["w"] == [79.5, 80, 80.7, 80.5, 81.0] and it["TTE.PA"]["wv"] == [2, 3, None]
    assert it["SAP.DE"]["w"] == [200, 201, 203, 204, None] and it["SAP.DE"]["wv"] == [5, 6, None]
    assert it["HEBDO.PA"]["w"] == [5, 5, 5, 5, None]


@case("Fiches : dates différentes d'un fichier à l'autre → aucune séance ajoutée ; séance absente des dates → rien")
def _():
    shs = [shard({"TTE.PA": {"currency": "EUR", "d": [1, 1, 1, 1, 1]}}),
           shard({"ASML.AS": {"currency": "EUR", "d": [1, 1, 1, 1, 1]}}, dd=DD[:-1] + ["2026-10-18"])]
    before = copy.deepcopy(shs)
    st = B.patch_catalogue(shs, enx_of(TTE_PA=("2026-10-20", 1.01, "EUR")), no_nordic, "2026-10-20", "2026-10-20")
    assert st["mode"] is None and shs == before
    st = B.patch_catalogue(shs, enx_of(TTE_PA=("2026-10-01", 1.01, "EUR")), no_nordic, "2026-10-20", "2026-10-01")
    assert st["mode"] is None and shs == before
    assert B.patch_catalogue(shs, {}, no_nordic, "2026-10-20", None)["mode"] is None


@case("Fiches nordiques : plusieurs séances rattrapées, les plus échangées d'abord, arrêt si la bourse était fermée")
def _():
    items = {f"N{k}.ST": {"currency": "SEK", "turnoverEur": 1e6 * (10 - k), "d": [100, 100, 100, None, None]} for k in range(6)}
    asked = []

    def nordic(sym):
        asked.append(sym)
        return [B.quote("2026-10-16", 101, currency="SEK"), B.quote("2026-10-19", 102, currency="SEK")]
    shs = [shard(items)]
    st = B.patch_catalogue(shs, {}, nordic, "2026-10-19", "2026-10-19")
    assert asked == [f"N{k}.ST" for k in range(6)] and st["filled"] == 6
    assert shs[0]["items"]["N0.ST"]["d"] == [100, 100, 100, 101, 102]
    asked.clear()

    def closed(sym):  # séance T absente chez Nasdaq (jour férié en Suède) : arrêt après trois titres
        asked.append(sym)
        return [B.quote("2026-10-16", 101, currency="SEK")]
    shs = [shard(items)]
    st = B.patch_catalogue(shs, {}, closed, "2026-10-19", "2026-10-19")
    assert len(asked) == 3 and st["filled"] == 0


def fake_get(responses, calls):
    class R:
        def __init__(self, js):
            self.js = js

        def json(self):
            if isinstance(self.js, Exception):
                raise self.js
            return self.js

    def get(url, params=None, accept=None, tries=1, timeout=20):
        calls.append(url)
        js = responses(url, params)
        if js is None:
            raise RuntimeError("HTTP 503")
        return R(js)
    return get


def listing(*rows):
    return {"data": {"instrumentListing": {"headers": {}, "rows": [
        {"symbol": sym, "orderbookId": oid, "currency": cur, "lastSalePrice": last, "netChange": chg, "volume": vol, "turnover": turn}
        for sym, oid, cur, last, chg, vol, turn in rows]}}}


LIST_STO = listing(("INVE A", "TX75", "SEK", "412.60", "-1.20", "1,197,856", "500,000,000"),
                   ("ABB", "TX291", "SEK", "897.40", "-12.60", "1,957,063", "900,000,000"),
                   ("CALME", "TX1", "SEK", "10.00", "", "", ""), ("", "TX2", "SEK", "5", "0", "1", "1"), ("SANS", "TX3", "SEK", "-", "", "1", "1"))
CHART_ABB = {"data": {"charts": {"rows": [{"dateTime": "2026-10-16", "close": "910.00"}, {"dateTime": "2026-10-19", "close": "897.40"}]}}}


@case("Listes Nasdaq Nordic : symboles Yahoo, titres sans échange du jour, réponses abîmées sans erreur")
def _():
    rows = B.parse_nordic_list(LIST_STO, "ST")
    assert set(rows) == {"INVE-A.ST", "ABB.ST", "CALME.ST"}
    assert rows["INVE-A.ST"] == {"close": 412.6, "change": -1.2, "volume": 1197856.0, "turnover": 5e8, "currency": "SEK", "oid": "TX75"}
    assert rows["CALME.ST"]["volume"] is None and rows["CALME.ST"]["change"] is None
    assert B.snum("+0.004") == 0.004 and B.snum("-1,234.50") == -1234.5 and B.snum("") is None and B.snum(None) is None
    for bad in (None, {}, {"data": None}, {"data": {"instrumentListing": None}}, {"data": {"instrumentListing": {"rows": [None, 1]}}}):
        assert B.parse_nordic_list(bad, "ST") == {}


@case("Listes Nasdaq Nordic : retenues seulement si deux titres très échangés confirment la séance (pas en séance)")
def _():
    def resp(live):
        def r(url, params):
            if url.endswith("/screener/shares"):
                return LIST_STO if params["market"] == "STO" and params["category"] == "MAIN_MARKET" else {"data": {"instrumentListing": {"rows": []}}}
            if "/TX291/" in url:
                return CHART_ABB
            if "/TX75/" in url:
                return {"data": {"charts": {"rows": [{"dateTime": "2026-10-19", "close": "412.60" if not live else "420.95"}]}}}
            return None
        return r
    calls, ids = [], {}
    n = B.Nordic(ids, "2026-10-19", get=fake_get(resp(False), calls))
    out, info = n.lists("2026-10-19")
    assert info["STO"] == {"rows": 3, "used": True} and info["HEL"] == {"rows": 0, "used": False}, info
    assert set(out) == {"INVE-A.ST", "ABB.ST"} and out["INVE-A.ST"]["date"] == "2026-10-19" and out["ABB.ST"]["close"] == 897.4
    assert ids["CALME.ST"] == ["TX1", "2026-10-19"] and n.asked == 0  # numéros gardés, aucun titre demandé un par un
    out, info = B.Nordic({}, "2026-10-19", get=fake_get(resp(True), [])).lists("2026-10-19")
    assert out == {} and info["STO"]["used"] is False  # cours en séance (différent de la clôture) : liste écartée

    def evening(url, params):  # le soir, historique encore arrêté à la veille : la clôture précédente de la liste le confirme
        if url.endswith("/screener/shares"):
            return LIST_STO if params["market"] == "STO" and params["category"] == "MAIN_MARKET" else {}
        if "/TX291/" in url:
            return {"data": {"charts": {"rows": [{"dateTime": "2026-10-16", "close": "910.00"}]}}}
        return {"data": {"charts": {"rows": [{"dateTime": "2026-10-16", "close": "413.80"}]}}}
    out, info = B.Nordic({}, "2026-10-19", get=fake_get(evening, [])).lists("2026-10-19")
    assert info["STO"]["used"] is True and out["ABB.ST"]["close"] == 897.4
    out, info = B.Nordic({}, "2026-10-20", get=fake_get(evening, [])).lists("2026-10-20")
    assert info["STO"]["used"] is True  # lundi férié en Suède : la clôture précédente de la liste du mardi est celle du vendredi
    out, info = B.Nordic({}, "2026-10-19", get=fake_get(lambda u, p: evening(u, p) if "screener" in u else
                                                         {"data": {"charts": {"rows": [{"dateTime": "2026-10-16", "close": "400"}]}}}, [])).lists("2026-10-19")
    assert info["STO"]["used"] is False  # clôture précédente différente : la liste ne correspond pas à la séance


@case("Nasdaq Nordic : numéro gardé d'un soir à l'autre, titre introuvable non recherché pendant 30 jours, limites")
def _():
    calls, ids = [], {}

    def resp(url, params):
        if url.endswith("/search"):
            return SEARCH if params["searchText"] == "INVE A" else {"data": []}
        return CHART
    n = B.Nordic(ids, "2026-10-19", get=fake_get(resp, calls))
    qs = n.quotes("INVE-A.ST")
    assert [q["date"] for q in qs] == ["2026-10-16", "2026-10-19"] and qs[0]["currency"] == "SEK"
    assert ids["INVE-A.ST"] == ["TX75", "2026-10-19"] and len(calls) == 2
    assert n.quotes("INVE-A.ST") is qs and len(calls) == 2  # même soir : pas de nouvelle requête
    assert n.quotes("XXX.ST") == [] and ids["XXX.ST"] == ["", "2026-10-19"]
    assert n.quotes("TTE.PA") is None  # place non nordique
    calls.clear()
    n2 = B.Nordic(ids, "2026-10-25", get=fake_get(resp, calls))
    assert n2.quotes("XXX.ST") == [] and calls == []  # introuvable il y a 6 jours : pas de recherche
    n2.quotes("INVE-A.ST")
    assert len(calls) == 1 and calls[0].endswith("/chart/download")  # numéro connu : historique seulement
    n3 = B.Nordic({}, "2026-10-19", max_n=2, get=fake_get(resp, []))
    assert n3.quotes("INVE-A.ST") and n3.quotes("XXX.ST") == [] and n3.quotes("ATCO-A.ST") is None and n3.asked == 2
    dead = B.Nordic({}, "2026-10-19", get=fake_get(lambda u, p: None, []))
    for k in range(8):
        dead.quotes(f"T{k}.ST")
    assert dead.asked == 5 and dead.errors == 5  # source muette : arrêt après 5 erreurs de suite


@case("Cours Euro Signal : séances manquantes ajoutées à la suite, semaine mise à jour, garde-fous")
def _():
    prices = {"items": {
        "FR0000120271": {"ticker": "TTE.PA", "currency": "EUR", "rows": [["2026-10-15", 80, 81, 79, 80.4, 10], ["2026-10-16", 80, 81, 79, 80.7, 10]],
                         "weekly": [["2026-10-09", 80], ["2026-10-16", 80.7]]},
        "FR0000121014": {"ticker": "MC.PA", "currency": "EUR", "rows": [["2026-10-19", 390, 391, 389, 390.0, 5]]},
        "FR0000000009": {"ticker": "BAD.PA", "currency": "EUR", "rows": [["2026-10-16", 10, 10, 10, 10, 1]]},
        "SE0015811963": {"ticker": "INVE-A.ST", "currency": "SEK", "rows": [["2026-10-15", 1, 1, 1, 410.0, 1]]},
        "DE0007164600": {"ticker": "SAP.DE", "currency": "EUR", "rows": [["2026-10-16", 1, 1, 1, 200.0, 1]]},
    }}
    enx = B.parse_euronext(CSV)
    enx["MC.PA"] = B.quote("2026-10-19", 391.0, currency="EUR")
    enx["BAD.PA"] = B.quote("2026-10-19", 31.0, currency="EUR")

    def nordic(sym):
        return B.parse_nordic_chart(CHART) if sym == "INVE-A.ST" else None
    st = B.patch_prices(prices, enx, nordic, "2026-10-19", "2026-10-19")
    it = prices["items"]
    assert st["needed"] == 4 and st["filled"] == 2 and st["rejected"] == 1, st
    assert it["FR0000120271"]["rows"][-1] == ["2026-10-19", 80.10, 81.00, 79.90, 80.53, 1000000]
    assert it["FR0000120271"]["weekly"][-1] == ["2026-10-19", 80.53] and it["FR0000120271"]["backup"] == "2026-10-19"
    assert it["FR0000121014"]["rows"][-1][4] == 390.0  # déjà à jour : rien
    assert len(it["FR0000000009"]["rows"]) == 1  # ×3 : écarté
    assert [r[0] for r in it["SE0015811963"]["rows"]] == ["2026-10-15", "2026-10-16", "2026-10-19"]
    assert len(it["DE0007164600"]["rows"]) == 1
    assert B.patch_prices(prices, enx, nordic, "2026-10-19", None)["filled"] == 0


@case("Calcul du soir complet (fichiers temporaires) : fiches, cours, numéros Nasdaq et compteurs écrits")
def _():
    d = Path(tempfile.mkdtemp())
    (d / "societes").mkdir()
    (d / "societes" / "0.json").write_text(json.dumps(shard({"TTE.PA": {"currency": "EUR", "d": [80, 80.2, 80.4, 80.7, None]}})))
    (d / "societes" / "1.json").write_text(json.dumps(shard({"INVE-A.ST": {"currency": "SEK", "d": [400, 405, 410, None, None]}})))
    (d / "prices.json").write_text(json.dumps({"items": {"FR0000120271": {"ticker": "TTE.PA", "currency": "EUR",
                                                                            "rows": [["2026-10-16", 80, 81, 79, 80.7, 10]]}}}))
    old = B.DATA, B.euronext_quotes, B.http_get, B.datetime
    calls = []

    class FakeDT(B.datetime):
        @classmethod
        def now(cls, tz=None):
            return B.datetime(2026, 10, 19, 22, 30, tzinfo=tz)
    try:
        B.DATA = d
        B.euronext_quotes = lambda: dict({f"X{k}.PA": B.quote("2026-10-19", 1.0) for k in range(40)}, **B.parse_euronext(CSV))
        B.http_get = fake_get(lambda u, p: SEARCH if u.endswith("/search") else CHART, calls)
        B.datetime = FakeDT
        assert B.main() == 0
    finally:
        B.DATA, B.euronext_quotes, B.http_get, B.datetime = old
    s0 = json.loads((d / "societes" / "0.json").read_text())
    s1 = json.loads((d / "societes" / "1.json").read_text())
    assert s0["items"]["TTE.PA"]["d"][-1] == 80.53
    assert s1["items"]["INVE-A.ST"]["d"] == [400, 405, 410, 413.8, 412.6]
    assert json.loads((d / "prices.json").read_text())["items"]["FR0000120271"]["rows"][-1][0] == "2026-10-19"
    assert json.loads((d / "backup-ids.json").read_text())["INVE-A.ST"][0] == "TX75"
    diag = json.loads((d / "diagnostics" / "backup.json").read_text())
    assert diag["session"] == "2026-10-19" and diag["catalogue"]["filled"] == 2 and diag["prices"]["filled"] == 1, diag


@case("Calcul du soir avec les listes nordiques retenues : clôtures prises dans la liste, aucun titre demandé un par un")
def _():
    d = Path(tempfile.mkdtemp())
    (d / "societes").mkdir()
    (d / "societes" / "0.json").write_text(json.dumps(shard({
        "INVE-A.ST": {"currency": "SEK", "turnoverEur": 5e7, "d": [400, 405, 410, 413.8, None]},
        "CALME.ST": {"currency": "SEK", "turnoverEur": 1e3, "d": [10, 10, 10, 10, None]},
    })))
    calls = []

    def resp(url, params):
        if url.endswith("/screener/shares"):
            return LIST_STO if params["market"] == "STO" and params["category"] == "MAIN_MARKET" else {}
        return CHART_ABB if "/TX291/" in url else CHART
    old = B.DATA, B.euronext_quotes, B.http_get, B.datetime

    class FakeDT(B.datetime):
        @classmethod
        def now(cls, tz=None):
            return B.datetime(2026, 10, 19, 22, 30, tzinfo=tz)
    try:
        B.DATA = d
        B.euronext_quotes = lambda: {f"X{k}.PA": B.quote("2026-10-19", 1.0) for k in range(40)}
        B.http_get = fake_get(resp, calls)
        B.datetime = FakeDT
        assert B.main() == 0
    finally:
        B.DATA, B.euronext_quotes, B.http_get, B.datetime = old
    it = json.loads((d / "societes" / "0.json").read_text())["items"]
    assert it["INVE-A.ST"]["d"][-1] == 412.6 and it["CALME.ST"]["d"][-1] is None
    assert not [u for u in calls if u.endswith("/search")] and len([u for u in calls if "/chart/" in u]) == 2, calls
    diag = json.loads((d / "diagnostics" / "backup.json").read_text())
    assert diag["nordic"]["lists"]["STO"]["used"] is True and diag["nordic"]["asked"] == 0 and diag["catalogue"]["byMarket"] == {"ST": 1}


if __name__ == "__main__":
    for r in results:
        print(*r)
    bad = [r for r in results if r[0] != "OK  "]
    print(f"\n{len(results) - len(bad)}/{len(results)} tests réussis")
    sys.exit(1 if bad else 0)
