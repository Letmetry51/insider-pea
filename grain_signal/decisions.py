"""
Bulletin des grains — lectures ajoutées au calcul du matin (appelées par build.py) : prix du jour sur 5 ans, profil saisonnier,
report de la courbe (ce que paie le stockage), prime locale (physique − Euronext), météo des zones de production, bilans
mondiaux, humeur du marché, risque géopolitique, pression de l'actualité. Des faits et des repères, jamais un conseil.

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
        base.update(code="aucune", texte="Aucune échéance plus lointaine de la même récolte cotée")
        return base
    best = max(opts, key=lambda o: o["gain"])
    mo = f"{MOIS_FR[int(best['echeance'][5:]) - 1]} {best['echeance'][:4]}"
    detail = (f"{'+' if best['ecart'] >= 0 else ''}{fr(best['ecart'])} €/t de report − {fr(best['cout'])} €/t de stockage = "
              f"{'+' if best['gain'] >= 0 else ''}{fr(best['gain'])} €/t")
    code = "paye" if best["gain"] >= cfg["seuilGain"] else "ne_paye_pas" if best["gain"] < 0 else "a_peine"
    quoi = {"paye": "la courbe paie le stockage", "ne_paye_pas": "la courbe ne couvre pas les frais", "a_peine": "la courbe couvre à peine les frais"}[code]
    base.update(code=code, meilleure=best, texte=f"Report jusqu'à {mo} : {detail} ({quoi})")
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
        res["texte"] = f"Prime {ref['place']} {res['code']} ({p}e percentile sur un an)"
    elif all(e.get("constante") for e in out):
        res["texte"] = "Prix physiques cotés au niveau d'Euronext (prime constante) : pas de lecture de la prime"
    else:
        res["texte"] = f"Historique de la prime en constitution ({max(e['jours'] for e in out)} jour(s), {mini} nécessaires pour la situer)"
    return res


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
    """État d'une zone d'après la pluie des 60 derniers jours rapportée à la normale, en paliers symétriques : normal de 80 à
    120 %. Note : la sécheresse peut faire monter les prix ; un excès d'eau gêne semis et récoltes, mais bien moins."""
    r = z.get("ratio")
    if r is None:
        return 0.0, "—"
    if r < 0.4:
        return 1.5, "très sec"
    if r < 0.6:
        return 1.0, "sec"
    if r < 0.8:
        return 0.4, "un peu sec"
    if r <= 1.2:
        return -0.3, "normal"
    if r <= 1.5:
        return -0.1, "un peu humide"
    if r <= 2.0:
        return 0.1, "humide"
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


# --------------------------------------------------------------------------------------------- bilans mondiaux (USDA)
def stocks_conso(bilans, precedent=None, hors_chine=True, fenetre=20):
    """Rapport stocks de fin / consommation de la dernière campagne (projection USDA), hors Chine par défaut (la Chine garde la
    moitié des stocks mondiaux de blé et de maïs, peu accessibles au marché), situé en percentile sur les `fenetre` campagnes
    précédentes, et sa révision depuis le bilan précédent."""
    def ratio(e):
        if not e:
            return None
        st = e["stocks"] - (e.get("stocks_chine", 0) if hors_chine else 0)
        co = e["conso"] - (e.get("conso_chine", 0) if hors_chine else 0)
        return st / co * 100 if co > 0 else None
    ans = sorted(y for y in (bilans or {}) if ratio(bilans[y]) is not None)
    if len(ans) < fenetre // 2 + 1:
        return None
    cur = ans[-1]
    r = ratio(bilans[cur])
    hist = [ratio(bilans[y]) for y in ans[-fenetre - 1:-1]]
    out = {"campagne": f"{cur}/{int(cur) % 100 + 1:02d}", "ratio": round(r, 1), "percentile": pctile(hist, r),
           "moyenne": round(sum(hist) / len(hist), 1), "min": round(min(hist), 1), "max": round(max(hist), 1),
           "stocks": round(bilans[cur]["stocks"] / 1000, 1), "conso": round(bilans[cur]["conso"] / 1000, 1),
           "prod": round(bilans[cur]["prod"] / 1000, 1), "hors_chine": hors_chine, "campagnes": len(hist)}
    rp = ratio((precedent or {}).get(cur))
    if rp is not None:
        out["revision"] = round(r - rp, 2)
    p = out["percentile"]
    out["lecture"] = ("stocks très serrés" if p <= 20 else "stocks plutôt serrés" if p <= 40 else "stocks dans la moyenne" if p < 60
                      else "stocks plutôt confortables" if p < 80 else "stocks très confortables")
    return out


# --------------------------------------------------------------------------------------------- psychologie des marchés
PSY_ETATS = ((20, "peur_extreme", "Peur extrême"), (40, "peur", "Peur"), (60, "neutre", "Neutre"), (80, "optimisme", "Optimisme"),
             (101, "euphorie", "Euphorie"))


def psy_etat(v):
    for hi, code, lib in PSY_ETATS:
        if v < hi:
            return code, lib
    return PSY_ETATS[-1][1], PSY_ETATS[-1][2]


