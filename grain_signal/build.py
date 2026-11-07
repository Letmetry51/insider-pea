"""
Grain Signal — calcul du matin : indicateurs, signaux de vente par culture, module engrais, déclencheurs.

Entrées : data/grain/prive/ (historiques de collect.py), data/grain/comite.json (dernier comité IA, facultatif).
Sorties : data/grain/grain-signal.json (page), data/grain/etat.json (mémoire d'un jour à l'autre), data/grain/prive/a-envoyer.json
(alertes du jour pour send_alerts.py), data/grain/demande-comite.json (comité d'alerte demandé).

  python grain_signal/build.py            (GS_TODAY=AAAA-MM-JJ pour rejouer un jour)
"""
import bisect
import csv
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import indicators as ind  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "data" / "grain"
PRIV = OUT / "prive"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
CULTURES = {"ble": "Blé tendre", "escourgeon": "Escourgeon brassicole", "orge_printemps": "Orge de printemps brassicole",
            "colza": "Colza", "mais": "Maïs"}
SIGNAUX = {"VENDRE": "🟢 VENDRE UNE TRANCHE", "TENIR": "🟡 TENIR LE PLAN", "ATTENDRE": "🔴 ATTENDRE-STOCKER", "COUVRIR": "🛡️ COUVRIR"}
PROXY = {"EBM": "ZW=F", "ECO": "RS=F", "EMA": "ZC=F"}
SIG_ENGRAIS = {"ACHETER_LARGE": "🟢 ACHETER LARGE", "SUIVRE": "🟡 SUIVRE LE PLAN", "FRACTIONNER": "🟠 FRACTIONNER", "ATTENDRE": "🔴 ATTENDRE"}


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


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
            old = by_date[dates[i]].get(refs[i - 1])
            if old is not None:
                adj = vals[i] - old
                for j in range(i):
                    vals[j] += adj
                raccords.append({"date": dates[i], "de": refs[i - 1], "vers": refs[i], "ajustement": round(adj, 2)})
            else:
                raccords.append({"date": dates[i], "de": refs[i - 1], "vers": refs[i], "ajustement": None})
    curve = by_date[dates[-1]] if dates else {}
    return dates, vals, (refs[-1] if refs else None), raccords, curve


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


