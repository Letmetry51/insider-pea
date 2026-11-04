"""
Tests hors ligne de l'email de contrôle du soir : rien quand tout va bien, constats listés sinon, contrôle manquant signalé.

  python euro_signal/test_health.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import send_health as H  # noqa: E402

ok = True


def check(cond, name):
    global ok
    print(("OK   " if cond else "ÉCHEC ") + name)
    ok = ok and cond


check(H.build({"issues": []}, {"summary": {}, "problems": [], "jsErrors": []}) == [], "tout va bien : aucun constat, aucun email")
b = H.build({"issues": ["✖ baisse anormale : comptes annuels 1500 → 988 (−34 %)"]},
            {"summary": {"texte illisible": 2}, "problems": [{"where": "Barco", "detail": "nullnull"}], "jsErrors": [{"message": "kvNum is not defined"}]})
check(len(b) == 4 and b[0].startswith("✖") and "JavaScript" in b[3], "baisse, affichage et erreur JavaScript listés")
check(H.build(None, None)[0].startswith("✖") and len(H.build(None, None)) == 2, "contrôles absents signalés")
steps = {"s1": {"outcome": "success", "conclusion": "success"}, "s3b": {"outcome": "failure", "conclusion": "success"},
         "s5b": {"outcome": "failure", "conclusion": "failure"}, "x": {"outcome": "skipped"}}
b = H.build({"issues": [], "date": "2026-10-20"}, {"summary": {}, "problems": [], "jsErrors": []}, steps, "2026-10-20")
check(b == ["✖ Étape « 3b. Secteurs et fiches sociétés » en échec ce soir", "✖ Étape « 5b. Calcul Euro Signal » en échec ce soir"],
      "étapes en échec signalées, même poursuivies (continue-on-error), dans l'ordre du calcul")
b = H.build({"issues": ["⚠ x"], "date": "2026-10-19"}, {"summary": {}, "problems": [], "jsErrors": []}, None, "2026-10-20")
check(len(b) == 1 and "arrêté avant le contrôle" in b[0], "contrôle de la veille : calcul arrêté avant la fin, signalé")
check(H.failed_steps(None) == [] and H.failed_steps({"a": None}) == [], "résumé des étapes absent ou abîmé : rien")
check(H.failed_steps({"s7": {"outcome": "cancelled"}}) == [("s7", H.STEP_LABELS["s7"])], "étape interrompue (job coupé) : signalée")
# calcul parti en retard qui passe minuit UTC entre le contrôle (23 h 50) et l'email (0 h 05) : contrôle de ce soir, pas de la veille
from datetime import datetime, timedelta, timezone  # noqa: E402
now = datetime.now(timezone.utc)
b = H.build({"issues": ["⚠ x"], "date": "2026-10-19", "at": (now - timedelta(minutes=15)).isoformat()},
            {"summary": {}, "problems": [], "jsErrors": []}, None, "2026-10-20")
check(b == ["⚠ x"], "contrôle écrit avant minuit UTC : ses constats sont envoyés (pas « calcul arrêté »)")
b = H.build({"issues": ["⚠ x"], "date": "2026-10-19", "at": (now - timedelta(hours=30)).isoformat()},
            {"summary": {}, "problems": [], "jsErrors": []}, None, "2026-10-20")
check(len(b) == 1 and "arrêté avant le contrôle" in b[0], "contrôle d'un calcul précédent (30 heures) : calcul arrêté, signalé")
import mail_status as M  # noqa: E402
dm = Path(tempfile.mkdtemp())
M.FILE = dm / "mail.json"
M.FILE.write_text(json.dumps({"date": "2026-10-19", "parts": {
    "alertes": {"ok": False, "detail": "SMTPAuthenticationError", "at": (now - timedelta(minutes=10)).isoformat()},
    "positions": {"ok": False, "detail": "ancien", "at": (now - timedelta(hours=30)).isoformat()}}}))
M.record("controle", True)
mp = json.loads(M.FILE.read_text())["parts"]
check(set(mp) == {"alertes", "controle"} and not mp["alertes"]["ok"],
      "état Gmail : échec noté avant minuit UTC gardé, échange d'un calcul précédent retiré")
d = Path(tempfile.mkdtemp())
H.DIAG, H.SENT = d, d / "health-sent.json"
(d / "quality.json").write_text(json.dumps({"issues": [], "cov": {}}))
(d / "ui-check.json").write_text(json.dumps({"summary": {}, "problems": [], "jsErrors": []}))
check(H.main() == 0 and not H.SENT.exists(), "rien à signaler : pas d'envoi")
print("\n" + ("tous réussis" if ok else "des tests ont échoué"))
sys.exit(0 if ok else 1)
