"""
Tests hors ligne du Bulletin des grains (lecture des pages, indicateurs, séries continues, comité, sécurité du rapport).

  python grain_signal/test_grain.py
"""
import csv
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
check(ind.analyse(["a"] * 10, list(range(10))).get("insuffisant"), "moins de 30 séances : insuffisant")
nv = ind.niveaux({"dernier": 225.5, "mm20": 233.81, "fibo": {"38.2": 232.65, "50": 235.62, "61.8": 238.6}, "haut3m": 248.25, "bas3m": 223.0})
check(nv["resistances"] == [232.75, 235.5] and nv["supports"] == [223.0], f"résistances au-dessus du cours, supports en dessous ({nv})")
_lec = ind.lecture(a)
check(_lec["sens"] in ("haussière", "neutre", "baissière") and "RSI 100 : surachat" in _lec["texte"], f"lecture technique en clair ({_lec})")
check(ind.sens(0.75) == "haussière" and ind.sens(-0.75) == "baissière" and ind.sens(0.5) == "neutre" and ind.sens(None) is None,
      "seuils de lecture : ±0,75")
import random as _rd  # noqa: E402
_rd.seed(3)
_x = [100.0]
for _ in range(400):
    _x.append(_x[-1] * (1 + _rd.gauss(0, 0.012)))
_a = ind.analyse([f"d{i}" for i in range(len(_x))], _x)
_sv = ind.score_serie(_x)
check(_sv[-1] is not None and abs(_sv[-1] - ind.score_technique({**_a, "divergence": "aucune"})) < 1e-9,
      f"note technique jour par jour (backtest) = note du matin ({_sv[-1]} / {ind.score_technique(_a)})")

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

# ------------------------------------------------------------------ lecture hebdomadaire : sortie machine et sécurité du rapport
TXT = """# Rapport
Texte <script>alert(1)</script> et [lien piégé](javascript:alert(1)) et [source](https://example.com/a).
```json
{"resume": "R", "cultures": {"ble": {"haussier": ["Russie : ports fermés", 3], "baissier": "pas une liste", "a_surveiller": "WASDE",
 "lecture": "équilibre"}, "colza": {"signal": "VENDRE"}, "inventee": {"haussier": ["x"]}, "engrais": {"baissier": ["Inde absente"]}},
 "calendrier": [{"date": "2026-11-10", "evenement": "WASDE"}, {"date": "demain", "evenement": "x"}]}
```"""
dec, rep = comite.parse_decision(TXT)
check(dec["cultures"]["ble"] == {"haussier": ["Russie : ports fermés", "3"], "baissier": [], "a_surveiller": "WASDE", "lecture": "équilibre"}
      and set(dec["cultures"]) == {"ble", "engrais"}, f"lecture hebdomadaire validée : arguments seuls, pas de signal ({dec['cultures']})")
check(dec["calendrier"] == [{"date": "2026-11-10", "evenement": "WASDE"}], "calendrier validé (date AAAA-MM-JJ)")
hs = comite.safe_html(rep)
check("<script" not in hs and "javascript:" not in hs.lower(), "rapport sans script ni lien javascript")
check('href="https://example.com/a"' in hs, "lien https conservé")
_p = (HERE / "prompt.md").read_text(encoding="utf-8")
check("INTERDIT" in _p and '"haussier"' in _p and '"signal"' not in _p and "ordres" not in _p, "consigne de la lecture : aucun conseil demandé")

