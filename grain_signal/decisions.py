"""
Grain Signal — aides à la décision ajoutées au calcul du matin (appelées par build.py) :
thermomètre du prix sur 5 ans, profil saisonnier, stocker ou vendre (report de la courbe), prime locale (physique − Euronext),
carnet de bord des signaux (noté à 4 et 8 semaines), note météo des zones de production.

Toutes les fonctions sont pures (données en entrée, dictionnaire en sortie) pour être testées sans réseau.
"""
from datetime import date, timedelta

MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def pctile(window, v):
    """Rang du chiffre dans sa fenêtre (0 = le plus bas, 100 = le plus haut), rang moyen pour les égalités : une série
    constante donne 50 (« normal »), pas 100."""
    w = [x for x in window if x is not None]
    if not w or v is None:
        return None
    return round((sum(1 for x in w if x < v) + 0.5 * sum(1 for x in w if x == v)) / len(w) * 100)


MOIS_COURT = {"janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "août": 8, "aout": 8,
              "sept": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12}


def mois_debut(periode):
    """Premier mois d'une période de livraison terre-net (« janv. - mars », « nov. », « mars - juin ») ou None."""
    t = str(periode or "").lower().replace("\xa0", " ").strip()
    for k, m in MOIS_COURT.items():
        if t.startswith(k):
            return m
    return None


def fr(v, d=2):
    return f"{v:.{d}f}".replace(".", ",")


# --------------------------------------------------------------------------------------------- thermomètre 5 ans
def thermometre(cinq_ans, dernier=None):
    """Prix du jour placé dans les 5 dernières années (clôtures hebdomadaires, marché mondial en €/t recalé sur Euronext)."""
    vals = [r[1] for r in (cinq_ans or []) if r[1] is not None]
    if len(vals) < 104:  # au moins 2 ans
        return None
    cur = dernier if dernier is not None else vals[-1]
    srt = sorted(vals)
    q = lambda p: srt[min(len(srt) - 1, int(p / 100 * len(srt)))]  # noqa: E731
    p = pctile(vals, cur)
    return {"percentile": p, "dernier": round(cur, 2), "min": round(srt[0], 2), "max": round(srt[-1], 2),
            "mediane": round(q(50), 2), "p20": round(q(20), 2), "p80": round(q(80), 2), "semaines": len(vals),
            "depuis": cinq_ans[-len(vals)][0] if len(vals) <= len(cinq_ans) else cinq_ans[0][0]}


# --------------------------------------------------------------------------------------------- profil saisonnier
def saisonnier(dates, vals, debut_campagne, mini=10):
    """Écart moyen de chaque mois au prix moyen de sa campagne (médiane sur toutes les campagnes complètes).
    debut_campagne : 7 (blé, colza : juillet → juin) ou 10 (maïs : octobre → septembre). Renvoie 12 valeurs de janvier à décembre."""
    by = {}
    for d, v in zip(dates, vals):
        y, m = int(d[:4]), int(d[5:7])
        camp = y if m >= debut_campagne else y - 1
        by.setdefault(camp, {}).setdefault(m, []).append(v)
    ecarts = {m: [] for m in range(1, 13)}
    n = 0
    for _camp, mois in by.items():
        if len(mois) < 12:
            continue  # campagne incomplète
        moy = {m: sum(x) / len(x) for m, x in mois.items()}
        ref = sum(moy.values()) / 12
        for m in range(1, 13):
            ecarts[m].append((moy[m] / ref - 1) * 100)
        n += 1
    if n < mini:
        return None

    def med(x):
        s = sorted(x)
        k = len(s) // 2
        return s[k] if len(s) % 2 else (s[k - 1] + s[k]) / 2

    prof = [round(med(ecarts[m]), 1) for m in range(1, 13)]
    hauts = [m for m in range(1, 13) if ecarts[m] and sum(1 for e in ecarts[m] if e > 0) / n >= 0.6]  # au-dessus de la moyenne 6 fois sur 10
    ordre = sorted(range(1, 13), key=lambda m: -prof[m - 1])
    return {"mois": prof, "campagnes": n, "plus_chers": ordre[:3], "moins_chers": ordre[-3:][::-1],
            "reguliers": hauts, "debut_campagne": debut_campagne}


