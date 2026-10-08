"""
Euro Signal — envoi des alertes par Gmail (SMTP), exécuté par GitHub Actions après build.mjs.

Activation explicite : l'envoi réel n'a lieu que si les trois secrets GitHub existent
(GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_TO). Sinon, mode simulation : l'alerte est journalisée, rien n'est envoyé.

Garantie : le journal est écrit AVANT chaque envoi (statut « en_cours »), puis mis à jour.
Si la machine s'arrête entre l'acceptation du message par Gmail et l'enregistrement, l'alerte reste
« en_cours » et n'est jamais renvoyée automatiquement : un doublon est évité au prix d'un statut incertain.
Aucune garantie « exactement une fois » n'est possible avec SMTP.
"""
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
DATA = ROOT / "data"
STATE = DATA / "euro-signal-state.json"
OUTBOX = DATA / "euro-signal-outbox.json"
DASH = DATA / "euro-signal.json"


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    user = os.environ.get("GMAIL_USER", "").strip()
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    # Plusieurs destinataires possibles : adresses séparées par des virgules, points-virgules ou espaces
    to_list = [a for a in re.split(r"[,;\s]+", os.environ.get("ALERT_TO", "")) if "@" in a] or ([user] if user else [])
    to = ", ".join(to_list)
    live = bool(user and pwd and to)
    state = load(STATE, {})
    state.setdefault("alerts", {})
    outbox = load(OUTBOX, [])

    phase = {"v": ""}

    def send(subject, text, html):
        msg = EmailMessage()
        msg["Subject"], msg["From"] = subject, user
        if len(to_list) <= 1:
            msg["To"] = to
        else:  # plusieurs destinataires : en copie cachée, chacun ne voit pas les adresses des autres
            msg["To"] = user
            msg["Bcc"] = to
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        phase["v"] = "connexion"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=40) as s:
            s.login(user, pwd)
            phase["v"] = "envoi"  # à partir d'ici, Gmail a peut-être accepté le message
            s.send_message(msg)
            phase["v"] = "accepte"

    if os.environ.get("ES_TEST_EMAIL", "").lower() == "true":
        if live:
            try:
                dash = (load(ROOT / "euro_signal" / "config.json", {}) or {}).get("dashboardUrl", "")
                send("[Euro Signal] Email de test", "Email de test envoyé par Euro Signal depuis GitHub Actions le " + now() + ". Aucune alerte dans ce message." + ("\nTableau de bord : " + dash if dash else ""),
                     '<p>Email de test envoyé par Euro Signal le ' + now() + '. Aucune alerte dans ce message.</p>' + ('<p><a href="' + dash + '" style="display:inline-block;background:#0D6A56;color:#fff;text-decoration:none;font-weight:bold;padding:10px 16px;border-radius:6px">Ouvrir le tableau de bord</a></p>' if dash else ''))
                print("Email de test envoyé à", len(to_list), "destinataire(s)")  # jamais les adresses : le journal est public
            except Exception as e:
                print("ÉCHEC de l'email de test :", type(e).__name__, str(e)[:200])
        else:
            print("Email de test impossible : secrets GMAIL_USER / GMAIL_APP_PASSWORD / ALERT_TO manquants")

    print("Mode :", "envoi réel" if live else "simulation (secrets Gmail absents)", "—", len(outbox), "alerte(s)")
    for item in outbox:
        rec = {k: item.get(k) for k in ("id", "isin", "name", "subject", "eventIds", "score", "version")}
        rec.update({"createdAt": now(), "mode": "envoi" if live else "simulation", "recipient": "configuré" if live else None})
        rec["status"] = "en_cours" if live else "simulee"
        state["alerts"][rec["id"]] = rec
        save(STATE, state)  # journal écrit avant l'envoi
        if not live:
            print("  simulée :", rec["subject"])
            continue
        phase["v"] = ""
        try:
            send(item["subject"], item["text"], item["html"])
            rec["status"] = "envoyee"
            print("  envoyée :", rec["subject"])
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as e:
            rec["status"] = "echec"  # refus certain : sera retentée à la prochaine exécution
            rec["error"] = type(e).__name__ + " : vérifiez GMAIL_USER, le mot de passe d'application et ALERT_TO"
            print("  ÉCHEC :", rec["subject"], rec["error"])
        except Exception as e:
            if phase["v"] in ("envoi", "accepte"):
                rec["status"] = "incertain"  # le message a pu partir : pas de renvoi automatique
                print("  INCERTAIN :", rec["subject"], type(e).__name__)
            else:
                rec["status"] = "echec"  # rien n'a été transmis : sera retentée à la prochaine exécution
                print("  ÉCHEC (connexion) :", rec["subject"], type(e).__name__)
            rec["error"] = phase["v"] + " — " + type(e).__name__ + " : " + str(e)[:160]
        rec["doneAt"] = now()
        save(STATE, state)

    dash = load(DASH, None)
    if dash is not None:  # le tableau de bord reflète le journal à jour
        alerts = sorted(state["alerts"].values(), key=lambda a: a.get("createdAt", ""), reverse=True)[:300]
        dash["alerts"] = {a["id"]: a for a in alerts}
        dash["mail"] = {"ready": live}
        save(DASH, dash)
    return 0


if __name__ == "__main__":
    sys.exit(main())
