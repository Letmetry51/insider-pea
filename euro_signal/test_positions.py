"""
Tests hors ligne des alertes personnelles (positions et plans surveillés) : lecture des emails, déclenchements,
et surtout absence d'emails répétés chaque soir. Aucun accès à Gmail.

  python euro_signal/test_positions.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import positions as P  # noqa: E402

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


@case("Lecture des emails : position, vente, surveiller, ne plus surveiller ; alertes envoyées ignorées")
def _():
    body = "Société : Ubisoft\nISIN : FR0000054470\nPrix d'achat : 4,95\nDate d'achat : 14/10/2026\nObjectif de hausse : 20\nSeuil de protection : 10"
    p = P.parse_position("[Euro Signal] Position FR0000054470", body, "2026-10-14T20:00:00+00:00")
    assert p["kind"] == "position" and p["price"] == 4.95 and p["date"] == "2026-10-14" and p["target"] == 20 and p["stop"] == 10, p
    assert P.parse_position("[Euro Signal] Vente FR0000054470", "", "2026-10-15T08:00:00+00:00")["kind"] == "vente"
    assert P.parse_position("[Euro Signal] Surveiller FR0000054470", "", "x")["kind"] == "surveiller"
    assert P.parse_position("[Euro Signal] Ne plus surveiller FR0000054470", "", "x")["kind"] == "arret"
    # les alertes envoyées par Euro Signal (dans les Envoyés) ne doivent jamais être lues comme une position ou une vente
    for subj in ("[Euro Signal] Revente — Ubisoft : objectif atteint (réf. FR0000054470:20261014:obj20)",
                 "[Euro Signal] Plan — Ubisoft : entre dans sa zone d'achat (réf. plan:FR0000054470:zone159)",
                 "[Euro Signal] Sélection de la semaine FR0000054470"):
        assert P.parse_position(subj, "", "x") is None, subj


def plan(entry, trig, upper, verdict="waitBreakout", key="breakout"):
    return {"verdict": verdict, "label": "Attendre une cassure", "primary": {"key": key, "trigger": trig, "entry": entry, "level": 10.0, "stop": 9.4,
            "zoneLo": 10.0, "zoneHi": 10.2}, "wedge": {"type": "falling", "upperNow": upper}}


@case("Plan surveillé : une seule alerte par événement, même si les niveaux bougent un peu chaque soir")
def _():
    keys = set()
    # dix soirs de suite au-dessus du déclencheur, avec un ATR (donc un déclencheur) et une droite de biseau qui varient
    for d in range(10):
        today = date(2026, 10, 19 + (d % 5))  # même semaine
        ev = P.watch_events(plan(10.3 + d * 0.002, 10.25 + d * 0.003, 10.1 - d * 0.01), 10.6, today)
        keys |= {k for k, _ in ev}
    assert len([k for k in keys if k.startswith("cassure")]) == 1, keys
    assert len([k for k in keys if k.startswith("biseau")]) == 1, keys
    # nouvelle résistance nettement plus haute : nouvel événement, nouvelle clé
    p2 = plan(11.6, 11.55, 11.0)
    p2["primary"]["level"] = 11.3
    k2 = {k for k, _ in P.watch_events(p2, 11.8, date(2026, 10, 26))}
    assert not (k2 & keys), (k2, keys)


@case("Plan surveillé : achat possible et stop, une alerte chacun")
def _():
    p = plan(10.1, None, None, verdict="buyNow", key="support")
    p["wedge"] = {}
    a = {k for k, _ in P.watch_events(p, 10.1, date(2026, 10, 20))}
    b = {k for k, _ in P.watch_events(p, 10.12, date(2026, 10, 27))}
    assert any(k.startswith("zone") for k in a) and any(k.startswith("achat") for k in a) and a == b, (a, b)
    s = {k for k, _ in P.watch_events(p, 9.3, date(2026, 10, 28))}
    assert any(k.startswith("stop") for k in s), s
    assert P.watch_events(None, 10) == [] and P.watch_events(p, None) == []


@case("Revente : objectif, protection, vente d'un dirigeant, rappel à 6 mois (plus d'alerte de repli ni de MM)")
def _():
    pos = {"isin": "FR0000054470", "price": 10.0, "date": "2026-09-01", "target": 20, "stop": 10}
    rows = [["2026-09-%02d" % d, 0, 0, 0, 10 + d * 0.1, 0] for d in range(1, 31)]  # 10,1 → 13,0 : +30 %
    ev, info = P.evaluate(pos, rows, {}, [], date(2026, 10, 1))
    assert any(k == "obj20" for k, _ in ev) and round(info["perf"]) == 30, ev
    rows2 = rows + [["2026-10-01", 0, 0, 0, 8.9, 0]]
    ev2, _ = P.evaluate(pos, rows2, {}, [{"type": "vente", "status": "ok", "pubDate": "2026-09-20", "person": "X", "txDate": "2026-09-18"}], date(2026, 10, 2))
    k2 = {k for k, _ in ev2}
    assert "stop10" in k2 and not any(k.startswith("repli") for k in k2) and "vente20260920" in k2 and "6mois" not in k2, k2
    ev3, _ = P.evaluate(pos, rows2, {"deathCrossDate": "2026-09-25"}, [], date(2027, 3, 3))
    k3 = {k for k, _ in ev3}
    assert "6mois" in k3 and not any(k.startswith("mm") for k in k3), k3
    assert P.evaluate(pos, [], {}, [], date(2026, 10, 2)) == ([], None)


@case("Paliers de baisse de 10 %, protection à −30 % par défaut, rappel à 6 mois selon le 🎯")
def _():
    pos = {"isin": "FR0000054470", "price": 10.0, "date": "2026-09-01"}  # ni objectif ni protection indiqués
    rows = lambda v: [["2026-09-02", 0, 0, 0, 10.0, 0], ["2026-09-03", 0, 0, 0, v, 0]]
    k = lambda v, d=date(2026, 9, 4), pk=None: {x for x, _ in P.evaluate(pos, rows(v), {}, [], d, pk)[0]}
    assert k(9.5) == set(), k(9.5)
    assert k(8.9) == {"baisse10"}, k(8.9)
    assert k(7.5) == {"baisse20"}, k(7.5)  # seul le palier le plus profond
    assert k(6.9) == {"stop30"}, k(6.9)     # −31 % : protection, pas de palier 30 en double
    assert k(5.5) == {"stop30", "baisse40"}, k(5.5)
    ev = dict(P.evaluate(pos, rows(11), {}, [], date(2027, 3, 5), True)[0])
    assert "encore dans le 🎯" in ev["6mois"], ev
    ev = dict(P.evaluate(pos, rows(11), {}, [], date(2027, 3, 5), False)[0])
    assert "n'est plus dans le 🎯" in ev["6mois"], ev


@case("Société du catalogue (symbole Yahoo, sans ISIN) : position lue, MM50 sous MM200 recalculée")
def _():
    p = P.parse_position("[Euro Signal] Position VOLV-B.ST", "Société : Volvo\nSymbole : VOLV-B.ST\nPrix d'achat : 250\nDate d'achat : 2026-10-20", "2026-10-20T20:00:00+00:00")
    assert p and p["isin"] == "VOLV-B.ST" and p["price"] == 250, p
    assert P.parse_position("[Euro Signal] Vente OMV.VI", "", "x")["isin"] == "OMV.VI"
    assert P.parse_position("[Euro Signal] Revente — Volvo : stop (réf. VOLV-B.ST:20261020:stop10)", "", "x") is None
    up = [[("2026-%03d" % k), 0, 0, 0, 100 + k * 0.5, 0] for k in range(260)]
    down = up + [[("2026-%03d" % (260 + k)), 0, 0, 0, 230 - k * 2.0, 0] for k in range(80)]
    assert P.death_cross(up, "2026-000") is None
    d = P.death_cross(down, "2026-000")
    assert d and d > "2026-260", d
    assert P.shard_of("VU.PA") == P.shard_of("VU.PA") and 0 <= P.shard_of("VOLV-B.ST") < 32


@case("Plan surveillé d'une société du catalogue : email « Surveiller SYMBOLE » lu, repères du classement utilisables")
def _():
    w = P.parse_position("[Euro Signal] Surveiller OMV.VI", "Société : OMV\nSymbole : OMV.VI", "2026-10-17T10:00:00+00:00")
    assert w and w["kind"] == "surveiller" and w["isin"] == "OMV.VI", w
    pw = {"v": "waitBreakout", "label": "Attendre une cassure", "p": {"key": "breakout", "trigger": 52.1, "entry": 52.3, "level": 51.8, "stop": 48.0, "zoneLo": None, "zoneHi": None}, "w": {"type": "rising", "upperNow": 55.0}}
    plan = {"verdict": pw["v"], "label": pw["label"], "primary": pw["p"], "wedge": pw["w"]}
    keys = [k for k, _ in P.watch_events(plan, 52.5)]
    assert any(k.startswith("cassure") for k in keys), keys
    assert any(k.startswith("stop") for k, _ in P.watch_events(plan, 47.0))



@case("Plan ✏️ ajusté à la main : niveaux lus dans l'email, une alerte par niveau, sens d'entrée respecté")
def _():
    body = "Société : Ubisoft\nISIN : FR0000054470\nDate : 2026-10-19\nEntrée ajustée : 12,5\nStop ajusté : 11\nObjectif ajusté : 15\nCours à la demande : 13,2"
    w = P.parse_position("[Euro Signal] Surveiller FR0000054470", body, "2026-10-19T10:00:00+00:00")
    c = w["custom"]
    assert w["kind"] == "surveiller" and c == {"entry": 12.5, "stop": 11.0, "target": 15.0, "ref": 13.2}, w
    assert P.parse_position("[Euro Signal] Surveiller FR0000054470", "Cours à la demande : 13", "x")["custom"] is None
    k = lambda cc, last: {x for x, _ in P.custom_events(cc, last)}
    # cours au-dessus du prix choisi : on attend le repli
    assert k(c, 13.0) == set(), k(c, 13.0)
    assert {x for x in k(c, 12.55) if x.startswith("perso-entree")} and k(c, 12.55) == k(c, 12.4), (k(c, 12.55), k(c, 12.4))
    assert any(x.startswith("perso-stop") for x in k(c, 10.9)) and any(x.startswith("perso-objectif") for x in k(c, 15.1))
    # cours sous le prix choisi : on attend la hausse jusqu'à ce prix
    b = dict(c, ref=11.8)
    assert k(b, 12.4) == set() and any(x.startswith("perso-entree") for x in k(b, 12.6)), (k(b, 12.4), k(b, 12.6))
    assert P.custom_events(None, 12) == [] and P.custom_events(c, None) == []
    assert P.plan_txt(c) == "ajusté à la main (entrée 12,50, stop 11,00, objectif 15,00)", P.plan_txt(c)


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
