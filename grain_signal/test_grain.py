"""
Tests hors ligne de Grain Signal (lecture des pages, indicateurs, séries continues, comité, sécurité du rapport).

  python grain_signal/test_grain.py
"""
import json
import math
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
    for f in ("build.py", "indicators.py", "decisions.py", "config.json", "comite.py", "send_alerts.py", "rapport_pdf.py", "actualites.py"):
        shutil.copy(HERE / f, tmp / "grain_signal" / f)
    shutil.copytree(HERE / "seed", tmp / "grain_signal" / "seed")
    priv = tmp / "data" / "grain" / "prive"
    priv.mkdir(parents=True)
    for f in ("euronext.csv", "wb_monthly.csv", "fert_fr.csv"):
        shutil.copy(HERE / "seed" / f, priv / f)
    # actualités déjà collectées et classées (sans appel à l'API : classement en cache), indice géopolitique
    _arts = [{"id": "a1", "titre": "Russia halts wheat exports from Novorossiysk after drone strike", "url": "https://example.com/1",
              "date": "2026-11-07T04:00+00:00", "source": "Reuters", "langue": "en", "autres_sources": ["Bloomberg", "AFP"]},
             {"id": "a2", "titre": "Le blé Euronext recule encore", "url": "https://example.com/2", "date": "2026-11-06T16:00+00:00",
              "source": "Terre-net", "langue": "fr"},
             {"id": "a3", "titre": "Urea prices climb as Egypt gas cuts bite", "url": "https://example.com/3", "date": "2026-11-05T10:00+00:00",
              "source": "DTN", "langue": "en"},
             {"id": "a4", "titre": "Recette de la tarte aux pommes", "url": "https://example.com/4", "date": "2026-11-06T10:00+00:00",
              "source": "Web-agri", "langue": "fr"},
             {"id": "a5", "titre": "<script>alert(1)</script> canola", "url": "javascript:alert(1)", "date": "2026-11-06T10:00+00:00",
              "source": "X", "langue": "en"}]
    (priv / "actualites_brut.json").write_text(json.dumps({"articles": _arts}), encoding="utf-8")
    _cls = {"a1": {"pertinent": True, "titre_fr": "La Russie suspend ses exportations de blé à Novorossiisk après une attaque de drones",
                   "theme": "geopolitique", "nature": "fait", "importance": 3, "impacts": {"ble": 2, "orge": 1, "mais": 1, "colza": 0, "engrais": 0},
                   "horizon": "semaines", "impact": "Moins de blé russe : soutien pour vos ventes de blé", "doublon_de": None, "classe_le": "2026-11-07"},
            "a2": {"pertinent": True, "titre_fr": "Le blé Euronext recule encore", "theme": "marche", "nature": "fait", "importance": 1,
                   "impacts": {"ble": -1}, "horizon": "jours", "impact": "Séance en baisse", "doublon_de": None, "classe_le": "2026-11-07"},
            "a3": {"pertinent": True, "titre_fr": "L'urée monte avec les coupures de gaz en Égypte", "theme": "engrais", "nature": "fait",
                   "importance": 2, "impacts": {"engrais": 2}, "horizon": "semaines", "impact": "Azote plus cher : couvrir la tranche",
                   "doublon_de": None, "classe_le": "2026-11-07"},
            "a4": {"pertinent": False, "titre_fr": "Recette", "classe_le": "2026-11-07"},
            "a5": {"pertinent": True, "titre_fr": "<script>alert(1)</script>", "theme": "demande", "nature": "rumeur", "importance": 1,
                   "impacts": {"colza": 1}, "horizon": "jours", "impact": "x", "doublon_de": None, "classe_le": "2026-11-07"}}
    (priv / "actualites_classees.json").write_text(json.dumps(_cls), encoding="utf-8")
    _gj = [[f"{2014 + i // 365:04d}-{(i % 365) // 31 % 12 + 1:02d}-{i % 28 + 1:02d}", 100.0 + (i % 50)] for i in range(4000)]
    _gj = sorted({x[0]: x for x in _gj}.values())
    _gj += [["2026-11-0" + str(k), 400.0] for k in range(1, 7)]
    (priv / "gpr.json").write_text(json.dumps({"quotidien": _gj, "mensuel": {"RUS": [[f"{2015 + m // 12}-{m % 12 + 1:02d}", 1.0 + m / 100] for m in range(140)]},
                                               "evenements": [["2026-10-20", "Attack on port"]]}), encoding="utf-8")
    env = dict(os.environ, GS_TODAY="2026-11-07", GS_NOW="2026-11-07T06:00:00+00:00", GS_DRY="1", ANTHROPIC_API_KEY="")
    pa = subprocess.run([sys.executable, str(tmp / "grain_signal" / "actualites.py")], capture_output=True, text=True, env=env)
    ac_ = json.loads((tmp / "data" / "grain" / "actualites.json").read_text(encoding="utf-8")) if pa.returncode == 0 else {}
    check(pa.returncode == 0 and [a["id"] for a in ac_.get("articles", [])] == ["a1", "a2", "a5", "a3"],
          "actualités : titres classés publiés, non pertinents écartés" + ("" if pa.returncode == 0 else " : " + pa.stderr[-300:]))
    pr_ = ac_.get("pression") or {}
    check(len(ac_.get("historique") or []) == 1 and ac_["historique"][0]["date"] == "2026-11-07", "actualités : pression du jour gardée en historique")
    check(pr_.get("ble", {}).get("valeur", 0) > 0.5 and pr_["ble"]["baisse"] == 0 and pr_.get("engrais", {}).get("valeur", 0) > 0.3,
          f"actualités : pression haussière sur le blé (compte rendu de séance exclu), azote plus cher ({pr_.get('ble')}, {pr_.get('engrais')})")
    _box = json.loads((priv / "a-envoyer.json").read_text(encoding="utf-8")) if (priv / "a-envoyer.json").exists() else []
    _dem = json.loads((tmp / "data" / "grain" / "demande-comite.json").read_text(encoding="utf-8")) if (tmp / "data" / "grain" / "demande-comite.json").exists() else {}
    check(ac_.get("majeurs") == ["a1"] and any(x["id"] == "2026-11-07:actu:a1" and x["grave"] for x in _box)
          and any("Novorossiisk" in m for m in _dem.get("motifs", [])),
          "actualité majeure : alerte email et comité d'alerte demandés")
    pa2 = subprocess.run([sys.executable, str(tmp / "grain_signal" / "actualites.py")], capture_output=True, text=True, env=env)
    _box2 = json.loads((priv / "a-envoyer.json").read_text(encoding="utf-8"))
    check(pa2.returncode == 0 and len([x for x in _box2 if ":actu:" in x["id"]]) == 1, "actualité majeure : une seule alerte, même relancé")
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
        pb_ = dash["cultures"]["ble"]["niveaux_retenus"].get("probas") or {}
        check(len(pb_.get("ordres") or []) == len(dash["cultures"]["ble"]["niveaux_retenus"]["ordres"]) and pb_.get("horizon") == "2026-11-30"
              and all(0 <= x <= 100 for x in pb_["ordres"]), f"chances d'atteindre les ordres d'ici la fin de la tranche ({pb_})")
        check((dash["cultures"]["ble"].get("actualite") or {}).get("sens") == "haussière" and dash["cultures"]["escourgeon"].get("actualite")
              and (dash.get("actualites") or {}).get("majeurs") == 1, "actualités : pression reprise par culture dans le calcul du matin")
        g_ = dash.get("geopolitique") or {}
        check(g_.get("percentile", 0) >= 90 and g_.get("etat") == "très élevé" and g_.get("pays", [{}])[0].get("nom") == "Russie"
              and g_.get("evenements"), f"géopolitique : pic récent au-dessus de 10 ans d'historique, pays et événements ({ {k: g_.get(k) for k in ('mois', 'percentile', 'etat')} })")
        bi_ = dash["cultures"]["ble"].get("biais") or {}
        check(bi_.get("plus_haut") is not None and bi_.get("depuis") == "2026-07-01" and 0 <= (bi_.get("gagner5") or -1) <= 100,
              f"biais d'ancrage : plus haut de la campagne et chances de gagner ou perdre 5 € ({bi_})")
        hp = tmp / "synthese.html"
        p3 = subprocess.run([sys.executable, str(tmp / "grain_signal" / "rapport_pdf.py"), "--html", str(hp)], capture_output=True, text=True, env=env)
        page = hp.read_text(encoding="utf-8") if p3.returncode == 0 else ""
        import re as _re
        check(p3.returncode == 0 and "Décisions du jour" in page and page.count("<section class='bloc'>") == 3
              and "235,50 €/t" in page and "1er ordre : 235,50 €/t" in page and "quand le blé Euronext atteint" in page
              and "Prime faible" not in page.replace("Prime faible : vendre via Euronext", ""),
              "synthèse PDF : page complète (décisions, 3 contrats, ordres en €/t)" + ("" if p3.returncode == 0 else " : " + p3.stderr[-300:]))
        check(not _re.search("[\U0001F000-\U0001FAFF\u2600-\u27BF]", page), "synthèse PDF : aucun emoji (carrés vides à l'impression)")
        check("Actualité, psychologie et géopolitique" in page and "Novorossiisk" in page and "<script>alert" not in page
              and "Risque géopolitique mondial" in page, "synthèse PDF : actualité traduite et géopolitique, texte échappé")
        p2 = subprocess.run([sys.executable, str(tmp / "grain_signal" / "send_alerts.py")], capture_output=True, text=True, env=env)
        check(p2.returncode == 0 and "alerte" in p2.stdout and "Actualité majeure" in p2.stdout, "emails en simulation (alerte d'actualité en tête)"
              + ("" if p2.returncode == 0 else " : " + p2.stderr[-300:]))
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


