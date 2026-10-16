"""
Tests hors ligne de la collecte des comptes annuels : une panne de Yahoo (réponses vides) ne doit jamais effacer les comptes
déjà connus. Aucun accès réseau (Yahoo simulé).

  python scrapers/test_financials.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import financials as F  # noqa: E402

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


def setup(n, schema=2, years=True):
    d = Path(tempfile.mkdtemp())
    F.DATA, F.OUT = d, d / "financials.json"
    isins = ["FR%010d" % k for k in range(n)]
    (d / "prices.json").write_text(json.dumps({"items": {i: {"ticker": "T%d.PA" % k} for k, i in enumerate(isins)}}))
    good = [{"date": "2025-12-31", "equity": 100.0, "netIncome": 10.0, "shares": 5.0, "revenue": 50.0}]
    (d / "financials.json").write_text(json.dumps({"items": {i: {"ticker": "T%d.PA" % k, "asOf": "2026-01-01", "schema": schema,
                                                                 "years": good if years else [], "currency": "EUR"} for k, i in enumerate(isins)}}))
    F.time.sleep = lambda s: None
    return isins


def saved():
    return json.loads(F.OUT.read_text())["items"]


@case("Yahoo répond vide pour tout le monde : comptes conservés, arrêt après quelques essais")
def _():
    isins = setup(200)
    calls = []
    F.statements = lambda t: calls.append(t) or {"years": [], "currency": None}
    F.main()
    it = saved()
    assert all(it[i]["years"] for i in isins), "comptes effacés"
    assert len(calls) <= F.STREAK_STOP + 1, len(calls)


@case("Yahoo lève une erreur : comptes conservés")
def _():
    isins = setup(30)

    def boom(t):
        raise RuntimeError("401 Invalid Crumb")
    F.statements = boom
    F.main()
    assert all(saved()[i]["years"] for i in isins)


@case("Yahoo répond : comptes remplacés par la nouvelle version ; vide isolé : anciens comptes gardés")
def _():
    isins = setup(20)
    new = [{"date": "2025-12-31", "equity": 120.0, "netIncome": 12.0, "shares": 5.0, "intangibles": 30.0}]
    F.statements = lambda t: {"years": [] if t == "T3.PA" else new, "currency": "EUR"}
    F.main()
    it = saved()
    assert it[isins[0]]["schema"] == F.SCHEMA and it[isins[0]]["years"][0]["intangibles"] == 30.0
    assert it[isins[3]]["years"][0]["equity"] == 100.0 and it[isins[3]]["schema"] == 2, it[isins[3]]


@case("Société nouvelle sans comptes chez Yahoo : notée vide, relue une semaine plus tard")
def _():
    isins = setup(5, schema=F.SCHEMA, years=False)
    raw = json.loads(F.OUT.read_text())
    for v in raw["items"].values():
        v["asOf"] = "2020-01-01"
    F.OUT.write_text(json.dumps(raw))
    F.statements = lambda t: {"years": [], "currency": None}
    F.main()
    it = saved()
    assert all(it[i]["years"] == [] and it[i]["asOf"] > "2020-01-01" for i in isins)


@case("Sociétés liquides du catalogue ajoutées (clé @TICKER), sauf celles déjà suivies, hors PEA ou peu liquides")
def _():
    setup(1)
    (F.DATA / "societes").mkdir()
    (F.DATA / "societes" / "0.json").write_text(json.dumps({"items": {"OMV.VI": {"pea": True, "turnoverEur": 5e7}, "T0.PA": {"pea": True, "turnoverEur": 9e7},
                                                                      "TINY.ST": {"pea": True, "turnoverEur": 2e4}, "UK.L": {"pea": False, "turnoverEur": 9e7}}}))
    got = F.catalogue_pairs({"T0.PA"})
    assert got == {"@OMV.VI": "OMV.VI"}, got


@case("Liste des titres réduite (pays plus suivis) : le fichier est quand même mis à jour")
def _():
    isins = setup(100)
    raw = json.loads((F.DATA / "prices.json").read_text())
    raw["items"] = {i: raw["items"][i] for i in isins[:50]}  # la moitié des sociétés quitte la liste
    (F.DATA / "prices.json").write_text(json.dumps(raw))
    new = [{"date": "2025-12-31", "equity": 120.0, "netIncome": 12.0, "shares": 5.0}]
    F.statements = lambda t: {"years": new, "currency": "EUR"}
    F.main()
    it = saved()
    assert len(it) == 50 and all(it[i]["schema"] == F.SCHEMA for i in isins[:50]), len(it)


@case("Yahoo bloqué : les nouvelles sociétés ne sont pas notées « sans comptes » (relues le soir suivant)")
def _():
    setup(2)
    (F.DATA / "societes").mkdir()
    (F.DATA / "societes" / "0.json").write_text(json.dumps({"items": {"N%d.ST" % k: {"pea": True, "turnoverEur": 5e6} for k in range(80)}}))
    F.statements = lambda t: {"years": [], "currency": None}
    F.main()
    it = saved()
    assert not any(k.startswith("@") for k in it), [k for k in it if k.startswith("@")][:5]
    assert all(it[i]["years"] for i in it), "anciens comptes conservés"


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
