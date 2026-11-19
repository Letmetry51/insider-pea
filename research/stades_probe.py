"""Sonde : fichiers Céré'Obs « Stades de développement » (semis, levée…) et progression USDA du blé d'hiver."""
import io
import re
import requests
from python_calamine import CalamineWorkbook

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/124", "Accept": "application/json, text/plain, */*"})
B = "https://cereobs.franceagrimer.fr/cereobs-sp/api/public/publications/"
for cult in ["Blé tendre", "Orge d'hiver"]:
    L = [p for p in S.get(B + "getPublicationsStadeDev", params={"libelleCulture": cult}, timeout=60).json() if p["typePublication"]["format"] == "XLS"]
    print(f"\n== {cult} : {len(L)} fichiers XLS :", [p["libellePublication"] for p in L])
    for p in L:
        r = S.get(B + "rapportExcel", params={"idPublication": p["id"]}, timeout=60)
        print(f"\n##### {p['libellePublication']} stade={p.get('stade')}")
        rows = CalamineWorkbook.from_filelike(io.BytesIO(r.content)).get_sheet_by_index(0).to_python()
        for row in rows[:30]:
            if any(str(v).strip() for v in row):
                print(" | ".join(str(v) for v in row[:10]))
t = S.get("https://esmis.nal.usda.gov/publication/crop-progress", timeout=30).text
u = re.search(r'href="([^"]+prog\d+\.txt)"', t).group(1)
txt = S.get(requests.compat.urljoin("https://esmis.nal.usda.gov/", u), timeout=30).text
for titre in ["Winter Wheat Planted", "Winter Wheat Emerged"]:
    i = txt.find(titre)
    print("\n", txt[i:i + 300] if i >= 0 else f"pas de {titre}")
    j = txt.find("18 States", i)
    print(txt[j:j + 120] if i >= 0 else "")
