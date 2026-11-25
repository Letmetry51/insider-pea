"""
Tests hors ligne de la lecture des comptes par l'IA (scrapers/comptes_ia.py) : quelles sociétés sont lues, texte envoyé, lecture
de la réponse, fichier jamais abîmé par une panne de l'API. Aucun accès réseau (API simulée).

  python scrapers/test_comptes_ia.py
"""
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comptes_ia as C  # noqa: E402

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


def ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


Y = [{"date": "2024-12-31", "revenue": 100e6, "operatingIncome": 10e6, "netIncome": 6e6, "ebitda": 20e6, "totalDebt": 50e6,
      "cash": 10e6, "equity": 80e6, "totalAssets": 200e6, "shares": 10e6, "interestExpense": 2e6, "fcf": 5e6},
     {"date": "2025-12-31", "revenue": 110e6, "operatingIncome": 13.2e6, "netIncome": 8e6, "ebitda": 25e6, "totalDebt": 60e6,
      "cash": 5e6, "equity": 85e6, "totalAssets": 210e6, "shares": 12e6, "interestExpense": 3e6, "fcf": 4e6}]
Q = [{"date": "2025-06-30", "revenue": 26e6, "operatingIncome": 2e6, "netIncome": -1e6},
     {"date": "2025-09-30", "revenue": 27e6, "operatingIncome": 3e6, "netIncome": 1e6},
     {"date": "2025-12-31", "revenue": 30e6, "operatingIncome": 4e6, "netIncome": 2e6},
     {"date": "2026-03-31", "revenue": 28e6, "operatingIncome": 3e6, "netIncome": 1.5e6},
     {"date": "2026-06-30", "revenue": 29e6, "operatingIncome": 3.5e6, "netIncome": 2e6, "cash": 8e6, "totalDebt": 55e6},
     {"date": "2026-09-30", "revenue": 24e6, "operatingIncome": 1e6, "netIncome": -0.5e6, "cash": 4e6, "totalDebt": 70e6}]


def setup(fin, dash=None, old=None):
    d = Path(tempfile.mkdtemp())
    C.DATA, C.OUT = d, d / "comptes_ia.json"
    (d / "financials.json").write_text(json.dumps({"items": fin}))
    (d / "euro-signal.json").write_text(json.dumps(dash or {"rank": {"rows": []}}))
    if old is not None:
        C.OUT.write_text(json.dumps(old))
    return d


def reponse(entries):
    return {"content": [{"type": "text", "text": json.dumps({"lectures": entries}, ensure_ascii=False)}],
            "usage": {"input_tokens": 1000, "output_tokens": 300}}


def entry(k, **kw):
    e = {"id": k, "resume": "Chiffre d'affaires en recul, marge en baisse.", "forts": ["trésorerie positive"], "faibles": ["CA −11 %"],
         "impact": "baisse", "avis": "mitigé", "alerte": ""}
    e.update(kw)
    return e


@case("Dernière période : exercice, trimestre ou semestre")
def _():
    assert C.derniere({"years": Y}) == ("2025-12-31", "exercice")
    assert C.derniere({"years": Y, "quarters": Q}) == ("2026-09-30", "trimestre")
    S = [{"date": "2025-06-30", "revenue": 1.0, "cash": 1.0}, {"date": "2025-12-31", "revenue": 1.0, "cash": 1.0},
         {"date": "2026-06-30", "revenue": 1.0, "cash": 1.0}]
    assert C.derniere({"years": Y, "quarters": S}) == ("2026-06-30", "semestre")
    assert C.derniere({"years": [], "quarters": Q}) is None, "sans exercice annuel : pas de lecture"


@case("Société à lire : sans lecture, consigne changée ou période plus récente ; pas pour une période plus ancienne")
def _():
    f = {"years": Y, "quarters": Q}
    assert C.a_lire(None, f) == ("2026-09-30", "trimestre")
    assert C.a_lire({"per": "2026-09-30", "v": C.VERSION}, f) is None
    assert C.a_lire({"per": "2026-06-30", "v": C.VERSION}, f) == ("2026-09-30", "trimestre")
    assert C.a_lire({"per": "2026-12-31", "v": C.VERSION}, f) is None, "trimestre retiré par Yahoo : lecture gardée"
    assert C.a_lire({"per": "2026-09-30", "v": C.VERSION - 1}, f) == ("2026-09-30", "trimestre")


