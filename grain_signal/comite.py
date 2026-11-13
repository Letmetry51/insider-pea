"""
Bulletin des grains — lecture hebdomadaire du marché (grain_signal/prompt.md) par l'API Claude avec la recherche web : arguments
haussiers et baissiers par culture, à surveiller, calendrier. Jamais de conseil de vente ou d'achat.

Quand : chaque lundi ; GS_COMITE=force (lancement manuel) la relance. Sans le secret ANTHROPIC_API_KEY : rien n'est appelé.

Entrée : data/grain/grain-signal.json (chiffres du matin). Sorties : data/grain/comite.json (dernière lecture),
data/grain/comites/AAAA-MM-JJ-mode.json (archive), email ajouté à data/grain/prive/a-envoyer.json.

  python grain_signal/comite.py
"""
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from commun import boite, load, save  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "data" / "grain"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
API = "https://api.anthropic.com/v1/messages"
PRIX = {"claude-opus-5-5": (4, 20), "claude-sonnet-5-5": (2, 10), "claude-haiku-5-5": (0.1, 0.5)}  # $ par million de jetons
CLES = ("ble", "escourgeon", "orge_printemps", "colza", "mais", "engrais")


def decide_mode(today, dash, last):
    """'hebdo' (le lundi, une fois ; ou sur demande) ou None."""
    if os.environ.get("GS_COMITE", "").strip().lower() in ("force", "oui", "true", "1"):
        return "hebdo"
    hist = load(OUT / "comites-journal.json", [])
    if today.weekday() == CFG["comite"]["jourHebdo"] and not any(h.get("date") == today.isoformat() for h in hist):
        return "hebdo"
    if not last.get("date"):
        return "hebdo"  # première lecture : sans attendre lundi
    return None


def sans_series(x, maxi=16):
    """Retire les séries (listes de plus de `maxi` éléments : historiques de cours, courbes des graphiques) : le modèle lit les
    chiffres du jour et les repères déjà calculés. Chaque jeton envoyé est relu à chaque recherche web : les séries faisaient
    les deux tiers de la facture (59 000 jetons par envoi)."""
    if isinstance(x, dict):
        return {k: sans_series(v, maxi) for k, v in x.items() if not (isinstance(v, list) and len(v) > maxi)}
    if isinstance(x, list):
        return [sans_series(v, maxi) for v in x]
    return x


def compact(dash):
    """Données du matin pour le comité (sans les séries graphiques ni la configuration)."""
    d = json.loads(json.dumps(dash))
    for c in (d.get("contrats") or {}).values():
        c.pop("graphique", None)
        c.pop("long", None)
    d.pop("historique_declencheurs", None)
    d.pop("config", None)
    d.pop("comite", None)
    col = (d.get("collecte") or {}).get("sources") or {}
    d["collecte"] = {"echecs": {k: v.get("detail") for k, v in col.items() if not v.get("ok")}, "date": (d.get("collecte") or {}).get("date")}
    # lecture de la semaine précédente : envoyée à part (« previous »), pas en double dans chaque culture
    for c in (d.get("cultures") or {}).values():
        if isinstance(c, dict):
            c.pop("comite", None)
    if isinstance(d.get("engrais"), dict):
        d["engrais"].pop("comite", None)
    return sans_series(d)


def call(messages, system, key, recherche=True, max_tokens=None):
    # cache des consignes et des données (cache_control) : relues à chaque recherche web et à chaque reprise, elles coûtent
    # alors 10 % du prix normal au lieu de 100 %
    msgs = [dict(m) for m in messages]
    if msgs and isinstance(msgs[0].get("content"), str):
        msgs[0]["content"] = [{"type": "text", "text": msgs[0]["content"], "cache_control": {"type": "ephemeral"}}]
    body = {"model": CFG["comite"]["modele"], "max_tokens": max_tokens or CFG["comite"]["maxTokens"],
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}], "messages": msgs}
    if recherche:
        body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": CFG["comite"]["recherchesMax"],
                          "user_location": {"type": "approximate", "country": "FR", "timezone": "Europe/Paris"}}]
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    last = None
    for i in range(4):
        try:
            r = requests.post(API, headers=headers, json=body, timeout=900)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code} : {r.text[:300]}"
            if r.status_code in (400, 401, 403, 404):
                break  # erreur de requête ou de clé : inutile d'insister
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__} : {str(e)[:200]}"
        time.sleep(20 * (i + 1))
    raise RuntimeError(last)


