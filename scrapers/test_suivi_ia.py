"""
Tests hors ligne de la mesure en direct des lectures de l'IA (scrapers/suivi_ia.py) : journal sans doublon, date de l'événement
jamais avant le soir où l'outil la voit, écart avec la moyenne des sociétés sur les mêmes séances, cas sans cours, totaux des cas
anciens, fichier illisible. Aucun accès réseau.

  python scrapers/test_suivi_ia.py
"""
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import suivi_ia as S  # noqa: E402

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


TODAY = date.today()


def days(n):
    """n séances de semaine finissant aujourd'hui (dates AAAA-MM-JJ)."""
    out, d = [], TODAY
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def setup(n_syms=60, comptes=None, news=None, old=None, grow=None):
    """Fiches de n_syms sociétés : cours qui montent de 0,1 % par séance (moyenne), sauf grow = {symbole: pente}."""
    d = Path(tempfile.mkdtemp())
    S.DATA, S.OUT = d, d / "suivi_ia.json"
    (d / "societes").mkdir()
    dd = days(260)
    items = {}
    for j in range(n_syms):
        sym = "S%d.PA" % j
        g = (grow or {}).get(sym, .001)
        items[sym] = {"d": [round(10 * (1 + g) ** k, 4) for k in range(len(dd))]}
    (d / "societes" / "0.json").write_text(json.dumps({"dDates": dd, "items": items}))
    rows = [{"key": "K%d" % j, "sym": "S%d.PA" % j} for j in range(n_syms)]
    (d / "euro-signal.json").write_text(json.dumps({"rank": {"rows": rows}}))
    (d / "comptes_ia.json").write_text(json.dumps({"items": comptes or {}}))
    (d / "news.json").write_text(json.dumps({"items": news or {}}))
    if old is not None:
        S.OUT.write_text(json.dumps(old) if not isinstance(old, str) else old)
    return dd


def saved():
    return json.loads(S.OUT.read_text())


@case("Journal : une ligne par lecture de comptes (société, période) et par société et par soir pour les titres, sans doublon")
def _():
    comptes = {"K1": {"per": "2026-09-30", "a": "fav", "i": "up", "res": "x"}, "K2": {"per": "2025-12-31", "a": "def", "i": "down"},
               "K3": {"per": "2025-12-31", "a": "?"}}
    news = {"K1": [{"t": "Bonne nouvelle", "v": 1, "p": 1, "i": "up"}, {"t": "Autre", "v": 1, "p": 1, "i": "up"},
                   {"t": "Sans rapport", "v": 1, "p": 0, "i": "flat"}, {"t": "Pas lu", "k": "pos"}],
            "K2": [{"t": "Mauvaise", "v": 1, "p": 1, "i": "down"}], "K4": [{"t": "Neutre", "v": 1, "p": 1, "i": "flat"}]}
    setup(comptes=comptes, news=news)
    assert S.main() == 0
    b = saved()
    assert sorted(b["c"]) == ["c|K1|2026-09-30", "c|K2|2025-12-31"], b["c"]
    assert b["c"]["c|K2|2025-12-31"]["al"] == 1 and b["c"]["c|K1|2026-09-30"]["al"] == 0, "avis défavorable : conseil point d'alerte"
    assert b["c"]["c|K1|2026-09-30"]["d"] == TODAY.isoformat() and b["c"]["c|K1|2026-09-30"]["s"] == "S1.PA"
    t = {v["k"]: v for v in b["t"].values()}
    assert t["K1"]["net"] == 1 and t["K1"]["n"] == 2 and t["K2"]["net"] == -1 and t["K4"]["net"] == 0, t
    assert S.main() == 0
    b2 = saved()
    assert len(b2["c"]) == 2 and len(b2["t"]) == 3 and len(b2["seen"]) == 4, "relu le même soir : rien de compté deux fois"


@case("Même société relue dans le mois (premier relevé des trimestres) : pas notée deux fois, sauf comptes tout juste publiés")
def _():
    setup(comptes={"K1": {"per": "2026-09-30", "a": "fav", "i": "up"}, "K2": {"per": "2026-09-30", "a": "mit", "pub": "2026-11-25"}})
    d = (TODAY - timedelta(days=5)).isoformat()
    S.OUT.write_text(json.dumps({"c": {"c|K1|2025-12-31": {"k": "K1", "s": "S1.PA", "d": d, "i": "flat", "a": "fav", "al": 0},
                                       "c|K2|2025-12-31": {"k": "K2", "s": "S2.PA", "d": d, "i": "flat", "a": "mit", "al": 0}},
                                 "t": {}, "seen": {}, "arch": {}}))
    assert S.main() == 0
    c = saved()["c"]
    assert "c|K1|2026-09-30" not in c and c["c|K2|2026-09-30"]["p"] == 1, sorted(c)


