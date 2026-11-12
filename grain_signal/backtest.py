"""
Bulletin des grains — backtest : ce que valent les lectures de l'outil sur l'historique.

Pour chaque lecture affichée, le cours a-t-il ensuite évolué autrement que par hasard ?
  - lecture technique (hausse / neutre / baisse) : variation des 20 et 60 séances suivantes, blé et maïs de Chicago convertis
    en €/t depuis 2000, blé, colza et maïs d'Euronext depuis 2019 ;
  - humeur du marché (peur ↔ euphorie) : mêmes marchés ;
  - risque géopolitique (Caldara et Iacoviello) : blé de Chicago.
Chaque résultat est comparé à des cours tirés au sort de même longueur et de même nervosité (le « hasard seul »).

Sortie : data/grain/backtest.json (page, onglet Méthode).   python grain_signal/backtest.py
"""
import bisect
import csv
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from commun import load  # noqa: E402
from indicators import rsi, score_serie, sens, sma  # noqa: E402,F401  (rsi, sma : aussi utilisés par les scripts de recherche)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "data" / "grain"
PRIV = OUT / "prive"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------------------- outils statistiques
def _rang(x):
    o = sorted(range(len(x)), key=lambda i: x[i])
    r = [0] * len(x)
    for k, i in enumerate(o):
        r[i] = k
    return r


def spearman(a, b):
    """Corrélation de rang (−1 à +1) : l'indicateur classe-t-il les rendements suivants ?"""
    n = len(a)
    if n < 30:
        return None
    ra, rb = _rang(a), _rang(b)
    m = (n - 1) / 2
    cov = sum((x - m) * (y - m) for x, y in zip(ra, rb))
    var = sum((x - m) ** 2 for x in ra)
    return round(cov / var, 3) if var else None


def fonds_indice(cftc, cult):
    """Indice 0-100 de la position nette des fonds sur 3 ans (CFTC, rapport publié 3 jours après), à une date donnée."""
    cot = [([x["date"] for x in v["serie"]], [x["long"] - x["short"] for x in v["serie"]])
           for v in cftc.values() if isinstance(v, dict) and v.get("culture") == cult and v.get("serie")]

    def f(d):
        lim = (datetime.fromisoformat(d) - timedelta(days=3)).date().isoformat()
        sc = []
        for dd, nets in cot:
            j = bisect.bisect_right(dd, lim) - 1
            if j < 52:
                continue
            w = nets[max(0, j - 155):j + 1]
            lo, hi = min(w), max(w)
            sc.append((nets[j] - lo) / (hi - lo) * 100 if hi > lo else 50.0)
        return sum(sc) / len(sc) if sc else None
    return f if cot else None


def par_humeur(dates, p, idx, horizons=(20, 60)):
    """Rendement moyen des `h` séances suivantes selon l'humeur du jour (tranches de 20 points), et par période."""
    sys.path.insert(0, str(HERE))
    import decisions as dec  # noqa: E402

    out = {}
    for h in horizons:
        pts = [(idx[i], p[i + h] / p[i] - 1, dates[i]) for i in range(len(p) - h) if idx[i] is not None]
        if len(pts) < 200:
            continue
        o = {"points": len(pts), "moyenne": round(sum(x[1] for x in pts) / len(pts) * 100, 1),
             "correlation": spearman([x[0] for x in pts], [x[1] for x in pts]), "tranches": {}, "periodes": {}}
        for hi_, code, lib in dec.PSY_ETATS:
            lo_ = {"peur_extreme": 0, "peur": 20, "neutre": 40, "optimisme": 60, "euphorie": 80}[code]
            sub = [x[1] for x in pts if lo_ <= x[0] < hi_]
            if len(sub) >= 20:
                o["tranches"][code] = {"libelle": lib, "moyenne": round(sum(sub) / len(sub) * 100, 1),
                                       "hausses": round(sum(1 for x in sub if x > 0) / len(sub) * 100), "n": len(sub)}
        for lab, a, b in (("2000-2012", "2000", "2012"), ("2013-2019", "2013", "2019"), ("2020 et après", "2020", "2100")):
            sel = [x for x in pts if a <= x[2][:4] <= b]
            if len(sel) >= 200:
                o["periodes"][lab] = spearman([x[0] for x in sel], [x[1] for x in sel])
        out[str(h)] = o
    return out


