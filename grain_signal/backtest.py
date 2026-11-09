"""
Grain Signal — backtest : ce que les règles auraient rapporté sur les campagnes passées.

Ventes de céréales (blé, maïs) : prix quotidiens du marché américain convertis en €/t (Yahoo, depuis 2000, EUR/USD du jour),
faute d'historique Euronext long ; c'est la TENDANCE qui est testée, pas le niveau exact d'Euronext ni la base locale.
  S0  tout vendre à la moisson (moyenne du mois de récolte)
  S1  même quantité chaque mois, de la moisson à juin suivant
  S2  calendrier de tranches de Grain Signal, chaque tranche vendue en moyenne sur sa période
  S3  S2 + timing technique (au creux : ordre au-dessus du marché, rempli au rebond ou en fin de période)
  S4  S3 + tendance (score technique ≤ −1 : tranche suivante avancée ; ≥ +0,5 : tranche décalée), 35 % au plus avant la moisson
  S5  outil complet sans le comité : S3 + note de marché du matin (technique 45 %, fonds CFTC 20 % dès 2006, macro 20 % :
      euro-dollar et Brent), mêmes seuils ; la météo et le comité IA ne sont pas rejouables sur le passé
Même test sur les cours officiels d'Euronext (blé, colza, maïs, échéance la plus proche) depuis novembre 2019, et par période.
Achats d'azote (urée, mensuel Banque mondiale, depuis 1960) : besoins d'une campagne achetés d'avril à janvier.
  E0  tout acheter en janvier          E1  même quantité chaque mois
  E2  saison seule (avril à juillet)   E3  règles Grain Signal (ratio urée/blé, rattrapage du gaz, saison, 50 % au plus tard fin octobre)

Sortie : data/grain/backtest.json (page, onglet Méthode).   python grain_signal/backtest.py
"""
import bisect
import csv
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "data" / "grain"
PRIV = OUT / "prive"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
TONNE = {"ZW=F": 36.744, "ZC=F": 39.368}
CULTURES = {"ble": ("ZW=F", 7, "Blé (Chicago converti en €/t)"), "mais": ("ZC=F", 10, "Maïs (Chicago converti en €/t)")}


def load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


# ----------------------------------------------------------------------------------------- indicateurs vectorisés
def sma(x, n):
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x, n):
    k, e, out = 2 / (n + 1), None, []
    for v in x:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def rsi(x, n=14):
    out = [None] * len(x)
    if len(x) <= n:
        return out
    d = [x[i] - x[i - 1] for i in range(1, len(x))]
    au = sum(max(v, 0) for v in d[:n]) / n
    ad = sum(max(-v, 0) for v in d[:n]) / n
    out[n] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    for i in range(n, len(d)):
        au += (max(d[i], 0) - au) / n
        ad += (max(-d[i], 0) - ad) / n
        out[i + 1] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


def indicateurs(p):
    n = len(p)
    m20, m50 = sma(p, 20), sma(p, 50)
    macd = [a - b for a, b in zip(ema(p, 12), ema(p, 26))]
    sig = ema(macd, 9)
    hist = [a - b for a, b in zip(macd, sig)]
    r = rsi(p)
    pb, hi, lo = [None] * n, [None] * n, [None] * n
    for i in range(n):
        if i >= 19:
            w = p[i - 19:i + 1]
            mu = sum(w) / 20
            sd = math.sqrt(sum((v - mu) ** 2 for v in w) / 19)
            pb[i] = (p[i] - (mu - 2 * sd)) / (4 * sd) if sd else 0.5
        w3 = p[max(0, i - 62):i + 1]
        hi[i], lo[i] = max(w3), min(w3)
    return {"m20": m20, "m50": m50, "hist": hist, "rsi": r, "pb": pb, "hi": hi, "lo": lo}


def feu(I, p, i, rsi_creux=40, pos_creux=20):
    """Même logique que indicators.feu_execution, sur des tableaux."""
    r, pb = I["rsi"][i], I["pb"][i]
    if r is None:
        return "executer"
    if r < 30 or (pb is not None and pb < 0.05):
        return "attendre"
    hi, lo = I["hi"][i], I["lo"][i]
    pos = (p[i] - lo) / (hi - lo) * 100 if hi > lo else 50
    if r < rsi_creux and pos <= pos_creux:
        return "attendre"
    if r > 70 and i >= 5 and I["hist"][i] < I["hist"][i - 5]:
        return "accelerer"
    return "executer"


