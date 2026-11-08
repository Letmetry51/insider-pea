"""
Grain Signal — emails (Gmail SMTP). Compte d'envoi : GMAIL_USER, GMAIL_APP_PASSWORD (ceux d'Euro Signal).
Destinataires : GRAIN_ALERT_TO (propre à Grain Signal), sinon ALERT_TO (Euro Signal), sinon GMAIL_USER.
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


def niveaux_txt(ordres, eq, nr):
    if not ordres:
        return "—"
    f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")  # noqa: E731
    t = " · ".join(f(x) for x in ordres if isinstance(x, (int, float))) + " €/t"
    if nr.get("sur_ble"):
        t = "blé à " + t + (f" (≈ {' · '.join(f(x) for x in eq)} €/t d'orge)" if eq else "")
    return t


def jauge(p, acheteur=False):
    """Percentile en pastille colorée et petite barre (lisible dans un email, sans image) : vert = bon moment pour vendre
    (ou pour acheter, côté azote)."""
    if p is None:
        return "—"
    q = 100 - p if acheteur else p
    col = "#b0281f" if q <= 20 else "#9a5b00" if q <= 40 else "#6b6d60" if q < 60 else "#2a62b8" if q < 80 else "#1f7a3e"
    return (f"<span style='background:{col};color:#fff;border-radius:5px;padding:2px 6px;font:600 12px monospace'>{p}e</span>"
            f"<div style='margin-top:4px;width:90px;height:6px;background:#e7e3d6;border-radius:3px;position:relative'>"
            f"<div style='position:absolute;left:{max(0, min(100, p)) * 0.9 - 4:.0f}px;top:-2px;width:8px;height:8px;border-radius:50%;"
            f"background:#fff;border:2px solid #1c1a12'></div></div>")


def table_signaux(dash):
    rows = []
    contrats = dash.get("contrats") or {}
    for c in (dash.get("cultures") or {}).values():
        th = (contrats.get(c.get("contrat")) or {}).get("thermo") or {}
        feu = (c.get("feu") or {}).get("texte", "")
        nr = c.get("niveaux_retenus") or {}  # mêmes niveaux que la page (comité, sinon techniques)
        ordres = nr.get("ordres") or []
        eq = (nr.get("equivalent_orge") or {}).get("ordres") or []
        rows.append(f"<tr><td style='padding:6px 8px;border-bottom:1px solid #ddd'><b>{e(c['nom'])}</b></td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #ddd'>{e(c.get('libelle'))}</td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #ddd'>{jauge(th.get('percentile'))}</td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #ddd'>{e(niveaux_txt(ordres, eq, nr))}</td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #ddd;color:#555'>{e(feu)}</td></tr>")
    eng = dash.get("engrais") or {}
    rows.append(f"<tr><td style='padding:6px 8px'><b>Engrais azotés</b></td><td style='padding:6px 8px'>{e(eng.get('libelle'))}</td>"
                f"<td style='padding:6px 8px'>{jauge(eng.get('percentile_retenu'), acheteur=True)}</td>"
                f"<td style='padding:6px 8px'>{e(eng.get('a_acheter'))}</td><td style='padding:6px 8px;color:#555'>{e(' ; '.join(eng.get('notes', [])))}</td></tr>")
    return ("<table style='border-collapse:collapse;font-size:14px;width:100%'><tr style='background:#eef2ee'><th align=left style='padding:6px 8px'>Culture</th>"
            "<th align=left style='padding:6px 8px'>Signal</th><th align=left style='padding:6px 8px'>Prix 5 ans / ratio azote</th>"
            "<th align=left style='padding:6px 8px'>Ordres</th><th align=left style='padding:6px 8px'>Timing</th></tr>"
            + "".join(rows) + "</table>")


PDF_NOTE = "<!--synthese-pdf-->"  # remplacé à l'envoi par la mention de la pièce jointe, ou retiré s'il n'y a pas de PDF
PDF_TXT = "<p style='color:#555;font-size:13px'>📄 La synthèse du jour est jointe en PDF (à imprimer ou à garder).</p>"


def synthese(dash):
    """PDF fabriqué ce matin par rapport_pdf.py (jamais un ancien) : contenu et nom de fichier, sinon (None, None)."""
    p = OUT / "prive" / "synthese.pdf"
    try:
        if p.exists() and (datetime.now(timezone.utc).timestamp() - p.stat().st_mtime) < 6 * 3600:
            return p.read_bytes(), f"Grain-Signal-synthese-{dash.get('date', 'du-jour')}.pdf"
    except OSError:
        pass
    print("Synthèse PDF absente : emails envoyés sans pièce jointe")
    return None, None


def wrap(title, inner):
    return (f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:760px;color:#17201c'><h2 style='margin:0 0 12px'>{e(title)}</h2>{inner}"
            f"<p style='margin-top:18px'><a href='{e(URL)}' style='color:#0d6a56'>Ouvrir Grain Signal</a></p>"
            "<p style='color:#777;font-size:12px'>Aide à la décision automatique, pas un conseil en investissement. Décision finale : l'exploitant.</p></div>")


def main():
    user = os.environ.get("GMAIL_USER", "").strip()
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    def adresses(var):
        return [a for a in re.split(r"[,;\s]+", os.environ.get(var, "")) if "@" in a]

    to_list = adresses("GRAIN_ALERT_TO") or adresses("ALERT_TO") or ([user] if user else [])
    print("Destinataires :", "GRAIN_ALERT_TO" if adresses("GRAIN_ALERT_TO") else "ALERT_TO (Euro Signal)" if adresses("ALERT_TO")
          else "GMAIL_USER", f"({len(to_list)} adresse{'s' if len(to_list) > 1 else ''})")
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
            mails.append(([x["id"]], subj, wrap(x["titre"], inner + PDF_NOTE)))
        elif x.get("type") == "comite":
            sent[x["id"]] = "sans rapport"
    if os.environ.get("GS_TEST_EMAIL", "").lower() == "true":
        mails.append(([], "🌾 Grain Signal — email de test", wrap("Email de test", table_signaux(dash) + PDF_NOTE)))
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
    pdf, pdf_nom = synthese(dash)
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=60) as s:
            s.login(user, pwd)
            for ids, subj, body in mails:
                joint = PDF_NOTE in body and pdf
                body = body.replace(PDF_NOTE, PDF_TXT if joint else "")
                msg = EmailMessage()
                msg["Subject"] = re.sub(r"[\x00-\x1f\x7f-\x9f  ]+", " ", subj).strip()
                msg["From"], msg["To"] = user, ", ".join(to_list)
                text = re.sub(r"<[^>]+>", " ", body)
                msg.set_content(re.sub(r"\s+\n", "\n", html.unescape(text))[:20000])
                msg.add_alternative(body, subtype="html")
                if joint:  # synthèse PDF jointe aux emails du comité et à l'email de test
                    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=pdf_nom)
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
