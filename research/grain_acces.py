"""Sonde : pour un échantillon d'articles de la revue de presse, l'article est-il lisible en entier ? (lecture seule)"""
import json, re, sys, time, collections
from pathlib import Path
from urllib.parse import quote
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
from collect import UA  # noqa: E402

arts = json.loads(Path("../data/grain/prive/actualites_brut.json").read_text(encoding="utf-8"))["articles"]
out = []
MARQ = re.compile(r"isAccessibleForFree\"?\s*[:=]\s*\"?(false|true)|réservé(?:e|s)? aux abonnés|contenu réservé|article réservé|"
                  r"réservé à nos abonnés|pour lire la suite|subscribe to (?:continue|read)|subscribers? only|premium content|"
                  r"paywall|piano|tinypass|poool|abonnez-vous pour", re.I)

def decode_gn(url):
    i = url.split("/articles/")[1].split("?")[0]
    r = requests.get(f"https://news.google.com/rss/articles/{i}", headers=UA, timeout=15)
    sg = re.search(r'data-n-a-sg="([^"]+)"', r.text); ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
    if not (sg and ts):
        return None, f"pas de signature (HTTP {r.status_code})"
    req = [[["Fbv4je", json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], i, int(ts.group(1)), sg.group(1)]), None, "generic"]]]
    r = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute", headers={**UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                      data="f.req=" + quote(json.dumps(req)), timeout=15)
    try:
        dec = json.loads(json.loads(r.text.split("\n\n")[1])[0][2])[1]
        return dec, "ok"
    except Exception as e:
        return None, f"décodage : {r.status_code} {str(e)[:60]}"

parsrc = collections.defaultdict(list)
for a in arts:
    parsrc[a.get("source") or "?"].append(a)
ech = []
for s, l in sorted(parsrc.items(), key=lambda x: -len(x[1])):
    ech += l[:3] if s in ("Terre-net", "Réussir", "La France Agricole", "CMB News", "Web-agri", "Agri-mutuel") else l[:1]
t0 = time.time()
for a in ech[:70]:
    url = a["url"]; note = ""
    if "news.google.com" in url:
        url, note = decode_gn(url)
        time.sleep(0.5)
    if not url:
        out.append(f"{a.get('source')} | GN {note} | {a['titre'][:60]}"); continue
    try:
        r = requests.get(url, headers=UA, timeout=15)
        m = sorted(set(x.group(0)[:40].lower() for x in MARQ.finditer(r.text)))
        out.append(f"{a.get('source')} | {r.status_code} {len(r.text)//1000}ko | {m[:6]} | {url[:90]}")
    except Exception as e:
        out.append(f"{a.get('source')} | ERR {type(e).__name__} | {url[:90]}")
out.append(f"durée {time.time() - t0:.0f} s pour {len(ech[:70])} articles")
Path("out").mkdir(exist_ok=True); Path("out/acces.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