def score(I, p, i):
    """Note technique de −2 à +2 (tendance MM50, MACD, excès RSI), comme indicators.score_technique (sans divergence)."""
    s = 0.0
    m50 = I["m50"]
    if m50[i] is not None and i >= 10 and m50[i - 10] is not None:
        e, pente = p[i] / m50[i] - 1, m50[i] / m50[i - 10] - 1
        s += 1 if (e > 0 and pente > 0) else -1 if (e < 0 and pente < 0) else 0
    h = I["hist"]
    s += 0.5 if h[i] > 0 else -0.5
    if i >= 5:
        s += 0.25 if h[i] > h[i - 5] else -0.25
    r = I["rsi"][i]
    if r is not None:
        s += 0.5 if r < 30 else -0.5 if r > 70 else 0
    return max(-2, min(2, s))


# ----------------------------------------------------------------------------------------- ventes
def ym_idx(dates):
    """Index du premier et du dernier jour de chaque mois (année, mois)."""
    idx = {}
    for i, d in enumerate(dates):
        k = (int(d[:4]), int(d[5:7]))
        if k not in idx:
            idx[k] = [i, i]
        idx[k][1] = i
    return idx


def rel(hy, r):
    k = hy * 12 + r - 1
    return k // 12, k % 12 + 1


def window(idx, hy, a, b):
    s, e = idx.get(rel(hy, a)), idx.get(rel(hy, b))
    return (s[0], e[1]) if s and e else None


def campagne(p, I, idx, hy, tranches, harvest_m, opts, note_fn=None):
    """Prix moyen obtenu (€/t) par chaque stratégie pour la récolte hy. None si la campagne n'est pas complète."""
    wins = [window(idx, hy, a, b) for a, b, _ in tranches]
    if any(w is None for w in wins):
        return None
    pcts = [pct for _, _, pct in tranches]
    res = {}
    hm = idx.get((hy, harvest_m + 1 if harvest_m < 12 else 12))  # mois qui suit le début de la moisson (août, novembre)
    if not hm:
        return None
    res["S0"] = sum(p[hm[0]:hm[1] + 1]) / (hm[1] - hm[0] + 1)
    months = [idx.get(rel(hy, m)) for m in range(harvest_m, 19)]
    if any(m is None for m in months):
        return None
    res["S1"] = sum(sum(p[a:b + 1]) / (b - a + 1) for a, b in months) / len(months)
    res["S2"] = sum(pct * sum(p[a:b + 1]) / (b - a + 1) for (a, b), pct in zip(wins, pcts)) / 100

    def run(use_trend, fn=None):
        recette, reste_report = 0.0, 0.0
        vendu_avant = 0.0
        for k, ((a, b), pct) in enumerate(zip(wins, pcts)):
            pre = rel(hy, tranches[k][1]) < (hy, harvest_m)
            q = pct + reste_report
            reste_report = 0.0
            if use_trend:
                sc = fn(a) if fn else score(I, p, a)
                sc = score(I, p, a) if sc is None else sc
                last = k == len(wins) - 1
                if sc >= 0.5 and not last:
                    reste_report, q = q, 0.0  # tranche décalée sur la suivante
                elif sc <= -1 and not last:
                    extra = pcts[k + 1]
                    if pre:
                        extra = max(0.0, min(extra, 35 - vendu_avant - q))
                    pcts[k + 1] -= extra  # tranche suivante avancée
                    recette += extra * p[a]
                    if pre:
                        vendu_avant += extra
            if q <= 0:
                continue
            if pre:
                vendu_avant += q
            # timing dans la période : au creux, ordre au-dessus du marché ; sinon vente étalée sur la période
            ndays = b - a + 1
            reste, niveau = q, None
            for i in range(a, b + 1):
                if reste <= 1e-9:
                    break
                f = feu(I, p, i, opts["rsi"], opts["pos"])
                if niveau is not None and p[i] >= niveau:
                    recette += reste * niveau
                    reste = 0
                    break
                if f == "attendre":
                    if niveau is None:
                        m20 = I["m20"][i]
                        lo, hi = I["lo"][i], I["hi"][i]
                        cand = [x for x in (m20, lo + 0.382 * (hi - lo)) if x and x > p[i] * 1.003]
                        niveau = min(cand) if cand else p[i] * 1.02
                    continue
                if f == "accelerer":
                    recette += reste * p[i]
                    reste = 0
                    break
                if niveau is None:
                    part = min(reste, q / ndays)
                    recette += part * p[i]
                    reste -= part
            if reste > 1e-9:
                recette += reste * p[b]  # fin de période : le reste part au dernier cours
        return recette / 100

    pcts_orig = list(pcts)
    res["S3"] = run(False)
    pcts[:] = pcts_orig
    res["S4"] = run(True)
    pcts[:] = pcts_orig
    if note_fn:
        res["S5"] = run(True, note_fn)
        pcts[:] = pcts_orig
    return res