# --------------------------------------------------------------------------------------------- stocker ou vendre
def fin_campagne(today, moisson):
    """Premier jour du mois de la prochaine moisson (les échéances qui expirent après livrent la nouvelle récolte)."""
    y = today.year if today.month < moisson else today.year + 1
    return date(y, moisson, 1)


def stockage(curve, ref, expiry_fn, today, moisson, cfg):
    """Gain net d'un report de vente sur chaque échéance de la même récolte : écart de prix − frais de stockage − coût de l'argent.
    curve : {échéance AAAA-MM: prix}, ref : échéance de référence du jour, expiry_fn(échéance) → date d'expiration."""
    if not curve or ref not in curve:
        return None
    fin = fin_campagne(today, moisson)
    p0 = curve[ref]
    e0 = expiry_fn(ref)
    if e0 >= fin:
        return {"code": "nouvelle", "texte": "Les échéances cotées livrent déjà la nouvelle récolte : pas de report possible sur l'ancienne"}
    opts = []
    for m in sorted(curve):
        if m <= ref:
            continue
        em = expiry_fn(m)
        if em >= fin:
            break
        mois = max(1, round((em - e0).days / 30.4))
        cout = mois * cfg["fraisMensuels"] + p0 * cfg["tauxAnnuel"] / 100 / 12 * mois
        ecart = curve[m] - p0
        opts.append({"echeance": m, "prix": round(curve[m], 2), "mois": mois, "ecart": round(ecart, 2), "cout": round(cout, 2),
                     "gain": round(ecart - cout, 2)})
    base = {"reference": ref, "prix": round(p0, 2), "options": opts, "hypotheses": cfg}
    if not opts:
        base.update(code="vendre", texte="Aucune échéance plus lointaine de la même récolte : vendre plutôt que stocker")
        return base
    best = max(opts, key=lambda o: o["gain"])
    mo = f"{MOIS_FR[int(best['echeance'][5:]) - 1]} {best['echeance'][:4]}"
    detail = f"{'+' if best['ecart'] >= 0 else ''}{fr(best['ecart'])} €/t de report − {fr(best['cout'])} €/t de stockage = {'+' if best['gain'] >= 0 else ''}{fr(best['gain'])} €/t"
    if best["gain"] >= cfg["seuilGain"]:
        base.update(code="stocker", meilleure=best, texte=f"Stocker jusqu'à {mo} : le marché paie le stockage ({detail})")
    elif best["gain"] < 0:
        base.update(code="vendre", meilleure=best, texte=f"Vendre plutôt que stocker : le report ne couvre pas les frais (au mieux {mo} : {detail})")
    else:
        base.update(code="neutre", meilleure=best, texte=f"Stockage à peine rémunéré (au mieux {mo} : {detail}) : décider sur le prix, pas sur le report")
    return base


