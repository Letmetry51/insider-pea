"""
Tests hors ligne de la résolution des symboles Yahoo (aucun accès réseau) : secours par le catalogue des sociétés cotées
ou une société déjà suivie, noms sans accents, contrôle du prix déclaré, cache abîmé.

  python scrapers/test_prices.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prices as P  # noqa: E402

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


def setup():
    d = Path(tempfile.mkdtemp())
    P.DATA = d
    (d / "societes-index.json").write_text(json.dumps({"rows": [["ENG.MC", "Enagás, S.A.", "ES", 4000], ["FCT.MI", "Fincantieri S.p.A.", "IT", 3000], ["INVE-B.ST", "Investor AB (publ)", "SE", 80000]]}))


@case("Secours par le catalogue : accents, forme juridique, bourse du pays d'origine")
def _():
    setup()
    assert P.local_by_name("ESO130960018", "Enagas SA", {}, {})["ticker"] == "ENG.MC"
    assert P.local_by_name("SE0015811963", "Investor Aktiebolag", {}, {})["ticker"] == "INVE-B.ST"
    assert P.local_by_name("DE0001234567", "Enagas SA", {}, {}) is None  # autre pays : pas de rapprochement
    assert P.local_by_name("SE0000000000", "Inconnue AB", {}, {}) is None


@case("Secours par une société déjà suivie ; cache abîmé (symbole vide, entrée nulle) sans plantage")
def _():
    setup()
    cache = {"X": {"ticker": None}, "Y": None, "IT0001415246": {"ticker": "FCT2.MI", "name": "Fincantieri SpA"}}
    (P.DATA / "societes-index.json").write_text(json.dumps({"rows": []}))
    assert P.local_by_name("IT0005599862", "Fincantieri SpA", cache, {})["ticker"] == "FCT2.MI"


@case("Contrôle du prix déclaré : même ordre de grandeur que le cours, sinon refus")
def _():
    h = {"rows": [["2026-10-01", 0, 0, 0, 10.0]]}
    assert P.coherent(h, ("2026-10-02", 11)) and P.coherent(h, None)
    assert not P.coherent(h, ("2026-10-02", 100)) and not P.coherent(h, ("2026-10-02", 2))


@case("Liste officielle de la bourse : ISIN introuvable chez Yahoo ou cours figé, retenue si cours frais et prix déclaré cohérent")
def _():
    from datetime import date
    today = date(2026, 10, 20)
    rows = [[f"2026-{m:02d}-{d:02d}", 1, 1, 1, 10.0, 1] for m in range(1, 11) for d in range(1, 29)][:280]
    rows[-1][0] = "2026-10-19"
    fresh = {"rows": rows, "currency": "EUR", "splits": [], "dividends": [], "weekly": []}
    old = {"rows": [r for r in rows if r[0] < "2026-09-01"], "currency": "EUR"}
    table = {"FR0000036816": ["EIFF.PA", "EUR"]}
    got = P.try_exchange("FR0000036816", table, ("2026-10-01", 10.5), today, fetch=lambda t, p: fresh)
    assert got[0] == "EIFF.PA" and got[1] is fresh
    assert P.try_exchange("FR0000036816", table, ("2026-10-01", 100), today, fetch=lambda t, p: fresh) == (None, None)  # autre titre
    assert P.try_exchange("FR0000036816", table, None, today, fetch=lambda t, p: old) == (None, None)  # pas plus frais
    assert P.try_exchange("FR0000036816", table, None, today, current="EIFF.PA", fetch=lambda t, p: fresh) == (None, None)
    assert P.try_exchange("FR9999999999", table, None, today, fetch=lambda t, p: fresh) == (None, None)
    assert P.try_exchange("FR0000036816", None, None, today) == (None, None)
    assert P.frozen(old, today) and not P.frozen(fresh, today) and not P.frozen(None, today)


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
