"""Grain Signal — changements d'échéance : cours des deux échéances autour de chaque raccord (blé, colza, maïs Euronext).

Pour chaque changement d'échéance de la série continue (5 jours ouvrés avant l'expiration), écart nouvelle − ancienne échéance
sur les 25 séances qui précèdent : un écart qui s'envole juste avant l'expiration (échéance proche peu liquide, livraison)
fausse l'ajustement s'il est pris le seul jour du raccord.   python grain_roll_probe.py      Résultat : out/grain_roll_probe.txt
"""
import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "grain_signal"))
import build  # noqa: E402

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)


rows = list(csv.DictReader(open(os.path.join(HERE, "..", "data", "grain", "prive", "euronext.csv"), encoding="utf-8")))
log(f"{len(rows)} lignes")
for prod in ("EBM", "ECO", "EMA"):
    by = {}
    for r in rows:
        if r["product"] == prod and build.fnum(r["settle"]) is not None:
            by.setdefault(r["date"], {})[r["maturity"]] = float(r["settle"])
    d, v, ref, rac, _ = build.continuous(rows, prod)
    dates = sorted(by)
    log(f"\n===== {prod} : {len(dates)} séances, {len(rac)} raccords")
    for x in rac[-12:]:
        i = dates.index(x["date"])
        old, new = x["de"], x["vers"]
        sp = []
        for k in range(max(0, i - 25), min(len(dates), i + 3)):
            q = by[dates[k]]
            if old in q and new in q:
                sp.append((dates[k], q[old], q[new], round(q[new] - q[old], 2)))
        ecarts = [s[3] for s in sp if s[0] < x["date"]]
        med = statistics.median(ecarts[-20:-5]) if len(ecarts) >= 10 else None
        log(f"-- {x['date']} {old} → {new} : ajustement retenu {x['ajustement']} ; médiane de l'écart 20 à 5 séances avant : {med}")
        log("   " + " | ".join(f"{s[0][5:]} {s[1]:.2f}/{s[2]:.2f} ({s[3]:+.2f})" for s in sp[-14:]))
open(os.path.join(OUT, "grain_roll_probe.txt"), "w", encoding="utf-8").write("\n".join(lines))
