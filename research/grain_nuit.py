"""Sonde : Chicago « depuis la clôture d'Euronext » (18 h 30 Paris → 7 h le lendemain), en données horaires, annonce-t-il mieux
la séance Euronext que la clôture de Chicago de la veille ? (lecture seule)"""
import csv, sys, bisect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import yfinance as yf
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
import os
os.chdir(Path(__file__).resolve().parent.parent)
import build  # noqa: E402
import indicators as ind  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
rows = list(csv.DictReader(open("data/grain/prive/euronext.csv", encoding="utf-8")))
out = []
for prod, nom, tk in (("EBM", "Blé", "ZW=F"), ("ECO", "Colza", "ZS=F"), ("EMA", "Maïs", "ZC=F")):
    d, v, *_ = build.continuous(rows, prod)
    h = yf.Ticker(tk).history(period="730d", interval="1h", auto_adjust=False)["Close"].dropna()
    ts = [t.to_pydatetime().astimezone(PARIS) for t in h.index]
    px = list(h.values)
    out.append(f"\n=== {nom} ({tk}) : {len(px)} barres horaires, {ts[0]:%Y-%m-%d} → {ts[-1]:%Y-%m-%d}")

    def prix_a(moment):
        i = bisect.bisect_right(ts, moment) - 1
        return (px[i], ts[i]) if i >= 0 else (None, None)

    res = {"nuit": {}, "veille": {}}
    sc = ind.score_serie(v)
    combo = {}
    for i in range(1, len(d)):
        jour, veille = datetime.fromisoformat(d[i]).replace(tzinfo=PARIS), datetime.fromisoformat(d[i - 1]).replace(tzinfo=PARIS)
        if veille < ts[0] + timedelta(days=2):
            continue
        p0, t0 = prix_a(veille.replace(hour=18, minute=30))
        p1, t1 = prix_a(jour.replace(hour=7, minute=0))
        if not p0 or not p1 or t1 <= t0 or (veille.replace(hour=18, minute=30) - t0) > timedelta(hours=6):
            continue
        r = v[i] / v[i - 1] - 1
        if r == 0:
            continue
        c = p1 / p0 - 1
        if abs(c) > 0.005 and sc[i - 1] is not None:
            t = ind.sens(sc[i - 1])
            cle = "technique d'accord" if (t == "haussière" and c > 0) or (t == "baissière" and c < 0) else ("technique neutre" if t == "neutre" else "technique contraire")
            n, k = combo.get(cle, (0, 0))
            combo[cle] = (n + 1, k + ((r > 0) == (c > 0)))
        # clôture de Chicago de la veille (référence actuelle de l'outil) : dernière barre ≤ 20 h 20 la veille vs ≤ 20 h 20 l'avant-veille
        pc1, _ = prix_a(veille.replace(hour=20, minute=20))
        pc0, _ = prix_a((veille - timedelta(days=1 if veille.weekday() else 3)).replace(hour=20, minute=20))
        for nomr, x in (("nuit", c), ("veille", (pc1 / pc0 - 1) if pc0 and pc1 else None)):
            if x is None:
                continue
            for s in (0, 0.0025, 0.005, 0.01):
                if abs(x) > s:
                    n, k = res[nomr].get(s, (0, 0))
                    res[nomr][s] = (n + 1, k + ((r > 0) == (x > 0)))
    for cle, (n, k) in sorted(combo.items()):
        out.append(f"  Chicago nuit > ±0,5 % et {cle} : même sens que Chicago {k}/{n} = {100 * k / n:.0f} %")
    for nomr, lab in (("nuit", "Chicago 18 h 30 → 7 h (depuis la clôture d'Euronext)"), ("veille", "clôture de Chicago de la veille (actuel)")):
        out.append(f"  {lab} :")
        for s, (n, k) in sorted(res[nomr].items()):
            out.append(f"    mouvement > ±{s * 100:.2f} % : même sens {k}/{n} = {100 * k / n:.0f} %")

Path("research/out").mkdir(exist_ok=True)
Path("research/out/nuit.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
