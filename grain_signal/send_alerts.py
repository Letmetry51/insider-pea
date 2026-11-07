"""
Grain Signal — emails (Gmail SMTP), mêmes secrets qu'Euro Signal : GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_TO.
Sans secrets : mode simulation (rien n'est envoyé, le contenu est affiché dans le journal).

Deux sortes d'emails, à partir de data/grain/a-envoyer.json :
- les déclencheurs du jour, regroupés en un seul email ;
- le rapport du comité IA (lundi ou alerte), en entier.
Un envoi réussi est noté dans data/grain/etat.json (« envoyes ») : jamais renvoyé. Un envoi en échec reste dans la file (retenté demain).
GS_TEST_EMAIL=true : envoie aussi un email de test avec l'état du jour.
"""
import html
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "grain"
CFG = json.loads((Path(__file__).resolve().parent / "config.json").read_text(encoding="utf-8"))
URL = CFG["dashboardUrl"]


def load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save(p, obj):
    tmp = Path(p).with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def e(t):
    return html.escape(str(t if t is not None else ""), quote=True)


def table_signaux(dash):
    rows = []
    for c in (dash.get("cultures") or {}).values():
        feu = (c.get("feu") or {}).get("texte", "")
        niv = c.get("niveaux") or {}
        ordres = (c.get("comite") or {}).get("ordres") or niv.get("ordres") or []
        rows.append(f"<tr><td style='padding:6px 8px;border-bottom:1px solid #ddd'><b>{e(c['nom'])}</b></td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #ddd'>{e(c.get('libelle'))}</td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #ddd'>{e(', '.join(f'{x:g}' for x in ordres if isinstance(x, (int, float))))}</td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #ddd;color:#555'>{e(feu)}</td></tr>")
    eng = dash.get("engrais") or {}
    rows.append(f"<tr><td style='padding:6px 8px'><b>Engrais azotés</b></td><td style='padding:6px 8px'>{e(eng.get('libelle'))}</td>"
                f"<td style='padding:6px 8px'>{e(eng.get('a_acheter'))}</td><td style='padding:6px 8px;color:#555'>{e(' ; '.join(eng.get('notes', [])))}</td></tr>")
    return ("<table style='border-collapse:collapse;font-size:14px;width:100%'><tr style='background:#eef2ee'><th align=left style='padding:6px 8px'>Culture</th>"
            "<th align=left style='padding:6px 8px'>Signal</th><th align=left style='padding:6px 8px'>Ordres</th><th align=left style='padding:6px 8px'>Timing</th></tr>"
            + "".join(rows) + "</table>")


def wrap(title, inner):
    return (f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:760px;color:#17201c'><h2 style='margin:0 0 12px'>{e(title)}</h2>{inner}"
            f"<p style='margin-top:18px'><a href='{e(URL)}' style='color:#0d6a56'>Ouvrir Grain Signal</a></p>"
            "<p style='color:#777;font-size:12px'>Aide à la décision automatique, pas un conseil en investissement. Décision finale : l'exploitant.</p></div>")


def main():
    user = os.environ.get("GMAIL_USER", "").strip()
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    to_list = [a for a in re.split(r"[,;\s]+", os.environ.get("ALERT_TO", "")) if "@" in a] or ([user] if user else [])
    live = bool(user and pwd and to_list) and not os.environ.get("GS_DRY")  # GS_DRY : essai sur une branche, aucun envoi
    etat = load(OUT / "etat.json", {})
    sent = etat.setdefault("envoyes", {})
    outbox = []
    for x in load(OUT / "prive" / "a-envoyer.json", []):
        if x["id"] in sent:
            continue
        m = re.search(r"\d{4}-\d{2}-\d{2}", x["id"])
        if m and (datetime.now(timezone.utc).date() - datetime.fromisoformat(m.group(0)).date()).days > 3:
            sent[x["id"]] = "périmé"  # alerte de plus de 3 jours jamais envoyée (Gmail absent ou en panne) : plus d'actualité
            continue
        outbox.append(x)
    dash = load(OUT / "grain-signal.json", {})
    comite = load(OUT / "comite.json", {})
    mails = []
    trig = [x for x in outbox if x.get("type") != "comite"]
    if trig:
        first = sorted(trig, key=lambda x: not x.get("grave"))[0]
        subj = f"🌾 Grain Signal — {len(trig)} déclencheur{'s' if len(trig) > 1 else ''} : {first['titre']}"
        items = "".join(f"<li style='margin:4px 0'>{'⚠️ ' if x.get('grave') else ''}<b>{e(x['titre'])}</b><br><span style='color:#555'>{e(x.get('detail'))}</span></li>"
                        for x in trig)
        mails.append(([x["id"] for x in trig], subj, wrap("Déclencheurs du jour", f"<ul style='padding-left:18px'>{items}</ul><h3>Signaux</h3>{table_signaux(dash)}")))
    for x in outbox:
        if x.get("type") == "comite" and comite.get("rapport_html"):
            sig = ", ".join(f"{v.get('nom', k)} {v.get('libelle', '')}" for k, v in (dash.get("cultures") or {}).items() if k in ("ble", "colza", "mais"))
            subj = f"🌾 {x['titre']} — {sig}"[:180]
            inner = (f"<p style='background:#eef2ee;padding:10px;border-radius:6px'>{e(comite.get('resume'))}</p>{table_signaux(dash)}"
                     f"<hr style='margin:18px 0'>{comite['rapport_html']}")
            mails.append(([x["id"]], subj, wrap(x["titre"], inner)))
        elif x.get("type") == "comite":
            sent[x["id"]] = "sans rapport"
    if os.environ.get("GS_TEST_EMAIL", "").lower() == "true":
        mails.append(([], "🌾 Grain Signal — email de test", wrap("Email de test", table_signaux(dash))))
    if not mails:
        print("Emails : rien à envoyer")
        save(OUT / "etat.json", etat)
        return 0
    if not live:
        for ids, subj, _ in mails:
            print("SIMULATION (secrets Gmail absents ou essai) :", subj)
        save(OUT / "etat.json", etat)
        return 0
    failed = 0
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=60) as s:
            s.login(user, pwd)
            for ids, subj, body in mails:
                msg = EmailMessage()
                msg["Subject"] = re.sub(r"[\x00-\x1f\x7f-\x9f  ]+", " ", subj).strip()
                msg["From"], msg["To"] = user, ", ".join(to_list)
                text = re.sub(r"<[^>]+>", " ", body)
                msg.set_content(re.sub(r"\s+\n", "\n", html.unescape(text))[:20000])
                msg.add_alternative(body, subtype="html")
                try:
                    s.send_message(msg)
                    for i in ids:
                        sent[i] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    print("Envoyé :", subj)
                except Exception as ex:  # noqa: BLE001
                    failed += 1
                    print("Échec d'envoi :", type(ex).__name__)
    except Exception as ex:  # noqa: BLE001
        print("Connexion Gmail impossible :", type(ex).__name__)
        failed += 1
    # journal compact : 400 derniers envois
    etat["envoyes"] = dict(sorted(sent.items(), key=lambda kv: kv[1])[-400:])
    save(OUT / "etat.json", etat)
    save(OUT / "prive" / "a-envoyer.json", [x for x in load(OUT / "prive" / "a-envoyer.json", []) if x["id"] not in etat["envoyes"]])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
