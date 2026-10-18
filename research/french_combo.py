"""Momentum + valeur (Asness, Moskowitz, Pedersen 2013) sur l'Europe : facteurs gratuits de Kenneth French, toutes sociétés, 1990-2026."""
import csv, io, zipfile
from pathlib import Path
import numpy as np, requests
OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(exist_ok=True)
B = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
lines = []
def log(s): print(s, flush=True); lines.append(s)
def monthly(name, cols):
    z = zipfile.ZipFile(io.BytesIO(requests.get(B + name, timeout=120, headers={"User-Agent": "Mozilla/5.0"}).content))
    txt = z.read(z.namelist()[0]).decode("latin-1"); out = {}; hdr = None
    for row in csv.reader(io.StringIO(txt)):
        r = [c.strip() for c in row]
        if r and r[0] == "" and len(r) > 1 and hdr is None: hdr = r; continue
        if r and len(r[0]) == 6 and r[0].isdigit():
            out[r[0][:4] + "-" + r[0][4:]] = {c: float(r[hdr.index(c)]) / 100 for c in cols if hdr and c in hdr}
        elif out and r and r[0] and not r[0].isdigit(): break
    return out
m = monthly("Europe_Mom_Factor_CSV.zip", ["WML"]); f3 = monthly("Europe_3_Factors_CSV.zip", ["Mkt-RF", "SMB", "HML", "RF"])
ms = sorted(k for k in m if k in f3 and "WML" in m[k] and "HML" in f3[k])
log("Mois en commun : %d (%s → %s)" % (len(ms), ms[0], ms[-1]))
S = {"Momentum (gagnants − perdants)": np.array([m[k]["WML"] for k in ms]), "Valeur (bon marché − chères)": np.array([f3[k]["HML"] for k in ms])}
S["50 % momentum + 50 % valeur"] = (S["Momentum (gagnants − perdants)"] + S["Valeur (bon marché − chères)"]) / 2
S["Marché européen (au-delà du taux sans risque)"] = np.array([f3[k]["Mkt-RF"] for k in ms])
log("Corrélation momentum / valeur : %.2f" % np.corrcoef(S["Momentum (gagnants − perdants)"], S["Valeur (bon marché − chères)"])[0, 1])
yrs = np.array([int(k[:4]) for k in ms])
log("%-46s %10s %10s %10s %12s %14s" % ("", "%/an", "volat.", "rend/risque", "perte max", "pire année"))
for k, x in S.items():
    eq = np.cumprod(1 + x); dd = (eq / np.maximum.accumulate(eq) - 1).min()
    ann = {y: np.prod(1 + x[yrs == y]) - 1 for y in sorted(set(yrs)) if (yrs == y).sum() == 12}
    worst = min(ann, key=ann.get)
    log("%-46s %+9.1f %9.1f %10.2f %+11.0f %% %8.0f %% (%d)" % (k, x.mean() * 1200, x.std() * np.sqrt(12) * 100, x.mean() / x.std() * np.sqrt(12), dd * 100, ann[worst] * 100, worst))
for lab, a, b in [("1990-2008", 1990, 2008), ("2009-2017", 2009, 2017), ("2018-2026", 2018, 2026)]:
    sel = (yrs >= a) & (yrs <= b)
    log("%s : momentum %+.1f %%/an, valeur %+.1f, mélange %+.1f (rend/risque %.2f / %.2f / %.2f)" % (lab, *(S[k][sel].mean() * 1200 for k in list(S)[:3]), *(S[k][sel].mean() / S[k][sel].std() * np.sqrt(12) for k in list(S)[:3])))
(OUT / "combo.txt").write_text("\n".join(lines) + "\n")