@case("Mesure : écart avec la moyenne des sociétés sur les mêmes séances, à 13 et 26 semaines, seulement avec assez de recul")
def _():
    dd = setup(grow={"S1.PA": .003, "S2.PA": -.002})
    d0 = (TODAY - timedelta(days=200)).isoformat()
    old = {"c": {"c|K1|x": {"k": "K1", "s": "S1.PA", "d": d0, "i": "up", "a": "fav", "al": 0},
                 "c|K2|x": {"k": "K2", "s": "S2.PA", "d": d0, "i": "down", "a": "def", "al": 1},
                 "c|K9|x": {"k": "K9", "s": "INCONNU.PA", "d": d0, "i": "flat", "a": "mit", "al": 0},
                 "c|K3|x": {"k": "K3", "s": "S3.PA", "d": (TODAY - timedelta(days=30)).isoformat(), "i": "flat", "a": "mit", "al": 0}},
           "t": {}, "seen": {}, "arch": {}}
    S.OUT.write_text(json.dumps(old))
    assert dd and S.main() == 0
    c = saved()["c"]
    assert c["c|K1|x"]["x13"] > 10 and c["c|K1|x"]["x26"] > c["c|K1|x"]["x13"], c["c|K1|x"]  # +0,3 %/séance face à +0,1 %
    assert c["c|K2|x"]["x13"] < -10, c["c|K2|x"]
    assert "x13" not in c["c|K9|x"], "cours introuvable : pas de mesure, nouvel essai plus tard"
    assert "x13" not in c["c|K3|x"], "30 jours de recul : trop tôt"
    st = saved()["stats"]["c"]
    assert st["avis:fav"]["n13"] == 1 and st["avis:fav"]["m13"] > 10 and st["conseil:1"]["m13"] < -10 and st["avis:mit"]["n13"] == 0, st


@case("Première séance à partir du soir de la lecture : jamais un cours d'avant")
def _():
    dd = ["2026-01-05", "2026-01-06", "2026-01-08"]
    assert S.first_at(dd, "2026-01-06") == 1 and S.first_at(dd, "2026-01-07") == 2 and S.first_at(dd, "2026-01-09") is None
    assert S.ret((dd, [10, 11, 12]), "2026-01-07", 1) is None, "pas encore de séance après"
    assert S.ret((dd, [10, 0, 12]), "2026-01-05", 1) is None, "cours nul"
    assert abs(S.ret((dd, [10, 11, 50]), "2026-01-05", 3) - 3.0) < 1e-9, "borné à +300 %"


@case("Cas de plus de 400 jours mesurés : rangés dans les totaux, bilan inchangé ; cas sans cours abandonnés après 420 jours")
def _():
    setup()
    d_old = (TODAY - timedelta(days=401)).isoformat()
    d_gone = (TODAY - timedelta(days=421)).isoformat()
    old = {"c": {"c|A|x": {"k": "A", "s": "S1.PA", "d": d_old, "i": "up", "a": "fav", "al": 0, "x13": 5.0, "x26": 7.0},
                 "c|B|x": {"k": "B", "s": "PARTI.PA", "d": d_gone, "i": "down", "a": "def", "al": 1}},
           "t": {"t|A|x": {"k": "A", "s": "S1.PA", "d": d_old, "net": 1, "n": 1, "x13": -1.0, "x26": 2.0}}, "seen": {}, "arch": {}}
    S.OUT.write_text(json.dumps(old))
    assert S.main() == 0
    b = saved()
    assert "c|A|x" not in b["c"] and "t|A|x" not in b["t"], b
    assert b["arch"]["c:avis:fav"] == {"n13": 1, "s13": 5.0, "n26": 1, "s26": 7.0}, b["arch"]
    assert b["stats"]["c"]["avis:fav"]["m26"] == 7.0 and b["stats"]["t"]["effet:1"]["m13"] == -1.0, b["stats"]
    assert "c|B|x" not in b["c"] and b["stats"]["c"]["avis:def"]["n13"] == 0, "cas sans cours : abandonné puis rangé, sans chiffre"


@case("Fichier du suivi illisible : rien n'est écrit, l'étape le signale")
def _():
    setup(comptes={"K1": {"per": "2026-09-30", "a": "fav"}}, old="{abîmé")
    assert S.main() == 1 and S.OUT.read_text() == "{abîmé"


@case("Titres déjà comptés oubliés après 60 jours")
def _():
    setup()
    S.OUT.write_text(json.dumps({"c": {}, "t": {}, "seen": {"a": (TODAY - timedelta(days=61)).isoformat(), "b": TODAY.isoformat()},
                                 "arch": {}}))
    assert S.main() == 0 and saved()["seen"] == {"b": TODAY.isoformat()}


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