def bruit(dates, p, essais=30):
    """Corrélation obtenue par pur hasard : même test sur des marches aléatoires de même longueur et de même volatilité (90e
    percentile des |corrélations|). Les jours se chevauchent : sur 7 ans, le hasard seul donne souvent ±0,1 ou plus."""
    sys.path.insert(0, str(HERE))
    import decisions as dec  # noqa: E402

    lr = [math.log(p[i] / p[i - 1]) for i in range(1, len(p)) if p[i] > 0 and p[i - 1] > 0]
    sd = (sum(x * x for x in lr) / len(lr)) ** 0.5 if lr else 0.015
    out = {}
    rng = random.Random(42)
    rhos = {"20": [], "60": []}
    for _ in range(essais):
        v = [100.0]
        for _ in range(len(p) - 1):
            v.append(v[-1] * math.exp(rng.gauss(0, sd)))
        comp = dec.psy_series(v)
        idx = [dec.psy_indice({k: comp[k][i] for k in ("rsi", "ecart200", "elan20")}) for i in range(len(v))]
        for h in (20, 60):
            pts = [(idx[i], v[i + h] / v[i] - 1) for i in range(len(v) - h) if idx[i] is not None]
            c = spearman([x[0] for x in pts], [x[1] for x in pts])
            if c is not None:
                rhos[str(h)].append(abs(c))
    for h, l in rhos.items():
        if l:
            out[h] = round(sorted(l)[int(len(l) * 0.9) - 1], 3)
    return out


def backtest_psychologie(yahoo, cftc):
    """L'humeur du marché (peur ↔ euphorie) annonce-t-elle la suite ? Blé et maïs de Chicago depuis 2000 (fonds CFTC dès 2006),
    blé, colza et maïs d'Euronext depuis 2019 (série ajustée des changements d'échéance)."""
    sys.path.insert(0, str(HERE))
    import build  # noqa: E402
    import decisions as dec  # noqa: E402

    res = {}

    def serie(nom, d, p, cult):
        if len(p) < 800:
            return
        comp = dec.psy_series(p)
        ff = fonds_indice(cftc, cult) if cult in ("ble", "mais") else None
        idx = [dec.psy_indice({k: comp[k][i] for k in ("rsi", "ecart200", "elan20")}, ff(d[i]) if ff else None) for i in range(len(p))]
        r = par_humeur(d, p, idx)
        if r:
            res[nom] = {"depuis": d[0], "fonds": bool(ff), **r, "bruit": bruit(d, p)}
    for tk, cult, nom in (("ZW=F", "ble", "Blé Chicago"), ("ZC=F", "mais", "Maïs Chicago")):
        s = (yahoo.get(tk) or {}).get("serie") or {}
        d = sorted(s)
        serie(nom, d, [s[x] for x in d], cult)
    path = PRIV / "euronext.csv"
    rows_e = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    for prod, cult, nom in (("EBM", "ble", "Blé Euronext"), ("ECO", "colza", "Colza Euronext"), ("EMA", "mais", "Maïs Euronext")):
        d, p, *_ = build.continuous(rows_e, prod)
        serie(nom, d, p, cult)
    return res


def backtest_geopolitique(yahoo):
    """Le risque géopolitique (moyenne 30 jours de l'indice quotidien) annonce-t-il le prix du blé à 20 et 60 séances ?"""
    g = load(PRIV / "gpr.json", {}).get("quotidien") or []
    s = (yahoo.get("ZW=F") or {}).get("serie") or {}
    if len(g) < 1000 or len(s) < 1000:
        return {"erreur": "historiques insuffisants"}
    gd, gv = [x[0] for x in g], [x[1] for x in g]
    d = sorted(s)
    p = [s[x] for x in d]

    def mesure(prix, h):
        a, b = [], []
        for i in range(len(prix) - h):
            j = bisect.bisect_right(gd, d[i]) - 1
            if j < 30:
                continue
            a.append(sum(gv[j - 29:j + 1]) / 30)
            b.append(prix[i + h] / prix[i] - 1)
        if len(a) < 200:
            return None
        q = sorted(a)[int(len(a) * 0.9)]
        hi = [y for x, y in zip(a, b) if x >= q]
        return a, b, spearman(a, b), (sum(hi) / len(hi) - sum(b) / len(b)) * 100, len(hi)

    out = {"depuis": max(gd[0], d[0])}
    # hasard : même indice géopolitique, cours tirés au sort de même nervosité (90e percentile des écarts obtenus)
    rng = random.Random(7)
    lr = [math.log(p[i] / p[i - 1]) for i in range(1, len(p)) if p[i] > 0 and p[i - 1] > 0]
    sd = (sum(x * x for x in lr) / len(lr)) ** 0.5
    sims = []
    for _ in range(30):
        v = [100.0]
        for _ in range(len(p) - 1):
            v.append(v[-1] * math.exp(rng.gauss(0, sd)))
        sims.append(v)
    for h in (20, 60):
        m = mesure(p, h)
        if not m:
            continue
        a, b, rho, ecart, n = m
        br = [mesure(v, h) for v in sims]
        br = [x for x in br if x]
        out[str(h)] = {"correlation": rho, "points": len(a), "moyenne": round(sum(b) / len(b) * 100, 1),
                       "tendu": round(sum(b) / len(b) * 100 + ecart, 1), "n_tendu": n,
                       "bruit_correlation": round(sorted(abs(x[2]) for x in br)[int(len(br) * 0.9) - 1], 3) if br else None,
                       "bruit_tendu": round(sorted(abs(x[3]) for x in br)[int(len(br) * 0.9) - 1], 1) if br else None}
    return out


