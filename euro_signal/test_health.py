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
d = Path(tempfile.mkdtemp())
H.DIAG, H.SENT = d, d / "health-sent.json"
(d / "quality.json").write_text(json.dumps({"issues": [], "cov": {}}))
(d / "ui-check.json").write_text(json.dumps({"summary": {}, "problems": [], "jsErrors": []}))
check(H.main() == 0 and not H.SENT.exists(), "rien à signaler : pas d'envoi")
print("\n" + ("tous réussis" if ok else "des tests ont échoué"))
sys.exit(0 if ok else 1)
