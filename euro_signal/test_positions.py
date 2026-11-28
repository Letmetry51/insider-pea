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


@case("Dividendes détachés depuis l'achat (relecture du 07/11/2026) : comptés dans la performance, pas de fausse protection −30 %")
def _():
    pos = {"isin": "WAWI.OL", "price": 100.0, "date": "2026-06-01"}
    d = date(2026, 9, 4)
    adj = [["2026-06-01", 0, 0, 0, 100.0, 0], ["2026-07-15", 0, 0, 0, 80.0, 0], ["2026-09-03", 0, 0, 0, 69.0, 0]]
    ev0, info0 = P.evaluate(pos, adj, {}, [], d, adjusted=True)
    assert "stop30" in {k for k, _ in ev0} and abs(info0["perf"] + 31) < 0.01, (ev0, info0)  # sans dividende : −31 %
    divs = [{"date": "2026-05-20", "amount": 9.0}, {"date": "2026-07-15", "amount": 12.0}, {"date": "2026-09-10", "amount": 5.0}]
    ev, info = P.evaluate(pos, adj, {}, [], d, adjusted=True, dividends=divs)  # seul le dividende du 15/07 compte (avant : déjà payé ; après : pas encore)
    keys = {k for k, _ in ev}
    assert "stop30" not in keys and "baisse10" in keys and abs(info["perf"] + 19) < 0.01 and info["div"] == 12.0, (ev, info)
    # cours bruts d'Euro Signal : dividende de 4 au cours d'avant la division par 2, soit 2 par action d'aujourd'hui
    raw = [["2026-06-01", 0, 0, 0, 100.0, 0], ["2026-07-14", 0, 0, 0, 90.0, 0], ["2026-07-15", 0, 0, 0, 45.0, 0], ["2026-09-03", 0, 0, 0, 34.0, 0]]
    ev2, info2 = P.evaluate(pos, raw, {}, [], d, splits=[{"date": "2026-07-15", "ratio": 2.0}], dividends=[{"date": "2026-06-20", "amount": 4.0}])
    assert abs(info2["perf"] - ((34 + 2) / 50 - 1) * 100) < 0.01 and "stop30" not in {k for k, _ in ev2}, (ev2, info2)
    ev3, _ = P.evaluate(pos, adj, {}, [], d, adjusted=True, dividends=[{"date": "x"}, None, {"date": "2026-07-01", "amount": "abc"}])
    assert "stop30" in {k for k, _ in ev3}, "dividendes illisibles : ignorés"
    # catalogue, division par 2 depuis l'achat : base = cours ajusté du jour de l'achat, qui compte déjà les dividendes
    split = [["2026-06-01", 0, 0, 0, 48.5, 0], ["2026-09-03", 0, 0, 0, 52.0, 0]]
    _, info4 = P.evaluate(pos, split, {}, [], d, adjusted=True, dividends=[{"date": "2026-07-01", "amount": 1.5}])
    assert abs(info4["perf"] - (52 / 48.5 - 1) * 100) < 0.01 and info4["div"] == 0, info4