def note_marche(dates, p, I, cult, cftc, yahoo):
    """Note de marché du matin rejouée jour par jour (comme build.py) : technique 45 %, fonds 20 %, macro 20 % (poids de config.json),
    renormalisés sur les parties disponibles ce jour-là. Fonds : indice de la position nette des fonds sur 3 ans au dernier rapport
    publié (vendredi pour le mardi : 3 jours de décalage), lu à contre-courant. Macro : variation sur 20 séances de l'euro-dollar
    (et du Brent pour le colza et le maïs)."""
    W = CFG["poids"]
    series = [v["serie"] for v in cftc.values() if isinstance(v, dict) and v.get("culture") == cult and v.get("serie")]
    cot = []
    for ser in series:
        dd = [x["date"] for x in ser]
        nets = [x["long"] - x["short"] for x in ser]
        cot.append((dd, nets))
    fx = (yahoo.get("EURUSD=X") or {}).get("serie") or {}
    br = (yahoo.get("BZ=F") or {}).get("serie") or {}
    fxd, brd = sorted(fx), sorted(br)

    def chg20(keys, ser, d):
        j = bisect.bisect_right(keys, d) - 1
        if j < 20:
            return None
        return (ser[keys[j]] / ser[keys[j - 20]] - 1) * 100

    def cot_at(d):
        lim = (datetime.fromisoformat(d) - timedelta(days=3)).date().isoformat()
        sc = []
        for dd, nets in cot:
            j = bisect.bisect_right(dd, lim) - 1
            if j < 19:
                continue
            w = nets[max(0, j - 155):j + 1]
            lo, hi = min(w), max(w)
            idx = (nets[j] - lo) / (hi - lo) * 100 if hi > lo else 50.0
            sc.append(1.5 if idx <= 15 else -1.5 if idx >= 85 else max(-1.0, min(1.0, -(idx - 50) / 35)))
        return sum(sc) / len(sc) if sc else None

    def fn(i):
        d = dates[i]
        parts = {"technique": score(I, p, i), "cot": cot_at(d)}
        e20, b20 = chg20(fxd, fx, d), chg20(brd, br, d)
        if e20 is not None or b20 is not None:
            m = -max(-1, min(1, (e20 or 0) / 2)) * 0.5
            if cult == "colza":
                m += max(-1, min(1, (b20 or 0) / 10)) * 0.75
            elif cult == "mais":
                m += max(-1, min(1, (b20 or 0) / 10)) * 0.25
            parts["macro"] = m
        den = sum(W[k] for k, v in parts.items() if v is not None)
        return sum(W[k] * v for k, v in parts.items() if v is not None) / den if den else None
    return fn


def par_periode(rows, keys, ref):
    """Bilan par décennie (et la dernière période en cours) : un réglage qui ne gagne que sur une période est fragile."""
    out = {}
    for lab, a, b in (("2000-2009", 2000, 2009), ("2010-2019", 2010, 2019), ("2020 et après", 2020, 2100)):
        sub = [r for r in rows if a <= r["recolte"] <= b]
        if len(sub) >= 3:
            out[lab] = bilan(sub, keys, ref)
    return out


def serie_eur(yahoo, tk):
    s = (yahoo.get(tk) or {}).get("serie") or {}
    fx = (yahoo.get("EURUSD=X") or {}).get("serie") or {}
    if not s or not fx:
        return [], []
    fd = sorted(fx)
    dates, vals = [], []
    for d, c in sorted(s.items()):
        j = bisect.bisect_right(fd, d) - 1
        if j < 0 or not c or c <= 0:
            continue
        dates.append(d)
        vals.append(c / 100 * TONNE[tk] / fx[fd[j]])
    return dates, vals