# ----------------------------------------------------------------------------------------- lecture technique
def marche_aleatoire(p, rng):
    """Cours tirés au sort : même longueur, même nervosité (écart-type des variations quotidiennes), sans tendance."""
    lr = [math.log(p[i] / p[i - 1]) for i in range(1, len(p)) if p[i] > 0 and p[i - 1] > 0]
    sd = (sum(x * x for x in lr) / len(lr)) ** 0.5 if lr else 0.015
    v = [100.0]
    for _ in range(len(p) - 1):
        v.append(v[-1] * math.exp(rng.gauss(0, sd)))
    return v


def par_lecture(p, horizons=(20, 60)):
    """Variation moyenne des `h` séances suivantes selon la lecture technique du jour ; écart « hausse » − « baisse » (points)."""
    sc = score_serie(p)
    out = {}
    for h in horizons:
        g = {"haussière": [], "neutre": [], "baissière": []}
        for i in range(len(p) - h):
            if sc[i] is not None:
                g[sens(sc[i])].append(p[i + h] / p[i] - 1)
        grp = {k: {"moyenne": round(sum(v) / len(v) * 100, 1), "hausses": round(sum(1 for x in v if x > 0) / len(v) * 100), "n": len(v)}
               for k, v in g.items() if len(v) >= 20}
        ecart = (round(grp["haussière"]["moyenne"] - grp["baissière"]["moyenne"], 1)
                 if "haussière" in grp and "baissière" in grp else None)
        out[str(h)] = {"groupes": grp, "ecart": ecart}
    return out


def backtest_technique(yahoo, essais=30):
    """La lecture technique annonce-t-elle la suite ? Chicago (€/t) depuis 2000, Euronext depuis 2019 (série ajustée)."""
    sys.path.insert(0, str(HERE))
    import build  # noqa: E402

    res = {}
    series = []
    for tk, nom in (("ZW=F", "Blé Chicago"), ("ZC=F", "Maïs Chicago")):
        d, v = build.proxy_eur(yahoo, tk)
        series.append((nom, d, v))
    path = PRIV / "euronext.csv"
    rows_e = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    for prod, nom in (("EBM", "Blé Euronext"), ("ECO", "Colza Euronext"), ("EMA", "Maïs Euronext")):
        d, v, *_ = build.continuous(rows_e, prod)
        series.append((nom, d, v))
    for nom, d, p in series:
        if len(p) < 500:
            continue
        r = par_lecture(p)
        rng = random.Random(11)
        sims = [par_lecture(marche_aleatoire(p, rng)) for _ in range(essais)]
        for h, o in r.items():
            ec = sorted(abs(x[h]["ecart"]) for x in sims if x[h]["ecart"] is not None)
            o["bruit"] = round(ec[int(len(ec) * 0.9) - 1], 1) if ec else None
        res[nom] = {"depuis": d[0], **r}
    return res