@case("Ratios calculés : croissance, marges, dette nette / EBITDA, intérêts, dilution, même trimestre un an plus tôt")
def _():
    R = " ".join(C.ratios({"years": Y, "quarters": Q}, "Industrie"))
    for t in ("croissance du CA +10,0 %", "marge d'exploitation 12,0 % (10,0 % l'exercice précédent)", "dette nette 55,0 = 2,2 fois l'EBITDA",
              "intérêts couverts 4,4 fois", "nombre d'actions +20,0 % sur un an", "Dernier trimestre (2026-09-30) face au même trimestre",
              "(2025-09-30)", "CA −11,1 %", "résultat net −0,50 contre 1,0", "trésorerie 4,0 (5,0 à la clôture de l'exercice)",
              "dette financière 70,0 (60,0"):
        assert t in R, (t, R)
    B = " ".join(C.ratios({"years": Y}, "Finance"))
    assert "EBITDA" not in B and "marge d'exploitation" not in B and "croissance du CA +10,0 %" in B, B
    N = " ".join(C.ratios({"years": [dict(Y[1], cash=90e6)]}, "Industrie"))
    assert "trésorerie nette (plus de trésorerie que de dette) 30,0" in N, N


@case("Montants à la française, en millions")
def _():
    assert C.mil(1234.4e6) == "1 234" and C.mil(12.46e6) == "12,5" and C.mil(-0.354e6) == "−0,35" and C.mil(None) is None
    assert C.pc(0.032) == "3,2 %" and C.pc(-0.111, True) == "−11,1 %" and C.pc(0.1, True) == "+10,0 %"


@case("Texte envoyé : identifiant, société, période, exercices, trimestres, ratios, écart à l'attente des résultats qui la présentent")
def _():
    ctx = {"X1": {"nom": "Exemple SA", "symbole": "EX.PA", "pays": "FR", "secteur": "Industrie", "f9": 6}}
    est = {"EX.PA": {"surprises": [["2026-10-25", -12.5], ["2027-01-20", 40.0]]}}
    t = C.bloc("X1", {"years": Y, "quarters": Q, "currency": "EUR", "ticker": "EX.PA"}, ctx, "2026-09-30", "trimestre", {}, est)
    for s in ('Société id "X1" : Exemple SA (symbole EX.PA, pays FR, secteur Industrie)', "comptes en EUR", "F-score de Piotroski calculé par l'outil : 6/9",
              "Dernière période : 2026-09-30 (trimestre)", "Exercices annuels :", "Dernier trimestre : 2026-09-30 : CA 24,0",
              "Même trimestre un an plus tôt : 2025-09-30 : CA 27,0", "Ratios calculés :",
              "Résultats publiés le 2026-10-25 : bénéfice par action 12,5 % en dessous de l'attente des analystes"):
        assert s in t, (s, t)
    assert "2026-06-30 :" not in t, "trimestre précédent envoyé (Haiku comparait au trimestre précédent à l'essai)"
    t2 = C.bloc("X1", {"years": Y, "quarters": [q for q in Q if q["date"] != "2025-09-30"], "currency": "EUR"}, ctx, "2026-09-30", "trimestre", {}, {})
    assert "Même trimestre un an plus tôt : non fourni par Yahoo (ne pas comparer à une autre période)" in t2, t2
    bk = {"B1": {"nom": "Banque SA", "symbole": "BQ.PA", "pays": "FR", "secteur": "Finance"}}
    t3 = C.bloc("B1", {"years": Y, "quarters": Q, "currency": "EUR"}, bk, "2026-09-30", "trimestre", {}, {})
    assert "dette financière" not in t3 and "trésorerie" not in t3 and "EBITDA" not in t3 and "résultat net 8,0" in t3, t3
    ev = {"X1": {"earnings": [{"date": "2026-10-24", "epsActual": 1.1, "epsEstimate": 1.0}]}}
    assert C.surprise("X1", "EX.PA", "2026-09-30", ev, est)[0] == "2026-10-24"
    assert abs(C.surprise("X1", "EX.PA", "2026-09-30", ev, {})[1] - 10.0) < 1e-9