def bilan(rows, keys, ref, achat=False):
    """Écart moyen avec la référence, en €/t (ventes : + = mieux vendu ; achats : + = moins cher payé)."""
    out = {}
    for k in keys:
        diffs = [(r[ref] - r[k]) if achat else (r[k] - r[ref]) for r in rows]
        out[k] = {"moyenne": round(sum(r[k] for r in rows) / len(rows), 1),
                  "ecart_moyen": round(sum(diffs) / len(diffs), 1),
                  "gagnantes": sum(1 for x in diffs if x > 0.05), "campagnes": len(rows),
                  "pire": round(min(diffs), 1), "meilleure": round(max(diffs), 1)}
    return out


def backtest_ventes(yahoo, cftc):
    res = {}
    for cult, (tk, hm, nom) in CULTURES.items():
        d, p = serie_eur(yahoo, tk)
        if len(p) < 800:
            res[cult] = {"nom": nom, "erreur": f"historique trop court ({len(p)} séances)"}
            continue
        I = indicateurs(p)
        idx = ym_idx(d)
        tr = CFG["calendrier"][cult]["tranches"]
        rows = []
        base = {"rsi": 40, "pos": 20}
        nf = note_marche(d, p, I, cult, cftc, yahoo)
        for hy in range(int(d[0][:4]) + 1, int(d[-1][:4])):
            r = campagne(p, I, idx, hy, [list(t) for t in tr], hm, base, nf)
            if r:
                rows.append({"recolte": hy, **{k: round(v, 1) for k, v in r.items()}})
        if len(rows) < 3:
            res[cult] = {"nom": nom, "erreur": "moins de 3 campagnes complètes"}
            continue
        keys = ["S0", "S1", "S2", "S3", "S4", "S5"]
        variantes = []
        for rc in (30, 35, 40, 45):
            for pc in (15, 20, 30):
                vals = [campagne(p, I, idx, r["recolte"], [list(t) for t in tr], hm, {"rsi": rc, "pos": pc}) for r in rows]
                ok = [(v["S3"] - v["S2"]) for v in vals if v]
                variantes.append({"rsi": rc, "pos": pc, "ecart_moyen_vs_S2": round(sum(ok) / len(ok), 2),
                                  "gagnantes": sum(1 for x in ok if x > 0.05), "campagnes": len(ok)})
        variantes.sort(key=lambda v: -v["ecart_moyen_vs_S2"])
        res[cult] = {"nom": nom, "depuis": d[0], "campagnes": rows, "bilan_vs_S1": bilan(rows, keys, "S1"),
                     "bilan_vs_S2": bilan(rows, keys, "S2"), "variantes_timing": variantes, "periodes": par_periode(rows, keys, "S1")}
    return res


EURONEXT = {"ble": ("EBM", 7, "Blé tendre (Euronext)"), "colza": ("ECO", 7, "Colza (Euronext)"), "mais": ("EMA", 10, "Maïs (Euronext)")}


def backtest_euronext(cftc, yahoo):
    """Mêmes stratégies sur les cours officiels d'Euronext (prix réel de l'échéance la plus proche), depuis novembre 2019."""
    sys.path.insert(0, str(HERE))
    import build  # noqa: E402  (front_series : même choix d'échéance que la page)

    path = PRIV / "euronext.csv"
    rows_e = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    res = {}
    for cult, (prod, hm, nom) in EURONEXT.items():
        d, p = build.front_series(rows_e, prod)
        if len(p) < 500:
            res[cult] = {"nom": nom, "erreur": f"historique Euronext encore court ({len(p)} séances) : récupération en cours"}
            continue
        I = indicateurs(p)
        idx = ym_idx(d)
        tr = CFG["calendrier"][cult]["tranches"]
        nf = note_marche(d, p, I, cult, cftc, yahoo)
        rows = []
        for hy in range(int(d[0][:4]), int(d[-1][:4]) + 1):
            r = campagne(p, I, idx, hy, [list(t) for t in tr], hm, {"rsi": 40, "pos": 20}, nf)
            if r:
                rows.append({"recolte": hy, **{k: round(v, 1) for k, v in r.items()}})
        if len(rows) < 3:
            res[cult] = {"nom": nom, "depuis": d[0], "erreur": f"{len(rows)} campagne(s) complète(s) seulement depuis le {d[0]}"}
            continue
        keys = ["S0", "S1", "S2", "S3", "S4", "S5"]
        res[cult] = {"nom": nom, "depuis": d[0], "campagnes": rows, "bilan_vs_S1": bilan(rows, keys, "S1")}
    return res


