"""
Grain Signal — calcul du matin : indicateurs, signaux de vente par culture, module engrais, déclencheurs.

Entrées : data/grain/prive/ (historiques de collect.py), data/grain/comite.json (dernier comité IA, facultatif).
Sorties : data/grain/grain-signal.json (page), data/grain/etat.json (mémoire d'un jour à l'autre), data/grain/prive/a-envoyer.json
(alertes du jour pour send_alerts.py), data/grain/demande-comite.json (comité d'alerte demandé).

  python grain_signal/build.py            (GS_TODAY=AAAA-MM-JJ pour rejouer un jour)
"""
import bisect
import calendar
import csv
import email.utils
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decisions as dec  # noqa: E402
import indicators as ind  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "data" / "grain"
PRIV = OUT / "prive"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
CULTURES = {"ble": "Blé tendre", "escourgeon": "Escourgeon brassicole", "orge_printemps": "Orge de printemps brassicole",
            "colza": "Colza", "mais": "Maïs"}
SIGNAUX = {"VENDRE": "🟢 VENDRE UNE TRANCHE", "TENIR": "🟡 TENIR LE PLAN", "ATTENDRE": "🔴 ATTENDRE-STOCKER", "COUVRIR": "🛡️ COUVRIR"}
PROXY = {"EBM": "ZW=F", "ECO": "ZL=F", "EMA": "ZC=F"}  # colza : huile de soja (le canola ICE n'est pas sur Yahoo)
# conversion en $/t : blé 36,744 boisseaux/t, maïs 39,368 boisseaux/t (cents/boisseau) ; huile de soja 2 204,62 livres/t (cents/livre)
TONNE = {"ZW=F": 36.744, "KE=F": 36.744, "ZC=F": 39.368, "ZS=F": 36.744, "ZL=F": 2204.62}
SIG_ENGRAIS = {"ACHETER_LARGE": "🟢 ACHETER LARGE", "SUIVRE": "🟡 SUIVRE LE PLAN", "FRACTIONNER": "🟠 FRACTIONNER", "ATTENDRE": "🔴 ATTENDRE"}


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def as_dict(v):
    return v if isinstance(v, dict) else {}


def clean_comite(c):
    """Comité relu défensivement : un fichier malformé ne doit ni planter le calcul ni injecter de valeurs absurdes."""
    c = as_dict(c)
    out = dict(c)
    cults = {}
    for k, v in as_dict(c.get("cultures")).items():
        if isinstance(v, dict):
            v = dict(v)
            v["ordres"] = [float(x) for x in (v.get("ordres") or []) if fnum(x) is not None and 0 < float(x) < 5000] if isinstance(v.get("ordres"), list) else []
            for key in ("score", "revision_bas", "revision_haut"):
                if fnum(v.get(key)) is None:
                    v[key] = None
            cults[k] = v
    out["cultures"] = cults
    out["declencheurs"] = [t for t in (c.get("declencheurs") if isinstance(c.get("declencheurs"), list) else [])
                           if isinstance(t, dict) and fnum(t.get("niveau")) is not None]
    out["engrais"] = as_dict(c.get("engrais"))
    out["chiffres"] = as_dict(c.get("chiffres"))
    out["calendrier"] = [x for x in (c.get("calendrier") if isinstance(c.get("calendrier"), list) else []) if isinstance(x, dict)]
    return out


