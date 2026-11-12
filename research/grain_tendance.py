"""Sonde : qu'est-ce qui annonce la séance Euronext du jour, avant l'ouverture ? (lecture seule)
Cible : variation de la séance D (règlement D / règlement de la séance précédente, série ajustée aux changements d'échéance).
Indices connus avant 10 h 45 le jour D : clôture de Chicago de la veille (20 h 20, après la clôture d'Euronext à 18 h 30),
variation d'Euronext la veille, lecture technique de la veille, combinaisons."""
import csv, json, sys, bisect
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
import os
os.chdir(Path(__file__).resolve().parent.parent)  # noqa: E402
import build  # noqa: E402
import indicators as ind  # noqa: E402

P = Path("data/grain/prive")
rows = list(csv.DictReader(open(P / "euronext.csv", encoding="utf-8")))
y = json.loads((P / "yahoo_long.json").read_text(encoding="utf-8"))
yc = json.loads((P / "yahoo.json").read_text(encoding="utf-8"))
for k, v in yc.items():  # séances récentes
    if isinstance(v, dict) and isinstance(v.get("serie"), dict):
        y.setdefault(k, {"serie": {}}).setdefault("serie", {}).update(v["serie"])
out = []

def usd(tk):
    s = (y.get(tk) or {}).get("serie") or {}
    d = sorted(s)
    return d, [s[x] for x in d]

def taux(n, k):
    return f"{k}/{n} = {100 * k / n:.0f} %" if n else "—"

for prod, nom, tks in (("EBM", "Blé", ("ZW=F", "KE=F")), ("ECO", "Colza", ("ZL=F", "ZS=F")), ("EMA", "Maïs", ("ZC=F",))):
    d, v, *_ = build.continuous(rows, prod)
    sc = ind.score_serie(v)
    out.append(f"\n=== {nom} Euronext : {d[0]} → {d[-1]}, {len(d)} séances")
    hausses = sum(1 for i in range(1, len(v)) if v[i] > v[i - 1])
    out.append(f"séances en hausse (référence du hasard) : {taux(len(v) - 1, hausses)}")
    # variation de la veille → séance du jour
    for lab, cond in (("veille en hausse → hausse", lambda r0: r0 > 0), ("veille en baisse → baisse", lambda r0: r0 < 0)):
        n = k = 0
        for i in range(2, len(v)):
            r0, r1 = v[i - 1] / v[i - 2] - 1, v[i] / v[i - 1] - 1
            if cond(r0) and r1 != 0:
                n += 1
                k += (r1 > 0) == (r0 > 0)
        out.append(f"  {lab} : {taux(n, k)}")
    # technique de la veille
    for s in ("haussière", "baissière"):
        n = k = 0
        for i in range(1, len(v)):
            if sc[i - 1] is not None and ind.sens(sc[i - 1]) == s and v[i] != v[i - 1]:
                n += 1
                k += (v[i] > v[i - 1]) == (s == "haussière")
        out.append(f"  technique {s} la veille → même sens : {taux(n, k)}")
    # Chicago de la veille au soir
    for tk in tks:
        cd, cv = usd(tk)
        if len(cd) < 100:
            continue
        res = {}
        for i in range(1, len(d)):
            j = bisect.bisect_left(cd, d[i]) - 1  # dernière séance de Chicago avant le jour D
            if j < 1 or cd[j] < d[i - 1]:  # Chicago doit avoir clôturé après la séance Euronext précédente
                continue
            c = cv[j] / cv[j - 1] - 1
            r1 = v[i] / v[i - 1] - 1
            if r1 == 0 or c == 0:
                continue
            for seuil in (0, 0.005, 0.01, 0.02):
                if abs(c) > seuil:
                    n, k = res.get(seuil, (0, 0))
                    res[seuil] = (n + 1, k + ((r1 > 0) == (c > 0)))
        for seuil, (n, k) in sorted(res.items()):
            out.append(f"  {tk} veille {'> ±' + str(seuil * 100) + ' %' if seuil else '(tout)'} → même sens : {taux(n, k)}")
    # combinaison : Chicago (1er contrat) + technique + veille, vote
    cd, cv = usd(tks[0])
    tab = {}
    for i in range(2, len(d)):
        j = bisect.bisect_left(cd, d[i]) - 1
        if j < 1 or cd[j] < d[i - 1] or sc[i - 1] is None:
            continue
        c = cv[j] / cv[j - 1] - 1
        votes = (1 if c > 0.005 else -1 if c < -0.005 else 0) + (1 if sc[i - 1] >= 0.75 else -1 if sc[i - 1] <= -0.75 else 0)
        r1 = v[i] / v[i - 1] - 1
        if r1 == 0:
            continue
        n, k, s = tab.get(votes, (0, 0, 0.0))
        tab[votes] = (n + 1, k + (r1 > 0), s + r1)
    for vt, (n, k, s) in sorted(tab.items()):
        out.append(f"  vote Chicago + technique = {vt:+d} : hausse {taux(n, k)}, variation moyenne {100 * s / n:+.2f} %")
    # taille moyenne d'une séance
    ab = sorted(abs(v[i] / v[i - 1] - 1) for i in range(1, len(v)))
    out.append(f"  variation absolue médiane d'une séance : {100 * ab[len(ab) // 2]:.2f} %")

Path("research/out").mkdir(exist_ok=True)
Path("research/out/tendance.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