def safe_html(md_text):
    """Markdown → HTML sans balise ni lien dangereux venus du modèle ou des pages lues."""
    import markdown

    out = markdown.markdown(html.escape(md_text, quote=False), extensions=["tables", "sane_lists"])

    def fix(m):
        url = html.unescape(m.group(1))
        if not re.match(r"^https?://", url, re.I):
            return "<a>"
        return '<a href="' + html.escape(url, quote=True) + '" rel="noopener noreferrer" target="_blank">'

    return re.sub(r'<a href="([^"]*)"[^>]*>', fix, out)


def bloc_json(text):
    """Dernier bloc ```json du texte ; à défaut, dernier objet JSON qui contient « cultures » (bloc mal balisé)."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    for b in reversed(blocks):
        if '"cultures"' in b:
            return b
    i = text.rfind('{"resume"')
    if i < 0:
        i = text.rfind('"cultures"')
        i = text.rfind("{", 0, i) if i >= 0 else -1
    if i >= 0:
        depth = 0
        for k in range(i, len(text)):
            depth += {"{": 1, "}": -1}.get(text[k], 0)
            if depth == 0:
                return text[i:k + 1]
    return None


def parse_decision(text):
    """Bloc JSON final : arguments par culture (listes de phrases), résumé, calendrier. Rien d'autre n'est gardé."""
    bloc = bloc_json(text)
    if not bloc:
        raise ValueError("bloc JSON final absent")
    j = json.loads(bloc)
    phr = lambda v, n=300: str(v).strip()[:n] if isinstance(v, (str, int, float)) and str(v).strip() else None  # noqa: E731
    cultures = {}
    for k, v in (j.get("cultures") or {}).items():
        if k not in CLES or not isinstance(v, dict):
            continue
        h = [phr(x) for x in v.get("haussier") or [] if phr(x)] if isinstance(v.get("haussier"), list) else []
        b = [phr(x) for x in v.get("baissier") or [] if phr(x)] if isinstance(v.get("baissier"), list) else []
        if h or b or phr(v.get("lecture")):
            cultures[k] = {"haussier": h[:5], "baissier": b[:5], "a_surveiller": phr(v.get("a_surveiller")), "lecture": phr(v.get("lecture"))}
    if not cultures:
        raise ValueError("aucune culture lue")
    cal = [{"date": c["date"], "evenement": phr(c.get("evenement"), 140)} for c in (j.get("calendrier") or [])
           if isinstance(c, dict) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(c.get("date", ""))) and phr(c.get("evenement"))]
    cut = text.rfind("```json")
    report = (text[:cut] if cut >= 0 else text).strip()
    return {"resume": str(j.get("resume", ""))[:600], "cultures": cultures, "calendrier": cal[:20]}, report


def main():
    today = date.fromisoformat(os.environ["GS_TODAY"]) if os.environ.get("GS_TODAY") else datetime.now(timezone.utc).date()
    dash = load(OUT / "grain-signal.json", {})
    last = load(OUT / "comite.json", {})
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    mode = decide_mode(today, dash, last)
    if mode and os.environ.get("GS_DRY") and os.environ.get("GS_COMITE", "").strip().lower() != "force":
        print(f"Comité : essai sur une branche, comité {mode} non réuni (aucun appel payant)")
        return 0
    if not mode:
        print("Comité : pas de réunion aujourd'hui")
        return 0
    if not key:
        print("Lecture hebdomadaire : secret ANTHROPIC_API_KEY absent, non activée")
        if not last.get("date"):
            save(OUT / "comite.json", {"erreur": "Comité IA non activé : ajouter le secret ANTHROPIC_API_KEY dans Settings → Secrets → Actions"})
        return 0
    if not dash:
        print("Comité : données du matin absentes, réunion annulée")
        return 1
    system = (HERE / "prompt.md").read_text(encoding="utf-8")
    consigne = "Lecture hebdomadaire"
    previous = {k: last.get(k) for k in ("date", "resume", "cultures")} if last.get("date") and last.get("format") == "lecture" else None
    donnees = compact(dash)
    actu = load(OUT / "actualites.json", {})
    if str(actu.get("date", "")) == today.isoformat():
        # le premier calcul du matin tourne avant la revue de presse : pression et synthèse de la veille remplacées par celles du jour
        donnees["actualites"] = {"date": actu.get("date"), "synthese": actu.get("synthese"), "pression": actu.get("pression"),
                                 "majeurs": len(actu.get("majeurs") or []), "compte": actu.get("compte")}
        cle = {"ble": "ble", "escourgeon": "orge", "orge_printemps": "orge", "colza": "colza", "mais": "mais"}
        for c, v in (donnees.get("cultures") or {}).items():
            p = (actu.get("pression") or {}).get(cle.get(c))
            if p:
                v["actualite"] = p
            else:
                v.pop("actualite", None)
    arts = [a for a in actu.get("articles") or [] if a.get("pertinent") and not a.get("doublon_de") and (a.get("importance") or 0) >= 2][:40]
    user = (f"Mode : {consigne}\nDate du jour : {today.isoformat()} (heure de Paris le matin ; dernières clôtures : séance précédente).\n\n"
            f"Données chiffrées du matin (Bulletin des grains, JSON) :\n```json\n{json.dumps(donnees, ensure_ascii=False, separators=(',', ':'))}\n```\n\n"
            + (f"Lecture de la semaine précédente, pour mesurer ce qui a changé :\n```json\n{json.dumps(previous, ensure_ascii=False, separators=(',', ':'))}\n```\n\n" if previous else ""))
    if arts:
        user += ("Actualités des 7 derniers jours traduites en impacts (Bulletin des grains ; −2 baisse forte à +2 hausse forte du prix ; "
                 "engrais : + = plus cher) :\n" + "\n".join(
                     f"- {a['date'][:10]} ({a.get('source') or '?'}{' + ' + str(len(a['autres_sources'])) + ' autres sites' if a.get('autres_sources') else ''}) "
                     f"{a.get('titre_fr') or a['titre']} — {a.get('theme')}, {a.get('nature')}, importance {a.get('importance')}, "
                     f"impacts {json.dumps(a.get('impacts'), ensure_ascii=False)} : {a.get('impact')}" for a in arts)
                 + (f"\nSynthèse de l'actualité : {actu['synthese']}" if actu.get("synthese") else "") + "\n\n")
    user += "Rends le rapport au format de sortie du prompt, puis le bloc JSON final."
    messages = [{"role": "user", "content": user}]
    usage = {"input": 0, "output": 0, "searches": 0}
    texts, sources, assistant = [], [], []
    t0 = time.time()
    stop = None
    try:
        for _ in range(8):
            resp = call(messages, system, key)
            stop = resp.get("stop_reason")
            u = resp.get("usage") or {}
            usage["input"] += u.get("input_tokens", 0)
            usage["cache_lu"] = usage.get("cache_lu", 0) + u.get("cache_read_input_tokens", 0)
            usage["cache_ecrit"] = usage.get("cache_ecrit", 0) + u.get("cache_creation_input_tokens", 0)
            usage["output"] += u.get("output_tokens", 0)
            usage["searches"] += (u.get("server_tool_use") or {}).get("web_search_requests", 0)
            for b in resp.get("content") or []:
                if b.get("type") == "text":
                    texts.append(b.get("text", ""))
                    for c in b.get("citations") or []:
                        if c.get("url") and c["url"] not in [s["url"] for s in sources]:
                            sources.append({"url": c["url"], "titre": (c.get("title") or "")[:120]})
            if resp.get("stop_reason") == "pause_turn":  # recherche longue mise en pause : on renvoie tel quel ce qui a été produit
                assistant += resp.get("content") or []
                messages = [messages[0], {"role": "assistant", "content": assistant}]
                continue
            break
        text = "".join(texts)
        print(f"Comité : réponse terminée ({stop}), {usage['output']} jetons rédigés, {usage['searches']} recherches")
        try:
            decision, report = parse_decision(text)
        except ValueError as ex:
            # rapport coupé (limite de longueur) ou rendu sans le bloc final : seconde demande courte, sans recherche web, du
            # seul bloc JSON, à partir du rapport déjà rédigé
            print(f"Comité : {ex} (fin de réponse : {stop}) — demande du seul bloc JSON")
            rep = call([messages[0], {"role": "assistant", "content": text.strip() or "(rapport vide)"},
                        {"role": "user", "content": "Ton rapport ci-dessus a été coupé ou ne se termine pas par le bloc JSON final. Rends "
                                                    "maintenant UNIQUEMENT ce bloc ```json, au format exact de la SORTIE MACHINE, cohérent avec "
                                                    "ton rapport (aucun texte avant ni après)."}],
                       system, key, recherche=False, max_tokens=6000)
            u = rep.get("usage") or {}
            usage["input"] += u.get("input_tokens", 0)
            usage["output"] += u.get("output_tokens", 0)
            extra = "".join(b.get("text", "") for b in rep.get("content") or [] if b.get("type") == "text")
            decision, _ = parse_decision(extra)
            report = text.strip() + ("\n\n*(Rapport coupé : synthèse reprise par une seconde demande.)*" if stop == "max_tokens" else "")
    except Exception as e:  # noqa: BLE001
        print("Comité : échec —", e)
        err = dict(last) if last.get("date") else {}
        err["erreur"] = f"Dernière lecture du marché ({today.isoformat()}) en échec : {str(e)[:300]}"
        save(OUT / "comite.json", err)
        return 1
    pin, pout = PRIX.get(CFG["comite"]["modele"], (4, 20))
    # cache : lecture à 10 % du prix, écriture à 125 % ; recherche web : 10 $ les 1 000
    cost = ((usage["input"] + 0.1 * usage.get("cache_lu", 0) + 1.25 * usage.get("cache_ecrit", 0)) / 1e6 * pin
            + usage["output"] / 1e6 * pout + usage["searches"] * 0.01)
    res = {"format": "lecture", "date": today.isoformat(), "mode": mode, "consigne": consigne, "modele": CFG["comite"]["modele"], **decision,
           "rapport_md": report, "rapport_html": safe_html(report), "sources": sources[:60], "usage": usage,
           "cout_usd": round(cost, 2), "duree_s": round(time.time() - t0)}
    save(OUT / "comite.json", res)
    save(OUT / "comites" / f"{today.isoformat()}-{mode}.json", res)
    arch = sorted((OUT / "comites").glob("*.json"))
    for old in arch[:-40]:
        old.unlink()
    hist = load(OUT / "comites-journal.json", [])
    hist = ([{"date": today.isoformat(), "mode": mode, "cout_usd": res["cout_usd"], "resume": res["resume"]}] + hist)[:120]
    save(OUT / "comites-journal.json", hist)
    outbox = boite(OUT / "prive" / "a-envoyer.json")
    # heure dans l'identifiant : un comité relancé le même jour est un nouveau rapport, envoyé lui aussi (le 9/11, la relance de
    # l'après-midi portait le même identifiant que celui du matin et n'était pas partie)
    outbox.append({"id": f"comite:{today.isoformat()}:{mode}:{datetime.now(timezone.utc):%H%M}", "type": "comite",
                   "titre": "Lecture du marché de la semaine", "detail": res["resume"], "grave": False})
    save(OUT / "prive" / "a-envoyer.json", outbox)
    print(f"Lecture hebdomadaire : {len(decision['cultures'])} cultures, {usage['searches']} recherches, ≈ {res['cout_usd']} $")
    return 0


if __name__ == "__main__":
    sys.exit(main())
