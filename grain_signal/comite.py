"""
Grain Signal — Comité IA : applique le prompt du comité (grain_signal/prompt.md) avec l'API Claude et la recherche web.

Quand : chaque lundi (comité complet), et en mode « Alerte » quand un déclencheur important a sauté (au plus
config.comite.alerteMaxParSemaine fois sur 7 jours). GS_COMITE=force (lancement manuel) force un comité complet.
Sans le secret ANTHROPIC_API_KEY : rien n'est appelé, la page indique que le comité n'est pas activé.

Entrée : data/grain/grain-signal.json (chiffres du matin). Sorties : data/grain/comite.json (dernier comité),
data/grain/comites/AAAA-MM-JJ-mode.json (archive), email ajouté à data/grain/a-envoyer.json.

  python grain_signal/comite.py
"""
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "data" / "grain"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
API = "https://api.anthropic.com/v1/messages"
PRIX = {"claude-opus-5-5": (4, 20), "claude-sonnet-5-5": (2, 10), "claude-haiku-5-5": (0.1, 0.5)}  # $ par million de jetons
SIGNAUX = {"VENDRE", "TENIR", "ATTENDRE", "COUVRIR"}
SIG_ENGRAIS = {"ACHETER_LARGE", "SUIVRE", "FRACTIONNER", "ATTENDRE"}


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


def decide_mode(today, dash, last):
    """'complet', 'alerte' ou None."""
    if os.environ.get("GS_COMITE", "").strip().lower() in ("force", "oui", "true", "1"):
        return "complet"
    hist = load(OUT / "comites-journal.json", [])
    week = [h for h in hist if h.get("date", "") >= (today - timedelta(days=7)).isoformat()]
    if today.weekday() == CFG["comite"]["jourHebdo"] and not any(h.get("mode") == "complet" and h["date"] == today.isoformat() for h in hist):
        return "complet"
    if not last.get("date"):
        return "complet"  # premier comité : sans attendre lundi
    dem = load(OUT / "demande-comite.json", {})
    if dem.get("date") == today.isoformat() and sum(1 for h in week if h.get("mode") == "alerte") < CFG["comite"]["alerteMaxParSemaine"]:
        if not any(h["date"] == today.isoformat() for h in hist):
            return "alerte"
    return None


def compact(dash):
    """Données du matin pour le comité (sans les séries graphiques ni la configuration)."""
    d = json.loads(json.dumps(dash))
    for c in (d.get("contrats") or {}).values():
        c.pop("graphique", None)
    d.pop("historique_declencheurs", None)
    d.pop("config", None)
    d.pop("comite", None)
    col = (d.get("collecte") or {}).get("sources") or {}
    d["collecte"] = {"echecs": {k: v.get("detail") for k, v in col.items() if not v.get("ok")}, "date": (d.get("collecte") or {}).get("date")}
    return d


def call(messages, system, key):
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": CFG["comite"]["recherchesMax"],
              "user_location": {"type": "approximate", "country": "FR", "timezone": "Europe/Paris"}}]
    body = {"model": CFG["comite"]["modele"], "max_tokens": CFG["comite"]["maxTokens"], "system": system, "messages": messages, "tools": tools}
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


def parse_decision(text):
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not blocks:
        raise ValueError("bloc JSON final absent")
    j = json.loads(blocks[-1])
    cultures = {}
    for k, v in (j.get("cultures") or {}).items():
        if isinstance(v, dict) and str(v.get("signal", "")).upper() in SIGNAUX:
            v["signal"] = v["signal"].upper()
            cultures[k] = v
    if not cultures:
        raise ValueError("aucune culture avec un signal valide")
    eng = j.get("engrais") or {}
    if str(eng.get("signal", "")).upper() not in SIG_ENGRAIS:
        eng = {}
    else:
        eng["signal"] = eng["signal"].upper()
    trig = [t for t in (j.get("declencheurs") or []) if isinstance(t, dict) and t.get("contrat") in ("EBM", "ECO", "EMA", "TTF")
            and t.get("sens") in (">", "<") and isinstance(t.get("niveau"), (int, float))]
    cal = [c for c in (j.get("calendrier") or []) if isinstance(c, dict) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(c.get("date", "")))]
    report = text[: text.rfind("```json")].strip()
    return {"resume": str(j.get("resume", ""))[:600], "cultures": cultures, "engrais": eng, "declencheurs": trig[:20], "calendrier": cal[:20]}, report


