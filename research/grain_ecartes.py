"""Liste les prix que le filtre des prix aberrants écarte sur les vrais historiques (lecture seule, rien n'est publié)."""
import csv, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
os.chdir(Path(__file__).resolve().parent.parent)
import build  # noqa: E402

out = []
def voir(nom, rows, cle, champ, **kw):
    keep = {id(r) for r in build.nettoyer(rows, cle, champ, **kw)}
    by = {}
    for r in rows:
        by.setdefault(cle(r), []).append(r)
    for k, v in by.items():
        v.sort(key=lambda r: r["date"])
        for i, r in enumerate(v):
            if id(r) not in keep:
                ctx = [(x["date"], x[champ]) for x in v[max(0, i - 2):i + 3]]
                out.append(f"{nom} {k} {r['date']} {r[champ]} | {ctx}")
    out.append(f"{nom} : {len(rows)} lignes, {len(rows) - len(keep)} écartées")

P = Path("data/grain/prive")
voir("euronext", list(csv.DictReader(open(P / "euronext.csv"))), lambda r: (r["product"], r["maturity"]), "settle")
voir("engrais", list(csv.DictReader(open(P / "fert_fr.csv"))), lambda r: (r["product"],), "price", saut=0.35)
par = {}
for r in csv.DictReader(open(P / "physique_hist.csv")):
    par[(r["date"], r["page"], r["place"])] = r
voir("physique (brut)", list(par.values()), lambda r: (r["page"], r["place"]), "prix")
ph = build.physique()
keep = {(r["date"], r["page"], r["place"]) for r in ph}
import re
for r in sorted(par.values(), key=lambda r: (r["page"], r["place"], r["date"])):
    if r["page"] == "orge_brassicole":
        out.append(f"  {r['date']} {r['place'][:30]:30} {r['prix']:>7} | {r['titre'][-40:]}")
out.append("redaté : " + str(sorted((r["date"], r["place"][:25], r["prix"]) for r in ph if r["page"] == "orge_brassicole")))
from datetime import date as _d
for k, o in build.orges(_d.today(), []).items():
    g = [r for r in o.get("graphique") or [] if r[1] is not None]
    out.append(f"{k} : {o.get('prix')} le {o.get('date')}, 5 derniers {g[-5:]}, var1j {round(g[-1][1] - g[-2][1], 2) if len(g) >= 2 else None}")
Path("out").mkdir(exist_ok=True)
Path("out/ecartes.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