def psy_series(vals, win=756):
    """Composantes de l'humeur du marché, chacune en percentile sur 3 ans glissants (jour par jour, fenêtre des `win` séances
    précédentes) : RSI 14, écart à la moyenne 200 séances, élan sur 20 séances. Sert au calcul du matin (dernier jour) et au
    backtest (tous les jours). Fenêtre triée tenue à jour (insertion et retrait par dichotomie)."""
    import bisect
    n = len(vals)
    from indicators import rsi

    r = rsi(vals)
    s, m200 = 0.0, [None] * n
    for i, v in enumerate(vals):
        s += v
        if i >= 200:
            s -= vals[i - 200]
        if i >= 199:
            m200[i] = s / 200
    raw = {"rsi": r, "ecart200": [vals[i] / m200[i] - 1 if m200[i] else None for i in range(n)],
           "elan20": [vals[i] / vals[i - 20] - 1 if i >= 20 and vals[i - 20] else None for i in range(n)]}
    out = {}
    for k, ser in raw.items():
        res, win_l, q = [None] * n, [], []
        for i, v in enumerate(ser):
            if v is not None and len(win_l) >= 200:
                lo = bisect.bisect_left(win_l, v)
                hi = bisect.bisect_right(win_l, v)
                res[i] = (lo + 0.5 * (hi - lo)) / len(win_l) * 100
            if v is not None:
                bisect.insort(win_l, v)
                q.append(v)
                if len(q) > win:
                    old = q.pop(0)
                    del win_l[bisect.bisect_left(win_l, old)]
        out[k] = res
    out["_brut"] = raw
    return out


def psy_indice(comp, fonds=None):
    """Indice 0 (peur) → 100 (euphorie) : moyenne des composantes disponibles (3 au moins), position des fonds comprise."""
    vals = [v for v in comp.values() if v is not None]
    if fonds is not None:
        vals.append(fonds)
    return sum(vals) / len(vals) if len(vals) >= 3 else None


def psychologie(vals, fonds=None, win=756):
    """Humeur du marché du dernier jour. `fonds` : indice 0-100 de la position nette des fonds (le plus acheteur = 100)."""
    if not vals or len(vals) < 460:
        return None
    s = psy_series(vals, win)
    comp = {k: (round(s[k][-1]) if s[k][-1] is not None else None) for k in ("rsi", "ecart200", "elan20")}
    idx = psy_indice(comp, fonds)
    if idx is None:
        return None
    code, lib = psy_etat(idx)
    b = s["_brut"]
    lecture = {"peur_extreme": "Le marché panique : cours très bas par rapport à ses 3 dernières années",
               "peur": "Le marché est pessimiste",
               "neutre": "Humeur ordinaire, sans excès",
               "optimisme": "Le marché est optimiste",
               "euphorie": "Le marché s'emballe : cours très hauts par rapport à ses 3 dernières années"}[code]
    return {"indice": round(idx), "etat": code, "libelle": lib, "lecture": lecture,
            "composantes": {**comp, "fonds": round(fonds) if fonds is not None else None},
            "valeurs": {"rsi": round(b["rsi"][-1], 1) if b["rsi"][-1] is not None else None,
                        "ecart200": round(b["ecart200"][-1] * 100, 1) if b["ecart200"][-1] is not None else None,
                        "elan20": round(b["elan20"][-1] * 100, 1) if b["elan20"][-1] is not None else None}}


# --------------------------------------------------------------------------------------------- risque géopolitique
def geopolitique(jours, pays=None, noms=None, evenements=None, today=None):
    """Indice de risque géopolitique de Caldara et Iacoviello (articles de presse sur guerres, menaces, terrorisme ; 100 =
    moyenne 1985-2019). `jours` : [(date, valeur)] quotidien ; `pays` : {code: [(mois, valeur)]}. Niveau du mois (moyenne
    30 jours) situé en percentile sur 10 ans, tendance sur 30 jours, pays qui comptent pour les grains et les engrais."""
    j = sorted((x[0], x[1]) for x in (jours if isinstance(jours, list) else [])
               if isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[1], (int, float)))
    if len(j) < 400:
        return None
    vals = [v for _, v in j]

    def ma(k, n=30):
        w = vals[max(0, k - n + 1):k + 1]
        return sum(w) / len(w)
    last = len(vals) - 1
    m30 = [ma(k) for k in range(max(0, last - 3650), last + 1)]
    cur = m30[-1]
    out = {"au": j[-1][0], "jour": round(vals[-1]), "semaine": round(ma(last, 7)), "mois": round(cur),
           "percentile": pctile(m30[:-1], cur), "il_y_a_30j": round(m30[-31]) if len(m30) > 31 else None}
    p = out["percentile"]
    out["etat"] = ("très élevé" if p >= 90 else "élevé" if p >= 70 else "normal" if p > 30 else "calme")
    pl = []
    for code, ser in (pays or {}).items():
        s = sorted((m, v) for m, v in ser if v is not None)
        if len(s) < 24:
            continue
        pl.append({"code": code, "nom": (noms or {}).get(code, code), "mois": s[-1][0], "valeur": round(s[-1][1], 2),
                   "percentile": pctile([v for _, v in s[-121:-1]], s[-1][1])})
    out["pays"] = sorted(pl, key=lambda x: -(x["percentile"] or 0))
    if evenements:
        lim = (today - timedelta(days=120)).isoformat() if today else ""
        out["evenements"] = [{"date": d, "texte": t} for d, t in sorted(evenements, reverse=True) if d >= lim][:4]
    return out


