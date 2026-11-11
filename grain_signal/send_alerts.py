"""
Bulletin des grains — emails (Gmail SMTP). Compte d'envoi : GMAIL_USER, GMAIL_APP_PASSWORD (ceux d'Euro Signal).
Destinataires : GRAIN_ALERT_TO (propre au Bulletin des grains), sinon ALERT_TO (Euro Signal), sinon GMAIL_USER.
Sans secrets : mode simulation (rien n'est envoyé, le contenu est affiché dans le journal).

Un seul email par calcul, à partir de data/grain/prive/a-envoyer.json : la lecture hebdomadaire du marché (le lundi), sinon le
rapport du matin (une fois par jour), sinon les alertes d'un calcul relancé. Chacun montre le marché du matin (cours, technique,
actualité) et les alertes ; son objet donne le fait marquant du jour. Jamais de conseil de vente ou d'achat.
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

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def aujourdhui():
    """Date du jour à Paris (GS_TODAY pour les tests)."""
    from datetime import date
    from zoneinfo import ZoneInfo

    if os.environ.get("GS_TODAY"):
        return date.fromisoformat(os.environ["GS_TODAY"])
    return datetime.now(ZoneInfo("Europe/Paris")).date()


def rapport_attendu(out=None):
    """Identifiant du rapport du matin s'il reste à envoyer aujourd'hui (un par jour, du lundi au samedi, sur le calcul du jour)."""
    out = out or OUT
    j = aujourdhui()
    dash = load(out / "grain-signal.json", {}) or {}
    sent = (load(out / "etat.json", {}) or {}).get("envoyes") or {}
    rid = f"rapport:{j.isoformat()}"
    return rid if j.weekday() < 6 and str(dash.get("date")) == j.isoformat() and rid not in sent else None

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "grain"
CFG = json.loads((Path(__file__).resolve().parent / "config.json").read_text(encoding="utf-8"))
URL = CFG["dashboardUrl"]


def e(t):
    return html.escape(str(t if t is not None else ""), quote=True)


def f(v, d=2):
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def sg(v, d=2):
    return ("+" if v > 0 else "") + f(v, d)


SENS_HTML = {"haussière": ("▲ haussière", "#1f7a3e"), "baissière": ("▼ baissière", "#b0281f"), "neutre": ("● neutre", "#6b6d60"),
             "équilibrée": ("● équilibrée", "#6b6d60")}


def sens_html(s_, azote=False):
    if not s_:
        return "<span style='color:#999'>—</span>"
    t, c = SENS_HTML.get(s_, (s_, "#6b6d60"))
    if azote and s_ in ("haussière", "baissière"):
        t += " (plus cher)" if s_ == "haussière" else " (moins cher)"
    return f"<span style='color:{c};white-space:nowrap'>{e(t)}</span>"


def table_marche(dash):
    """Le marché ce matin, une ligne par culture et une pour l'azote : cours, variation, lecture technique, effet de l'actualité."""
    td = "padding:7px 8px;border-bottom:1px solid #ddd;vertical-align:top"
    rows = []
    for c in (dash.get("cultures") or {}).values():
        tq, ac = c.get("technique") or {}, c.get("actualite") or {}
        var = c.get("var1j")
        cours = (f"<b>{f(c['cours'])}</b>" + (f" <span style='color:{'#1f7a3e' if var > 0 else '#b0281f' if var < 0 else '#666'}'>{sg(var)}</span>" if var else "")
                 + ("<br><span style='color:#666;font-size:12px'>physique Creil</span>" if c.get("physique") else "")) if c.get("cours") else "—"
        rows.append(f"<tr><td style='{td}'><b>{e(c['nom'].replace(' brassicole', '').replace(' tendre', ''))}</b></td>"
                    f"<td style='{td};text-align:right;white-space:nowrap'>{cours}</td>"
                    f"<td style='{td}'>{sens_html(tq.get('sens'))}{' <span style=color:#666;font-size:12px>(blé)</span>' if tq.get('sur_ble') else ''}</td>"
                    f"<td style='{td}'>{sens_html(ac.get('sens'))}</td></tr>")
    eng = dash.get("engrais") or {}
    u = (eng.get("france") or {}).get("uree") or {}
    if u.get("prix"):
        v1 = u.get("var1m")
        rows.append(f"<tr><td style='{td}'><b>Azote</b></td><td style='{td};text-align:right;white-space:nowrap'><b>{f(u['prix'])}</b>"
                    + (f" <span style='color:#666'>{sg(v1, 1)} % en 1 mois</span>" if v1 is not None else "") + "<br><span style='color:#666;font-size:12px'>urée</span></td>"
                    f"<td style='{td}'>{e('ratio azote/blé au ' + str(eng['percentile_retenu']) + 'e percentile') if eng.get('percentile_retenu') is not None else '—'}</td>"
                    f"<td style='{td}'>{sens_html((eng.get('actualite') or {}).get('sens'), azote=True)}</td></tr>")
    return ("<table style='border-collapse:collapse;font-size:14px;width:100%'><tr style='background:#eef2ee'>"
            "<th align=left style='padding:6px 8px'>Culture</th><th align=right style='padding:6px 8px'>Cours €/t</th>"
            "<th align=left style='padding:6px 8px'>Technique</th><th align=left style='padding:6px 8px'>Actualité</th></tr>"
            + "".join(rows) + "</table>")


def fait_marquant(dash, trig):
    """Objet de l'email : l'actualité majeure, sinon un seuil franchi, sinon un plus haut ou plus bas de 3 mois, sinon le plus fort
    mouvement de la séance (jamais une panne de source)."""
    for test in (lambda x: x.get("type") == "actu", lambda x: ":seuil:" in x["id"], lambda x: x["id"].endswith(("bas3m", "haut3m"))):
        x = next((x for x in trig if test(x)), None)
        if x:
            return x["titre"]
    mv = [(abs(c["var1j"] / c["cours"]), c) for c in (dash.get("cultures") or {}).values()
          if c.get("var1j") and c.get("cours") and not c.get("physique")]
    if mv:
        c = max(mv, key=lambda t: t[0])[1]
        return f"{c['nom'].replace(' tendre', '')} {sg(c['var1j'])} €/t à {f(c['cours'])}"
    return "marché calme"


ACTU_NOMS = {"ble": "blé", "orge": "orges", "colza": "colza", "mais": "maïs", "engrais": "azote"}


def bloc_actu(n=3):
    """Synthèse de l'actualité et les nouvelles qui comptent (importance 2 et 3, hors comptes rendus de séance), avec leur effet sur les prix."""
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
                fx.append(f"<span style='color:{'#1f7a3e' if v > 0 else '#b0281f'}'>{e(ACTU_NOMS.get(c, c))} {'↑' * abs(v) if v > 0 else '↓' * abs(v)}</span>")
        lien = a.get("url") if str(a.get("url", "")).startswith("http") else None
        titre = e(a.get("titre_fr") or a.get("titre"))
        if lien:
            titre = f"<a href='{e(lien)}' style='color:#17201c'>{titre}</a>"
        lis.append(f"<li style='margin:6px 0'><b>{titre}</b>"
                   f" <span style='color:#777;font-size:12px'>({e(a.get('source') or '')})</span><br>{e(a.get('impact'))}"
                   + (f"<br><span style='font-size:12px'>{' · '.join(fx)}</span>" if fx else "") + "</li>")
    return ("<h3>📰 L'actualité et son effet sur les prix</h3>"
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
            f"<p style='margin-top:18px'><a href='{e(URL)}' style='color:#0d6a56'>Ouvrir le Bulletin des grains</a></p>"
            "<p style='color:#777;font-size:12px'>Outil d'aide à la décision : il décrit le marché, il ne conseille ni de vendre ni d'acheter. "
            "La décision vous appartient.</p></div>")


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
        if m and (aujourdhui() - datetime.fromisoformat(m.group(0)).date()).days > 3:
            sent[x["id"]] = "périmé"  # alerte de plus de 3 jours jamais envoyée (Gmail absent ou en panne) : plus d'actualité
            continue
        outbox.append(x)
    dash = load(OUT / "grain-signal.json", {})
    comite = load(OUT / "comite.json", {})
    mails = []
    trig = [x for x in outbox if x.get("type") != "comite"]
    rid = rapport_attendu()
    j = aujourdhui()
    jour = f"{JOURS[j.weekday()]} {j.day} {MOIS[j.month - 1]}"
    items = "".join(f"<li style='margin:4px 0'>{'📰 ' if x.get('type') == 'actu' else '⚠️ ' if x.get('grave') else ''}<b>{e(x['titre'])}</b>"
                    f"<br><span style='color:#555'>{e(x.get('detail'))}</span>"
                    + (f" <a href='{e(x['url'])}' style='color:#0d6a56'>Lire</a>" if str(x.get("url", "")).startswith("http") else "")
                    + "</li>" for x in sorted(trig, key=lambda x: (x.get("type") != "actu", not x.get("grave"))))
    alertes_h = f"<h3>⚠️ Alertes</h3><ul style='padding-left:18px'>{items}</ul>" if trig else ""
    coms = [x for x in outbox if x.get("type") == "comite" and comite.get("rapport_html")]
    for x in [x for x in outbox if x.get("type") == "comite" and not comite.get("rapport_html")]:
        sent[x["id"]] = "sans rapport"
    for x in coms[:-1]:  # plusieurs comités en attente (envoi en échec la veille) : seul le dernier rapport part, il remplace les autres
        sent[x["id"]] = "remplacé"
    ids = [x["id"] for x in trig] + ([rid] if rid else [])
    # un seul email par calcul : celui du comité s'il s'est réuni, sinon le rapport du matin (une fois par jour), sinon les alertes
    # d'un calcul relancé dans la journée ; chacun emporte les alertes du calcul
    marche = f"<h3>Le marché ce matin</h3>{table_marche(dash)}"
    tete = fait_marquant(dash, trig)
    if coms:
        x = coms[-1]
        inner = (f"{alertes_h}<p style='background:#eef2ee;padding:10px;border-radius:6px'>{e(comite.get('resume'))}</p>"
                 f"{marche}{bloc_actu()}<hr style='margin:18px 0'>{comite['rapport_html']}")
        mails.append(([x["id"]] + ids, f"🌾 {x['titre']} — {jour} : {tete}"[:180], wrap(x["titre"], inner + PDF_NOTE)))
    elif rid:
        mails.append((ids, f"🌾 Bulletin des grains — {jour} : {tete}"[:180], wrap(f"Le marché du {jour}", f"{alertes_h}{marche}{bloc_actu()}{PDF_NOTE}")))
    elif trig:
        # email d'alertes seules : l'objet nomme l'alerte (une panne seulement s'il n'y a qu'elle)
        tri = sorted(trig, key=lambda x: (x.get("type") != "actu", ":seuil:" not in x["id"], not x.get("grave"), ":panne:" in x["id"] or ":retablie:" in x["id"]))
        tete = fait_marquant(dash, trig) if any(":seuil:" in x["id"] or x.get("type") == "actu" for x in trig) else tri[0]["titre"]
        mails.append((ids, f"🌾 Bulletin des grains — {len(trig)} alerte{'s' if len(trig) > 1 else ''} : {tete}"[:180],
                      wrap("Alertes du jour", f"{alertes_h}{bloc_actu()}{marche}")))
    if os.environ.get("GS_TEST_EMAIL", "").lower() == "true" and not mails:
        from zoneinfo import ZoneInfo

        h_ = datetime.now(ZoneInfo("Europe/Paris"))
        # date et heure dans l'objet : Gmail ne range pas l'email sous un envoi précédent (même objet = même conversation)
        mails.append(([], f"🌾 Bulletin des grains — synthèse du {jour} à {h_.hour} h {h_.minute:02d}",
                      wrap("Synthèse à la demande", f"<h3>Le marché ce matin</h3>{table_marche(dash)}" + bloc_actu() + PDF_NOTE)))
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
                if joint:  # synthèse PDF jointe au rapport du matin, à la lecture hebdomadaire et à l'email de test
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
