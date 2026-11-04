"""
Euro Signal — état des échanges avec Gmail du soir : data/diagnostics/mail.json, publié avec le site.

Un envoi Gmail en échec (mot de passe d'application révoqué, compte bloqué) ne peut pas être signalé par email : c'est le même
canal. La garde du calcul du soir (.github/workflows/watchdog.yml) lit ce fichier au petit matin et échoue s'il signale une panne ;
GitHub prévient alors le propriétaire du dépôt par sa propre notification, sans passer par Gmail.

Fichier public : aucune adresse, aucune donnée personnelle (ni position, ni nombre de positions), seulement le type d'erreur.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "data" / "diagnostics" / "mail.json"


def record(part, ok, detail=""):
    """Note le résultat d'un échange avec Gmail (« alertes », « controle », « positions ») ; jamais bloquant."""
    try:
        today = date.today().isoformat()
        try:
            cur = json.loads(FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cur = {}
        if not isinstance(cur, dict) or not isinstance(cur.get("parts"), dict):
            cur = {"parts": {}}
        now = datetime.now(timezone.utc)

        def fresh(p):
            try:
                return (now - datetime.fromisoformat(str(p.get("at")).replace("Z", "+00:00"))).total_seconds() < 20 * 3600
            except (AttributeError, TypeError, ValueError):
                return False
        # échanges d'un calcul précédent (plus de 20 heures) retirés ; ceux du calcul en cours gardés, même s'il passe minuit UTC
        # (jusqu'au 04/11/2026 : tout était effacé au changement de date, un échec Gmail noté à 23 h 58 disparaissait à 0 h 01)
        cur["parts"] = {k: v for k, v in cur["parts"].items() if isinstance(v, dict) and fresh(v)}
        cur["date"] = today
        at = now.isoformat()
        cur["at"] = at
        cur["parts"][part] = {"ok": bool(ok), "detail": str(detail or "")[:200], "at": at}
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(FILE)
    except Exception as e:  # noqa: BLE001
        print("État des emails non enregistré :", type(e).__name__)
