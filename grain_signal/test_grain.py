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

# ------------------------------------------------------------------ indicateurs
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
    for f in ("build.py", "indicators.py", "config.json", "comite.py", "send_alerts.py"):
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
        check(dash["engrais"].get("signal") in ("ACHETER_LARGE", "SUIVRE", "FRACTIONNER", "ATTENDRE"), "décision engrais")
        p2 = subprocess.run([sys.executable, str(tmp / "grain_signal" / "send_alerts.py")], capture_output=True, text=True, env=env)
        check(p2.returncode == 0, "emails en simulation")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

for st, name in results:
    print(st, name)
fails = [n for s, n in results if s != "OK  "]
print(f"{len(results) - len(fails)}/{len(results)} tests réussis")
sys.exit(1 if fails else 0)
