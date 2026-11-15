"""Sonde : fiabilité de l'orientation selon l'heure du dernier cours de Chicago pris en compte (7 h, 8 h, 9 h, 10 h 30), même
calcul que le matin (decisions.chicago_nuit) sur les cours horaires gardés. Lecture seule."""
import csv, json, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
import os
os.chdir(Path(__file__).resolve().parent.parent)
import build  # noqa: E402
import collect  # noqa: E402
import decisions as dec  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
p = Path("data/grain/prive/chicago_horaire.json")
if not p.exists():
    collect.PRIV.mkdir(parents=True, exist_ok=True)
    collect.collect_chicago_horaire()
hor = json.loads(p.read_text())
rows = list(csv.DictReader(open("data/grain/prive/euronext.csv", encoding="utf-8")))
out = []
for cult, prod in (("ble", "EBM"), ("colza", "ECO"), ("mais", "EMA")):
    barres = dec.barres_valides(hor.get(dec.OUVERTURE_CHICAGO[cult]))
    d, v, *_ = build.continuous(rows, prod)
    out.append(f"\n=== {cult} ({len(barres)} barres)")
    for hh in ("07:00", "08:00", "09:00", "10:00", "10:45"):
        res = {"05": [0, 0], "1": [0, 0]}
        for i in range(1, len(d)):
            if v[i] == v[i - 1]:
                continue
            t = datetime.fromisoformat(d[i] + "T" + hh).replace(tzinfo=PARIS).timestamp()
            c = dec.chicago_nuit(barres, d[i - 1], t)
            m = dec.ouverture(c)["mesurable"]
            if not m:
                continue
            for k in (("05", "1") if m == "1" else ("05",)):
                res[k][0] += 1
                res[k][1] += (v[i] > v[i - 1]) == (c > 0)
        out.append(f"  dernier cours à {hh} : > ±0,5 % {res['05'][1]}/{res['05'][0]} = {100 * res['05'][1] / max(1, res['05'][0]):.0f} % ; "
                   f"> ±1 % {res['1'][1]}/{res['1'][0]} = {100 * res['1'][1] / max(1, res['1'][0]):.0f} %")
Path("research/out").mkdir(exist_ok=True)
Path("research/out/heure.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