# --------------------------------------------------------------------------------------------- prime locale
def prime_locale(phys_rows, places, front_fn, mini=40):
    """Prix physique − échéance Euronext de référence du même jour, par place. Percentile sur l'historique quand il est assez long.
    phys_rows : lignes de physique_hist (date, page, place, prix) ; places : [[page, place], …] ; front_fn(date) → prix ou None."""
    def norm(t):  # terre-net sépare les mots par des espaces insécables
        return " ".join(str(t or "").replace("\xa0", " ").split()).lower()

    out = []
    for page, place in places:
        hist = []
        rows = (r for r in phys_rows if r.get("page") == page and norm(r.get("place")) == norm(place))
        for r in sorted(rows, key=lambda r: r["date"]):
            try:
                p = float(r["prix"])
            except (TypeError, ValueError):
                continue
            f = front_fn(r["date"], r.get("echeance"))
            if f is not None:
                if hist and hist[-1][0] == r["date"]:
                    hist[-1] = (r["date"], round(p - f, 2))
                else:
                    hist.append((r["date"], round(p - f, 2)))
        if not hist:
            continue
        cur = hist[-1][1]
        e = {"place": place, "date": hist[-1][0], "prime": cur, "jours": len(hist)}
        if len(hist) >= mini and len({h[1] for h in hist[-260:]}) == 1:
            e["constante"] = True  # prix nominal = Euronext (Rouen) : une prime qui ne varie jamais n'a rien à dire
        elif len(hist) >= mini:
            e["percentile"] = pctile([h[1] for h in hist[-260:]], cur)
            e["moyenne"] = round(sum(h[1] for h in hist[-260:]) / len(hist[-260:]), 2)
        out.append(e)
    if not out:
        return None
    res = {"places": out}
    jour = max(e["date"] for e in out)
    memes = [e for e in out if e["date"] == jour]  # places comparées seulement à la même date
    best = max(memes, key=lambda e: e["prime"])
    if len(memes) > 1:
        worst = min(memes, key=lambda e: e["prime"])
        if best["prime"] - worst["prime"] >= 1:
            res["comparaison"] = f"{best['place']} paie {fr(best['prime'] - worst['prime'])} €/t de plus que {worst['place']} par rapport à Euronext"
    ref = next((e for e in out if e.get("percentile") is not None), None)
    if ref:
        p = ref["percentile"]
        res["percentile"] = p
        res["code"] = "forte" if p >= 80 else "faible" if p <= 20 else "normale"
        res["texte"] = {"forte": f"Prime {ref['place']} forte ({p}e percentile) : bon moment pour vendre au physique",
                        "faible": f"Prime {ref['place']} faible ({p}e percentile) : vendre via Euronext ou attendre que la prime revienne",
                        "normale": f"Prime {ref['place']} normale ({p}e percentile)"}[res["code"]]
    elif all(e.get("constante") for e in out):
        res["texte"] = "Prix physiques cotés au niveau d'Euronext (prime constante) : pas de lecture de la prime"
    else:
        res["texte"] = f"Historique de la prime en constitution ({max(e['jours'] for e in out)} jour(s), {mini} nécessaires pour la situer)"
    return res


# --------------------------------------------------------------------------------------------- carnet de bord
SENS = {"VENDRE": -1, "COUVRIR": -1, "ATTENDRE": 1, "TENIR": 0}  # grains : vendre = on attend une baisse ; attendre = une hausse
SENS_ENGRAIS = {"ACHETER_LARGE": 1, "SUIVRE": 0, "FRACTIONNER": 0, "ATTENDRE": -1}  # acheteur : acheter large = on attend une hausse


def carnet_ajoute(carnet, cle, date_, signal, prix, source, texte=""):
    """Nouvelle ligne si l'avis (même source, même date d'avis) n'est pas déjà noté."""
    rid = f"{cle}:{source}:{signal}"
    if any(x["id"] == rid for x in carnet):
        return False
    carnet.append({"id": rid, "cle": cle, "date": date_, "signal": signal, "prix": prix, "texte": texte})
    return True


def prix_a(serie, d):
    """Premier cours connu à la date d ou après (série {date: prix}), et sa date."""
    ks = sorted(k for k in serie if k >= d)
    return (ks[0], serie[ks[0]]) if ks else (None, None)


def carnet_note(entree, serie, today, engrais=False):
    """Résultat à 4 et 8 semaines. Grains : gain d'avoir suivi l'avis (vendre : baisse évitée ; attendre : hausse gagnée).
    Engrais : acheter large = hausse évitée ; attendre = baisse gagnée. Avis neutres (tenir, suivre, fractionner) : mouvement seul."""
    d0, p0 = prix_a(serie, entree["date"])
    if p0 is None:
        return entree
    sens = (SENS_ENGRAIS if engrais else SENS).get(entree["signal"], 0)
    for lab, jours in (("s4", 28), ("s8", 56)):
        cible = (date.fromisoformat(d0) + timedelta(days=jours)).isoformat()
        if cible > today.isoformat():
            entree[lab] = {"le": cible}
            continue
        d1, p1 = prix_a(serie, cible)
        if p1 is None:
            entree[lab] = {"le": cible}
            continue
        var = p1 - p0
        e = {"le": d1, "variation": round(var, 2), "pct": round(var / p0 * 100, 1)}
        if sens:
            g = round(var * sens, 2)
            e["gain"] = g
            tol = 0.005 * p0  # ± 0,5 % : ni bon ni mauvais
            e["verdict"] = "bon" if g > tol else "mauvais" if g < -tol else "neutre"
        else:
            e["verdict"] = "neutre"
        entree[lab] = e
    return entree


