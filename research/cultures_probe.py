"""Sonde 4 : conditions de culture Céré'Obs (liste par culture, fichier XLS)."""
import io
import requests
import xlrd

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/124", "Accept": "application/json, text/plain, */*"})
B = "https://cereobs.franceagrimer.fr/cereobs-sp/"
dern = None
for cult in ["Blé tendre", "Orge d'hiver", "Orge de printemps", "Blé dur", "Maïs grain"]:
    r = S.get(B + "api/public/publications/getPublicationsCondCulture", params={"libelleCulture": cult}, timeout=60)
    print(f"\n== {cult} -> {r.status_code} {len(r.content)} o")
    if not r.ok:
        print(r.text[:200]); continue
    L = r.json()
    print(len(L), "publications")
    for p in L[:4] + L[-3:]:
        print("  ", p["id"], p["libellePublication"], p["typePublication"]["format"], p["semaineObservation"]["libelleSemaine"], p.get("datePublication"), p.get("conditionCulture"))
    xls = [p for p in L if p["typePublication"]["format"] == "XLS"]
    if xls and dern is None:
        dern = max(xls, key=lambda p: p["semaineObservation"]["dateFin"])
if dern:
    r = S.get(B + "api/public/publications/rapportExcel", params={"idPublication": dern["id"]}, timeout=60)
    print(f"\n##### {dern['libellePublication']} -> {r.status_code} {r.headers.get('content-type')} {len(r.content)} o")
    wb = xlrd.open_workbook(file_contents=r.content)
    for sh in wb.sheets()[:4]:
        print(f"--- {sh.name} {sh.nrows}x{sh.ncols}")
        for i in range(min(sh.nrows, 60)):
            row = sh.row_values(i)
            if any(str(v).strip() for v in row):
                print(" | ".join(str(v) for v in row[:14]))
