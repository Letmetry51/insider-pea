"""
Euro Signal — archive permanente des résultats publiés et des rachats d'actions (exécuté après build.mjs).

build.mjs ne garde que 30 mois d'événements dans data/euro-signal-state.json. Ce script recopie chaque soir
tout ce qu'il y trouve dans data/history/events.json.gz, sans jamais rien effacer, pour pouvoir tester
plus tard la convergence « achat de dirigeant + rachat + bons résultats » sur un historique long.

Sans regard vers le futur : un élément est enregistré tel qu'il a été vu la PREMIÈRE fois (jamais réécrit),
avec « seen » = date de cette première observation ; « lastSeen » est mis à jour à chaque passage.
"""
import gzip
import io
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "euro-signal-state.json"
ARCH = ROOT / "data" / "history" / "events.json.gz"
KINDS = ("buybacks", "results")


def load_archive():
    try:
        with gzip.open(ARCH, "rt", encoding="utf-8") as f:
            a = json.load(f)
        return a if isinstance(a, dict) else {}
    except FileNotFoundError:
        return {}


def save_archive(arch):
    raw = json.dumps(arch, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:  # mtime=0 : fichier identique si rien n'a changé (pas de commit inutile)
        g.write(raw)
    data = buf.getvalue()
    if ARCH.exists() and ARCH.read_bytes() == data:
        return False
    ARCH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARCH.with_name(ARCH.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(ARCH)
    return True


def merge(arch, events, today):
    new = {k: 0 for k in KINDS}
    for isin, e in (events or {}).items():
        if not isinstance(e, dict):
            continue
        a = arch.setdefault(isin, {k: {} for k in KINDS})
        for kind in KINDS:
            bucket = a.setdefault(kind, {})
            for x in e.get(kind) or []:
                if not isinstance(x, dict) or not x.get("id"):
                    continue
                if x["id"] in bucket:
                    bucket[x["id"]]["lastSeen"] = today
                else:
                    bucket[x["id"]] = dict(x, seen=today, lastSeen=today)
                    new[kind] += 1
    return new


def main():
    try:
        events = json.loads(STATE.read_text(encoding="utf-8")).get("events") or {}
    except Exception as exc:
        print(f"Archive des événements : état Euro Signal illisible ({exc}), rien n'est modifié")
        return 0
    arch = load_archive()
    new = merge(arch, events, date.today().isoformat())
    changed = save_archive(arch)
    tot = {k: sum(len(v.get(k) or {}) for v in arch.values()) for k in KINDS}
    print(f"Archive des événements : +{new['results']} résultats, +{new['buybacks']} rachats ; "
          f"total {tot['results']} résultats, {tot['buybacks']} rachats sur {len(arch)} sociétés"
          + ("" if changed else " (inchangée)"))
    if tot["buybacks"] == 0:
        print("  ATTENTION : aucun rachat d'actions détecté par Euro Signal ; le signal « rachats » est vide à ce jour")
    return 0


if __name__ == "__main__":
    sys.exit(main())