# --------------------------------------------------------------------------------------------- actualités
ACTU_CULTURES = ("ble", "orge", "colza", "mais", "engrais")
POIDS_IMPORTANCE = {1: 0.3, 2: 0.6, 3: 1.0}
POIDS_NATURE = {"fait": 1.0, "prevision": 0.7, "opinion": 0.5, "rumeur": 0.4}


def actu_age(a, now):
    """Âge d'un article en jours (date ISO avec heure UTC)."""
    from datetime import datetime
    try:
        d = datetime.fromisoformat(str(a.get("date")).replace("Z", "+00:00"))
        return max(0.0, (now - d).total_seconds() / 86400)
    except (TypeError, ValueError):
        return None


def actu_compte(a):
    """Un article compte dans la pression s'il est pertinent, classé, pas un doublon, et pas un simple compte rendu de séance
    (le cours du jour l'a déjà intégré)."""
    return bool(a.get("pertinent")) and a.get("impacts") and not a.get("doublon_de") and a.get("theme") != "marche"


ACTU_PRUDENCE = 1.0  # poids d'un « titre neutre » ajouté à chaque moyenne : peu de nouvelles → valeur ramenée vers 0


def actu_pression(articles, now, demi_vie=3.0, jours=7):
    """Pression de l'actualité par culture, de −2 (baissière) à +2 (haussière) : MOYENNE des effets des nouvelles des 7 derniers
    jours, pondérée par l'importance, la nature (un fait pèse plus qu'une rumeur) et la fraîcheur (demi-vie de `demi_vie` jours),
    avec un poids de prudence (ACTU_PRUDENCE) qui ramène vers 0 quand il y a peu de nouvelles. Une moyenne ne sature pas avec
    le nombre de titres (une somme collait au plafond les semaines chargées) : +2 demande des faits forts et concordants.
    Repères : un seul fait majeur du jour à effet fort ≈ +1 ; des nouvelles modérées (+1) toutes dans le même sens ≈ +0,8 ;
    autant de nouvelles haussières que baissières ≈ 0. Engrais : + = engrais plus chers."""
    out = {}
    for c in ACTU_CULTURES:
        s, sw, nh, nb, top = 0.0, 0.0, 0, 0, []
        for a in articles:
            if not actu_compte(a):
                continue
            age = actu_age(a, now)
            imp = (a.get("impacts") or {}).get(c)
            if age is None or age > jours or not isinstance(imp, (int, float)) or imp == 0:
                continue
            w = POIDS_IMPORTANCE.get(int(a.get("importance") or 1), 0.3) * POIDS_NATURE.get(a.get("nature"), 0.5) * 0.5 ** (age / demi_vie)
            s += max(-2, min(2, imp)) * w
            sw += w
            nh += imp > 0
            nb += imp < 0
            top.append((abs(imp) * w, a.get("id")))
        v = s / (sw + ACTU_PRUDENCE)
        out[c] = {"valeur": round(v, 2), "hausse": nh, "baisse": nb,
                  "sens": "haussière" if v >= 0.5 else "baissière" if v <= -0.5 else "équilibrée",
                  "principaux": [i for _, i in sorted(top, reverse=True)[:3]]}
    return out


def actu_majeur(a, now, heures=72):
    """Événement majeur : fait avéré, importance 3, impact fort (±2) sur au moins une culture ou les engrais, de moins de 72 h
    (le week-end n'a pas de calcul le dimanche : un fait du samedi matin est encore alerté le lundi)."""
    age = actu_age(a, now)
    return (actu_compte(a) and int(a.get("importance") or 0) >= 3 and a.get("nature") == "fait" and age is not None
            and age <= heures / 24 and any(abs(v) >= 2 for v in (a.get("impacts") or {}).values() if isinstance(v, (int, float))))


def actu_norm(titre):
    """Titre réduit pour repérer les doublons : minuscules, sans accents, sans le nom du site (« … - Terre-net »)."""
    import re
    import unicodedata
    t = str(titre or "")
    for sep in (" - ", " | ", " – "):
        if sep in t and len(t.rsplit(sep, 1)[1]) <= 40:
            t = t.rsplit(sep, 1)[0]
            break
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def actu_doublon(a, b):
    """Deux titres sur le même événement (mots communs ≥ 70 % du plus court)."""
    wa = {w for w in actu_norm(a).split() if len(w) > 3}
    wb = {w for w in actu_norm(b).split() if len(w) > 3}
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.7
