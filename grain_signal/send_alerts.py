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

from commun import load, save  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "grain"
CFG = json.loads((Path(__file__).resolve().parent / "config.json").read_text(encoding="utf-8"))
URL = CFG["dashboardUrl"]


def e(t):
    return html.escape(str(t if t is not None else ""), quote=True)


def table_signaux(dash):
    """Que faire aujourd'hui, une ligne par culture : la décision calculée par build.py, comme la page et le PDF."""
    coul = {"good": "#1f7a3e", "bad": "#b0281f", "warn": "#9a5b00", "info": "#2a62b8", "neutral": "#6b6d60"}
    td = "padding:7px 8px;border-bottom:1px solid #ddd;vertical-align:top"
    f = lambda v, d=2: f"{v:,.{d}f}".replace(",", " ").replace(".", ",")  # noqa: E731
    rows = []
    eng = dash.get("engrais") or {}
    for c in list((dash.get("cultures") or {}).values()) + [{"nom": "Azote", "decision": eng.get("decision") or {}, "azote": True}]:
        x = c.get("decision") or {}
        sous = [f"Comité : {x['consigne']}"] if x.get("consigne") else []
        if x.get("chance") is not None:
            h_ = str(x.get("horizon") or "")
            mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
            sous.append(f"{x['chance']} % de chances d'ici le {int(h_[8:10])} {mois[int(h_[5:7]) - 1]}" if len(h_) >= 10 else f"{x['chance']} % de chances")
        if x.get("declencheur_ble"):
            sous.append(f"quand le blé Euronext atteint {f(x['declencheur_ble'])} €/t")
        if x.get("plafond"):
            sous.append(f"plafond d'achat {f(x['plafond'], 0)} €/t")
        cours = (("urée " if c.get("azote") else "") + f(x["cours"]) + " €/t") if x.get("cours") else "—"
        rows.append(f"<tr><td style='{td}'><b>{e(c['nom'].replace(' brassicole', ''))}</b></td>"
                    f"<td style='{td}'><span style='background:{coul.get(x.get('couleur'), coul['neutral'])};color:#fff;border-radius:5px;"
                    f"padding:2px 7px;font:600 12px monospace'>{e(x.get('libelle', '—'))}</span> <b>{e(x.get('quoi'))}</b>"
                    + (f"<br><span style='color:#666;font-size:12px'>{e(' · '.join(sous))}</span>" if sous else "") + "</td>"
                    f"<td style='{td};text-align:right;white-space:nowrap'>{cours}</td></tr>")
    return ("<table style='border-collapse:collapse;font-size:14px;width:100%'><tr style='background:#eef2ee'>"
            "<th align=left style='padding:6px 8px'>Culture</th><th align=left style='padding:6px 8px'>Que faire</th>"
            "<th align=right style='padding:6px 8px'>Cours</th></tr>" + "".join(rows) + "</table>")

ACTU_NOMS = {"ble": "blé", "orge": "orges", "colza": "colza", "mais": "maïs", "engrais": "azote"}


def bloc_actu(n=3):
    """Synthèse de l'actualité et les nouvelles qui comptent (importance 2 et 3, hors comptes rendus de séance), avec leur effet."""
    ac = load(OUT / "actualites.json", {})
    arts = [a for a in ac.get("articles") or [] if a.get("pertinent") and not a.get("doublon_de") and a.get("theme") != "marche"
            and (a.get("importance") or 0) >= 2]
    arts.sort(key=lambda a: ((a.get("importance") or 0), str(a.get("date"))), reverse=True)  # le plus important, puis le plus récent
    if not arts and not ac.get("synthese"):
        return ""
    lis = []
    for a in arts[:n]:
        fx = []
        for c, v in (a.get("impacts") or {}).items():
            if v:
                fav = v < 0 if c == "engrais" else v > 0
                fx.append(f"<span style='color:{'#1f7a3e' if fav else '#b0281f'}'>{e(ACTU_NOMS.get(c, c))} {'↑' * abs(v) if v > 0 else '↓' * abs(v)}</span>")
        lien = a.get("url") if str(a.get("url", "")).startswith("http") else None
        titre = e(a.get("titre_fr") or a.get("titre"))
        if lien:
            titre = f"<a href='{e(lien)}' style='color:#17201c'>{titre}</a>"
        lis.append(f"<li style='margin:6px 0'><b>{titre}</b>"
                   f" <span style='color:#777;font-size:12px'>({e(a.get('source') or '')})</span><br>{e(a.get('impact'))}"
                   + (f"<br><span style='font-size:12px'>{' · '.join(fx)}</span>" if fx else "") + "</li>")
    return ("<h3>📰 Ce que l'actualité change</h3>"
            + (f"<p style='background:#f4f1e6;padding:10px;border-radius:6px'>{e(ac['synthese'])}</p>" if ac.get("synthese") else "")
            + (f"<ul style='padding-left:18px'>{''.join(lis)}</ul>" if lis else ""))


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
        # actualité majeure d'abord (elle convoque le comité), puis les déclencheurs graves
        first = sorted(trig, key=lambda x: (x.get("type") != "actu", not x.get("grave")))[0]
        mot = "alerte" if any(x.get("type") == "actu" for x in trig) else "déclencheur"
        subj = f"🌾 Grain Signal — {len(trig)} {mot}{'s' if len(trig) > 1 else ''} : {first['titre']}"
        items = "".join(f"<li style='margin:4px 0'>{'📰 ' if x.get('type') == 'actu' else '⚠️ ' if x.get('grave') else ''}<b>{e(x['titre'])}</b>"
                        f"<br><span style='color:#555'>{e(x.get('detail'))}</span>"
                        + (f" <a href='{e(x['url'])}' style='color:#0d6a56'>Lire</a>" if str(x.get("url", "")).startswith("http") else "")
                        + "</li>" for x in trig)
        mails.append(([x["id"] for x in trig], subj, wrap("Alertes du jour", f"<ul style='padding-left:18px'>{items}</ul>{bloc_actu()}<h3>Que faire aujourd'hui</h3>{table_signaux(dash)}")))
    coms = [x for x in outbox if x.get("type") == "comite"]
    for x in coms[:-1]:  # plusieurs comités en attente (envoi en échec la veille) : seul le dernier rapport part, il remplace les autres
        sent[x["id"]] = "remplacé"
    for x in coms[-1:]:
        if comite.get("rapport_html"):
            sig = ", ".join(f"{v.get('nom', k).replace(' tendre', '')} {(v.get('decision') or {}).get('libelle', '')}"
                            for k, v in (dash.get("cultures") or {}).items() if k in ("ble", "colza", "mais"))
            subj = f"🌾 {x['titre']} — {sig}"[:180]
            inner = (f"<p style='background:#eef2ee;padding:10px;border-radius:6px'>{e(comite.get('resume'))}</p>{table_signaux(dash)}{bloc_actu()}"
                     f"<hr style='margin:18px 0'>{comite['rapport_html']}")
            mails.append(([x["id"]], subj, wrap(x["titre"], inner + PDF_NOTE)))
        else:
            sent[x["id"]] = "sans rapport"
    if os.environ.get("GS_TEST_EMAIL", "").lower() == "true":
        mails.append(([], "🌾 Grain Signal — email de test", wrap("Email de test", table_signaux(dash) + bloc_actu() + PDF_NOTE)))
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