def comparaison(chicago, euronext):
    """Campagnes communes : les écarts des stratégies sur Chicago et sur Euronext vont-ils dans le même sens ?"""
    out = {}
    for cult in ("ble", "mais"):
        c, e = chicago.get(cult) or {}, euronext.get(cult) or {}
        if "campagnes" not in c or "campagnes" not in e:
            continue
        cc = {r["recolte"]: r for r in c["campagnes"]}
        com = [r for r in e["campagnes"] if r["recolte"] in cc]
        if len(com) < 3:
            continue
        o = {}
        for k in ("S2", "S3", "S4", "S5"):
            ec = [cc[r["recolte"]][k] - cc[r["recolte"]]["S1"] for r in com if k in cc[r["recolte"]] and k in r]
            ee = [r[k] - r["S1"] for r in com if k in r]
            if ec and ee:
                o[k] = {"chicago": round(sum(ec) / len(ec), 1), "euronext": round(sum(ee) / len(ee), 1),
                        "meme_sens": sum(1 for a, b in zip(ec, ee) if (a > 0) == (b > 0)), "campagnes": len(ee)}
        out[cult] = o
    return out


# ----------------------------------------------------------------------------------------- psychologie et géopolitique
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
    import random
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
    out = {"depuis": max(gd[0], d[0])}
    for h in (20, 60):
        a, b = [], []
        for i in range(len(p) - h):
            j = bisect.bisect_right(gd, d[i]) - 1
            if j < 30:
                continue
            a.append(sum(gv[j - 29:j + 1]) / 30)
            b.append(p[i + h] / p[i] - 1)
        if len(a) >= 200:
            q = sorted(a)[int(len(a) * 0.9)]
            hi = [y for x, y in zip(a, b) if x >= q]
            out[str(h)] = {"correlation": spearman(a, b), "points": len(a), "moyenne": round(sum(b) / len(b) * 100, 1),
                           "tendu": round(sum(hi) / len(hi) * 100, 1), "n_tendu": len(hi)}
    return out


# ----------------------------------------------------------------------------------------- achats d'azote
def backtest_engrais():
    path = PRIV / "wb_monthly.csv"
    if not path.exists():
        path = HERE / "seed" / "wb_monthly.csv"
    rows = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append((r["month"], float(r["urea"]), float(r["wheat_hrw"]), float(r["gas_eu"]) if r.get("gas_eu") else None))
            except (ValueError, KeyError):
                continue
    rows.sort()
    by = {m: (u, w, g) for m, u, w, g in rows}
    months = [m for m, *_ in rows]
    E = CFG["engrais"]
    out = []
    for y in range(int(months[0][:4]) + 11, int(months[-1][:4]) + 1):
        season = [f"{y - 1}-{m:02d}" for m in range(4, 13)] + [f"{y}-01"]
        if not all(m in by for m in season):
            continue
        price = [by[m][0] for m in season]
        r = {"campagne": y, "E0": price[-1], "E1": sum(price) / len(price), "E2": sum(price[:4]) / 4}
        bought, cost = 0.0, 0.0
        for k, m in enumerate(season):
            i = months.index(m)
            hist = [by[x][0] / by[x][1] for x in months[max(0, i - 120):i]]
            ratio = by[m][0] / by[m][1]
            pct = sum(1 for h in hist if h <= ratio) / len(hist) * 100 if hist else 50
            step = 0 if pct > E["ratioHaut"] else 1 if pct > E["ratioMoyen"] else 2 if pct > E["ratioBas"] else 3
            if i >= 3 and by[m][2] and by[months[i - 3]][2]:
                gap = (by[m][2] / by[months[i - 3]][2] - 1) * 100 - (by[m][0] / by[months[i - 3]][0] - 1) * 100
                step = min(3, step + 1) if gap > E["rattrapage"] else max(0, step - 1) if gap < -E["rattrapage"] else step
            frac = [0.0, 5.0, 10.0, 30.0][step]
            if int(m[5:]) in E["saisonChere"] and step <= 2:
                frac /= 2
            q = min(frac, 100 - bought)
            if m == f"{y - 1}-10" and bought + q < 50:
                q = 50 - bought  # au moins la moitié couverte fin octobre
            if k == len(season) - 1:
                q = 100 - bought  # le reste en janvier
            bought += q
            cost += q * by[m][0]
        r["E3"] = cost / 100
        out.append({k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()})
    if len(out) < 3:
        return {"erreur": "historique insuffisant"}
    return {"nom": "Urée (Banque mondiale, $/t, Moyen-Orient)", "campagnes": out, "bilan_vs_E1": bilan(out, ["E0", "E1", "E2", "E3"], "E1", achat=True)}


