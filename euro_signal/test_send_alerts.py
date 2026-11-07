"""
Tests hors ligne de l'envoi des alertes (euro_signal/send_alerts.py, relecture du 07/11/2026) : statut de chaque alerte selon la réponse
de Gmail, sans réseau ni vraie adresse (serveur SMTP simulé, fichiers dans un dossier temporaire).

  python euro_signal/test_send_alerts.py
"""
import json
import os
import shutil
import smtplib
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mail_status  # noqa: E402
import send_alerts as SA  # noqa: E402

results = []


class FakeSMTP:
    """smtplib.SMTP_SSL simulé : `mode` dit ce que fait l'envoi."""
    mode = "ok"
    sent = []

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pwd):
        if FakeSMTP.mode == "auth":
            raise smtplib.SMTPAuthenticationError(535, b"refus")

    def send_message(self, msg):
        if FakeSMTP.mode == "data":
            raise smtplib.SMTPDataError(421, b"4.7.0 Try again later")
        if FakeSMTP.mode == "coupure":
            raise smtplib.SMTPServerDisconnected("connexion perdue pendant l'envoi")
        FakeSMTP.sent.append(msg["Subject"])


def run(mode):
    tmp = Path(tempfile.mkdtemp())
    saved = (SA.STATE, SA.OUTBOX, SA.DASH, mail_status.FILE, SA.smtplib.SMTP_SSL, dict(os.environ))
    try:
        SA.STATE, SA.OUTBOX, SA.DASH = tmp / "state.json", tmp / "outbox.json", tmp / "dash.json"
        mail_status.FILE = tmp / "mail.json"
        SA.OUTBOX.write_text(json.dumps([{"id": "a1", "kind": "bondjour", "subject": "[Euro Signal] test", "text": "t", "html": "<p>t</p>"}]),
                             encoding="utf-8")
        os.environ.update({"GMAIL_USER": "expediteur@example.com", "GMAIL_APP_PASSWORD": "x", "ALERT_TO": "destinataire@example.com"})
        os.environ.pop("ES_TEST_EMAIL", None)
        FakeSMTP.mode, FakeSMTP.sent = mode, []
        SA.smtplib.SMTP_SSL = FakeSMTP
        code = SA.main()
        st = json.loads(SA.STATE.read_text(encoding="utf-8"))
        return code, st["alerts"]["a1"]["status"]
    finally:
        SA.STATE, SA.OUTBOX, SA.DASH, mail_status.FILE, SA.smtplib.SMTP_SSL = saved[:5]
        os.environ.clear()
        os.environ.update(saved[5])
        shutil.rmtree(tmp, ignore_errors=True)


def case(name, fn):
    try:
        fn()
        results.append(("OK  ", name, ""))
    except Exception as e:
        results.append(("ÉCHEC", name, f"{e}\n{traceback.format_exc(limit=3)}"))


def _ok():
    code, status = run("ok")
    assert (code, status) == (0, "envoyee") and FakeSMTP.sent == ["[Euro Signal] test"], (code, status)


def _data():
    code, status = run("data")
    assert (code, status) == (3, "echec"), (code, status)  # refus de Gmail : retentée demain, étape signalée


def _cut():
    code, status = run("coupure")
    assert status == "incertain", status  # le message a pu partir : jamais renvoyé automatiquement


def _auth():
    code, status = run("auth")
    assert (code, status) == (3, "echec"), (code, status)


case("Envoi accepté : alerte envoyée", _ok)
case("Gmail refuse le message pendant l'envoi (421 Try again later) : échec, retentée demain", _data)
case("Connexion coupée pendant l'envoi : statut incertain, pas de renvoi (doublon évité)", _cut)
case("Mot de passe refusé : échec, retentée demain", _auth)

for r in results:
    print(r[0], r[1])
    if r[2]:
        print("    ", r[2])
fails = sum(1 for r in results if r[0] != "OK  ")
print(f"\n{len(results) - fails} réussis, {fails} échoués")
sys.exit(1 if fails else 0)
