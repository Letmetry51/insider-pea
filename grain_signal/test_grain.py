"""
Tests hors ligne de Grain Signal (lecture des pages, indicateurs, séries continues, comité, sécurité du rapport).

  python grain_signal/test_grain.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import collect  # noqa: E402
import comite  # noqa: E402
import indicators as ind  # noqa: E402

results = []


def check(cond, name):
    results.append(("OK  " if cond else "ÉCHEC", name))


# ------------------------------------------------------------------ lecture des nombres et des échéances
check(collect.num("613,75€/t") == 613.75, "nombre français avec €/t")
check(collect.num("-7,25 €/t") == -7.25, "variation négative")
check(collect.num("1 234,5") == 1234.5, "séparateur de milliers")
check(collect.num("=") is None, "pas de nombre")
check(collect.maturity("déc. 2026") == "2026-12", "échéance « déc. 2026 »")
check(collect.maturity("Mars 2027") == "2027-03", "échéance « Mars 2027 »")
check(collect.maturity("12/2026") == "2026-12", "échéance « 12/2026 »")
check(collect.maturity("Fév 27") == "2027-02", "échéance « Fév 27 »")
check(collect.maturity("Rouen Rendu") is None, "un lieu n'est pas une échéance")

# ------------------------------------------------------------------ page de cotations à terme (structure terre-net, 2 lignes par échéance)
FUT = """<html><body><p>Mis à jour le : 6 novembre 2026 à 20:14</p><table>
<tr><th>Echéance</th><th>Dernier</th><th>+/-</th><th>Volume</th><th>Achat</th><th>Qté achat</th><th>+ Haut</th><th>Compensation</th></tr>
<tr><th>Heure</th><th>Vol. Jour</th><th>Vente</th><th>Qté vente</th><th>+ Bas</th><th>P.O.</th></tr>
<tr><td>déc. 2026</td><td>225,75</td><td>+2,50</td><td>12 345</td><td>225,50</td><td>10</td><td>226,25</td><td>225,50</td></tr>
<tr><td>18:29</td><td>20 000</td><td>225,75</td><td>5</td><td>218,50</td><td>210 000</td></tr>
<tr><td>mars 2027</td><td>223,25</td><td>+1,00</td><td>5 000</td><td>223,00</td><td>4</td><td>223,75</td><td>223,00</td></tr>
<tr><td>18:29</td><td>8 000</td><td>223,25</td><td>2</td><td>218,25</td><td>120 000</td></tr>
</table></body></html>"""
got = collect.parse_futures(FUT)
check(got == {"2026-12": 225.5, "2027-03": 223.0}, f"compensations lues ({got})")
check(collect.parse_date_fr(FUT, None).isoformat() == "2026-11-06", "date de séance « Mis à jour le »")

PHY = """<div>06 novembre</div><div>Urée (prix en €/t)</div><table><tr><th>Place</th><th>Cotation précédente</th><th>Cotation</th><th>Variation</th></tr>
<tr><td>Port Départ Contenu réservé aux abonnés</td><td>621€/t</td><td><b>613,75€/t</b></td><td>-7,25 €/t</td></tr></table>"""
pp = collect.parse_place_prices(PHY)
check(len(pp) == 1 and pp[0]["prix"] == 613.75 and pp[0]["place"] == "Port Départ", f"prix engrais lu ({pp})")
from datetime import date  # noqa: E402

check(collect.day_month(pp[0]["titre"], date(2026, 11, 7)) == date(2026, 11, 6), "date « 06 novembre » au-dessus de la table")
check(collect.day_month("30 décembre", date(2026, 1, 3)) == date(2025, 12, 30), "date de fin d'année lue au début de l'année suivante")

check(collect.num("225.50") == 225.5 and collect.num("+1.25") == 1.25, "nombre à point décimal (pages en anglais)")
check(collect.num("1.234") == 1234 and collect.num("12 345") == 12345, "séparateurs de milliers")
NOCOL = FUT.replace("Compensation", "Clôture")
check(collect.parse_futures(NOCOL) == {}, "colonne « compensation » absente : aucune valeur inventée")
from datetime import datetime as _dt, timezone as _tz  # noqa: E402

check(collect.date_seance(None, _dt(2026, 11, 7, 4, 47, tzinfo=_tz.utc)).isoformat() == "2026-11-06", "sans date lue : dernière séance close")
check(collect.date_seance(date(2026, 11, 9), _dt(2026, 11, 9, 4, 47, tzinfo=_tz.utc)).isoformat() == "2026-11-06",
      "date du jour le matin (séance pas close) : ramenée à la séance précédente")
check(collect.parse_date_fr("Mis à jour le 06/11/2026 à 18h30", None).isoformat() == "2026-11-06", "date au format jj/mm/aaaa")

# ------------------------------------------------------------------ indicateurs
# RSI de Wilder : valeur de référence (amorçage par la moyenne simple des 14 premières variations)
_x = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
_r = ind.rsi(_x)
_d = [b - a for a, b in zip(_x, _x[1:])]
_g, _l = sum(max(v, 0) for v in _d[:14]) / 14, sum(max(-v, 0) for v in _d[:14]) / 14
_ref14 = 100 - 100 / (1 + _g / _l)
for v in _d[14:]:
    _g, _l = (_g * 13 + max(v, 0)) / 14, (_l * 13 + max(-v, 0)) / 14
_ref19 = 100 - 100 / (1 + _g / _l)
check(abs(_r[14] - _ref14) < 1e-9 and abs(_r[19] - _ref19) < 1e-9 and _r[13] is None,
      f"RSI de Wilder conforme au calcul de référence ({_r[14]:.2f}, {_r[19]:.2f})")
up = [100 + i for i in range(40)]
r = ind.rsi(up)
check(r[-1] == 100.0, "RSI d'une hausse continue = 100")
m, s, hh = ind.macd(up)
check(m[-1] > 0 and hh[-1] is not None, "MACD positif en hausse")
check(ind.sma([1, 2, 3, 4], 2)[-1] == 3.5, "moyenne mobile")
a = ind.analyse([f"d{i}" for i in range(40)], up)
check(a["rsi"] == 100.0 and a["haut3m"] == 139 and a["fibo"]["sens"] == "hausse", "tableau technique complet")
check(ind.feu_execution({"rsi": 25, "boll_pb": 0.1, "dernier": 1, "haut3m": 2, "bas3m": 0.5})["code"] == "attendre", "pas de vente en survente")
check(ind.feu_execution({"rsi": 75, "boll_pb": 0.9, "croisement_macd": {"sens": "baissier"}, "dernier": 2, "haut3m": 2, "bas3m": 1})["code"] == "accelerer",
      "accélérer en surachat qui s'essouffle")
check(ind.analyse(["a"] * 10, list(range(10))).get("insuffisant"), "moins de 30 séances : insuffisant")
nv = ind.niveaux({"dernier": 225.5, "mm20": 233.81, "fibo": {"38.2": 232.65, "50": 235.62, "61.8": 238.6}, "haut3m": 248.25, "bas3m": 223.0})
check(nv["ordres"][0] > 225.5 and nv["revision"] < 223.0, f"ordres au-dessus du cours, révision sous le plus bas ({nv})")

# ------------------------------------------------------------------ série continue : raccord ajusté
rows = [{"date": "2026-10-29", "product": "ECO", "maturity": "2026-11", "settle": "528.75"},
        {"date": "2026-10-30", "product": "ECO", "maturity": "2026-11", "settle": "527.5"},
        {"date": "2026-10-30", "product": "ECO", "maturity": "2027-02", "settle": "555.25"},
        {"date": "2026-11-02", "product": "ECO", "maturity": "2027-02", "settle": "546"}]
d, v, ref, rac, curve = build.continuous(rows, "ECO")
check(ref == "2027-02" and rac and rac[0]["ajustement"] == 27.75, f"raccord nov.→févr. ajusté de +27,75 ({rac})")
check(abs(v[0] - (528.75 + 27.75)) < 1e-9, "série ajustée en arrière")
check(build.expiry("EBM", "2026-12").isoformat() == "2026-12-10", "expiration blé : le 10 du mois")
check(build.expiry("ECO", "2027-02").isoformat() == "2027-01-29", "expiration colza : dernier jour ouvré du mois précédent")
check(build.matrix(-1.2) == "VENDRE" and build.matrix(0.6) == "ATTENDRE" and build.matrix(0) == "TENIR", "matrice de décision")
check(build.cot_score(10) == 1.5 and build.cot_score(90) == -1.5, "lecture des fonds à contre-courant")

# ------------------------------------------------------------------ comité : sortie machine et sécurité du rapport
TXT = """# Rapport
Texte <script>alert(1)</script> et [lien piégé](javascript:alert(1)) et [source](https://example.com/a).
```json
{"resume": "R", "cultures": {"ble": {"signal": "tenir", "score": 0.1, "ordres": [233]}, "colza": {"signal": "INVENTÉ"}},
 "engrais": {"signal": "FRACTIONNER"}, "declencheurs": [{"contrat": "EBM", "sens": "<", "niveau": 218, "texte": "x"},
 {"contrat": "XXX", "sens": "<", "niveau": 1}], "calendrier": [{"date": "2026-11-10", "evenement": "WASDE"}]}
```"""
dec, rep = comite.parse_decision(TXT)
check(dec["cultures"]["ble"]["signal"] == "TENIR" and "colza" not in dec["cultures"], "signaux du comité validés")
check(len(dec["declencheurs"]) == 1 and dec["engrais"]["signal"] == "FRACTIONNER", "déclencheurs et engrais validés")
hs = comite.safe_html(rep)
check("<script" not in hs and "javascript:" not in hs.lower(), "rapport sans script ni lien javascript")
check('href="https://example.com/a"' in hs, "lien https conservé")

# ------------------------------------------------------------------ calcul complet sur les historiques de départ (dossier temporaire)
tmp = Path(tempfile.mkdtemp())
try:
    (tmp / "grain_signal").mkdir()
    for f in ("build.py", "indicators.py", "decisions.py", "config.json", "comite.py", "send_alerts.py"):
        shutil.copy(HERE / f, tmp / "grain_signal" / f)
    shutil.copytree(HERE / "seed", tmp / "grain_signal" / "seed")
    priv = tmp / "data" / "grain" / "prive"
    priv.mkdir(parents=True)
    for f in ("euronext.csv", "wb_monthly.csv", "fert_fr.csv"):
        shutil.copy(HERE / "seed" / f, priv / f)
    env = dict(os.environ, GS_TODAY="2026-11-07", GS_DRY="1")
    p = subprocess.run([sys.executable, str(tmp / "grain_signal" / "build.py")], capture_output=True, text=True, env=env)
    check(p.returncode == 0, "calcul complet sur les historiques de départ" + ("" if p.returncode == 0 else " : " + p.stderr[-400:]))
    if p.returncode == 0:
        dash = json.loads((tmp / "data" / "grain" / "grain-signal.json").read_text(encoding="utf-8"))
        check(set(dash["cultures"]) == {"ble", "escourgeon", "orge_printemps", "colza", "mais"}, "cinq cultures")
        check(dash["cultures"]["ble"]["source"] == "comite", "comité de départ appliqué")
        check(dash["orges"]["escourgeon"]["prime"] == -6.25 and dash["orges"]["orge_printemps"]["prix"] == 234.25,
              "orges brassicoles : prix physique et prime sur la fourragère")
        pl = dash["cultures"]["ble"]["plan"]
        check([(x["recolte"], x["pct"]) for x in pl] == [(2026, 15), (2027, 10)], f"plan de vente du blé au 07/11/2026 ({pl})")
        check(pl[1].get("ordre") == 228.0, "ordre de la récolte 2027 décalé de l'écart entre échéances (235,5 − 7,5)")
        check(all(sum(t[2] for t in v["tranches"]) == 100 for v in dash["config"]["calendrier"].values()), "calendriers à 100 %")
        check(dash["engrais"].get("signal") in ("ACHETER_LARGE", "SUIVRE", "FRACTIONNER", "ATTENDRE"), "décision engrais")
        st_ = dash["contrats"]["EBM"].get("stockage") or {}
        check(st_.get("code") in ("stocker", "vendre", "neutre") and st_.get("reference") == "2026-12",
              f"stocker ou vendre calculé sur la courbe du blé ({st_.get('texte')})")
        cb_ = dash["carnet"]["entrees"]
        check(len(cb_) == 6 and {x["cle"] for x in cb_} == {"ble", "escourgeon", "orge_printemps", "colza", "mais", "engrais"},
              "carnet de bord : avis du comité de départ notés (5 cultures et l'azote)")
        check("meteo" in dash["cultures"]["ble"]["composantes"], "note météo dans les composantes du score")
        p2 = subprocess.run([sys.executable, str(tmp / "grain_signal" / "send_alerts.py")], capture_output=True, text=True, env=env)
        check(p2.returncode == 0, "emails en simulation")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ------------------------------------------------------------------ tests de résistance (données vides, corrompues, relances)
def run_build(setup, today="2026-11-07", twice=False):
    t = Path(tempfile.mkdtemp())
    try:
        (t / "grain_signal").mkdir()
        for f in ("build.py", "indicators.py", "decisions.py", "config.json"):
            shutil.copy(HERE / f, t / "grain_signal" / f)
        shutil.copytree(HERE / "seed", t / "grain_signal" / "seed")
        pv = t / "data" / "grain" / "prive"
        pv.mkdir(parents=True)
        setup(t, pv)
        env = dict(os.environ, GS_TODAY=today)
        outs = []
        for _ in range(2 if twice else 1):
            r = subprocess.run([sys.executable, str(t / "grain_signal" / "build.py")], capture_output=True, text=True, env=env)
            dash = json.loads((t / "data" / "grain" / "grain-signal.json").read_text(encoding="utf-8")) if r.returncode == 0 else None
            box = json.loads((pv / "a-envoyer.json").read_text(encoding="utf-8")) if (pv / "a-envoyer.json").exists() else []
            outs.append((r.returncode, dash, box, r.stderr[-300:]))
        return outs
    finally:
        shutil.rmtree(t, ignore_errors=True)


def seeds(t, pv):
    for f in ("euronext.csv", "wb_monthly.csv", "fert_fr.csv", "physique_hist.csv"):
        shutil.copy(HERE / "seed" / f, pv / f)


def empty_seed(t, pv):  # aucune donnée, même pas les historiques de départ
    for f in (t / "grain_signal" / "seed").glob("*"):
        f.unlink()


(rc, dash, _, err), = run_build(empty_seed)
check(rc == 0 and dash is not None, "calcul sans aucune donnée : pas de plantage" + ("" if rc == 0 else " : " + err))


def corrupt(t, pv):
    seeds(t, pv)
    (pv / "yahoo.json").write_text("{pas du json", encoding="utf-8")
    (pv / "cftc.json").write_text("[]", encoding="utf-8")
    (t / "data" / "grain" / "comite.json").write_text(json.dumps({
        "date": "2026-11-07", "cultures": {"ble": {"signal": "TENIR", "score": "abc", "ordres": ["x", None, 230]},
                                            "colza": {"signal": "N'IMPORTE"}},
        "declencheurs": [{"contrat": "EBM", "sens": ">", "niveau": "nan"}, "texte"], "engrais": "rien"}), encoding="utf-8")
    with (pv / "euronext.csv").open("a", encoding="utf-8") as fh:
        fh.write("2026-11-06,EBM,2027-03,nan\n2026-11-06,EBM,2027-05,\n")


(rc, dash, _, err), = run_build(corrupt)
check(rc == 0 and dash is not None, "calcul avec fichiers corrompus (Yahoo illisible, comité malformé, prix vides)" + ("" if rc == 0 else " : " + err))
if dash:
    check(dash["cultures"]["ble"]["niveaux_retenus"]["ordres"] == [230.0], "ordres du comité nettoyés (valeurs non numériques ignorées)")
    check(dash["cultures"]["colza"]["source"] != "comite", "signal du comité invalide ignoré")


def one_row(t, pv):
    (pv / "euronext.csv").write_text("date,product,maturity,settle\n2026-11-06,EBM,2026-12,225.5\n", encoding="utf-8")


(rc, dash, _, err), = run_build(one_row)
check(rc == 0 and dash["contrats"]["EBM"]["technique"].get("insuffisant"), "une seule séance Euronext : indicateurs marqués insuffisants")

runs = run_build(seeds, twice=True)
check(all(r[0] == 0 for r in runs), "deux calculs le même jour")
if all(r[0] == 0 for r in runs):
    ids = [x["id"] for x in runs[1][2]]
    check(len(ids) == len(set(ids)), "pas d'alerte en double après un second calcul le même jour")
    check(runs[1][1]["declencheurs"] == [], "pas de nouveau déclencheur sans nouvelle séance")

def roll_colza(t, pv):  # changement d'échéance colza nov. → févr. le 02/11 ; comité du 29/10 avec un ordre à 540 sur nov.
    seeds(t, pv)
    (t / "data" / "grain" / "comite.json").write_text(json.dumps({
        "date": "2026-10-29", "modele": "test", "references": {"ECO": "2026-11"},
        "cultures": {"colza": {"signal": "TENIR", "score": 0, "ordres": [540], "revision_bas": 500}},
        "declencheurs": [{"contrat": "ECO", "sens": ">", "niveau": 540, "texte": "ordre"}]}), encoding="utf-8")
    (t / "data" / "grain" / "etat.json").write_text(json.dumps({"contrats": {"ECO": {"seance": "2026-10-30", "dernier": 527.5}}}), encoding="utf-8")


(rc, dash, box, err), = run_build(roll_colza, today="2026-11-03")
if rc == 0:
    nr = dash["cultures"]["colza"]["niveaux_retenus"]
    check(nr["revision"] == 527.75 and nr.get("decalage_echeance") == 27.75, f"niveaux du comité décalés après le changement d'échéance ({nr})")
    check(not any(":niveau:" in x["id"] for x in dash["declencheurs"]), "pas de faux « niveau franchi » le jour du changement d'échéance")
else:
    check(False, "scénario de changement d'échéance : " + err)


def comite_change(t, pv):
    seeds(t, pv)
    (t / "data" / "grain" / "etat.json").write_text(json.dumps({"signaux": {"ble": "VENDRE", "escourgeon": "VENDRE"}}), encoding="utf-8")


(rc, dash, _, err), = run_build(comite_change)
ids = [x["id"] for x in (dash or {}).get("declencheurs", [])]
check(rc == 0 and any(i.endswith("ble:signal") for i in ids) and any(i.endswith("escourgeon:signal") for i in ids),
      "changement de signal signalé pour toutes les cultures, orges comprises")

def wb_octobre(t, pv):  # chiffre Banque mondiale d'octobre, aucun relevé France en octobre : interpolation au 15
    seeds(t, pv)
    with (pv / "wb_monthly.csv").open("a", encoding="utf-8") as fh:
        fh.write("2026-10,,420.0,,,317.0,\n")


(rc, dash, _, err), = run_build(wb_octobre)
est = (dash or {}).get("engrais", {}).get("estimation") or {}
check(rc == 0 and "interpolée au 15 entre 555 le 30/09 et 621 le 05/11" in est.get("methode", ""), f"ratio engrais : urée interpolée au milieu du mois ({est})")

for day in ("2027-01-02", "2027-06-30", "2027-07-01", "2027-12-31"):
    (rc, dash, _, err), = run_build(seeds, today=day)
    ok = rc == 0 and all(sum(1 for p in c["plan"] if p["statut"] == "due") <= 2 for c in dash["cultures"].values())
    check(ok, f"plan de vente au {day} (passage d'année, moisson)" + ("" if rc == 0 else " : " + err))

# ------------------------------------------------------------------ backtest : prix constant → toutes les stratégies au même prix
import backtest as bt  # noqa: E402
from datetime import timedelta as _td  # noqa: E402

_d0, _ds = date(2015, 1, 1), []
while _d0 < date(2019, 12, 31):
    if _d0.weekday() < 5:
        _ds.append(_d0.isoformat())
    _d0 += _td(days=1)
_p = [200.0] * len(_ds)
_r = bt.campagne(_p, bt.indicateurs(_p), bt.ym_idx(_ds), 2017, [list(t) for t in bt.CFG["calendrier"]["ble"]["tranches"]], 7,
                 {"rsi": 40, "pos": 20})
check(_r and all(abs(v - 200) < 1e-6 for v in _r.values()), f"backtest : prix constant, toutes les stratégies à 200 €/t ({_r})")
_p2 = [100 + i * 0.05 for i in range(len(_ds))]  # hausse régulière : vendre tout à la moisson doit être battu par l'étalement
_r2 = bt.campagne(_p2, bt.indicateurs(_p2), bt.ym_idx(_ds), 2017, [list(t) for t in bt.CFG["calendrier"]["ble"]["tranches"]], 7,
                  {"rsi": 40, "pos": 20})
check(_r2 and _r2["S1"] > _r2["S0"], "backtest : marché haussier, la vente étalée bat la vente à la moisson")

# ---------------------------------------------------------------- COT Euronext (tableau du rapport hebdomadaire)
_rr = ["52", "270", "0", "0", "0", "0", "185 796.15", "344 744.46", "0", "0"]
_ot = ["172 644.28", "166 309.95", "121 518.82", "5 175.75", "127 540.71", "78 075.64", "51 059.05", "93 017.99", "0", "0"]
_tot = [f"{collect.cot_num(a) + collect.cot_num(b):,.2f}".replace(",", " ") for a, b in zip(_rr, _ot)]
_rows = [["", "Long", "Short"] * 3, ["Number of positions"], ["Risk Reducing directly related to commercial activities", *_rr],
         ["Other", *_ot], ["Total", *_tot], ["Changes (+/-)"], ["Risk Reducing", *["0"] * 10], ["Other", *["1 000"] * 10],
         ["Total", *["1 000"] * 10]]
_c = collect.parse_cot_rows("Report date: 19/11/2021 Publication date: 24/11/2021", _rows)
check(_c["date"] == "2021-11-19" and _c["fonds_long"] == 121519 and _c["fonds_short"] == 5176 and _c["net"] == 116343,
      f"COT Euronext : fonds d'investissement lus, milliers séparés par des espaces ({_c})")
check(collect.cot_num("1 234.5") == 1234.5 and collect.cot_num("12 34") is None and collect.cot_num("Long") is None,
      "COT Euronext : nombres (espace = milliers, point = décimales), texte rejeté")
_bad = [list(r) for r in _rows]
_bad[4] = ["Total", *(["1"] * 10)]
try:
    collect.parse_cot_rows("Report date: 19/11/2021", _bad)
    check(False, "COT Euronext : total incohérent rejeté")
except RuntimeError:
    check(True, "COT Euronext : total incohérent rejeté (rien n'est deviné)")
_ser = [{"date": f"2026-{1 + i // 4:02d}-{1 + (i % 4) * 7:02d}", "net": i * 100} for i in range(30)]
check(build.cot_reading(_ser[:10], mini=26)["indice"] is None and build.cot_reading(_ser, mini=26)["indice"] == 100,
      "COT Euronext : pas d'indice avant 26 semaines, indice 100 au plus haut")

# ---------------------------------------------------------------- pannes de source
_j1, _j2, _j3 = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)
_ko = {"x": {"ok": False, "detail": "HTTP 500"}, "y": {"ok": True}}
_e1, _m1 = build.suivi_pannes(_ko, {}, _j1)
_e1b, _m1b = build.suivi_pannes(_ko, _e1, _j1)  # second calcul le même jour : toujours un seul jour
_e2, _m2 = build.suivi_pannes(_ko, _e1b, _j2)
_e3, _m3 = build.suivi_pannes(_ko, _e2, _j3)
check(not _m1 and not _m1b and len(_m2) == 1 and "panne" in _m2[0][1] and not _m3,
      "pannes : alerte au 2e jour distinct, une seule fois par incident")
_e4, _m4 = build.suivi_pannes({"y": {"ok": True}}, _e3, _j3)  # x non interrogée ce jour-là
check(not _m4 and _e4.get("x") == _e3["x"], "pannes : source non interrogée, état gardé, pas de faux rétablissement")
_e5, _m5 = build.suivi_pannes({"x": {"ok": True}}, _e3, _j3)
check(len(_m5) == 1 and "rétablie" in _m5[0][1] and "x" not in _e5, "pannes : message au rétablissement, incident clos")

# ---------------------------------------------------------------- aides à la décision (decisions.py)
import decisions as dec  # noqa: E402

_c5 = [[f"w{i}", 100 + i] for i in range(200)]
_t = dec.thermometre(_c5)
check(_t["percentile"] == 100 and _t["min"] == 100 and _t["max"] == 299, f"thermomètre : prix au plus haut des 5 ans = 100e ({_t})")
check(dec.thermometre(_c5[:50]) is None, "thermomètre : rien sous 2 ans d'historique")
check(dec.pctile([1, 2, 3, 4], 2) == 50 and dec.pctile([], 1) is None, "percentile : rang dans la fenêtre")

_ds, _vs = [], []
_d0 = date(2000, 7, 1)
while _d0 < date(2020, 7, 1):
    _ds.append(_d0.isoformat())
    _vs.append(100 * (1.1 if _d0.month == 3 else 1.0))
    _d0 += _td(days=1)
_sp = dec.saisonnier(_ds, _vs, 7)
check(_sp and _sp["campagnes"] == 20 and _sp["plus_chers"][0] == 3 and _sp["mois"][2] > 8, f"saisonnalité : mars repéré comme le mois cher ({_sp and _sp['mois']})")


def _exp(m):
    return date(int(m[:4]), int(m[5:]), 10)


_cfg = {"fraisMensuels": 0.6, "tauxAnnuel": 4.0, "seuilGain": 3.0}
_s1 = dec.stockage({"2026-12": 220, "2027-03": 232, "2027-05": 236, "2027-09": 240}, "2026-12", _exp, date(2026, 11, 7), 7, _cfg)
check(_s1["code"] == "stocker" and all(o["echeance"] != "2027-09" for o in _s1["options"]),
      f"stocker ou vendre : report de +16 €/t → stocker, échéance de la nouvelle récolte exclue ({_s1['texte']})")
_s2 = dec.stockage({"2026-12": 220, "2027-03": 219, "2027-05": 218}, "2026-12", _exp, date(2026, 11, 7), 7, _cfg)
check(_s2["code"] == "vendre", "stocker ou vendre : déport → vendre plutôt que stocker")
_s3 = dec.stockage({"2027-09": 220, "2027-12": 230}, "2027-09", _exp, date(2027, 6, 20), 7, _cfg)
check(_s3["code"] == "nouvelle", "stocker ou vendre : échéance de la nouvelle récolte → pas de report sur l'ancienne")

_rows = [{"date": f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}", "page": "ble", "place": "Rouen Rendu", "prix": 200 + (i % 10)} for i in range(50)]
_pl = dec.prime_locale(_rows, [["ble", "Rouen Rendu"], ["ble", "Inconnue"]], lambda d_: 200.0)
check(_pl and _pl["places"][0]["jours"] == 50 and _pl["percentile"] is not None and len(_pl["places"]) == 1,
      f"prime locale : physique − Euronext, percentile après 40 relevés ({_pl and _pl.get('texte')})")
_pl2 = dec.prime_locale(_rows[:5], [["ble", "Rouen Rendu"]], lambda d_: 200.0)
check("percentile" not in _pl2 and "constitution" in _pl2["texte"], "prime locale : historique trop court annoncé")

_serie = {(date(2026, 9, 1) + _td(days=i)).isoformat(): 200 - i * 0.5 for i in range(80)}
_cb = []
check(dec.carnet_ajoute(_cb, "ble", "2026-09-01", "VENDRE", 200, "2026-09-01") and
      not dec.carnet_ajoute(_cb, "ble", "2026-09-02", "VENDRE", 200, "2026-09-01"), "carnet : un avis n'est noté qu'une fois")
dec.carnet_note(_cb[0], _serie, date(2026, 11, 20))
check(_cb[0]["s4"]["verdict"] == "bon" and _cb[0]["s4"]["gain"] == 14.0 and _cb[0]["s8"]["verdict"] == "bon",
      f"carnet : vendre avant une baisse = bon avis ({_cb[0]['s4']})")
_cw = [{"id": "a", "cle": "colza", "date": "2026-09-01", "signal": "ATTENDRE", "prix": 200}]
dec.carnet_note(_cw[0], _serie, date(2026, 10, 10))
check(_cw[0]["s4"]["verdict"] == "mauvais" and "variation" not in _cw[0]["s8"], "carnet : attendre avant une baisse = mauvais ; 8 semaines pas encore jugées")
_ce = [{"id": "e", "cle": "engrais", "date": "2026-09-01", "signal": "ATTENDRE", "prix": 200}]
dec.carnet_note(_ce[0], _serie, date(2026, 11, 20), engrais=True)
check(_ce[0]["s4"]["verdict"] == "bon", "carnet : azote, attendre avant une baisse = bon avis")

_today = date(2026, 11, 7)
_obs, _k = {}, _today - _td(days=4100)
while _k <= _today - _td(days=6):
    _obs[_k.isoformat()] = (2.0 if _k < _today - _td(days=80) else 0.4, 15.0)
    _k += _td(days=1)
_prev = {(_today + _td(days=i)).isoformat(): (0.4, 33.0) for i in range(-10, 14)}
_z = dec.meteo_zone(_obs, _prev, _today)
check(_z and _z["ratio"] == 0.2 and _z["chaleur14"] == 14 and dec.meteo_etat(_z)[1] == "très sec",
      f"météo : 60 jours à 20 % de la normale = très sec ({_z})")
_mc = {"zones": {"A": {"sensible": {"ble": [11]}, "chaleur": {"ble": [11]}}, "B": {"sensible": {"ble": [5]}}},
       "cultures": {"ble": {"A": 0.5, "B": 0.5}}}
_ms = dec.meteo_score({"A": _z, "B": {"ratio": 1.0, "chaleur14": 0}}, _mc, _today)
check(_ms["ble"]["score"] == round((0.5 * 2.3 + 0.5 * -0.3 * 0.25), 2), f"météo : note pondérée, hors saison au quart ({_ms['ble']})")

for st, name in results:
    print(st, name)
fails = [n for s, n in results if s != "OK  "]
print(f"{len(results) - len(fails)}/{len(results)} tests réussis")
sys.exit(1 if fails else 0)