# ------------------------------------------------------------------ calcul complet sur les historiques de départ (dossier temporaire)
tmp = Path(tempfile.mkdtemp())
try:
    (tmp / "grain_signal").mkdir()
    for f in ("build.py", "indicators.py", "decisions.py", "commun.py", "config.json", "comite.py", "send_alerts.py", "rapport_pdf.py", "actualites.py"):
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
    _cls["a_vieux"] = {"pertinent": True, "titre_fr": "Ancien classement", "classe_le": "2026-11-07"}  # sans version : relu
    (priv / "actualites_classees.json").write_text(json.dumps({k: {**v, "v": 2} if k not in ("a_vieux", "a3") else v for k, v in _cls.items()}),
                                                   encoding="utf-8")  # a3 : classement de la version 1 (phrase avec conseil)
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
    _a3 = next((a for a in ac_.get("articles", []) if a["id"] == "a3"), {})
    check(_a3.get("impacts") == {"engrais": 2} and _a3.get("impact") is None,
          "classement d'une version antérieure : effets gardés pour la pression, phrase masquée en attendant la relecture")
    check(len(ac_.get("historique") or []) == 1 and ac_["historique"][0]["date"] == "2026-11-07", "actualités : pression du jour gardée en historique")
    check(pr_.get("ble", {}).get("valeur", 0) > 0.5 and pr_["ble"]["baisse"] == 0 and pr_.get("engrais", {}).get("valeur", 0) > 0.3,
          f"actualités : pression haussière sur le blé (compte rendu de séance exclu), azote plus cher ({pr_.get('ble')}, {pr_.get('engrais')})")
    _box = json.loads((priv / "a-envoyer.json").read_text(encoding="utf-8")) if (priv / "a-envoyer.json").exists() else []
    check(ac_.get("majeurs") == ["a1"] and any(x["id"] == "2026-11-07:actu:a1" and x["grave"] for x in _box)
          and not (tmp / "data" / "grain" / "demande-comite.json").exists(), "actualité majeure : alerte email (plus de comité d'alerte)")
    _cache = json.loads((priv / "actualites_classees.json").read_text(encoding="utf-8"))
    check(_cache["a1"]["v"] == 2 and "a_vieux" in _cache, "classements gardés (version antérieure conservée en attendant sa relecture)")
    pa2 = subprocess.run([sys.executable, str(tmp / "grain_signal" / "actualites.py")], capture_output=True, text=True, env=env)
    _box2 = json.loads((priv / "a-envoyer.json").read_text(encoding="utf-8"))
    check(pa2.returncode == 0 and len([x for x in _box2 if ":actu:" in x["id"]]) == 1, "actualité majeure : une seule alerte, même relancé")
    p = subprocess.run([sys.executable, str(tmp / "grain_signal" / "build.py")], capture_output=True, text=True, env=env)
    check(p.returncode == 0, "calcul complet sur les historiques de départ" + ("" if p.returncode == 0 else " : " + p.stderr[-400:]))
    if p.returncode == 0:
        dash = json.loads((tmp / "data" / "grain" / "grain-signal.json").read_text(encoding="utf-8"))
        check(set(dash["cultures"]) == {"ble", "escourgeon", "orge_printemps", "colza", "mais"}, "cinq cultures")
        c_ = dash["cultures"]["ble"]
        check(dash["format"] == "grain-signal-2" and c_["cours"] == 225.5 and c_["var1j"] == 2.5 and not c_["physique"],
              f"blé : cours Euronext du jour et variation sur la séance ({c_.get('cours')}, {c_.get('var1j')})")
        check(c_["technique"]["sens"] in ("haussière", "neutre", "baissière") and c_["technique"]["resistances"]
              and all(x > 225.5 for x in c_["technique"]["resistances"]) and all(x < 225.5 for x in c_["technique"]["supports"]),
              f"blé : lecture technique, résistances au-dessus et supports en dessous ({c_['technique']})")
        _forb = ("signal", "plan", "decision", "niveaux_retenus", "libelle", "feu", "score_marche", "biais")
        check(not any(k in c for c in dash["cultures"].values() for k in _forb) and "decision" not in dash["engrais"]
              and "signal" not in dash["engrais"] and "a_acheter" not in dash["engrais"] and "carnet" not in dash,
              "aucun conseil publié : ni signal, ni plan, ni ordre, ni décision")
        e_ = dash["cultures"]["escourgeon"]
        check(e_["physique"] and e_["cours"] == 209.0 and e_["technique"].get("sur_ble")
              and e_["technique"]["resistances"][0] == round(c_["technique"]["resistances"][0] - 16.5, 2),
              f"escourgeon : prix physique, technique du blé ramenée au niveau de l'orge ({e_['technique']})")
        check(dash["orges"]["escourgeon"]["prime"] == -6.25 and dash["orges"]["orge_printemps"]["prix"] == 234.25,
              "orges brassicoles : prix physique et prime sur la fourragère")
        rp_ = c_["reperes"]
        check(rp_.get("plus_haut") == 248.25 and rp_.get("campagne_depuis") == "2026-07-01" and rp_.get("ecart_plus_haut") == -22.75,
              f"repère : plus haut de la campagne et écart ({rp_})")
        st_ = dash["contrats"]["EBM"].get("stockage") or {}
        check(st_.get("code") in ("paye", "ne_paye_pas", "a_peine") and st_.get("reference") == "2026-12" and "stocker" not in st_.get("texte", "").lower(),
              f"report de la courbe du blé, sans conseil ({st_.get('texte')})")
        ng_ = dash["engrais"]
        check(ng_.get("percentile_retenu") is not None and not any("percentile" in n for n in ng_.get("notes", []))
              and not any(w in " ".join(ng_["notes"]).lower() for w in ("acheter", "attendre", "fractionner")),
              f"azote : faits seulement, ratio en jauge sans note qui le répète ({ng_.get('notes')})")
        check((dash["cultures"]["ble"].get("actualite") or {}).get("sens") == "haussière" and dash["cultures"]["escourgeon"].get("actualite")
              and (dash.get("actualites") or {}).get("majeurs") == 1, "actualités : pression reprise par culture dans le calcul du matin")
        g_ = dash.get("geopolitique") or {}
        check(g_.get("percentile", 0) >= 90 and g_.get("etat") == "très élevé" and g_.get("pays", [{}])[0].get("nom") == "Russie"
              and g_.get("evenements"), f"géopolitique : pic récent au-dessus de 10 ans d'historique, pays et événements ({ {k: g_.get(k) for k in ('mois', 'percentile', 'etat')} })")
        hp = tmp / "synthese.html"
        p3 = subprocess.run([sys.executable, str(tmp / "grain_signal" / "rapport_pdf.py"), "--html", str(hp)], capture_output=True, text=True, env=env)
        page = hp.read_text(encoding="utf-8") if p3.returncode == 0 else ""
        import re as _re
        check(p3.returncode == 0 and "Le marché ce matin" in page and page.count("<section class='bloc'>") == 3
              and "Résistance 232,75" in page and "Support 223,00" in page and "225,50" in page,
              "synthèse PDF : page complète (marché, 3 contrats, supports et résistances)" + ("" if p3.returncode == 0 else " : " + p3.stderr[-300:]))
        _low = page.lower()
        check(not any(w in _low for w in ("que faire", "vendre une tranche", "ordre :", "bon pour vendre", "acheter large", "fractionner")),
              "synthèse PDF : aucun conseil de vente ou d'achat")
        check(not _re.search("[\U0001F000-\U0001FAFF\u2600-\u27BF]", page), "synthèse PDF : aucun emoji (carrés vides à l'impression)")
        check("<h2>Actualité</h2>" in page and "Novorossiisk" in page and "<script>alert" not in page,
              "synthèse PDF : actualité traduite, texte échappé")
        p2 = subprocess.run([sys.executable, str(tmp / "grain_signal" / "send_alerts.py")], capture_output=True, text=True, env=env)
        check(p2.returncode == 0 and p2.stdout.count("SIMULATION") == 1 and "Bulletin des grains — samedi 7 nov. : Actualité majeure" in p2.stdout,
              "rapport du matin : un seul email, l'actualité majeure en objet" + (": " + p2.stdout[-400:] if p2.returncode == 0 else "")
              + ("" if p2.returncode == 0 else " : " + p2.stderr[-300:]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ------------------------------------------------------------------ tests de résistance (données vides, corrompues, relances)
def run_build(setup, today="2026-11-07", twice=False):
    t = Path(tempfile.mkdtemp())
    try:
        (t / "grain_signal").mkdir()
        for f in ("build.py", "indicators.py", "decisions.py", "commun.py", "config.json"):
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
        "format": "lecture", "date": "2026-11-07", "cultures": {"ble": {"haussier": ["ok", {"x": 1}, None], "baissier": "texte"}, "colza": ["liste"],
                                            "mais": {"signal": "VENDRE"}}, "calendrier": "rien"}), encoding="utf-8")
    with (pv / "euronext.csv").open("a", encoding="utf-8") as fh:
        fh.write("2026-11-06,EBM,2027-03,nan\n2026-11-06,EBM,2027-05,\n")


