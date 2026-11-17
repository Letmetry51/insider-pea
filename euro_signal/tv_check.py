"""
Euro Signal — contrôle des comptes Yahoo par TradingView (17/11/2026) : le F-score de Piotroski de chaque société du classement
(calculé par le moteur sur les comptes Yahoo) comparé à celui que TradingView calcule sur ses propres comptes.

Simple contrôle, jamais utilisé par le classement (barème gelé jusqu'à la revue du 31/01/2027) : un écart de 3 points ou plus
sur une société de la sélection, des 10 🎯 ou des 10 💎 signale des comptes à vérifier (erreur de Yahoo, exercice différent,
définition différente d'un critère). Sonde du 17/11/2026 sur 1 176 sociétés : 38 % identiques, 83 % à un point près, 3 % d'écarts
de 3 points ou plus ; TradingView est en moyenne un peu plus sévère.

Lit data/euro-signal.json (classement du soir) et data/tradingview.json (scrapers/tradingview.py) ; écrit
data/diagnostics/fscore-tv.json, affiché dans l'onglet Aide (« Contrôle automatique »). Sans données TradingView ce soir :
fichier écrit avec « available » à false, rien d'autre ne change.

  python euro_signal/tv_check.py
"""
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
GAP = 3  # écart à partir duquel les comptes sont « à vérifier »


def read(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def compare(rank, tv_items):
    """Classement du soir (rank de euro-signal.json) et items TradingView → rapport (dictionnaire sérialisable)."""
    rows = [r for r in (rank or {}).get("rows") or [] if isinstance(r, dict)]
    watched = {}
    for i in ((rank or {}).get("selection") or {}).get("items") or []:
        if isinstance(i, dict) and i.get("key"):
            watched.setdefault(i["key"], "sélection")
    for lst, tag in (((rank or {}).get("pick10"), "10 🎯"), ((rank or {}).get("value10"), "10 💎")):
        for k in lst or []:
            if isinstance(k, str):
                watched.setdefault(k, tag)
    diffs, check = Counter(), []
    for r in rows:
        f9, tv = r.get("f9"), (tv_items or {}).get(r.get("sym") or "")
        f9_tv = tv[6] if isinstance(tv, list) and len(tv) > 6 else None
        if not isinstance(f9, int) or isinstance(f9, bool) or not isinstance(f9_tv, int) or isinstance(f9_tv, bool):
            continue
        d = f9_tv - f9
        diffs[d] += 1
        if abs(d) >= GAP and r.get("key") in watched:
            check.append({"sym": r.get("sym"), "name": r.get("name"), "list": watched[r["key"]], "f9": f9, "tv": f9_tv,
                          "fy": tv[7] if len(tv) > 7 else None})
    n = sum(diffs.values())
    order = {"sélection": 0, "10 🎯": 1, "10 💎": 2}
    check.sort(key=lambda c: (order.get(c["list"], 9), -abs(c["tv"] - c["f9"])))
    return {"compared": n, "same": diffs[0], "within1": sum(v for k, v in diffs.items() if abs(k) <= 1),
            "gap": GAP, "gaps": sum(v for k, v in diffs.items() if abs(k) >= GAP),
            "meanDiff": round(sum(k * v for k, v in diffs.items()) / n, 2) if n else None,
            "watched": len(watched), "check": check}


def main():
    es, tv = read(DATA / "euro-signal.json"), read(DATA / "tradingview.json")
    today = datetime.now(timezone.utc).date().isoformat()
    ok = isinstance(tv, dict) and tv.get("date") == today and isinstance(tv.get("items"), dict) and tv["items"]
    out = {"date": today, "available": bool(ok)}
    if ok and isinstance(es, dict):
        out.update(compare(es.get("rank"), tv["items"]))
    (DATA / "diagnostics").mkdir(parents=True, exist_ok=True)
    (DATA / "diagnostics" / "fscore-tv.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if not out["available"]:
        print("F-score TradingView : pas de données TradingView ce soir, contrôle sauté")
    else:
        print(f"F-score Euro Signal / TradingView : {out.get('compared', 0)} sociétés comparées, {out.get('same', 0)} identiques, "
              f"{out.get('within1', 0)} à un point près ; à vérifier : "
              + (", ".join(f"{c['sym']} ({c['list']}, {c['f9']} contre {c['tv']})" for c in out.get("check", [])) or "aucune"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