def main():
    today = date.fromisoformat(os.environ["GS_TODAY"]) if os.environ.get("GS_TODAY") else datetime.now(timezone.utc).date()
    dash = load(OUT / "grain-signal.json", {})
    last = load(OUT / "comite.json", {})
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    mode = decide_mode(today, dash, last)
    if not mode:
        print("Comité : pas de réunion aujourd'hui")
        return 0
    if not key:
        print("Comité : secret ANTHROPIC_API_KEY absent, comité non activé")
        if not last.get("date"):
            save(OUT / "comite.json", {"erreur": "Comité IA non activé : ajouter le secret ANTHROPIC_API_KEY dans Settings → Secrets → Actions"})
        return 0
    if not dash:
        print("Comité : données du matin absentes, réunion annulée")
        return 1
    system = (HERE / "prompt.md").read_text(encoding="utf-8")
    consigne = {"complet": "Comité complet", "alerte": "Alerte : " + " ; ".join(load(OUT / "demande-comite.json", {}).get("motifs", []))}[mode]
    previous = {k: last.get(k) for k in ("date", "mode", "resume", "cultures", "engrais")} if last.get("date") else None
    user = (f"Mode : {consigne}\nDate du jour : {today.isoformat()} (heure de Paris le matin ; dernières clôtures : séance précédente).\n\n"
            f"Données chiffrées du matin (Grain Signal, JSON) :\n```json\n{json.dumps(compact(dash), ensure_ascii=False)}\n```\n\n"
            + (f"Avis du comité précédent, pour mesurer ce qui a changé :\n```json\n{json.dumps(previous, ensure_ascii=False)}\n```\n\n" if previous else "")
            + "Rends le rapport au format de sortie du prompt, puis le bloc JSON final.")
    messages = [{"role": "user", "content": user}]
    usage = {"input": 0, "output": 0, "searches": 0}
    texts, sources, assistant = [], [], []
    t0 = time.time()
    try:
        for _ in range(8):
            resp = call(messages, system, key)
            u = resp.get("usage") or {}
            usage["input"] += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
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
        decision, report = parse_decision(text)
    except Exception as e:  # noqa: BLE001
        print("Comité : échec —", e)
        err = dict(last) if last.get("date") else {}
        err["erreur"] = f"Dernier comité ({today.isoformat()}, {mode}) en échec : {str(e)[:300]}"
        save(OUT / "comite.json", err)
        return 1
    pin, pout = PRIX.get(CFG["comite"]["modele"], (4, 20))
    cost = usage["input"] / 1e6 * pin + usage["output"] / 1e6 * pout + usage["searches"] * 0.01
    res = {"date": today.isoformat(), "mode": mode, "consigne": consigne, "modele": CFG["comite"]["modele"], **decision,
           "rapport_md": report, "rapport_html": safe_html(report), "sources": sources[:60], "usage": usage,
           "cout_usd": round(cost, 2), "duree_s": round(time.time() - t0),
           "chiffres": {k: {"composantes": v.get("composantes")} for k, v in (dash.get("cultures") or {}).items()}}
    save(OUT / "comite.json", res)
    save(OUT / "comites" / f"{today.isoformat()}-{mode}.json", res)
    arch = sorted((OUT / "comites").glob("*.json"))
    for old in arch[:-40]:
        old.unlink()
    hist = load(OUT / "comites-journal.json", [])
    hist = ([{"date": today.isoformat(), "mode": mode, "cout_usd": res["cout_usd"], "resume": res["resume"]}] + hist)[:120]
    save(OUT / "comites-journal.json", hist)
    outbox = load(OUT / "prive" / "a-envoyer.json", [])
    outbox.append({"id": f"comite:{today.isoformat()}:{mode}", "type": "comite", "titre": f"Comité grains et engrais — {consigne}"[:140],
                   "detail": res["resume"], "grave": mode == "alerte"})
    save(OUT / "prive" / "a-envoyer.json", outbox)
    print(f"Comité {mode} : {len(decision['cultures'])} cultures, {usage['searches']} recherches, ≈ {res['cout_usd']} $")
    return 0


if __name__ == "__main__":
    sys.exit(main())