(rc, dash, _, err), = run_build(corrupt)
check(rc == 0 and dash is not None, "calcul avec fichiers corrompus (Yahoo illisible, comité malformé, prix vides)" + ("" if rc == 0 else " : " + err))
if dash:
    check(dash["cultures"]["ble"]["comite"]["haussier"] == ["ok"] and dash["cultures"]["ble"]["comite"]["baissier"] == [],
          "lecture hebdomadaire malformée nettoyée (textes seuls)")
    check("comite" not in dash["cultures"]["colza"] and "comite" not in dash["cultures"]["mais"], "ancien format (signal) ou liste ignorés")


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


def seeds_sens_veille(t, pv):  # la veille, la lecture technique du blé était « haussière »
    seeds(t, pv)
    (t / "data" / "grain" / "etat.json").write_text(json.dumps({"contrats": {"EBM": {"seance": "2026-11-05", "dernier": 223.0, "sens": "haussière"}}}),
                                                    encoding="utf-8")


runs = run_build(seeds_sens_veille, twice=True)
if all(r[0] == 0 for r in runs):
    t1 = [x["id"] for x in runs[0][1]["declencheurs"]]
    t2 = [x["id"] for x in runs[1][1]["declencheurs"]]
    check(any(i.endswith("EBM:sens") for i in t1) and t1 == t2,
          f"changement de lecture technique signalé, encore affiché après le 2e calcul ({t1} / {t2})")
    check(len([x for x in runs[1][2] if x["id"].endswith("EBM:sens")]) == 1, "changement de lecture envoyé une seule fois")
else:
    check(False, "scénario de changement de lecture : " + runs[0][3])