def seeds_signal_veille(t, pv):  # la veille, le blé était à « vendre » : changement de signal ce matin
    seeds(t, pv)
    (t / "data" / "grain" / "etat.json").write_text(json.dumps({"signaux": {"ble": "VENDRE"}}), encoding="utf-8")


runs = run_build(seeds_signal_veille, twice=True)
if all(r[0] == 0 for r in runs):
    t1 = [x["id"] for x in runs[0][1]["declencheurs"]]
    t2 = [x["id"] for x in runs[1][1]["declencheurs"]]
    check(any(i.endswith("ble:signal") for i in t1) and t1 == t2,
          f"déclencheurs du jour encore affichés après le 2e calcul (page et PDF = email) ({t1} / {t2})")
    check(len([x for x in runs[1][2] if x["id"].endswith("ble:signal")]) == 1, "changement de signal envoyé une seule fois")

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

# note de marché rejouée (S5) : technique, fonds (indice sur 3 ans au dernier rapport publié) et macro, pondérés comme build.py
_cf = {"001602": {"culture": "ble", "serie": [{"date": (date(2015, 1, 6) + _td(weeks=k)).isoformat(), "long": 100, "short": 100 + k * 10}
                                            for k in range(200)]}}
_fx = {"EURUSD=X": {"serie": {d_: 1.20 - i * 0.0005 for i, d_ in enumerate(_ds)}}}
_nf = bt.note_marche(_ds, _p, bt.indicateurs(_p), "ble", _cf, _fx)
_i = _ds.index("2018-06-01")
_t = bt.score(bt.indicateurs(_p), _p, _i)
W_ = bt.CFG["poids"]
_cot_attendu = 1.5  # dernière position nette = la plus vendeuse des 3 ans → indice 0 → +1,5
_e20 = (_fx["EURUSD=X"]["serie"][_ds[_i]] / _fx["EURUSD=X"]["serie"][_ds[_i - 20]] - 1) * 100
_mac = -max(-1, min(1, _e20 / 2)) * 0.5
_att = (W_["technique"] * _t + W_["cot"] * _cot_attendu + W_["macro"] * _mac) / (W_["technique"] + W_["cot"] + W_["macro"])
check(abs(_nf(_i) - _att) < 1e-9, f"backtest S5 : note rejouée = technique + fonds + macro pondérés ({_nf(_i):.3f} / {_att:.3f})")
_r3 = bt.campagne(_p, bt.indicateurs(_p), bt.ym_idx(_ds), 2017, [list(t) for t in bt.CFG["calendrier"]["ble"]["tranches"]], 7,
                  {"rsi": 40, "pos": 20}, _nf)