# --------------------------------------------------------------------------------------------- COT et macro
def cot_reading(serie):
    if not serie or len(serie) < 20:
        return None
    nets = [s["long"] - s["short"] for s in serie]
    w = nets[-156:]
    lo, hi = min(w), max(w)
    idx = (nets[-1] - lo) / (hi - lo) * 100 if hi > lo else 50.0
    return {"date": serie[-1]["date"], "net": nets[-1], "variation": nets[-1] - nets[-2], "indice": round(idx, 0)}


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
    out["mondial"] = {"mois": last["month"], "uree": float(last["urea"]), "ble_hrw": float(last["wheat_hrw"]),
                      "ratio": round(ratios[-1], 3), "percentile": percentile(win, ratios[-1])}
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
        uree_rows = [r for r in rows if r["product"] == "uree"]
        mend = (date.fromisoformat(last["month"] + "-01") + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        u_ref = asof(uree_rows, mend.isoformat())
        i = bisect.bisect_right(ble_dates, mend.isoformat()) - 1
        if u_ref and i >= 0:
            est = ratios[-1] * (fr["uree"]["prix"] / float(u_ref["price"])) / (ble_vals[-1] / ble_vals[i])
            out["estimation"] = {"ratio": round(est, 3), "percentile": percentile(win, est),
                                 "methode": f"ratio mondial de {last['month']} corrigé de l'évolution de l'urée France "
                                            f"(depuis le {u_ref['date']}) et du blé Euronext (depuis le {ble_dates[i]})"}
    pct = out.get("estimation", {}).get("percentile", out["mondial"]["percentile"])
    out["percentile_retenu"] = pct
    # gaz TTF (Yahoo) : niveau, tendance, rattrapage du jour
    ttf = (yahoo.get("TTF=F") or {}).get("serie") or {}
    if len(ttf) > 70:
        d, v = list(ttf.keys()), list(ttf.values())
        a = ind.analyse(d, v)
        out["ttf"] = {k: a.get(k) for k in ("dernier", "au", "var1s", "var1m", "var3m", "mm20", "ecart_mm20", "mm50", "rsi", "histo",
                                             "croisement_macd", "haut3m", "bas3m")}
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


# --------------------------------------------------------------------------------------------- calcul principal
def main():
    today = date.fromisoformat(os.environ["GS_TODAY"]) if os.environ.get("GS_TODAY") else datetime.now(timezone.utc).date()
    eur = read_csv(PRIV / "euronext.csv")
    yahoo = load_json(PRIV / "yahoo.json", {})
    cftc = load_json(PRIV / "cftc.json", {})
    if not (OUT / "comite.json").exists() and (HERE / "seed" / "comite-initial.json").exists():
        (OUT / "comite.json").write_bytes((HERE / "seed" / "comite-initial.json").read_bytes())  # premier calcul : comité du 07/11/2026
    comite = load_json(OUT / "comite.json", {})
    etat = load_json(OUT / "etat.json", {})
    collecte = load_json(OUT / "collecte.json", {})

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
        a.pop("_rsi", None)
        a.pop("_histo", None)
        info = {"nom": c["nom"], "culture": c["culture"], "echeance": ref, "technique": a, "score_technique": ind.score_technique(a),
                "feu": ind.feu_execution(a), "niveaux": ind.niveaux(a), "courbe": courbe(prod, curve, ref), "raccords": rac[-3:],
                "dernier_reel": curve.get(ref), "seance": d[-1]}
        recent = [r for r in rac if r["ajustement"] is None and r["date"] >= d[max(0, len(d) - 63)]]
        if recent:
            info["alerte_raccord"] = f"Changement d'échéance du {recent[-1]['date']} non ajusté (pas de cotation commune) : indicateurs approximatifs"
        if a.get("insuffisant"):  # historique Euronext encore court : lecture technique du marché américain correspondant
            px = PROXY.get(prod)
            if px in inter:
                info.update(score_technique=inter[px]["score_technique"], feu=ind.feu_execution(inter[px]["technique"]),
                            proxy={"ticker": px, "nom": inter[px]["nom"],
                                   "texte": f"Historique Euronext de {a['seances']} séances (30 nécessaires) : lecture technique de {inter[px]['nom']}"})
        mm20, mm50 = ind.sma(v, 20), ind.sma(v, 50)
        k = max(0, len(v) - 120)
        info["graphique"] = [[d[i], round(v[i], 2), round(mm20[i], 2) if mm20[i] else None, round(mm50[i], 2) if mm50[i] else None]
                             for i in range(k, len(v))]
        contrats[prod] = info
        if prod == "EBM":
            series_ble = (d, v)

    cot = {}
    for code, c in CFG["cftc"]["marches"].items():
        rd = cot_reading((cftc.get(code) or {}).get("serie"))
        if rd:
            rd.update(nom=c["nom"], culture=c["culture"], score=cot_score(rd["indice"]))
            cot[code] = rd

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

    W, WC = CFG["poids"], CFG["poidsComite"]
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
        cots = [x["score"] for x in cot.values() if x["culture"] == base and x["score"] is not None]
        cs = sum(cots) / len(cots) if cots else None
        if base == "colza" and cs is not None:
            cs *= 0.5  # soja et huile de soja US : lecture indirecte pour le colza
        parts = {"technique": ci.get("score_technique"), "cot": cs, "macro": macro(base)}
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
        entry["libelle"] = SIGNAUX.get(entry["signal"] or "", "—")
        cultures[cult] = entry

    engrais = module_engrais(today, series_ble[0], series_ble[1], yahoo)
    if valid_comite and comite.get("engrais", {}).get("signal") in SIG_ENGRAIS:
        engrais["comite"] = comite["engrais"]

    # ------------------------------------------------------------------- déclencheurs (comparaison avec la veille)
    trig = []

    def add(key, titre, detail, grave=False):
        trig.append({"id": f"{today.isoformat()}:{key}", "titre": titre, "detail": detail, "grave": grave})

    prev = etat.get("contrats", {})
    for prod, ci in contrats.items():
        a = ci.get("technique") or {}
        if a.get("insuffisant") or "dernier" not in a:
            continue
        p = prev.get(prod, {})
        if p.get("seance") == ci["seance"]:
            continue  # pas de nouvelle séance : rien à comparer
        nom = ci["nom"]
        last = a["dernier"]
        if p.get("dernier") is not None:
            if last < a["bas3m_hier"]:
                add(prod + ":bas3m", f"{nom} : nouveau plus bas de 3 mois ({last:.2f})", "Le score est à revoir (cadre de vente, règle 3)", True)
            elif last > a["haut3m_hier"]:
                add(prod + ":haut3m", f"{nom} : nouveau plus haut de 3 mois ({last:.2f})", "Moment favorable pour une tranche prévue", True)
            rs, rp = a.get("rsi"), p.get("rsi")
            if rs is not None and rp is not None:
                if rs < 30 <= rp:
                    add(prod + ":rsi30", f"{nom} : RSI sous 30 ({rs:.0f})", "Survente : ne pas vendre le creux, placer les ordres sur rebond")
                if rs > 70 >= rp:
                    add(prod + ":rsi70", f"{nom} : RSI au-dessus de 70 ({rs:.0f})", "Surachat : fenêtre pour une tranche")
            h, hp = a.get("histo"), p.get("histo")
            if h is not None and hp is not None and (h > 0) != (hp > 0):
                add(prod + ":macd", f"{nom} : croisement {'haussier' if h > 0 else 'baissier'} du MACD", f"Histogramme {hp:+.2f} → {h:+.2f}")
            # niveaux du comité (ordres et seuils de révision)
            for t in ((comite.get("declencheurs") or []) if valid_comite else []):
                if t.get("contrat") != prod or fnum(t.get("niveau")) is None:
                    continue
                lv, pl = float(t["niveau"]), p["dernier"]
                if (t.get("sens") == ">" and pl <= lv < last) or (t.get("sens") == "<" and pl >= lv > last):
                    add(f"{prod}:niveau:{lv}", f"{nom} : niveau {lv:g} franchi ({last:.2f})", t.get("texte") or "Niveau fixé par le comité", True)
        old_sig = (etat.get("signaux") or {}).get(ci.get("culture"))
        new_sig = cultures.get(ci.get("culture"), {}).get("signal")
        if old_sig and new_sig and old_sig != new_sig:
            add(prod + ":signal", f"{nom} : signal {SIGNAUX.get(old_sig, old_sig)} → {SIGNAUX.get(new_sig, new_sig)}", "Changement de signal", True)
    for cult, e in cultures.items():
        if e.get("a_revoir") and not (etat.get("a_revoir") or {}).get(cult):
            add(f"{cult}:revoir", f"{e['nom']} : signal du comité à revoir", e["a_revoir"], True)
    pe = etat.get("engrais", {})
    if pe.get("signal") and pe["signal"] != engrais.get("signal"):
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
        if a0 is not None and a1 is not None and (a0 <= lvl) != (a1 <= lvl):
            add(f"ratio:{lvl}", f"Ratio azote/blé : passage du {lvl}e percentile ({a0} → {a1})", "Voir le module engrais")
    g0, g1 = pe.get("rattrapage"), engrais.get("rattrapage")
    rl = CFG["engrais"]["rattrapage"]
    if g0 is not None and g1 is not None and ((g0 <= rl) != (g1 <= rl) or (g0 >= -rl) != (g1 >= -rl)):
        add("rattrapage", f"Écart gaz − azote sur 3 mois : {g0:+.0f} → {g1:+.0f} pts", "Seuil de ±15 pts franchi")

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
        "cot": cot,
        "macro": {"eurusd_var20": round(e20, 2) if e20 is not None else None, "brent_var20": round(b20, 2) if b20 is not None else None},
        "engrais": engrais,
        "physique": load_json(OUT / "physique.json", {}),
        "declencheurs": trig,
        "historique_declencheurs": hist,
        "collecte": collecte,
        "comite": {"date": comite.get("date"), "valide": valid_comite, "mode": comite.get("mode"), "resume": comite.get("resume"),
                   "calendrier": comite.get("calendrier"), "modele": comite.get("modele"), "cout_usd": comite.get("cout_usd"),
                   "erreur": comite.get("erreur")},
        "config": {"poids": W, "engrais": CFG["engrais"], "comite_modele": CFG["comite"]["modele"]},
    }
    save_json(OUT / "grain-signal.json", dash)
    new_state = {
        "date": today.isoformat(),
        "contrats": {k: {"seance": v.get("seance"), "dernier": (v.get("technique") or {}).get("dernier"), "rsi": (v.get("technique") or {}).get("rsi"),
                         "histo": (v.get("technique") or {}).get("histo")} for k, v in contrats.items() if v.get("technique")},
        "signaux": {k: v.get("signal") for k, v in cultures.items()},
        "a_revoir": {k: bool(v.get("a_revoir")) for k, v in cultures.items()},
        "engrais": {"signal": engrais.get("signal"), "percentile": engrais.get("percentile_retenu"), "rattrapage": engrais.get("rattrapage"),
                    "ttf": (engrais.get("ttf") or {}).get("dernier"), "ttf_au": (engrais.get("ttf") or {}).get("au"),
                    "sous_seuil_bas": (engrais.get("ttf") or {}).get("sous_seuil_bas", 0)},
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
