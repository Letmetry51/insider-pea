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
d = Path(tempfile.mkdtemp())
H.DIAG, H.SENT = d, d / "health-sent.json"
(d / "quality.json").write_text(json.dumps({"issues": [], "cov": {}}))
(d / "ui-check.json").write_text(json.dumps({"summary": {}, "problems": [], "jsErrors": []}))
check(H.main() == 0 and not H.SENT.exists(), "rien à signaler : pas d'envoi")
print("\n" + ("tous réussis" if ok else "des tests ont échoué"))
sys.exit(0 if ok else 1)