def main():
    longue = load(PRIV / "yahoo_long.json", {})
    yahoo = longue if all(k in longue for k in ("ZW=F", "ZC=F", "EURUSD=X")) else load(PRIV / "yahoo.json", {})
    cftc = load(PRIV / "cftc_long.json", {}) or load(PRIV / "cftc.json", {})
    for k, v in list(cftc.items()):  # fichier court (calcul du matin) : culture prise dans la configuration
        if isinstance(v, dict) and "culture" not in v and k in CFG["cftc"]["marches"]:
            v["culture"] = CFG["cftc"]["marches"][k]["culture"]
    ventes = backtest_ventes(yahoo, cftc)
    eu = backtest_euronext(cftc, yahoo)
    res = {"genere": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ventes": ventes, "ventes_euronext": eu,
           "comparaison": comparaison(ventes, eu), "engrais": backtest_engrais(),
           "psychologie": backtest_psychologie(yahoo, cftc), "geopolitique": backtest_geopolitique(yahoo),
           "limites": ["Ventes testées sur le marché américain converti en €/t : la tendance d'Euronext, pas son niveau ni la base locale.",
                       "Pas de frais, pas de coût de stockage, pas de fiscalité ; échéance continue non ajustée des changements de contrat.",
                       "S4 ne contient que la technique ; S5 ajoute les fonds (CFTC, depuis 2006) et la macro (euro-dollar, Brent) : la météo et le comité IA ne sont pas rejoués.",
                       "Cours Euronext : prix réel de l'échéance la plus proche, depuis novembre 2019 seulement (fichiers statistiques publics).",
                       "Achats d'azote testés sur l'urée mondiale mensuelle, pas sur les prix rendus France.",
                       "Humeur du marché et risque géopolitique : rendements des séances suivantes, sans frais ; points qui se chevauchent (corrélations à lire comme des ordres de grandeur).",
                       "Le passé ne garantit pas l'avenir : ce test sert à écarter les mauvais réglages, pas à promettre un gain."]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "backtest.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for cult, v in res["ventes"].items():
        if "erreur" in v:
            print(cult, ":", v["erreur"])
            continue
        b = v["bilan_vs_S1"]
        print(f"{v['nom']} — {len(v['campagnes'])} campagnes ; écart moyen vs vente mensuelle (€/t) :",
              {k: b[k]["ecart_moyen"] for k in b}, "| meilleur timing :", v["variantes_timing"][0])
        for lab, bp in v["periodes"].items():
            print(f"   {lab} : ", {k: bp[k]["ecart_moyen"] for k in bp})
    for cult, v in res["ventes_euronext"].items():
        print(v["nom"], ":", v.get("erreur") or {k: x["ecart_moyen"] for k, x in v["bilan_vs_S1"].items()},
              f"({len(v.get('campagnes', []))} campagnes)" if "campagnes" in v else "")
    print("Chicago / Euronext, campagnes communes :", res["comparaison"])
    for nom, v in res["psychologie"].items():
        for h, o in ((k, x) for k, x in v.items() if k in ("20", "60")):
            print(f"Humeur — {nom} à {h} séances : corrélation {o['correlation']} (hasard ±{v['bruit'].get(h)}), "
                  + ", ".join(f"{t['libelle']} {t['moyenne']:+.1f} %" for t in o["tranches"].values()))
    print("Risque géopolitique → blé :", res["geopolitique"])
    e = res["engrais"]
    if "erreur" not in e:
        print("Azote —", len(e["campagnes"]), "campagnes ; écart moyen vs achat mensuel ($/t) :", {k: e["bilan_vs_E1"][k]["ecart_moyen"] for k in e["bilan_vs_E1"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
