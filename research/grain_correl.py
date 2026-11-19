"""Sonde : corrélations entre pétrole, gaz, blé, maïs, soja et azote (urée), mensuelles depuis 2000 (Banque mondiale) et
hebdomadaires sur 5 ans (Yahoo, Euronext, urée France) ; avance/retard. Variations (pas niveaux) : deux prix qui montent
avec l'inflation ont des niveaux corrélés sans lien réel. Lecture seule."""
import csv, json, math, sys, io, re
from datetime import date, timedelta
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
import os
os.chdir(Path(__file__).resolve().parent.parent)
import build  # noqa: E402
import collect  # noqa: E402
out = []
P = Path("data/grain/prive")


def corr(a, b):
    n = len(a)
    if n < 10:
        return None, n
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return (sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else None), n


def rendements(serie, dates):
    return {dates[i]: math.log(serie[dates[i]] / serie[dates[i - 1]]) for i in range(1, len(dates))
            if serie.get(dates[i]) and serie.get(dates[i - 1])}


def matrice(series, titre, lags=()):
    noms = list(series)
    dates = sorted(set.intersection(*[set(s) for s in series.values()]))
    rend = {k: rendements(series[k], dates) for k in noms}
    out.append(f"\n=== {titre} : {dates[0]} → {dates[-1]}, {len(dates)} points (corrélation des variations)")
    out.append(" " * 10 + "".join(f"{k[:8]:>9}" for k in noms))
    for a in noms:
        lig = f"{a[:9]:10}"
        for b in noms:
            ks = sorted(set(rend[a]) & set(rend[b]))
            c, n = corr([rend[a][k] for k in ks], [rend[b][k] for k in ks])
            lig += f"{c:9.2f}" if c is not None else "      —  "
        out.append(lig)
    for a, b, kmax in lags:
        ks = sorted(set(rend[a]) & set(rend[b]))
        res = []
        for k in range(0, kmax + 1):
            xs = [rend[a][ks[i]] for i in range(len(ks) - k)]
            ys = [rend[b][ks[i + k]] for i in range(len(ks) - k)]
            c, n = corr(xs, ys)
            res.append(f"{k}:{c:+.2f}")
        out.append(f"  {a} → {b} plus tard (décalage : corrélation) : " + "  ".join(res))


# 1) mensuel, Banque mondiale (téléchargé ici, avec pétrole et soja)
page = requests.get("https://www.worldbank.org/en/research/commodity-markets", headers=collect.UA, timeout=60).text
m = re.search(r"https?://[^\"'\s>]*CMO-Historical-Data-Monthly\.xlsx", page)
from openpyxl import load_workbook  # noqa: E402
wb = load_workbook(io.BytesIO(requests.get(m.group(0), headers=collect.UA, timeout=120).content), read_only=True, data_only=True)
grid = list(wb["Monthly Prices"].iter_rows(values_only=True))
hi = next(i for i, r in enumerate(grid) if r and any(isinstance(c, str) and c.strip().lower().startswith("crude oil, brent") for c in r))
head = [str(c or "").strip().lower().rstrip("* ").strip() for c in grid[hi]]
cols = {"pétrole": "crude oil, brent", "gaz UE": "natural gas, europe", "urée": "urea", "blé": "wheat, us hrw", "maïs": "maize", "soja": "soybeans"}
idx = {k: head.index(v) for k, v in cols.items()}
mens = {k: {} for k in cols}
for r in grid[hi + 1:]:
    if r and isinstance(r[0], str) and re.match(r"^\d{4}M\d{2}$", r[0]) and r[0] >= "2000M01":
        for k, i in idx.items():
            if isinstance(r[i], (int, float)) and r[i] > 0:
                mens[k][r[0]] = float(r[i])
matrice(mens, "Mensuel 2000-2026 (Banque mondiale, $)", lags=[("gaz UE", "urée", 4), ("pétrole", "urée", 4), ("urée", "blé", 4), ("pétrole", "maïs", 4), ("gaz UE", "blé", 4)])
recent = {k: {d: v for d, v in s.items() if d >= "2016M01"} for k, s in mens.items()}
matrice(recent, "Mensuel 2016-2026")

# 2) hebdomadaire sur 5 ans : Yahoo (pétrole, gaz, soja, maïs CBOT), Euronext (blé, maïs), urée France
y = json.loads((P / "yahoo.json").read_text(encoding="utf-8"))
rows = list(csv.DictReader(open(P / "euronext.csv", encoding="utf-8")))


def hebdo(serie):  # dernier cours de chaque semaine (vendredi)
    out_ = {}
    for d, v in sorted(serie.items()):
        dd = date.fromisoformat(d[:10])
        out_[(dd + timedelta(days=4 - dd.weekday())).isoformat()] = v
    return out_


s = {}
s["pétrole"] = hebdo((y.get("BZ=F") or {}).get("serie") or {})
s["gaz TTF"] = hebdo((y.get("TTF=F") or {}).get("serie") or {})
s["soja"] = hebdo((y.get("ZS=F") or {}).get("serie") or {})
d, v, *_ = build.continuous(rows, "EBM"); s["blé Ex"] = hebdo(dict(zip(d, v)))
d, v, *_ = build.continuous(rows, "EMA"); s["maïs Ex"] = hebdo(dict(zip(d, v)))
u = {r["date"]: float(r["price"]) for r in csv.DictReader(open(P / "fert_fr.csv", encoding="utf-8")) if r["product"] == "uree" and r.get("price")}
s["urée FR"] = hebdo(u)
debut = (date.today() - timedelta(days=5 * 365)).isoformat()
s = {k: {d_: x for d_, x in v_.items() if d_ >= debut} for k, v_ in s.items()}
out.append("\nNombre de semaines par série : " + ", ".join(f"{k} {len(v_)}" for k, v_ in s.items()))
matrice(s, "Hebdomadaire, 5 ans (€ et $)", lags=[("gaz TTF", "urée FR", 8), ("pétrole", "urée FR", 8), ("urée FR", "blé Ex", 6), ("gaz TTF", "blé Ex", 6)])

Path("research/out").mkdir(exist_ok=True)
Path("research/out/correl.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
