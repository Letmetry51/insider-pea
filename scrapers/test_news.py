"""
Tests hors ligne de l'actualité qualitative (scrapers/news.py) : un soir où le budget de temps est atteint, les sociétés non relues
gardent leurs titres de la veille (encore récents) ; fichier écrit sans fichier temporaire laissé. Aucun accès réseau.

  python scrapers/test_news.py
"""
import json
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


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
