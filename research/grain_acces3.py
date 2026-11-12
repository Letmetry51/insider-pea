"""Sonde : accès de chaque article avec la règle en place (lecture seule)."""
import collections, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
import collect  # noqa: E402

arts = json.loads(Path("../data/grain/prive/actualites_brut.json").read_text(encoding="utf-8"))["articles"]
pub = {a["id"] for a in json.loads(Path("../data/grain/actualites.json").read_text(encoding="utf-8")).get("articles", [])}
arts = [a for a in arts if a["id"] in pub]  # seulement les articles publiés sur la page
sites = {s: k for k, l in (collect.CFG["actualites"].get("acces") or {}).items() if k in ("entier", "abonnes") for s in l}
t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(lambda a: (a.get("source") or "?", collect.acces_article(a, sites)[0]), arts))
par = collections.defaultdict(collections.Counter)
for s, acc in res:
    par[s][acc] += 1
out = [f"{s[:34]:34} {dict(c)}" for s, c in sorted(par.items(), key=lambda x: -sum(x[1].values()))]
tot = collections.Counter(acc for _, acc in res)
out.append(f"total {dict(tot)} — {len(arts)} articles publiés en {time.time() - t0:.0f} s")
Path("out").mkdir(exist_ok=True); Path("out/acces3.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
