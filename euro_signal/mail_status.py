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
        if not isinstance(cur, dict) or cur.get("date") != today or not isinstance(cur.get("parts"), dict):
            cur = {"date": today, "parts": {}}
        at = datetime.now(timezone.utc).isoformat()
        cur["at"] = at
        cur["parts"][part] = {"ok": bool(ok), "detail": str(detail or "")[:200], "at": at}
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(FILE)
    except Exception as e:  # noqa: BLE001
        print("État des emails non enregistré :", type(e).__name__)
