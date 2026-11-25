"""
Tests hors ligne de l'actualité qualitative (scrapers/news.py) : un soir où le budget de temps est atteint, les sociétés non relues
gardent leurs titres de la veille (encore récents) ; fichier écrit sans fichier temporaire laissé. Aucun accès réseau.

  python scrapers/test_news.py
"""
import json
import os
import sys
import tempfile
import types
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news as N  # noqa: E402

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


@case("Budget atteint : sociétés non relues avec les titres de la veille, sauf les titres trop anciens")
def _():
    d = Path(tempfile.mkdtemp())
    N.DATA, N.OUT = d, d / "news.json"
    today = date.today().isoformat()
    recent = (date.today() - timedelta(days=3)).isoformat()
    N.targets = lambda: {"A": "Alpha", "B": "Beta", "C": "Gamma"}
    N.yahoo_press = lambda: {}
    N.OUT.write_text(json.dumps({"items": {"B": [{"t": "Beta signe un contrat", "s": "X", "d": recent, "u": ""}],
                                           "C": [{"t": "Gamma, un vieux titre", "s": "X", "d": "2000-01-01", "u": ""}]}}))
    calls = []

    def google(name, lang):
        calls.append(name)
        return [{"t": name + " publie ses résultats", "s": "Y", "d": today, "u": ""}]
    N.google = google
    clock = [0.0]

    def fake_time():
        clock[0] += 300.0  # chaque lecture de l'horloge avance de 5 minutes : budget de 7 minutes atteint après la 1re société
        return clock[0]
    # horloge de news.py seulement (time.time remplacé partout fausserait date.today(), qui la lit aussi)
    N.time = types.SimpleNamespace(time=fake_time, sleep=lambda s: None)
    N.main()
    out = json.loads(N.OUT.read_text())["items"]
    assert calls == ["Alpha"], calls
    assert out["A"][0]["t"] == "Alpha publie ses résultats", out
    assert out["B"][0]["t"] == "Beta signe un contrat", out
    assert "C" not in out, out
    assert not list(d.glob("*.tmp")), "fichier temporaire laissé"


@case("Lecture de l'IA reprise d'un soir à l'autre pour le même titre ; titre nouveau : mots-clés seulement ; « cours » ≠ « course »")
def _():
    d = Path(tempfile.mkdtemp())
    N.DATA, N.OUT = d, d / "news.json"
    today = date.today().isoformat()
    N.targets = lambda: {"SE0001662230": "Husqvarna AB (publ)"}
    N.yahoo_press = lambda: {}
    t1 = "Husqvarna demande à l'autorité commerciale britannique d'enquêter sur le dumping de tondeuses robotisées chinoises"
    N.OUT.write_text(json.dumps({"items": {"SE0001662230": [{"t": t1, "s": "IndexBox", "d": today, "u": "", "k": "neg", "i": "up", "p": 1,
                                                             "r": "protection possible contre les tondeuses chinoises", "v": 1}]}}))
    N.google = lambda name, lang: [{"t": t1, "s": "IndexBox", "d": today, "u": ""},
                                   {"t": "Husqvarna relève ses prévisions", "s": "X", "d": today, "u": ""}]
    N.time = types.SimpleNamespace(time=lambda: 0.0, sleep=lambda s: None)
    N.main()
    lst = {g["t"]: g for g in json.loads(N.OUT.read_text())["items"]["SE0001662230"]}
    assert lst[t1].get("i") == "up" and lst[t1].get("v") == 1 and lst[t1]["k"] == "neg", lst[t1]
    assert "v" not in lst["Husqvarna relève ses prévisions"], lst
    assert not N.FIN_RE.search("TEST DE COURSE MXA: 2026 HUSQVARNA FC450") and N.FIN_RE.search("le cours de Husqvarna"), "cours / course"


sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_ia as NI  # noqa: E402


def _items():
    return {"SE0001662230": [
        {"t": "Husqvarna FF - BK Häcken FF 2 Statistiques: Football Scores & Résultats", "s": "Eurosport", "d": "2026-11-07", "u": "", "k": ""},
        {"t": "TEST DE COURSE MXA: 2026 HUSQVARNA FC450", "s": "MXA", "d": "2026-11-20", "u": "", "k": ""},
        {"t": "Husqvarna demande d'enquêter sur le dumping de tondeuses chinoises", "s": "IndexBox", "d": "2026-11-22", "u": "", "k": "neg"}]}


@case("IA : lectures reportées (hausse, sans rapport), réponse en partie mal formée, ordre d'affichage")
def _():
    it = _items()
    rep = ('{"lectures": [{"id": "SE0001662230:2", "pertinent": true, "impact": "hausse", "raison": "protection contre le dumping chinois"},'
           ' {"id": "SE0001662230:0", "pertinent": false, "impact": "neutre", "raison": "club de football homonyme"},'
           ' {"id": "SE0001662230:1", "pertinent": false, "raison": "moto KTM" ')  # dernière entrée coupée
    n = NI.applique(it, NI.lire(rep))
    assert n == 2, n
    g = it["SE0001662230"]
    assert g[2]["i"] == "up" and g[2]["p"] == 1 and g[2]["v"] == NI.VERSION, g[2]
    assert g[0]["p"] == 0 and g[0]["i"] == "flat" and "football" in g[0]["r"], g[0]
    assert "v" not in g[1], "entrée coupée : pas de lecture inventée"
    o = NI.ordre(g)
    assert [x["s"] for x in o] == ["IndexBox", "MXA", "Eurosport"], [x["s"] for x in o]  # lu et utile, non lu, sans rapport
    assert NI.applique(it, [{"id": "inconnu:0", "pertinent": True}, {"id": "SE0001662230:9", "pertinent": True},
                            {"id": "SE0001662230:1", "pertinent": "oui"}]) == 0, "identifiants faux ou réponse invalide ignorés"


@case("IA : lots par société, sans secret aucun appel ni écriture, appel en erreur → mots-clés gardés, écriture atomique")
def _():
    d = Path(tempfile.mkdtemp())
    NI.DATA, NI.OUT = d, d / "news.json"
    (d / "euro-signal.json").write_text(json.dumps({"rank": {"rows": [{"key": "SE0001662230", "name": "Husqvarna AB (publ)",
                                                                        "sym": "HUSQ-B.ST", "country": "SE", "sector": "Industrie"}]}}))
    NI.OUT.write_text(json.dumps({"items": _items()}))
    L = NI.lots(_items(), NI.contexte(), 40)
    assert len(L) == 1 and len(L[0][0][1]) == 3, L
    msg = NI.message(L[0], _items(), NI.contexte())
    assert "Husqvarna AB (publ) (symbole HUSQ-B.ST, pays SE, secteur Industrie)" in msg and 'id "SE0001662230:2"' in msg, msg
    called = []
    NI.appel = lambda *a: called.append(1) or (_ for _ in ()).throw(RuntimeError("HTTP 529"))
    os.environ.pop("ANTHROPIC_API_KEY", None)
    before = NI.OUT.read_text()
    NI.main()
    assert not called and NI.OUT.read_text() == before, "sans secret : rien appelé, rien écrit"
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        NI.main()
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    assert called and NI.OUT.read_text() == before, "API en panne : fichier laissé tel quel (ordre des mots-clés compris)"
    assert not list(d.glob("*.tmp")), "fichier temporaire laissé"


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
