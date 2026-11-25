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
    F.quarters_of = lambda t: []  # trimestres : aucun réseau dans les tests (chaque test qui en a besoin les simule)
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
    assert got == {"@OMV.VI": "OMV.VI", "@UK.L": "UK.L"}, got  # hors PEA compris depuis le 18/10/2026


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


@case("Liste du soir incomplète (cours absents) : comptes récents des autres sociétés gardés")
def _():
    isins = setup(100)
    raw = json.loads(F.OUT.read_text())
    recent = (F.datetime.now(F.timezone.utc).date() - F.timedelta(days=10)).isoformat()
    for v in raw["items"].values():
        v["asOf"] = recent
    F.OUT.write_text(json.dumps(raw))
    pr = json.loads((F.DATA / "prices.json").read_text())
    pr["items"] = {i: pr["items"][i] for i in isins[:20]}  # 20 sociétés seulement ce soir (cours de la veille perdus)
    (F.DATA / "prices.json").write_text(json.dumps(pr))
    F.statements = lambda t: {"years": [{"date": "2025-12-31", "equity": 1.0}], "currency": "EUR"}
    F.main()
    it = saved()
    assert len(it) == 100 and all(it[i]["years"] for i in isins), len(it)
    assert not list(F.DATA.glob("*.tmp")), "fichier temporaire laissé"


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


def today():
    return F.datetime.now(F.timezone.utc).date()


def ago(n):
    return (today() - F.timedelta(days=n)).isoformat()


def rewrite(fn):
    raw = json.loads(F.OUT.read_text())
    for k, v in raw["items"].items():
        fn(k, v)
    F.OUT.write_text(json.dumps(raw))


@case("Trimestres relevés avec les comptes ; Yahoo sans trimestres : nouvel essai seulement 3 mois plus tard")
def _():
    isins = setup(2, schema=F.SCHEMA)
    rewrite(lambda k, v: v.update(asOf="2020-01-01", quarters=[] if k == isins[1] else None, qAt=ago(10) if k == isins[1] else None))
    asked = []
    q = [{"date": ago(60), "revenue": 12.0, "netIncome": 1.0}]
    F.quarters_of = lambda t: asked.append(t) or q
    F.statements = lambda t: {"years": [{"date": "2025-12-31", "equity": 1.0, "revenue": 50.0}], "currency": "EUR"}
    F.main()
    it = saved()
    assert asked == ["T0.PA"], asked
    assert it[isins[0]]["quarters"] == q and it[isins[0]]["qAt"] == today().isoformat(), it[isins[0]]
    assert it[isins[1]]["quarters"] == [] and it[isins[1]]["qAt"] == ago(10), it[isins[1]]


@case("Erreur de Yahoo sur les trimestres : comptes annuels mis à jour, trimestres déjà connus gardés")
def _():
    isins = setup(1, schema=F.SCHEMA)
    q = [{"date": "2026-06-30", "revenue": 12.0, "netIncome": 1.0}]
    rewrite(lambda k, v: v.update(asOf="2020-01-01", quarters=q, qAt="2026-07-15"))

    def boom(t):
        raise RuntimeError("429")
    F.quarters_of = boom
    F.statements = lambda t: {"years": [{"date": "2025-12-31", "equity": 2.0}], "currency": "EUR"}
    F.main()
    v = saved()[isins[0]]
    assert v["years"][0]["equity"] == 2.0 and v["quarters"] == q and v["qAt"] == "2026-07-15", v


@case("Nouvelle publication (newAt) : période plus récente et récente ; pas au premier relevé des trimestres ni à l'arrivée d'une vieille période")
def _():
    t = today()
    yrs = [{"date": "2025-12-31", "revenue": 50.0}]
    old = {"ticker": "A", "schema": 4, "years": yrs, "quarters": [{"date": ago(150), "revenue": 9.0}]}
    new = {"ticker": "A", "years": yrs, "quarters": [{"date": ago(150), "revenue": 9.0}, {"date": ago(60), "revenue": 10.0}]}
    assert F.new_period(old, new, t) == ago(60)
    assert F.new_period(dict(old, quarters=[]), new, t) is None, "premier relevé des trimestres pris pour une publication"
    assert F.new_period(dict(old, schema=3), new, t) is None, "relecture du changement de version prise pour une publication"
    assert F.new_period(old, dict(new, quarters=[{"date": ago(140), "revenue": 9.0}]), t) is None, "période close il y a 140 jours"
    assert F.new_period(old, dict(old), t) is None, "rien de nouveau"
    assert F.new_period(dict(old, ticker="B"), new, t) is None, "autre symbole"
    an = {"ticker": "A", "schema": 4, "years": [{"date": ago(500)}], "quarters": []}
    assert F.new_period(an, {"ticker": "A", "years": [{"date": ago(500)}, {"date": ago(80)}], "quarters": []}, t) == ago(80)


@case("Résultats publiés il y a 3 jours : comptes de moins de 30 jours relus, puis chaque semaine jusqu'aux nouveaux comptes")
def _():
    isins = setup(3, schema=F.SCHEMA)
    q0 = [{"date": ago(120), "revenue": 9.0, "netIncome": 1.0}]
    rewrite(lambda k, v: v.update(asOf=ago(10), quarters=q0, qAt=ago(10)))
    ev = {isins[0]: {"earnings": [{"date": ago(3)}, {"date": ago(-80)}]}, isins[1]: {"earnings": [{"date": ago(1)}]}}
    (F.DATA / "events.json").write_text(json.dumps({"items": ev}))
    (F.DATA / "sectors").mkdir()
    (F.DATA / "sectors" / "estimates.json").write_text(json.dumps({"T2.PA": {"past": [ago(4)], "surprises": [[ago(200), 5.0]]}}))
    asked = []
    F.statements = lambda t: asked.append(t) or {"years": [{"date": "2025-12-31", "equity": 1.0}], "currency": "EUR"}
    F.quarters_of = lambda t: q0 + [{"date": ago(40), "revenue": 10.0, "netIncome": 2.0}] if t == "T0.PA" else q0
    F.main()
    it = saved()
    assert sorted(asked) == ["T0.PA", "T2.PA"], asked  # T1 : résultats d'hier, trop tôt
    assert it[isins[0]]["newAt"] == today().isoformat() and it[isins[0]]["newPer"] == ago(40), it[isins[0]]
    assert "newAt" not in it[isins[2]], "Yahoo pas encore à jour : pas de nouvelle publication"
    asked.clear()
    F.main()
    assert asked == [], "relu deux fois le même soir"
    rewrite(lambda k, v: v.update(asOf=ago(8)))
    F.main()
    assert asked == ["T2.PA"], asked  # T0 : nouveaux comptes déjà vus ; T2 : nouvel essai une semaine plus tard
    assert saved()[isins[0]]["newAt"] == today().isoformat(), "date de la nouvelle publication perdue"


@case("Date de résultats illisible : ignorée sans arrêter la collecte")
def _():
    isins = setup(1, schema=F.SCHEMA)
    (F.DATA / "events.json").write_text(json.dumps({"items": {isins[0]: {"earnings": [{"date": "2026-13-45"}, {"date": None}]}}}))
    assert F.results_dates({isins[0]: "T0.PA"}, today()) == {}


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
