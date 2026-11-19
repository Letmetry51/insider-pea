"""Sonde : sources de l'état des cultures (FranceAgriMer Céré'Obs, USDA Crop Progress)."""
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
S = requests.Session()
S.headers.update(UA)


def get(u, **kw):
    try:
        r = S.get(u, timeout=30, **kw)
        print(f"GET {u} -> {r.status_code} {r.headers.get('content-type')} {len(r.content)} o")
        return r
    except Exception as e:
        print(f"GET {u} -> ERREUR {e}")


base = "https://cereobs.franceagrimer.fr/cereobs-sp/"
r = get(base)
if r is not None and r.ok:
    print(r.text[:1500])
    js = re.findall(r'src="([^"]+\.js)"', r.text)
    print("JS:", js)
    vus = set()
    for j in js:
        u = requests.compat.urljoin(base, j)
        rj = get(u)
        if rj is None or not rj.ok:
            continue
        for m in sorted(set(re.findall(r'["\'`]((?:/|\.\./|https?://)[^"\'`\s]{0,80}(?:api|rest|public|export|publication|rapport|csv|xls)[^"\'`\s]{0,80})["\'`]', rj.text))):
            if m not in vus:
                vus.add(m)
                print("  chemin:", m)
        for m in sorted(set(re.findall(r'["\'`](api/[^"\'`\s]{0,100})["\'`]', rj.text)))[:80]:
            print("  api:", m)
for u in ["https://cereobs.franceagrimer.fr/cereobs-sp/api/public/publications",
          "https://cereobs.franceagrimer.fr/cereobs-sp/api/publications",
          "https://cereobs.franceagrimer.fr/cereobs-sp/#/publications",
          "https://cereobs.franceagrimer.fr/"]:
    rr = get(u)
    if rr is not None and rr.ok:
        print(rr.text[:600])

# USDA
r = get("https://esmis.nal.usda.gov/publication/crop-progress")
if r is not None and r.ok:
    txts = re.findall(r'href="([^"]+prog\d+\.txt)"', r.text)
    print("TXT:", txts[:3])
    if txts:
        t = get(requests.compat.urljoin("https://esmis.nal.usda.gov/", txts[0]))
        if t is not None and t.ok:
            i = t.text.find("Winter Wheat Condition")
            print(t.text[i:i + 1200] if i >= 0 else "pas de tableau blé d'hiver")