check(_r3 and "S5" in _r3 and abs(_r3["S5"] - 200) < 1e-6, "backtest S5 : prix constant, l'outil complet vend aussi à 200 €/t")
_rows = [{"recolte": y, "S1": 200, "S2": 200 + (y % 3)} for y in range(2001, 2024)]
_pp = bt.par_periode(_rows, ["S1", "S2"], "S1")
check(set(_pp) == {"2000-2009", "2010-2019", "2020 et après"} and _pp["2020 et après"]["S2"]["campagnes"] == 4,
      "backtest : bilan par période")

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
check(dec.pctile([1, 2, 3, 4], 2) == 38 and dec.pctile([5] * 40, 5) == 50 and dec.pctile([], 1) is None,
      "percentile : rang moyen (série constante = 50e, pas 100e)")
check(dec.mois_debut("janv. - mars") == 1 and dec.mois_debut("nov.") == 11 and dec.mois_debut("mars\xa0-\xa0juin") == 3
      and dec.mois_debut("") is None, "prime locale : début de la période de livraison lu")

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

_rows = [{"date": f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}", "page": "ble", "place": "Rouen\xa0Rendu", "prix": 200 + (i % 10)} for i in range(50)]
_pl = dec.prime_locale(_rows, [["ble", "Rouen Rendu"], ["ble", "Inconnue"]], lambda d_, p_=None: 200.0)
check(_pl and _pl["places"][0]["jours"] == 50 and _pl["percentile"] is not None and len(_pl["places"]) == 1,
      f"prime locale : physique − Euronext (espaces insécables de terre-net), percentile après 40 relevés ({_pl and _pl.get('texte')})")
_pl2 = dec.prime_locale(_rows[:5], [["ble", "Rouen Rendu"]], lambda d_, p_=None: 200.0)
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

# ---------------------------------------------------------------- corrections de la revue indépendante
_eu = [{"date": "2026-11-06", "product": "EBM", "maturity": m, "settle": v} for m, v in (("2026-12", 225.5), ("2027-03", 223.0))]
_f = build.front_on(_eu, "EBM")
check(_f("2026-11-06") == 225.5 and _f("2026-11-06", "janv. - mars") == 223.0 and _f("2026-11-06", "nov.") == 225.5,
      "prime locale : physique « janv. - mars » comparé à mars, « nov. » à décembre")
_pc = dec.prime_locale([{"date": f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}", "page": "ble", "place": "Rouen Rendu", "prix": 200}
                        for i in range(45)], [["ble", "Rouen Rendu"]], lambda d_, p_=None: 200.0)
check("percentile" not in _pc and _pc["places"][0].get("constante") and "constante" in _pc["texte"],
      "prime locale : prime toujours nulle (prix nominal) sans verdict « prime forte »")
_old = [{"date": "2026-08-01", "long": 10, "short": 5}] * 30
check(build.cot_reading(_old, today=date(2026, 11, 8)).get("perime") and build.cot_reading(_old, today=date(2026, 11, 8))["indice"] is None,
      "positions des fonds : rapport de plus de 3 semaines affiché mais plus compté")
import send_alerts as _sa  # noqa: E402
check("#b0281f" in _sa.jauge(20)[:60] and "#9a5b00" in _sa.jauge(40)[:60] and "#6b6d60" in _sa.jauge(50)[:60]
      and "#6b6d60" in _sa.jauge(30, _sa.ECH_RATIO)[:60] and "#b0281f" in _sa.jauge(85, _sa.ECH_RATIO)[:60],
      "email : couleurs des jauges = page (20 rouge, 40 orange, ratio 30 normal, ratio 85 rouge)")
check("position" not in _sa.jauge(55), "email : jauge sans « position » (retiré par Gmail)")
check(_sa.niveaux_txt([235.5], [219.0], {"sur_ble": True}).startswith("≈ 219 €/t d'orge, quand le blé Euronext atteint 235,5"),
      "email : ordres d'orge en prix d'orge, le blé comme déclencheur")

# collecte des positions Euronext : une erreur réseau n'est jamais une « semaine sans rapport », mercredi de la même semaine
_tmp2 = Path(tempfile.mkdtemp())
try:
    collect.PRIV = _tmp2
    _base = {"EBM": {"serie": [{"date": "2026-10-30", "publie": "2026-11-03", "net": 1}], "absents": []}}
    (_tmp2 / "cot_euronext.json").write_text(json.dumps(_base))
    _asked = []

    def _down(url):
        _asked.append(url.rsplit("_", 1)[1][:8])
        return None  # réseau coupé
    collect.fetch_pdf = _down
    collect.collect_cot_euronext(date(2026, 11, 6))
    _after = json.loads((_tmp2 / "cot_euronext.json").read_text())
    check(_after["EBM"]["absents"] == [], f"COT Euronext : réseau coupé, aucune semaine marquée absente ({_after['EBM']['absents']})")
    _asked.clear()
    collect.fetch_pdf = lambda url: (_asked.append(url.rsplit("_", 1)[1][:8]), "absent")[1]
    collect.collect_cot_euronext(date(2026, 11, 6))
    check("20261028" in _asked, f"COT Euronext : rapport du mardi 03/11, la semaine du 28/10 est bien cherchée ({sorted(set(_asked))[:6]})")
    _stale = {"EBM": {"serie": [{"date": "2026-08-28", "publie": "2026-09-02", "net": 1}], "absents": []}}
    (_tmp2 / "cot_euronext.json").write_text(json.dumps(_stale))
    collect.collect_cot_euronext(date(2026, 11, 6))
    check(collect.status["cot_euronext_EBM"]["ok"] is False and "depuis" in collect.status["cot_euronext_EBM"]["detail"],
          "COT Euronext : plus aucun rapport depuis 2 mois = source en panne")
finally:
    shutil.rmtree(_tmp2, ignore_errors=True)

# ---------------------------------------------------------------- historique officiel Euronext (fichiers statistiques publics)
from datetime import date as _date  # noqa: E402

_H = ["Date", "Market Place", "Product Group", "_", "Contract Type", "Contract Name", "Contract Code", "Last Trading Date",
      "Expiration Date", "Exercise Price", "Instrument Type", "Valuation Coefficient", "Exercise Type", "AMR", "ISIN", "Currency",
      "First Price", "Highest Price", "Lowest Price", "Last Price", "Settlement Price"]


def _row(code, amr, ltd, sp):
    r = [None] * len(_H)
    r[6], r[13], r[7], r[20] = code, amr, ltd, sp
    return r


_rows = [["Euronext Derivatives - Series"], _H,
         _row("EBM", "YFEBM 2612A000000F", _date(2026, 12, 10), 223),
         _row("EBM", "YFEBMT2611K000000F", _date(2026, 11, 20), 0),  # contrat TAS : écarté
         _row("ECO", "YFECO 2701T000000F", _date(2027, 1, 29), 526),  # colza février 2027 (expire fin janvier)
         _row("EMA", "YFEMA 27035000000F", _date(2027, 3, 5), 246),
         _row("EMA", "YFEMA 28036000000F", _date(2028, 3, 6), 0),  # prix nul : écarté
         _row("IS6", "AFIS6 2611F000000F", _date(2026, 11, 20), 16.5)]
_ps = {(x["product"], x["maturity"]): x["settle"] for x in collect.parse_series(_rows, _date(2026, 11, 5))}
check(_ps == {("EBM", "2026-12"): 223.0, ("ECO", "2027-02"): 526.0, ("EMA", "2027-03"): 246.0},
      f"historique Euronext : compensation par échéance, colza décalé d'un mois, TAS et prix nuls écartés ({_ps})")
_H2 = [h.replace("Expiration Date", "Expiry Month") for h in _H]  # format 2019-2023
_r2 = [_H2, _row("EBM", "YFEBM191200000F", _date(2019, 12, 10), 178.5)]
check(collect.parse_series(_r2, _date(2019, 11, 8))[0]["maturity"] == "2019-12", "historique Euronext : ancien format (2019) lu")

_tmp3 = Path(tempfile.mkdtemp())
try:
    collect.PRIV = _tmp3
    (_tmp3 / "euronext.csv").write_text("date,product,maturity,settle\n2026-11-05,EBM,2026-12,223.5\n", encoding="utf-8")
    _calls = []

    class _R:
        def __init__(self, code, content=b""):
            self.status_code, self.content = code, content

    def _get(url, **kw):
        d_ = url.rsplit("%20", 1)[1][:8]
        _calls.append(d_)
        if d_ in ("20261105", "20261104"):
            return _R(200, b"PK" + d_.encode())
        return _R(404)
    _orig_get, _orig_rows = collect.requests.get, collect.stats_rows
    collect.requests.get = _get
    collect.stats_rows = lambda content, d: [{"date": d.isoformat(), "product": "EBM", "maturity": "2026-12", "settle": 223.0}]
    collect.HISTO_DEBUT = _date(2026, 10, 20)
    collect.collect_euronext_histo(_date(2026, 11, 7), budget=30, workers=1)
    _st = json.loads((_tmp3 / "euronext_histo.json").read_text())["faits"]
    _csv = collect.read_csv(_tmp3 / "euronext.csv")
    check("2026-11-06" not in _st and "2026-11-05" in _st and "2026-10-23" in _st,
          f"historique Euronext : fichier récent absent redemandé demain, ancien absent = jour férié ({_st[-4:]})")
    check(any(r["date"] == "2026-11-04" for r in _csv) and len([r for r in _csv if r["date"] == "2026-11-05"]) == 1,
          "historique Euronext : séances ajoutées sans doublon")
    check(collect.status["controle_terre_net"]["ok"] is False and "223.5" in collect.status["controle_terre_net"]["detail"],
          "contrôle croisé : écart entre terre-net et Euronext signalé")
    collect.requests.get, collect.stats_rows = _orig_get, _orig_rows
finally:
    shutil.rmtree(_tmp3, ignore_errors=True)

_fe = [{"date": "2026-12-01", "product": "EBM", "maturity": "2026-12", "settle": "230"},
       {"date": "2026-12-01", "product": "EBM", "maturity": "2027-03", "settle": "228"},
       {"date": "2026-12-04", "product": "EBM", "maturity": "2026-12", "settle": "231"},
       {"date": "2026-12-04", "product": "EBM", "maturity": "2027-03", "settle": "229"}]
check(build.front_series(_fe, "EBM") == (["2026-12-01", "2026-12-04"], [230.0, 229.0]),
      "prix réel de l'échéance de référence : bascule sur mars 5 jours ouvrés avant l'expiration de décembre")

# ---------------------------------------------------------------- bilans mondiaux USDA et chances d'atteindre un ordre
import io as _io  # noqa: E402
import zipfile as _zf  # noqa: E402

_buf = _io.BytesIO()
with _zf.ZipFile(_buf, "w") as _z:
    _lines = ["Commodity_Code,Commodity_Description,Country_Code,Country_Name,Market_Year,Calendar_Year,Month,Attribute_ID,"
              "Attribute_Description,Unit_ID,Unit_Description,Value"]
    for _y in range(2000, 2027):
        for _c, _st, _co in (("China", 100, 150), ("European Union", 15 + (_y - 2000), 120)):
            _lines += [f"0410000,Wheat,XX,{_c},{_y},{_y},10,176,Ending Stocks,21,(1000 MT),{_st}",
                       f"0410000,Wheat,XX,{_c},{_y},{_y},10,125,Domestic Consumption,21,(1000 MT),{_co}",
                       f"0410000,Wheat,XX,{_c},{_y},{_y},10,28,Production,21,(1000 MT),{_co}",
                       f"0410000,Wheat,XX,{_c},{_y},{_y},10,184,Yield,26,(MT/HA),7"]
    _z.writestr("psd_grains_pulses.csv", "\n".join(_lines))
_bl = collect.usda_bilans(_buf.getvalue())
check(_bl["ble"]["2026"]["stocks"] == 141 and _bl["ble"]["2026"]["stocks_chine"] == 100 and _bl["ble"]["2026"]["conso"] == 270,
      "USDA : bilans mondiaux = somme des pays, part de la Chine gardée, rendements ignorés")
_sc = dec.stocks_conso(_bl["ble"], {"2026": dict(_bl["ble"]["2026"], stocks=_bl["ble"]["2026"]["stocks"] - 6)})
check(_sc["campagne"] == "2026/27" and _sc["ratio"] == round(41 / 120 * 100, 1) and _sc["percentile"] == 100
      and _sc["revision"] == round((41 / 120 - 35 / 120) * 100, 2) and "confortables" in _sc["lecture"],
      f"USDA : stocks / consommation hors Chine, au plus haut des 20 ans, révision du mois ({_sc})")
check(dec.proba_toucher(100, 100, 0.01, 25) == 100 and dec.proba_toucher(100, 100 * math.exp(0.05), 0.01, 25) == 32
      and dec.proba_toucher(100, 100 * math.exp(-0.05), 0.01, 25) == 32 and dec.proba_toucher(100, 150, 0.01, 25) == 0,
      "chances d'atteindre un prix : 100 % au cours, 32 % à un écart-type, symétrique, ~0 % très loin")

# ------------------------------------------------------------------ psychologie, géopolitique, actualités
import random as _rnd  # noqa: E402

_rnd.seed(7)
_v = [200.0]
for _i in range(900):
    _v.append(_v[-1] * math.exp(_rnd.gauss(0, 0.012)))
_up = _v + [_v[-1] * (1.006 ** k) for k in range(1, 41)]  # 40 séances de hausse régulière
_dn = _v + [_v[-1] * (0.994 ** k) for k in range(1, 41)]
_pu, _pd = dec.psychologie(_up, 90), dec.psychologie(_dn, 10)
check(_pu["etat"] == "euphorie" and _pd["etat"] == "peur_extreme" and _pu["composantes"]["fonds"] == 90,
      f"humeur du marché : euphorie après une hausse régulière, peur extrême après une baisse ({_pu['indice']}, {_pd['indice']})")
check(dec.psychologie(_v[:300]) is None, "humeur du marché : rien sous 460 séances d'historique")
_s = dec.psy_series(_v)
check(all(x is None or 0 <= x <= 100 for k in ("rsi", "ecart200", "elan20") for x in _s[k]) and _s["rsi"][150] is None and _s["rsi"][300] is not None,
      "humeur du marché : percentiles bornés, calculés après 200 points de fenêtre")
from datetime import datetime as _dt, timezone as _tz  # noqa: E402

_now = _dt(2026, 11, 9, 8, tzinfo=_tz.utc)
_a = lambda i, imp, nat="fait", th="offre", age_h=2, doub=None, pert=True: {  # noqa: E731
    "id": i, "pertinent": pert, "theme": th, "nature": nat, "importance": imp, "impacts": {"ble": 2}, "doublon_de": doub,
    "date": (_now - __import__("datetime").timedelta(hours=age_h)).isoformat()}
_p1 = dec.actu_pression([_a("x", 3)], _now)["ble"]["valeur"]
_p2 = dec.actu_pression([_a("x", 3, nat="rumeur")], _now)["ble"]["valeur"]
_p3 = dec.actu_pression([_a("x", 3, age_h=24 * 6)], _now)["ble"]["valeur"]
_p4 = dec.actu_pression([_a("x", 3, th="marche"), _a("y", 3, doub="x"), _a("z", 3, pert=False), _a("w", 3, age_h=24 * 8)], _now)["ble"]["valeur"]
_p5 = dec.actu_pression([_a(str(k), 3) for k in range(30)], _now)["ble"]["valeur"]
check(_p1 > _p2 > 0 and _p1 > _p3 > 0 and _p4 == 0 and 1.9 < _p5 <= 2,
      f"pression de l'actualité : fait > rumeur, récent > ancien, séances, doublons, hors sujet et > 7 jours exclus, bornée à 2 ({_p1}, {_p2}, {_p3}, {_p5})")
check(dec.actu_majeur(_a("x", 3), _now) and not dec.actu_majeur(_a("x", 2), _now) and not dec.actu_majeur(_a("x", 3, nat="prevision"), _now)
      and dec.actu_majeur(_a("x", 3, age_h=47), _now) and not dec.actu_majeur(_a("x", 3, age_h=80), _now),
      "événement majeur : fait, importance 3, effet fort, moins de 72 h (fait du samedi matin alerté le lundi)")
check(dec.actu_doublon("Russia raises wheat export tax - Reuters", "Russia raises its wheat export tax again")
      and not dec.actu_doublon("Russia raises wheat export tax", "Egypt buys French wheat in tender")
      and dec.actu_norm("Le blé Euronext reste bloqué - Terre-net") == "le ble euronext reste bloque", "actualités : doublons et titres normalisés")
_rss = (b'<?xml version="1.0"?><rss><channel><item><title>Russia raises wheat export quota - Reuters</title>'
        b'<link>https://news.google.com/rss/articles/x</link><pubDate>Mon, 09 Nov 2026 06:40:49 GMT</pubDate>'
        b'<source url="https://reuters.com">Reuters</source></item><item><title>Le bl&#233; recule</title><link>https://t.fr/a</link>'
        b'<pubDate>Fri, 06 Nov 2026 13:00:00 +0100</pubDate></item><item><title>Sans lien</title><link>javascript:x</link></item></channel></rss>')
_it = collect.rss_items(_rss)
check(len(_it) == 2 and _it[0]["titre"] == "Russia raises wheat export quota" and _it[0]["source"] == "Reuters"
      and _it[0]["date"] == "2026-11-09T06:40+00:00" and _it[1]["date"] == "2026-11-06T12:00+00:00" and _it[1]["titre"] == "Le blé recule",
      "flux RSS : titre sans le nom du site, date en UTC, liens non http écartés")
_at = collect.rss_items(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Urea up</title><link href="https://x.com/a"/>'
                        b'<updated>2026-11-08T10:00:00Z</updated></entry></feed>')
check(_at == [{"titre": "Urea up", "url": "https://x.com/a", "date": "2026-11-08T10:00+00:00", "source": ""}], "flux Atom")
_arts = {}
check(collect.actu_ajoute(_arts, dict(_it[0]), _now, 7, origine="google")
      and not collect.actu_ajoute(_arts, {"titre": "Russia raises its wheat export quota again", "url": "https://b", "date": "2026-11-09T07:00+00:00",
                                         "source": "Bloomberg"}, _now, 7)
      and list(_arts.values())[0]["autres_sources"] == ["Bloomberg"]
      and not collect.actu_ajoute(_arts, {"titre": "Old wheat news from Egypt", "url": "https://c", "date": "2026-10-01T07:00+00:00"}, _now, 7),
      "actualités : même événement compté une fois (autres sites notés), titres trop anciens ignorés")
check(collect.ACTU_MOTS.search("Prix du colza en hausse") and collect.ACTU_MOTS.search("Urea demand slows")
      and not collect.ACTU_MOTS.search("Le secteur agricole recrute"), "presse agricole : filtre des titres sur les marchés")
check(collect.gpr_quotidien([["DAY", "GPRD", "event"], [20261101.0, 77.6, None], [20261102.0, 97.6, "Attack on port"], ["x", "y", None]])
      == ([("2026-11-01", 77.6), ("2026-11-02", 97.6)], [("2026-11-02", "Attack on port")]), "risque géopolitique : feuille quotidienne")
import datetime as _dtm  # noqa: E402

check(collect.gpr_mensuel([["month", "GPR", "GPRC_RUS", "GPRC_UKR"], [_dtm.datetime(2026, 9, 1), 100, 1.2, 0.8], [46296.0, 99, 1.3, "x"]],
                          ["RUS", "UKR", "CHN"]) == {"RUS": [("2026-09", 1.2), ("2026-10", 1.3)], "UKR": [("2026-09", 0.8)]},
      "risque géopolitique : feuille mensuelle par pays (dates Excel et dates)")
sys.path.insert(0, str(HERE))
import actualites as _act  # noqa: E402

_ok = _act.valide({"id": "a", "pertinent": True, "titre_fr": "T", "theme": "inconnu", "nature": "fait", "importance": 7,
                   "impacts": {"ble": 5, "orge": "-1", "colza": None, "pirate": 2}, "horizon": "siècles", "impact": "x" * 500, "doublon_de": 3})
check(_act.valide({"id": "b", "pertinent": "false"})["pertinent"] is False
      and _act.valide({"id": "c", "pertinent": True, "importance": 3.0, "impacts": {"ble": 2.0}})["importance"] == 3,
      "actualités : « false » en texte non pertinent, importance 3.0 lue comme 3")
check(_ok["theme"] == "offre" and _ok["importance"] == 3 and _ok["impacts"] == {"ble": 2, "orge": -1} and _ok["horizon"] == "jours"
      and len(_ok["impact"]) == 300 and _ok["doublon_de"] is None and _act.valide({"pertinent": True}) is None,
      "actualités : réponse de l'IA vérifiée champ par champ (bornes, valeurs inconnues écartées)")

# comité : il reçoit la pression et la synthèse de l'actualité du jour (le premier calcul a lu celles de la veille)
_tc = Path(tempfile.mkdtemp())
try:
    _old_out, _old_call = comite.OUT, comite.call
    comite.OUT = _tc
    (_tc / "grain-signal.json").write_text(json.dumps({"cultures": {"ble": {"nom": "Blé", "actualite": {"valeur": 1.77, "sens": "haussière"}},
                                                                    "colza": {"nom": "Colza", "actualite": {"valeur": 0.9}}},
                                                       "actualites": {"date": "2026-11-08", "synthese": "VIEILLE SYNTHÈSE"}}), encoding="utf-8")
    (_tc / "actualites.json").write_text(json.dumps({"date": "2026-11-09", "synthese": "Synthèse du jour", "majeurs": ["a1"],
                                                     "pression": {"ble": {"valeur": -1.25, "sens": "baissière"}},
                                                     "articles": [{"id": "a1", "pertinent": True, "importance": 3, "titre": "T", "titre_fr": "Fait majeur du jour",
                                                                   "date": "2026-11-09T05:00+00:00", "impacts": {"ble": -2}, "impact": "x"}]}), encoding="utf-8")
    _vu = {}

    def _faux(messages, system, key):
        _vu["user"] = messages[0]["content"]
        raise RuntimeError("arrêt du test")
    comite.call = _faux
    _env = {k: os.environ.get(k) for k in ("GS_TODAY", "ANTHROPIC_API_KEY", "GS_COMITE", "GS_DRY")}
    os.environ.update(GS_TODAY="2026-11-09", ANTHROPIC_API_KEY="test", GS_COMITE="force")
    os.environ.pop("GS_DRY", None)
    import contextlib as _cl
    with _cl.redirect_stdout(_io.StringIO()):
        comite.main()
    _u = _vu.get("user", "")
    check("-1.25" in _u and "1.77" not in _u and "0.9" not in _u and "VIEILLE" not in _u and "Synthèse du jour" in _u
          and "Fait majeur du jour" in _u and _u.count("Rends le rapport") == 1,
          "comité : actualité du jour (pression, synthèse, titres) à la place de celle de la veille, consigne finale unique")
finally:
    comite.OUT, comite.call = _old_out, _old_call
    for _k, _v in _env.items():
        if _v is None:
            os.environ.pop(_k, None)
        else:
            os.environ[_k] = _v
    shutil.rmtree(_tc, ignore_errors=True)

for st, name in results:
    print(st, name)
fails = [n for s, n in results if s != "OK  "]
print(f"{len(results) - len(fails)}/{len(results)} tests réussis")
sys.exit(1 if fails else 0)
