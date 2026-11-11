"""
Grain Signal — calcul du matin : lecture du marché par culture (cours, technique, actualité, repères), module engrais, alertes.
Un outil d'aide à la décision : il décrit le marché, il ne dit jamais quoi vendre ni quand.

Entrées : data/grain/prive/ (historiques de collect.py), data/grain/actualites.json, data/grain/comite.json (lecture hebdomadaire).
Sorties : data/grain/grain-signal.json (page), data/grain/etat.json (mémoire d'un jour à l'autre), data/grain/prive/a-envoyer.json
(alertes du jour pour send_alerts.py).

  python grain_signal/build.py            (GS_TODAY=AAAA-MM-JJ pour rejouer un jour)
"""
import bisect
import csv
import email.utils
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from commun import load as load_json, save as save_json  # noqa: E402

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
PROXY = {"EBM": "ZW=F", "ECO": "ZL=F", "EMA": "ZC=F"}  # colza : huile de soja (le canola ICE n'est pas sur Yahoo)
# conversion en $/t : blé 36,744 boisseaux/t, maïs 39,368 boisseaux/t (cents/boisseau) ; huile de soja 2 204,62 livres/t (cents/livre)
TONNE = {"ZW=F": 36.744, "KE=F": 36.744, "ZC=F": 39.368, "ZS=F": 36.744, "ZL=F": 2204.62}


def as_dict(v):
    return v if isinstance(v, dict) else {}


def clean_comite(c):
    """Lecture du comité relue défensivement : arguments haussiers et baissiers (listes de textes courts) par culture."""
    c = as_dict(c)
    txt = lambda v, n=300: str(v)[:n] if isinstance(v, (str, int, float)) and str(v).strip() else None  # noqa: E731
    cults = {}
    for k, v in as_dict(c.get("cultures")).items():
        if isinstance(v, dict) and (v.get("haussier") or v.get("baissier") or v.get("lecture")):
            cults[k] = {"haussier": [txt(x) for x in (v.get("haussier") or []) if txt(x)][:5] if isinstance(v.get("haussier"), list) else [],
                        "baissier": [txt(x) for x in (v.get("baissier") or []) if txt(x)][:5] if isinstance(v.get("baissier"), list) else [],
                        "a_surveiller": txt(v.get("a_surveiller")), "lecture": txt(v.get("lecture"))}
    return {"format": c.get("format"), "date": c.get("date"), "mode": c.get("mode"), "resume": txt(c.get("resume"), 800), "cultures": cults,
            "calendrier": [x for x in (c.get("calendrier") if isinstance(c.get("calendrier"), list) else []) if isinstance(x, dict)],
            "modele": c.get("modele"), "cout_usd": c.get("cout_usd"), "erreur": c.get("erreur")}


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
CONTRAT = {"ble": "EBM", "escourgeon": "EBM", "orge_printemps": "EBM", "colza": "ECO", "mais": "EMA"}
COT_EURONEXT = {"EBM": ("Blé tendre Euronext (fonds)", "ble"), "ECO": ("Colza Euronext (fonds)", "colza"),
                "EMA": ("Maïs Euronext (fonds)", "mais")}