@case("Division ou regroupement d'actions après l'achat : pas de fausse protection −30 % ni de faux objectif")
def _():
    pos = {"isin": "FR0000054470", "price": 100.0, "date": "2026-06-01"}
    d = date(2026, 9, 4)
    # cours bruts d'Euro Signal : division par 2 le 15/07, signalée dans « splits »
    raw = [["2026-06-01", 0, 0, 0, 101.0, 0], ["2026-07-14", 0, 0, 0, 110.0, 0], ["2026-07-15", 0, 0, 0, 55.0, 0], ["2026-09-03", 0, 0, 0, 52.0, 0]]
    ev, info = P.evaluate(pos, raw, {}, [], d, splits=[{"date": "2026-07-15", "ratio": 2.0}])
    assert not ev and abs(info["perf"] - 4.0) < 0.01 and info["peak"] == 55.0, (ev, info)
    ev0, _ = P.evaluate(pos, raw, {}, [], d)
    assert "stop30" in {k for k, _ in ev0}, "sans la liste des divisions, l'ancienne erreur réapparaît"
    # cours ajustés du catalogue : la série montre 50,5 le jour de l'achat (payé 100)
    adj = [["2026-05-29", 0, 0, 0, 50.0, 0], ["2026-06-01", 0, 0, 0, 50.5, 0], ["2026-07-15", 0, 0, 0, 55.0, 0], ["2026-09-03", 0, 0, 0, 52.0, 0]]
    ev, info = P.evaluate(pos, adj, {}, [], d, adjusted=True)
    assert not ev and abs(info["perf"] - 2.97) < 0.1, (ev, info)
    # regroupement par 10 (catalogue) : payé 2,00, cours ajusté du jour de l'achat 20,40
    ev2, info2 = P.evaluate(dict(pos, price=2.0, target=50), [["2026-06-01", 0, 0, 0, 20.4, 0], ["2026-09-03", 0, 0, 0, 21.0, 0]], {}, [], d, adjusted=True)
    assert not ev2 and info2["perf"] < 5, (ev2, info2)
    # dividende (série ajustée de 3 %) ou achat en cours de séance : le prix payé reste la base ; une vraie baisse reste signalée
    assert P.split_base(100.0, 97.0) == 100.0 and P.split_base(100.0, 112.0) == 100.0
    assert P.split_base(100.0, None) == 100.0 and P.split_base(None, 50.0) is None
    ev3, _ = P.evaluate(pos, [["2026-06-01", 0, 0, 0, 97.0, 0], ["2026-09-03", 0, 0, 0, 68.0, 0]], {}, [], d, adjusted=True)
    assert "stop30" in {k for k, _ in ev3}, ev3
    assert "une seule séance" not in dict(ev3)["stop30"], "deux cours à trois mois d'écart : pas une séance"


@case("Séance à −20 % ou pire (détachement de droits que Yahoo n'ajuste pas) : alerte maintenue, avec l'avertissement")
def _():
    pos = {"isin": "FR0000131757", "price": 100.0, "date": "2026-06-01"}
    d = date(2026, 11, 20)
    # Eramet, 16/11/2026 : −30 % le jour du détachement des droits, cours Yahoo non ajusté
    rows = [["2026-06-01", 0, 0, 0, 100.0, 0], ["2026-11-13", 0, 0, 0, 97.0, 0], ["2026-11-16", 0, 0, 0, 67.5, 0], ["2026-11-17", 0, 0, 0, 68.0, 0]]
    ev = dict(P.evaluate(pos, rows, {}, [], d)[0])
    assert "stop30" in ev and "16/11/2026 en une seule séance" in ev["stop30"] and "augmentation de capital" in ev["stop30"], ev
    # même baisse répartie sur plusieurs séances : pas d'avertissement
    slow = [["2026-06-01", 0, 0, 0, 100.0, 0], ["2026-11-12", 0, 0, 0, 85.0, 0], ["2026-11-13", 0, 0, 0, 76.0, 0], ["2026-11-16", 0, 0, 0, 68.0, 0]]
    ev2 = dict(P.evaluate(pos, slow, {}, [], d)[0])
    assert "stop30" in ev2 and "une seule séance" not in ev2["stop30"], ev2
    # palier de baisse (−20 % en une séance, perte totale −25 %) : avertissement aussi
    mid = [["2026-06-01", 0, 0, 0, 100.0, 0], ["2026-11-13", 0, 0, 0, 94.0, 0], ["2026-11-16", 0, 0, 0, 75.0, 0]]
    ev3 = dict(P.evaluate(pos, mid, {}, [], d)[0])
    assert "baisse20" in ev3 and "une seule séance" in ev3["baisse20"], ev3


@case("Date du jour en texte : le rappel des 6 mois part quand même (jusqu'au 04/11/2026, jamais envoyé)")
def _():
    pos = {"isin": "FR0000120271", "price": 50.0, "date": "2026-04-01", "target": None, "stop": None}
    rows = [["2026-04-01", 0, 0, 0, 50.0, 0], ["2026-10-05", 0, 0, 0, 55.0, 0]]
    assert "6mois" in {k for k, _ in P.evaluate(pos, rows, {}, [], "2026-10-05")[0]}
    assert "6mois" in {k for k, _ in P.evaluate(pos, rows, {}, [], date(2026, 10, 5))[0]}
    assert "6mois" not in {k for k, _ in P.evaluate(pos, rows, {}, [], "2026-09-01")[0]}