@case("Réponse lue : avis et impact reconnus, textes raccourcis, alerte « aucune » retirée, entrée sans avis ignorée")
def _():
    store = {}
    todo = {"A": ("2026-09-30", "trimestre", "2026-11-20"), "B": ("2025-12-31", "exercice", None), "C": ("2025-12-31", "exercice", None)}
    n = C.applique(store, [entry("A", forts=["x " * 80, "b", "c", "d"], alerte="Dette nette à 4,5 fois l'EBITDA"),
                           entry("B", avis="Favorable", impact="hausse", alerte="Aucune."), entry("C", avis="?"), entry("Z")],
                   todo, "2026-11-25", "claude-haiku-5-5")
    assert n == 2 and sorted(store) == ["A", "B"], store
    a, b = store["A"], store["B"]
    assert a["per"] == "2026-09-30" and a["nat"] == "trimestre" and a["pub"] == "2026-11-20" and a["i"] == "down" and a["a"] == "mit"
    assert len(a["f"]) == 3 and len(a["f"][0]) <= 100 and a["f"][0].endswith("…") and a["al"].startswith("Dette nette")
    assert b["a"] == "fav" and b["i"] == "up" and "al" not in b and "pub" not in b, b
    assert C.conseil(a).startswith("Point d'alerte") and C.conseil(b) == "Rien dans ces comptes qui contredise la règle testée."
    assert C.conseil({"a": "def"}).startswith("Point d'alerte")


@case("Sans secret ANTHROPIC_API_KEY : rien n'est lu, fichier inchangé")
def _():
    setup({"FR0000000001": {"ticker": "A.PA", "years": Y}}, old={"items": {"x": 1}})
    os.environ.pop("ANTHROPIC_API_KEY", None)
    C.appel = lambda *a, **k: (_ for _ in ()).throw(AssertionError("appel sans clé"))
    before = C.OUT.read_text()
    assert C.main() == 0 and C.OUT.read_text() == before


@case("Lecture du soir : nouvelles publications puis 🎯 / 💎 d'abord, « pub » seulement pour des comptes vus il y a moins de 10 jours")
def _():
    fin = {"FR0000000001": {"ticker": "A.PA", "years": Y, "quarters": Q, "newAt": ago(1), "newPer": "2026-09-30"},
           "@B.ST": {"ticker": "B.ST", "years": Y},
           "FR0000000003": {"ticker": "C.PA", "years": Y, "quarters": Q, "newAt": ago(20), "newPer": "2026-09-30"},
           "FR0000000004": {"ticker": "D.PA", "years": []}}
    dash = {"rank": {"rows": [{"key": "B.ST", "sym": "B.ST", "name": "Bêta", "note": 60}], "pick10": ["B.ST"]}}
    setup(fin, dash, old={"items": {"OLD.ST": {"per": "2025-12-31", "v": C.VERSION}}})
    os.environ["ANTHROPIC_API_KEY"] = "test"
    seen = []

    def fake(key, cfg, texte, systeme=None):
        ids = [ln.split('"')[1] for ln in texte.splitlines() if ln.startswith('Société id "')]
        seen.append(ids)
        assert systeme == C.SYSTEME
        return reponse([entry(i) for i in ids])
    C.appel = fake
    orig = C.config
    C.config = lambda: dict(orig(), lot=1, paralleles=1)
    try:
        assert C.main() == 0
    finally:
        C.config = orig
    cfg = C.config()
    out = json.loads(C.OUT.read_text())
    it = out["items"]
    assert [s[0] for s in seen] == ["FR0000000001", "B.ST", "FR0000000003"], seen
    assert it["FR0000000001"]["pub"] == ago(1) and "pub" not in it["FR0000000003"] and "pub" not in it["B.ST"], it
    assert "OLD.ST" not in it and "FR0000000004" not in it, "société sortie des comptes retirée, société sans comptes non lue"
    assert out["lecture"]["lus"] == 3 and out["lecture"]["modele"] == cfg["modele"]
    seen.clear()
    assert C.main() == 0 and seen == [], "relu sans nouvelle période"


@case("API en panne : fichier précédent gardé tel quel, sans fichier temporaire")
def _():
    setup({"FR0000000001": {"ticker": "A.PA", "years": Y}}, old={"items": {"FR0000000001": {"per": "2024-12-31", "v": C.VERSION}}})
    os.environ["ANTHROPIC_API_KEY"] = "test"

    def down(*a, **k):
        raise RuntimeError("HTTP 529")
    C.appel = down
    before = C.OUT.read_text()
    assert C.main() == 0 and C.OUT.read_text() == before
    assert not list(C.DATA.glob("*.tmp"))


@case("Budget de la publication du code : variable COMPTES_BUDGET (bornée)")
def _():
    base = C.config()["budget"]
    os.environ["COMPTES_BUDGET"] = "540"
    try:
        assert C.config()["budget"] == 540
        os.environ["COMPTES_BUDGET"] = "99999"
        assert C.config()["budget"] == 1200
        os.environ["COMPTES_BUDGET"] = "abc"
        assert C.config()["budget"] == base
    finally:
        os.environ.pop("COMPTES_BUDGET", None)


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