def nom_source(src):
    """Nom lisible d'une source de collecte (« yahoo_TTF=F » → « Gaz TTF (Yahoo Finance) »)."""
    pre, _, k = src.partition("_")
    if pre == "yahoo":
        return f"{CFG['yahoo'].get(k, k)} (Yahoo Finance)" if k in CFG["yahoo"] else "Historique long Yahoo Finance"
    if pre == "euronext":
        return f"Euronext {(CFG['euronext'].get(k) or {}).get('nom', k)}" if k in CFG["euronext"] else "Historique Euronext"
    if pre == "cftc":
        return f"Positions des fonds CFTC ({(CFG['cftc']['marches'].get(k) or {}).get('nom', k)})" if k in CFG["cftc"]["marches"] else "Historique CFTC"
    if src.startswith("cot_euronext_"):
        return f"Positions des fonds Euronext ({(CFG['euronext'].get(src[13:]) or {}).get('nom', src[13:])})"
    return {"usda": "Bilans USDA", "meteo": "Météo Open-Meteo", "banque_mondiale": "Banque mondiale (Pink Sheet)",
            "geopolitique": "Indice géopolitique", "actualites": "Actualités", "collecte": "Collecte du matin"}.get(
        src, src.replace("engrais_", "Prix engrais ").replace("physique_", "Prix physique ").replace("_", " "))


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
                msgs.append((f"panne:{src}", f"⚠️ Source en panne : {nom_source(src)} depuis {len(jours)} jours",
                             f"Échec depuis le {e['debut']} : {e['detail'] or 'sans détail'}. Les calculs continuent sans elle."))
                e["alerte"] = True
            etat[src] = e
        elif st is None:  # source non interrogée ce jour-là (collecte hebdomadaire ou mensuelle) : état inchangé
            if p:
                etat[src] = p
        elif p.get("alerte"):
            msgs.append((f"retablie:{src}", f"✅ Source rétablie : {nom_source(src)}", f"De nouveau lue après une panne commencée le {p.get('debut')}."))
    return etat, msgs


def chg(ser, n):
    v = list(ser.values()) if isinstance(ser, dict) else ser
    if len(v) <= n:
        return None
    return (v[-1] / v[-1 - n] - 1) * 100


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
    # faits, sans consigne d'achat
    e = CFG["engrais"]
    notes = []  # le ratio azote/blé est montré en jauge : pas de note qui le répète
    gap = out.get("rattrapage")
    if gap is not None and abs(gap) > e["rattrapage"]:
        notes.append(f"Sur 3 mois, le gaz a {'plus' if gap > 0 else 'moins'} monté que l'urée ({gap:+.0f} pts) : l'urée suit souvent le gaz "
                     f"avec 1 à 3 mois de retard")
    mo = today.month
    out["saison"] = ("basse (avril-juillet) : prix habituellement les plus bas de l'année" if mo in e["saisonAchat"] else
                     "haute (septembre-novembre) : prix habituellement les plus hauts de l'année" if mo in e["saisonChere"] else "intermédiaire")
    if out.get("ttf") and out["ttf"]["dernier"] > e["ttfHaut"]:
        notes.append(f"Gaz au-dessus de {e['ttfHaut']} €/MWh")
    if out.get("ttf") and out["ttf"]["sous_seuil_bas"] >= e["ttfBasSeances"]:
        notes.append(f"Gaz sous {e['ttfBas']} €/MWh depuis {e['ttfBasSeances']} séances")
    formes = sorted([(v["euro_un"], k) for k, v in fr.items() if v.get("euro_un")])
    out.update(notes=notes, forme_moins_chere=(CFG["engraisFrance"][formes[0][1]]["nom"] if formes else None))
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


# --------------------------------------------------------------------------------------------- calcul principal
def seuils_cfg():
    """Seuils de l'exploitant (config.json → seuils) : {culture: {"au_dessus": [..], "en_dessous": [..]}} en €/t."""
    out = {}
    for k, v in as_dict(CFG.get("seuils")).items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        out[k] = {s: sorted({float(x) for x in (v.get(s) or []) if fnum(x) is not None and float(x) > 0}) for s in ("au_dessus", "en_dessous")}
    return out


