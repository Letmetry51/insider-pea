"""
Euro Signal — email de contrôle du soir : envoyé seulement quand un contrôle trouve un problème (étape du calcul en échec,
calcul arrêté avant la fin, fichiers produits, trous dans les cours, baisse anormale d'une rubrique par rapport au calcul
précédent, affichage du tableau de bord sur téléphone).
Rien n'est envoyé quand tout va bien. Un même constat n'est envoyé qu'une fois par jour.

Secrets : GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_TO (sinon : simulation, le message est seulement affiché).

  python euro_signal/send_health.py
"""
import hashlib
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail_status import record  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIAG = ROOT / "data" / "diagnostics"
SENT = DIAG / "health-sent.json"


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


# étapes du calcul du soir (identifiants de .github/workflows/update-data.yml) : une étape en échec est signalée, même quand le
# calcul continue sans elle (« continue-on-error » : GitHub affiche alors le calcul en succès et n'avertit personne)
STEP_LABELS = {
    "restore": "0. Données de la veille", "deps": "Installation des dépendances", "s1": "1. Déclarations AMF",
    "s2": "2. Déclarations Belgique et Pays-Bas", "s2c": "2c. Positions vendeuses des fonds", "s3": "3. Cours Yahoo Finance",
    "s3b": "3b. Secteurs et fiches sociétés", "s3c": "3c. Cours de secours (Euronext, Nasdaq Nordic)",
    "s4": "4. Résultats, communiqués et révisions", "s4b": "4b. Comptes annuels", "s4c": "4c. Actualité des sociétés",
    "s5a": "5a. Tests du moteur", "s5b": "5b. Calcul Euro Signal", "s5c": "5c. Archive des résultats et rachats",
    "s5t": "5c bis. Double calcul", "s5d": "5d. Contrôle des fichiers", "s5e": "5e. Contrôle de l'affichage", "s6": "6. Alertes email",
    "s6b": "6b. Vos positions (alertes de revente)",
    "s7": "7. Publication du site : la page garde les données de la veille (données du soir sauvegardées 30 jours)",
}


def failed_steps(steps):
    """Étapes en échec d'après le résumé GitHub (toJSON(steps)) : [(identifiant, libellé)], dans l'ordre du calcul."""
    if not isinstance(steps, dict):
        return []
    order = list(STEP_LABELS)
    bad = [k for k, v in steps.items() if isinstance(v, dict) and v.get("outcome") == "failure"]
    return [(k, STEP_LABELS.get(k, k)) for k in sorted(bad, key=lambda k: order.index(k) if k in order else len(order))]


def build(quality, ui, steps=None, today=None):
    """Constats du soir : liste de lignes, vide quand tout va bien."""
    out = [f"✖ Étape « {label} » en échec ce soir" for _, label in failed_steps(steps)]
    if not quality:
        out.append("✖ Contrôle des fichiers non fait (quality.json absent) : le calcul s'est peut-être arrêté avant.")
    elif today and quality.get("date") and quality["date"] != today:
        out.append(f"✖ Calcul du soir arrêté avant le contrôle des fichiers (dernier contrôle du {quality['date']}) : "
                   "la page garde les données précédentes.")
    else:
        out += [i for i in quality.get("issues") or [] if i.startswith(("✖", "⚠"))]
    if not ui:
        out.append("⚠ Contrôle de l'affichage non fait (ui-check.json absent).")
    else:
        if ui.get("note"):
            out.append("⚠ " + ui["note"])
        by = ui.get("summary") or {}
        for k, n in by.items():
            out.append(f"✖ Affichage : {k} ({n})")
        for p in (ui.get("problems") or [])[:8]:
            out.append(f"   · {p.get('where', '')} : {p.get('detail', '')}"[:180])
        if ui.get("jsErrors"):
            out.append(f"✖ Affichage : {len(ui['jsErrors'])} erreur(s) JavaScript, par exemple : {ui['jsErrors'][0].get('message', '')[:120]}")
    return out


def main():
    quality, ui = load(DIAG / "quality.json", None), load(DIAG / "ui-check.json", None)
    try:
        steps = json.loads(os.environ.get("STEPS") or "null")
    except ValueError:
        steps = None
    today = datetime.now(timezone.utc).date().isoformat()
    issues = build(quality, ui, steps, today)
    if not issues:
        print("Contrôle du soir : aucun problème, pas d'email")
        return 0
    key = hashlib.sha1("\n".join(issues).encode("utf-8")).hexdigest()[:12]
    sent = load(SENT, {})
    if sent.get("date") == today and sent.get("key") == key:
        print("Contrôle du soir : mêmes constats déjà envoyés aujourd'hui")
        return 0
    dash = (load(ROOT / "euro_signal" / "config.json", {}) or {}).get("dashboardUrl", "")
    n = sum(1 for i in issues if i.startswith(("✖", "⚠")))
    subject = f"[Euro Signal] Contrôle du soir : {n} point(s) à vérifier"
    cov = (quality or {}).get("cov") or {}
    cov_txt = "\n".join(f"  {k} : {v[0]}" + (f" (avant : {v[1]})" if v[1] is not None and v[1] != v[0] else "") for k, v in cov.items())
    text = ("Le contrôle automatique du calcul du " + today + " a trouvé :\n\n" + "\n".join(issues) +
            ("\n\nCouverture des données :\n" + cov_txt if cov_txt else "") +
            "\n\nDétail : Aide → État des données." + ("\n" + dash + "#aide" if dash else "") +
            "\nCopiez ce message dans la conversation avec Claude pour une correction.")
    html = ("<p>Le contrôle automatique du calcul du " + today + " a trouvé :</p><ul>" + "".join("<li>" + escape(i) + "</li>" for i in issues) + "</ul>" +
            ("<p><b>Couverture des données</b></p><pre style='font-size:13px'>" + escape(cov_txt) + "</pre>" if cov_txt else "") +
            ("<p><a href='" + escape(dash) + "#aide'>Ouvrir Aide → État des données</a></p>" if dash else ""))
    user = os.environ.get("GMAIL_USER", "").strip()
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    to_list = [a for a in re.split(r"[,;\s]+", os.environ.get("ALERT_TO", "")) if "@" in a] or ([user] if user else [])
    if not (user and pwd and to_list):
        print("Simulation (secrets absents) :\n" + subject + "\n" + text)
        return 0
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to_list[0]
    if len(to_list) > 1:
        msg["Bcc"] = ", ".join(to_list[1:])
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=40) as s:
            s.login(user, pwd)
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        print("Email de contrôle non envoyé :", type(e).__name__)
        record("controle", False, "email de contrôle non envoyé (" + type(e).__name__ + ")")  # vu par la garde du matin
        return 0
    record("controle", True, f"{n} point(s) signalé(s)")
    SENT.write_text(json.dumps({"date": today, "key": key}), encoding="utf-8")
    print(f"Email de contrôle envoyé ({n} point(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