@case("Lecture Gmail : objets d'abord (par lots), message entier seulement pour positions et plans ; réf. avec « & »")
def _():
    from email.message import EmailMessage

    def mk(subject, body=""):
        m = EmailMessage()
        m["Subject"], m["From"], m["Date"] = subject, "moi@example.com", "Mon, 05 Oct 2026 18:00:00 +0000"
        m.set_content(body)
        return m.as_bytes()

    box = {b"1": mk("[Euro Signal] Position FR0000120271", "Prix d'achat : 50\nDate d'achat : 2026-10-01"),
           b"2": mk("[Euro Signal] 📣 Bond du jour : Saipem SpA (+12 % sur gros volume)", "x" * 50000),
           b"3": mk("[Euro Signal] Revente — Total : 6 mois (réf. FR0000120271:20261001:6mois)"),
           b"4": mk("[Euro Signal] Plan — M&G : entrée (réf. plan:M&G.L:entree)"),
           b"5": mk("[Euro Signal] Surveiller VOLV-B.ST", "Entrée ajustée : 250")}

    class FakeIMAP:
        def __init__(self):
            self.full, self.head_calls = [], 0

        def list(self):
            return "OK", [b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']

        def select(self, folder, readonly=False):
            assert readonly
            return "OK", [b"5"]

        def search(self, charset, crit):
            return "OK", [b" ".join(sorted(box))]

        def fetch(self, mset, spec):
            if "HEADER.FIELDS" in spec:
                self.head_calls += 1
                out = []
                for mid in mset.split(b","):
                    raw = box[mid]
                    head = raw.split(b"\n\n", 1)[0] + b"\n\n"
                    out += [(mid + b" (BODY[HEADER.FIELDS (SUBJECT DATE)] {%d}" % len(head), head), b")"]
                return "OK", out
            self.full.append(mset)
            return "OK", [(mset + b" (RFC822 {%d}" % len(box[mset]), box[mset]), b")"]

    im = FakeIMAP()
    positions, refs, watches = P.read_positions(im)
    assert im.head_calls == 1, im.head_calls
    assert sorted(im.full) == [b"1", b"5"], im.full
    assert [p["isin"] for p in positions] == ["FR0000120271"] and positions[0]["price"] == 50.0, positions
    assert positions[0]["sentAt"].startswith("2026-10-05"), positions[0]["sentAt"]
    assert refs == {"FR0000120271:20261001:6mois", "plan:M&G.L:entree"}, refs
    assert [w["isin"] for w in watches] == ["VOLV-B.ST"], watches
    assert P.one_line("[Euro Signal] Revente — ACME\r\nSA : 6 mois") == "[Euro Signal] Revente — ACME SA : 6 mois"

@case("📑 Nouveaux comptes d'une position : signalés 10 jours au plus après leur relevé, jamais sans « pub » ; conseil sans IA")
def _():
    c = {"per": "2026-09-30", "nat": "trimestre", "at": "2026-11-25", "pub": "2026-11-24", "res": "CA en recul de 11 %.", "f": ["trésorerie nette"],
         "w": ["perte au trimestre"], "i": "down", "a": "mit", "al": "Dette en hausse"}
    t = P.comptes_event(c, date(2026, 11, 25))
    for s in ("Nouveaux comptes (trimestre clos le 30/09/2026), lus par l'IA le 25/11/2026.", "baisse possible", "avis sur les comptes : mitigé",
              "Points forts : trésorerie nette", "Points faibles : perte au trimestre", "⚠️ Dette en hausse",
              "Conseil : Point d'alerte : à vérifier avant d'acheter ou de garder (la règle testée reste la référence)."):
        assert s in t, (s, t)
    assert P.comptes_event(c, date(2026, 12, 6)) is None, "plus de 10 jours"
    assert P.comptes_event(dict(c, pub=None), date(2026, 11, 25)) is None, "lecture sans nouvelle publication"
    assert P.comptes_event(dict(c, pub="xx"), date(2026, 11, 25)) is None and P.comptes_event(dict(c, a="?"), date(2026, 11, 25)) is None
    assert P.comptes_conseil({"a": "fav"}) == "Rien dans ces comptes qui contredise la règle testée."
    import re as _re
    js = (Path(__file__).resolve().parent / "core.js").read_text(encoding="utf-8")
    for txt in (P.comptes_conseil({"a": "def"}), P.comptes_conseil({"a": "fav"})):  # même conseil dans la page, les emails et ici
        assert txt.replace("'", "\\'") in js or txt in js, txt
    assert _re.search(r"ref = \"comptes:%s:%s\"", (Path(__file__).resolve().parent / "positions.py").read_text(encoding="utf-8"))


@case("🧾 Ordres de la semaine : arrondis, parts en % (70 / 30, lignes égales), lignes en attente, détenues, ventes, protections")
def _():
    assert P.sig3(27.68 * 1.02, True) == 28.3 and P.sig3(13720 * 1.02, True) == 14000 and P.sig3(0.512 * 1.02, True) == 0.523
    assert P.sig3(0.7 * 28.3, False) == 19.8 and P.sig3(0.7 * 337, False) == 235 and P.sig3(0, True) is None
    assert P.px_txt(14000) == "14 000" and P.px_txt(28.3) == "28,3" and P.px_txt(0.523) == "0,523" and P.px_txt(337) == "337"
    a = P.allocation([{"key": k, "icon": ic} for k, ic in (("A", "🎯"), ("B", "🎯"), ("C", "📣"), ("D", "🎯"), ("E", "🎯"), ("F", "💎"), ("G", "💎"))])
    assert a == {"A": 14, "B": 14, "C": 14, "D": 14, "E": 14, "F": 15, "G": 15}, a
    a = P.allocation([{"key": k, "icon": "🎯"} for k in "ABC"])
    assert sum(a.values()) == 100 and sorted(a.values()) == [33, 33, 34], a
    assert P.allocation([{"key": "F", "icon": "💎"}]) == {"F": 100} and P.allocation([]) == {}
    buys = [{"icon": "🎯", "name": "JCDecaux", "key": "FR0000077919", "isin": "FR0000077919", "sym": "DEC.PA", "cur": "EUR", "last": 27.68,
             "lastDay": "2026-11-23"},
            {"icon": "📣", "name": "Bonesupport", "key": "SE0009858152", "isin": "SE0009858152", "sym": "BONEX.ST", "cur": "SEK", "last": 330.2,
             "lastDay": "2026-11-23"},
            {"icon": "💎", "name": "Lotus Bakeries", "key": "LOTB.BR", "isin": None, "sym": "LOTB.BR", "cur": "EUR", "last": 13720,
             "lastDay": "2026-11-23"}]
    waits = [{"icon": "🎯", "name": "Frontline", "key": "FRO.OL", "sym": "FRO.OL", "cur": "NOK", "last": 460.6, "lastDay": "2026-11-23"}]
    prots = [{"name": "Husqvarna B", "cur": "SEK", "stop": 42.0, "stopPct": 30, "buy": 60.0, "date": "2026-10-02", "div": "2026-11-20"}]
    sells = [{"name": "Vusion", "why": "6 mois depuis l'achat du 20/05/2026 (+12,0 %) et plus dans le 🎯 ni le 💎"}]
    subj, body = P.orders_email("2026-W48", "2026-11-23", buys, waits, ["Repsol"], sells, prots, {"SEK": 11.2, "NOK": 10.7},
                                date(2026, 11, 23), "https://x.github.io/insider-pea/euro-signal.html")
    assert subj == "[Euro Signal] 🧾 Ordres de la semaine (2026-W48) : 3 achats, 1 en attente, 1 vente (réf. ordres:2026-W48)", subj
    for s in ("70 % pour le 🎯 et le 📣, 30 % pour le 💎 (dosage conseillé), lignes égales dans chaque groupe",
              "Part : 24 % de l'enveloppe de la semaine. Achat à cours limité à 28,3 € au plus (dernier cours 27,68 € le 23/11/2026 + 2 %), "
              "valable jusqu'au vendredi 27/11/2026.",
              "Part : 23 % de l'enveloppe de la semaine. Achat à cours limité à 337 SEK au plus", "1 € = 11,2 SEK", "Nasdaq Stockholm",
              "Part : 30 % de l'enveloppe de la semaine. Achat à cours limité à 14 000 € au plus",
              "Protection : seuil à 19,8 €", "Pas d'ordre stop chez le courtier", "Euronext Paris — FR0000077919 — DEC.PA",
              "Frontline — Euronext Oslo : part réservée 23 % ; ordres prêts pour le feu vert : achat à 470 NOK au plus, puis protection à 329 NOK",
              "DÉJÀ EN PORTEFEUILLE (d'après vos emails « Je l'ai acheté ») : Repsol", "• Vusion : 6 mois", "vendre toute la ligne",
              "SEUILS DE PROTECTION DE VOS LIGNES", "Husqvarna B : seuil 42,0 SEK (30 % sous votre prix d'achat de 60,00 SEK le 02/10/2026).",
              "#FR0000077919", "#co=LOTB.BR", "Euro Signal ne passe aucun ordre", "Pourquoi des lignes égales : testé sur 25 ans", "1,8 point par an de plus",
              "Pourquoi pas d'ordre stop chez le courtier : testé sur 25 ans"):
        assert s in body, (s, body)
    assert "actions à" not in body and "MONTANT" not in body and "ordre stop de vente" not in body and "dividende détaché" not in body, body
    # ordre stop chez le courtier (réglage « ordres.stopCourtier ») : consignes et rappel après un dividende
    _, b2 = P.orders_email("2026-W48", "2026-11-23", buys, [], [], [], prots, {}, date(2026, 11, 27), "", stop_order=True)
    for s in ("ordre stop de vente (à seuil de déclenchement) sur toutes les actions achetées, seuil 19,8 €", "vendredi 04/12/2026",
              "PROTECTIONS EN PLACE", "⚠️ dividende détaché le 20/11/2026", "+19,3 % par an"):
        assert s in b2, (s, b2)
    assert P.orders_email("2026-W48", "2026-11-23", [], [], ["Repsol"], [], [dict(prots[0], div=None)], {}, date(2026, 11, 23), "") is None
    assert P.orders_email("2026-W48", "2026-11-23", [], [], [], [], prots, {}, date(2026, 11, 23), "") is None, "dividende sans ordre stop"
    assert P.orders_email("2026-W48", "2026-11-23", [], [], [], [], prots, {}, date(2026, 11, 23), "", stop_order=True), "ordre à reposer"
    assert P.orders_config()["stopCourtier"] is False and P.orders_config()["margeLimite"] == 0.02, "réglage par défaut du dépôt"


@case("🧾 Ordres de la semaine : une fois par sélection, lignes déjà détenues retirées, sélection trop ancienne ignorée")
def _():
    dash = {"rank": {"selection": {"week": "2026-W48", "items": [{"key": "FR0000077919", "isin": "FR0000077919", "sym": "DEC.PA", "name": "JCDecaux",
                                                                  "cur": "EUR", "m10": 3.1},
                                                                 {"key": "ES0173516115", "isin": "ES0173516115", "sym": "REP.MC", "name": "Repsol",
                                                                  "cur": "EUR", "m10": -1.2}]},
                     "rows": [{"key": "SE0001662230", "isin": "SE0001662230", "sym": "HUSQ-B.ST", "name": "Husqvarna B", "cur": "SEK"}],
                     "value10": ["SE0001662230", "XX"]},
            "fx": {"SEK": 11.2}, "cfg": {}}
    state = {"rankSelections": {"2026-W48": {"date": "2026-11-23", "items": [{"key": "FR0000077919", "name": "JCDecaux"},
                                                                            {"key": "ES0173516115", "name": "Repsol", "bd": 1}]}}}
    prices = {k: {"rows": [["2026-11-23", 1, 1, 1, v, 1]]} for k, v in (("FR0000077919", 27.68), ("ES0173516115", 27.82), ("SE0001662230", 60.6))}
    held = [{"isin": "SE0001662230", "price": 60.0, "date": "2026-10-02"}]
    om = P.weekly_orders(dash, state, prices, held, [], set(), date(2026, 11, 23))
    assert om and "ordres:2026-W48" in om[0], om
    assert "JCDecaux" in om[1] and "EN ATTENTE" in om[1] and "📣 Repsol" in om[1] and "DÉJÀ EN PORTEFEUILLE" in om[1] and "Husqvarna B" in om[1], om[1]
    assert "Part : 50 %" in om[1] and "part réservée 50 %" in om[1], om[1]  # 💎 détenu, l'autre sans cours : tout au 🎯 et au 📣
    assert "100 % pour les lignes de la semaine" in om[1] and "pas de part attribuée" in om[1], om[1]
    assert P.weekly_orders(dash, state, prices, held, [], {"ordres:2026-W48"}, date(2026, 11, 24)) is None, "déjà envoyé"
    assert P.weekly_orders(dash, state, prices, held, [], set(), date(2026, 12, 1)) is None, "sélection de la semaine passée"
    assert P.weekly_orders({"rank": {}}, state, prices, held, [], set(), date(2026, 11, 23)) is None
    assert P.REF_RE.findall(om[0]) == ["ordres:2026-W48"], "la référence doit être relue dans les Envoyés"

if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
