"""
Grain Signal — actualités traduites en impacts (chaque matin, après le premier calcul et avant le comité).

Entrée : data/grain/prive/actualites_brut.json (titres collectés par collect.py), data/grain/grain-signal.json (cours et signaux du
matin, pour situer l'impact). Chaque nouveau titre est lu par l'API Claude (sans recherche web : seulement le titre, sa source et
sa date) qui dit s'il concerne l'exploitation, son thème (géopolitique, météo, offre, demande, politique, macro, engrais,
logistique, psychologie, marché), sa nature (fait, prévision, rumeur, opinion), son importance (1 à 3), le sens de son effet sur
chaque prix (−2 à +2) et ce que cela change concrètement, en une phrase. Un titre déjà lu n'est jamais relu.

Sorties : data/grain/actualites.json (page, comité, emails, PDF) avec la pression de l'actualité par culture sur 7 jours et les
événements majeurs ; un événement majeur (fait avéré, importance 3, effet fort) part en alerte et demande un comité d'alerte.
Sans le secret ANTHROPIC_API_KEY : titres publiés sans traduction, pression non calculée.

  python grain_signal/actualites.py
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import decisions as dec  # noqa: E402

ROOT = HERE.parent
OUT = ROOT / "data" / "grain"
PRIV = OUT / "prive"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
API = "https://api.anthropic.com/v1/messages"
PRIX = {"claude-opus-5-5": (4, 20), "claude-sonnet-5-5": (2, 10), "claude-haiku-5-5": (0.1, 0.5)}  # $ par million de jetons
THEMES = {"geopolitique", "meteo", "offre", "demande", "politique", "macro", "engrais", "logistique", "psychologie", "marche"}
NATURES = {"fait", "prevision", "rumeur", "opinion"}
HORIZONS = {"jours", "semaines", "mois"}

SYSTEME = """Tu traduis l'actualité des marchés agricoles en impacts concrets pour une exploitation céréalière de la Marne (craie de
Champagne) qui VEND du blé tendre (Euronext), de l'escourgeon et de l'orge de printemps brassicoles (malterie), du colza et du maïs
grain, et qui ACHÈTE de l'azote (solution azotée, ammonitrate, urée). Tu reçois des titres d'articles (titre, site, date) : tu ne
vois que le titre, donc tu restes prudent et tu n'inventes aucun chiffre qui n'y figure pas.

Pour CHAQUE titre de la liste « à classer », rends :
- pertinent : true si le titre peut faire bouger, même un peu, le prix d'une de ces cultures ou de l'azote ; false sinon (publicité,
  conseils techniques sans effet sur les prix, élevage, autre pays sans lien, sujet trop vague).
- titre_fr : le titre en français, court et clair (traduis l'anglais ; garde le sens exact, n'ajoute rien).
- theme : geopolitique (guerre, attaques de ports, sanctions, quotas ou taxes d'export décidés par un État, détroit d'Ormuz,
  mer Noire) · meteo (sécheresse, gel, pluies, état des cultures) · offre (récoltes, bilans, stocks, WASDE) · demande (appels
  d'offres, achats chinois, trituration, malterie) · politique (douanes, accords commerciaux, PAC, droits sur les engrais russes,
  CBAM, Mercosur) · macro (euro, dollar, pétrole, taux) · engrais (prix et offre d'azote, de gaz pour l'azote) · logistique (fret,
  ports, Rhin, canaux) · psychologie (fonds spéculatifs, panique, euphorie, positionnement, rumeurs de marché) · marche (simple
  compte rendu de séance : « le blé recule à Euronext »).
