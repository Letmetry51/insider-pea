"""Sonde : accès aux articles — balise de l'éditeur, texte réellement présent dans la page, mention abonnés (lecture seule)."""
import collections, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
import collect  # noqa: E402

arts = json.loads(Path("../data/grain/prive/actualites_brut.json").read_text(encoding="utf-8"))["articles"]
par = collections.defaultdict(list)
for a in sorted(arts, key=lambda a: a["date"], reverse=True):
    par[a.get("source") or "?"].append(a)
ech = [a for s, l in par.items() for a in l[:2]][:160]
TAG = re.compile(r"<(script|style|nav|header|footer|aside|form|noscript)\b.*?</\1>", re.S | re.I)
P = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S | re.I)
ABO = re.compile(r"réservée? (?:aux|à nos) abonnés|pour lire la suite|subscribe to (?:continue|read)|subscribers? only|"
                 r"sign in to read|log ?in to read|to read the full|create a free account|inscrivez-vous gratuitement", re.I)

def mots(html):
    h = TAG.sub(" ", html)
    t = " ".join(re.sub(r"<[^>]+>", " ", x) for x in P.findall(h))
    return len(re.findall(r"\w{2,}", t))

def voir(a):
    url = a.get("url_directe") or a["url"]
    try:
        if "news.google.com" in url:
            url = collect.gn_lien(url) or url
        r = requests.get(url, headers=collect.UA, timeout=15)
        ld = collect.ACCES_LD.findall(r.text)
        m = ABO.findall(r.text)
        return f"{a.get('source')[:28]:28} | {a.get('acces')!s:8} | {r.status_code} ld={ld[:2]} mots={mots(r.text):5} abo={sorted(set(x.lower() for x in m))[:2]} | {url[:80]}"
    except Exception as e:
        return f"{a.get('source')[:28]:28} | {a.get('acces')!s:8} | ERR {type(e).__name__} | {url[:80]}"

t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    out = sorted(ex.map(voir, ech))
out.append(f"{len(ech)} articles en {time.time() - t0:.0f} s")
Path("out").mkdir(exist_ok=True); Path("out/acces2.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