def save_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def read_csv(p):
    p = Path(p)
    if not p.exists():
        p = HERE / "seed" / p.name
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------------------------- Euronext : série continue
def business_back(d, n):
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def expiry(prod, mat):
    y, m = int(mat[:4]), int(mat[5:7])
    rule = CFG["euronext"][prod]["expiration"]
    if rule["regle"] == "jour":
        d = date(y, m, rule["jour"])
    else:  # dernier jour ouvré du mois précédent
        d = date(y, m, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def continuous(rows, prod):
    """Série continue ajustée aux changements d'échéance (différence le jour du changement quand les deux échéances cotent).
    Renvoie dates, valeurs, échéance de référence du dernier jour, journal des raccords."""
    by_date = {}
    for r in rows:
        if r["product"] == prod and fnum(r["settle"]) is not None:
            by_date.setdefault(r["date"], {})[r["maturity"]] = float(r["settle"])
    dates = sorted(by_date)
    vals, refs = [], []
    for d in dates:
        dd = date.fromisoformat(d)
        avail = sorted(by_date[d])
        ok = [m for m in avail if business_back(expiry(prod, m), CFG["rollJours"]) > dd]
        ref = ok[0] if ok else avail[-1]
        refs.append(ref)
        vals.append(by_date[d][ref])
    raccords = []
    for i in range(1, len(dates)):
        if refs[i] != refs[i - 1]:
            # écart nouvelle − ancienne échéance : médiane des 5 dernières séances où les deux cotent (une séance agitée de
            # fin de vie de l'échéance proche ne fausse plus toute la série ; maïs octobre 2026 : −49,5 €/t un seul jour)
            ec = [by_date[dates[k]][refs[i]] - by_date[dates[k]][refs[i - 1]] for k in range(max(0, i - 4), i + 1)
                  if refs[i] in by_date[dates[k]] and refs[i - 1] in by_date[dates[k]]]
            if ec:
                ec.sort()
                adj = ec[len(ec) // 2] if len(ec) % 2 else (ec[len(ec) // 2 - 1] + ec[len(ec) // 2]) / 2
                for j in range(i):
                    vals[j] += adj
                raccords.append({"date": dates[i], "de": refs[i - 1], "vers": refs[i], "ajustement": round(adj, 2)})
            else:
                raccords.append({"date": dates[i], "de": refs[i - 1], "vers": refs[i], "ajustement": None})
    curve = by_date[dates[-1]] if dates else {}
    return dates, vals, (refs[-1] if refs else None), raccords, curve


def front_series(rows, prod):
    """Prix réel (sans ajustement) de l'échéance de référence de chaque séance : le prix que l'agriculteur voyait ce jour-là. Sert aux
    vues longues et au thermomètre ; la série ajustée (continuous) sert aux indicateurs techniques."""
    by = {}
    for r in rows:
        if r["product"] == prod and fnum(r["settle"]) is not None:
            by.setdefault(r["date"], {})[r["maturity"]] = float(r["settle"])
    dates, vals = [], []
    for d in sorted(by):
        dd = date.fromisoformat(d)
        avail = sorted(by[d])
        ok = [m for m in avail if business_back(expiry(prod, m), CFG["rollJours"]) > dd]
        dates.append(d)
        vals.append(by[d][ok[0] if ok else avail[-1]])
    return dates, vals


def long_views(dates, vals):
    """Vues 1 an (quotidien, MM50 et MM200) et 5 ans (dernier cours de chaque semaine, MM 10 et 40 semaines)."""
    r2 = lambda x: round(x, 2) if x is not None else None  # noqa: E731
    m50, m200 = ind.sma(vals, 50), ind.sma(vals, 200)
    k1 = max(0, len(vals) - 252)
    wk, wd = [], []
    for d_, v_ in zip(dates, vals):
        key = date.fromisoformat(d_).isocalendar()[:2]
        if wd and wd[-1][0] == key:
            wd[-1], wk[-1] = (key, d_), v_
        else:
            wd.append((key, d_))
            wk.append(v_)
    w10, w40 = ind.sma(wk, 10), ind.sma(wk, 40)
    return {"an": [[dates[i], r2(vals[i]), r2(m50[i]), r2(m200[i]), None] for i in range(k1, len(vals))],
            "cinq_ans": [[wd[i][1], r2(wk[i]), r2(w10[i]), r2(w40[i]), None] for i in range(max(0, len(wk) - 262), len(wk))],
            "depuis": dates[0], "semaines": len(wk)}


def courbe(prod, curve, ref):
    """Structure de la courbe : report (le marché paie le stockage) ou déport."""
    mats = sorted(m for m in curve if m >= (ref or ""))
    pts = [{"echeance": m, "prix": curve[m]} for m in mats]
    out = {"points": pts}
    if len(mats) >= 2:
        a, b = mats[0], mats[1]
        months = (int(b[:4]) - int(a[:4])) * 12 + int(b[5:]) - int(a[5:])
        spread = curve[b] - curve[a]
        out.update(proche=a, suivante=b, ecart=round(spread, 2), par_mois=round(spread / months, 2) if months else None)
        fr = lambda v: f"{v:.2f}".replace(".", ",")  # noqa: E731
        if spread > 0:
            out["lecture"] = f"Report de +{fr(spread)} €/t ({fr(spread / months)} €/t/mois) : comparer au coût réel du stockage"
        else:
            out["lecture"] = f"Déport de {fr(spread)} €/t : le marché ne paie pas le stockage"
    return out


def front_on(rows, prod):
    """Prix Euronext à une date (ou à la séance précédente, 4 jours au plus) : f(d) = échéance de référence ; f(d, période) = première
    échéance cotée qui couvre le début de la période de livraison d'un prix physique (« janv. - mars » → mars ; « nov. » → décembre)."""
    by = {}
    for r in rows:
        if r["product"] == prod and fnum(r["settle"]) is not None:
            by.setdefault(r["date"], {})[r["maturity"]] = float(r["settle"])
    ds = sorted(by)

    def f(d, periode=None):
        i = bisect.bisect_right(ds, d) - 1
        if i < 0 or (date.fromisoformat(d) - date.fromisoformat(ds[i])).days > 4:
            return None
        dd = date.fromisoformat(ds[i])
        ok = [m for m in sorted(by[ds[i]]) if business_back(expiry(prod, m), CFG["rollJours"]) > dd]
        mo = dec.mois_debut(periode)
        if mo:
            y = dd.year + (1 if mo < dd.month - 2 else 0)  # « janv. » relevé en novembre : janvier de l'année suivante
            cible = f"{y}-{mo:02d}"
            ok = [m for m in ok if m >= cible] or ok
        return by[ds[i]][ok[0]] if ok else None
    return f


# --------------------------------------------------------------------------------------------- COT et macro
def cot_reading(serie, mini=20, today=None, max_age=21):
    """Position nette des fonds et indice sur 3 ans (0 = la plus vendeuse, 100 = la plus acheteuse).
    Moins de `mini` semaines : position affichée, indice absent (pas de lecture sur un historique trop court)."""
    if not serie or len(serie) < 2:
        return None
    nets = [s["net"] if "net" in s else s["long"] - s["short"] for s in serie]
    w = nets[-156:]
    lo, hi = min(w), max(w)
    idx = round((nets[-1] - lo) / (hi - lo) * 100 if hi > lo else 50.0, 0) if len(serie) >= mini else None
    out = {"date": serie[-1]["date"], "net": nets[-1], "variation": nets[-1] - nets[-2], "indice": idx, "semaines": len(serie)}
    try:
        if today and (today - date.fromisoformat(serie[-1]["date"][:10])).days > max_age:
            out.update(indice=None, perime=True)  # rapport de plus de 3 semaines : affiché, plus compté dans la note
    except ValueError:
        pass
    return out


ACTU_CLE = {"ble": "ble", "escourgeon": "orge", "orge_printemps": "orge", "colza": "colza", "mais": "mais"}
COT_EURONEXT = {"EBM": ("Blé tendre Euronext (fonds)", "ble"), "ECO": ("Colza Euronext (fonds)", "colza"),
                "EMA": ("Maïs Euronext (fonds)", "mais")}


def suivi_pannes(sources, avant, today):
    """Sources en échec : date de début et jours distincts d'échec. Alerte au 2e jour, une seule fois ; message au rétablissement.
    Renvoie (nouvel état, [(clé, titre, détail)])."""
    jour = today.isoformat()
    etat, msgs = {}, []
    for src in sorted(set(sources) | set(avant)):
        st, p = sources.get(src), avant.get(src) or {}
        if isinstance(st, dict) and st.get("ok") is False:
            jours = sorted(set(p.get("jours") or []) | {jour})[-10:]
            e = {"debut": p.get("debut") or jour, "jours": jours, "alerte": p.get("alerte", False), "detail": st.get("detail", "")}
            if len(jours) >= 2 and not e["alerte"]:
                msgs.append((f"panne:{src}", f"⚠️ Source en panne : {src} depuis {len(jours)} jours",
                             f"Échec depuis le {e['debut']} : {e['detail'] or 'sans détail'}. Les calculs continuent sans elle."))
                e["alerte"] = True
            etat[src] = e
        elif st is None:  # source non interrogée ce jour-là (collecte hebdomadaire ou mensuelle) : état inchangé
            if p:
                etat[src] = p
        elif p.get("alerte"):
            msgs.append((f"retablie:{src}", f"✅ Source rétablie : {src}", f"De nouveau lue après une panne commencée le {p.get('debut')}."))
    return etat, msgs


def cot_score(idx):
    """Lecture à contre-courant : fonds très vendeurs (indice bas) = rachat possible ; très acheteurs = liquidation possible."""
    if idx is None:
        return None
    if idx <= 15:
        return 1.5
    if idx >= 85:
        return -1.5
    return round(max(-1.0, min(1.0, -(idx - 50) / 35)), 2)


def chg(ser, n):
    v = list(ser.values()) if isinstance(ser, dict) else ser
    if len(v) <= n:
        return None
    return (v[-1] / v[-1 - n] - 1) * 100


def clamp(v, a=-2.0, b=2.0):
    return max(a, min(b, v))


def matrix(score):
    if score is None:
        return None
    if score <= CFG["matrice"]["vendre"]:
        return "VENDRE"
    if score >= CFG["matrice"]["attendre"]:
        return "ATTENDRE"
    return "TENIR"


# --------------------------------------------------------------------------------------------- engrais
def asof(rows, d, key="date"):
    """Dernière ligne (triée par key) à la date d ou avant."""
    ks = [r[key] for r in rows]
    i = bisect.bisect_right(ks, d) - 1
    return rows[i] if i >= 0 else None


def fr_n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def percentile(window, v):
    return round(sum(1 for w in window if w <= v) / len(window) * 100) if window else None


def module_engrais(today, ble_dates, ble_vals, yahoo):
    wb = [r for r in read_csv(PRIV / "wb_monthly.csv") if fnum(r.get("urea")) and fnum(r.get("wheat_hrw"))]
    wb.sort(key=lambda r: r["month"])
    out = {"sources": {}}
    if len(wb) < 60:
        out["erreur"] = "Historique Banque mondiale insuffisant"
        return out
    ratios = [float(r["urea"]) / float(r["wheat_hrw"]) for r in wb]
    last = wb[-1]
    win = ratios[-121:-1]
    ur_all = [float(r["urea"]) for r in wb]
    out["mondial"] = {"mois": last["month"], "uree": float(last["urea"]), "ble_hrw": float(last["wheat_hrw"]),
                      "ratio": round(ratios[-1], 3), "percentile": percentile(win, ratios[-1]),
                      "uree_percentile": percentile(ur_all[-121:-1], ur_all[-1])}  # prix de l'urée seul, sur 10 ans
    # écart mensuel gaz − urée sur 3 mois (Banque mondiale)
    gas = [fnum(r.get("gas_eu")) for r in wb]
    if len(wb) > 3 and gas[-1] and gas[-4]:
        g3 = (gas[-1] / gas[-4] - 1) * 100
        u3 = (float(wb[-1]["urea"]) / float(wb[-4]["urea"]) - 1) * 100
        out["mondial"]["rattrapage"] = round(g3 - u3, 1)
    # prix France (terre-net) et estimation du ratio du jour
    fr = {}
    rows = sorted(read_csv(PRIV / "fert_fr.csv"), key=lambda r: r["date"])
    for prod, c in CFG["engraisFrance"].items():
        pr = [r for r in rows if r["product"] == prod and fnum(r["price"])]
        if not pr:
            continue
        cur = pr[-1]
        e = {"nom": c["nom"], "prix": float(cur["price"]), "date": cur["date"], "source": cur.get("source", "")}
        if c.get("titre"):
            e["euro_un"] = round(float(cur["price"]) / (c["titre"] * 1000), 3)
        for lab, days in (("var1m", 30), ("var3m", 91)):
            ref = asof(pr, (date.fromisoformat(cur["date"]) - timedelta(days=days)).isoformat())
            if ref and ref["date"] != cur["date"]:
                e[lab] = round((float(cur["price"]) / float(ref["price"]) - 1) * 100, 1)
                e[lab + "_depuis"] = ref["date"]
        if ble_vals:
            e["ratio_ble"] = round(float(cur["price"]) / ble_vals[-1], 2)
        fr[prod] = e
    out["france"] = fr
    est = None
    if "uree" in fr and ble_vals:
        # le chiffre Banque mondiale est une moyenne du mois : les bases France et Euronext doivent être prises DANS ce mois
        mo = last["month"]
        u_obs = sorted((r["date"], float(r["price"])) for r in rows if r["product"] == "uree" and fnum(r["price"]))
        u_m = [v_ for d_, v_ in u_obs if d_[:7] == mo]
        b_m = [v_ for d_, v_ in zip(ble_dates, ble_vals) if d_[:7] == mo]
        u0, how = None, ""
        if u_m:
            u0, how = sum(u_m) / len(u_m), f"moyenne de {len(u_m)} cotation(s) du mois"
        else:  # pas de relevé dans le mois : prix interpolé au 15 du mois entre les relevés qui l'encadrent (45 jours au plus)
            mid = date.fromisoformat(mo + "-15")
            av = [(date.fromisoformat(d_), v_) for d_, v_ in u_obs if mid - timedelta(days=45) <= date.fromisoformat(d_) <= mid]
            ap = [(date.fromisoformat(d_), v_) for d_, v_ in u_obs if mid <= date.fromisoformat(d_) <= mid + timedelta(days=45)]
            if av and ap:
                (d1, v1), (d2, v2) = av[-1], ap[0]
                u0 = v1 if d1 == d2 else v1 + (v2 - v1) * (mid - d1).days / (d2 - d1).days
                how = f"interpolée au 15 entre {fr_n(v1)} le {d1:%d/%m} et {fr_n(v2)} le {d2:%d/%m}"
        if u0 and len(b_m) >= 5:
            b0 = sum(b_m) / len(b_m)
            est = ratios[-1] * (fr["uree"]["prix"] / u0) / (ble_vals[-1] / b0)
            out["estimation"] = {"ratio": round(est, 3), "percentile": percentile(win, est),
                                 "methode": f"ratio mondial de {mo} (moyenne du mois) corrigé de l'évolution depuis le milieu du mois : "
                                            f"urée France {fr_n(u0)} → {fr_n(fr['uree']['prix'])} €/t ({how}) ; blé Euronext "
                                            f"{fr_n(b0)} → {fr_n(ble_vals[-1])} €/t (moyenne de {len(b_m)} séances du mois)"}
        else:
            out["estimation_absente"] = (f"Pas assez de prix France et Euronext autour de {mo} (mois du dernier chiffre Banque "
                                         f"mondiale) : ratio mondial retenu tel quel")
    pct = out.get("estimation", {}).get("percentile", out["mondial"]["percentile"])
    out["percentile_retenu"] = pct
    out["base"] = "estimation" if "estimation" in out else "mondial"
    # historiques mensuels (Banque mondiale) : urée et DAP en $/t avec moyenne 12 mois, ratio urée/blé avec ses seuils
    ur = [float(r["urea"]) for r in wb]
    mm12 = ind.sma(ur, 12)
    dap = [fnum(r.get("dap")) for r in wb]
    k = max(0, len(wb) - 120)
    out["histo_uree"] = [[wb[i]["month"] + "-15", round(ur[i], 1), round(mm12[i], 1) if mm12[i] else None,
                          round(dap[i], 1) if dap[i] else None] for i in range(k, len(wb))]
    srt = sorted(win)
    q = lambda p_: round(srt[max(0, math.ceil(p_ / 100 * len(srt)) - 1)], 3)  # noqa: E731  (valeur du p-ième percentile)
    out["histo_ratio"] = {"points": [[wb[i]["month"] + "-15", round(ratios[i], 3)] for i in range(k, len(wb))],
                          "seuils": {"20": q(20), "60": q(60), "80": q(80)},
                          "estimation": round(est, 3) if est else None}
    # gaz TTF (Yahoo) : niveau, tendance, rattrapage du jour
    ttf = (yahoo.get("TTF=F") or {}).get("serie") or {}
    if len(ttf) > 70:
        d, v = list(ttf.keys()), list(ttf.values())
        vu = vues(d, v)  # une seule analyse du gaz, réutilisée partout
        a = vu["technique"]
        out["ttf"] = {k: a.get(k) for k in ("dernier", "au", "var1s", "var1m", "var3m", "mm20", "ecart_mm20", "mm50", "rsi", "histo",
                                             "croisement_macd", "haut3m", "bas3m")}
        out["ttf"]["vues"] = vu
        out["ttf"]["percentile_5ans"] = percentile(v[-1260:], v[-1])
        out["ttf"]["sous_seuil_bas"] = sum(1 for x in v[-CFG["engrais"]["ttfBasSeances"]:] if x < CFG["engrais"]["ttfBas"])
        if "uree" in fr and fr["uree"].get("var3m") is not None and a.get("var3m") is not None:
            out["rattrapage"] = round(a["var3m"] - fr["uree"]["var3m"], 1)
    elif "rattrapage" in out["mondial"]:
        out["rattrapage"] = out["mondial"]["rattrapage"]
    # décision
    e = CFG["engrais"]
    steps = ["ATTENDRE", "FRACTIONNER", "SUIVRE", "ACHETER_LARGE"]
    if pct is None:
        sig = "SUIVRE"
    elif pct <= e["ratioBas"]:
        sig = "ACHETER_LARGE"
    elif pct <= e["ratioMoyen"]:
        sig = "SUIVRE"
    elif pct <= e["ratioHaut"]:
        sig = "FRACTIONNER"
    else:
        sig = "ATTENDRE"
    notes = [f"Ratio azote/blé au {pct}e percentile sur 10 ans" if pct is not None else "Ratio azote/blé indisponible"]
    gap = out.get("rattrapage")
    ttf_faible = bool(out.get("ttf") and (out["ttf"].get("ecart_mm20") or 0) < 0 and (out["ttf"].get("histo") or 0) < 0)
    if gap is not None and gap > e["rattrapage"]:
        if ttf_faible:
            notes.append(f"Rattrapage de {gap:+.0f} pts (gaz plus haussier que l'azote), mais le gaz repasse sous sa MM20 : signal affaibli")
        else:
            sig = steps[min(3, steps.index(sig) + 1)]
            notes.append(f"Rattrapage de {gap:+.0f} pts : hausse de l'azote probable sous 1 à 3 mois, achat avancé d'un cran")
    elif gap is not None and gap < -e["rattrapage"]:
        sig = steps[max(0, steps.index(sig) - 1)]
        notes.append(f"Écart de {gap:+.0f} pts (azote plus haussier que le gaz) : achat retardé d'un cran")
    mo = today.month
    if mo in e["saisonAchat"]:
        out["saison"] = "basse (avril-juillet) : fenêtre d'achat habituelle"
    elif mo in e["saisonChere"]:
        out["saison"] = "haute (septembre-novembre) : reporter si le plan le permet"
        if sig == "SUIVRE":
            notes.append("Saison chère : la tranche peut être reportée")
    else:
        out["saison"] = "intermédiaire"
    if out.get("ttf"):
        if out["ttf"]["dernier"] > e["ttfHaut"]:
            notes.append(f"Gaz au-dessus de {e['ttfHaut']} €/MWh : risque de hausse rapide de l'azote")
        if out["ttf"]["sous_seuil_bas"] >= e["ttfBasSeances"]:
            notes.append(f"Gaz sous {e['ttfBas']} €/MWh depuis {e['ttfBasSeances']} séances : fenêtre d'achat")
    pct_now = {"ACHETER_LARGE": "40 à 50 %", "SUIVRE": "la tranche prévue (≈ 25 %)", "FRACTIONNER": "15 à 20 %", "ATTENDRE": "0 à 10 % (l'indispensable)"}
    formes = sorted([(v["euro_un"], k) for k, v in fr.items() if v.get("euro_un")])
    out.update(signal=sig, libelle=SIG_ENGRAIS[sig], a_acheter=pct_now[sig], notes=notes,
               forme_moins_chere=(CFG["engraisFrance"][formes[0][1]]["nom"] if formes else None))
    return out


def mini_series(dates, rsi_s, histo_s, n=63):
    """RSI et histogramme MACD des 3 derniers mois, pour les petits graphiques de la page."""
    if not rsi_s or not histo_s:
        return None
    k = max(0, len(dates) - n)
    return {"dates": dates[k:], "rsi": [round(x, 1) if x is not None else None for x in rsi_s[k:]],
            "histo": [round(x, 3) if x is not None else None for x in histo_s[k:]]}


def decale(a, gap):
    """Tableau technique du blé ramené au niveau de l'orge : niveaux de prix décalés de l'écart, écarts et oscillateurs inchangés."""
    if not a:
        return a
    b = json.loads(json.dumps(a))
    for k in ("dernier", "mm20", "mm50", "mm200", "haut3m", "bas3m", "haut3m_hier", "bas3m_hier"):
        if b.get(k) is not None:
            b[k] = round(b[k] + gap, 2)
    for k in ("38.2", "50", "61.8"):
        if (b.get("fibo") or {}).get(k) is not None:
            b["fibo"][k] = round(b["fibo"][k] + gap, 2)
    return b


def vues(dates, vals):
    """Graphique 6 mois (cours, MM20, MM50), séries RSI/MACD de 3 mois, vues 1 an (MM50, MM200) et 5 ans hebdomadaire
    (MM 10 et 40 semaines) d'une série quotidienne."""
    if len(vals) < 30:
        return {}
    a = ind.analyse(dates, vals)
    rs_, hs_ = a.pop("_rsi", None), a.pop("_histo", None)
    m20, m50, m200 = ind.sma(vals, 20), ind.sma(vals, 50), ind.sma(vals, 200)
    r2 = lambda x: round(x, 2) if x is not None else None  # noqa: E731
    k6, k1 = max(0, len(vals) - 120), max(0, len(vals) - 252)
    wk, wd = [], []
    for d_, v_ in zip(dates, vals):
        key = date.fromisoformat(d_).isocalendar()[:2]
        if wd and wd[-1][0] == key:
            wd[-1], wk[-1] = (key, d_), v_
        else:
            wd.append((key, d_))
            wk.append(v_)
    w10, w40 = ind.sma(wk, 10), ind.sma(wk, 40)
    return {"technique": a, "score_technique": ind.score_technique(a), "niveaux": ind.niveaux(a), "series": mini_series(dates, rs_, hs_),
            "graphique": [[dates[i], r2(vals[i]), r2(m20[i]), r2(m50[i])] for i in range(k6, len(vals))],
            "long": {"an": [[dates[i], r2(vals[i]), r2(m50[i]), r2(m200[i]), None] for i in range(k1, len(vals))],
                     "cinq_ans": [[wd[i][1], r2(wk[i]), r2(w10[i]), r2(w40[i]), None] for i in range(max(0, len(wk) - 262), len(wk))],
                     "depuis": dates[0]}}


def vue_longue(yahoo, tk, e_dates, e_vals):
    """Vues 1 an (quotidien, MM50 et MM200) et 5 ans (hebdomadaire, MM 10 et 40 semaines) : marché américain converti en €/t
    pour la tendance longue, avec la série Euronext par-dessus là où elle existe."""
    pd_, pv = proxy_eur(yahoo, tk)
    if len(pv) < 60:
        return None
    eu = dict(zip(e_dates, e_vals))
    f = recale(pd_, pv, e_dates, e_vals)  # même échelle qu'Euronext, raccord exact au dernier jour commun
    pv = [x * f for x in pv]
    m50, m200 = ind.sma(pv, 50), ind.sma(pv, 200)
    k = max(0, len(pv) - 252)
    an = [[pd_[i], round(pv[i], 2), round(m50[i], 2) if m50[i] else None, round(m200[i], 2) if m200[i] else None,
           round(eu[pd_[i]], 2) if pd_[i] in eu else None] for i in range(k, len(pv))]
    # hebdomadaire : dernier cours de chaque semaine (vendredi ou dernière séance)
    wk, wd = [], []
    for d_, v_ in zip(pd_, pv):
        key = date.fromisoformat(d_).isocalendar()[:2]
        if wd and wd[-1][0] == key:
            wd[-1] = (key, d_)
            wk[-1] = v_
        else:
            wd.append((key, d_))
            wk.append(v_)
    w10, w40 = ind.sma(wk, 10), ind.sma(wk, 40)
    eu_w = {}
    for d_, v_ in zip(e_dates, e_vals):
        eu_w[date.fromisoformat(d_).isocalendar()[:2]] = v_
    cinq = [[wd[i][1], round(wk[i], 2), round(w10[i], 2) if w10[i] else None, round(w40[i], 2) if w40[i] else None,
             round(eu_w[wd[i][0]], 2) if wd[i][0] in eu_w else None] for i in range(max(0, len(wk) - 262), len(wk))]
    return {"ticker": tk, "nom": (yahoo.get(tk) or {}).get("nom", tk), "an": an, "cinq_ans": cinq, "recalage": round(f, 4),
            "depuis": pd_[0], "euronext_depuis": e_dates[0] if e_dates else None}


def recale(p_dates, p_vals, e_dates, e_vals):
    """Facteur qui ramène une série américaine au niveau d'Euronext le DERNIER jour où les deux cotent : la courbe recalée finit
    exactement au cours Euronext du jour (pas de marche entre les deux courbes)."""
    pmap = dict(zip(p_dates, p_vals))
    common = [d_ for d_ in e_dates if pmap.get(d_)]
    if not common:
        return 1.0
    return e_vals[e_dates.index(common[-1])] / pmap[common[-1]]


def proxy_eur(yahoo, tk):
    """Série américaine convertie en €/t (cents → $/t, puis EUR/USD du même jour ou de la veille)."""
    ser = (yahoo.get(tk) or {}).get("serie") or {}
    fx = (yahoo.get("EURUSD=X") or {}).get("serie") or {}
    if not ser or not fx or tk not in TONNE:
        return [], []
    fx_d = sorted(fx)
    dates, vals = [], []
    for d, c in sorted(ser.items()):
        i = bisect.bisect_right(fx_d, d) - 1
        if i < 0:
            continue
        dates.append(d)
        vals.append(c / 100 * TONNE[tk] / fx[fx_d[i]])
    return dates, vals


def orges(today, ble_vals):
    """Escourgeon (Etincel) et orge de printemps (Planet) brassicoles : prix physiques terre-net, prime sur l'orge
    fourragère au même endroit (Creil FOB), écart avec le blé Euronext, historique quotidien."""
    rows = [r for r in read_csv(PRIV / "physique_hist.csv") if fnum(r.get("prix"))]
    rows.sort(key=lambda r: r["date"])
    out = {}

    def pick(rs, *keys):
        return [r for r in rs if all(k.lower() in (r.get("titre", "") + " " + r.get("place", "")).lower() for k in keys)]

    four = pick([r for r in rows if r["page"] == "orge"], "creil")
    four_by = {r["date"]: float(r["prix"]) for r in four}
    for cult, var, nom in (("escourgeon", "etincel", "Escourgeon brassicole (Etincel)"), ("orge_printemps", "planet", "Orge de printemps brassicole (Planet)")):
        rs = pick([r for r in rows if r["page"] == "orge_brassicole"], var, "creil")
        if not rs:
            continue
        by = {}
        for r in rs:
            by[r["date"]] = float(r["prix"])
        dates = sorted(by)
        last_d = dates[-1]
        e = {"nom": nom, "prix": by[last_d], "date": last_d, "place": "Creil FOB", "echeance": rs[-1].get("echeance", "")}
        fd = [d for d in sorted(four_by) if d <= last_d]
        if fd:
            e["fourragere"] = four_by[fd[-1]]
            e["fourragere_echeance"] = next((r.get("echeance", "") for r in reversed(four) if r["date"] == fd[-1]), "")
            e["prime"] = round(by[last_d] - four_by[fd[-1]], 2)
        if ble_vals:
            e["ecart_ble"] = round(by[last_d] - ble_vals[-1], 2)
        rouen = pick([r for r in rows if r["page"] == "orge_brassicole" and r["date"] == last_d], var, "rouen")
        if rouen:
            e["rouen_rendu"] = float(rouen[-1]["prix"])
        for lab, days in (("var1m", 30), ("var3m", 91)):
            ref = [d for d in dates if d <= (date.fromisoformat(last_d) - timedelta(days=days)).isoformat()]
            if ref:
                e[lab] = round((by[last_d] / by[ref[-1]] - 1) * 100, 1)
        e["graphique"] = [[d, by[d], (round(by[d] - four_by[d], 2) if d in four_by else None)] for d in dates[-120:]]
        if len(dates) >= 30:
            a = ind.analyse(dates, [by[d] for d in dates])
            a.pop("_rsi", None)
            a.pop("_histo", None)
            e["technique"] = a
        out[cult] = e
    return out


MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def ym(harvest_year, rel):
    """Mois relatif à janvier de l'année de récolte (1 = janvier, 0 = décembre d'avant, 13 = janvier d'après) → (année, mois)."""
    k = harvest_year * 12 + rel - 1
    return k // 12, k % 12 + 1


def periode(a, b):
    (y1, m1), (y2, m2) = a, b
    return f"{MOIS_FR[m1 - 1]}–{MOIS_FR[m2 - 1]} {y2}" if y1 == y2 else f"{MOIS_FR[m1 - 1]} {y1}–{MOIS_FR[m2 - 1]} {y2}"


def plan_vente(cult, today, entry, contrats):
    """Tranches dues ou prochaines, par récolte en cours de vente, avec l'action conseillée selon le signal et le timing."""
    cal = (CFG.get("calendrier") or {}).get(cult)
    if not cal:
        return []
    now = (today.year, today.month)
    out = []
    for hy in (today.year - 1, today.year, today.year + 1):
        tr = [(ym(hy, a), ym(hy, b), pct) for a, b, pct in cal["tranches"]]
        if not (tr[0][0] <= now <= tr[-1][1]) and not (now < tr[0][0] and (tr[0][0][0] * 12 + tr[0][0][1]) - (now[0] * 12 + now[1]) <= 2):
            continue  # récolte hors calendrier (vendue, ou ventes pas encore ouvertes)
        cum, due, nxt, done = 0, None, None, 0
        for a, b, pct in tr:
            if b < now:
                done += pct
            elif a <= now <= b and due is None:
                due = (a, b, pct, done + pct)
            elif a > now and nxt is None:
                nxt = (a, b, pct)
            cum += pct
        harvest_m = 10 if cult == "mais" else 7
        pre = (now[0], now[1]) < (hy, harvest_m)
        e = {"recolte": hy, "avant_moisson": pre, "cumul_fait": done}
        nr = entry.get("niveaux_retenus") or {}
        ordres = nr.get("ordres") or []
        ref = cal.get("reference")
        if ref:
            c = contrats.get(ref[0]) or {}
            mat = f"{hy}-{ref[1]:02d}"
            pts = {p["echeance"]: p["prix"] for p in ((c.get("courbe") or {}).get("points") or [])}
            if mat in pts:
                e["reference"] = {"contrat": ref[0], "echeance": mat, "prix": pts[mat]}
                # récolte à venir : ordres décalés de l'écart entre son échéance et l'échéance de référence du jour
                cur = c.get("dernier_reel")
                if pre and ordres and cur and mat != c.get("echeance"):
                    ordres = [round((o + pts[mat] - cur) * 4) / 4 for o in ordres]
        if due:
            a, b, pct, cible = due
            fin = date(b[0], b[1], calendar.monthrange(b[0], b[1])[1])
            e.update(statut="due", periode=periode(a, b), pct=pct, cumul_vise=cible, fin=fin.isoformat())
            sig = entry.get("signal")
            feu = (entry.get("feu") or {}).get("code")
            contrat = cal.get("contrat") and pre  # orge de printemps avant la moisson : contrats malterie
            quoi = "la tranche par contrat malterie" if contrat else "la tranche"
            if sig == "VENDRE":
                extra = nxt[2] if nxt else 0
                if pre:  # jamais plus de 35 % de la récolte vendus avant la moisson
                    extra = max(0, min(extra, 35 - cible))
                e["action"] = (f"Avancer : vendre {quoi} et la suivante ({pct + extra} %)" if extra
                               else f"Vendre {quoi} ({pct} %) : plafond de 35 % avant la moisson atteint")
                e["code"] = "vendre"
            elif sig == "ATTENDRE":
                e["action"] = f"Décaler {quoi} : attendre ou stocker"
                e["code"] = "attendre"
            elif sig == "COUVRIR":
                e["action"] = f"Couvrir {quoi} (vente à terme ou option de vente) sans livrer le grain"
                e["code"] = "couvrir"
            elif contrat:
                e["action"] = f"Contractualiser {pct} % avec la malterie si la prime brassicole tient"
                e["code"] = "executer"
            elif ordres:
                lieu = "quand le blé Euronext atteint" if nr.get("sur_ble") else "par ordre à"
                o = f"{ordres[0]:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " €/t"
                if pre and ref:  # récolte à venir : l'ordre porte sur l'échéance de la nouvelle récolte
                    o += f" (échéance {MOIS_FR[ref[1] - 1]} {hy})"
                if feu == "attendre":
                    e["action"] = f"Ne pas vendre au marché (creux) : {pct} % {lieu} {o}"
                    e["code"] = "ordre"
                elif feu == "accelerer":
                    e["action"] = f"Vendre {pct} % maintenant : le marché s'essouffle (sinon {lieu} {o})"
                    e["code"] = "executer"
                else:
                    e["action"] = f"Vendre {pct} % {lieu} {o}, au marché seulement si besoin de trésorerie"
                    e["code"] = "ordre"
                e["ordre"] = ordres[0]
            elif feu == "attendre":
                e["action"] = f"Ne pas vendre au marché (creux) : attendre un rebond pour ces {pct} %"
                e["code"] = "patienter"
            else:
                e["action"] = f"Vendre {pct} % d'ici fin {MOIS_FR[b[1] - 1]}"
                e["code"] = "executer"
            if pre and not contrat and ref and not e.get("ordre"):
                e["action"] += f" (échéance {MOIS_FR[ref[1] - 1]} {hy})"
        elif nxt:
            a, b, pct = nxt
            e.update(statut="prochaine", periode=periode(a, b), pct=pct, cumul_vise=done + pct,
                     action=f"Rien de prévu avant {MOIS_FR[a[1] - 1]} {a[0]}", code="rien")
        else:
            continue
        out.append(e)
    return out


# --------------------------------------------------------------------------------------------- calcul principal
def main():
    today = date.fromisoformat(os.environ["GS_TODAY"]) if os.environ.get("GS_TODAY") else datetime.now(timezone.utc).date()
    eur = read_csv(PRIV / "euronext.csv")
    yahoo = {k: v for k, v in as_dict(load_json(PRIV / "yahoo.json", {})).items() if isinstance(v, dict) and isinstance(v.get("serie"), dict)}
    cftc = {k: v for k, v in as_dict(load_json(PRIV / "cftc.json", {})).items() if isinstance(v, dict) and isinstance(v.get("serie"), list)}
    cot_eu = {k: v for k, v in as_dict(load_json(PRIV / "cot_euronext.json", {})).items() if isinstance(v, dict) and isinstance(v.get("serie"), list)}
    seed_c = load_json(HERE / "seed" / "comite-initial.json", {})
    cur_c = load_json(OUT / "comite.json", {})
    if cur_c.get("date") == seed_c.get("date") and "(session)" in str(cur_c.get("modele")) and cur_c.get("version_seed") != seed_c.get("version_seed"):
        (OUT / "comite.json").unlink()  # comité de départ corrigé : nouvelle version reprise
    if not (OUT / "comite.json").exists() and (HERE / "seed" / "comite-initial.json").exists():
        (OUT / "comite.json").write_bytes((HERE / "seed" / "comite-initial.json").read_bytes())  # premier calcul : comité du 07/11/2026
    comite = clean_comite(load_json(OUT / "comite.json", {}))
    etat = as_dict(load_json(OUT / "etat.json", {}))
    collecte = as_dict(load_json(OUT / "collecte.json", {}))

    inter = {}
    for tk, y in yahoo.items():
        s = y.get("serie") or {}
        if len(s) < 30:
            continue
        a = ind.analyse(list(s.keys()), list(s.values()))
        a.pop("_rsi", None)
        a.pop("_histo", None)
        inter[tk] = {"nom": y.get("nom", tk), "technique": a, "score_technique": ind.score_technique(a)}

    contrats, series_ble = {}, ([], [])
    for prod, c in CFG["euronext"].items():
        d, v, ref, rac, curve = continuous(eur, prod)
        if not d:
            contrats[prod] = {"nom": c["nom"], "culture": c["culture"], "erreur": "aucune cotation"}
            continue
        a = ind.analyse(d, v)
        rs_, hs_ = a.pop("_rsi", None), a.pop("_histo", None)
        info = {"nom": c["nom"], "culture": c["culture"], "echeance": ref, "series": mini_series(d, rs_, hs_), "technique": a, "score_technique": ind.score_technique(a),
                "feu": ind.feu_execution(a), "niveaux": ind.niveaux(a), "courbe": courbe(prod, curve, ref), "raccords": rac[-3:],
                "dernier_reel": curve.get(ref), "seance": d[-1],
                "_serie": dict(zip(d, v)), "_curve": curve, "_raccords": rac}
        recent = [r for r in rac if r["ajustement"] is None and r["date"] >= d[max(0, len(d) - 63)]]
        if recent:
            info["alerte_raccord"] = f"Changement d'échéance du {recent[-1]['date']} non ajusté (pas de cotation commune) : indicateurs approximatifs"
        if a.get("insuffisant"):  # historique Euronext encore court : lecture technique du marché américain, converti en €/t
            px = PROXY.get(prod)
            pd_, pv = proxy_eur(yahoo, px)
            fx_ = recale(pd_, pv, d, v)  # lecture de secours au niveau d'Euronext (sinon 155 €/t affichés pour un maïs à 247)
            pv = [x * fx_ for x in pv]
            if len(pv) >= 30:
                pa = ind.analyse(pd_, pv)
                prs, phs = pa.pop("_rsi", None), pa.pop("_histo", None)
                m20, m50 = ind.sma(pv, 20), ind.sma(pv, 50)
                kk = max(0, len(pv) - 120)
                nom_px = (yahoo.get(px) or {}).get("nom", px)
                info.update(score_technique=ind.score_technique(pa), feu=ind.feu_execution(pa),
                            proxy={"ticker": px, "nom": nom_px, "technique": pa, "series": mini_series(pd_, prs, phs),
                                   "niveaux": ind.niveaux(pa),
                                   "graphique": [[pd_[i], round(pv[i], 2), round(m20[i], 2) if m20[i] else None,
                                                  round(m50[i], 2) if m50[i] else None] for i in range(kk, len(pv))],
                                   "texte": f"Historique Euronext de {a['seances']} séance(s), 30 nécessaires (environ 6 semaines) : en attendant, "
                                            f"lecture technique de {nom_px} converti en €/t et recalé sur le cours Euronext du jour"})
        mm20, mm50 = ind.sma(v, 20), ind.sma(v, 50)
        k = max(0, len(v) - 120)
        info["graphique"] = [[d[i], round(v[i], 2), round(mm20[i], 2) if mm20[i] else None, round(mm50[i], 2) if mm50[i] else None]
                             for i in range(k, len(v))]
        fd, fv = front_series(eur, prod)
        lv = long_views(fd, fv) if len(fd) >= 260 else None
        if lv and lv["semaines"] >= 104:  # au moins 2 ans de cours officiels Euronext : vues longues et thermomètre sur Euronext
            info["long"] = {**lv, "source": "euronext", "nom": "Euronext (échéance la plus proche)", "euronext_depuis": fd[0]}
        else:  # historique encore court : marché américain converti en €/t et recalé sur Euronext
            info["long"] = vue_longue(yahoo, PROXY.get(prod), d, v)
        contrats[prod] = info
        if prod == "EBM":
            series_ble = (d, v)

    moisson = {"EBM": 7, "ECO": 7, "EMA": 10}
    for prod, info in contrats.items():
        if info.get("long"):
            info["thermo"] = dec.thermometre(info["long"].get("cinq_ans"), info.get("dernier_reel")
                                             if info["long"].get("source") == "euronext" else None)
            if info["thermo"]:
                info["thermo"]["source"] = "Euronext" if info["long"].get("source") == "euronext" else info["long"].get("nom")
                info["thermo"]["euronext"] = info["long"].get("source") == "euronext"
        if info.get("_curve") and info.get("echeance"):
            info["stockage"] = dec.stockage(info["_curve"], info["echeance"], lambda m, p=prod: expiry(p, m), today, moisson[prod],
                                           {k: v for k, v in CFG["stockage"].items() if not k.startswith("_")})
        places = (CFG.get("primeLocale") or {}).get(info.get("culture"))
        if places:
            info["prime_locale"] = dec.prime_locale(read_csv(PRIV / "physique_hist.csv"), places, front_on(eur, prod))
    longue = as_dict(load_json(PRIV / "yahoo_long.json", {}))
    src_s = longue if all(k in longue for k in ("ZW=F", "ZC=F", "EURUSD=X")) else yahoo
    saison = {}
    for cult, tk, deb in (("ble", "ZW=F", 7), ("mais", "ZC=F", 10)):
        sd, sv = proxy_eur(src_s, tk)
        sp = dec.saisonnier(sd, sv, deb) if sv else None
        if sp:
            sp["source"] = f"{(yahoo.get(tk) or {}).get('nom', tk)} converti en €/t, campagnes {sd[0][:4]}-{sd[-1][:4]}"
            saison[cult] = sp
    usda = as_dict(load_json(PRIV / "usda.json", {}))
    bil, prec = as_dict(usda.get("bilans")), as_dict(usda.get("precedent"))
    stocks = {}
    for cult in ("ble", "mais", "orge", "colza"):
        r = dec.stocks_conso(as_dict(bil.get(cult)), as_dict(prec.get(cult)), hors_chine=cult in ("ble", "mais"))
        if r:
            stocks[cult] = r
    if stocks:
        def jour(h):  # « Fri, 09 Oct 2026 15:40:43 GMT » → 2026-10-09
            try:
                return email.utils.parsedate_to_datetime(h).date().isoformat()
            except (TypeError, ValueError):
                return None
        stocks["_source"] = {"dates": {k: jour(v) for k, v in as_dict(usda.get("maj")).items()},
                             "precedent": {k: jour(v) for k, v in as_dict(usda.get("precedent_maj")).items() if v}}
    meteo_raw = as_dict(load_json(PRIV / "meteo.json", {}))
    zones = {}
    for zn in (CFG.get("meteo") or {}).get("zones", {}):
        zr = as_dict(meteo_raw.get(zn))
        frais = str(zr.get("prevision_au", ""))[:10] >= (today - timedelta(days=2)).isoformat()
        z = dec.meteo_zone({k: tuple(v) for k, v in as_dict(zr.get("archive")).items()},
                           {k: tuple(v) for k, v in as_dict(zr.get("prevision")).items()} if frais else {}, today)
        if z:
            z["etat"] = dec.meteo_etat(z)[1]
            zones[zn] = z
    meteo = dec.meteo_score(zones, CFG["meteo"], today) if zones else {}

    cot = {}
    for code, c in CFG["cftc"]["marches"].items():
        rd = cot_reading((cftc.get(code) or {}).get("serie"), today=today)
        if rd:
            sc_ = cot_score(rd["indice"])
            rd.update(nom=c["nom"], culture=c["culture"], score=round(sc_, 2) if sc_ is not None else None, source="cftc")
            cot[code] = rd
    for prod, (nom_, cult_) in COT_EURONEXT.items():  # fonds d'investissement sur Euronext : la lecture directe du marché français
        rd = cot_reading((cot_eu.get(prod) or {}).get("serie"), mini=26, today=today)
        if rd:
            sc_ = cot_score(rd["indice"])
            rd.update(nom=nom_, culture=cult_, score=round(sc_, 2) if sc_ is not None else None, source="euronext")
            cot["EURONEXT_" + prod] = rd

    eurusd = (yahoo.get("EURUSD=X") or {}).get("serie") or {}
    brent = (yahoo.get("BZ=F") or {}).get("serie") or {}
    e20, b20 = chg(eurusd, 20), chg(brent, 20)

    def macro(cult):
        if e20 is None and b20 is None:
            return None
        s = -clamp((e20 or 0) / 2, -1, 1) * 0.5  # euro qui monte : export européen moins compétitif
        if cult == "colza":
            s += clamp((b20 or 0) / 10, -1, 1) * 0.75
        elif cult == "mais":
            s += clamp((b20 or 0) / 10, -1, 1) * 0.25
        return round(s, 2)

    # ------------------------------------------------------------------- psychologie des marchés : humeur peur ↔ euphorie
    # (RSI, écart à la MM200, élan sur 20 séances, position des fonds) ; éclairage seulement : sur Euronext depuis 2019, elle
    # n'a pas annoncé la suite des prix (backtest, onglet Méthode), elle n'entre donc pas dans la note de marché
    for prod, ci in contrats.items():
        ser = list((ci.get("_serie") or {}).values())
        f, fsrc = (cot.get("EURONEXT_" + prod) or {}).get("indice"), "fonds sur Euronext"
        if f is None and ci.get("culture") in ("ble", "mais"):
            us = [x["indice"] for x in cot.values() if x.get("culture") == ci["culture"] and x.get("source") == "cftc" and x.get("indice") is not None]
            f, fsrc = (sum(us) / len(us), "fonds à Chicago (CFTC)") if us else (None, None)
        ps = dec.psychologie(ser, f)
        if ps:
            ps["fonds_source"] = fsrc if f is not None else None
            ci["psychologie"] = ps
    gp = as_dict(load_json(PRIV / "gpr.json", {}))
    geo = dec.geopolitique(gp.get("quotidien"), as_dict(gp.get("mensuel")), CFG["geopolitique"]["pays"], gp.get("evenements"), today)
    actu = as_dict(load_json(OUT / "actualites.json", {}))
    actu_frais = str(actu.get("date", "")) >= (today - timedelta(days=2)).isoformat()
    pression = as_dict(actu.get("pression")) if actu_frais else {}

    W, WC = CFG["poids"], CFG["poidsComite"]
    com_refs = as_dict(comite.get("references"))

    def com_shift(prod):
        """Niveaux du comité fixés sur l'échéance de référence du jour du comité : après un changement d'échéance, ils sont
        décalés de l'écart entre la nouvelle et l'ancienne échéance (courbe du jour, sinon ajustement du raccord)."""
        ci = contrats.get(prod) or {}
        cr, cur = com_refs.get(prod), ci.get("echeance")
        if not cr or not cur or cr == cur:
            return 0.0
        rc = ci.get("_curve") or {}
        if cr in rc and cur in rc:
            return rc[cur] - rc[cr]
        return sum(r["ajustement"] for r in ci.get("_raccords") or []
                   if r["ajustement"] is not None and r["date"] > str(comite.get("date", ""))[:10])
    valid_comite = False
    if comite.get("date"):
        try:
            valid_comite = (today - date.fromisoformat(comite["date"][:10])).days <= CFG["comite"]["joursValidite"]
        except ValueError:
            pass
    cultures = {}
    for cult, nom in CULTURES.items():
        prod = {"ble": "EBM", "escourgeon": "EBM", "orge_printemps": "EBM", "colza": "ECO", "mais": "EMA"}[cult]
        ci = contrats.get(prod, {})
        base = "ble" if cult in ("escourgeon", "orge_printemps") else cult
        cots = [x["score"] for x in cot.values() if x["culture"] == base and x["score"] is not None and x.get("source") == "cftc"]
        cs = sum(cots) / len(cots) if cots else None
        if base == "colza" and cs is not None:
            cs *= 0.5  # soja et huile de soja US : lecture indirecte pour le colza
        eu = (cot.get("EURONEXT_" + prod) or {}).get("score")
        if eu is not None:  # Euronext 70 %, États-Unis 30 %
            cs = round(0.7 * eu + 0.3 * cs, 2) if cs is not None else eu
        parts = {"technique": ci.get("score_technique"), "cot": cs, "macro": macro(base), "meteo": (meteo.get(base) or {}).get("score")}
        num = sum(W[k] * v for k, v in parts.items() if v is not None)
        den = sum(W[k] for k, v in parts.items() if v is not None)
        q = round(num / den, 2) if den else None
        entry = {"nom": nom, "contrat": prod, "score_marche": q, "lecture_marche": matrix(q), "composantes": parts,
                 "feu": ci.get("feu"), "niveaux": ci.get("niveaux"), "proxy": cult in ("escourgeon", "orge_printemps")}
        cc = (comite.get("cultures") or {}).get(cult) if valid_comite else None
        if cc and cc.get("signal") in SIGNAUX:
            entry.update(signal=cc["signal"], source="comite", comite=cc)
            sc = fnum(cc.get("score"))
            then = ((comite.get("chiffres") or {}).get(cult) or {}).get("composantes") or {}
            if sc is not None:
                delta = sum(WC[k] * (parts[k] - then[k]) for k in WC if parts.get(k) is not None and then.get(k) is not None)
                entry["score_actualise"] = round(sc + delta, 2)
                if matrix(entry["score_actualise"]) != matrix(sc):
                    entry["a_revoir"] = (f"Depuis le comité, la technique, les fonds et la macro font passer le score de {sc:+.2f} à "
                                         f"{entry['score_actualise']:+.2f} : signal à revoir")
        else:
            entry.update(signal="TENIR", source="sans_comite",
                         note="Pas d'avis du comité valide : plan calendaire par défaut ; la lecture de marché seule ne suffit pas à vendre")
        # une seule série de niveaux par culture : ceux du comité s'il en a fixé, sinon les niveaux techniques
        tech = ci.get("niveaux") or {}
        cc_ = entry.get("comite") or {}
        c_ord = [float(x) for x in (cc_.get("ordres") or []) if fnum(x) is not None]
        cur = (ci.get("technique") or {}).get("dernier")
        if c_ord or fnum(cc_.get("revision_bas")) is not None:
            dl = com_shift(prod)
            q4 = lambda x: round(x * 4) / 4  # noqa: E731
            rv = fnum(cc_.get("revision_bas"))
            ret = {"source": "comite", "ordres": sorted(q4(x + dl) for x in c_ord if cur is None or x + dl > cur),
                   "revision": q4(rv + dl) if rv is not None else None, "decalage_echeance": round(dl, 2)}
        elif cult not in ("escourgeon", "orge_printemps") and not ci.get("proxy"):
            ret = {"source": "technique", "ordres": tech.get("ordres") or [], "revision": tech.get("revision")}
        else:
            ret = {"source": "aucun", "ordres": [], "revision": None}
        ret.update(contrat=prod, echeance=ci.get("echeance"), sur_ble=cult in ("escourgeon", "orge_printemps"))
        entry["niveaux_retenus"] = ret
        entry["libelle"] = SIGNAUX.get(entry["signal"] or "", "—")
        cultures[cult] = entry

    for cult, e in cultures.items():
        e["plan"] = plan_vente(cult, today, e, contrats)
        # probabilité que chaque ordre (et le seuil de révision) soit touché d'ici la fin de la tranche due (volatilité des
        # 3 derniers mois, sans tendance) : aide à placer des ordres réalistes
        nr = e["niveaux_retenus"]
        ci = contrats.get(nr.get("contrat")) or {}
        s0, ser = ci.get("dernier_reel"), list((ci.get("_serie") or {}).values())
        vj = dec.vol_quotidienne(ser) if ser else None
        due = next((p for p in e["plan"] if p.get("statut") == "due" and not p.get("avant_moisson")), None) or \
            next((p for p in e["plan"] if p.get("statut") == "due"), None)
        fin = date.fromisoformat(due["fin"]) if due and due.get("fin") else today + timedelta(days=30)
        n = max(5, sum(1 for k in range((fin - today).days) if (today + timedelta(days=k + 1)).weekday() < 5))
        # biais d'ancrage : le plus haut de la campagne (série ajustée, au niveau de l'échéance du jour) et la chance de le revoir
        # d'ici la fin de la tranche ; « attendre encore 5 € » : chances de les voir, et risque de voir le cours reculer de 5 €
        if s0 and vj:
            deb = 10 if cult == "mais" else 7
            y0 = today.year if today.month >= deb else today.year - 1
            camp = {d_: v_ for d_, v_ in (ci.get("_serie") or {}).items() if d_ >= f"{y0}-{deb:02d}-01"}
            if len(camp) >= 10:
                dh = max(camp, key=camp.get)
                hi = camp[dh]
                e["biais"] = {"plus_haut": round(hi, 2), "plus_haut_le": dh, "ecart": round(s0 - hi, 2), "depuis": f"{y0}-{deb:02d}-01",
                              "chance_plus_haut": dec.proba_toucher(s0, hi, vj, n) if hi > s0 * 1.005 else None,
                              "gagner5": dec.proba_toucher(s0, s0 + 5, vj, n), "perdre5": dec.proba_toucher(s0, s0 - 5, vj, n),
                              "horizon": fin.isoformat(), "sur_ble": cult in ("escourgeon", "orge_printemps")}
        if pression.get(ACTU_CLE.get(cult)):
            e["actualite"] = pression[ACTU_CLE[cult]]
        if s0 and vj and (nr.get("ordres") or nr.get("revision")):
            nr["probas"] = {"horizon": fin.isoformat(), "seances": n, "vol_annuelle": round(vj * math.sqrt(252) * 100, 1),
                            "ordres": [dec.proba_toucher(s0, o, vj, n) for o in nr.get("ordres") or []],
                            "revision": dec.proba_toucher(s0, nr["revision"], vj, n) if nr.get("revision") else None,
                            "cours": s0}
    for prod, main in (("EBM", "ble"), ("ECO", "colza"), ("EMA", "mais")):
        if prod in contrats and main in cultures:
            contrats[prod]["niveaux_retenus"] = cultures[main]["niveaux_retenus"]
    org = orges(today, series_ble[1])
    eb = contrats.get("EBM") or {}
    for cult, e in org.items():
        gap = e.get("ecart_ble")
        nrc = (cultures.get(cult) or {}).get("niveaux_retenus") or {}
        if gap is not None and eb.get("graphique"):
            sh = lambda r: [r[0]] + [round(x + gap, 2) if x is not None else None for x in r[1:4]]  # noqa: E731
            phys = {p_[0]: p_[1] for p_ in e.get("graphique") or []}
            e["estime"] = {
                "ecart": gap,
                "graphique": [sh(r) for r in eb["graphique"]],
                "long": None,  # vues 1 an / 5 ans : reconstruites par la page à partir de celles du blé (évite de publier deux copies)
                "long_depuis_ble": bool(eb.get("long")),
                "technique": decale(eb.get("technique"), gap), "series": eb.get("series"),
                # niveaux de la culture (comité ou aucun), exprimés au niveau de l'orge : mêmes chiffres que la carte Signaux
                "niveaux": ({"ordres": [round(o + gap, 2) for o in (nrc.get("ordres") or [])],
                             "revision": round(nrc["revision"] + gap, 2) if nrc.get("revision") else None}),
            }
            # points physiques réels par-dessus (4e colonne)
            for r in e["estime"]["graphique"]:
                r.append(phys.get(r[0]))
    for cult, e in org.items():
        if cult in cultures:
            cultures[cult]["physique"] = {k: e.get(k) for k in ("prix", "date", "place", "fourragere", "prime", "ecart_ble", "rouen_rendu")}
            if e.get("estime"):
                cultures[cult]["niveaux_retenus"]["equivalent_orge"] = e["estime"]["niveaux"]
    engrais = module_engrais(today, series_ble[0], series_ble[1], yahoo)
    if valid_comite and comite.get("engrais", {}).get("signal") in SIG_ENGRAIS:
        engrais["comite"] = comite["engrais"]

    # ------------------------------------------------------------------- carnet de bord : chaque avis du comité, noté à 4 et 8 semaines
    carnet = [x for x in (load_json(OUT / "carnet.json", []) or []) if isinstance(x, dict) and x.get("id")]
    cdate = str(comite.get("date", ""))[:10]
    for cult, e in cultures.items():
        ci = contrats.get(e["contrat"]) or {}
        if e.get("source") == "comite" and ci.get("seance"):
            px = (e.get("physique") or {}).get("prix") if e.get("proxy") else ci.get("dernier_reel")
            dec.carnet_ajoute(carnet, cult, ci["seance"], e["signal"], px, cdate, (e.get("comite") or {}).get("pct") or "")
    uree = {r["date"]: float(r["price"]) for r in read_csv(PRIV / "fert_fr.csv") if r.get("product") == "uree" and fnum(r.get("price"))}
    if (engrais.get("comite") or {}).get("signal") and uree:
        last_u = max(uree)
        dec.carnet_ajoute(carnet, "engrais", last_u, engrais["comite"]["signal"], uree[last_u], cdate, engrais["comite"].get("pct") or "")
    for x in carnet:
        if x["cle"] == "engrais":
            dec.carnet_note(x, uree, today, engrais=True)
        else:
            prod = {"ble": "EBM", "escourgeon": "EBM", "orge_printemps": "EBM", "colza": "ECO", "mais": "EMA"}.get(x["cle"])
            dec.carnet_note(x, (contrats.get(prod) or {}).get("_serie") or {}, today)
    carnet = sorted(carnet, key=lambda x: (x["date"], x["cle"]))[-120:]
    save_json(OUT / "carnet.json", carnet)

    # ------------------------------------------------------------------- déclencheurs (comparaison avec la veille)
    trig = []

    def add(key, titre, detail, grave=False):
        trig.append({"id": f"{today.isoformat()}:{key}", "titre": titre, "detail": detail, "grave": grave})

    prev = etat.get("contrats", {})
    marques = {}  # dates des derniers « plus bas / plus haut de 3 mois » signalés (pas d'alerte répétée chaque jour)

    def recent(dt, days=14):
        try:
            return dt and (today - date.fromisoformat(dt)).days < days
        except ValueError:
            return False

    for prod, ci in contrats.items():
        a = ci.get("technique") or {}
        p = prev.get(prod, {})
        marques[prod] = {"bas3m_le": p.get("bas3m_le"), "haut3m_le": p.get("haut3m_le")}
        if a.get("insuffisant") or "dernier" not in a:
            continue
        if p.get("seance") == ci["seance"]:
            continue  # pas de nouvelle séance : rien à comparer
        nom = ci["nom"]
        last = a["dernier"]
        # cours de la veille pris dans la série ajustée : un changement d'échéance ne passe pas pour un mouvement de prix
        pl = (ci.get("_serie") or {}).get(p.get("seance"), p.get("dernier"))
        if pl is not None:
            if last < a["bas3m_hier"] and not recent(p.get("bas3m_le")):
                add(prod + ":bas3m", f"{nom} : nouveau plus bas de 3 mois ({last:.2f})", "Le score est à revoir (cadre de vente, règle 3)", True)
                marques[prod]["bas3m_le"] = today.isoformat()
            elif last > a["haut3m_hier"] and not recent(p.get("haut3m_le")):
                add(prod + ":haut3m", f"{nom} : nouveau plus haut de 3 mois ({last:.2f})", "Moment favorable pour une tranche prévue", True)
                marques[prod]["haut3m_le"] = today.isoformat()
            rs, rp = a.get("rsi"), p.get("rsi")
            if rs is not None and rp is not None:
                if rs < 30 <= rp:
                    add(prod + ":rsi30", f"{nom} : RSI sous 30 ({rs:.0f})", "Survente : ne pas vendre le creux, placer les ordres sur rebond")
                if rs > 70 >= rp:
                    add(prod + ":rsi70", f"{nom} : RSI au-dessus de 70 ({rs:.0f})", "Surachat : fenêtre pour une tranche")
            h, hp = a.get("histo"), p.get("histo")
            if h is not None and hp is not None and (h > 0) != (hp > 0):
                add(prod + ":macd", f"{nom} : croisement {'haussier' if h > 0 else 'baissier'} du MACD", f"Histogramme {hp:+.2f} → {h:+.2f}")
            # niveaux du comité (ordres et seuils de révision), décalés si l'échéance de référence a changé depuis le comité
            dl = com_shift(prod)
            for t in ((comite.get("declencheurs") or []) if valid_comite else []):
                if t.get("contrat") != prod or fnum(t.get("niveau")) is None:
                    continue
                lv = round((float(t["niveau"]) + dl) * 4) / 4
                if (t.get("sens") == ">" and pl <= lv < last) or (t.get("sens") == "<" and pl >= lv > last):
                    add(f"{prod}:niveau:{lv}", f"{nom} : niveau {lv:g} franchi ({last:.2f})", t.get("texte") or "Niveau fixé par le comité", True)
    for cult, e in cultures.items():  # changement de signal, pour toutes les cultures (orges comprises), séance nouvelle ou non
        old_sig = (etat.get("signaux") or {}).get(cult)
        new_sig = e.get("signal")
        if old_sig and new_sig and old_sig != new_sig:
            add(cult + ":signal", f"{e['nom']} : signal {SIGNAUX.get(old_sig, old_sig)} → {SIGNAUX.get(new_sig, new_sig)}", "Changement de signal", True)
    for cult, e in cultures.items():
        if e.get("a_revoir") and not (etat.get("a_revoir") or {}).get(cult):
            add(f"{cult}:revoir", f"{e['nom']} : signal du comité à revoir", e["a_revoir"], True)
    pe = etat.get("engrais", {})
    meme_base = pe.get("base", engrais.get("base")) == engrais.get("base")  # ratio estimé ↔ mondial : pas un vrai mouvement
    if pe.get("signal") and pe["signal"] != engrais.get("signal") and meme_base:
        add("engrais:signal", f"Engrais : {SIG_ENGRAIS.get(pe['signal'])} → {engrais.get('libelle')}", " ; ".join(engrais.get("notes", [])), True)
    t = engrais.get("ttf") or {}
    if t.get("dernier") is not None and pe.get("ttf") is not None and pe.get("ttf_au") != t.get("au"):
        if t["dernier"] > CFG["engrais"]["ttfHaut"] >= pe["ttf"]:
            add("ttf:haut", f"Gaz TTF au-dessus de {CFG['engrais']['ttfHaut']} €/MWh ({t['dernier']:.1f})", "Acheter une tranche d'azote sans attendre", True)
        if t["sous_seuil_bas"] >= CFG["engrais"]["ttfBasSeances"] > pe.get("sous_seuil_bas", 0):
            add("ttf:bas", f"Gaz TTF sous {CFG['engrais']['ttfBas']} €/MWh depuis {CFG['engrais']['ttfBasSeances']} séances",
                "Fenêtre d'achat d'azote", True)
    if t.get("dernier") is not None and pe.get("ttf") is not None and pe.get("ttf_au") != t.get("au"):
        for c in ((comite.get("declencheurs") or []) if valid_comite else []):
            if c.get("contrat") != "TTF" or fnum(c.get("niveau")) is None:
                continue
            lv = float(c["niveau"])
            if (c.get("sens") == ">" and pe["ttf"] <= lv < t["dernier"]) or (c.get("sens") == "<" and pe["ttf"] >= lv > t["dernier"]):
                add(f"ttf:niveau:{lv}", f"Gaz TTF : niveau {lv:g} €/MWh franchi ({t['dernier']:.1f})", c.get("texte") or "Niveau fixé par le comité", True)
    for lvl in (CFG["engrais"]["ratioBas"], CFG["engrais"]["ratioMoyen"], CFG["engrais"]["ratioHaut"]):
        a0, a1 = pe.get("percentile"), engrais.get("percentile_retenu")
        if a0 is not None and a1 is not None and (a0 <= lvl) != (a1 <= lvl) and meme_base:
            add(f"ratio:{lvl}", f"Ratio azote/blé : passage du {lvl}e percentile ({a0} → {a1})", "Voir le module engrais")
    g0, g1 = pe.get("rattrapage"), engrais.get("rattrapage")
    rl = CFG["engrais"]["rattrapage"]
    if g0 is not None and g1 is not None and ((g0 <= rl) != (g1 <= rl) or (g0 >= -rl) != (g1 >= -rl)):
        add("rattrapage", f"Écart gaz − azote sur 3 mois : {g0:+.0f} → {g1:+.0f} pts", "Seuil de ±15 pts franchi")

    sources = as_dict(collecte.get("sources"))
    if str(collecte.get("date", ""))[:10] != today.isoformat():  # collecte du jour absente ou coupée : rien n'est daté d'aujourd'hui
        sources = {"collecte": {"ok": False, "detail": f"pas de collecte du jour (dernière : {str(collecte.get('date', '—'))[:16]})"}}
    pannes, msgs = suivi_pannes(sources, as_dict(etat.get("pannes")), today)
    for key, titre, detail in msgs:
        add(key, titre, detail)

    # ------------------------------------------------------------------- comité d'alerte demandé
    graves = [x for x in trig if x["grave"]]
    if graves:
        save_json(OUT / "demande-comite.json", {"date": today.isoformat(), "motifs": [x["titre"] for x in graves]})

    hist = (load_json(OUT / "grain-signal.json", {}).get("historique_declencheurs") or [])
    known = {x["id"] for x in hist}
    hist = ([x for x in trig if x["id"] not in known] + hist)[:60]

    dash = {
        "format": "grain-signal-1",
        "genere": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": today.isoformat(),
        "cultures": cultures,
        "contrats": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in contrats.items()},
        "international": inter,
        "orges": org,
        "cot": cot,
        "saison": saison,
        "stocks_mondiaux": stocks,
        "geopolitique": geo,
        "actualites": ({"date": actu.get("date"), "synthese": actu.get("synthese"), "synthese_du": actu.get("synthese_du"),
                        "pression": pression or None, "majeurs": len(actu.get("majeurs") or []), "compte": actu.get("compte"),
                        "sans_ia": actu.get("sans_ia"), "erreur": actu.get("erreur")} if actu_frais else None),
        "meteo": {"zones": zones, "cultures": meteo, "source": "Open-Meteo (CC BY 4.0)"},
        "carnet": {"entrees": carnet[-40:], "bilan": dec.carnet_bilan(carnet)},
        "macro": {"eurusd_var20": round(e20, 2) if e20 is not None else None, "brent_var20": round(b20, 2) if b20 is not None else None},
        "engrais": engrais,
        "physique": load_json(OUT / "physique.json", {}),
        # déclencheurs du jour : ceux de ce calcul et ceux d'un calcul précédent du même jour (le workflow calcule deux fois :
        # au 2e passage, etat.json est déjà à jour et trig est vide, alors que l'email est parti)
        "declencheurs": [x for x in hist if x["id"].startswith(today.isoformat() + ":")],
        "historique_declencheurs": hist,
        "collecte": collecte,
        "comite": {"date": comite.get("date"), "valide": valid_comite, "mode": comite.get("mode"), "resume": comite.get("resume"),
                   "calendrier": comite.get("calendrier"), "modele": comite.get("modele"), "cout_usd": comite.get("cout_usd"),
                   "erreur": comite.get("erreur")},
        "config": {"poids": W, "engrais": CFG["engrais"], "comite_modele": CFG["comite"]["modele"],
                   "calendrier": {k: v for k, v in (CFG.get("calendrier") or {}).items() if not k.startswith("_")},
                   "stockage": {k: v for k, v in CFG["stockage"].items() if not k.startswith("_")}},
    }
    save_json(OUT / "grain-signal.json", dash)
    new_state = {
        "date": today.isoformat(),
        "contrats": {k: {"seance": v.get("seance"), "dernier": (v.get("technique") or {}).get("dernier"), "rsi": (v.get("technique") or {}).get("rsi"),
                         "histo": (v.get("technique") or {}).get("histo"), **marques.get(k, {})}
                     for k, v in contrats.items() if v.get("technique")},
        "signaux": {k: v.get("signal") for k, v in cultures.items()},
        "a_revoir": {k: bool(v.get("a_revoir")) for k, v in cultures.items()},
        "engrais": {"signal": engrais.get("signal"), "percentile": engrais.get("percentile_retenu"), "base": engrais.get("base"), "rattrapage": engrais.get("rattrapage"),
                    "ttf": (engrais.get("ttf") or {}).get("dernier"), "ttf_au": (engrais.get("ttf") or {}).get("au"),
                    "sous_seuil_bas": (engrais.get("ttf") or {}).get("sous_seuil_bas", 0)},
        "pannes": pannes,
        "envoyes": etat.get("envoyes", {}),
    }
    save_json(OUT / "etat.json", new_state)
    outbox = load_json(OUT / "prive" / "a-envoyer.json", [])
    sent = new_state["envoyes"]
    outbox = [x for x in outbox if x["id"] not in sent] + [x for x in trig if x["id"] not in sent and x["id"] not in {o["id"] for o in outbox}]
    save_json(OUT / "prive" / "a-envoyer.json", outbox)

    for cult, e in cultures.items():
        print(f"{e['nom']:<30} {e['libelle']:<24} marché {e['score_marche']} ({e['source']}) feu {(e.get('feu') or {}).get('code')}")
    print(f"Engrais : {engrais.get('libelle')} — {' ; '.join(engrais.get('notes', []))}")
    print(f"Déclencheurs du jour : {len(trig)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
