"""Sonde 3 : contenu des publications Céré'Obs (Excel national, tableau de la semaine)."""
import io
import re
import collections
import requests
import openpyxl

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/124", "Accept": "application/json, text/plain, */*"})
B = "https://cereobs.franceagrimer.fr/cereobs-sp/"
idx = S.get(B, timeout=30).text
js = S.get(B + re.search(r'src="(main-es2015[^"]+\.js)"', idx).group(1), timeout=60).text
for nom in ["getPublicationsBySemaineObservation", "getPublicationsCondCulture", "getPublicationParDerniereSemaine", "initHttpParams(e,t,i,n,r)"]:
    for m in list(re.finditer(re.escape(nom), js))[:2]:
        print(f"\n=== {nom} ===\n", js[max(0, m.start() - 300): m.end() + 400])

pubs = S.get(B + "api/public/publications/getPublicationParDerniereSemaine", timeout=60).json()
c = collections.Counter((p["typePublication"]["libelleLongTypePublication"], p["typePublication"]["format"], bool(p.get("region")), bool(p.get("culture")), bool(p.get("conditionCulture"))) for p in pubs)
for k, v in c.most_common():
    print(v, k)
nat = [p for p in pubs if not p.get("region") and not p.get("zpc")]
for p in nat[:40]:
    print(p["id"], p["libellePublication"], p["typePublication"]["libelleLongTypePublication"], (p.get("culture") or {}).get("libelleCulture"), p.get("conditionCulture"))
cc = [p for p in pubs if p.get("conditionCulture")]
if cc:
    print("EX conditionCulture:", {k: cc[0][k] for k in ("libellePublication", "conditionCulture", "culture", "region")})


def montre(r, titre):
    print(f"\n##### {titre} -> {r.status_code} {r.headers.get('content-type')} {r.headers.get('content-disposition')} {len(r.content)} o")
    if r.ok and r.content[:2] == b"PK":
        wb = openpyxl.load_workbook(io.BytesIO(r.content), data_only=True)
        for ws in wb.worksheets[:6]:
            print(f"--- feuille {ws.title} {ws.max_row}x{ws.max_column}")
            for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 45), values_only=True):
                if any(v is not None for v in row):
                    print(" | ".join("" if v is None else str(v) for v in row[:16]))
    else:
        print(r.content[:300])


montre(S.get(B + "api/public/publications/rapportExcel", params={"idPublication": nat[0]["id"]}, timeout=60), "rapportExcel national")
sem = nat[0]["semaineObservation"]["id"]
montre(S.get(B + "api/public/publications/tableau", params={"semaineObservation": sem}, timeout=60), "tableau semaine")