def seuils_franchis(t, pv):  # seuils de l'exploitant : blé ≥ 225 franchi (223 → 225,5), colza ≤ 500 pas franchi
    seeds(t, pv)
    cfg = json.loads((t / "grain_signal" / "config.json").read_text(encoding="utf-8"))
    cfg["seuils"]["ble"] = {"au_dessus": [225, "x", -3], "en_dessous": [200]}
    cfg["seuils"]["colza"] = {"au_dessus": [], "en_dessous": [500]}
    (t / "grain_signal" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (t / "data" / "grain" / "etat.json").write_text(json.dumps({"cours": {"ble": 223.0, "colza": 525.0}, "cours_du": {"ble": "2026-11-05"}}),
                                                    encoding="utf-8")


runs = run_build(seuils_franchis, twice=True)
if all(r[0] == 0 for r in runs):
    ids = [x["id"] for x in runs[0][1]["declencheurs"]]
    sl = runs[0][1]["cultures"]["ble"].get("seuils")
    check(ids.count("2026-11-07:seuil:ble:>225") == 1 and not any(":seuil:colza" in i for i in ids)
          and sl == [{"sens": ">", "niveau": 225.0, "atteint": True}, {"sens": "<", "niveau": 200.0, "atteint": False}],
          f"seuils de l'exploitant : alerte au franchissement, valeurs invalides ignorées ({ids}, {sl})")
    check(len([x for x in runs[1][2] if ":seuil:" in x["id"]]) == 1, "seuil franchi signalé une seule fois")
else:
    check(False, "scénario des seuils : " + runs[0][3])


def roll_colza(t, pv):  # changement d'échéance colza nov. → févr. le 02/11 (+27,75) : un seuil à 540 n'est pas « franchi »
    seeds(t, pv)
    cfg = json.loads((t / "grain_signal" / "config.json").read_text(encoding="utf-8"))
    cfg["seuils"]["colza"] = {"au_dessus": [540], "en_dessous": []}
    (t / "grain_signal" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (t / "data" / "grain" / "etat.json").write_text(json.dumps({"cours": {"colza": 527.5}, "cours_du": {"colza": "2026-10-30"}}), encoding="utf-8")


(rc, dash, box, err), = run_build(roll_colza, today="2026-11-03")
check(rc == 0 and not any(":seuil:" in x["id"] for x in (dash or {}).get("declencheurs", [])),
      "pas de faux seuil franchi le jour du changement d'échéance" + ("" if rc == 0 else " : " + err))


def ancien_comite(t, pv):  # avis du comité à l'ancien format (signaux, ordres) : plus affiché
    seeds(t, pv)
    (t / "data" / "grain" / "comite.json").write_text(json.dumps({"date": "2026-11-06", "resume": "Vendre le maïs",
                                                                 "cultures": {"ble": {"signal": "VENDRE", "haussier": ["x"]}}}), encoding="utf-8")


(rc, dash, _, err), = run_build(ancien_comite)
check(rc == 0 and not dash["comite"]["valide"] and "comite" not in dash["cultures"]["ble"], "ancien avis du comité (avant la refonte) ignoré")


def wb_octobre(t, pv):  # chiffre Banque mondiale d'octobre, aucun relevé France en octobre : interpolation au 15
    seeds(t, pv)
    with (pv / "wb_monthly.csv").open("a", encoding="utf-8") as fh:
        fh.write("2026-10,,420.0,,,317.0,\n")


(rc, dash, _, err), = run_build(wb_octobre)
est = (dash or {}).get("engrais", {}).get("estimation") or {}
check(rc == 0 and "interpolée au 15 entre 555 le 30/09 et 621 le 05/11" in est.get("methode", ""), f"ratio engrais : urée interpolée au milieu du mois ({est})")

for day in ("2027-01-02", "2027-07-01", "2027-12-31"):
    (rc, dash, _, err), = run_build(seeds, today=day)
    check(rc == 0, f"calcul au {day} (passage d'année, moisson)" + ("" if rc == 0 else " : " + err))

# ------------------------------------------------------------------ backtest : la lecture technique annonce-t-elle la suite ?
import backtest as bt  # noqa: E402
from datetime import timedelta as _td  # noqa: E402

_p = [100 * (1.0004 ** i) for i in range(600)]  # hausse régulière : lecture « hausse », cours plus haut 60 séances après
_pl = bt.par_lecture(_p)
_g = _pl["60"]["groupes"]
check(set(_g) == {"haussière"} and _g["haussière"]["hausses"] == 100 and abs(_g["haussière"]["moyenne"] - 2.4) < 0.1
      and _pl["60"]["ecart"] is None, f"backtest technique : hausse régulière, lecture « hausse » et cours plus haut ({_g})")
import random as _rd2  # noqa: E402
_w = bt.marche_aleatoire([100 * (1.01 if i % 2 else 0.99) ** (i % 2) for i in range(300)], _rd2.Random(1))
check(len(_w) == 300 and all(x > 0 for x in _w), "backtest : cours tirés au sort de même longueur")

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

# panne puis rétablissement le même jour : seul le rétablissement reste affiché
def panne_retablie(t, pv):
    seeds(t, pv)
    (t / "data" / "grain" / "grain-signal.json").write_text(json.dumps({"historique_declencheurs": [
        {"id": "2026-11-07:panne:yahoo_TTF=F", "titre": "⚠️ Source en panne", "detail": "", "grave": False}]}), encoding="utf-8")
    (t / "data" / "grain" / "etat.json").write_text(json.dumps({"pannes": {"yahoo_TTF=F": {"debut": "2026-11-06", "jours": ["2026-11-06", "2026-11-07"], "alerte": True}}}),
                                                    encoding="utf-8")
    (t / "data" / "grain" / "collecte.json").write_text(json.dumps({"date": "2026-11-07T06:00", "sources": {"yahoo_TTF=F": {"ok": True}}}), encoding="utf-8")


(rc, dash, _, err), = run_build(panne_retablie)
_ids = [x["id"] for x in (dash or {}).get("declencheurs", [])]
check(rc == 0 and "2026-11-07:retablie:yahoo_TTF=F" in _ids and "2026-11-07:panne:yahoo_TTF=F" not in _ids,
      f"panne puis rétablissement le même jour : seul le rétablissement affiché ({_ids})")

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
check(_s1["code"] == "paye" and all(o["echeance"] != "2027-09" for o in _s1["options"]) and "la courbe paie le stockage" in _s1["texte"],
      f"report : +16 €/t, la courbe paie le stockage, échéance de la nouvelle récolte exclue ({_s1['texte']})")
_s2 = dec.stockage({"2026-12": 220, "2027-03": 219, "2027-05": 218}, "2026-12", _exp, date(2026, 11, 7), 7, _cfg)
check(_s2["code"] == "ne_paye_pas" and "vendre" not in _s2["texte"].lower(), f"report : déport, la courbe ne couvre pas les frais ({_s2['texte']})")
_s3 = dec.stockage({"2027-09": 220, "2027-12": 230}, "2027-09", _exp, date(2027, 6, 20), 7, _cfg)
check(_s3["code"] == "nouvelle", "report : échéance de la nouvelle récolte → pas de report sur l'ancienne")

_rows = [{"date": f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}", "page": "ble", "place": "Rouen\xa0Rendu", "prix": 200 + (i % 10)} for i in range(50)]
_pl = dec.prime_locale(_rows, [["ble", "Rouen Rendu"], ["ble", "Inconnue"]], lambda d_, p_=None: 200.0)
check(_pl and _pl["places"][0]["jours"] == 50 and _pl["percentile"] is not None and len(_pl["places"]) == 1,
      f"prime locale : physique − Euronext (espaces insécables de terre-net), percentile après 40 relevés ({_pl and _pl.get('texte')})")
_pl2 = dec.prime_locale(_rows[:5], [["ble", "Rouen Rendu"]], lambda d_, p_=None: 200.0)
check("percentile" not in _pl2 and "constitution" in _pl2["texte"], "prime locale : historique trop court annoncé")

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
import html as _html  # noqa: E402

_dash = {"cultures": {"ble": {"nom": "Blé tendre", "cours": 225.5, "var1j": 2.5, "technique": {"sens": "baissière"}, "actualite": {"sens": "haussière"}},
                      "escourgeon": {"nom": "Escourgeon brassicole", "cours": 209.0, "physique": True, "var1j": 0.0,
                                     "technique": {"sens": "baissière", "sur_ble": True}},
                      "colza": {"nom": "Colza", "cours": 522.75, "var1j": -8.25, "technique": {"sens": "neutre"}}},
         "engrais": {"percentile_retenu": 77, "actualite": {"sens": "haussière"}, "france": {"uree": {"prix": 613.75, "var1m": 10.6}}}}
_ts = _html.unescape(_sa.table_marche(_dash))
check("225,50" in _ts and "+2,50" in _ts and "▼ baissière" in _ts and "▲ haussière" in _ts and "(blé)" in _ts and "physique Creil" in _ts
      and "613,75" in _ts and "(plus cher)" in _ts and "77e percentile" in _ts and "Que faire" not in _ts,
      "email : le marché du matin (cours, variation, technique, actualité), sans consigne")
check(_sa.fait_marquant(_dash, []) == "Colza -8,25 €/t à 522,75", f"objet : plus fort mouvement de la séance ({_sa.fait_marquant(_dash, [])})")
_tr = [{"id": "2026-11-07:panne:x", "titre": "⚠️ Source en panne"}, {"id": "2026-11-07:EBM:haut3m", "titre": "Blé : plus haut de 3 mois"},
       {"id": "2026-11-07:seuil:ble:>240", "titre": "Blé : votre seuil"}]
check(_sa.fait_marquant(_dash, _tr) == "Blé : votre seuil" and _sa.fait_marquant(_dash, _tr[:2]) == "Blé : plus haut de 3 mois"
      and _sa.fait_marquant(_dash, _tr[:1]).startswith("Colza"), "objet : seuil, puis extrême de 3 mois, jamais une panne de source")

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

_fe = [{"date": "2026-11-18", "product": "EBM", "maturity": "2026-12", "settle": "230"},
       {"date": "2026-11-18", "product": "EBM", "maturity": "2027-03", "settle": "228"},
       {"date": "2026-11-19", "product": "EBM", "maturity": "2026-12", "settle": "231"},
       {"date": "2026-11-19", "product": "EBM", "maturity": "2027-03", "settle": "229"}]
check(build.front_series(_fe, "EBM") == (["2026-11-18", "2026-11-19"], [230.0, 228.0 + 1]),
      "prix réel de l'échéance de référence : bascule sur mars 15 jours ouvrés avant l'expiration de décembre (avant la fin de vie agitée)")
# raccord : écart médian des 5 dernières séances communes, pas celui du seul jour du changement (fin de vie agitée de l'échéance proche)
_rc = []
for _i, (_d, _nov, _mar) in enumerate((("2026-10-09", 280, 275), ("2026-10-12", 281, 275), ("2026-10-13", 282, 276), ("2026-10-14", 290, 276),
                                       ("2026-10-15", 330, 277))):
    _rc += [{"date": _d, "product": "EMA", "maturity": "2026-11", "settle": str(_nov)},
            {"date": _d, "product": "EMA", "maturity": "2027-03", "settle": str(_mar)}]
_cd, _cv, _cref, _crac, _ = build.continuous(_rc, "EMA")
check(_cref == "2027-03" and _crac and _crac[-1]["ajustement"] == -6.0 and _cv[0] == 274.0,
      f"raccord sur l'écart médian des dernières séances (−6), pas sur le −53 du jour du changement ({_crac})")

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
check(_p1 > _p2 > 0 and _p1 > _p3 > 0 and _p4 == 0 and 1.9 < _p5 <= 2 and abs(_p1 - 1.0) < 0.03,
      f"pression de l'actualité : fait > rumeur, récent > ancien, séances, doublons, hors sujet et > 7 jours exclus, bornée à 2 ({_p1}, {_p2}, {_p3}, {_p5})")
_mod = lambda i, v: {**_a(i, 2), "impacts": {"ble": v}}  # noqa: E731
_p6 = dec.actu_pression([_mod(str(k), 1) for k in range(40)], _now)["ble"]["valeur"]
_p7 = dec.actu_pression([_mod(str(k), 1 if k % 2 else -1) for k in range(40)], _now)["ble"]["valeur"]
check(0.9 < _p6 < 1.0 and abs(_p7) < 0.05,
      f"pression : 40 nouvelles modérées dans le même sens restent modérées (pas de saturation), autant de haussières que de baissières ≈ 0 ({_p6}, {_p7})")
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
          "lecture hebdo : actualité du jour (pression, synthèse, titres) à la place de celle de la veille, consigne finale unique")
finally:
    comite.OUT, comite.call = _old_out, _old_call
    for _k, _v in _env.items():
        if _v is None:
            os.environ.pop(_k, None)
        else:
            os.environ[_k] = _v
    shutil.rmtree(_tc, ignore_errors=True)

# comité : rapport coupé par la limite de longueur → seconde demande du seul bloc JSON, décisions gardées
_tc = Path(tempfile.mkdtemp())
try:
    _old_out, _old_call = comite.OUT, comite.call
    comite.OUT = _tc
    (_tc / "grain-signal.json").write_text(json.dumps({"cultures": {"ble": {"nom": "Blé"}}}), encoding="utf-8")
    _appels = []
    _bloc = json.dumps({"resume": "R", "cultures": {"ble": {"haussier": ["a"], "baissier": ["b"], "lecture": "c"}}, "calendrier": []})

    def _faux2(messages, system, key, recherche=True, max_tokens=None):
        _appels.append(recherche)
        if recherche:
            return {"content": [{"type": "text", "text": "# Rapport\n\nTrès long rapport coupé au milieu d'une phr"}],
                    "stop_reason": "max_tokens", "usage": {"input_tokens": 10, "output_tokens": 32000}}
        return {"content": [{"type": "text", "text": "```json\n" + _bloc + "\n```"}], "stop_reason": "end_turn", "usage": {}}
    comite.call = _faux2
    _env = {k: os.environ.get(k) for k in ("GS_TODAY", "ANTHROPIC_API_KEY", "GS_COMITE", "GS_DRY")}
    os.environ.update(GS_TODAY="2026-11-09", ANTHROPIC_API_KEY="test", GS_COMITE="force")
    os.environ.pop("GS_DRY", None)
    with _cl.redirect_stdout(_io.StringIO()):
        _rc = comite.main()
    _cj = json.loads((_tc / "comite.json").read_text(encoding="utf-8"))
    _box = json.loads((_tc / "prive" / "a-envoyer.json").read_text(encoding="utf-8"))
    check(_rc == 0 and _appels == [True, False] and _cj["cultures"]["ble"]["haussier"] == ["a"] and "Rapport coupé" in _cj["rapport_md"]
          and not _cj.get("erreur") and _cj["format"] == "lecture" and _box[-1]["titre"] == "Lecture du marché de la semaine",
          "lecture hebdo : rapport coupé, synthèse reprise par une seconde demande sans recherche web")
    check(json.loads(comite.bloc_json('texte {"resume": "x", "cultures": {"ble": {"haussier": ["y"]}}} fin'))["cultures"]["ble"]["haussier"] == ["y"],
          "lecture hebdo : bloc JSON final retrouvé même sans balise ```json")
    os.environ.pop("GS_COMITE", None)
    check(comite.decide_mode(date(2026, 11, 9), {}, {"date": "2026-11-02"}) is None, "lecture hebdo : une seule fois le lundi")
    check(comite.decide_mode(date(2026, 11, 16), {}, {"date": "2026-11-09"}) == "hebdo" and comite.decide_mode(date(2026, 11, 12), {}, {"date": "2026-11-09"}) is None,
          "lecture hebdo : le lundi suivant, pas en semaine (plus de comité d'alerte)")
finally:
    comite.OUT, comite.call = _old_out, _old_call
    for _k, _v in _env.items():
        if _v is None:
            os.environ.pop(_k, None)
        else:
            os.environ[_k] = _v
    shutil.rmtree(_tc, ignore_errors=True)

# rapport du matin : un par jour, du lundi au samedi, seulement sur le calcul du jour
_tr = Path(tempfile.mkdtemp())
try:
    import send_alerts as _sa2  # noqa: E402

    (_tr / "grain-signal.json").write_text(json.dumps({"date": "2026-11-10"}), encoding="utf-8")
    _old_today = os.environ.get("GS_TODAY")
    os.environ["GS_TODAY"] = "2026-11-10"
    _a1 = _sa2.rapport_attendu(_tr)
    (_tr / "etat.json").write_text(json.dumps({"envoyes": {"rapport:2026-11-10": "2026-11-10T06:31:00+00:00"}}), encoding="utf-8")
    _a2 = _sa2.rapport_attendu(_tr)
    os.environ["GS_TODAY"] = "2026-11-11"
    _a3 = _sa2.rapport_attendu(_tr)  # données de la veille : calcul du jour pas encore passé
    os.environ["GS_TODAY"] = "2026-11-15"
    (_tr / "grain-signal.json").write_text(json.dumps({"date": "2026-11-15"}), encoding="utf-8")
    _a4 = _sa2.rapport_attendu(_tr)  # dimanche
    check(_a1 == "rapport:2026-11-10" and _a2 is None and _a3 is None and _a4 is None,
          "rapport du matin : attendu une fois par jour, pas sur des données de la veille ni le dimanche")
finally:
    if _old_today is None:
        os.environ.pop("GS_TODAY", None)
    else:
        os.environ["GS_TODAY"] = _old_today
    shutil.rmtree(_tr, ignore_errors=True)

# actualités : réponse mal formée (guillemet non échappé) → articles bien formés repris un par un, synthèse à part
import actualites as _act  # noqa: E402
_bad = ('{"articles": [{"id": "x1", "pertinent": true, "impacts": {"ble": 1}}, {"id": "x2", "titre_fr": "Il dit "non"", "impacts": {}},'
        ' {"id": "x3", "pertinent": false}], "synthese": "Blé soutenu \\"fort\\""}')
_j = _act.lire_json(_bad)
check([a["id"] for a in _j["articles"]] == ["x1", "x3"] and _j["synthese"] == 'Blé soutenu "fort"',
      f"actualités : réponse mal formée, articles valides et synthèse récupérés ({_j})")
check(build.nom_source("yahoo_TTF=F") == "Gaz TTF (Yahoo Finance)" and build.nom_source("euronext_EBM").startswith("Euronext Blé")
      and build.nom_source("cftc_001602").startswith("Positions des fonds CFTC") and build.nom_source("usda") == "Bilans USDA",
      "alertes de panne : nom lisible de la source")

# météo : régions françaises (pays FR) et grands bassins, poids par culture qui somment à 1, zones pesées qui existent
_mt = json.loads((HERE / "config.json").read_text(encoding="utf-8"))["meteo"]
_fr = [k for k, v in _mt["zones"].items() if v.get("pays") == "FR"]
check(len(_fr) == 9 and "Hauts-de-France" in _fr and "Grand Est" in _fr and _mt["zones"]["Grand Est"].get("ancien") == "Champagne"
      and all(abs(sum(w.values()) - 1) < 0.01 and set(w) <= set(_mt["zones"]) for w in _mt["cultures"].values()),
      "météo : 9 régions françaises, poids par culture = 1, historique des anciennes zones repris")

# prix aberrants : 0, négatif, hors d'échelle ou saut isolé écartés ; un nouveau niveau confirmé le lendemain est gardé
_rw = lambda d, v, m="2026-12": {"date": d, "product": "EBM", "maturity": m, "settle": v}  # noqa: E731
_n = build.nettoyer([_rw("2026-11-02", "220"), _rw("2026-11-03", "0"), _rw("2026-11-04", "-5"), _rw("2026-11-05", "1e9"), _rw("2026-11-06", "nan"),
                     _rw("2026-11-09", "22.1"), _rw("2026-11-10", "222"), _rw("2026-11-12", "300"), _rw("2026-11-13", "301"), _rw("2026-11-14", "305")],
                    lambda r: (r["product"], r["maturity"]), "settle")
check([r["settle"] for r in _n] == ["220", "222", "300", "301", "305"],
      f"prix aberrants écartés (0, négatif, 1e9, nan, virgule décalée) ; nouveau niveau gardé dès son premier jour ({[r['settle'] for r in _n]})")
_n = build.nettoyer([_rw("2026-11-02", "505"), _rw("2026-11-03", "400"), _rw("2026-11-04", "517"), _rw("2026-11-05", "520"), _rw("2026-11-06", "640")],
                    lambda r: (r["product"], r["maturity"]), "settle")
check([r["settle"] for r in _n] == ["505", "517", "520"],
      f"pic isolé écarté (la séance d'après revient au niveau d'avant), le dernier prix en saut attend confirmation ({[r['settle'] for r in _n]})")

# prix physiques rangés la veille par erreur (relevé du matin daté du jour précédent) : redatés d'après leur table, sans doublon
import tempfile as _tf  # noqa: E402
_ph = Path(_tf.mkdtemp()) / "physique_hist.csv"
with _ph.open("w", encoding="utf-8", newline="") as _fh:  # place avec espace insécable : même série
    csv.writer(_fh).writerows([["date", "page", "place", "echeance", "titre", "prix"],
                               ["2026-11-09", "orge_brassicole", "Creil, Etincel Fob", "janv. - juin", "/t +0,75 €/t 09 novembre Etincel", "209.0"],
                               ["2026-11-09", "orge_brassicole", "Creil, Etincel\xa0Fob", "janv. - juin", "€/t +0,5 €/t 10 novembre Etincel", "209.5"],
                               ["2026-11-10", "orge_brassicole", "Creil, Etincel Fob", "janv. - juin", "€/t +0,5 €/t 10 novembre Etincel", "209.5"],
                               ["2026-11-10", "orge_brassicole", "Creil, Etincel\xa0Fob", "janv. - juin", "€/t +2,5 €/t 11 novembre Etincel", "211.75"],
                               ["2026-11-11", "orge_brassicole", "Creil, Etincel Fob", "janv. - juin", "€/t +2,5 €/t 11 novembre Etincel", "211.75"]])
_pr = [(r["date"], r["prix"]) for r in build.physique(_ph)]
check(_pr == [("2026-11-09", "209.0"), ("2026-11-10", "209.5"), ("2026-11-11", "211.75")],
      f"prix physiques redatés d'après leur table, sans doublon, espaces insécables compris ({_pr})")
import collect as _col  # noqa: E402
check(_col.date_publiee(date(2026, 11, 11), date(2026, 11, 11)) == date(2026, 11, 11)
      and _col.date_publiee(date(2026, 10, 1), date(2026, 11, 11)) == date(2026, 11, 10),
      "prix physiques : date de la table gardée (même lue le matin), date trop ancienne ramenée à la dernière séance")

# accès aux articles : balise des éditeurs ; les menus « réservé aux abonnés » des pages libres ne comptent pas
check(collect.acces_page('<script type="application/ld+json">{"isAccessibleForFree": false}</script>') == "abonnes"
      and collect.acces_page('<script>{"isAccessibleForFree":"True"}</script> Contenu réservé aux abonnés') == "entier"
      and collect.acces_page("<nav>Contenu réservé aux abonnés · Déjà abonné ?</nav><p>Texte libre</p>") is None,
      "accès aux articles : abonnés ou disponible en entier d'après la balise de l'éditeur")
_sites = {"Bloomberg.com": "abonnes"}
check(collect.acces_article({"url": "", "source": "Bloomberg.com"}, _sites) == ("abonnes", None)
      and collect.acces_article({"url": "", "source": "Inconnu"}, _sites) == (None, None),
      "accès aux articles : page illisible → site connu, sinon rien d'affiché")

# avant l'ouverture : vote de trois indices, journal noté le lendemain
_o = dec.ouverture(0.8, 0.6, "neutre")
check(_o["total"] == 2 and _o["orientation"] == "hausse" and _o["mesurable"] == 1
      and dec.ouverture(-0.2, None, "baissière")["orientation"] == "legere_baisse"
      and dec.ouverture(0.3, -0.1, "neutre")["orientation"] == "partage",
      "avant l'ouverture : Chicago > 0,5 %, actualité ≥ 0,5 et technique comptent chacun pour un indice")
check(dec.prochaine_seance(date(2026, 11, 12)) == "2026-11-12" and dec.prochaine_seance(date(2026, 11, 14)) == "2026-11-16",
      "avant l'ouverture : prochaine séance (samedi → lundi)")
_cu = {"ble": {"seance": "2026-11-11", "var1j": 2.5, "ouverture": {"total": 1}}}
_j = dec.journal_ouverture([], _cu, "2026-11-12")
_cu2 = {"ble": {"seance": "2026-11-12", "var1j": -1.0, "ouverture": {"total": -2}}}
_j = dec.journal_ouverture(_j, _cu2, "2026-11-13")
check(_j == [{"pour": "2026-11-12", "cult": "ble", "total": 1, "var": -1.0}, {"pour": "2026-11-13", "cult": "ble", "total": -2}]
      and dec.bilan_ouverture(_j, "ble") == {"justes": 0, "notees": 1}
      and dec.journal_ouverture(_j, _cu2, "2026-11-13") == _j,
      "avant l'ouverture : orientation notée à la séance suivante, sans doublon au 2e calcul du matin")
_rows = []
import random as _rnd  # noqa: E402
_r = _rnd.Random(3)
_px, _cb, _d0 = 200.0, 500.0, date(2024, 1, 1)
_yh = {"ZW=F": {"serie": {}}, "ZS=F": {"serie": {}}, "ZC=F": {"serie": {}}}
for _i in range(400):
    _dd = (_d0 + _td(days=_i)).isoformat()
    _mv = _r.gauss(0, 1)
    _cb *= 1 + _mv / 100
    for _t in _yh:
        _yh[_t]["serie"][_dd] = _cb
    _px *= 1 + (_mv if _i else 0) / 100 * 0.5 + _r.gauss(0, 0.3) / 100
    _rows.append({"date": (_d0 + _td(days=_i + 1)).isoformat(), "product": "EBM", "maturity": "2030-03", "settle": str(round(_px, 2))})
_bo = bt.backtest_ouverture(_yh, _rows)
check(_bo.get("ble") and _bo["ble"]["2"]["seances"] > 0 and _bo["ble"]["1"]["part"] is not None,
      f"avant l'ouverture : backtest Chicago + technique ({_bo.get('ble')})")

for st, name in results:
    print(st, name)
fails = [n for s, n in results if s != "OK  "]
print(f"{len(results) - len(fails)}/{len(results)} tests réussis")
sys.exit(1 if fails else 0)
