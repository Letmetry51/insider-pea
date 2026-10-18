"""
Contrôle gratuit du biais du survivant : notre effet momentum (cours des sociétés encore cotées) comparé au facteur momentum
européen de Kenneth French (Dartmouth), calculé sur toutes les sociétés, y compris disparues. Données publiques, mensuelles, en USD
(sans effet sur un écart gagnants − perdants). Si nos chiffres sont proches, le biais du survivant pèse peu sur l'effet mesuré.
"""
import csv, io, zipfile
from pathlib import Path
import numpy as np, requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)
URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Europe_Mom_Factor_CSV.zip"
lines = []
def log(s): print(s, flush=True); lines.append(s)

z = zipfile.ZipFile(io.BytesIO(requests.get(URL, timeout=120, headers={"User-Agent": "Mozilla/5.0"}).content))
txt = z.read(z.namelist()[0]).decode("latin-1")
fr = {}
for row in csv.reader(io.StringIO(txt)):
    if len(row) >= 2 and row[0].strip().isdigit() and len(row[0].strip()) == 6:
        try: fr["%s-%s" % (row[0].strip()[:4], row[0].strip()[4:])] = float(row[1]) / 100
        except ValueError: pass
    elif fr and row and row[0].strip() and not row[0].strip().isdigit():
        break  # fin du tableau mensuel (suivent les moyennes annuelles)
ours = {r["month"]: r for r in csv.DictReader(open(ROOT / "our_wml.csv"))}
common = sorted(set(fr) & set(ours))
log("Facteur momentum Europe (French) : %d mois, de %s à %s ; en commun avec nos données : %d mois (%s → %s)" % (len(fr), min(fr), max(fr), len(common), common[0], common[-1]))
def stats(ms):
    a = np.array([fr[m] for m in ms]); b = np.array([float(ours[m]["wml"]) for m in ms])
    return a.mean() * 12 * 100, b.mean() * 12 * 100, np.corrcoef(a, b)[0, 1], (a > 0).mean() * 100, (b > 0).mean() * 100
log("%-12s %20s %20s %12s" % ("période", "French (toutes)", "nous (survivantes)", "corrélation"))
for lab, a, b in [("1998-2008", "1998-01", "2008-12"), ("2009-2017", "2009-01", "2017-12"), ("2018-2026", "2018-01", "2026-12"), ("tout", "0000", "9999")]:
    ms = [m for m in common if a <= m <= b]
    if len(ms) < 24: continue
    f, o, c, pf, po = stats(ms)
    log("%-12s %+17.1f %%/an %+17.1f %%/an %12.2f   (mois positifs : %.0f %% / %.0f %%)" % (lab, f, o, c, pf, po))
(OUT / "french.txt").write_text("\n".join(lines) + "\n")