def main():
    today = date.fromisoformat(os.environ["GS_TODAY"]) if os.environ.get("GS_TODAY") else datetime.now(timezone.utc).date()
    eur = read_csv(PRIV / "euronext.csv")
    yahoo = {k: v for k, v in as_dict(load_json(PRIV / "yahoo.json", {})).items() if isinstance(v, dict) and isinstance(v.get("serie"), dict)}
    cftc = {k: v for k, v in as_dict(load_json(PRIV / "cftc.json", {})).items() if isinstance(v, dict) and isinstance(v.get("serie"), list)}
    cot_eu = {k: v for k, v in as_dict(load_json(PRIV / "cot_euronext.json", {})).items() if isinstance(v, dict) and isinstance(v.get("serie"), list)}
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
        inter[tk] = {"nom": y.get("nom", tk), "technique": a, "lecture": ind.lecture(a)}

    # ------------------------------------------------------------------- contrats Euronext : cours, technique, vues longues
    contrats, series_ble = {}, ([], [])
    for prod, c in CFG["euronext"].items():
        d, v, ref, rac, curve = continuous(eur, prod)
        if not d:
            contrats[prod] = {"nom": c["nom"], "culture": c["culture"], "erreur": "aucune cotation"}
            continue
        a = ind.analyse(d, v)
        rs_, hs_ = a.pop("_rsi", None), a.pop("_histo", None)
        info = {"nom": c["nom"], "culture": c["culture"], "echeance": ref, "series": mini_series(d, rs_, hs_), "technique": a,
                "lecture": ind.lecture(a), "courbe": courbe(prod, curve, ref), "raccords": rac[-3:], "dernier_reel": curve.get(ref),
                "seance": d[-1], "_serie": dict(zip(d, v)), "_curve": curve, "_raccords": rac}
        recent = [r for r in rac if r["ajustement"] is None and r["date"] >= d[max(0, len(d) - 63)]]
        if recent:
            info["alerte_raccord"] = f"Changement d'échéance du {recent[-1]['date']} non ajusté (pas de cotation commune) : indicateurs approximatifs"
        if a.get("insuffisant"):  # historique Euronext encore court : lecture technique du marché américain, converti en €/t
            px = PROXY.get(prod)
            pd_, pv = proxy_eur(yahoo, px)
            fx_ = recale(pd_, pv, d, v)
            pv = [x * fx_ for x in pv]
            if len(pv) >= 30:
                pa = ind.analyse(pd_, pv)
                prs, phs = pa.pop("_rsi", None), pa.pop("_histo", None)
                m20, m50 = ind.sma(pv, 20), ind.sma(pv, 50)
                kk = max(0, len(pv) - 120)
                nom_px = (yahoo.get(px) or {}).get("nom", px)
                info["lecture"] = ind.lecture(pa)
                info["proxy"] = {"ticker": px, "nom": nom_px, "technique": pa, "series": mini_series(pd_, prs, phs),
                                 "graphique": [[pd_[i], round(pv[i], 2), round(m20[i], 2) if m20[i] else None,
                                                round(m50[i], 2) if m50[i] else None] for i in range(kk, len(pv))],
                                 "texte": f"Historique Euronext de {a['seances']} séance(s), 30 nécessaires (environ 6 semaines) : en attendant, "
                                          f"lecture technique de {nom_px} converti en €/t et recalé sur le cours Euronext du jour"}
        mm20, mm50 = ind.sma(v, 20), ind.sma(v, 50)
        k = max(0, len(v) - 120)
        info["graphique"] = [[d[i], round(v[i], 2), round(mm20[i], 2) if mm20[i] else None, round(mm50[i], 2) if mm50[i] else None]
                             for i in range(k, len(v))]
        fd, fv = front_series(eur, prod)
        lv = long_views(fd, fv) if len(fd) >= 260 else None
        if lv and lv["semaines"] >= 104:  # au moins 2 ans de cours officiels Euronext : vues longues et thermomètre sur Euronext
            info["long"] = {**lv, "source": "euronext", "nom": "Euronext (échéance la plus proche)", "euronext_depuis": fd[0]}
        else:
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

    # ------------------------------------------------------------------- contexte : saisons, bilans, météo, fonds, macro
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
            rd.update(nom=c["nom"], culture=c["culture"], source="cftc")
            cot[code] = rd
    for prod, (nom_, cult_) in COT_EURONEXT.items():  # fonds d'investissement sur Euronext : la lecture directe du marché français
        rd = cot_reading((cot_eu.get(prod) or {}).get("serie"), mini=26, today=today)
        if rd:
            rd.update(nom=nom_, culture=cult_, source="euronext")
            cot["EURONEXT_" + prod] = rd
    e20, b20 = chg((yahoo.get("EURUSD=X") or {}).get("serie") or {}, 20), chg((yahoo.get("BZ=F") or {}).get("serie") or {}, 20)
    # psychologie des marchés : humeur peur ↔ euphorie (éclairage ; elle n'a pas annoncé la suite des prix, onglet Méthode)
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
    valid_comite = False
    if comite.get("date") and comite.get("format") == "lecture":  # un ancien avis du comité (signaux, ordres) n'est plus affiché
        try:
            valid_comite = (today - date.fromisoformat(str(comite["date"])[:10])).days <= CFG["comite"]["joursValidite"]
        except ValueError:
            pass

    # ------------------------------------------------------------------- lecture du marché par culture
    org = orges(today, series_ble[1])
    seuils = seuils_cfg()
    cultures = {}
    for cult, nom in CULTURES.items():
        prod = CONTRAT[cult]
        ci = contrats.get(prod) or {}
        sur_ble = cult in ("escourgeon", "orge_printemps")
        ser = list((ci.get("_serie") or {}).values())
        o = org.get(cult) or {}
        e = {"nom": nom, "contrat": prod, "proxy": sur_ble, "echeance": ci.get("echeance"), "seance": ci.get("seance")}
        if sur_ble:  # pas de marché à terme : prix physique Creil, technique et repères du blé Euronext
            g = [r for r in o.get("graphique") or [] if r[1] is not None]
            e.update(cours=o.get("prix"), physique=True, date=o.get("date"),
                     var1j=round(g[-1][1] - g[-2][1], 2) if len(g) >= 2 else None, var1m=o.get("var1m"))
        else:
            e.update(cours=ci.get("dernier_reel"), physique=False, date=ci.get("seance"),
                     var1j=round(ser[-1] - ser[-2], 2) if len(ser) >= 2 else None, var1s=(ci.get("technique") or {}).get("var1s"))
        lec = dict(ci.get("lecture") or {}) or None
        if lec and sur_ble:  # niveaux du blé ramenés au niveau de l'orge (écart physique − blé du jour)
            gap = o.get("ecart_ble")
            lec["sur_ble"] = True
            if gap is not None:
                lec["resistances"] = [round(x + gap, 2) for x in lec.get("resistances") or []]
                lec["supports"] = [round(x + gap, 2) for x in lec.get("supports") or []]
            else:
                lec["resistances"], lec["supports"] = [], []
        e["technique"] = lec
        if pression.get(ACTU_CLE[cult]):
            e["actualite"] = pression[ACTU_CLE[cult]]
        th = ci.get("thermo") or {}
        rp = {"percentile5": th.get("percentile"), "p20": th.get("p20"), "p80": th.get("p80"), "sur_ble": sur_ble}
        deb = 10 if cult == "mais" else 7
        y0 = today.year if today.month >= deb else today.year - 1
        camp = {d_: v_ for d_, v_ in (ci.get("_serie") or {}).items() if d_ >= f"{y0}-{deb:02d}-01"}
        if len(camp) >= 10 and ci.get("dernier_reel"):
            dh = max(camp, key=camp.get)
            rp.update(plus_haut=round(camp[dh], 2), plus_haut_le=dh, ecart_plus_haut=round(ci["dernier_reel"] - camp[dh], 2),
                      campagne_depuis=f"{y0}-{deb:02d}-01")
        e["reperes"] = rp
        if o:
            e["physique_detail"] = {k: o.get(k) for k in ("prix", "date", "place", "fourragere", "prime", "ecart_ble", "rouen_rendu")}
        sl = seuils.get(cult) or {}
        if e.get("cours") and (sl.get("au_dessus") or sl.get("en_dessous")):
            e["seuils"] = ([{"sens": ">", "niveau": x, "atteint": e["cours"] >= x} for x in sl.get("au_dessus") or []]
                           + [{"sens": "<", "niveau": x, "atteint": e["cours"] <= x} for x in sl.get("en_dessous") or []])
        cc = (comite.get("cultures") or {}).get(cult) if valid_comite else None
        if cc:
            e["comite"] = cc
        cultures[cult] = e
    for cult, o in org.items():  # graphiques des orges : blé décalé de l'écart du jour, points physiques par-dessus
        gap, eb = o.get("ecart_ble"), contrats.get("EBM") or {}
        if gap is not None and eb.get("graphique"):
            sh = lambda r: [r[0]] + [round(x + gap, 2) if x is not None else None for x in r[1:4]]  # noqa: E731
            phys = {p_[0]: p_[1] for p_ in o.get("graphique") or []}
            o["estime"] = {"ecart": gap, "graphique": [sh(r) + [phys.get(r[0])] for r in eb["graphique"]],
                           "long": None, "long_depuis_ble": bool(eb.get("long")), "technique": decale(eb.get("technique"), gap),
                           "series": eb.get("series"), "lecture": (cultures.get(cult) or {}).get("technique")}
    engrais = module_engrais(today, series_ble[0], series_ble[1], yahoo)
    if pression.get("engrais"):
        engrais["actualite"] = pression["engrais"]
    sl = seuils.get("uree") or {}
    up = (engrais.get("france") or {}).get("uree", {}).get("prix")
    if up and (sl.get("au_dessus") or sl.get("en_dessous")):
        engrais["seuils"] = ([{"sens": ">", "niveau": x, "atteint": up >= x} for x in sl.get("au_dessus") or []]
                             + [{"sens": "<", "niveau": x, "atteint": up <= x} for x in sl.get("en_dessous") or []])
    if valid_comite and (comite.get("cultures") or {}).get("engrais"):
        engrais["comite"] = comite["cultures"]["engrais"]

    # ------------------------------------------------------------------- alertes (comparaison avec la veille), en faits
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

    def franchi(avant, apres, sl):
        """Seuils de l'exploitant franchis entre deux cours : [(sens, niveau)]."""
        return ([(">", x) for x in sl.get("au_dessus") or [] if avant < x <= apres]
                + [("<", x) for x in sl.get("en_dessous") or [] if avant > x >= apres])

    for prod, ci in contrats.items():
        a = ci.get("technique") or {}
        p = prev.get(prod, {})
        marques[prod] = {"bas3m_le": p.get("bas3m_le"), "haut3m_le": p.get("haut3m_le")}
        if a.get("insuffisant") or "dernier" not in a or p.get("seance") == ci["seance"]:
            continue  # pas de nouvelle séance : rien à comparer
        nom, last = ci["nom"], a["dernier"]
        # cours de la veille pris dans la série ajustée : un changement d'échéance ne passe pas pour un mouvement de prix
        pl = (ci.get("_serie") or {}).get(p.get("seance"), p.get("dernier"))
        if pl is None:
            continue
        if last < a["bas3m_hier"] and not recent(p.get("bas3m_le")):
            add(prod + ":bas3m", f"{nom} : plus bas de 3 mois ({fr_n(last)} €/t)", f"Sous le plus bas précédent de {fr_n(a['bas3m_hier'])} €/t")
            marques[prod]["bas3m_le"] = today.isoformat()
        elif last > a["haut3m_hier"] and not recent(p.get("haut3m_le")):
            add(prod + ":haut3m", f"{nom} : plus haut de 3 mois ({fr_n(last)} €/t)", f"Au-dessus du plus haut précédent de {fr_n(a['haut3m_hier'])} €/t")
            marques[prod]["haut3m_le"] = today.isoformat()
        rs, rp_ = a.get("rsi"), p.get("rsi")
        if rs is not None and rp_ is not None:
            if rs < 30 <= rp_:
                add(prod + ":rsi30", f"{nom} : RSI sous 30 ({rs:.0f})", "Survente : baisse rapide et forte à court terme")
            if rs > 70 >= rp_:
                add(prod + ":rsi70", f"{nom} : RSI au-dessus de 70 ({rs:.0f})", "Surachat : hausse rapide et forte à court terme")
        h, hp = a.get("histo"), p.get("histo")
        if h is not None and hp is not None and (h > 0) != (hp > 0):
            add(prod + ":macd", f"{nom} : croisement {'haussier' if h > 0 else 'baissier'} du MACD", f"Histogramme {hp:+.2f} → {h:+.2f}")
        s0, s1 = p.get("sens"), (ci.get("lecture") or {}).get("sens")
        if s0 and s1 and s0 != s1:
            add(prod + ":sens", f"{nom} : lecture technique {s0} → {s1}", (ci.get("lecture") or {}).get("texte") or "")
    cours_prec = as_dict(etat.get("cours"))
    for cult, e in cultures.items():  # seuils de l'exploitant (cours du jour comparé au dernier cours connu)
        avant, du = cours_prec.get(cult), as_dict(etat.get("cours_du")).get(cult)
        if not e.get("physique"):  # série ajustée : un changement d'échéance n'est pas un franchissement
            avant = ((contrats.get(e["contrat"]) or {}).get("_serie") or {}).get(du, avant)
        if e.get("cours") and avant is not None and e.get("date") != du:
            for sens_, x in franchi(avant, e["cours"], seuils.get(cult) or {}):
                add(f"seuil:{cult}:{sens_}{x:g}", f"{e['nom']} : votre seuil de {fr_n(x)} €/t est franchi ({fr_n(e['cours'])} €/t)",
                    f"Seuil {'haut' if sens_ == '>' else 'bas'} fixé dans la configuration", True)
    if up and cours_prec.get("uree") is not None and up != cours_prec["uree"]:
        for sens_, x in franchi(cours_prec["uree"], up, seuils.get("uree") or {}):
            add(f"seuil:uree:{sens_}{x:g}", f"Urée : votre seuil de {fr_n(x)} €/t est franchi ({fr_n(up)} €/t)",
                f"Seuil {'haut' if sens_ == '>' else 'bas'} fixé dans la configuration", True)
    pe = etat.get("engrais", {})
    meme_base = pe.get("base", engrais.get("base")) == engrais.get("base")  # ratio estimé ↔ mondial : pas un vrai mouvement
    t = engrais.get("ttf") or {}
    if t.get("dernier") is not None and pe.get("ttf") is not None and pe.get("ttf_au") != t.get("au"):
        if t["dernier"] > CFG["engrais"]["ttfHaut"] >= pe["ttf"]:
            add("ttf:haut", f"Gaz TTF au-dessus de {CFG['engrais']['ttfHaut']} €/MWh ({t['dernier']:.1f})",
                "Le prix de l'azote suit souvent celui du gaz avec environ 1 mois de retard")
        if t["sous_seuil_bas"] >= CFG["engrais"]["ttfBasSeances"] > pe.get("sous_seuil_bas", 0):
            add("ttf:bas", f"Gaz TTF sous {CFG['engrais']['ttfBas']} €/MWh depuis {CFG['engrais']['ttfBasSeances']} séances",
                "Le prix de l'azote suit souvent celui du gaz avec environ 1 mois de retard")
    for lvl in (CFG["engrais"]["ratioBas"], CFG["engrais"]["ratioMoyen"], CFG["engrais"]["ratioHaut"]):
        a0, a1 = pe.get("percentile"), engrais.get("percentile_retenu")
        if a0 is not None and a1 is not None and (a0 <= lvl) != (a1 <= lvl) and meme_base:
            add(f"ratio:{lvl}", f"Ratio azote/blé : passage du {lvl}e percentile ({a0} → {a1})",
                f"Azote {'moins' if a1 < a0 else 'plus'} cher par rapport au blé")
    g0, g1 = pe.get("rattrapage"), engrais.get("rattrapage")
    rl = CFG["engrais"]["rattrapage"]
    if g0 is not None and g1 is not None and ((g0 <= rl) != (g1 <= rl) or (g0 >= -rl) != (g1 >= -rl)):
        add("rattrapage", f"Écart gaz − azote sur 3 mois : {g0:+.0f} → {g1:+.0f} pts", f"Seuil de ±{rl} pts franchi")
    sources = as_dict(collecte.get("sources"))
    if str(collecte.get("date", ""))[:10] != today.isoformat():  # collecte du jour absente ou coupée : rien n'est daté d'aujourd'hui
        sources = {"collecte": {"ok": False, "detail": f"pas de collecte du jour (dernière : {str(collecte.get('date', '—'))[:16]})"}}
    pannes, msgs = suivi_pannes(sources, as_dict(etat.get("pannes")), today)
    for key, titre, detail in msgs:
        add(key, titre, detail)

    hist = (load_json(OUT / "grain-signal.json", {}).get("historique_declencheurs") or [])
    known = {x["id"] for x in hist}
    hist = ([x for x in trig if x["id"] not in known] + hist)[:60]
    dash = {
        "format": "grain-signal-2",
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
        "macro": {"eurusd_var20": round(e20, 2) if e20 is not None else None, "brent_var20": round(b20, 2) if b20 is not None else None},
        "engrais": engrais,
        "physique": load_json(OUT / "physique.json", {}),
        # alertes du jour : celles de ce calcul et celles d'un calcul précédent du même jour (au 2e passage, etat.json est déjà à
        # jour et trig est vide, alors que l'email est parti)
        "declencheurs": [x for x in hist if x["id"].startswith(today.isoformat() + ":")
                         and not (":panne:" in x["id"] and x["id"].replace(":panne:", ":retablie:") in {y["id"] for y in hist})],
        "historique_declencheurs": hist,
        "collecte": collecte,
        "comite": {**{k: comite.get(k) for k in ("date", "mode", "resume", "calendrier", "modele", "cout_usd", "erreur")}, "valide": valid_comite},
        "config": {"engrais": CFG["engrais"], "comite_modele": CFG["comite"]["modele"], "seuils": seuils,
                   "stockage": {k: v for k, v in CFG["stockage"].items() if not k.startswith("_")}},
    }
    save_json(OUT / "grain-signal.json", dash)
    new_state = {
        "date": today.isoformat(),
        "contrats": {k: {"seance": v.get("seance"), "dernier": (v.get("technique") or {}).get("dernier"), "rsi": (v.get("technique") or {}).get("rsi"),
                         "histo": (v.get("technique") or {}).get("histo"), "sens": (v.get("lecture") or {}).get("sens"), **marques.get(k, {})}
                     for k, v in contrats.items() if v.get("technique")},
        "cours": {**{k: v.get("cours") for k, v in cultures.items() if v.get("cours") is not None}, **({"uree": up} if up else {})},
        "cours_du": {k: v.get("date") for k, v in cultures.items() if v.get("cours") is not None},
        "engrais": {"percentile": engrais.get("percentile_retenu"), "base": engrais.get("base"), "rattrapage": engrais.get("rattrapage"),
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
        tq, ac = e.get("technique") or {}, e.get("actualite") or {}
        print(f"{e['nom']:<30} {fr_n(e['cours']) if e.get('cours') else '—':>8} €/t  technique {tq.get('sens') or '—':<10} actualité {ac.get('sens') or '—'}")
    print(f"Engrais : {' ; '.join(engrais.get('notes', []))}")
    print(f"Alertes du jour : {len(trig)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