def backtest_ouverture(yahoo, rows_e=None):
    """Avant l'ouverture : quand Chicago (clôture de la veille, après Euronext) et la lecture technique de la veille penchent d'un
    côté, la séance Euronext suivante va-t-elle dans ce sens ? Part des séances suivies, à comparer à 50 % : « 1 » = un seul des
    deux indices donne un sens (l'autre neutre), « 2 » = les deux d'accord. L'actualité n'a pas encore d'historique assez long :
    l'orientation complète est suivie au jour le jour (journal dans etat.json)."""
    sys.path.insert(0, str(HERE))
    import build  # noqa: E402
    import decisions as dec  # noqa: E402

    if rows_e is None:
        path = PRIV / "euronext.csv"
        rows_e = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    out = {}
    for cult, prod in (("ble", "EBM"), ("colza", "ECO"), ("mais", "EMA")):
        d, v, *_ = build.continuous(rows_e, prod)
        s = (yahoo.get(dec.OUVERTURE_CHICAGO[cult]) or {}).get("serie") or {}
        cd = sorted(s)
        if len(d) < 300 or len(cd) < 300:
            continue
        sc = score_serie(v)
        res = {1: [0, 0], 2: [0, 0]}
        for i in range(1, len(d)):
            j = bisect.bisect_left(cd, d[i]) - 1  # dernière séance de Chicago avant le jour de la séance
            if j < 1 or cd[j] < d[i - 1] or sc[i - 1] is None or v[i] == v[i - 1]:
                continue
            vt = dec.vote_chicago((s[cd[j]] / s[cd[j - 1]] - 1) * 100) + dec.vote_technique(sens(sc[i - 1]))
            if vt:
                r = res[abs(vt)]
                r[0] += 1
                r[1] += (v[i] > v[i - 1]) == (vt > 0)
        out[cult] = {"depuis": d[0], **{str(k): {"seances": n, "suivies": k_, "part": round(k_ / n * 100) if n else None}
                                          for k, (n, k_) in res.items()}}
    return out


def main():
    longue = load(PRIV / "yahoo_long.json", {})
    yahoo = longue if all(k in longue for k in ("ZW=F", "ZC=F", "EURUSD=X")) else load(PRIV / "yahoo.json", {})
    # avant l'ouverture : séries longues complétées des séances récentes (et du soja, absent de l'historique long)
    yahoo_ouv = {k: dict(v) for k, v in longue.items() if isinstance(v, dict)}
    for k, v in load(PRIV / "yahoo.json", {}).items():
        if isinstance(v, dict) and isinstance(v.get("serie"), dict):
            yahoo_ouv.setdefault(k, {"serie": {}})
            yahoo_ouv[k]["serie"] = {**(yahoo_ouv[k].get("serie") or {}), **v["serie"]}
    cftc = load(PRIV / "cftc_long.json", {}) or load(PRIV / "cftc.json", {})
    for k, v in list(cftc.items()):  # fichier court (calcul du matin) : culture prise dans la configuration
        if isinstance(v, dict) and "culture" not in v and k in CFG["cftc"]["marches"]:
            v["culture"] = CFG["cftc"]["marches"][k]["culture"]
    res = {"genere": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "technique": backtest_technique(yahoo), "psychologie": backtest_psychologie(yahoo, cftc),
           "geopolitique": backtest_geopolitique(yahoo), "ouverture": backtest_ouverture(yahoo_ouv),
           "limites": ["Chicago converti en €/t : la tendance d'Euronext, pas son niveau ni la base locale.",
                       "Cours Euronext : échéance la plus proche ajustée des changements d'échéance, depuis novembre 2019 seulement.",
                       "Les périodes de 20 et 60 séances se chevauchent : le « hasard seul » donne l'ordre de grandeur à dépasser.",
                       "Le passé ne garantit pas l'avenir."]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "backtest.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for nom, v in res["technique"].items():
        o = v["60"]
        print(f"Technique — {nom} à 60 séances : " + ", ".join(f"{k} {g['moyenne']:+.1f} %" for k, g in o["groupes"].items())
              + f" ; écart {o['ecart']} pt (hasard ±{o['bruit']})")
    for nom, v in res["psychologie"].items():
        for h, o in ((k, x) for k, x in v.items() if k in ("20", "60")):
            print(f"Humeur — {nom} à {h} séances : corrélation {o['correlation']} (hasard ±{v['bruit'].get(h)}), "
                  + ", ".join(f"{t['libelle']} {t['moyenne']:+.1f} %" for t in o["tranches"].values()))
    print("Risque géopolitique → blé :", res["geopolitique"])
    for cult, o in res["ouverture"].items():
        print(f"Avant l'ouverture — {cult} : 1 indice {o['1']['part']} % suivi ({o['1']['seances']} séances), "
              f"2 indices d'accord {o['2']['part']} % ({o['2']['seances']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