- nature : fait (événement avéré) · prevision (estimation, prévision chiffrée) · rumeur (non confirmé) · opinion (analyse, avis).
- importance : 1 (anecdotique, effet de quelques cents) · 2 (peut peser quelques €/t pendant des jours) · 3 (change le bilan
  mondial ou l'accès à un grand exportateur ou importateur : réservé aux vrais chocs, au plus 1 titre sur 15).
- impacts : sens de l'effet sur le PRIX, de −2 (forte baisse) à +2 (forte hausse), 0 si aucun effet, pour ble, orge (escourgeon
  et orge de printemps brassicoles), colza, mais, engrais (pour engrais : +2 = l'azote va coûter beaucoup plus cher).
  Un compte rendu de séance (theme marche) décrit le passé : impacts du mouvement constaté, importance 1.
- horizon : jours, semaines ou mois (durée probable de l'effet).
- impact : UNE phrase, à l'exploitant, qui dit ce que ça change pour lui (« Moins de blé russe à l'export : soutien pour vos ventes
  de blé, sans urgence à vendre » ; « Urée en hausse : couvrir la prochaine tranche d'azote plutôt que d'attendre »). Pas de
  conseil d'achat ou de vente ferme : le sens et l'ampleur seulement.
- doublon_de : l'id d'un autre titre de la liste qui raconte le même événement (le plus ancien ou le plus complet est gardé), sinon null.
Pour un titre non pertinent, seuls id, pertinent et titre_fr sont utiles.

Tu reçois aussi, pour contexte, les cours du matin et les titres importants déjà classés les jours précédents. Rends enfin une
« synthese » de 3 phrases au plus : ce que l'actualité des derniers jours (titres déjà classés compris) change pour l'exploitation,
culture par culture quand c'est utile, en distinguant ce qui est déjà dans les prix de ce qui ne l'est pas encore.

Réponds UNIQUEMENT par un objet JSON, sans texte autour :
{"articles": [{"id": "...", "pertinent": true, "titre_fr": "...", "theme": "...", "nature": "...", "importance": 1,
  "impacts": {"ble": 0, "orge": 0, "colza": 0, "mais": 0, "engrais": 0}, "horizon": "...", "impact": "...", "doublon_de": null}],
 "synthese": "..."}"""


def load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def contexte(dash):
    """Cours et signaux du matin, en quelques lignes."""
    lignes = []
    for k, c in (dash.get("contrats") or {}).items():
        t = c.get("technique") or {}
        if c.get("dernier_reel") is not None:
            lignes.append(f"{c.get('nom', k)} ({k} {c.get('echeance')}) : {c['dernier_reel']} €/t, RSI {t.get('rsi')}")
    for k, c in (dash.get("cultures") or {}).items():
        lignes.append(f"{c.get('nom', k)} : signal {c.get('libelle')}")
    e = dash.get("engrais") or {}
    if e.get("libelle"):
        lignes.append(f"Engrais : {e.get('libelle')}")
    return "\n".join(lignes)


def impacts(imp):
    """Effets −2 à +2 par culture (entiers), cultures inconnues et effets nuls écartés."""
    out = {}
    for c in dec.ACTU_CULTURES:
        v = imp.get(c)
        if isinstance(v, (int, float)) or re.fullmatch(r"-?\d+(\.\d+)?", str(v or "")):
            n = max(-2, min(2, int(round(float(v)))))
            if n:
                out[c] = n
    return out


def valide(x):
    """Classement rendu par le modèle → champs vérifiés (rien d'inattendu ne passe vers la page)."""
    if not isinstance(x, dict) or not isinstance(x.get("id"), str):
        return None
    out = {"pertinent": bool(x.get("pertinent")), "titre_fr": str(x.get("titre_fr") or "")[:220]}
    if not out["pertinent"]:
        return out
    imp = x.get("impacts") if isinstance(x.get("impacts"), dict) else {}
    out.update(
        theme=x.get("theme") if x.get("theme") in THEMES else "offre",
        nature=x.get("nature") if x.get("nature") in NATURES else "opinion",
        importance=max(1, min(3, int(x.get("importance") or 1))) if str(x.get("importance") or "1").isdigit() else 1,
        impacts=impacts(imp),
        horizon=x.get("horizon") if x.get("horizon") in HORIZONS else "jours",
        impact=str(x.get("impact") or "")[:300],
        doublon_de=x.get("doublon_de") if isinstance(x.get("doublon_de"), str) else None,
    )
    return out


def appel(key, user):
    cfg = CFG["actualites"]
    body = {"model": cfg["modele"], "max_tokens": cfg["maxTokens"], "system": SYSTEME, "messages": [{"role": "user", "content": user}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    last = None
    for i in range(3):
        try:
            r = requests.post(API, headers=headers, json=body, timeout=300)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code} : {r.text[:200]}"
            if r.status_code in (400, 401, 403, 404):
                break
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__} : {str(e)[:150]}"
        time.sleep(15 * (i + 1))
    raise RuntimeError(last)


def lire_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("réponse sans JSON")
    return json.loads(m.group(0))


def main():
    cfg = CFG["actualites"]
    now = datetime.fromisoformat(os.environ["GS_NOW"]) if os.environ.get("GS_NOW") else datetime.now(timezone.utc)
    today = now.date()
    brut = load(PRIV / "actualites_brut.json", {}).get("articles") or []
    cache = load(PRIV / "actualites_classees.json", {})  # classement de chaque titre déjà lu (30 jours)
    prev = load(OUT / "actualites.json", {})
    dash = load(OUT / "grain-signal.json", {})
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    recents = [a for a in brut if (dec.actu_age(a, now) or 99) <= cfg["joursGarde"]]
    a_lire = [a for a in sorted(recents, key=lambda a: a["date"], reverse=True) if a["id"] not in cache][: cfg["maxNouveaux"]]
    usage, erreur, synthese = {"input": 0, "output": 0}, None, None
    if key and a_lire:
        deja = [f"- {cache[a['id']].get('titre_fr') or a['titre']} ({a['date'][:10]}, {cache[a['id']].get('theme')}, "
                f"impacts {cache[a['id']].get('impacts')})" for a in recents
                if a["id"] in cache and cache[a["id"]].get("pertinent") and (cache[a["id"]].get("importance") or 0) >= 2][:30]
        liste = "\n".join(f'{{"id": "{a["id"]}", "site": {json.dumps(a.get("source") or a.get("requete") or "")}, '
                          f'"date": "{a["date"][:16]}", "langue": "{a.get("langue", "")}", "titre": {json.dumps(a["titre"], ensure_ascii=False)}}}'
                          for a in a_lire)
        user = (f"Date : {today.isoformat()}\n\nCours et signaux du matin (Grain Signal) :\n{contexte(dash)}\n\n"
                + ("Titres importants déjà classés (contexte de la synthèse, ne pas les reclasser) :\n" + "\n".join(deja) + "\n\n" if deja else "")
                + f"Titres à classer ({len(a_lire)}) :\n{liste}")
        try:
            resp = appel(key, user)
            u = resp.get("usage") or {}
            usage = {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0)}
            text = "".join(b.get("text", "") for b in resp.get("content") or [] if b.get("type") == "text")
            j = lire_json(text)
            ids = {a["id"] for a in a_lire}
            for x in j.get("articles") or []:
                v = valide(x)
                if v and x["id"] in ids:
                    cache[x["id"]] = {**v, "classe_le": today.isoformat()}
            synthese = str(j.get("synthese") or "")[:900] or None
            print(f"Actualités : {len(a_lire)} titres lus, {sum(1 for a in a_lire if (cache.get(a['id']) or {}).get('pertinent'))} pertinents")
        except Exception as e:  # noqa: BLE001
            erreur = f"Traduction des actualités en échec ({today.isoformat()}) : {str(e)[:200]}"
            print(erreur)
    elif not key:
        print("Actualités : secret ANTHROPIC_API_KEY absent, titres publiés sans traduction")
    lim = (today - timedelta(days=30)).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("classe_le", "9999") >= lim}
    save(PRIV / "actualites_classees.json", cache)

    articles = []
    for a in sorted(recents, key=lambda a: a["date"], reverse=True):
        c = cache.get(a["id"])
        if c and not c.get("pertinent"):
            continue
        x = {k: a.get(k) for k in ("id", "titre", "url", "date", "source", "langue")}
        x["autres_sources"] = (a.get("autres_sources") or [])[:6]
        if c:
            x.update({k: v for k, v in c.items() if k != "classe_le"})
        else:
            x["non_classe"] = True
        articles.append(x)
    classes = [a for a in articles if not a.get("non_classe")]
    pression = dec.actu_pression(classes, now, cfg["demiVieJours"]) if classes else None
    deja_alerte = set(prev.get("alertes_envoyees") or [])
    majeurs = [a for a in classes if dec.actu_majeur(a, now)]
    nouveaux_majeurs = [a for a in majeurs if a["id"] not in deja_alerte]
    pin, pout = PRIX.get(cfg["modele"], (2, 10))
    res = {
        "date": today.isoformat(), "genere": now.isoformat(timespec="minutes"), "modele": cfg["modele"] if key else None,
        # pas de nouvelle synthèse (aucun titre nouveau, ou échec) : celle d'un jour précédent, datée, si elle a moins de 4 jours
        "synthese": synthese or (prev.get("synthese") if str(prev.get("synthese_du") or "") >= (today - timedelta(days=3)).isoformat() else None),
        "synthese_du": today.isoformat() if synthese else (prev.get("synthese_du") if str(prev.get("synthese_du") or "") >= (today - timedelta(days=3)).isoformat() else None),
        "pression": pression, "majeurs": [a["id"] for a in majeurs],
        # titres non traduits montrés seulement sans IA ou si la traduction a échoué (sinon : traduits au prochain calcul)
        "articles": [a for a in articles if not a.get("non_classe") or not key or erreur][:150],
        "compte": {"lus": len(recents), "pertinents": len(classes), "nouveaux": len(a_lire)},
        "cout_usd": round(usage["input"] / 1e6 * pin + usage["output"] / 1e6 * pout, 3),
        "erreur": erreur, "sans_ia": not key,
        "alertes_envoyees": sorted(deja_alerte | {a["id"] for a in nouveaux_majeurs})[-200:],
        # pression de chaque jour (90 jours) : la page montre l'évolution, plus parlante que le niveau
        "historique": ([h for h in prev.get("historique") or [] if isinstance(h, dict) and h.get("date") != today.isoformat()]
                       + ([{"date": today.isoformat(), **{c: v["valeur"] for c, v in pression.items()}}] if pression else []))[-90:],
    }
    save(OUT / "actualites.json", res)

    if nouveaux_majeurs:  # alerte email et comité d'alerte (dans la limite hebdomadaire du comité)
        outbox = load(PRIV / "a-envoyer.json", [])
        known = {o["id"] for o in outbox}
        for a in nouveaux_majeurs:
            iid = f"{today.isoformat()}:actu:{a['id']}"
            if iid in known:
                continue
            fort = ", ".join(f"{dict(ble='blé', orge='orges', colza='colza', mais='maïs', engrais='azote')[c]} {'↑' if v > 0 else '↓'}"
                             for c, v in (a.get("impacts") or {}).items() if v and abs(v) >= 1)
            outbox.append({"id": iid, "type": "actu", "titre": f"Actualité majeure : {a.get('titre_fr') or a['titre']}"[:160],
                           "detail": f"{a.get('impact', '')} ({fort} ; {a.get('source') or ''}, {a['date'][:10]})", "grave": True,
                           "url": a.get("url")})
        save(PRIV / "a-envoyer.json", outbox)
        dem = load(OUT / "demande-comite.json", {})
        motifs = (dem.get("motifs") or []) if dem.get("date") == today.isoformat() else []
        motifs += [f"Actualité majeure : {a.get('titre_fr') or a['titre']}"[:200] for a in nouveaux_majeurs]
        save(OUT / "demande-comite.json", {"date": today.isoformat(), "motifs": motifs})
        print(f"Actualités : {len(nouveaux_majeurs)} événement(s) majeur(s), alerte et comité demandés")
    if pression:
        print("Pression de l'actualité :", ", ".join(f"{k} {v['valeur']:+.2f}" for k, v in pression.items()))
    for a in sorted(classes, key=lambda a: (a.get("importance") or 0, a["date"]), reverse=True)[:10]:  # journal : les titres qui comptent
        print(f"  [{a.get('importance')}] {a['date'][:10]} {a.get('theme')}/{a.get('nature')} {a.get('impacts')} — {a.get('titre_fr') or a['titre']}"
              f" ({a.get('source')}) → {a.get('impact')}")
    if synthese:
        print("Synthèse :", synthese)
    return 0


if __name__ == "__main__":
    sys.exit(main())