def carnet_bilan(carnet):
    """Avis jugés à 8 semaines (bons / mauvais) et gain moyen des avis grains en €/t."""
    notes = [x["s8"]["verdict"] for x in carnet if isinstance(x.get("s8"), dict) and x["s8"].get("verdict") in ("bon", "mauvais")]
    gains = [x["s8"]["gain"] for x in carnet if isinstance(x.get("s8"), dict) and x["s8"].get("gain") is not None and x["cle"] != "engrais"]
    return {"juges": len(notes), "bons": notes.count("bon"), "mauvais": notes.count("mauvais"),
            "gain_moyen": round(sum(gains) / len(gains), 2) if gains else None}


# --------------------------------------------------------------------------------------------- météo
def meteo_zone(obs, prev, today, chaleur=32):
    """obs : {date: (pluie mm, tmax)} observé (archive) ; prev : idem prévision (passé récent et 14 jours).
    Cumul de pluie des 60 derniers jours rapporté à la moyenne des 10 années précédentes sur la même fenêtre ; jours de chaleur prévus."""
    jour = {**obs, **{d: v for d, v in prev.items() if d not in obs}}
    hier = today - timedelta(days=1)
    fen = [(hier - timedelta(days=k)).isoformat() for k in range(60)]
    if sum(1 for d in fen if d in jour and jour[d][0] is not None) < 55:
        return None
    p60 = sum(jour[d][0] or 0 for d in fen if d in jour)
    normales = []
    for y in range(1, 11):
        try:
            fy = [(hier.replace(year=hier.year - y) - timedelta(days=k)).isoformat() for k in range(60)]
        except ValueError:  # 29 février
            fy = [(hier - timedelta(days=365 * y + k)).isoformat() for k in range(60)]
        vals = [obs[d][0] for d in fy if d in obs and obs[d][0] is not None]
        if len(vals) >= 55:
            normales.append(sum(vals) * 60 / len(vals))
    if len(normales) < 5:
        return None
    norm = sum(normales) / len(normales)
    futur = [v for d, v in sorted(prev.items()) if d >= today.isoformat()][:14]
    return {"pluie60": round(p60), "normale60": round(norm), "ratio": round(p60 / norm, 2) if norm > 0 else None,
            "pluie14": round(sum(v[0] or 0 for v in futur)), "chaleur14": sum(1 for v in futur if v[1] is not None and v[1] >= chaleur),
            "tmax14": max((v[1] for v in futur if v[1] is not None), default=None)}


def meteo_etat(z):
    r = z.get("ratio")
    if r is None:
        return 0.0, "—"
    if r < 0.4:
        return 1.5, "très sec"
    if r < 0.6:
        return 1.0, "sec"
    if r < 0.8:
        return 0.4, "un peu sec"
    if r <= 1.5:
        return -0.3, "normal"
    return 0.2, "très humide"


def meteo_score(zones, cfg, today):
    """Note par culture : moyenne pondérée des zones (sécheresse, chaleur), pleine en saison sensible, au quart hors saison.
    Positive = conditions qui peuvent faire monter les prix (attendre) ; négative = conditions favorables aux récoltes (prix sous pression)."""
    out = {}
    for cult, poids in cfg["cultures"].items():
        num = den = 0.0
        det = []
        for zn, w in poids.items():
            z = zones.get(zn)
            zc = cfg["zones"].get(zn) or {}
            if not z:
                continue
            s, lab = meteo_etat(z)
            sens = (zc.get("sensible") or {}).get(cult) or []
            fact = 1.0 if today.month in sens else 0.25
            if z.get("chaleur14", 0) >= 3 and today.month in (zc.get("chaleur") or {}).get(cult, []):
                s += 0.8
                lab += f", {z['chaleur14']} j de chaleur prévus"
            num += w * s * fact
            den += w
            det.append({"zone": zn, "etat": lab, "saison": fact == 1.0})
        if den:
            out[cult] = {"score": round(max(-1.0, min(2.0, num / den)), 2), "zones": det}
    return out
